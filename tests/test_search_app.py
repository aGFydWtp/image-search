"""Search Service のヘルスチェックエンドポイント (/healthz, /readyz) のテスト。

Cloud Run / GKE のプローブに直接マップできる粒度を想定:
- /healthz: liveness (プロセス生存のみ)
- /readyz: readiness (エイリアス解決 + コレクション件数取得)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shared.qdrant.resolver import AliasNotFoundError, CollectionResolver


def _mock_resolver(
    resolve_result: str | Exception = "artworks_v1",
    alias_name: str = "artworks_current",
    exists: bool = True,
) -> MagicMock:
    resolver = MagicMock(spec=CollectionResolver)
    resolver.alias_name = alias_name
    resolver.exists.return_value = exists
    if isinstance(resolve_result, Exception):
        resolver.resolve.side_effect = resolve_result
    else:
        resolver.resolve.return_value = resolve_result
    return resolver


def _mock_repo(
    count_result: int | Exception = 100,
) -> MagicMock:
    repo = MagicMock()
    repo.ensure_collection.return_value = None
    if isinstance(count_result, Exception):
        repo.count.side_effect = count_result
    else:
        repo.count.return_value = count_result
    return repo


def _build_app(
    resolver: MagicMock, repo: MagicMock, *, suppress_logging_config: bool = True
) -> TestClient:
    client_mock = MagicMock()
    patchers = [
        patch(
            "shared.qdrant.factory.build_repository",
            return_value=(client_mock, resolver, repo),
        ),
    ]
    if suppress_logging_config:
        # configure_logging は root handler を差し替えるため、pytest の caplog
        # と衝突する。ログ捕捉が必要なテストでは no-op パッチで回避する。
        patchers.append(patch("shared.logging.configure_logging"))
    for p in patchers:
        p.start()
    from services.search.app import app

    tc = TestClient(app)
    tc.__enter__()
    return tc, patchers


def _teardown(tc: TestClient, patchers) -> None:
    tc.__exit__(None, None, None)
    for p in patchers:
        p.stop()


class TestHealthz:
    """/healthz は依存を確認せず 200 を返す (liveness)。"""

    def test_returns_200_with_status_ok(self) -> None:
        resolver = _mock_resolver()
        repo = _mock_repo()
        tc, patchers = _build_app(resolver, repo)
        try:
            response = tc.get("/healthz")
        finally:
            _teardown(tc, patchers)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_does_not_invoke_resolver(self) -> None:
        resolver = _mock_resolver()
        repo = _mock_repo()
        tc, patchers = _build_app(resolver, repo)
        try:
            resolver.resolve.reset_mock()
            repo.count.reset_mock()
            tc.get("/healthz")
        finally:
            _teardown(tc, patchers)
        resolver.resolve.assert_not_called()
        repo.count.assert_not_called()


class TestReadyz:
    """/readyz はエイリアス解決 + count 成功時のみ 200。"""

    def test_returns_200_with_alias_collection_points_count(self) -> None:
        resolver = _mock_resolver(
            resolve_result="artworks_v2", alias_name="artworks_current"
        )
        repo = _mock_repo(count_result=2500)
        tc, patchers = _build_app(resolver, repo)
        try:
            response = tc.get("/readyz")
        finally:
            _teardown(tc, patchers)
        assert response.status_code == 200
        body = response.json()
        assert body["alias"] == "artworks_current"
        assert body["collection"] == "artworks_v2"
        assert body["points_count"] == 2500

    def test_returns_503_when_alias_not_defined(self) -> None:
        resolver = _mock_resolver(
            resolve_result=AliasNotFoundError("alias missing")
        )
        repo = _mock_repo()
        tc, patchers = _build_app(resolver, repo)
        try:
            response = tc.get("/readyz")
        finally:
            _teardown(tc, patchers)
        assert response.status_code == 503

    def test_returns_503_when_count_fails(self) -> None:
        resolver = _mock_resolver()
        repo = _mock_repo(count_result=ConnectionError("qdrant down"))
        tc, patchers = _build_app(resolver, repo)
        try:
            response = tc.get("/readyz")
        finally:
            _teardown(tc, patchers)
        assert response.status_code == 503

    def test_does_not_expose_secrets_in_response(self) -> None:
        """`/readyz` レスポンスに API キー等が含まれない。"""
        resolver = _mock_resolver()
        repo = _mock_repo()
        # settings にシークレット混入していても、readyz には漏れない
        with patch(
            "shared.config.Settings",
            return_value=MagicMock(
                qdrant_api_key=SecretStr("leaky-key"),
                qdrant_alias="artworks_current",
                qdrant_collection="artworks_v1",
            ),
        ):
            tc, patchers = _build_app(resolver, repo)
            try:
                response = tc.get("/readyz")
            finally:
                _teardown(tc, patchers)
        assert response.status_code == 200
        raw = response.text
        assert "leaky-key" not in raw
        body = response.json()
        for forbidden_key in ("qdrant_api_key", "api_key", "password", "secret"):
            assert forbidden_key not in body

    def test_503_logs_readiness_failed_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """失敗経路で event=search.readiness.failed が ERROR 以上で記録される。"""
        resolver = _mock_resolver(
            resolve_result=AliasNotFoundError("alias missing"),
            alias_name="artworks_current",
        )
        repo = _mock_repo()
        tc, patchers = _build_app(resolver, repo)
        try:
            caplog.set_level("ERROR")
            response = tc.get("/readyz")
        finally:
            _teardown(tc, patchers)
        assert response.status_code == 503
        failed_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "search.readiness.failed"
        ]
        assert len(failed_records) == 1
        assert getattr(failed_records[0], "alias", None) == "artworks_current"
        assert getattr(failed_records[0], "error_type", None) == "AliasNotFoundError"

    def test_lifespan_configures_structured_logging_once(self) -> None:
        """lifespan が shared.logging.configure_logging を 1 回だけ呼ぶ。"""
        resolver = _mock_resolver()
        repo = _mock_repo()
        with patch("shared.logging.configure_logging") as mock_configure:
            tc, patchers = _build_app(
                resolver, repo, suppress_logging_config=False
            )
            try:
                mock_configure.assert_called_once()
            finally:
                _teardown(tc, patchers)

    def test_health_legacy_delegates_to_readyz(self) -> None:
        """既存の /health は /readyz と同じ挙動に委譲 (破壊的変更回避)。"""
        resolver = _mock_resolver(resolve_result="artworks_v1")
        repo = _mock_repo(count_result=42)
        tc, patchers = _build_app(resolver, repo)
        try:
            response = tc.get("/health")
        finally:
            _teardown(tc, patchers)
        assert response.status_code == 200
        body = response.json()
        assert body["alias"] == "artworks_current"
        assert body["collection"] == "artworks_v1"
        assert body["points_count"] == 42
