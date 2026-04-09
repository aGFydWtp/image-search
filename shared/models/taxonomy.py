"""Taxonomy関連のデータモデル。"""

from pydantic import BaseModel, Field


class NormalizedTags(BaseModel):
    """TaxonomyMapper出力の正規化済みタグ。"""

    mood_tags: list[str]
    motif_tags: list[str]
    style_tags: list[str]
    subject_tags: list[str]
    freeform_keywords: list[str]
    color_tags: list[str]
    taxonomy_version: str = Field(min_length=1)
