"""VLM関連のデータモデル。"""

from pydantic import BaseModel


class VLMExtractionResult(BaseModel):
    """VLMによるメタデータ抽出結果。"""

    caption: str
    motif_candidates: list[str]
    style_candidates: list[str]
    subject_candidates: list[str]
    mood_candidates: list[str]
