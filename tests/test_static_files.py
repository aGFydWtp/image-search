"""StaticFiles配信のテスト。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """テスト用の静的ファイルディレクトリを作成する。"""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        "<!DOCTYPE html><html><body><h1>Search UI</h1></body></html>",
        encoding="utf-8",
    )
    css_dir = static / "css"
    css_dir.mkdir()
    (css_dir / "style.css").write_text("body { margin: 0; }", encoding="utf-8")
    return static


@pytest.fixture
def app_with_static(static_dir: Path) -> FastAPI:
    """StaticFilesマウント付きのFastAPIアプリを生成する。"""
    from fastapi.staticfiles import StaticFiles

    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/artworks/search")
    def search() -> dict[str, str]:
        return {"result": "ok"}

    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


@pytest.fixture
def client(app_with_static: FastAPI) -> TestClient:
    return TestClient(app_with_static)


class TestStaticFilesMount:
    """StaticFilesマウントが正しく設定されていることを検証する。"""

    def test_root_serves_index_html(self, client: TestClient) -> None:
        """ルートパスがindex.htmlを返すこと。"""
        response = client.get("/")
        assert response.status_code == 200
        assert "Search UI" in response.text

    def test_css_file_served(self, client: TestClient) -> None:
        """CSSファイルが正しく配信されること。"""
        response = client.get("/css/style.css")
        assert response.status_code == 200
        assert "margin" in response.text

    def test_api_routes_take_priority(self, client: TestClient) -> None:
        """APIルートがStaticFilesより優先されること。"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_api_post_routes_work(self, client: TestClient) -> None:
        """POST APIルートがStaticFilesと共存できること。"""
        response = client.post("/api/artworks/search")
        assert response.status_code == 200

    def test_nonexistent_file_returns_404(self, client: TestClient) -> None:
        """存在しないファイルは404を返すこと。"""
        response = client.get("/nonexistent.js")
        assert response.status_code == 404


class TestStaticFilesExist:
    """静的ファイルディレクトリが正しく存在することを検証する。"""

    def test_static_directory_exists(self) -> None:
        """services/search/static/ディレクトリが存在すること。"""
        static_dir = Path("services/search/static")
        assert static_dir.is_dir(), f"{static_dir} が存在しません"

    def test_index_html_exists(self) -> None:
        """index.htmlが存在すること。"""
        index = Path("services/search/static/index.html")
        assert index.is_file(), f"{index} が存在しません"

    def test_index_html_has_content(self) -> None:
        """index.htmlがDOCTYPE宣言を含むこと。"""
        index = Path("services/search/static/index.html")
        content = index.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content.upper() or "<!doctype html>" in content.lower()


class TestSearchAppStaticMount:
    """実際のSearchアプリにStaticFilesマウントが追加されていることを検証する。"""

    def test_app_has_static_mount(self) -> None:
        """app.pyにStaticFilesマウントが含まれていること。"""
        app_source = Path("services/search/app.py").read_text(encoding="utf-8")
        assert "StaticFiles" in app_source
        assert "mount" in app_source
