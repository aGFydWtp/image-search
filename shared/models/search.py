"""検索関連のデータモデル。"""

from pydantic import BaseModel, Field


class QueryFilters(BaseModel):
    """クエリ分解後のpayloadフィルタ条件。"""

    motif_tags: list[str] = []
    color_tags: list[str] = []


class QueryBoosts(BaseModel):
    """クエリ分解後のスコアブースト条件。"""

    brightness_min: float | None = Field(default=None, ge=0.0, le=1.0)


class ParsedQuery(BaseModel):
    """クエリパーサーの出力。"""

    semantic_query: str
    filters: QueryFilters
    boosts: QueryBoosts


class SearchRequest(BaseModel):
    """POST /api/artworks/search のリクエスト。"""

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=24, ge=1, le=100)


class SearchResultItem(BaseModel):
    """検索結果の個別アイテム。"""

    artwork_id: str
    title: str
    artist_name: str
    thumbnail_url: str
    score: float
    match_reasons: list[str]


class SearchResponse(BaseModel):
    """POST /api/artworks/search のレスポンス。"""

    parsed_query: ParsedQuery
    items: list[SearchResultItem]
