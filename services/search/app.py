"""Search Service FastAPIアプリケーション。"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from shared.models.ingestion import IndexRequest, IndexResponse
from shared.models.search import SearchRequest, SearchResponse
from shared.qdrant.repository import SearchFilters

logger = logging.getLogger(__name__)

# 依存注入用のグローバル（lifespan or テストで設定）
_query_parser = None
_embedding_client = None
_qdrant_repo = None
_reranker = None
_ingestion_service = None
_index_http_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリ起動時に全依存を初期化する。"""
    global _query_parser, _embedding_client, _qdrant_repo, _reranker
    global _ingestion_service, _index_http_client

    from qdrant_client import QdrantClient

    from services.ingestion.color_extractor import ColorExtractor
    from services.ingestion.image_preprocessor import ImagePreprocessor
    from services.ingestion.pipeline import IngestionService
    from services.search.query_parser import QueryParser
    from services.search.reranker import Reranker
    from shared.clients.embedding import EmbeddingClient
    from shared.clients.vlm import VLMClient
    from shared.config import Settings
    from shared.qdrant.repository import QdrantRepository
    from shared.taxonomy.mapper import TaxonomyMapper

    settings = Settings()

    # Qdrant
    qdrant_client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    _qdrant_repo = QdrantRepository(client=qdrant_client, settings=settings)
    _qdrant_repo.ensure_collection()

    # Clients
    _embedding_client = EmbeddingClient(settings=settings)
    vlm_client = VLMClient(settings=settings)

    # Search
    _query_parser = QueryParser()
    _reranker = Reranker()

    # Ingestion (for /internal/artworks/index)
    _ingestion_service = IngestionService(
        vlm_client=vlm_client,
        embedding_client=_embedding_client,
        qdrant_repo=_qdrant_repo,
        preprocessor=ImagePreprocessor(),
        color_extractor=ColorExtractor(),
        taxonomy_mapper=TaxonomyMapper(),
    )
    _index_http_client = httpx.Client(timeout=30.0)

    logger.info("Search Service initialized")
    yield

    # Cleanup
    _index_http_client.close()
    _embedding_client.close()
    vlm_client.close()
    logger.info("Search Service shutdown")


app = FastAPI(title="Image Search API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/artworks/search", response_model=SearchResponse)
def search_artworks(req: SearchRequest) -> SearchResponse:
    """自然言語クエリでアートワークを検索する。"""
    if _query_parser is None or _embedding_client is None or _qdrant_repo is None or _reranker is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # 1. クエリ分解
    parsed = _query_parser.parse(req.query)

    # 2. テキスト埋め込み生成
    try:
        query_vector = _embedding_client.embed_text(parsed.semantic_query)
    except Exception as e:
        logger.error("Embedding service error: %s", e)
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from e

    # 3. Qdrant prefilter + vector search
    filters = SearchFilters(
        motif_tags=parsed.filters.motif_tags,
        color_tags=parsed.filters.color_tags,
    )

    try:
        candidates = _qdrant_repo.search(
            query_vector=query_vector,
            filters=filters if filters.motif_tags or filters.color_tags else None,
            limit=req.limit,
        )
    except Exception as e:
        logger.error("Qdrant search error: %s", e)
        raise HTTPException(status_code=503, detail="Vector database unavailable") from e

    # 4. リランキング
    items = _reranker.rerank(candidates, parsed)

    return SearchResponse(parsed_query=parsed, items=items)


@app.post("/internal/artworks/index", response_model=IndexResponse)
def index_artwork(req: IndexRequest) -> IndexResponse:
    """個別アートワークをインジェスションパイプラインに投入する。"""
    if _ingestion_service is None or _qdrant_repo is None or _index_http_client is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # 1. 既存チェック（created/updated判定用）
    already_exists = _qdrant_repo.exists(req.artwork_id)

    # 2. 画像ダウンロード
    try:
        response = _index_http_client.get(str(req.image_url))
        response.raise_for_status()
        image_bytes = response.content
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            raise HTTPException(status_code=404, detail=f"Image not found: {req.image_url}") from e
        raise HTTPException(status_code=502, detail=f"Image download failed: {e}") from e
    except httpx.ConnectError as e:
        raise HTTPException(status_code=502, detail=f"Image download failed: {e}") from e

    # 3. インジェスションパイプライン実行
    success = _ingestion_service.process_artwork(
        artwork_id=req.artwork_id,
        image_bytes=image_bytes,
        image_url=str(req.image_url),
        title=req.title,
        artist_name=req.artist_name,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Ingestion pipeline failed")

    return IndexResponse(
        artwork_id=req.artwork_id,
        status="updated" if already_exists else "created",
    )


# 静的ファイル配信（APIルートの後に配置し、ルート優先順位を確保）
_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
else:
    logger.warning("Static files directory not found: %s — UI will not be served", _static_dir)
