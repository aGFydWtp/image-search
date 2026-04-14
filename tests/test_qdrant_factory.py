"""Qdrant ファクトリのテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from shared.config import Settings
from shared.qdrant.factory import build_repository
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.resolver import CollectionResolver


def _settings(**overrides) -> Settings:
    defaults = {
        "qdrant_host": "qdrant-test",
        "qdrant_port": 6333,
        "qdrant_collection": "artworks_v1",
        "qdrant_alias": "artworks_current",
        "vector_dim": 1152,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestBuildRepository:
    """build_repository(settings) は Client / Resolver / Repository を返す。"""

    @patch("shared.qdrant.factory.QdrantClient")
    def test_returns_client_resolver_repository_triple(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client_cls.return_value = MagicMock()
        settings = _settings()

        client, resolver, repo = build_repository(settings)

        assert client is mock_client_cls.return_value
        assert isinstance(resolver, CollectionResolver)
        assert isinstance(repo, QdrantRepository)

    @patch("shared.qdrant.factory.QdrantClient")
    def test_client_is_initialized_with_host_and_port(
        self, mock_client_cls: MagicMock
    ) -> None:
        settings = _settings(qdrant_host="qdrant-prod", qdrant_port=6334)

        build_repository(settings)

        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs["host"] == "qdrant-prod"
        assert kwargs["port"] == 6334

    @patch("shared.qdrant.factory.QdrantClient")
    def test_resolver_uses_alias_from_settings(
        self, mock_client_cls: MagicMock
    ) -> None:
        settings = _settings(qdrant_alias="artworks_staging")

        _, resolver, _ = build_repository(settings)

        assert resolver.alias_name == "artworks_staging"

    @patch("shared.qdrant.factory.QdrantClient")
    def test_repository_receives_vector_dim(
        self, mock_client_cls: MagicMock
    ) -> None:
        settings = _settings(vector_dim=768)

        _, _, repo = build_repository(settings)

        assert repo._vector_dim == 768

    @patch("shared.qdrant.factory.QdrantClient")
    def test_api_key_passed_to_client_when_set(
        self, mock_client_cls: MagicMock
    ) -> None:
        settings = _settings(qdrant_api_key=SecretStr("super-secret"))

        build_repository(settings)

        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs.get("api_key") == "super-secret"

    @patch("shared.qdrant.factory.QdrantClient")
    def test_api_key_is_none_when_unset(self, mock_client_cls: MagicMock) -> None:
        settings = _settings()

        build_repository(settings)

        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs.get("api_key") is None

    @patch("shared.qdrant.factory.QdrantClient")
    def test_secret_str_not_exposed_in_repr(
        self, mock_client_cls: MagicMock
    ) -> None:
        """ファクトリが settings を repr しても API キーが露出しない。"""
        settings = _settings(qdrant_api_key=SecretStr("leaky"))

        build_repository(settings)

        assert "leaky" not in repr(settings)
