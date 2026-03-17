"""画像前処理関連のデータモデル。"""

from pydantic import BaseModel, Field


class PreprocessedImage(BaseModel):
    """画像前処理の結果。"""

    normalized: bytes
    thumbnail: bytes
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect_ratio: float = Field(gt=0)
