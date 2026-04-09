"""QueryParser: 自然言語クエリをsemantic_query + filters + boostsに分解する。"""

import json
from functools import lru_cache
from pathlib import Path

from shared.models.search import ParsedQuery, QueryBoosts, QueryFilters

# 日本語色名 → 英語正規化形
_COLOR_MAP: dict[str, str] = {
    "赤": "red",
    "青": "blue",
    "緑": "green",
    "黄": "yellow",
    "金": "gold",
    "銀": "silver",
    "白": "white",
    "黒": "black",
    "紫": "purple",
    "ピンク": "pink",
    "オレンジ": "orange",
    "茶": "brown",
    "灰": "gray",
    "水色": "teal",
}


@lru_cache(maxsize=1)
def _load_motif_map() -> list[tuple[str, str]]:
    """config/motif_jp_map.json から (JP, EN) ペアのリストを構築する。

    JSONは EN→[JP list] 形式。1つの日本語表現が複数の英語タグに
    マッチし得る（例: "海"→sea, ocean）。
    長い日本語表現を先にマッチさせるため、文字数降順でソートして返す。
    """
    config_path = Path(__file__).resolve().parents[2] / "config" / "motif_jp_map.json"
    with open(config_path, encoding="utf-8") as f:
        data: dict[str, list[str]] = json.load(f)

    pairs: list[tuple[str, str]] = []
    for en_tag, jp_list in data.items():
        if en_tag.startswith("_"):
            continue
        for jp_expr in jp_list:
            pairs.append((jp_expr, en_tag))

    # 長い表現を先にマッチさせる（例: "火山" を "火" より先に）
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs

# 明るさ関連の日本語表現 → brightness_min値
_BRIGHTNESS_BRIGHT: list[str] = ["明るい", "明るく", "光", "輝", "鮮やか"]
_BRIGHTNESS_DARK: list[str] = ["暗い", "暗く", "暗め", "ダーク", "闇"]


class QueryParser:
    """日本語自然言語クエリを構造化されたParsedQueryに分解する。"""

    def parse(self, query: str) -> ParsedQuery:
        """クエリを分解する。"""
        color_tags = self._extract_colors(query)
        motif_tags = self._extract_motifs(query)
        brightness_min = self._extract_brightness(query)
        semantic_query = self._build_semantic_query(query)

        return ParsedQuery(
            semantic_query=semantic_query,
            filters=QueryFilters(
                color_tags=color_tags,
                motif_tags=motif_tags,
            ),
            boosts=QueryBoosts(
                brightness_min=brightness_min,
            ),
        )

    def _extract_colors(self, query: str) -> list[str]:
        """クエリから色表現を抽出し、英語正規化形に変換する。"""
        found: list[str] = []
        seen: set[str] = set()
        for jp, en in _COLOR_MAP.items():
            if jp in query and en not in seen:
                found.append(en)
                seen.add(en)
        return found

    def _extract_motifs(self, query: str) -> list[str]:
        """クエリからモチーフ表現を抽出し、英語タグに変換する。"""
        pairs = _load_motif_map()
        found: list[str] = []
        seen: set[str] = set()
        for jp, en in pairs:
            if jp in query and en not in seen:
                found.append(en)
                seen.add(en)
        return found

    def _extract_brightness(self, query: str) -> float | None:
        """クエリから明るさ表現を検出し、brightness_min値を返す。"""
        for expr in _BRIGHTNESS_BRIGHT:
            if expr in query:
                return 0.6
        for expr in _BRIGHTNESS_DARK:
            if expr in query:
                return 0.0  # 暗い = brightness_min低い値でフィルタ（上限として使うか要検討）
        return None

    def _build_semantic_query(self, query: str) -> str:
        """クエリ全体をsemantic_queryとして返す。

        v1ではクエリ全体をそのまま使用する。SigLIP2が多言語対応のため、
        日本語クエリをそのままテキスト埋め込みに渡す。
        """
        return query
