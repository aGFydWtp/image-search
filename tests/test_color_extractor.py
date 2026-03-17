"""ColorExtractor のユニットテスト。"""

from io import BytesIO

import pytest
from PIL import Image

from shared.models.color import ColorInfo


def _make_solid_image(r: int, g: int, b: int, size: tuple[int, int] = (200, 200)) -> bytes:
    """単色テスト画像を生成する。"""
    img = Image.new("RGB", size, color=(r, g, b))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestColorInfoModel:
    """ColorInfo データモデルのテスト。"""

    def test_valid_color_info(self) -> None:
        info = ColorInfo(
            color_tags=["blue", "white"],
            palette_hex=["#0000FF", "#FFFFFF"],
            brightness_score=0.5,
            saturation_score=0.8,
            warmth_score=0.3,
        )
        assert info.color_tags == ["blue", "white"]
        assert info.brightness_score == 0.5

    def test_score_range_validation(self) -> None:
        with pytest.raises(Exception):
            ColorInfo(
                color_tags=[],
                palette_hex=[],
                brightness_score=1.5,
                saturation_score=0.5,
                warmth_score=0.5,
            )


class TestColorExtractorExtract:
    """ColorExtractor.extract() のテスト。"""

    def test_returns_color_info(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(255, 0, 0))

        assert isinstance(result, ColorInfo)

    def test_palette_hex_format(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(0, 128, 255))

        assert len(result.palette_hex) >= 1
        for hex_color in result.palette_hex:
            assert hex_color.startswith("#")
            assert len(hex_color) == 7

    def test_palette_hex_count(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        # Gradient image for more colors
        img = Image.new("RGB", (200, 200))
        for x in range(200):
            for y in range(200):
                img.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
        buf = BytesIO()
        img.save(buf, format="PNG")

        result = ext.extract(buf.getvalue())
        assert 3 <= len(result.palette_hex) <= 5


class TestBrightnessScore:
    """brightness_score のテスト。"""

    def test_white_is_bright(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(255, 255, 255))
        assert result.brightness_score > 0.9

    def test_black_is_dark(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(0, 0, 0))
        assert result.brightness_score < 0.1

    def test_score_in_range(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(128, 128, 128))
        assert 0.0 <= result.brightness_score <= 1.0


class TestSaturationScore:
    """saturation_score のテスト。"""

    def test_pure_red_is_saturated(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(255, 0, 0))
        assert result.saturation_score > 0.8

    def test_gray_is_unsaturated(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(128, 128, 128))
        assert result.saturation_score < 0.1

    def test_score_in_range(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(100, 200, 50))
        assert 0.0 <= result.saturation_score <= 1.0


class TestWarmthScore:
    """warmth_score のテスト。"""

    def test_red_is_warm(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(255, 100, 0))
        assert result.warmth_score > 0.6

    def test_blue_is_cool(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(0, 0, 255))
        assert result.warmth_score < 0.4

    def test_score_in_range(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(128, 128, 128))
        assert 0.0 <= result.warmth_score <= 1.0


class TestColorTags:
    """color_tags のテスト。"""

    def test_red_image_tagged_red(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(220, 30, 30))
        assert "red" in result.color_tags

    def test_blue_image_tagged_blue(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(30, 30, 220))
        assert "blue" in result.color_tags

    def test_green_image_tagged_green(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(30, 200, 30))
        assert "green" in result.color_tags

    def test_white_image_tagged_white(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(250, 250, 250))
        assert "white" in result.color_tags

    def test_black_image_tagged_black(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(5, 5, 5))
        assert "black" in result.color_tags

    def test_gold_image_tagged_gold(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor

        ext = ColorExtractor()
        result = ext.extract(_make_solid_image(212, 175, 55))
        assert "gold" in result.color_tags
