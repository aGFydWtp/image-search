"""VLMClient のユニットテスト。

LM Studio API呼び出しをモックして、VLMClientのロジックを検証する。
"""

import base64
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from shared.models.vlm import VLMExtractionResult


class TestVLMExtractionResult:
    """VLMExtractionResult データモデルのテスト。"""

    def test_valid_result(self) -> None:
        result = VLMExtractionResult(
            caption="A calm sunset over the ocean",
            motif_candidates=["sky", "sea", "sun"],
            style_candidates=["impressionism"],
            subject_candidates=["landscape"],
            mood_candidates=["calm", "warm"],
        )
        assert result.caption == "A calm sunset over the ocean"
        assert result.motif_candidates == ["sky", "sea", "sun"]

    def test_empty_lists_are_valid(self) -> None:
        result = VLMExtractionResult(
            caption="Abstract art",
            motif_candidates=[],
            style_candidates=[],
            subject_candidates=[],
            mood_candidates=[],
        )
        assert result.mood_candidates == []


class TestVLMClientBuildMessages:
    """VLMClientのメッセージ構築テスト。"""

    def test_builds_vision_message_with_base64_image(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        prompt = "Describe this image"

        messages = client._build_messages(image_bytes, prompt)

        assert len(messages) == 2
        # System message
        assert messages[0]["role"] == "system"
        # User message with image + text
        assert messages[1]["role"] == "user"
        content = messages[1]["content"]
        assert len(content) == 2
        # Image part
        image_part = content[0]
        assert image_part["type"] == "image_url"
        encoded = base64.b64encode(image_bytes).decode()
        assert encoded in image_part["image_url"]["url"]
        # Text part
        text_part = content[1]
        assert text_part["type"] == "text"
        assert prompt in text_part["text"]


class TestVLMClientParseResponse:
    """VLMClientのレスポンス解析テスト。"""

    def test_parses_valid_json_response(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        raw = json.dumps({
            "caption": "A forest scene",
            "motif_candidates": ["tree", "forest"],
            "style_candidates": ["realism"],
            "subject_candidates": ["nature"],
            "mood_candidates": ["peaceful"],
        })

        result = client._parse_response(raw)
        assert isinstance(result, VLMExtractionResult)
        assert result.caption == "A forest scene"
        assert result.motif_candidates == ["tree", "forest"]

    def test_parses_json_embedded_in_markdown(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        raw = """Here is the analysis:
```json
{
    "caption": "Ocean view",
    "motif_candidates": ["sea"],
    "style_candidates": [],
    "subject_candidates": ["seascape"],
    "mood_candidates": ["calm"]
}
```
"""
        result = client._parse_response(raw)
        assert result.caption == "Ocean view"

    def test_raises_on_invalid_json(self) -> None:
        from shared.clients.vlm import VLMClient, VLMExtractionError

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        with pytest.raises(VLMExtractionError):
            client._parse_response("This is not JSON at all")

    def test_raises_on_missing_fields(self) -> None:
        from shared.clients.vlm import VLMClient, VLMExtractionError

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        raw = json.dumps({"caption": "Only caption"})

        with pytest.raises(VLMExtractionError):
            client._parse_response(raw)


class TestVLMClientExtractMetadata:
    """VLMClient.extract_metadata() の統合テスト。"""

    def test_successful_extraction(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        api_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "caption": "Sunset painting",
                            "motif_candidates": ["sun", "sky"],
                            "style_candidates": ["impressionism"],
                            "subject_candidates": ["landscape"],
                            "mood_candidates": ["warm"],
                        })
                    }
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            result = client.extract_metadata(
                image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
                prompt="Analyze this artwork",
            )

        assert result.caption == "Sunset painting"
        assert result.mood_candidates == ["warm"]

    def test_retries_on_json_parse_failure(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        bad_response = MagicMock()
        bad_response.status_code = 200
        bad_response.json.return_value = {
            "choices": [{"message": {"content": "not json"}}]
        }
        bad_response.raise_for_status = MagicMock()

        good_response = MagicMock()
        good_response.status_code = 200
        good_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "caption": "Retry success",
                            "motif_candidates": ["tree"],
                            "style_candidates": [],
                            "subject_candidates": [],
                            "mood_candidates": ["calm"],
                        })
                    }
                }
            ]
        }
        good_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.side_effect = [bad_response, good_response]
            result = client.extract_metadata(
                image_bytes=b"\x89PNG" + b"\x00" * 100,
                prompt="Analyze",
            )

        assert result.caption == "Retry success"
        assert mock_http.post.call_count == 2

    def test_raises_after_max_retries(self) -> None:
        from shared.clients.vlm import VLMClient, VLMExtractionError

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        bad_response = MagicMock()
        bad_response.status_code = 200
        bad_response.json.return_value = {
            "choices": [{"message": {"content": "garbage"}}]
        }
        bad_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = bad_response
            with pytest.raises(VLMExtractionError, match="retries"):
                client.extract_metadata(
                    image_bytes=b"\x89PNG" + b"\x00" * 100,
                    prompt="Analyze",
                )

    def test_raises_on_http_error(self) -> None:
        from shared.clients.vlm import VLMClient, VLMExtractionError

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.side_effect = httpx.ConnectError("Connection refused")
            with pytest.raises(VLMExtractionError, match="connect"):
                client.extract_metadata(
                    image_bytes=b"\x89PNG" + b"\x00" * 100,
                    prompt="Analyze",
                )


