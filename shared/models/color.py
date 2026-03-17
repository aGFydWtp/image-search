"""色抽出関連のデータモデル。"""

from pydantic import BaseModel, Field


class ColorInfo(BaseModel):
    """画像から抽出された色情報。"""

    color_tags: list[str]
    palette_hex: list[str]
    brightness_score: float = Field(ge=0.0, le=1.0)
    saturation_score: float = Field(ge=0.0, le=1.0)
    warmth_score: float = Field(ge=0.0, le=1.0)
