"""ReindexOrchestrator.catchup: 旧 → 新コレクションへの差分再投入。

再インデックス中に旧コレクションへ差分 ingestion された artwork を
新コレクションへ反映するためのユーティリティ。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.models import PointStruct, Record

from shared.qdrant.alias_admin import AliasAdmin
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.validation import ValidationGate
from services.ingestion.reindex import CatchupResult, ReindexOrchestrator


def _record(point_id: int, artwork_id: str) -> Record:
    return Record(
        id=point_id,
        payload={"artwork_id": artwork_id, "title": f"title-{artwork_id}"},
        vector={
            "image_semantic": [0.1, 0.2, 0.3, 0.4],
            "text_semantic": [0.5, 0.6, 0.7, 0.8],
        },
    )


def _scroll_pages(pages: list[list[Record]]):
    """連続する scroll 呼び出しで pages を順に返し、最後で None offset を返す。"""
    responses = []
    for i, batch in enumerate(pages):
        next_offset = (i + 1) if i + 1 < len(pages) else None
        responses.append((batch, next_offset))
    return responses


def _make_orchestrator(
    scroll_pages_list: list[list[Record]],
) -> tuple[ReindexOrchestrator, MagicMock, MagicMock]:
    client = MagicMock()
    client.scroll.side_effect = _scroll_pages(scroll_pages_list)
    repo = MagicMock(spec=QdrantRepository)
    admin = MagicMock(spec=AliasAdmin)
    gate = MagicMock(spec=ValidationGate)
    orch = ReindexOrchestrator(
        client=client,
        repository=repo,
        alias_admin=admin,
        validation_gate=gate,
        alias_name="artworks_current",
    )
    return orch, client, repo


class TestCatchup:
    def test_copies_each_point_via_qdrant_upsert(self) -> None:
        orch, client, _repo = _make_orchestrator(
            [[_record(1, "art-001"), _record(2, "art-002")]]
        )

        result = orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
            batch_size=100,
        )

        # Upsert is issued against the target collection
        assert client.upsert.call_count >= 1
        upsert_calls = client.upsert.call_args_list
        all_points: list[PointStruct] = []
        for call in upsert_calls:
            assert call.kwargs["collection_name"] == "artworks_v2"
            all_points.extend(call.kwargs["points"])
        assert len(all_points) == 2
        assert {p.id for p in all_points} == {1, 2}

    def test_scrolls_source_collection_with_vectors_and_payload(self) -> None:
        orch, client, _ = _make_orchestrator(
            [[_record(1, "art-001")]]
        )

        orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
            batch_size=50,
        )

        first_call = client.scroll.call_args_list[0]
        assert first_call.kwargs["collection_name"] == "artworks_v1"
        assert first_call.kwargs["with_payload"] is True
        assert first_call.kwargs["with_vectors"] is True
        assert first_call.kwargs["limit"] == 50

    def test_continues_scrolling_until_offset_none(self) -> None:
        pages = [
            [_record(1, "a"), _record(2, "b")],
            [_record(3, "c")],
        ]
        orch, client, _ = _make_orchestrator(pages)

        result = orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
        )

        assert client.scroll.call_count == 2
        assert result.copied_count == 3

    def test_returns_catchup_result(self) -> None:
        orch, _, _ = _make_orchestrator([[_record(1, "a")]])

        result = orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
        )

        assert isinstance(result, CatchupResult)
        assert result.source_collection == "artworks_v1"
        assert result.target_collection == "artworks_v2"
        assert result.copied_count == 1

    def test_empty_source_returns_zero_count(self) -> None:
        orch, _, _ = _make_orchestrator([[]])

        result = orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
        )

        assert result.copied_count == 0

    def test_rejects_same_source_and_target(self) -> None:
        orch, _, _ = _make_orchestrator([])

        with pytest.raises(ValueError):
            orch.catchup(
                source_collection="artworks_v1",
                target_collection="artworks_v1",
            )

    def test_emits_progress_event_per_batch(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pages = [
            [_record(1, "a"), _record(2, "b")],
            [_record(3, "c"), _record(4, "d")],
            [_record(5, "e")],
        ]
        orch, _, _ = _make_orchestrator(pages)

        caplog.set_level("INFO")
        orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
            batch_size=2,
        )

        progress = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.catchup.progress"
        ]
        # 3 ページ分それぞれで progress が出る
        assert len(progress) == 3
        assert [getattr(r, "copied", None) for r in progress] == [2, 4, 5]

    def test_logs_started_and_completed_events(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        orch, _, _ = _make_orchestrator([[_record(1, "a"), _record(2, "b")]])

        caplog.set_level("INFO")
        orch.catchup(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
        )

        started = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.catchup.started"
        ]
        completed = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.catchup.completed"
        ]
        assert len(started) == 1
        assert len(completed) == 1
        assert getattr(completed[0], "copied_count", None) == 2

    def test_batch_size_validated(self) -> None:
        orch, _, _ = _make_orchestrator([])
        with pytest.raises(ValueError):
            orch.catchup(
                source_collection="artworks_v1",
                target_collection="artworks_v2",
                batch_size=0,
            )
