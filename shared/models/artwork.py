"""アートワーク関連のデータモデル。"""

import re
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class ArtworkPayload(BaseModel):
    """Qdrant pointのpayloadとして保存するアートワークデータ。"""

    artwork_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    artist_name: str = Field(min_length=1)
    image_url: AnyHttpUrl
    thumbnail_url: AnyHttpUrl
    caption: str
    mood_tags: list[str]
    motif_tags: list[str]
    style_tags: list[str]
    subject_tags: list[str]
    freeform_keywords: list[str]
    color_tags: list[str]
    palette_hex: list[str]
    brightness_score: float = Field(ge=0.0, le=1.0)
    saturation_score: float = Field(ge=0.0, le=1.0)
    warmth_score: float = Field(ge=0.0, le=1.0)
    is_abstract: bool
    has_character: bool
    taxonomy_version: str = Field(min_length=1)
    ingested_at: datetime
    updated_at: datetime

    @field_validator("palette_hex")
    @classmethod
    def validate_hex_colors(cls, v: list[str]) -> list[str]:
        pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for color in v:
            if not pattern.match(color):
                raise ValueError(f"Invalid hex color: {color!r}")
        return v
