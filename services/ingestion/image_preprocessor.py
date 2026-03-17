"""ImagePreprocessor: 画像の正規化・サムネイル生成・メタデータ抽出。"""

from io import BytesIO

from PIL import Image

from shared.models.preprocessing import PreprocessedImage

THUMBNAIL_MAX_SIZE = 256


class ImagePreprocessor:
    """画像バイナリを正規化し、サムネイルとメタデータを返す。"""

    def process(self, image_bytes: bytes) -> PreprocessedImage:
        """画像バイナリを前処理する。"""
        img = Image.open(BytesIO(image_bytes))
        width, height = img.size

        # 色空間をRGBに統一
        rgb_img = img.convert("RGB")

        # 正規化画像（RGB JPEG）
        normalized = self._to_bytes(rgb_img, fmt="JPEG")

        # サムネイル生成（アスペクト比維持）
        thumb_img = rgb_img.copy()
        thumb_img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.LANCZOS)
        thumbnail = self._to_bytes(thumb_img, fmt="JPEG")

        return PreprocessedImage(
            normalized=normalized,
            thumbnail=thumbnail,
            width=width,
            height=height,
            aspect_ratio=width / height,
        )

    def _to_bytes(self, img: Image.Image, fmt: str = "JPEG", quality: int = 85) -> bytes:
        """PIL Imageをバイナリにエンコードする。"""
        buf = BytesIO()
        img.save(buf, format=fmt, quality=quality)
        return buf.getvalue()
