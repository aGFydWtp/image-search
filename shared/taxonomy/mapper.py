"""TaxonomyMapper: VLM出力の語彙揺れを正規化し、統制されたタグに変換する。"""

import json
import logging
from pathlib import Path

from shared.models.taxonomy import NormalizedTags
from shared.models.vlm import VLMExtractionResult

logger = logging.getLogger(__name__)

_DEFINITIONS_PATH = Path(__file__).parent / "definitions.json"


class TaxonomyMapper:
    """VLM出力を正規化済みタグに変換する。"""

    def __init__(self, definitions_path: Path = _DEFINITIONS_PATH) -> None:
        with open(definitions_path) as f:
            defs = json.load(f)

        self._version: str = defs["version"]
        self._motif_synonyms: dict[str, str] = defs["motif_synonyms"]
        self._motif_vocab: set[str] = set(defs["motif_vocabulary"])
        self._mood_synonyms: dict[str, str] = defs["mood_synonyms"]
        self._mood_vocab: set[str] = set(defs["mood_vocabulary"])
        self._style_synonyms: dict[str, str] = defs["style_synonyms"]
        self._style_vocab: set[str] = set(defs["style_vocabulary"])
        self._subject_synonyms: dict[str, str] = defs["subject_synonyms"]
        self._subject_vocab: set[str] = set(defs["subject_vocabulary"])
        self._stopwords: set[str] = set(defs["stopwords"])

    def normalize(self, raw: VLMExtractionResult) -> NormalizedTags:
        """VLM抽出結果を正規化済みタグに変換する。"""
        return NormalizedTags(
            motif_tags=self._normalize_list(
                raw.motif_candidates, self._motif_synonyms, self._motif_vocab
            ),
            mood_tags=self._normalize_list(
                raw.mood_candidates, self._mood_synonyms, self._mood_vocab
            ),
            style_tags=self._normalize_list(
                raw.style_candidates, self._style_synonyms, self._style_vocab
            ),
            subject_tags=self._normalize_list(
                raw.subject_candidates, self._subject_synonyms, self._subject_vocab
            ),
            color_tags=[],
            taxonomy_version=self._version,
        )

    def _normalize_list(
        self,
        candidates: list[str],
        synonyms: dict[str, str],
        vocabulary: set[str],
    ) -> list[str]:
        """候補リストを正規化し、重複・不要タグを除去する。"""
        result: list[str] = []
        seen: set[str] = set()

        for candidate in candidates:
            normalized = candidate.strip().lower()

            # ストップワード除去
            if normalized in self._stopwords:
                continue

            # 同義語変換
            if normalized in synonyms:
                normalized = synonyms[normalized]
            # 語彙チェック
            elif normalized not in vocabulary:
                continue

            # 重複排除
            if normalized not in seen:
                result.append(normalized)
                seen.add(normalized)

        return result
