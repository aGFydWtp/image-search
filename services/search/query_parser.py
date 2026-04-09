"""QueryParser: 自然言語クエリをsemantic_query + filters + boostsに分解する。"""


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

# 日本語モチーフ表現 → 英語motif_tags
_MOTIF_MAP: dict[str, str] = {
    # 既存24語
    "空": "sky",
    "海": "sea",
    "花": "flower",
    "山": "mountain",
    "木": "tree",
    "森": "forest",
    "川": "river",
    "湖": "lake",
    "太陽": "sun",
    "月": "moon",
    "星": "star",
    "鳥": "bird",
    "雪": "snow",
    "雨": "rain",
    "街": "city",
    "家": "house",
    "人": "figure",
    "橋": "bridge",
    "船": "boat",
    "庭": "garden",
    "岩": "rock",
    "道": "road",
    "窓": "window",
    "火": "fire",
    # 拡張: 動物
    "猫": "cat",
    "犬": "dog",
    "馬": "horse",
    "蝶": "butterfly",
    "鹿": "deer",
    "魚": "fish",
    "象": "elephant",
    "蛇": "snake",
    "鷹": "eagle",
    # 拡張: 建築・構造物
    "城": "castle",
    "塔": "tower",
    "寺": "temple",
    "教会": "church building",
    "灯台": "lighthouse",
    "宮殿": "palace",
    "廃墟": "ruins",
    # 拡張: 自然・地形
    "虹": "rainbow",
    "滝": "waterfall",
    "泉": "fountain",
    "丘": "hill",
    "砂漠": "desert",
    "島": "island",
    "洞窟": "cave",
    "火山": "volcano",
    "雲": "cloud",
    "霧": "fog",
    "嵐": "storm",
    "稲妻": "lightning",
    # 拡張: 植物
    "薔薇": "rose",
    "蓮": "lotus",
    "百合": "lily",
    # 拡張: 物品・シンボル
    "剣": "sword",
    "冠": "crown",
    "鏡": "mirror",
    "鐘": "bell",
}

# 明るさ関連の日本語表現 → brightness_min値
_BRIGHTNESS_BRIGHT: list[str] = ["明るい", "明るく", "光", "輝", "鮮やか"]
_BRIGHTNESS_DARK: list[str] = ["暗い", "暗く", "暗め", "ダーク", "闇"]

# ムード/雰囲気の日本語表現（semantic_queryに残す）
_MOOD_EXPRESSIONS: list[str] = [
    "やさしい", "優しい", "穏やか", "静か", "落ち着", "温かい", "あたたかい",
    "冷たい", "涼しい", "寂しい", "悲しい", "楽しい", "力強い",
    "神秘", "幻想", "ドラマチック", "ノスタルジック", "エレガント",
    "透明感", "爽やか", "重厚", "繊細", "大胆",
]


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
        found: list[str] = []
        seen: set[str] = set()
        for jp, en in _MOTIF_MAP.items():
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
