"""TaxonomyMapper のユニットテスト。"""

import json
from pathlib import Path

import pytest

from shared.models.vlm import VLMExtractionResult


def _make_vlm_result(**overrides) -> VLMExtractionResult:
    defaults = {
        "caption": "A calm scene",
        "motif_candidates": [],
        "style_candidates": [],
        "subject_candidates": [],
        "mood_candidates": [],
    }
    defaults.update(overrides)
    return VLMExtractionResult(**defaults)


def _load_definitions() -> dict:
    defs_path = Path(__file__).parent.parent / "shared" / "taxonomy" / "definitions.json"
    with open(defs_path) as f:
        return json.load(f)


class TestNormalizedTagsModel:
    """NormalizedTags データモデルのテスト。"""

    def test_valid_normalized_tags(self) -> None:
        from shared.models.taxonomy import NormalizedTags

        tags = NormalizedTags(
            mood_tags=["calm"],
            motif_tags=["sky"],
            style_tags=["impressionism"],
            subject_tags=["landscape"],
            color_tags=[],
            freeform_keywords=["lighthouse"],
            taxonomy_version="v2",
        )
        assert tags.taxonomy_version == "v2"
        assert tags.freeform_keywords == ["lighthouse"]

    def test_freeform_keywords_field_required(self) -> None:
        """freeform_keywords は必須フィールドであること。"""
        from pydantic import ValidationError

        from shared.models.taxonomy import NormalizedTags

        with pytest.raises(ValidationError):
            NormalizedTags(
                mood_tags=["calm"],
                motif_tags=["sky"],
                style_tags=[],
                subject_tags=[],
                color_tags=[],
                taxonomy_version="v2",
            )


class TestMotifNormalization:
    """モチーフ正規化のテスト。"""

    def test_normalizes_synonym(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["ocean", "skies"]))

        assert "sea" in result.motif_tags
        assert "sky" in result.motif_tags

    def test_passes_through_known_motif(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["tree"]))

        assert "tree" in result.motif_tags

    def test_removes_unknown_motif(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["xyzzy_unknown"]))

        assert "xyzzy_unknown" not in result.motif_tags

    def test_deduplicates_motifs(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["ocean", "sea"]))

        assert result.motif_tags.count("sea") == 1


class TestMoodNormalization:
    """ムード語彙マッピングのテスト。"""

    def test_normalizes_mood_synonym(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(mood_candidates=["peaceful", "tranquil"]))

        assert "calm" in result.mood_tags

    def test_passes_through_known_mood(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(mood_candidates=["warm"]))

        assert "warm" in result.mood_tags

    def test_removes_unknown_mood(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(mood_candidates=["nonsense_mood"]))

        assert "nonsense_mood" not in result.mood_tags

    def test_deduplicates_moods(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(mood_candidates=["peaceful", "serene", "calm"]))

        assert result.mood_tags.count("calm") == 1


class TestStyleNormalization:
    """スタイルタグ正規化のテスト。"""

    def test_normalizes_style(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(style_candidates=["abstract art"]))

        assert "abstract" in result.style_tags

    def test_passes_through_known_style(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(style_candidates=["impressionism"]))

        assert "impressionism" in result.style_tags


class TestSubjectNormalization:
    """サブジェクトタグ正規化のテスト。"""

    def test_normalizes_subject(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(subject_candidates=["scenery"]))

        assert "landscape" in result.subject_tags

    def test_passes_through_known_subject(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(subject_candidates=["portrait"]))

        assert "portrait" in result.subject_tags


class TestStopwordFiltering:
    """不要・冗長タグ除去のテスト。"""

    def test_removes_stopword_motifs(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["background", "object", "sky"]))

        assert "background" not in result.motif_tags
        assert "object" not in result.motif_tags
        assert "sky" in result.motif_tags


class TestTaxonomyVersion:
    """taxonomy_version の付与テスト。"""

    def test_includes_version_v2(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result())

        assert result.taxonomy_version == "v2"


