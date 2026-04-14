"""ValidationGate のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shared.logging import NOTICE
from shared.qdrant.validation import (
    CheckResult,
    ValidationGate,
    ValidationReport,
)


def _mock_client(
    counts: dict[str, int] | None = None,
    query_error: Exception | None = None,
) -> MagicMock:
    client = MagicMock()

    def _count(collection_name: str, exact: bool = True) -> MagicMock:  # noqa: ARG001
        result = MagicMock()
        result.count = counts.get(collection_name, 0) if counts else 0
        return result

    client.count.side_effect = _count
    if query_error is not None:
        client.query_points.side_effect = query_error
    else:
        client.query_points.return_value = MagicMock(points=[])
    return client


class TestPointCountRatio:
    """件数比で合否判定。"""

    def test_passes_when_ratio_meets_threshold(self) -> None:
        client = _mock_client(counts={"old": 1000, "new": 950})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])

        assert report.passed is True
        ratio_check = next(c for c in report.checks if c.name == "point_count_ratio")
        assert ratio_check.passed is True

    def test_fails_when_ratio_below_threshold(self) -> None:
        client = _mock_client(counts={"old": 1000, "new": 500})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])

        assert report.passed is False
        ratio_check = next(c for c in report.checks if c.name == "point_count_ratio")
        assert ratio_check.passed is False

    def test_old_none_skips_ratio_check(self) -> None:
        """初回投入など old が None のときは比率チェックなしで合格扱い。"""
        client = _mock_client(counts={"new": 100})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old=None, new="new", sample_queries=[[0.1] * 8])

        assert report.passed is True

    def test_ratio_check_detail_contains_counts(self) -> None:
        client = _mock_client(counts={"old": 1000, "new": 950})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])
        ratio_check = next(c for c in report.checks if c.name == "point_count_ratio")
        assert "1000" in ratio_check.detail and "950" in ratio_check.detail


class TestSampleQueries:
    """サンプル検索チェック。"""

    def test_passes_when_all_queries_succeed(self) -> None:
        client = _mock_client(counts={"old": 100, "new": 100})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(
            old="old", new="new", sample_queries=[[0.1] * 8, [0.2] * 8]
        )

        assert report.passed is True

    def test_zero_result_is_accepted(self) -> None:
        """サンプル検索が 0 件でも例外でない限り合格。"""
        client = _mock_client(counts={"old": 100, "new": 100})
        # query_points returns empty points (default from _mock_client)
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])

        assert report.passed is True

    def test_fails_when_query_raises(self) -> None:
        client = _mock_client(
            counts={"old": 100, "new": 100},
            query_error=ConnectionError("qdrant down"),
        )
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])

        assert report.passed is False
        failing = [c for c in report.checks if not c.passed]
        assert any("sample_query" in c.name for c in failing)


class TestSkipValidation:
    def test_skip_validation_bypasses_all_checks(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = _mock_client(counts={"old": 1000, "new": 100})  # would fail ratio
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        caplog.set_level("WARNING")
        report = gate.validate(
            old="old", new="new", sample_queries=[], skip_validation=True
        )

        assert report.passed is True
        skip_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.validation.skipped"
        ]
        assert len(skip_records) == 1
        assert skip_records[0].levelname == "WARNING"

    def test_skip_validation_does_not_query_qdrant(self) -> None:
        client = _mock_client()
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        gate.validate(
            old="old", new="new", sample_queries=[[0.1] * 8], skip_validation=True
        )

        client.count.assert_not_called()
        client.query_points.assert_not_called()


class TestLogging:
    def test_failure_logs_validation_failed_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = _mock_client(counts={"old": 1000, "new": 100})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        caplog.set_level("ERROR")
        gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])

        failed_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.validation.failed"
        ]
        assert len(failed_records) == 1

    def test_success_logs_validation_passed_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = _mock_client(counts={"old": 100, "new": 100})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        caplog.set_level("DEBUG")
        gate.validate(old="old", new="new", sample_queries=[[0.1] * 8])

        passed_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.validation.passed"
        ]
        assert len(passed_records) == 1
        assert passed_records[0].levelno == NOTICE


class TestReport:
    def test_report_is_frozen_dataclass(self) -> None:
        client = _mock_client(counts={"old": 100, "new": 100})
        gate = ValidationGate(client=client, sample_ratio_threshold=0.9)

        report = gate.validate(old="old", new="new", sample_queries=[])

        assert isinstance(report, ValidationReport)
        for check in report.checks:
            assert isinstance(check, CheckResult)
