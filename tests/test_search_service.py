"""SearchService と POST /api/artworks/search エンドポイントのテスト。"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from shared.models.search import ParsedQuery, QueryBoosts, QueryFilters, SearchResultItem
from shared.qdrant.repository import SearchResult


def _make_search_result(artwork_id: str = "art-001", score: float = 0.9) -> SearchResult:
    return SearchResult(
        artwork_id=artwork_id,
        title="Test Art",
        artist_name="Artist",
        thumbnail_url="https://example.com/thumb.jpg",
        score=score,
        payload={"motif_tags": ["sky"], "color_tags": ["blue"], "brightness_score": 0.7},
    )


def _make_ranked_item(artwork_id: str = "art-001", score: float = 0.85) -> SearchResultItem:
    return SearchResultItem(
        artwork_id=artwork_id,
        title="Test Art",
        artist_name="Artist",
        thumbnail_url="https://example.com/thumb.jpg",
        score=score,
        match_reasons=["雰囲気が近い"],
    )


def _mock_deps():
    """SearchService依存をモック。"""
    query_parser = MagicMock()
    query_parser.parse.return_value = ParsedQuery(
        semantic_query="calm atmosphere",
        filters=QueryFilters(motif_tags=["sky"], color_tags=["blue"]),
        boosts=QueryBoosts(brightness_min=None),
    )

    embedding_client = MagicMock()
    embedding_client.embed_text.return_value = [0.1] * 1152

    qdrant_repo = MagicMock()
    qdrant_repo.search.return_value = [_make_search_result()]

    reranker = MagicMock()
    reranker.rerank.return_value = [_make_ranked_item()]

    return query_parser, embedding_client, qdrant_repo, reranker


class TestSearchEndpoint:
    """POST /api/artworks/search のテスト。"""

    def test_successful_search(self) -> None:
        query_parser, embedding_client, qdrant_repo, reranker = _mock_deps()

        with (
            patch("services.search.app._query_parser", query_parser),
            patch("services.search.app._embedding_client", embedding_client),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._reranker", reranker),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/artworks/search", json={"query": "穏やかな青い空"})

        assert response.status_code == 200
        data = response.json()
        assert "parsed_query" in data
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["artwork_id"] == "art-001"

    def test_returns_parsed_query(self) -> None:
        query_parser, embedding_client, qdrant_repo, reranker = _mock_deps()

        with (
            patch("services.search.app._query_parser", query_parser),
            patch("services.search.app._embedding_client", embedding_client),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._reranker", reranker),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/artworks/search", json={"query": "calm scene"})

        data = response.json()
        assert data["parsed_query"]["semantic_query"] == "calm atmosphere"
        assert "sky" in data["parsed_query"]["filters"]["motif_tags"]

    def test_empty_query_returns_422(self) -> None:
        from services.search.app import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/artworks/search", json={"query": ""})

        assert response.status_code == 422

    def test_missing_query_returns_422(self) -> None:
        from services.search.app import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/artworks/search", json={})

        assert response.status_code == 422

    def test_custom_limit(self) -> None:
        query_parser, embedding_client, qdrant_repo, reranker = _mock_deps()

        with (
            patch("services.search.app._query_parser", query_parser),
            patch("services.search.app._embedding_client", embedding_client),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._reranker", reranker),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/artworks/search", json={"query": "test", "limit": 10})

        assert response.status_code == 200
        qdrant_repo.search.assert_called_once()
        call_kwargs = qdrant_repo.search.call_args.kwargs
        assert call_kwargs["limit"] == 10

    def test_qdrant_connection_failure_returns_503(self) -> None:
        query_parser, embedding_client, qdrant_repo, reranker = _mock_deps()
        qdrant_repo.search.side_effect = Exception("Connection refused")

        with (
            patch("services.search.app._query_parser", query_parser),
            patch("services.search.app._embedding_client", embedding_client),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._reranker", reranker),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/artworks/search", json={"query": "test"})

        assert response.status_code == 503


class TestSearchServiceLogic:
    """SearchService内部ロジックのテスト。"""

    def test_calls_pipeline_in_order(self) -> None:
        query_parser, embedding_client, qdrant_repo, reranker = _mock_deps()

        with (
            patch("services.search.app._query_parser", query_parser),
            patch("services.search.app._embedding_client", embedding_client),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._reranker", reranker),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            client.post("/api/artworks/search", json={"query": "test"})

        query_parser.parse.assert_called_once_with("test")
        embedding_client.embed_text.assert_called_once()
        qdrant_repo.search.assert_called_once()
        reranker.rerank.assert_called_once()

    def test_passes_filters_to_qdrant(self) -> None:
        query_parser, embedding_client, qdrant_repo, reranker = _mock_deps()

        with (
            patch("services.search.app._query_parser", query_parser),
            patch("services.search.app._embedding_client", embedding_client),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._reranker", reranker),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            client.post("/api/artworks/search", json={"query": "test"})

        call_kwargs = qdrant_repo.search.call_args.kwargs
        filters = call_kwargs["filters"]
        assert filters.motif_tags == ["sky"]
        assert filters.color_tags == ["blue"]
