"""VLMClient: LM Studio OpenAI互換API経由のメタデータ抽出クライアント。"""

import base64
import json
import logging
import re
from typing import Any, Self

import httpx

from shared.config import Settings
from shared.models.vlm import VLMExtractionResult

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_PROMPT = """\
Analyze this artwork image and extract metadata in JSON format.
Return ONLY a JSON object with these exact keys:
- "caption": A concise English description of the artwork (1-2 sentences)
- "motif_candidates": List of visual motifs (e.g. "sky", "tree", "sea", "mountain", "flower")
- "style_candidates": List of art styles (e.g. "impressionism", "abstract", "realism")
- "subject_candidates": List of subjects (e.g. "landscape", "portrait", "still life")
- "mood_candidates": List of moods/atmospheres (e.g. "calm", "warm", "melancholic", "vibrant")

Respond with ONLY the JSON object, no other text."""

_MAX_RETRIES = 2
_TIMEOUT_SECONDS = 60.0


class VLMExtractionError(Exception):
    """VLMメタデータ抽出に失敗した場合の例外。"""


_MIME_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),  # WebP starts with RIFF....WEBP
    (b"GIF8", "image/gif"),
]


def _detect_mime_type(image_bytes: bytes) -> str:
    """画像バイナリのマジックバイトからMIMEタイプを推定する。"""
    for signature, mime in _MIME_SIGNATURES:
        if image_bytes[:len(signature)] == signature:
            return mime
    return "application/octet-stream"


class VLMClient:
    """LM Studio（OpenAI互換API）を使用したVLMメタデータ抽出クライアント。"""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.lm_studio_url
        self._http_client = httpx.Client(timeout=_TIMEOUT_SECONDS)

    def close(self) -> None:
        """HTTPクライアントをクローズする。"""
        self._http_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def extract_metadata(
        self,
        image_bytes: bytes,
        prompt: str,
    ) -> VLMExtractionResult:
        """画像からメタデータを抽出する。JSON解析失敗時はリトライする。"""
        messages = self._build_messages(image_bytes, prompt)
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                raw_content = self._call_api(messages)
                return self._parse_response(raw_content)
            except VLMExtractionError as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    logger.warning("VLM JSON parse failed (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES + 1, e)
                    continue
                raise VLMExtractionError(
                    f"Failed to extract metadata after {_MAX_RETRIES + 1} retries: {last_error}"
                ) from last_error

        raise VLMExtractionError(f"Failed after retries: {last_error}")  # pragma: no cover

    def _call_api(self, messages: list[dict[str, Any]]) -> str:
        """LM Studio chat/completions APIを呼び出す。"""
        url = f"{self._base_url}/v1/chat/completions"
        body: dict[str, Any] = {
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "artwork_metadata",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "caption": {"type": "string"},
                            "motif_candidates": {"type": "array", "items": {"type": "string"}},
                            "style_candidates": {"type": "array", "items": {"type": "string"}},
                            "subject_candidates": {"type": "array", "items": {"type": "string"}},
                            "mood_candidates": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": [
                            "caption",
                            "motif_candidates",
                            "style_candidates",
                            "subject_candidates",
                            "mood_candidates",
                        ],
                    },
                },
            },
        }

        try:
            response = self._http_client.post(url, json=body)
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise VLMExtractionError(f"Failed to connect to LM Studio: {e}") from e
        except httpx.HTTPStatusError as e:
            raise VLMExtractionError(f"LM Studio API error: {e}") from e

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise VLMExtractionError(f"Unexpected LM Studio response structure: {e}") from e

    def _build_messages(self, image_bytes: bytes, prompt: str) -> list[dict[str, Any]]:
        """OpenAI vision形式のメッセージを構築する。"""
        mime_type = _detect_mime_type(image_bytes)
        encoded = base64.b64encode(image_bytes).decode()
        data_url = f"data:{mime_type};base64,{encoded}"

        return [
            {
                "role": "system",
                "content": "You are an art analysis expert. Respond only with valid JSON.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            },
        ]

    def _parse_response(self, raw: str) -> VLMExtractionResult:
        """VLMレスポンスからJSONを抽出しバリデーションする。"""
        json_str = self._extract_json(raw)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise VLMExtractionError(f"Invalid JSON in VLM response: {e}") from e

        try:
            return VLMExtractionResult.model_validate(data)
        except Exception as e:
            raise VLMExtractionError(f"VLM response validation failed: {e}") from e

    def _extract_json(self, raw: str) -> str:
        """レスポンス文字列からJSON部分を抽出する。Markdownコードブロック・thinkタグ対応。"""
        # <think>...</think> タグを除去（Qwen3.5等の思考モード対応）
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # ```json ... ``` ブロックを探す
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
        if match:
            return match.group(1).strip()

        # {...} ブロックを探す（前後にテキストがあっても抽出）
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return match.group(0).strip()

        raise VLMExtractionError(f"No JSON found in VLM response: {raw[:200]}")
