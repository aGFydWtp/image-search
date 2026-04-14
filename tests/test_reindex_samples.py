"""サンプルクエリ定義の読み込み / 埋め込みテスト。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shared.qdrant.sample_queries import (
    SampleQueriesError,
    SampleQuery,
    embed_sample_queries,
    load_sample_queries,
)


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TestLoad:
    """load_sample_queries: JSON → list[SampleQuery]。"""

    def test_loads_well_formed_json(self, tmp_path: Path) -> None:
        file = _write(
            tmp_path / "samples.json",
            {
                "version": 1,
                "queries": [
                    {"label": "mood_calm", "text": "やさしい雰囲気の風景"},
                    {"label": "color_green_gold", "text": "緑と金が入っている作品"},
                ],
            },
        )

        queries = load_sample_queries(file)

        assert queries == [
            SampleQuery(label="mood_calm", text="やさしい雰囲気の風景"),
            SampleQuery(label="color_green_gold", text="緑と金が入っている作品"),
        ]

    def test_empty_queries_list_is_allowed(self, tmp_path: Path) -> None:
        file = _write(tmp_path / "samples.json", {"version": 1, "queries": []})

        queries = load_sample_queries(file)

        assert queries == []

    def test_missing_file_raises_sample_queries_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "no-such-file.json"

        with pytest.raises(SampleQueriesError) as exc:
            load_sample_queries(missing)

        assert str(missing) in str(exc.value)

    def test_invalid_json_raises_sample_queries_error(
        self, tmp_path: Path
    ) -> None:
        file = tmp_path / "broken.json"
        file.write_text("{not json", encoding="utf-8")

        with pytest.raises(SampleQueriesError):
            load_sample_queries(file)

    def test_missing_queries_key_raises(self, tmp_path: Path) -> None:
        file = _write(tmp_path / "samples.json", {"version": 1})

        with pytest.raises(SampleQueriesError):
            load_sample_queries(file)

    def test_queries_not_list_raises(self, tmp_path: Path) -> None:
        file = _write(
            tmp_path / "samples.json", {"version": 1, "queries": "not-a-list"}
        )

        with pytest.raises(SampleQueriesError):
            load_sample_queries(file)

    def test_query_missing_label_raises(self, tmp_path: Path) -> None:
        file = _write(
            tmp_path / "samples.json",
            {"version": 1, "queries": [{"text": "hi"}]},
        )

        with pytest.raises(SampleQueriesError):
            load_sample_queries(file)

    def test_query_missing_text_raises(self, tmp_path: Path) -> None:
        file = _write(
            tmp_path / "samples.json",
            {"version": 1, "queries": [{"label": "x"}]},
        )

        with pytest.raises(SampleQueriesError):
            load_sample_queries(file)

    def test_unsupported_schema_version_raises(self, tmp_path: Path) -> None:
        file = _write(tmp_path / "samples.json", {"version": 2, "queries": []})

        with pytest.raises(SampleQueriesError) as exc:
            load_sample_queries(file)
        assert "version" in str(exc.value).lower()

    def test_version_field_is_optional(self, tmp_path: Path) -> None:
        """version 省略は現行仕様として受け入れる (互換のため)。"""
        file = _write(
            tmp_path / "samples.json",
            {"queries": [{"label": "a", "text": "hi"}]},
        )

        queries = load_sample_queries(file)
        assert queries == [SampleQuery(label="a", text="hi")]


class TestEmbed:
    """embed_sample_queries: SampleQuery → ベクトル。"""

    def test_returns_vector_per_query(self) -> None:
        queries = [
            SampleQuery(label="a", text="text-a"),
            SampleQuery(label="b", text="text-b"),
        ]
        embedder = MagicMock(
            side_effect=[[0.1, 0.2], [0.3, 0.4]]
        )

        vectors = embed_sample_queries(queries, embed_text=embedder)

        assert vectors == [[0.1, 0.2], [0.3, 0.4]]
        assert embedder.call_count == 2
        embedder.assert_any_call("text-a")
        embedder.assert_any_call("text-b")

    def test_empty_query_list_returns_empty_vectors(self) -> None:
        embedder = MagicMock()

        vectors = embed_sample_queries([], embed_text=embedder)

        assert vectors == []
        embedder.assert_not_called()

    def test_propagates_embedder_errors(self) -> None:
        queries = [SampleQuery(label="a", text="boom")]
        embedder = MagicMock(side_effect=RuntimeError("embedding service down"))

        with pytest.raises(RuntimeError):
            embed_sample_queries(queries, embed_text=embedder)


class TestShippedConfig:
    """リポジトリ同梱の config/reindex_samples.json が有効であること。"""

    def test_default_config_file_loads(self) -> None:
        root = Path(__file__).resolve().parents[1]
        default_file = root / "config" / "reindex_samples.json"
        assert default_file.exists(), "default sample query file must be shipped"
        queries = load_sample_queries(default_file)
        assert len(queries) >= 1
        for q in queries:
            assert q.label and q.text
