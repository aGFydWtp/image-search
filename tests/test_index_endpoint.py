"""POST /internal/artworks/index エンドポイントのテスト。"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _mock_ingestion_deps():
    """インジェスション関連の依存をモック。"""
    ingestion_svc = MagicMock()
    ingestion_svc.process_artwork.return_value = True

    qdrant_repo = MagicMock()
    qdrant_repo.exists.return_value = False

    http_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_response.raise_for_status = MagicMock()
    http_client.get.return_value = mock_response

    return ingestion_svc, qdrant_repo, http_client


class TestIndexEndpoint:
    """POST /internal/artworks/index のテスト。"""

    def test_successful_index_new_artwork(self) -> None:
        ingestion_svc, qdrant_repo, http_client = _mock_ingestion_deps()
        qdrant_repo.exists.return_value = False

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/internal/artworks/index", json={
                "artwork_id": "art-001",
                "image_url": "https://example.com/art-001.jpg",
                "title": "Sunset",
                "artist_name": "Artist",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["artwork_id"] == "art-001"
        assert data["status"] == "created"

    def test_successful_index_existing_artwork(self) -> None:
        ingestion_svc, qdrant_repo, http_client = _mock_ingestion_deps()
        qdrant_repo.exists.return_value = True

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/internal/artworks/index", json={
                "artwork_id": "art-001",
                "image_url": "https://example.com/art-001.jpg",
                "title": "Sunset",
                "artist_name": "Artist",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

    def test_image_download_failure_returns_502(self) -> None:
        ingestion_svc, qdrant_repo, http_client = _mock_ingestion_deps()
        import httpx
        http_client.get.side_effect = httpx.ConnectError("Connection refused")

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/internal/artworks/index", json={
                "artwork_id": "art-001",
                "image_url": "https://example.com/fail.jpg",
                "title": "T",
                "artist_name": "A",
            })

        assert response.status_code == 502

    def test_image_404_returns_404(self) -> None:
        ingestion_svc, qdrant_repo, http_client = _mock_ingestion_deps()
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=mock_response
        )
        http_client.get.return_value = mock_response

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/internal/artworks/index", json={
                "artwork_id": "art-001",
                "image_url": "https://example.com/missing.jpg",
                "title": "T",
                "artist_name": "A",
            })

        assert response.status_code == 404

    def test_pipeline_failure_returns_500(self) -> None:
        ingestion_svc, qdrant_repo, http_client = _mock_ingestion_deps()
        ingestion_svc.process_artwork.return_value = False

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/internal/artworks/index", json={
                "artwork_id": "art-fail",
                "image_url": "https://example.com/art.jpg",
                "title": "T",
                "artist_name": "A",
            })

        assert response.status_code == 500

    def test_invalid_request_returns_422(self) -> None:
        from services.search.app import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/internal/artworks/index", json={"artwork_id": ""})

        assert response.status_code == 422

    def test_calls_process_artwork_with_image_bytes(self) -> None:
        ingestion_svc, qdrant_repo, http_client = _mock_ingestion_deps()

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant_repo),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            client.post("/internal/artworks/index", json={
                "artwork_id": "art-001",
                "image_url": "https://example.com/art.jpg",
                "title": "Sunset",
                "artist_name": "Artist",
            })

        ingestion_svc.process_artwork.assert_called_once()
        call_kwargs = ingestion_svc.process_artwork.call_args.kwargs
        assert call_kwargs["artwork_id"] == "art-001"
        assert call_kwargs["title"] == "Sunset"
        assert isinstance(call_kwargs["image_bytes"], bytes)
