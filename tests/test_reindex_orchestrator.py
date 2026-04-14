"""ReindexOrchestrator のテスト。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from shared.qdrant.alias_admin import AliasAdmin, SwapResult
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.validation import CheckResult, ValidationGate, ValidationReport
from services.ingestion.reindex import (
    CollectionExistsError,
    ReindexOrchestrator,
    ReindexResult,
)


def _passed_report() -> ValidationReport:
    return ValidationReport(
        passed=True,
        checks=(CheckResult(name="ok", passed=True, detail="all good"),),
    )


def _failed_report() -> ValidationReport:
    return ValidationReport(
        passed=False,
        checks=(CheckResult(name="point_count_ratio", passed=False, detail="too low"),),
    )


def _swap_result(new: str, prev: str | None = None) -> SwapResult:
    return SwapResult(
        alias="artworks_current",
        previous_target=prev,
        new_target=new,
        swapped_at=datetime.now(tz=timezone.utc),
    )


def _make_orchestrator(
    *,
    target_exists: bool = False,
    validation_report: ValidationReport | None = None,
    current_alias_target: str | None = "artworks_v1",
    progress_interval: int = 2,
) -> tuple[ReindexOrchestrator, MagicMock, MagicMock, MagicMock, MagicMock]:
    client = MagicMock()
    client.collection_exists.return_value = target_exists

    repo = MagicMock(spec=QdrantRepository)
    admin = MagicMock(spec=AliasAdmin)
    admin.current_target.return_value = current_alias_target
    admin.swap.return_value = _swap_result("artworks_v2", prev=current_alias_target)
    gate = MagicMock(spec=ValidationGate)
    gate.validate.return_value = validation_report or _passed_report()

    orchestrator = ReindexOrchestrator(
        client=client,
        repository=repo,
        alias_admin=admin,
        validation_gate=gate,
        alias_name="artworks_current",
        progress_interval=progress_interval,
    )
    return orchestrator, client, repo, admin, gate


def _populate_success(count: int):
    def _populate(target: str):  # noqa: ARG001
        for _ in range(count):
            yield True

    return _populate


def _populate_mixed(results: list[bool]):
    def _populate(target: str):  # noqa: ARG001
        for ok in results:
            yield ok

    return _populate


def _populate_raises():
    def _populate(target: str):  # noqa: ARG001
        yield True
        raise RuntimeError("source stream broken")

    return _populate


class TestOrderOfOperations:
    """create → populate → validate → swap の順に呼ばれる。"""

    def test_happy_path_calls_in_order(self) -> None:
        orch, _client, repo, admin, gate = _make_orchestrator()

        result = orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(3),
            sample_query_vectors=[[0.1] * 4],
        )

        repo.ensure_collection.assert_called_once_with("artworks_v2")
        gate.validate.assert_called_once()
        admin.swap.assert_called_once_with("artworks_current", "artworks_v2")
        assert result.swapped is True
        assert result.processed_count == 3
        assert result.failed_count == 0
        assert result.target_collection == "artworks_v2"


class TestCollectionExists:
    """既存同名コレクションのハンドリング。"""

    def test_raises_when_target_exists_by_default(self) -> None:
        orch, _, repo, admin, gate = _make_orchestrator(target_exists=True)

        with pytest.raises(CollectionExistsError):
            orch.run(
                target_collection="artworks_v2",
                populate=_populate_success(1),
                sample_query_vectors=[],
            )
        repo.ensure_collection.assert_not_called()
        gate.validate.assert_not_called()
        admin.swap.assert_not_called()

    def test_force_recreate_drops_and_rebuilds(self) -> None:
        orch, client, repo, admin, _ = _make_orchestrator(target_exists=True)

        orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(1),
            sample_query_vectors=[],
            force_recreate=True,
        )

        client.delete_collection.assert_called_once_with(
            collection_name="artworks_v2"
        )
        repo.ensure_collection.assert_called_once_with("artworks_v2")
        admin.swap.assert_called_once()


class TestPopulateFailure:
    """populate 中の例外は swap を阻止する。"""

    def test_exception_during_populate_aborts_swap(self) -> None:
        orch, _, repo, admin, gate = _make_orchestrator()

        with pytest.raises(RuntimeError):
            orch.run(
                target_collection="artworks_v2",
                populate=_populate_raises(),
                sample_query_vectors=[],
            )

        repo.ensure_collection.assert_called_once_with("artworks_v2")
        gate.validate.assert_not_called()
        admin.swap.assert_not_called()

    def test_new_collection_is_kept_on_failure(self) -> None:
        """投入途中で落ちても新コレクションは削除しない (冪等再実行のため)。"""
        orch, client, _repo, _admin, _gate = _make_orchestrator()

        with pytest.raises(RuntimeError):
            orch.run(
                target_collection="artworks_v2",
                populate=_populate_raises(),
                sample_query_vectors=[],
            )

        client.delete_collection.assert_not_called()


class TestValidationFailure:
    """検証失敗は swap を阻止し、非ゼロな結果を返す。"""

    def test_validation_failure_blocks_swap(self) -> None:
        orch, _, _, admin, _ = _make_orchestrator(
            validation_report=_failed_report()
        )

        result = orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(1),
            sample_query_vectors=[[0.1] * 4],
        )

        admin.swap.assert_not_called()
        assert result.swapped is False
        assert result.validation_report is not None
        assert result.validation_report.passed is False


class TestDryRun:
    """dry_run=True は validator を呼ぶが swap は呼ばない。"""

    def test_dry_run_skips_swap_but_validates(self) -> None:
        orch, _, _, admin, gate = _make_orchestrator()

        result = orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(1),
            sample_query_vectors=[[0.1] * 4],
            dry_run=True,
        )

        gate.validate.assert_called_once()
        admin.swap.assert_not_called()
        assert result.swapped is False


class TestSkipValidation:
    def test_skip_validation_is_forwarded_to_gate(self) -> None:
        orch, _, _, _admin, gate = _make_orchestrator()

        orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(1),
            sample_query_vectors=[[0.1] * 4],
            skip_validation=True,
        )

        assert gate.validate.call_args.kwargs["skip_validation"] is True


class TestProgressLogging:
    """進捗ログが一定件数ごとに出力される。"""

    def test_emits_progress_event_at_interval(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        orch, _, _, _, _ = _make_orchestrator(progress_interval=2)

        caplog.set_level("INFO")
        orch.run(
            target_collection="artworks_v2",
            populate=_populate_mixed([True, True, True, True, False]),
            sample_query_vectors=[],
        )

        progress_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.progress"
        ]
        # 5 件 / interval 2 = 2 回 + 終端 1 回 = 3
        assert len(progress_records) >= 2

    def test_started_event_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        orch, _, _, _, _ = _make_orchestrator()

        caplog.set_level("INFO")
        orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(1),
            sample_query_vectors=[],
        )

        started = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.started"
        ]
        assert len(started) == 1


class TestConstructor:
    """コンストラクタのバリデーション。"""

    def test_rejects_non_positive_progress_interval(self) -> None:
        with pytest.raises(ValueError):
            ReindexOrchestrator(
                client=MagicMock(),
                repository=MagicMock(),
                alias_admin=MagicMock(),
                validation_gate=MagicMock(),
                alias_name="artworks_current",
                progress_interval=0,
            )

    def test_rejects_negative_progress_interval(self) -> None:
        with pytest.raises(ValueError):
            ReindexOrchestrator(
                client=MagicMock(),
                repository=MagicMock(),
                alias_admin=MagicMock(),
                validation_gate=MagicMock(),
                alias_name="artworks_current",
                progress_interval=-10,
            )


class TestResultShape:
    def test_result_is_frozen_dataclass(self) -> None:
        orch, _, _, _, _ = _make_orchestrator()

        result = orch.run(
            target_collection="artworks_v2",
            populate=_populate_success(2),
            sample_query_vectors=[],
        )

        assert isinstance(result, ReindexResult)
        with pytest.raises(Exception):
            result.swapped = False  # type: ignore[misc]
