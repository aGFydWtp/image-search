"""TaxonomyMapper のユニットテスト。"""

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
            taxonomy_version="v1",
        )
        assert tags.taxonomy_version == "v1"


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

    def test_includes_version_v1(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result())

        assert result.taxonomy_version == "v1"


class TestColorTagsPassthrough:
    """color_tags はTaxonomyMapperでは空を返す（ColorExtractor担当）。"""

    def test_color_tags_empty(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(_make_vlm_result())

        assert result.color_tags == []
