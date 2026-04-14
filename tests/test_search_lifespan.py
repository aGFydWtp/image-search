"""Search Service の lifespan 起動時検証テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shared.qdrant.resolver import AliasNotFoundError, CollectionResolver


def _mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.ensure_collection.return_value = None
    return repo


def _mock_resolver(exists: bool, alias_name: str = "artworks_current") -> MagicMock:
    resolver = MagicMock(spec=CollectionResolver)
    resolver.exists.return_value = exists
    resolver.alias_name = alias_name
    return resolver


class TestLifespanAliasExistenceCheck:
    """Req 1.2: 起動時にエイリアス未定義なら明示的エラーで起動失敗。"""

    def test_startup_fails_when_alias_not_defined(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client_mock = MagicMock()
        repo_mock = _mock_repo()
        resolver_mock = _mock_resolver(exists=False, alias_name="artworks_current")

        with patch(
            "shared.qdrant.factory.build_repository",
            return_value=(client_mock, resolver_mock, repo_mock),
        ), patch(
            "shared.logging.configure_logging"
        ):  # caplog と衝突させないため no-op 化
            from services.search.app import app

            caplog.set_level("CRITICAL")
            with pytest.raises((RuntimeError, AliasNotFoundError)):
                with TestClient(app):
                    pass  # lifespan enters here and should fail

        critical_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "search.alias.unresolved"
        ]
        assert len(critical_records) >= 1

    def test_startup_succeeds_when_alias_defined(self) -> None:
        client_mock = MagicMock()
        repo_mock = _mock_repo()
        resolver_mock = _mock_resolver(exists=True)

        with patch(
            "shared.qdrant.factory.build_repository",
            return_value=(client_mock, resolver_mock, repo_mock),
        ):
            from services.search.app import app

            with TestClient(app) as test_client:
                response = test_client.get("/health")
                assert response.status_code == 200

    def test_lifespan_uses_build_repository_factory(self) -> None:
        """lifespan が shared/qdrant/factory.build_repository を呼ぶ。"""
        client_mock = MagicMock()
        repo_mock = _mock_repo()
        resolver_mock = _mock_resolver(exists=True)

        with patch(
            "shared.qdrant.factory.build_repository",
            return_value=(client_mock, resolver_mock, repo_mock),
        ) as mock_factory:
            from services.search.app import app

            with TestClient(app):
                pass

            mock_factory.assert_called_once()