class TestMotifVocabularyExpansion:
    """motif_vocabulary 拡張のテスト（Task 1.1）。"""

    def _defs(self) -> dict:
        return _load_definitions()

    def test_vocabulary_has_at_least_800_terms(self) -> None:
        defs = self._defs()
        vocab = defs["motif_vocabulary"]
        assert len(vocab) >= 800, f"Expected >=800 motif terms, got {len(vocab)}"

    def test_vocabulary_contains_existing_terms(self) -> None:
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        existing = {"sky", "sea", "tree", "flower", "mountain", "river", "sun", "moon",
                    "star", "bird", "animal", "house", "figure", "snow", "rain", "field",
                    "rock", "road", "bridge", "boat", "garden", "lake", "city", "window",
                    "door", "chair", "table", "fruit", "vase", "candle", "mirror", "fire"}
        missing = existing - vocab
        assert not missing, f"Missing existing terms: {missing}"

    def test_vocabulary_contains_met_museum_terms(self) -> None:
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        met_samples = {"lighthouse", "castle", "butterfly", "elephant", "volcano",
                       "windmill", "hammock", "cathedral", "whale", "rainbow"}
        missing = met_samples - vocab
        assert not missing, f"Missing Met Museum terms: {missing}"

    def test_scientific_names_normalized(self) -> None:
        """学名が一般名に正規化されていること。"""
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        # 学名が含まれていないこと
        scientific = {"Bambusoideae", "Cupressus", "Panthera pardus", "Giraffa", "Canis lupus"}
        found = scientific & vocab
        assert not found, f"Scientific names should not be in vocabulary: {found}"
        # 一般名が含まれていること
        common = {"bamboo", "cypress", "leopard", "giraffe", "wolf"}
        missing = common - vocab
        assert not missing, f"Common names missing: {missing}"

    def test_no_proper_nouns(self) -> None:
        """固有名詞が含まれていないこと。"""
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        proper_nouns = {"Napoleon", "Venus", "Apollo", "Zeus", "Buddha", "Abraham Lincoln"}
        found = proper_nouns & vocab
        assert not found, f"Proper nouns should not be in vocabulary: {found}"

    def test_no_languages(self) -> None:
        """言語・文字体系が含まれていないこと。"""
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        languages = {"Arabic", "Hebrew", "Sanskrit", "Latin", "Greek", "Japanese"}
        found = languages & vocab
        assert not found, f"Languages should not be in vocabulary: {found}"

    def test_no_duplicates(self) -> None:
        defs = self._defs()
        vocab = defs["motif_vocabulary"]
        assert len(vocab) == len(set(vocab)), "Vocabulary contains duplicates"

    def test_all_terms_lowercase(self) -> None:
        defs = self._defs()
        vocab = defs["motif_vocabulary"]
        non_lower = [t for t in vocab if t != t.lower()]
        assert not non_lower, f"Non-lowercase terms: {non_lower[:10]}"

    def test_vocabulary_sorted(self) -> None:
        defs = self._defs()
        vocab = defs["motif_vocabulary"]
        assert vocab == sorted(vocab), "Vocabulary should be sorted alphabetically"

    def test_met_tags_normalizes_via_mapper(self) -> None:
        """拡張語彙で VLM 出力が正しく正規化されること。"""
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["lighthouse", "castle", "butterfly", "sky"]
        ))
        assert "lighthouse" in result.motif_tags
        assert "castle" in result.motif_tags
        assert "butterfly" in result.motif_tags
        assert "sky" in result.motif_tags


