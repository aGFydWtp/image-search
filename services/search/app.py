"""Search Service FastAPIアプリケーション。"""

import logging

import httpx
from fastapi import FastAPI, HTTPException

from shared.models.ingestion import IndexRequest, IndexResponse
from shared.models.search import SearchRequest, SearchResponse
from shared.qdrant.repository import SearchFilters

logger = logging.getLogger(__name__)

app = FastAPI(title="Image Search API", version="0.1.0")

# 依存注入用のグローバル（lifespan or テストで設定）
_query_parser = None
_embedding_client = None
_qdrant_repo = None
_reranker = None
_ingestion_service = None
_index_http_client = None


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
