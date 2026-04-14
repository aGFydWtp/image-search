"""CollectionResolver のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.models import AliasDescription, CollectionsAliasesResponse

from shared.qdrant.resolver import AliasNotFoundError, CollectionResolver


def _aliases_response(*aliases: tuple[str, str]) -> CollectionsAliasesResponse:
    return CollectionsAliasesResponse(
        aliases=[
            AliasDescription(alias_name=name, collection_name=collection)
            for name, collection in aliases
        ]
    )


class TestResolve:
    """`resolve()` は現在のエイリアス対象物理コレクション名を返す。"""

    def test_returns_target_collection_for_alias(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v2"),
            ("other_alias", "other_collection"),
        )
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        assert resolver.resolve() == "artworks_v2"

    def test_raises_alias_not_found_when_alias_missing(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response(
            ("other_alias", "other_collection")
        )
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        with pytest.raises(AliasNotFoundError) as exc:
            resolver.resolve()
        assert "artworks_current" in str(exc.value)

    def test_raises_alias_not_found_when_no_aliases_exist(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response()
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        with pytest.raises(AliasNotFoundError):
            resolver.resolve()

    def test_calls_qdrant_every_time_without_caching(self) -> None:
        """切替の即時反映のため、内部キャッシュを持たない。"""
        client = MagicMock()
        client.get_aliases.side_effect = [
            _aliases_response(("artworks_current", "artworks_v1")),
            _aliases_response(("artworks_current", "artworks_v2")),
        ]
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        assert resolver.resolve() == "artworks_v1"
        assert resolver.resolve() == "artworks_v2"
        assert client.get_aliases.call_count == 2


class TestExists:
    """`exists()` はエイリアス定義の有無を真偽で返す（起動時プローブ用）。"""

    def test_returns_true_when_alias_defined(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        assert resolver.exists() is True

    def test_returns_false_when_alias_missing(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response()
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        assert resolver.exists() is False

    def test_propagates_unexpected_errors(self) -> None:
        """AliasNotFoundError 以外 (ネットワーク・認証等) は呼び出し側に伝搬する。"""
        client = MagicMock()
        client.get_aliases.side_effect = ConnectionError("qdrant unreachable")
        resolver = CollectionResolver(client=client, alias_name="artworks_current")
        with pytest.raises(ConnectionError):
            resolver.exists()


class TestConstructor:
    def test_rejects_empty_alias_name(self) -> None:
        with pytest.raises(ValueError):
            CollectionResolver(client=MagicMock(), alias_name="")
