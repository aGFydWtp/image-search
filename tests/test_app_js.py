"""App JSモジュール（エントリポイント・統合）の構造検証テスト。"""

from pathlib import Path

import pytest

JS_DIR = Path("services/search/static/js")


class TestAppModule:
    """app.jsが全コンポーネントを接続し、状態管理を行うことを検証する。"""

    def test_file_exists(self) -> None:
        assert (JS_DIR / "app.js").is_file()

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        self.js = (JS_DIR / "app.js").read_text(encoding="utf-8")

    def test_imports_api_client(self) -> None:
        """ApiClientモジュールをインポートしていること (Req 1.2)。"""
        assert "api-client" in self.js

    def test_imports_search_form(self) -> None:
        """SearchFormモジュールをインポートしていること。"""
        assert "search-form" in self.js

    def test_imports_result_grid(self) -> None:
        """ResultGridモジュールをインポートしていること。"""
        assert "result-grid" in self.js

    def test_imports_query_info(self) -> None:
        """QueryInfoモジュールをインポートしていること。"""
        assert "query-info" in self.js

    def test_initializes_on_dom_content_loaded(self) -> None:
        """DOMContentLoadedで初期化すること (Req 7.3)。"""
        assert "DOMContentLoaded" in self.js

    def test_calls_search_function(self) -> None:
        """ApiClient.searchを呼び出すフローがあること。"""
        assert "search" in self.js

    def test_handles_error_flow(self) -> None:
        """エラーハンドリングフローがあること (Req 4.3, 4.4)。"""
        assert "catch" in self.js or "error" in self.js.lower()

    def test_manages_loading_state(self) -> None:
        """ローディング状態の管理があること。"""
        assert "loading" in self.js.lower() or "setLoading" in self.js

    def test_renders_results(self) -> None:
        """結果描画の呼び出しがあること。"""
        assert "renderResults" in self.js or "render" in self.js

    def test_renders_query_info(self) -> None:
        """クエリ情報描画の呼び出しがあること。"""
        assert "renderQueryInfo" in self.js or "QueryInfo" in self.js


class TestAllModulesPresent:
    """設計のFile Structureに従った全JSファイルが揃っていること。"""

    @pytest.mark.parametrize("filename", [
        "app.js",
        "api-client.js",
        "search-form.js",
        "result-grid.js",
        "result-card.js",
        "query-info.js",
    ])
    def test_js_module_exists(self, filename: str) -> None:
        assert (JS_DIR / filename).is_file(), f"{filename} が存在しません"
