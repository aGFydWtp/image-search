"""設定モデルのテスト。"""

from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

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


class TestReindexSettingsDefaults:
    """zero-downtime-reindex で追加される設定項目の既定値。"""

    def test_qdrant_alias_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.qdrant_alias == "artworks_current"

    def test_qdrant_api_key_default_none(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.qdrant_api_key is None

    def test_reindex_validation_ratio_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.reindex_validation_ratio == 0.9

    def test_reindex_sample_queries_path_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.reindex_sample_queries_path == "config/reindex_samples.json"

    def test_log_format_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.log_format == "json"

    def test_log_level_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.log_level == "INFO"

    def test_service_name_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.service_name == "image-search"

    def test_env_name_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.env_name == "local"


class TestReindexSettingsEnvOverride:
    """zero-downtime-reindex の設定項目を環境変数から上書きできる。"""

    def test_qdrant_alias_override(self) -> None:
        with patch.dict("os.environ", {"QDRANT_ALIAS": "artworks_staging"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.qdrant_alias == "artworks_staging"

    def test_qdrant_api_key_override_wraps_in_secret_str(self) -> None:
        with patch.dict("os.environ", {"QDRANT_API_KEY": "secret-key-123"}, clear=True):
            settings = Settings(_env_file=None)
            assert isinstance(settings.qdrant_api_key, SecretStr)
            assert settings.qdrant_api_key.get_secret_value() == "secret-key-123"

    def test_qdrant_api_key_not_exposed_in_repr(self) -> None:
        with patch.dict("os.environ", {"QDRANT_API_KEY": "secret-key-123"}, clear=True):
            settings = Settings(_env_file=None)
            assert "secret-key-123" not in repr(settings)
            assert "secret-key-123" not in str(settings)

    def test_reindex_validation_ratio_override(self) -> None:
        with patch.dict("os.environ", {"REINDEX_VALIDATION_RATIO": "0.75"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.reindex_validation_ratio == 0.75

    def test_reindex_sample_queries_path_override(self) -> None:
        env = {"REINDEX_SAMPLE_QUERIES_PATH": "/tmp/samples.json"}
        with patch.dict("os.environ", env, clear=True):
            settings = Settings(_env_file=None)
            assert settings.reindex_sample_queries_path == "/tmp/samples.json"

    def test_log_format_override_text(self) -> None:
        with patch.dict("os.environ", {"LOG_FORMAT": "text"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.log_format == "text"

    def test_log_level_override(self) -> None:
        with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.log_level == "DEBUG"

    def test_service_name_override(self) -> None:
        with patch.dict("os.environ", {"SERVICE_NAME": "ingestion"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.service_name == "ingestion"

    def test_env_name_override(self) -> None:
        with patch.dict("os.environ", {"ENV_NAME": "staging"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.env_name == "staging"


class TestReindexSettingsValidation:
    """値の妥当性検証。"""

    def test_log_format_invalid_value_raises(self) -> None:
        with patch.dict("os.environ", {"LOG_FORMAT": "xml"}, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_log_level_invalid_value_raises(self) -> None:
        with patch.dict("os.environ", {"LOG_LEVEL": "FOO"}, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)
