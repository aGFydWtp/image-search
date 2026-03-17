"""設定モデルのテスト。"""

from unittest.mock import patch

from shared.config import Settings


class TestSettings:
    def test_default_values(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.qdrant_host == "localhost"
            assert settings.qdrant_port == 6333
            assert settings.qdrant_collection == "artworks_v1"
            assert settings.vector_dim == 1152

    def test_lm_studio_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.lm_studio_url == "http://localhost:1234"

    def test_embedding_service_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.embedding_service_url == "http://localhost:8100"

    def test_env_override(self) -> None:
        env = {"QDRANT_HOST": "qdrant-server", "QDRANT_PORT": "6334"}
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)
            assert settings.qdrant_host == "qdrant-server"
            assert settings.qdrant_port == 6334
