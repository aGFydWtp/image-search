"""ColorExtractor: 画像から支配色・brightness・saturation・warmthを抽出する。"""

import colorsys
from io import BytesIO

from PIL import Image

from shared.models.color import ColorInfo

_PALETTE_SIZE = 5
_QUANTIZE_COLORS = 16

# HSV色相範囲ベースの色名マッピング (hue: 0-360)
_COLOR_NAMES: list[tuple[str, float, float]] = [
    # (name, hue_min, hue_max)
    ("red", 0, 15),
    ("orange", 15, 40),
    ("gold", 40, 55),
    ("yellow", 55, 70),
    ("green", 70, 165),
    ("teal", 165, 185),
    ("blue", 185, 260),
    ("purple", 260, 290),
    ("pink", 290, 340),
    ("red", 340, 360),
]


def _rgb_to_color_name(r: int, g: int, b: int) -> str:
    """RGB値から正規化済み英語色名を返す。"""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

    # 無彩色判定
    if v < 0.15:
        return "black"
    if v > 0.85 and s < 0.15:
        return "white"
    if s < 0.15:
        return "gray"

    hue_deg = h * 360
    for name, hue_min, hue_max in _COLOR_NAMES:
        if hue_min <= hue_deg < hue_max:
            return name
    return "gray"


class ColorExtractor:
    """画像から支配色、パレット、brightness/saturation/warmthスコアを抽出する。"""

    def extract(self, image_bytes: bytes) -> ColorInfo:
        """画像バイナリから色情報を抽出する。"""
        img = Image.open(BytesIO(image_bytes)).convert("RGB")

        # リサイズして処理高速化
        img_small = img.copy()
        img_small.thumbnail((150, 150), Image.LANCZOS)

        # 量子化で支配色を抽出
        palette_colors = self._extract_palette(img_small)
        palette_hex = [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in palette_colors]

        # 色名タグ（重複排除）
        color_tags: list[str] = []
        seen: set[str] = set()
        for r, g, b in palette_colors:
            name = _rgb_to_color_name(r, g, b)
            if name not in seen:
                color_tags.append(name)
                seen.add(name)

        # 全ピクセルからスコア算出
        raw = img_small.tobytes()
        pixels = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
        brightness = self._calc_brightness(pixels)
        saturation = self._calc_saturation(pixels)
        warmth = self._calc_warmth(pixels)

        return ColorInfo(
            color_tags=color_tags,
            palette_hex=palette_hex[:_PALETTE_SIZE],
            brightness_score=round(brightness, 4),
            saturation_score=round(saturation, 4),
            warmth_score=round(warmth, 4),
        )

    def _extract_palette(self, img: Image.Image) -> list[tuple[int, int, int]]:
        """画像を量子化して支配色パレットを抽出する。"""
        quantized = img.quantize(colors=_QUANTIZE_COLORS, method=Image.Quantize.MEDIANCUT)
        palette_data = quantized.getpalette()
        if palette_data is None:
            return [(128, 128, 128)]

        # パレットからRGBタプルを取得
        colors = []
        for i in range(_QUANTIZE_COLORS):
            idx = i * 3
            if idx + 2 < len(palette_data):
                colors.append((palette_data[idx], palette_data[idx + 1], palette_data[idx + 2]))

        # ピクセル数でソート（最頻色順）
        histogram = quantized.histogram()
        color_counts = [(histogram[i], colors[i]) for i in range(min(len(colors), len(histogram)))]
        color_counts.sort(reverse=True)

        return [c for _, c in color_counts[:_PALETTE_SIZE]]

    def _calc_brightness(self, pixels: list[tuple[int, int, int]]) -> float:
        """全ピクセルの平均輝度 (0.0-1.0)。"""
        if not pixels:
            return 0.0
        total = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels)
        return total / (len(pixels) * 255)

    def _calc_saturation(self, pixels: list[tuple[int, int, int]]) -> float:
        """全ピクセルの平均彩度 (0.0-1.0)。"""
        if not pixels:
            return 0.0
        total = sum(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1] for r, g, b in pixels)
        return total / len(pixels)

    def _calc_warmth(self, pixels: list[tuple[int, int, int]]) -> float:
        """全ピクセルの平均暖色度 (0.0-1.0)。R成分比率ベース。"""
        if not pixels:
            return 0.5
        total = 0.0
        for r, g, b in pixels:
            s = r + g + b
            if s == 0:
                total += 0.5
            else:
                # R成分が高いほど暖色、B成分が高いほど寒色
                total += (r - b) / (2 * s) + 0.5
        return max(0.0, min(1.0, total / len(pixels)))
