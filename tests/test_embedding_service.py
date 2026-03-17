"""SigLIP2埋め込みサービスのAPIテスト。

モデルをモックして、FastAPIエンドポイントのリクエスト/レスポンスを検証する。
"""

import importlib.util
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_mock_encoder(dim: int = 1152):
    """モックされたSigLIP2Encoderを生成する。"""
    encoder = MagicMock()
    encoder.encode_image.return_value = [0.1] * dim
    encoder.encode_text.return_value = [0.2] * dim
    encoder.vector_dim = dim
    return encoder


@pytest.fixture()
def client():
    """モデルをモックしたテストクライアント（lifespanバイパス）。"""
    from services.embedding.app import _set_encoder, app

    mock_enc = _make_mock_encoder()
    _set_encoder(mock_enc)

    # lifespanをバイパスしてtorchのimportを回避
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.router.lifespan_context = original_lifespan
        _set_encoder(None)


class TestHealthEndpoint:
    """GET /health のテスト。"""

    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_includes_model_info(self, client: TestClient) -> None:
        response = client.get("/health")
        data = response.json()
        assert "model" in data
        assert "vector_dim" in data


class TestEmbedImageEndpoint:
    """POST /embed/image のテスト。"""

    def test_returns_vector(self, client: TestClient) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        response = client.post(
            "/embed/image",
            content=image_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "vector" in data
        assert len(data["vector"]) == 1152

    def test_returns_correct_vector_values(self, client: TestClient) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        response = client.post(
            "/embed/image",
            content=image_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        data = response.json()
        assert data["vector"][0] == pytest.approx(0.1)

    def test_empty_body_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/embed/image",
            content=b"",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 422


class TestEmbedTextEndpoint:
    """POST /embed/text のテスト。"""

    def test_returns_vector(self, client: TestClient) -> None:
        response = client.post("/embed/text", json={"text": "a calm sunset"})
        assert response.status_code == 200
        data = response.json()
        assert "vector" in data
        assert len(data["vector"]) == 1152

    def test_returns_correct_vector_values(self, client: TestClient) -> None:
        response = client.post("/embed/text", json={"text": "ocean waves"})
        data = response.json()
        assert data["vector"][0] == pytest.approx(0.2)

    def test_empty_text_returns_422(self, client: TestClient) -> None:
        response = client.post("/embed/text", json={"text": ""})
        assert response.status_code == 422

    def test_missing_text_field_returns_422(self, client: TestClient) -> None:
        response = client.post("/embed/text", json={})
        assert response.status_code == 422


_HAS_TORCH = importlib.util.find_spec("torch") is not None


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
class TestSigLIP2Encoder:
    """SigLIP2Encoderの初期化・推論テスト（モデルはモック）。torch必須。"""

    def test_encoder_init_loads_model(self) -> None:
        with (
            patch("services.embedding.encoder.AutoModel") as mock_model_cls,
            patch("services.embedding.encoder.AutoProcessor") as mock_proc_cls,
        ):
            mock_model = MagicMock()
            mock_model.to.return_value = mock_model
            mock_model.eval.return_value = mock_model
            mock_model_cls.from_pretrained.return_value = mock_model
            mock_proc_cls.from_pretrained.return_value = MagicMock()

            from services.embedding.encoder import SigLIP2Encoder

            encoder = SigLIP2Encoder(model_name="test-model", device="cpu")

            mock_model_cls.from_pretrained.assert_called_once()
            mock_proc_cls.from_pretrained.assert_called_once()
            assert encoder.vector_dim == 1152

    def test_encode_image_returns_list(self) -> None:
        with (
            patch("services.embedding.encoder.AutoModel") as mock_model_cls,
            patch("services.embedding.encoder.AutoProcessor") as mock_proc_cls,
            patch("services.embedding.encoder.torch") as mock_torch,
            patch("services.embedding.encoder.Image") as mock_image,
        ):
            mock_model = MagicMock()
            mock_model.to.return_value = mock_model
            mock_model.eval.return_value = mock_model
            # _to_list expects pooler_output or a tensor with squeeze
            fake_output = MagicMock()
            fake_output.pooler_output = MagicMock()
            fake_output.pooler_output.squeeze.return_value = fake_output.pooler_output
            fake_output.pooler_output.cpu.return_value = fake_output.pooler_output
            fake_output.pooler_output.tolist.return_value = [0.5] * 1152
            mock_model.get_image_features.return_value = fake_output
            mock_model_cls.from_pretrained.return_value = mock_model

            mock_processor = MagicMock()
            mock_processor.return_value = {"pixel_values": MagicMock()}
            mock_proc_cls.from_pretrained.return_value = mock_processor

            mock_torch.no_grad.return_value.__enter__ = MagicMock()
            mock_torch.no_grad.return_value.__exit__ = MagicMock()

            mock_image.open.return_value.convert.return_value = MagicMock()

            from services.embedding.encoder import SigLIP2Encoder

            encoder = SigLIP2Encoder(model_name="test-model", device="cpu")
            result = encoder.encode_image(b"\x89PNG" + b"\x00" * 100)

            assert isinstance(result, list)
            assert len(result) == 1152

    def test_encode_text_returns_list(self) -> None:
        with (
            patch("services.embedding.encoder.AutoModel") as mock_model_cls,
            patch("services.embedding.encoder.AutoProcessor") as mock_proc_cls,
            patch("services.embedding.encoder.torch") as mock_torch,
        ):
            mock_model = MagicMock()
            mock_model.to.return_value = mock_model
            mock_model.eval.return_value = mock_model
            fake_output = MagicMock()
            fake_output.pooler_output = MagicMock()
            fake_output.pooler_output.squeeze.return_value = fake_output.pooler_output
            fake_output.pooler_output.cpu.return_value = fake_output.pooler_output
            fake_output.pooler_output.tolist.return_value = [0.3] * 1152
            mock_model.get_text_features.return_value = fake_output
            mock_model_cls.from_pretrained.return_value = mock_model

            mock_processor = MagicMock()
            mock_processor.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
            mock_proc_cls.from_pretrained.return_value = mock_processor

            mock_torch.no_grad.return_value.__enter__ = MagicMock()
            mock_torch.no_grad.return_value.__exit__ = MagicMock()

            from services.embedding.encoder import SigLIP2Encoder

            encoder = SigLIP2Encoder(model_name="test-model", device="cpu")
            result = encoder.encode_text("a calm sunset")

            assert isinstance(result, list)
            assert len(result) == 1152
