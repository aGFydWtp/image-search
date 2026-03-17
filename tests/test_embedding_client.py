"""EmbeddingClient のユニットテスト。

SigLIP2埋め込みサービスAPI呼び出しをモックして、クライアントロジックを検証する。
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from shared.clients.embedding import EmbeddingClient, EmbeddingError


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.embedding_service_url = "http://localhost:8100"
    settings.vector_dim = 1152
    return settings


def _make_vector(dim: int = 1152, val: float = 0.1) -> list[float]:
    return [val] * dim


class TestEmbedImage:
    """embed_image() のテスト。"""

    def test_returns_vector_on_success(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)
        expected = _make_vector()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vector": expected}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            result = client.embed_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        assert result == expected
        assert len(result) == 1152

    def test_posts_image_bytes_to_embed_image_endpoint(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)
        image_bytes = b"\x89PNG" + b"\x00" * 50

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vector": _make_vector()}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            client.embed_image(image_bytes)

        call_args = mock_http.post.call_args
        assert "/embed/image" in call_args.args[0]
        assert call_args.kwargs["content"] == image_bytes

    def test_raises_on_connection_error(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.side_effect = httpx.ConnectError("Connection refused")
            with pytest.raises(EmbeddingError, match="connect"):
                client.embed_image(b"\x89PNG" + b"\x00" * 50)

    def test_raises_on_http_error(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            with pytest.raises(EmbeddingError):
                client.embed_image(b"\x89PNG" + b"\x00" * 50)

    def test_raises_on_invalid_response_structure(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "no vector"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            with pytest.raises(EmbeddingError, match="response"):
                client.embed_image(b"\x89PNG" + b"\x00" * 50)

    def test_validates_vector_dimension(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vector": [0.1] * 512}  # wrong dim
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            with pytest.raises(EmbeddingError, match="dimension"):
                client.embed_image(b"\x89PNG" + b"\x00" * 50)


class TestEmbedText:
    """embed_text() のテスト。"""

    def test_returns_vector_on_success(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)
        expected = _make_vector(val=0.2)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vector": expected}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            result = client.embed_text("a calm sunset")

        assert result == expected
        assert len(result) == 1152

    def test_posts_text_to_embed_text_endpoint(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vector": _make_vector()}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            client.embed_text("a calm sunset")

        call_args = mock_http.post.call_args
        assert "/embed/text" in call_args.args[0]
        assert call_args.kwargs["json"] == {"text": "a calm sunset"}

    def test_raises_on_connection_error(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.side_effect = httpx.ConnectError("Connection refused")
            with pytest.raises(EmbeddingError, match="connect"):
                client.embed_text("test")

    def test_validates_vector_dimension(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"vector": [0.1] * 256}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            with pytest.raises(EmbeddingError, match="dimension"):
                client.embed_text("test")


class TestResourceManagement:
    """httpx.Client のリソース管理テスト。"""

    def test_close(self) -> None:
        settings = _make_settings()
        client = EmbeddingClient(settings=settings)

        with patch.object(client, "_http_client") as mock_http:
            client.close()
            mock_http.close.assert_called_once()

    def test_context_manager(self) -> None:
        settings = _make_settings()

        with patch("shared.clients.embedding.httpx.Client"):
            with EmbeddingClient(settings=settings) as client:
                assert client is not None
