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

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from typing import Callable, Iterable

from qdrant_client import QdrantClient
from qdrant_client.models import CreateAlias, CreateAliasOperation

from shared.config import Settings
from shared.logging import configure_logging
from shared.qdrant.alias_admin import (
    AliasAdmin,
    CollectionNotFoundError,
    PhysicalCollectionInUseError,
)
from shared.qdrant.alias_admin import SwapResult
from shared.qdrant.factory import build_repository
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.sample_queries import (
    SampleQueriesError,
    embed_sample_queries,
    load_sample_queries,
)
from shared.qdrant.validation import ValidationGate, ValidationReport

logger = logging.getLogger(__name__)

_VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_PHYSICAL_NAME_PATTERN = re.compile(r"^artworks_[a-zA-Z0-9_-]+$")

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _validate_version(value: str) -> str:
    """``--target-version`` / ``--to`` の値を正規表現で検証する。"""
    if not _VERSION_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            f"invalid target-version '{value}': "
            f"must match {_VERSION_PATTERN.pattern}"
        )
    return value


def _validate_physical_name(value: str) -> str:
    """``drop-collection`` が受ける物理コレクション名を検証する。"""
    if not _PHYSICAL_NAME_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            f"invalid collection name '{value}': "
            f"must match {_PHYSICAL_NAME_PATTERN.pattern}"
        )
    return value


