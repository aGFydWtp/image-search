"""AliasAdmin のテスト。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from qdrant_client.models import (
    AliasDescription,
    CollectionsAliasesResponse,
    CreateAliasOperation,
    DeleteAliasOperation,
)

from shared.qdrant.alias_admin import (
    AliasAdmin,
    CollectionNotFoundError,
    PhysicalCollectionInUseError,
    SwapResult,
)


def _aliases_response(*aliases: tuple[str, str]) -> CollectionsAliasesResponse:
    return CollectionsAliasesResponse(
        aliases=[
            AliasDescription(alias_name=name, collection_name=collection)
            for name, collection in aliases
        ]
    )


class TestCurrentTarget:
    def test_returns_target_when_alias_defined(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        admin = AliasAdmin(client=client)
        assert admin.current_target("artworks_current") == "artworks_v1"

    def test_returns_none_when_alias_not_defined(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response()
        admin = AliasAdmin(client=client)
        assert admin.current_target("artworks_current") is None


class TestSwap:
    def test_issues_single_atomic_update_with_delete_and_create(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        admin = AliasAdmin(client=client)

        admin.swap("artworks_current", "artworks_v2")

        client.update_collection_aliases.assert_called_once()
        ops = client.update_collection_aliases.call_args.kwargs.get(
            "change_aliases_operations"
        ) or client.update_collection_aliases.call_args.args[0]
        assert len(ops) == 2
        assert isinstance(ops[0], DeleteAliasOperation)
        assert ops[0].delete_alias.alias_name == "artworks_current"
        assert isinstance(ops[1], CreateAliasOperation)
        assert ops[1].create_alias.alias_name == "artworks_current"
        assert ops[1].create_alias.collection_name == "artworks_v2"

    def test_returns_swap_result_with_previous_and_new_targets(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        admin = AliasAdmin(client=client)

        result = admin.swap("artworks_current", "artworks_v2")

        assert isinstance(result, SwapResult)
        assert result.alias == "artworks_current"
        assert result.previous_target == "artworks_v1"
        assert result.new_target == "artworks_v2"
        assert isinstance(result.swapped_at, datetime)

    def test_previous_target_is_none_when_alias_was_undefined(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response()
        admin = AliasAdmin(client=client)

        result = admin.swap("artworks_current", "artworks_v2")

        assert result.previous_target is None

    def test_raises_when_new_target_collection_does_not_exist(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = False
        admin = AliasAdmin(client=client)

        with pytest.raises(CollectionNotFoundError) as exc:
            admin.swap("artworks_current", "artworks_v99")
        assert "artworks_v99" in str(exc.value)
        client.update_collection_aliases.assert_not_called()

    def test_logs_success_event(self, caplog: pytest.LogCaptureFixture) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        admin = AliasAdmin(client=client)

        caplog.set_level("INFO")
        admin.swap("artworks_current", "artworks_v2")

        swap_records = [
            r for r in caplog.records if getattr(r, "event", None) == "reindex.alias.swap"
        ]
        assert len(swap_records) == 1
        assert getattr(swap_records[0], "previous_target", None) == "artworks_v1"
        assert getattr(swap_records[0], "new_target", None) == "artworks_v2"

    def test_logs_failure_event_and_reraises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        client.update_collection_aliases.side_effect = RuntimeError("qdrant 500")
        admin = AliasAdmin(client=client)

        caplog.set_level("ERROR")
        with pytest.raises(RuntimeError):
            admin.swap("artworks_current", "artworks_v2")

        failure_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.alias.swap.failed"
        ]
        assert len(failure_records) == 1


class TestRollback:
    def test_rollback_delegates_to_swap(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v2")
        )
        admin = AliasAdmin(client=client)

        result = admin.rollback("artworks_current", previous_target="artworks_v1")

        assert result.new_target == "artworks_v1"
        assert result.previous_target == "artworks_v2"

    def test_rollback_logs_rollback_event(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v2")
        )
        admin = AliasAdmin(client=client)

        caplog.set_level("INFO")
        admin.rollback("artworks_current", previous_target="artworks_v1")

        rollback_records = [
            r for r in caplog.records if getattr(r, "event", None) == "reindex.rollback"
        ]
        assert len(rollback_records) == 1


class TestDropPhysicalCollection:
    def test_refuses_to_drop_current_alias_target(self) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v1")
        )
        admin = AliasAdmin(client=client)

        with pytest.raises(PhysicalCollectionInUseError):
            admin.drop_physical_collection("artworks_v1", alias="artworks_current")
        client.delete_collection.assert_not_called()

    def test_drops_non_current_collection(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = MagicMock()
        client.get_aliases.return_value = _aliases_response(
            ("artworks_current", "artworks_v2")
        )
        admin = AliasAdmin(client=client)

        caplog.set_level("INFO")
        admin.drop_physical_collection("artworks_v1", alias="artworks_current")

        client.delete_collection.assert_called_once_with(collection_name="artworks_v1")
        dropped_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.collection.dropped"
        ]
        assert len(dropped_records) == 1
