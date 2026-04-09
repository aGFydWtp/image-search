"""QueryInfo JSモジュールの構造検証テスト。"""

from pathlib import Path

import pytest

JS_DIR = Path("services/search/static/js")


class TestQueryInfoModule:
    """query-info.jsが要件を満たす構造を持つことを検証する。"""

    def test_file_exists(self) -> None:
        assert (JS_DIR / "query-info.js").is_file()

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        self.js = (JS_DIR / "query-info.js").read_text(encoding="utf-8")

    def test_exports_function(self) -> None:
        """描画関数がエクスポートされていること。"""
        assert "export" in self.js

    def test_shows_semantic_query(self) -> None:
        """semantic_queryを表示すること (Req 5.1)。"""
        assert "semantic_query" in self.js

    def test_shows_motif_tags(self) -> None:
        """motif_tagsを表示すること (Req 5.2)。"""
        assert "motif" in self.js

    def test_shows_color_tags(self) -> None:
        """color_tagsを表示すること (Req 5.2)。"""
        assert "color" in self.js

    def test_uses_badge_motif_class(self) -> None:
        """motif_tagsに緑系バッジクラスを使用すること (Req 5.2)。"""
        assert "badge-motif" in self.js

    def test_uses_badge_color_class(self) -> None:
        """color_tagsに青系バッジクラスを使用すること (Req 5.2)。"""
        assert "badge-color" in self.js

    def test_hides_when_empty(self) -> None:
        """フィルタが空の場合に非表示にすること。"""
        assert "hidden" in self.js

    def test_references_query_info_element(self) -> None:
        """query-infoのDOM要素を参照していること。"""
        assert "query-info" in self.js
