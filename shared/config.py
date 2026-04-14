"""プロジェクト共通設定。環境変数から読み込む。"""

from typing import Any, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """環境変数ベースのアプリケーション設定。"""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "artworks_v1"
    qdrant_alias: str = "artworks_current"
    qdrant_api_key: SecretStr | None = None

    @field_validator("qdrant_api_key", mode="before")
    @classmethod
    def _empty_api_key_to_none(cls, value: Any) -> Any:
        """docker-compose から空文字で渡された API キーを None に正規化する。

        ``QDRANT_API_KEY: ${QDRANT_API_KEY:-}`` などの使い方で env が未設定のとき
        空文字になり、QdrantClient に空キー認証を投げてしまうのを避ける。
        """
        if value == "":
            return None
        return value

    # LM Studio (Qwen2.5-VL)
    lm_studio_url: str = "http://localhost:1234"

    # SigLIP2 Embedding Service
    embedding_service_url: str = "http://localhost:8100"

    # Firebase
    firebase_credentials_path: str = ""
    firebase_storage_bucket: str = ""
    firebase_storage_prefix: str = ""

    # Vector dimensions
    vector_dim: int = 1152

    # Reindex / ValidationGate
    reindex_validation_ratio: float = 0.9
    reindex_sample_queries_path: str = "config/reindex_samples.json"

    # Logging
    log_format: Literal["json", "text"] = "json"
    log_level: Literal[
        "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL"
    ] = "INFO"
    service_name: str = "image-search"
    env_name: str = "local"

    model_config = {"env_file": ".env", "env_prefix": ""}
