"""ValidationGate 用サンプルクエリの読み込みと埋め込み変換。

``config/reindex_samples.json`` (あるいは ``REINDEX_SAMPLE_QUERIES_PATH``
で指定されたファイル) に記述された固定クエリを読み込み、必要に応じて
embedding クライアント経由でベクトル化する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 1


class SampleQueriesError(ValueError):
    """サンプルクエリ設定ファイルの読み込み / 検証に失敗した。"""


@dataclass(frozen=True)
class SampleQuery:
    """検証用サンプルクエリの 1 件。"""

    label: str
    text: str


def load_sample_queries(path: str | Path) -> list[SampleQuery]:
    """JSON ファイルを読み、SampleQuery のリストを返す。

    ``path`` は運用者が設定する信頼済みパス (``Settings.reindex_sample_queries_path``
    経由) を想定する。任意のユーザー入力を直接渡さないこと。

    期待するスキーマ::

        {
          "version": 1,
          "queries": [
            {"label": "mood_calm", "text": "やさしい雰囲気の風景"}
          ]
        }

    Raises:
        SampleQueriesError: ファイル不在 / 不正 JSON / 必須キー欠落 / 未知 version。
    """
    file = Path(path)
    if not file.exists():
        raise SampleQueriesError(f"sample queries file not found: {file}")

    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SampleQueriesError(f"invalid JSON in {file}: {exc}") from exc

    if not isinstance(raw, dict) or "queries" not in raw:
        raise SampleQueriesError(
            f"{file}: missing required 'queries' key"
        )
    version = raw.get("version")
    if version is not None and version != SCHEMA_VERSION:
        raise SampleQueriesError(
            f"{file}: unsupported schema version {version} "
            f"(expected {SCHEMA_VERSION})"
        )
    queries_raw = raw["queries"]
    if not isinstance(queries_raw, list):
        raise SampleQueriesError(f"{file}: 'queries' must be a list")

    queries: list[SampleQuery] = []
    for index, item in enumerate(queries_raw):
        if not isinstance(item, dict):
            raise SampleQueriesError(
                f"{file}: queries[{index}] must be an object"
            )
        label = item.get("label")
        text = item.get("text")
        if not isinstance(label, str) or not label:
            raise SampleQueriesError(
                f"{file}: queries[{index}] is missing 'label'"
            )
        if not isinstance(text, str) or not text:
            raise SampleQueriesError(
                f"{file}: queries[{index}] is missing 'text'"
            )
        queries.append(SampleQuery(label=label, text=text))
    return queries


def embed_sample_queries(
    queries: list[SampleQuery],
    embed_text: Callable[[str], list[float]],
) -> list[list[float]]:
    """各 SampleQuery の text をベクトル化して返す。

    埋め込みサービス呼び出しの例外はそのまま伝搬させ、呼び出し側
    (ReindexOrchestrator / CLI) で運用イベントとして記録させる。
    """
    return [embed_text(q.text) for q in queries]
