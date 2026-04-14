"""Qdrant エイリアス → 物理コレクション名の解決。

Read 経路を物理コレクション名から切り離すためのコンポーネント。
検索サービスのリクエストごとに :meth:`CollectionResolver.resolve` を呼び、
切替後の新コレクションへプロセス再起動なしで追従する。
"""

from __future__ import annotations

from qdrant_client import QdrantClient


class AliasNotFoundError(LookupError):
    """指定されたエイリアスが Qdrant 上に存在しない。"""


class CollectionResolver:
    """エイリアス名から現在の物理コレクション名を返す解決器。"""

    def __init__(self, client: QdrantClient, alias_name: str) -> None:
        if not alias_name:
            raise ValueError("alias_name must not be empty")
        self._client = client
        self._alias_name = alias_name

    @property
    def alias_name(self) -> str:
        return self._alias_name

    def resolve(self) -> str:
        """エイリアスの現在のターゲット物理コレクション名を返す。

        切替の即時反映のため内部キャッシュは持たず、毎回 Qdrant に問い合わせる。

        Raises:
            AliasNotFoundError: エイリアスが未定義のとき。
        """
        response = self._client.get_aliases()
        for description in response.aliases:
            if description.alias_name == self._alias_name:
                return description.collection_name
        raise AliasNotFoundError(
            f"alias '{self._alias_name}' is not defined in Qdrant"
        )

    def exists(self) -> bool:
        """エイリアス定義の有無を真偽で返す。起動時プローブ用。"""
        try:
            self.resolve()
        except AliasNotFoundError:
            return False
        return True
