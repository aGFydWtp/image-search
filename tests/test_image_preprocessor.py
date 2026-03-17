"""ImagePreprocessor のユニットテスト。"""

from io import BytesIO

import pytest
from PIL import Image

from shared.models.preprocessing import PreprocessedImage


def _make_test_image(width: int = 800, height: int = 600, fmt: str = "PNG") -> bytes:
    """テスト用画像バイナリを生成する。"""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_rgba_image(width: int = 400, height: int = 300) -> bytes:
    """RGBA（アルファチャンネル付き）テスト画像を生成する。"""
    img = Image.new("RGBA", (width, height), color=(100, 150, 200, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_grayscale_image(width: int = 400, height: int = 300) -> bytes:
    """グレースケールテスト画像を生成する。"""
    img = Image.new("L", (width, height), color=128)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestPreprocessedImageModel:
    """PreprocessedImage データモデルのテスト。"""

    def test_valid_result(self) -> None:
        result = PreprocessedImage(
            normalized=b"img",
            thumbnail=b"thumb",
            width=800,
            height=600,
            aspect_ratio=800 / 600,
        )
        assert result.width == 800
        assert result.aspect_ratio == pytest.approx(1.333, rel=1e-2)


class TestImagePreprocessorProcess:
    """ImagePreprocessor.process() のテスト。"""

    def test_returns_preprocessed_image(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(800, 600))

        assert isinstance(result, PreprocessedImage)
        assert result.width > 0
        assert result.height > 0

    def test_extracts_dimensions(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(1920, 1080))

        assert result.width == 1920
        assert result.height == 1080

    def test_calculates_aspect_ratio(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(1920, 1080))

        assert result.aspect_ratio == pytest.approx(1920 / 1080, rel=1e-3)

    def test_square_image_aspect_ratio(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(500, 500))

        assert result.aspect_ratio == pytest.approx(1.0)

    def test_normalized_is_valid_jpeg(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(800, 600))

        img = Image.open(BytesIO(result.normalized))
        assert img.mode == "RGB"

    def test_thumbnail_is_valid_image(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(800, 600))

        thumb = Image.open(BytesIO(result.thumbnail))
        assert thumb.mode == "RGB"
        assert max(thumb.size) <= 256

    def test_thumbnail_preserves_aspect_ratio(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(1600, 800))

        thumb = Image.open(BytesIO(result.thumbnail))
        original_ratio = 1600 / 800
        thumb_ratio = thumb.width / thumb.height
        assert thumb_ratio == pytest.approx(original_ratio, rel=0.05)


class TestImagePreprocessorFormats:
    """対応フォーマット（JPEG, PNG, WebP）のテスト。"""

    def test_handles_png(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(400, 300, "PNG"))
        assert result.width == 400

    def test_handles_jpeg(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(400, 300, "JPEG"))
        assert result.width == 400

    def test_handles_webp(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_test_image(400, 300, "WEBP"))
        assert result.width == 400


class TestImagePreprocessorColorSpace:
    """色空間統一のテスト。"""

    def test_converts_rgba_to_rgb(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_rgba_image())

        img = Image.open(BytesIO(result.normalized))
        assert img.mode == "RGB"

    def test_converts_grayscale_to_rgb(self) -> None:
        from services.ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()
        result = proc.process(_make_grayscale_image())

        img = Image.open(BytesIO(result.normalized))
        assert img.mode == "RGB"
