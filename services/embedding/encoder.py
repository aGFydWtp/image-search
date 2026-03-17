"""SigLIP2モデルラッパー。Transformers + MPS/CPUバックエンドで推論する。"""

import logging
from io import BytesIO

import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "google/siglip2-so400m-patch14-384"
VECTOR_DIM = 1152


class SigLIP2Encoder:
    """SigLIP2モデルによる画像・テキスト埋め込み生成。"""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, device: str = "auto") -> None:
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._device = device
        self.vector_dim = VECTOR_DIM

        logger.info("Loading SigLIP2 model %s on %s...", model_name, device)
        self._model = AutoModel.from_pretrained(model_name).to(device).eval()
        self._processor = AutoProcessor.from_pretrained(model_name)
        logger.info("SigLIP2 model loaded successfully")

    def encode_image(self, image_bytes: bytes) -> list[float]:
        """画像バイナリから埋め込みベクトルを生成する。"""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        inputs = self._processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self._device)

        with torch.no_grad():
            features = self._model.get_image_features(pixel_values=pixel_values)

        return features.squeeze().cpu().tolist()

    def encode_text(self, text: str) -> list[float]:
        """テキストから埋め込みベクトルを生成する。"""
        inputs = self._processor(text=[text], return_tensors="pt", padding=True)
        input_ids = inputs["input_ids"].to(self._device)
        attention_mask = inputs["attention_mask"].to(self._device)

        with torch.no_grad():
            features = self._model.get_text_features(
                input_ids=input_ids, attention_mask=attention_mask
            )

        return features.squeeze().cpu().tolist()

    def warmup(self) -> None:
        """モデルのウォームアップ（初回推論の遅延を回避）。"""
        logger.info("Warming up SigLIP2 model...")
        dummy_image = Image.new("RGB", (384, 384), color=(128, 128, 128))
        buf = BytesIO()
        dummy_image.save(buf, format="PNG")
        self.encode_image(buf.getvalue())
        self.encode_text("warmup text")
        logger.info("SigLIP2 warmup complete")
