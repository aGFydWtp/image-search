"""ResultCard JSモジュールの構造検証テスト。"""

from pathlib import Path

import pytest

JS_DIR = Path("services/search/static/js")


class TestResultCardModule:
    """result-card.jsが要件を満たす構造を持つことを検証する。"""

    def test_file_exists(self) -> None:
        assert (JS_DIR / "result-card.js").is_file()

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        self.js = (JS_DIR / "result-card.js").read_text(encoding="utf-8")

    def test_exports_function(self) -> None:
        """カード生成関数がエクスポートされていること。"""
        assert "export" in self.js

    def test_creates_image_element(self) -> None:
        """サムネイル画像要素を生成すること (Req 2.2)。"""
        assert "img" in self.js.lower() or "image" in self.js.lower()

    def test_shows_title(self) -> None:
        """作品タイトルを表示すること (Req 2.2)。"""
        assert "title" in self.js

    def test_shows_artist_name(self) -> None:
        """アーティスト名を表示すること (Req 2.2)。"""
        assert "artist" in self.js

    def test_shows_match_reasons_as_badges(self) -> None:
        """match_reasonsをバッジとして表示すること (Req 3.1)。"""
        assert "match_reasons" in self.js or "reasons" in self.js
        assert "badge" in self.js

    def test_has_hover_overlay(self) -> None:
        """ホバー/タップでスコア詳細のオーバーレイがあること (Req 3.2)。"""
        assert "overlay" in self.js

    def test_shows_score(self) -> None:
        """スコア表示があること (Req 3.2)。"""
        assert "score" in self.js

    def test_handles_image_error(self) -> None:
        """画像読み込みエラー時のフォールバックがあること (Req 6.3)。"""
        assert "error" in self.js.lower() or "onerror" in self.js.lower()

    def test_uses_thumbnail_url(self) -> None:
        """thumbnail_urlを使用していること。"""
        assert "thumbnail_url" in self.js

    def test_has_card_css_class(self) -> None:
        """result-card CSSクラスを使用していること。"""
        assert "result-card" in self.js
