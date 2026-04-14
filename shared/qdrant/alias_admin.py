"""Qdrant エイリアス管理 (Blue/Green 切替・ロールバック・物理削除)。

``update_collection_aliases`` は Qdrant 側でアトミック実行されるため、
``DeleteAlias`` + ``CreateAlias`` を単一リクエストで発行することで切替を
原子化する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
)

logger = logging.getLogger(__name__)


class CollectionNotFoundError(LookupError):
    """指定された物理コレクションが Qdrant 上に存在しない。"""


class PhysicalCollectionInUseError(RuntimeError):
    """エイリアスが現在指しているコレクションは削除できない。"""


@dataclass(frozen=True)
class SwapResult:
    """エイリアス切替の結果。"""

    alias: str
    previous_target: str | None
    new_target: str
    swapped_at: datetime


class AliasAdmin:
    """エイリアスの作成・切替・削除をアトミックに行う管理クラス。"""

    def __init__(self, client: QdrantClient) -> None:
        self._client = client

    def current_target(self, alias: str) -> str | None:
        """指定エイリアスが現在指している物理コレクション名を返す。未定義なら None。"""
        response = self._client.get_aliases()
        for description in response.aliases:
            if description.alias_name == alias:
                return description.collection_name
        return None

    def swap(self, alias: str, new_target: str) -> SwapResult:
        """エイリアスを ``new_target`` に向ける。

        ``DeleteAlias`` + ``CreateAlias`` を 1 回の
        ``update_collection_aliases`` で発行し、Qdrant 側で原子的に処理される。
        ``new_target`` 物理コレクションが不在の場合は
        :class:`CollectionNotFoundError` を送出し、操作は行わない。

        Raises:
            CollectionNotFoundError: ``new_target`` が Qdrant 上に存在しない。
        """
        return self._swap(alias, new_target, event="reindex.alias.swap")

    def rollback(self, alias: str, previous_target: str) -> SwapResult:
        """エイリアスを ``previous_target`` に戻す。``swap`` の薄いラッパ。"""
        return self._swap(alias, previous_target, event="reindex.rollback")

    def drop_physical_collection(self, name: str, alias: str) -> None:
        """物理コレクションを削除する。現在エイリアスが指している場合は拒否。

        Note:
            このガードには TOCTOU レースがある。``current_target`` チェックと
            ``delete_collection`` 呼び出しの間に別プロセスが alias を name へ
            向け直すと、運用中コレクションを削除する可能性がある。
            Qdrant には「エイリアス未参照なら削除」のアトミック API がないため
            完全排除は不可。単一運用者前提のため許容し、並列運用時は CLI 側で
            ロック機構の導入を検討する。

        Raises:
            PhysicalCollectionInUseError: ``name`` が ``alias`` の現行ターゲット。
        """
        if self.current_target(alias) == name:
            raise PhysicalCollectionInUseError(
                f"collection '{name}' is currently targeted by alias '{alias}' "
                "and cannot be dropped"
            )
        self._client.delete_collection(collection_name=name)
        logger.info(
            "collection dropped",
            extra={"event": "reindex.collection.dropped", "collection": name},
        )

    def _swap(self, alias: str, new_target: str, *, event: str) -> SwapResult:
        if not self._client.collection_exists(collection_name=new_target):
            raise CollectionNotFoundError(
                f"collection '{new_target}' does not exist in Qdrant"
            )
        previous = self.current_target(alias)

        operations = [
            DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)),
            CreateAliasOperation(
                create_alias=CreateAlias(alias_name=alias, collection_name=new_target)
            ),
        ]

        try:
            self._client.update_collection_aliases(
                change_aliases_operations=operations
            )
        except Exception:
            logger.exception(
                "alias swap failed",
                extra={
                    "event": "reindex.alias.swap.failed",
                    "alias": alias,
                    "previous_target": previous,
                    "new_target": new_target,
                },
            )
            raise

        result = SwapResult(
            alias=alias,
            previous_target=previous,
            new_target=new_target,
            swapped_at=datetime.now(tz=timezone.utc),
        )
        logger.info(
            "alias swapped",
            extra={
                "event": event,
                "alias": alias,
                "previous_target": previous,
                "new_target": new_target,
            },
        )
        return result
