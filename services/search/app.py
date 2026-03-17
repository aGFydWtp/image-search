"""Search Service FastAPIアプリケーション。"""

import logging

from fastapi import FastAPI, HTTPException

from shared.models.search import SearchRequest, SearchResponse
from shared.qdrant.repository import SearchFilters

logger = logging.getLogger(__name__)

app = FastAPI(title="Image Search API", version="0.1.0")

# 依存注入用のグローバル（lifespan or テストで設定）
_query_parser = None
_embedding_client = None
_qdrant_repo = None
_reranker = None


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