class TestSynonymConflictResolution:
    """synonym 衝突解消と新規追加のテスト（Task 1.2）。"""

    def _defs(self) -> dict:
        return _load_definitions()

    def test_cloud_is_independent_vocabulary(self) -> None:
        """cloud は sky の synonym ではなく独立 vocabulary 語であること。"""
        defs = self._defs()
        assert "cloud" in defs["motif_vocabulary"]
        assert defs["motif_synonyms"].get("cloud") != "sky"

    def test_forest_is_independent_vocabulary(self) -> None:
        defs = self._defs()
        assert "forest" in defs["motif_vocabulary"]
        assert defs["motif_synonyms"].get("forest") != "tree"

    def test_hill_is_independent_vocabulary(self) -> None:
        defs = self._defs()
        assert "hill" in defs["motif_vocabulary"]
        assert defs["motif_synonyms"].get("hill") != "mountain"

    def test_building_is_independent_vocabulary(self) -> None:
        defs = self._defs()
        assert "building" in defs["motif_vocabulary"]
        assert defs["motif_synonyms"].get("building") != "house"

    def test_man_woman_child_are_independent(self) -> None:
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        assert {"man", "woman", "child"}.issubset(vocab)
        syns = defs["motif_synonyms"]
        for term in ("man", "woman", "child", "person", "people"):
            assert syns.get(term) != "figure", f"{term} should not map to figure"

    def test_valid_synonyms_preserved(self) -> None:
        """ocean→sea 等の有効 synonym が維持されていること。"""
        defs = self._defs()
        syns = defs["motif_synonyms"]
        assert syns.get("ocean") == "sea"
        assert syns.get("waves") == "sea"
        assert syns.get("skies") == "sky"
        assert syns.get("blossom") == "flower"
        assert syns.get("bloom") == "flower"

    def test_plural_synonyms_for_new_terms(self) -> None:
        """新語彙の複数形 synonym が追加されていること。"""
        defs = self._defs()
        syns = defs["motif_synonyms"]
        assert syns.get("buildings") == "building"
        assert syns.get("hills") == "hill"
        assert syns.get("forests") == "forest"
        assert syns.get("clouds") == "cloud"
        assert syns.get("children") == "child"

    def test_no_synonym_points_outside_vocabulary(self) -> None:
        """全 synonym のターゲットが vocabulary に存在すること。"""
        defs = self._defs()
        vocab = set(defs["motif_vocabulary"])
        for src, target in defs["motif_synonyms"].items():
            assert target in vocab, f"Synonym {src}→{target}: target not in vocabulary"

    def test_mapper_resolves_cloud_independently(self) -> None:
        """cloud が sky にマージされず独立タグとして残ること。"""
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["cloud", "sky"]))
        assert "cloud" in result.motif_tags
        assert "sky" in result.motif_tags

    def test_mapper_resolves_man_independently(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(motif_candidates=["man", "woman"]))
        assert "man" in result.motif_tags
        assert "woman" in result.motif_tags

    def test_stream_is_independent_vocabulary(self) -> None:
        defs = self._defs()
        assert "stream" in defs["motif_vocabulary"]
        assert defs["motif_synonyms"].get("stream") != "river"

    def test_woods_maps_to_forest(self) -> None:
        defs = self._defs()
        assert defs["motif_synonyms"].get("woods") == "forest"

    def test_no_self_referential_synonyms(self) -> None:
        defs = self._defs()
        self_refs = {k for k, v in defs["motif_synonyms"].items() if k == v}
        assert not self_refs, f"Self-referential synonyms: {self_refs}"

    def test_all_synonym_categories_valid(self) -> None:
        """全カテゴリの synonym ターゲットが vocabulary に存在すること。"""
        defs = self._defs()
        pairs = [
            ("motif_synonyms", "motif_vocabulary"),
            ("mood_synonyms", "mood_vocabulary"),
            ("style_synonyms", "style_vocabulary"),
            ("subject_synonyms", "subject_vocabulary"),
        ]
        for syn_key, vocab_key in pairs:
            vocab = set(defs[vocab_key])
            for src, target in defs[syn_key].items():
                assert target in vocab, f"{syn_key}: {src}→{target} target not in {vocab_key}"

    def test_ocean_is_synonym_not_vocabulary(self) -> None:
        """ocean は vocabulary ではなく synonym として sea にマップされること。"""
        defs = self._defs()
        assert "ocean" not in defs["motif_vocabulary"]
        assert defs["motif_synonyms"].get("ocean") == "sea"


class TestFreeformKeywordsCollection:
    """freeform_keywords 収集ロジックのテスト（Task 2.2 / 5.1）。"""

    def test_captures_unknown_motifs(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["sky", "lighthouse_unknown_xyz", "windmill_rare"]
        ))
        assert "sky" in result.motif_tags
        assert "lighthouse_unknown_xyz" in result.freeform_keywords
        assert "windmill_rare" in result.freeform_keywords

    def test_excludes_stopwords(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["background", "composition", "rare_motif"]
        ))
        assert "background" not in result.freeform_keywords
        assert "composition" not in result.freeform_keywords
        assert "rare_motif" in result.freeform_keywords

    def test_excludes_short_strings(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["a", "x", "rare_motif"]
        ))
        assert "a" not in result.freeform_keywords
        assert "x" not in result.freeform_keywords
        assert "rare_motif" in result.freeform_keywords

    def test_excludes_long_strings(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        long_str = "a" * 51
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=[long_str, "rare_motif"]
        ))
        assert long_str.lower() not in result.freeform_keywords
        assert "rare_motif" in result.freeform_keywords

    def test_deduplicates(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["Rare_Motif", "rare_motif", "RARE_MOTIF"]
        ))
        assert result.freeform_keywords.count("rare_motif") == 1

    def test_excludes_synonym_matches(self) -> None:
        """synonym に一致するものは freeform に入らないこと。"""
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["ocean", "waves", "rare_motif"]
        ))
        # ocean, waves は synonym → motif_tags に入る
        assert "sea" in result.motif_tags
        # freeform には入らない
        assert "ocean" not in result.freeform_keywords
        assert "waves" not in result.freeform_keywords
        assert "rare_motif" in result.freeform_keywords

    def test_empty_when_all_match_taxonomy(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["sky", "sea", "tree"]
        ))
        assert result.freeform_keywords == []

    def test_lowercase_normalization(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result(
            motif_candidates=["EXOTIC_BIRD_TYPE"]
        ))
        assert "exotic_bird_type" in result.freeform_keywords


class TestColorTagsPassthrough:
    """color_tags はTaxonomyMapperでは空を返す（ColorExtractor担当）。"""

    def test_color_tags_empty(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result())

        assert result.color_tags == []