def _physical_name(version: str) -> str:
    return f"artworks_{version}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reindex",
        description="Qdrant Blue/Green 再インデックス CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="新物理コレクションを作成し切替まで実行")
    run.add_argument("--target-version", required=True, type=_validate_version)
    run.add_argument("--force-recreate", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--skip-validation", action="store_true")
    run.add_argument("--sample-ratio", type=float, default=None)

    rollback = sub.add_parser("rollback", help="エイリアスを指定バージョンへ戻す")
    rollback.add_argument("--to", required=True, type=_validate_version, dest="to")

    drop = sub.add_parser(
        "drop-collection", help="物理コレクションを削除 (現行ターゲットは拒否)"
    )
    drop.add_argument("name", type=_validate_physical_name)

    sub.add_parser("init-alias", help="既存物理コレクションに初期エイリアスを張る")

    return parser


class _TargetedRepository:
    """``QdrantRepository`` への薄いプロキシ。``upsert_artwork`` を指定物理名で固定する。

    ``IngestionService`` が利用する読み書き面のみを実装する部分プロキシ。
    将来 IngestionService が他メソッドを呼ぶようになったらここにも対応を追加する。
    """

    def __init__(self, delegate: QdrantRepository, target: str) -> None:
        self._delegate = delegate
        self._target = target

    def upsert_artwork(
        self,
        *,
        artwork_id: str,
        image_vector: list[float],
        text_vector: list[float],
        payload,
    ) -> None:
        self._delegate.upsert_artwork(
            artwork_id=artwork_id,
            image_vector=image_vector,
            text_vector=text_vector,
            payload=payload,
            target_collection=self._target,
        )

    def exists(self, artwork_id: str) -> bool:
        return self._delegate.exists(artwork_id)


def _build_populate(
    settings: Settings, repository: QdrantRepository
) -> Callable[[str], Iterable[bool]]:
    """実 Ingestion パイプラインを組み立て、target_collection を pin した
    populate コールバックを返す。

    Firebase / VLM / Embedding クライアントは 1 回だけ生成するが、
    ``IngestionService`` は target ごとに新規構築してプロキシ ``_TargetedRepository``
    をコンストラクタ経由で渡す (private 属性の外部書き換えを避ける)。

    テストでは本関数自体をパッチで差し替えるため、CLI 統合時のみの責務。
    """
    from services.ingestion.color_extractor import ColorExtractor
    from services.ingestion.firebase_storage import FirebaseStorageClient
    from services.ingestion.image_preprocessor import ImagePreprocessor
    from services.ingestion.pipeline import IngestionService
    from shared.clients.embedding import EmbeddingClient
    from shared.clients.vlm import VLMClient
    from shared.taxonomy.mapper import TaxonomyMapper

    firebase = FirebaseStorageClient(
        credentials_path=settings.firebase_credentials_path,
        bucket_name=settings.firebase_storage_bucket,
    )
    vlm = VLMClient(settings=settings)
    embedding = EmbeddingClient(settings=settings)
    preprocessor = ImagePreprocessor()
    color_extractor = ColorExtractor()
    taxonomy_mapper = TaxonomyMapper()

    def _populate(target: str) -> Iterable[bool]:
        ingestion = IngestionService(
            vlm_client=vlm,
            embedding_client=embedding,
            qdrant_repo=_TargetedRepository(repository, target=target),
            preprocessor=preprocessor,
            color_extractor=color_extractor,
            taxonomy_mapper=taxonomy_mapper,
        )
        for blob_path in firebase.list_images(prefix=settings.firebase_storage_prefix):
            artwork_id = firebase.extract_artwork_id(blob_path)
            image_bytes = firebase.download_image(blob_path)
            image_url = firebase.get_public_url(blob_path)
            yield ingestion.process_artwork(
                artwork_id=artwork_id,
                image_bytes=image_bytes,
                image_url=image_url,
                title=artwork_id,
                artist_name="",
            )

    return _populate


def _load_sample_vectors(settings: Settings) -> list[list[float]]:
    """サンプルクエリ JSON を読み、embedding サービスでベクトル化する。

    テストでは本関数自体をパッチで差し替える。
    """
    from shared.clients.embedding import EmbeddingClient

    queries = load_sample_queries(settings.reindex_sample_queries_path)
    embedding = EmbeddingClient(settings=settings)
    return embed_sample_queries(queries, embed_text=embedding.embed_text)


def _cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    client, _, repo = build_repository(settings)
    admin = AliasAdmin(client=client)
    ratio = (
        args.sample_ratio
        if args.sample_ratio is not None
        else settings.reindex_validation_ratio
    )
    gate = ValidationGate(client=client, sample_ratio_threshold=ratio)
    orch = ReindexOrchestrator(
        client=client,
        repository=repo,
        alias_admin=admin,
        validation_gate=gate,
        alias_name=settings.qdrant_alias,
    )

    try:
        sample_vectors = _load_sample_vectors(settings)
    except SampleQueriesError as exc:
        logger.error(
            "failed to load sample queries",
            extra={"event": "reindex.samples.load_failed", "error": str(exc)},
        )
        return 2

    populate = _build_populate(settings, repo)
    target = _physical_name(args.target_version)

    result = orch.run(
        target_collection=target,
        populate=populate,
        sample_query_vectors=sample_vectors,
        force_recreate=args.force_recreate,
        dry_run=args.dry_run,
        skip_validation=args.skip_validation,
    )

    if args.dry_run:
        return 0
    return 0 if result.swapped else 1


def _cmd_rollback(args: argparse.Namespace, settings: Settings) -> int:
    client, _, _ = build_repository(settings)
    admin = AliasAdmin(client=client)
    try:
        admin.rollback(settings.qdrant_alias, previous_target=_physical_name(args.to))
    except CollectionNotFoundError as exc:
        logger.error(
            "rollback target not found",
            extra={"event": "reindex.rollback.failed", "error": str(exc)},
        )
        return 1
    return 0


def _cmd_drop(args: argparse.Namespace, settings: Settings) -> int:
    client, _, _ = build_repository(settings)
    admin = AliasAdmin(client=client)
    try:
        admin.drop_physical_collection(args.name, alias=settings.qdrant_alias)
    except PhysicalCollectionInUseError as exc:
        logger.error(
            "cannot drop collection currently in use",
            extra={
                "event": "reindex.collection.drop_refused",
                "error": str(exc),
                "collection": args.name,
            },
        )
        return 1
    return 0


def _cmd_init_alias(_: argparse.Namespace, settings: Settings) -> int:
    client, _resolver, _repo = build_repository(settings)
    admin = AliasAdmin(client=client)
    current = admin.current_target(settings.qdrant_alias)
    if current is not None:
        logger.info(
            "alias already exists; init-alias is a no-op",
            extra={
                "event": "reindex.alias.init_skipped",
                "alias": settings.qdrant_alias,
                "target": current,
            },
        )
        return 0
    client.update_collection_aliases(
        change_aliases_operations=[
            CreateAliasOperation(
                create_alias=CreateAlias(
                    alias_name=settings.qdrant_alias,
                    collection_name=settings.qdrant_collection,
                )
            )
        ]
    )
    logger.info(
        "alias initialized",
        extra={
            "event": "reindex.alias.initialized",
            "alias": settings.qdrant_alias,
            "target": settings.qdrant_collection,
        },
    )
    return 0


_DISPATCH: dict[str, Callable[[argparse.Namespace, Settings], int]] = {
    "run": _cmd_run,
    "rollback": _cmd_rollback,
    "drop-collection": _cmd_drop,
    "init-alias": _cmd_init_alias,
}


def cli_main(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。戻り値は終了コード。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings)
    handler = _DISPATCH[args.command]
    return handler(args, settings)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main())
