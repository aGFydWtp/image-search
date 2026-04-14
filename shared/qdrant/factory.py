"""Settings から Qdrant クライアント・Resolver・Repository を一括生成するファクトリ。

検索サービス / 差分インジェスション / 再インデックス CLI の各エントリポイントで
同じ生成ロジックを繰り返さないためのユーティリティ。API キーの取り回しも
ここで完結させ、サービス層で ``SecretStr.get_secret_value()`` を書かずに済ませる。
"""

from __future__ import annotations

from qdrant_client import QdrantClient

from shared.config import Settings
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.resolver import CollectionResolver


def build_repository(
    settings: Settings,
) -> tuple[QdrantClient, CollectionResolver, QdrantRepository]:
    """Settings から Qdrant 依存一式を生成する。

    Returns:
        ``(client, resolver, repository)`` のタプル。呼び出し側は必要な
        要素だけを受け取る。
    """
    api_key = (
        settings.qdrant_api_key.get_secret_value()
        if settings.qdrant_api_key is not None
        else None
    )
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=api_key,
    )
    resolver = CollectionResolver(client=client, alias_name=settings.qdrant_alias)
    repository = QdrantRepository(
        client=client, resolver=resolver, vector_dim=settings.vector_dim
    )
    return client, resolver, repository
