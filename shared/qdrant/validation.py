"""再インデックス完了後、エイリアス切替前の検証ゲート。

- **件数比**: 新コレクション件数 / 旧コレクション件数 が閾値を満たすか
- **サンプル検索**: 指定ベクトルで ``query_points`` が例外なく返るか
  (件数 0 は許容、例外のみ NG)
- ``skip_validation=True`` で全チェックをスキップ (``--skip-validation``)

設計上、ValidationGate は**特定の物理コレクション**を対象とするため、
Resolver 経由ではなく :class:`qdrant_client.QdrantClient` を直接保持する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient

from shared.logging import NOTICE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckResult:
    """個別チェックの結果。"""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    """検証レポート。"""

    passed: bool
    checks: tuple[CheckResult, ...]


class ValidationGate:
    """エイリアス切替前の妥当性検証ゲート。"""

    def __init__(
        self, client: QdrantClient, sample_ratio_threshold: float = 0.9
    ) -> None:
        self._client = client
        self._threshold = sample_ratio_threshold

    def validate(
        self,
        old: str | None,
        new: str,
        sample_queries: list[list[float]],
        *,
        skip_validation: bool = False,
    ) -> ValidationReport:
        """新コレクション ``new`` の妥当性を検証する。

        Args:
            old: 旧物理コレクション。``None`` の場合は件数比チェックをスキップ。
            new: 新物理コレクション。
            sample_queries: `query_points` に渡すサンプルベクトル。
            skip_validation: True で全検証をスキップ、WARNING ログを残して合格扱い。
        """
        if skip_validation:
            logger.warning(
                "validation skipped by operator",
                extra={
                    "event": "reindex.validation.skipped",
                    "new": new,
                    "old": old,
                },
            )
            return ValidationReport(
                passed=True,
                checks=(
                    CheckResult(
                        name="skipped",
                        passed=True,
                        detail="--skip-validation was specified",
                    ),
                ),
            )

        checks: list[CheckResult] = []
        checks.append(self._check_point_count_ratio(old, new))
        checks.extend(self._check_sample_queries(new, sample_queries))

        passed = all(c.passed for c in checks)
        self._log_outcome(passed=passed, new=new, old=old, checks=checks)

        return ValidationReport(passed=passed, checks=tuple(checks))

    def _check_point_count_ratio(self, old: str | None, new: str) -> CheckResult:
        new_count = self._client.count(collection_name=new, exact=True).count
        if old is None:
            return CheckResult(
                name="point_count_ratio",
                passed=True,
                detail=f"new={new_count}, no previous collection to compare",
            )
        old_count = self._client.count(collection_name=old, exact=True).count
        if old_count == 0:
            return CheckResult(
                name="point_count_ratio",
                passed=True,
                detail=f"new={new_count}, old={old_count} (empty baseline)",
            )
        ratio = new_count / old_count
        passed = ratio >= self._threshold
        return CheckResult(
            name="point_count_ratio",
            passed=passed,
            detail=(
                f"new/old = {new_count}/{old_count} = {ratio:.3f} "
                f"(threshold: {self._threshold})"
            ),
        )

    def _check_sample_queries(
        self, new: str, sample_queries: list[list[float]]
    ) -> list[CheckResult]:
        if not sample_queries:
            return [
                CheckResult(
                    name="sample_queries",
                    passed=True,
                    detail="no sample queries configured",
                )
            ]
        failures: list[CheckResult] = []
        for index, vector in enumerate(sample_queries):
            try:
                self._client.query_points(
                    collection_name=new,
                    query=vector,
                    using="text_semantic",
                    limit=1,
                )
            except Exception as exc:
                failures.append(
                    CheckResult(
                        name=f"sample_query[{index}]",
                        passed=False,
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                )
        if failures:
            return failures
        return [
            CheckResult(
                name="sample_queries",
                passed=True,
                detail=f"all {len(sample_queries)} queries passed",
            )
        ]

    def _log_outcome(
        self,
        *,
        passed: bool,
        new: str,
        old: str | None,
        checks: list[CheckResult],
    ) -> None:
        if passed:
            logger.log(
                NOTICE,
                "validation passed",
                extra={
                    "event": "reindex.validation.passed",
                    "new": new,
                    "old": old,
                },
            )
            return
        logger.error(
            "validation failed",
            extra={
                "event": "reindex.validation.failed",
                "new": new,
                "old": old,
                "failed_checks": [c.name for c in checks if not c.passed],
            },
        )
