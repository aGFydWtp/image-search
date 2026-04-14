"""QueryParser: 自然言語クエリをsemantic_query + filters + boostsに分解する。"""

import json
from functools import lru_cache
from pathlib import Path

from shared.models.search import ParsedQuery, QueryBoosts, QueryFilters

# 日本語色名 → 英語正規化形
# 漢字1文字キーは「金属」「黄金」「銀河」「茶碗」等の複合語誤爆を避けるため
# 「〜色」の明示形を使用する。
_COLOR_MAP: dict[str, str] = {
    "赤": "red",
    "青": "blue",
    "緑": "green",
    "黄色": "yellow",
    "金色": "gold",
    "銀色": "silver",
    "白": "white",
    "黒": "black",
    "紫": "purple",
    "ピンク": "pink",
    "オレンジ": "orange",
    "茶色": "brown",
    "灰色": "gray",
    "水色": "teal",
}

# 質感・素材の日本語表現 → SigLIP2 への英語ヒント。
# semantic_query に英訳的に追記して意味埋め込みに質感情報を載せる。
_TEXTURE_EXPANSIONS: dict[str, str] = {
    "つや消し": "matte surface",
    "ツヤ消し": "matte surface",
    "金属": "metallic surface",
    "光沢": "glossy shiny surface",
    "つや": "glossy",
    "ツヤ": "glossy",
    "マット": "matte surface",
    "つるつる": "smooth glossy",
    "ざらざら": "rough textured",
    "なめらか": "smooth",
    "粗い": "rough textured",
    # 「きらきら」系の擬態語・動詞は brightness ではなく
    # sparkle/glitter の質感として SigLIP2 にヒントを渡す。
    # 抽象語 (sparkling/glittering) だけだと光沢生地と混同されるため、
    # SigLIP2 が画像-キャプション学習で接していそうな具体名詞
    # (stars, jewels, gems, fireworks 等) を併記して照準を絞る。
    "光り輝く": "shining radiant glowing light",
    "きらきら": (
        "sparkling glittering stars jewels gems "
        "twinkling lights points of light on dark background"
    ),
    "キラキラ": (
        "sparkling glittering stars jewels gems "
        "twinkling lights points of light on dark background"
    ),
    "煌びやか": "sparkling shimmering ornate jewels gold ornament",
    "煌めき": "sparkling shimmering stars jewels twinkling",
    "煌めく": "sparkling shimmering stars jewels twinkling",
    "輝く": "shining radiant glowing star sun light",
    "眩しい": "bright dazzling sunlight glare",
    "まぶしい": "bright dazzling sunlight glare",
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
# 「画像全体が明るい」を意味する語のみ。点状の光・煌めき表現
# (きらきら/輝く/煌めく/眩しい等) は質感寄りなので _TEXTURE_EXPANSIONS 側で扱う。
_BRIGHTNESS_BRIGHT: list[str] = ["明るい", "明るく", "鮮やか"]
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

        SigLIP2が多言語対応のため日本語クエリをそのまま埋め込みに渡すが、
        質感・素材語が含まれていれば英語ヒントを末尾に追加して意味的な
        手がかりを補強する。
        """
        seen: set[str] = set()
        expansions: list[str] = []
        # 長いキーから順にマッチさせ、ヒット部分を作業文字列から除去する。
        # これにより「つや消し」が「つや」に再マッチして glossy も付くのを防ぐ。
        remaining = query
        for jp, en in sorted(_TEXTURE_EXPANSIONS.items(), key=lambda x: -len(x[0])):
            if jp in remaining and en not in seen:
                expansions.append(en)
                seen.add(en)
                remaining = remaining.replace(jp, "")
        if not expansions:
            return query
        return f"{query} ({', '.join(expansions)})"
