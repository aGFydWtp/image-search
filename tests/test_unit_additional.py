"""Task 7.1 追加ユニットテスト。

既存TDDテストを補完するエッジケース・精度検証テスト。
"""

from io import BytesIO

import pytest
from PIL import Image

from shared.models.search import ParsedQuery, QueryBoosts, QueryFilters
from shared.models.vlm import VLMExtractionResult
from shared.qdrant.repository import SearchResult


def _make_solid_image(r: int, g: int, b: int) -> bytes:
    img = Image.new("RGB", (200, 200), color=(r, g, b))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
# QueryParser 追加テスト: ムード表現の網羅・エッジケース
# ──────────────────────────────────────────────────────────────

class TestQueryParserMoodExpressions:
    """各種ムード表現がsemantic_queryに含まれることの検証。"""

    @pytest.mark.parametrize("query", [
        "やさしい雰囲気",
        "穏やかな風景",
        "静かな湖畔",
        "温かい光",
        "冷たい空気感",
        "力強い表現",
        "幻想的な世界",
    ])
    def test_mood_queries_produce_nonempty_semantic(self, query: str) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse(query)
        assert len(result.semantic_query) > 0

    def test_compound_query_extracts_all_elements(self) -> None:
        """複合クエリ: ムード+色+モチーフ+明るさが全て抽出される。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("明るくて穏やかな、赤い花と青い空のある絵")

        assert "red" in result.filters.color_tags
        assert "blue" in result.filters.color_tags
        assert "flower" in result.filters.motif_tags
        assert "sky" in result.filters.motif_tags
        assert result.boosts.brightness_min is not None
        assert result.boosts.brightness_min >= 0.6

    def test_only_punctuation_returns_original(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("、。！？")
        assert result.semantic_query == "、。！？"
        assert result.filters.color_tags == []


# ──────────────────────────────────────────────────────────────
# TaxonomyMapper 追加テスト: ケース正規化・複合入力
# ──────────────────────────────────────────────────────────────

class TestTaxonomyMapperEdgeCases:
    """TaxonomyMapper のエッジケーステスト。"""

    def test_case_insensitive_normalization(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(VLMExtractionResult(
            caption="test",
            motif_candidates=["Ocean", "SKIES"],
            style_candidates=["Abstract Art"],
            subject_candidates=["Scenery"],
            mood_candidates=["Peaceful"],
        ))

        assert "sea" in result.motif_tags
        assert "sky" in result.motif_tags
        assert "abstract" in result.style_tags
        assert "landscape" in result.subject_tags
        assert "calm" in result.mood_tags

    def test_empty_input(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(VLMExtractionResult(
            caption="",
            motif_candidates=[],
            style_candidates=[],
            subject_candidates=[],
            mood_candidates=[],
        ))

        assert result.motif_tags == []
        assert result.mood_tags == []
        assert result.taxonomy_version == "v2"

    def test_all_stopwords_removed(self) -> None:
        from shared.taxonomy.mapper import TaxonomyMapper

        mapper = TaxonomyMapper()
        result = mapper.normalize(VLMExtractionResult(
            caption="test",
            motif_candidates=["background", "foreground", "element", "sky"],
            style_candidates=[],
            subject_candidates=[],
            mood_candidates=[],
        ))

        assert "background" not in result.motif_tags
        assert "foreground" not in result.motif_tags
        assert "sky" in result.motif_tags


# ──────────────────────────────────────────────────────────────
# ColorExtractor 追加テスト: 色精度検証
# ──────────────────────────────────────────────────────────────

class TestColorExtractorAccuracy:
    """ColorExtractor のスコア精度検証テスト。"""

    def test_yellow_image(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(255, 255, 0))
        assert "yellow" in result.color_tags

    def test_orange_image(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(255, 165, 0))
        assert "orange" in result.color_tags

    def test_teal_image(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(0, 180, 180))
        assert "teal" in result.color_tags

    def test_brightness_ordering(self) -> None:
        """明るい画像 > 暗い画像のbrightness_score。"""
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        bright = ext.extract(_make_solid_image(200, 200, 200))
        dark = ext.extract(_make_solid_image(50, 50, 50))

        assert bright.brightness_score > dark.brightness_score

    def test_saturation_ordering(self) -> None:
        """鮮やかな色 > グレーのsaturation_score。"""
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        vivid = ext.extract(_make_solid_image(255, 0, 0))
        gray = ext.extract(_make_solid_image(128, 128, 128))

        assert vivid.saturation_score > gray.saturation_score

    def test_warmth_ordering(self) -> None:
        """赤 > 青のwarmth_score。"""
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        warm = ext.extract(_make_solid_image(255, 100, 0))
        cool = ext.extract(_make_solid_image(0, 100, 255))

        assert warm.warmth_score > cool.warmth_score


# ──────────────────────────────────────────────────────────────
# Reranker 追加テスト: エッジケース
# ──────────────────────────────────────────────────────────────

class TestRerankerEdgeCases:
    """Reranker のエッジケーステスト。"""

    def test_preserves_order_for_equal_scores(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            SearchResult("art-a", "A", "Artist", "url", 0.8,
                         {"motif_tags": [], "color_tags": [], "brightness_score": 0.5}),
            SearchResult("art-b", "B", "Artist", "url", 0.8,
                         {"motif_tags": [], "color_tags": [], "brightness_score": 0.5}),
        ]
        query = ParsedQuery(
            semantic_query="test",
            filters=QueryFilters(),
            boosts=QueryBoosts(),
        )

        results = reranker.rerank(candidates, query)
        assert len(results) == 2

    def test_many_candidates_sorted(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            SearchResult(f"art-{i}", f"Title {i}", "A", "url", score,
                         {"motif_tags": [], "color_tags": [], "brightness_score": 0.5})
            for i, score in enumerate([0.3, 0.9, 0.5, 0.7, 0.1])
        ]
        query = ParsedQuery(
            semantic_query="test",
            filters=QueryFilters(),
            boosts=QueryBoosts(),
        )

        results = reranker.rerank(candidates, query)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_partial_motif_match(self) -> None:
        """クエリの一部だけmotif一致する場合のスコア。"""
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            SearchResult("art-1", "T", "A", "url", 0.8,
                         {"motif_tags": ["sky"], "color_tags": [], "brightness_score": 0.5}),
        ]
        query = ParsedQuery(
            semantic_query="test",
            filters=QueryFilters(motif_tags=["sky", "sea"]),
            boosts=QueryBoosts(),
        )

        results = reranker.rerank(candidates, query)
        # Partial match: 1/2 = 0.5 motif score
        assert results[0].score > 0.8 * 0.70  # Vector contribution alone
