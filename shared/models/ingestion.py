"""インジェスション関連のデータモデル。"""

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field


class IndexRequest(BaseModel):
    """POST /internal/artworks/index のリクエスト。"""

    artwork_id: str = Field(min_length=1)
    image_url: AnyHttpUrl
    title: str = Field(min_length=1)
    artist_name: str = Field(min_length=1)


class IndexResponse(BaseModel):
    """POST /internal/artworks/index のレスポンス。"""

    artwork_id: str
    status: Literal["created", "updated"]
