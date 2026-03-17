"""プロジェクト共通設定。環境変数から読み込む。"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """環境変数ベースのアプリケーション設定。"""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "artworks_v1"

    # LM Studio (Qwen2.5-VL)
    lm_studio_url: str = "http://localhost:1234"

    # SigLIP2 Embedding Service
    embedding_service_url: str = "http://localhost:8100"

    # Firebase
    firebase_credentials_path: str = ""
    firebase_storage_bucket: str = ""

    # Vector dimensions
    vector_dim: int = 1152

    model_config = {"env_file": ".env", "env_prefix": ""}
