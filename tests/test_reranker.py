"""Reranker のユニットテスト。"""


from shared.models.search import ParsedQuery, QueryBoosts, QueryFilters
from shared.qdrant.repository import SearchResult


def _make_candidate(
    artwork_id: str = "art-001",
    score: float = 0.9,
    motif_tags: list[str] | None = None,
    color_tags: list[str] | None = None,
    brightness_score: float = 0.5,
) -> SearchResult:
    return SearchResult(
        artwork_id=artwork_id,
        title="Test",
        artist_name="Artist",
        thumbnail_url="https://example.com/thumb.jpg",
        score=score,
        payload={
            "motif_tags": motif_tags or [],
            "color_tags": color_tags or [],
            "brightness_score": brightness_score,
        },
    )


def _make_query(
    semantic_query: str = "calm",
    motif_tags: list[str] | None = None,
    color_tags: list[str] | None = None,
    brightness_min: float | None = None,
) -> ParsedQuery:
    return ParsedQuery(
        semantic_query=semantic_query,
        filters=QueryFilters(
            motif_tags=motif_tags or [],
            color_tags=color_tags or [],
        ),
        boosts=QueryBoosts(brightness_min=brightness_min),
    )


class TestRerankerScoreComposition:
    """スコア合成ロジックのテスト。"""

    def test_vector_similarity_dominates(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            _make_candidate("high", score=0.95),
            _make_candidate("low", score=0.50),
        ]
        query = _make_query()

        results = reranker.rerank(candidates, query)

        assert results[0].artwork_id == "high"
        assert results[1].artwork_id == "low"

    def test_motif_match_boosts_score(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            _make_candidate("no_motif", score=0.8, motif_tags=[]),
            _make_candidate("has_motif", score=0.8, motif_tags=["sky", "sea"]),
        ]
        query = _make_query(motif_tags=["sky", "sea"])

        results = reranker.rerank(candidates, query)

        assert results[0].artwork_id == "has_motif"

    def test_color_match_boosts_score(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            _make_candidate("no_color", score=0.8, color_tags=[]),
            _make_candidate("has_color", score=0.8, color_tags=["green", "gold"]),
        ]
        query = _make_query(color_tags=["green", "gold"])

        results = reranker.rerank(candidates, query)

        assert results[0].artwork_id == "has_color"

    def test_brightness_affinity_boosts_score(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            _make_candidate("dark", score=0.8, brightness_score=0.1),
            _make_candidate("bright", score=0.8, brightness_score=0.9),
        ]
        query = _make_query(brightness_min=0.6)

        results = reranker.rerank(candidates, query)

        assert results[0].artwork_id == "bright"

    def test_final_score_in_valid_range(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [_make_candidate(score=0.95, motif_tags=["sky"], color_tags=["blue"])]
        query = _make_query(motif_tags=["sky"], color_tags=["blue"], brightness_min=0.6)

        results = reranker.rerank(candidates, query)

        assert 0.0 <= results[0].score <= 1.0

    def test_empty_candidates_returns_empty(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        results = reranker.rerank([], _make_query())
        assert results == []


class TestMatchReasons:
    """match_reasons 生成のテスト。"""

    def test_includes_motif_reason(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [_make_candidate(motif_tags=["sky"])]
        query = _make_query(motif_tags=["sky"])

        results = reranker.rerank(candidates, query)

        reasons = results[0].match_reasons
        assert any("sky" in r for r in reasons)

    def test_includes_color_reason(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [_make_candidate(color_tags=["green"])]
        query = _make_query(color_tags=["green"])

        results = reranker.rerank(candidates, query)

        reasons = results[0].match_reasons
        assert any("green" in r for r in reasons)

    def test_includes_semantic_reason(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [_make_candidate(score=0.9)]
        query = _make_query(semantic_query="calm atmosphere")

        results = reranker.rerank(candidates, query)

        reasons = results[0].match_reasons
        assert len(reasons) >= 1

    def test_no_reasons_for_low_match(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [_make_candidate(score=0.3, motif_tags=[], color_tags=[])]
        query = _make_query(motif_tags=["mountain"], color_tags=["red"])

        results = reranker.rerank(candidates, query)

        motif_reasons = [r for r in results[0].match_reasons if "mountain" in r]
        assert len(motif_reasons) == 0


class TestRankedResultFields:
    """結果フィールドの検証テスト。"""

    def test_preserves_artwork_fields(self) -> None:
        from services.search.reranker import Reranker

        reranker = Reranker()
        candidates = [
            SearchResult(
                artwork_id="art-042",
                title="Ocean View",
                artist_name="Painter",
                thumbnail_url="https://example.com/t.jpg",
                score=0.85,
                payload={"motif_tags": [], "color_tags": [], "brightness_score": 0.5},
            )
        ]
        query = _make_query()

        results = reranker.rerank(candidates, query)

        assert results[0].artwork_id == "art-042"
        assert results[0].title == "Ocean View"
        assert results[0].artist_name == "Painter"
