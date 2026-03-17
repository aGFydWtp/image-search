"""SigLIP2埋め込みサービス FastAPIアプリケーション。"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_encoder: Any = None


def _get_encoder():
    """グローバルエンコーダインスタンスを返す。テストでモック差し替え可能。"""
    return _encoder


def _set_encoder(encoder: Any) -> None:
    """エンコーダインスタンスを設定する。テストやlifespanから呼び出す。"""
    global _encoder
    _encoder = encoder


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリ起動時にモデルをロード・ウォームアップする。"""
    from services.embedding.encoder import SigLIP2Encoder

    encoder = SigLIP2Encoder()
    encoder.warmup()
    _set_encoder(encoder)
    logger.info("Embedding service ready")
    yield
    _set_encoder(None)


app = FastAPI(title="SigLIP2 Embedding Service", version="0.1.0", lifespan=lifespan)


class TextRequest(BaseModel):
    """POST /embed/text のリクエストボディ。"""

    text: str = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    """埋め込みベクトルのレスポンス。"""

    vector: list[float]


@app.get("/health")
def health() -> dict:
    encoder = _get_encoder()
    return {
        "status": "ok",
        "model": "siglip2-so400m-patch14-384",
        "vector_dim": encoder.vector_dim if encoder else 0,
    }


@app.post("/embed/image", response_model=EmbeddingResponse)
async def embed_image(request: Request) -> EmbeddingResponse:
    """画像バイナリから埋め込みベクトルを生成する。"""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="Empty image body")

    encoder = _get_encoder()
    if encoder is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    vector = encoder.encode_image(body)
    return EmbeddingResponse(vector=vector)


@app.post("/embed/text", response_model=EmbeddingResponse)
def embed_text(req: TextRequest) -> EmbeddingResponse:
    """テキストから埋め込みベクトルを生成する。"""
    encoder = _get_encoder()
    if encoder is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    vector = encoder.encode_text(req.text)
    return EmbeddingResponse(vector=vector)
