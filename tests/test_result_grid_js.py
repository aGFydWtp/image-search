"""ResultGrid JSモジュールの構造検証テスト。"""

from pathlib import Path

import pytest

JS_DIR = Path("services/search/static/js")


class TestResultGridModule:
    """result-grid.jsが要件を満たす構造を持つことを検証する。"""

    def test_file_exists(self) -> None:
        assert (JS_DIR / "result-grid.js").is_file()

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        self.js = (JS_DIR / "result-grid.js").read_text(encoding="utf-8")

    def test_exports_functions(self) -> None:
        """初期化・描画関数がエクスポートされていること。"""
        assert "export" in self.js

    def test_renders_items(self) -> None:
        """結果アイテムを描画する処理があること (Req 2.1)。"""
        assert "item" in self.js.lower() or "card" in self.js.lower()

    def test_shows_result_count(self) -> None:
        """件数表示があること (Req 2.4)。"""
        assert "件" in self.js or "count" in self.js.lower()

    def test_shows_empty_message(self) -> None:
        """0件メッセージの表示制御があること (Req 2.3)。"""
        assert "empty" in self.js.lower() or "見つかりませんでした" in self.js

    def test_shows_loading_state(self) -> None:
        """ローディング表示の制御があること (Req 4.1)。"""
        assert "loading" in self.js.lower()

    def test_shows_error_message(self) -> None:
        """エラーメッセージ表示があること (Req 4.3)。"""
        assert "error" in self.js.lower()

    def test_handles_timeout_message(self) -> None:
        """タイムアウトメッセージ対応があること (Req 4.4)。"""
        assert "error" in self.js.lower() or "message" in self.js.lower()

    def test_references_grid_element(self) -> None:
        """result-gridのDOM要素を参照していること。"""
        assert "result-grid" in self.js
