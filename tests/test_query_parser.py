"""QueryParser のユニットテスト。

日本語自然言語クエリの分解を検証する。
"""

from shared.models.search import ParsedQuery


class TestColorExtraction:
    """日本語色名 → 英語color_tagsへの変換テスト。"""

    def test_single_color(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("緑の絵")
        assert "green" in result.filters.color_tags

    def test_multiple_colors(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("緑と金が入っている作品")
        assert "green" in result.filters.color_tags
        assert "gold" in result.filters.color_tags

    def test_blue(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("青い空")
        assert "blue" in result.filters.color_tags

    def test_red(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("赤い花")
        assert "red" in result.filters.color_tags

    def test_white_and_black(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("白と黒のコントラスト")
        assert "white" in result.filters.color_tags
        assert "black" in result.filters.color_tags

    def test_orange(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("オレンジ色の夕焼け")
        assert "orange" in result.filters.color_tags

    def test_purple(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("紫の花")
        assert "purple" in result.filters.color_tags


class TestMotifExtraction:
    """日本語モチーフ表現 → 英語motif_tagsへの変換テスト。"""

    def test_sky(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("空っぽい作品")
        assert "sky" in result.filters.motif_tags

    def test_sea(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("海の風景")
        assert "sea" in result.filters.motif_tags

    def test_flower(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("花のある絵")
        assert "flower" in result.filters.motif_tags

    def test_mountain(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("山の風景画")
        assert "mountain" in result.filters.motif_tags

    def test_tree(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("木のある森")
        assert "tree" in result.filters.motif_tags

    def test_multiple_motifs(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("空と海のある風景")
        assert "sky" in result.filters.motif_tags
        assert "sea" in result.filters.motif_tags


class TestBrightnessBoost:
    """明るさ関連表現 → brightness boost変換テスト。"""

    def test_bright_expression(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("明るい雰囲気の絵")
        assert result.boosts.brightness_min is not None
        assert result.boosts.brightness_min >= 0.6

    def test_dark_expression(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("暗い雰囲気の絵")
        assert result.boosts.brightness_min is not None
        assert result.boosts.brightness_min <= 0.3

    def test_no_brightness_expression(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("花のある絵")
        assert result.boosts.brightness_min is None


class TestSemanticQuery:
    """semantic_query の構成テスト。"""

    def test_mood_becomes_semantic_query(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("やさしい感じの絵")
        assert len(result.semantic_query) > 0

    def test_full_query_example(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("やさしい感じで、緑と金が入っていて、空っぽい作品")
        assert "green" in result.filters.color_tags
        assert "gold" in result.filters.color_tags
        assert "sky" in result.filters.motif_tags
        assert len(result.semantic_query) > 0

    def test_returns_parsed_query_type(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("静かな海")
        assert isinstance(result, ParsedQuery)


class TestFallback:
    """分解不能クエリのフォールバックテスト。"""

    def test_unknown_query_uses_original_as_semantic(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("something completely unknown")
        assert result.semantic_query == "something completely unknown"
        assert result.filters.color_tags == []
        assert result.filters.motif_tags == []

    def test_empty_filters_for_pure_mood(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("穏やかな雰囲気")
        assert len(result.semantic_query) > 0
