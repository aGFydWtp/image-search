"""ApiClient JSモジュールの構造検証テスト。"""

from pathlib import Path

import pytest

JS_DIR = Path("services/search/static/js")


class TestApiClientFileExists:
    """api-client.jsが存在し、必要な構造を持つことを検証する。"""

    def test_file_exists(self) -> None:
        assert (JS_DIR / "api-client.js").is_file()

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        self.js = (JS_DIR / "api-client.js").read_text(encoding="utf-8")

    def test_exports_search_function(self) -> None:
        """search関数がエクスポートされていること (Req 1.2)。"""
        assert "export" in self.js
        assert "search" in self.js

    def test_uses_fetch_api(self) -> None:
        """fetch APIを使用していること。"""
        assert "fetch" in self.js

    def test_uses_abort_controller(self) -> None:
        """AbortControllerでタイムアウト制御していること (Req 4.4)。"""
        assert "AbortController" in self.js

    def test_posts_to_search_endpoint(self) -> None:
        """正しいAPIエンドポイントにPOSTすること (Req 1.2)。"""
        assert "/api/artworks/search" in self.js

    def test_handles_http_errors(self) -> None:
        """HTTPステータスエラーを処理すること (Req 4.3)。"""
        assert "ok" in self.js or "status" in self.js

    def test_timeout_value(self) -> None:
        """30秒のタイムアウトが設定されていること (Req 4.4)。"""
        assert "30000" in self.js or "30_000" in self.js

    def test_handles_abort_error(self) -> None:
        """AbortErrorを検知してタイムアウトメッセージを生成すること。"""
        assert "AbortError" in self.js

    def test_cancels_previous_request(self) -> None:
        """前回リクエストのキャンセル機構があること。"""
        assert "abort" in self.js

    def test_content_type_json(self) -> None:
        """Content-Type: application/jsonを送信すること。"""
        assert "application/json" in self.js
