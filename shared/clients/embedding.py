"""EmbeddingClient: SigLIP2埋め込みサービスへのHTTP呼び出しクライアント。"""

import logging
from typing import Self

import httpx

from shared.config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30.0


class EmbeddingError(Exception):
    """埋め込みサービスとの通信に失敗した場合の例外。"""


class EmbeddingClient:
    """SigLIP2埋め込みサービスへのREST APIクライアント。"""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.embedding_service_url
        self._vector_dim = settings.vector_dim
        self._http_client = httpx.Client(timeout=_TIMEOUT_SECONDS)

    def close(self) -> None:
        """HTTPクライアントをクローズする。"""
        self._http_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def embed_image(self, image_bytes: bytes) -> list[float]:
        """画像バイナリから1152次元の埋め込みベクトルを取得する。"""
        url = f"{self._base_url}/embed/image"

        try:
            response = self._http_client.post(
                url,
                content=image_bytes,
                headers={"Content-Type": "application/octet-stream"},
            )
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise EmbeddingError(f"Failed to connect to embedding service: {e}") from e
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(f"Embedding service error: {e}") from e

        return self._extract_vector(response)

    def embed_text(self, text: str) -> list[float]:
        """テキスト文字列から1152次元の埋め込みベクトルを取得する。"""
        url = f"{self._base_url}/embed/text"

        try:
            response = self._http_client.post(url, json={"text": text})
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise EmbeddingError(f"Failed to connect to embedding service: {e}") from e
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(f"Embedding service error: {e}") from e

        return self._extract_vector(response)

    def _extract_vector(self, response: httpx.Response) -> list[float]:
        """レスポンスからベクトルを抽出しバリデーションする。"""
        data = response.json()

        try:
            vector = data["vector"]
        except (KeyError, TypeError) as e:
            raise EmbeddingError(f"Unexpected embedding response structure: {e}") from e

        if len(vector) != self._vector_dim:
            raise EmbeddingError(
                f"Vector dimension mismatch: expected {self._vector_dim}, got {len(vector)}"
            )

        return vector
