"""SPA HTMLスケルトンとCSS構造の検証テスト。"""

from pathlib import Path

import pytest

STATIC_DIR = Path("services/search/static")


class TestHTMLStructure:
    """index.htmlのDOM構造が要件を満たすことを検証する。"""

    @pytest.fixture(autouse=True)
    def load_html(self) -> None:
        self.html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def test_has_doctype(self) -> None:
        assert "<!doctype html>" in self.html.lower()

    def test_lang_is_ja(self) -> None:
        assert 'lang="ja"' in self.html

    def test_has_viewport_meta(self) -> None:
        assert "viewport" in self.html

    def test_has_css_link(self) -> None:
        assert "style.css" in self.html

    def test_has_search_form_section(self) -> None:
        """検索フォーム用のセクションが存在すること (Req 1.1)。"""
        assert 'id="search-form"' in self.html or 'id="search-section"' in self.html

    def test_has_result_grid_section(self) -> None:
        """結果グリッド用のセクションが存在すること (Req 2.1)。"""
        assert 'id="result-grid"' in self.html or 'id="results"' in self.html

    def test_has_query_info_section(self) -> None:
        """クエリ解析結果用のセクションが存在すること (Req 5.1)。"""
        assert 'id="query-info"' in self.html

    def test_has_search_input(self) -> None:
        """テキスト入力フィールドが存在すること (Req 1.1)。"""
        assert '<input' in self.html and 'type="text"' in self.html

    def test_has_search_button(self) -> None:
        """検索ボタンが存在すること (Req 1.1)。"""
        assert '<button' in self.html

    def test_has_maxlength(self) -> None:
        """テキスト入力に500文字上限が設定されていること (Req 1.5)。"""
        assert 'maxlength="500"' in self.html

    def test_has_js_modules(self) -> None:
        """JSモジュールが読み込まれること (Req 7.3)。"""
        assert "app.js" in self.html


class TestCSSStructure:
    """style.cssの構造が要件を満たすことを検証する。"""

    @pytest.fixture(autouse=True)
    def load_css(self) -> None:
        self.css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")

    def test_css_file_exists(self) -> None:
        assert (STATIC_DIR / "css" / "style.css").is_file()

    def test_has_css_custom_properties(self) -> None:
        """CSS Custom Propertiesでテーマ変数が定義されていること。"""
        assert "--" in self.css and ":root" in self.css

    def test_has_grid_layout(self) -> None:
        """CSS Gridレイアウトが定義されていること (Req 2.1, 6.1)。"""
        assert "grid" in self.css.lower()

    def test_has_auto_fill_minmax(self) -> None:
        """auto-fill/minmaxでレスポンシブ列数を自動調整すること (Req 6.1)。"""
        assert "auto-fill" in self.css or "auto-fit" in self.css
        assert "minmax" in self.css

    def test_has_mobile_media_query(self) -> None:
        """768px未満のモバイル対応メディアクエリがあること (Req 6.2)。"""
        assert "768px" in self.css

    def test_has_object_fit_cover(self) -> None:
        """サムネイル画像のアスペクト比維持設定があること (Req 6.3)。"""
        assert "object-fit" in self.css

    def test_has_loading_spinner_style(self) -> None:
        """ローディングスピナーのスタイルが定義されていること。"""
        assert "spinner" in self.css.lower() or "loading" in self.css.lower()

    def test_has_badge_styles(self) -> None:
        """フィルタタグ用のバッジスタイルが定義されていること (Req 5.2)。"""
        assert "badge" in self.css.lower() or "tag" in self.css.lower()


class TestFileStructure:
    """設計のFile Structureに従ったディレクトリ構成であること。"""

    def test_css_directory_exists(self) -> None:
        assert (STATIC_DIR / "css").is_dir()

    def test_js_directory_exists(self) -> None:
        assert (STATIC_DIR / "js").is_dir()