class TestVLMClientDefaultPrompt:
    """デフォルトプロンプトのテスト。"""

    def test_default_prompt_requests_json(self) -> None:
        from shared.clients.vlm import DEFAULT_EXTRACTION_PROMPT

        assert "JSON" in DEFAULT_EXTRACTION_PROMPT or "json" in DEFAULT_EXTRACTION_PROMPT
        assert "caption" in DEFAULT_EXTRACTION_PROMPT
        assert "motif" in DEFAULT_EXTRACTION_PROMPT
        assert "mood" in DEFAULT_EXTRACTION_PROMPT


class TestVLMClientResourceManagement:
    """H1: httpx.Client のリソース管理テスト。"""

    def test_close_closes_http_client(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        with patch.object(client, "_http_client") as mock_http:
            client.close()
            mock_http.close.assert_called_once()

    def test_context_manager(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"

        with patch("shared.clients.vlm.httpx.Client"):
            with VLMClient(settings=settings) as client:
                assert client is not None
            # __exit__ should have been called (close)


class TestVLMClientResponseStructure:
    """M1: 不正なAPIレスポンス構造の防御テスト。"""

    def test_raises_on_empty_choices(self) -> None:
        from shared.clients.vlm import VLMClient, VLMExtractionError

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            with pytest.raises(VLMExtractionError, match="response structure"):
                client.extract_metadata(b"\x89PNG" + b"\x00" * 100, "test")

    def test_raises_on_missing_choices_key(self) -> None:
        from shared.clients.vlm import VLMClient, VLMExtractionError

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "something"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_http_client") as mock_http:
            mock_http.post.return_value = mock_response
            with pytest.raises(VLMExtractionError, match="response structure"):
                client.extract_metadata(b"\x89PNG" + b"\x00" * 100, "test")


class TestMimeTypeDetection:
    """M2: MIMEタイプ推定テスト。"""

    def test_detects_png(self) -> None:
        from shared.clients.vlm import _detect_mime_type

        assert _detect_mime_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10) == "image/png"

    def test_detects_jpeg(self) -> None:
        from shared.clients.vlm import _detect_mime_type

        assert _detect_mime_type(b"\xff\xd8\xff\xe0" + b"\x00" * 10) == "image/jpeg"

    def test_detects_webp(self) -> None:
        from shared.clients.vlm import _detect_mime_type

        assert _detect_mime_type(b"RIFF" + b"\x00" * 4 + b"WEBP") == "image/webp"

    def test_detects_gif(self) -> None:
        from shared.clients.vlm import _detect_mime_type

        assert _detect_mime_type(b"GIF89a" + b"\x00" * 10) == "image/gif"

    def test_unknown_returns_octet_stream(self) -> None:
        from shared.clients.vlm import _detect_mime_type

        assert _detect_mime_type(b"\x00\x01\x02\x03") == "application/octet-stream"

    def test_jpeg_image_uses_correct_mime_in_message(self) -> None:
        from shared.clients.vlm import VLMClient

        settings = MagicMock()
        settings.lm_studio_url = "http://localhost:1234"
        client = VLMClient(settings=settings)

        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        messages = client._build_messages(jpeg_bytes, "test")

        image_url = messages[1]["content"][0]["image_url"]["url"]
        assert image_url.startswith("data:image/jpeg;base64,")
