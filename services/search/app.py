"""Search Service FastAPIアプリケーション。"""

from fastapi import FastAPI

app = FastAPI(title="Image Search API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
