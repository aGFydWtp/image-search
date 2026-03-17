"""E2Eテスト用のテスト画像を生成するスクリプト。

各画像は特定の色・モチーフ特徴を持ち、検索精度評価に使用する。
実行: python tests/fixtures/generate_test_images.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

FIXTURE_DIR = Path(__file__).parent


def _save(img: Image.Image, name: str) -> None:
    path = FIXTURE_DIR / name
    img.save(path, format="JPEG", quality=90)
    print(f"Generated: {path}")


def generate() -> None:
    # 1. 青空: 上半分青、下半分緑 (sky + green)
    img = Image.new("RGB", (384, 384))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 384, 192], fill=(100, 150, 255))
    draw.rectangle([0, 192, 384, 384], fill=(50, 180, 50))
    _save(img, "blue_sky_green_field.jpg")

    # 2. 夕焼け: オレンジ〜赤のグラデーション (warm, orange, red)
    img = Image.new("RGB", (384, 384))
    for y in range(384):
        r = 255
        g = int(100 + (155 * (384 - y) / 384))
        b = int(50 * (384 - y) / 384)
        draw = ImageDraw.Draw(img)
        draw.line([(0, y), (384, y)], fill=(r, g, b))
    _save(img, "sunset_warm.jpg")

    # 3. 暗い森: 暗緑 (dark, tree, green)
    img = Image.new("RGB", (384, 384), color=(20, 50, 20))
    draw = ImageDraw.Draw(img)
    for x in range(50, 350, 60):
        draw.polygon([(x, 100), (x - 30, 300), (x + 30, 300)], fill=(30, 80, 30))
    _save(img, "dark_forest.jpg")

    # 4. 海: 青のグラデーション (sea, blue, calm)
    img = Image.new("RGB", (384, 384))
    for y in range(384):
        b = int(150 + (105 * y / 384))
        g = int(100 + (50 * y / 384))
        draw = ImageDraw.Draw(img)
        draw.line([(0, y), (384, y)], fill=(30, g, b))
    _save(img, "calm_ocean.jpg")

    # 5. 赤い花: 白背景に赤い丸 (flower, red, bright)
    img = Image.new("RGB", (384, 384), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    for cx, cy in [(192, 192), (120, 150), (260, 170), (150, 270), (240, 260)]:
        draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(220, 40, 40))
    draw.ellipse([172, 172, 212, 212], fill=(255, 200, 50))
    _save(img, "red_flowers_bright.jpg")

    print("All test images generated.")


if __name__ == "__main__":
    generate()
