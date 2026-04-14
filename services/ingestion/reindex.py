"""Blue/Green 再インデックスの中核オーケストレーター。

フロー:
    1. 新物理コレクションを作成 (既存なら既定で中止、``force_recreate`` で再作成)
    2. ``populate`` コールバックを実行し、進捗を ``reindex.progress`` イベントで記録
    3. :class:`ValidationGate` で切替前検証
    4. ``dry_run`` or 検証失敗でなければ :class:`AliasAdmin.swap` で原子切替

設計上、``populate`` は呼び出し側 (CLI) が組み立てる汎用コールバックで、
ターゲット物理コレクション名を受け取り、各アートワークの成否を bool で
yield する。これにより Ingestion パイプラインとの具体的な結合を Orchestrator
に持ち込まない。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable

from qdrant_client import QdrantClient

from shared.qdrant.alias_admin import AliasAdmin, SwapResult
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.validation import ValidationGate, ValidationReport

logger = logging.getLogger(__name__)

PopulateFn = Callable[[str], Iterable[bool]]


class CollectionExistsError(RuntimeError):
    """``force_recreate=False`` 時に、既に同名コレクションが存在する。"""


@dataclass(frozen=True)
class ReindexResult:
    """再インデックス実行結果。"""

    target_collection: str
    processed_count: int
    failed_count: int
    validation_report: ValidationReport | None
    swap_result: SwapResult | None
    swapped: bool


class ReindexOrchestrator:
    """create → populate → validate → swap を順に実行するオーケストレーター。"""

    def __init__(
        self,
        *,
        client: QdrantClient,
        repository: QdrantRepository,
        alias_admin: AliasAdmin,
        validation_gate: ValidationGate,
        alias_name: str,
        progress_interval: int = 100,
    ) -> None:
        if progress_interval <= 0:
            raise ValueError("progress_interval must be positive")
        self._client = client
        self._repo = repository
        self._admin = alias_admin
        self._gate = validation_gate
        self._alias = alias_name
        self._progress_interval = progress_interval

    def run(
        self,
        *,
        target_collection: str,
        populate: PopulateFn,
        sample_query_vectors: list[list[float]],
        force_recreate: bool = False,
        dry_run: bool = False,
        skip_validation: bool = False,
    ) -> ReindexResult:
        """再インデックスを開始から切替まで一気通貫で実行する。"""
        previous_target = self._admin.current_target(self._alias)
        logger.info(
            "reindex started",
            extra={
                "event": "reindex.started",
                "target": target_collection,
                "previous_target": previous_target,
                "alias": self._alias,
                "dry_run": dry_run,
            },
        )

        self._prepare_collection(target_collection, force_recreate=force_recreate)
        processed, failed = self._populate_and_track(populate, target_collection)

        report = self._gate.validate(
            old=previous_target,
            new=target_collection,
            sample_queries=sample_query_vectors,
            skip_validation=skip_validation,
        )

        swap_result: SwapResult | None = None
        swapped = False
        if dry_run:
            logger.info(
                "dry run: skipping alias swap",
                extra={
                    "event": "reindex.dry_run",
                    "target": target_collection,
                    "validation_passed": report.passed,
                },
            )
        elif not report.passed:
            logger.error(
                "validation failed; skipping alias swap",
                extra={
                    "event": "reindex.aborted",
                    "target": target_collection,
                },
            )
        else:
            swap_result = self._admin.swap(self._alias, target_collection)
            swapped = True

        return ReindexResult(
            target_collection=target_collection,
            processed_count=processed,
            failed_count=failed,
            validation_report=report,
            swap_result=swap_result,
            swapped=swapped,
        )

    def _prepare_collection(self, target: str, *, force_recreate: bool) -> None:
        if self._client.collection_exists(collection_name=target):
            if not force_recreate:
                raise CollectionExistsError(
                    f"collection '{target}' already exists; "
                    "pass force_recreate=True to drop and rebuild"
                )
            self._client.delete_collection(collection_name=target)
            logger.info(
                "recreating existing collection",
                extra={
                    "event": "reindex.collection.recreated",
                    "target": target,
                },
            )
        self._repo.ensure_collection(target)
        logger.info(
            "target collection ready",
            extra={
                "event": "reindex.collection.created",
                "target": target,
            },
        )

    def _populate_and_track(
        self, populate: PopulateFn, target: str
    ) -> tuple[int, int]:
        processed = 0
        failed = 0
        for ok in populate(target):
            if ok:
                processed += 1
            else:
                failed += 1
            total = processed + failed
            if total % self._progress_interval == 0:
                self._log_progress(target, processed, failed)
        # 終端の進捗 (interval に揃っていないときのみ)
        if (processed + failed) % self._progress_interval != 0:
            self._log_progress(target, processed, failed)
        return processed, failed

    def _log_progress(self, target: str, processed: int, failed: int) -> None:
        logger.info(
            "reindex progress",
            extra={
                "event": "reindex.progress",
                "target": target,
                "processed": processed,
                "failed": failed,
            },
        )
