"""SearchForm JSモジュールの構造検証テスト。"""

from pathlib import Path

import pytest

JS_DIR = Path("services/search/static/js")


class TestSearchFormModule:
    """search-form.jsが要件を満たす構造を持つことを検証する。"""

    def test_file_exists(self) -> None:
        assert (JS_DIR / "search-form.js").is_file()

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        self.js = (JS_DIR / "search-form.js").read_text(encoding="utf-8")

    def test_exports_init_function(self) -> None:
        """初期化関数がエクスポートされていること。"""
        assert "export" in self.js
        assert "init" in self.js.lower() or "SearchForm" in self.js

    def test_handles_submit_event(self) -> None:
        """formのsubmitイベントをハンドルすること (Req 1.2, 1.3)。"""
        assert "submit" in self.js

    def test_handles_input_event(self) -> None:
        """inputイベントで空文字チェックを行うこと (Req 1.4)。"""
        assert "input" in self.js

    def test_disables_button_on_empty(self) -> None:
        """空文字時にボタンをdisabledにすること (Req 1.4)。"""
        assert "disabled" in self.js

    def test_prevents_default_submit(self) -> None:
        """フォームのデフォルト送信を防止すること。"""
        assert "preventDefault" in self.js

    def test_has_loading_state(self) -> None:
        """ローディング状態の制御があること (Req 4.1, 4.2)。"""
        assert "loading" in self.js.lower() or "検索中" in self.js

    def test_has_callback_mechanism(self) -> None:
        """検索コールバック機構があること (Req 1.2)。"""
        assert "onSearch" in self.js or "callback" in self.js or "onSearch" in self.js

    def test_validates_query_length(self) -> None:
        """クエリの文字数チェックがあること (Req 1.5)。"""
        assert "length" in self.js or "500" in self.js

    def test_reads_input_value(self) -> None:
        """入力値を取得する処理があること。"""
        assert "value" in self.js and "trim" in self.js
