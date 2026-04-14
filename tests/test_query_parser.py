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
        result = parser.parse("緑と金色が入っている作品")
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


class TestExpandedMotifExtraction:
    """拡張モチーフマッピングのテスト（Task 4.2 / 5.3）。"""

    def test_new_animal_motifs(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for jp, en in [("猫", "cat"), ("犬", "dog"), ("馬", "horse"), ("蝶", "butterfly")]:
            result = parser.parse(f"{jp}のいる風景")
            assert en in result.filters.motif_tags, f"{jp}→{en} failed"

    def test_new_architecture_motifs(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for jp, en in [("城", "castle"), ("灯台", "lighthouse"), ("塔", "tower")]:
            result = parser.parse(f"{jp}のある風景")
            assert en in result.filters.motif_tags, f"{jp}→{en} failed"

    def test_new_nature_motifs(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for jp, en in [("虹", "rainbow"), ("滝", "waterfall"), ("雲", "cloud"), ("霧", "fog")]:
            result = parser.parse(f"{jp}の見える風景")
            assert en in result.filters.motif_tags, f"{jp}→{en} failed"

    def test_forest_mapping_changed(self) -> None:
        """森 は tree ではなく forest にマッピングされること。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("森の中の風景")
        assert "forest" in result.filters.motif_tags
        assert "tree" not in result.filters.motif_tags

    def test_existing_mappings_preserved(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for jp, en in [("空", "sky"), ("海", "sea"), ("花", "flower"), ("山", "mountain")]:
            result = parser.parse(f"{jp}の絵")
            assert en in result.filters.motif_tags, f"Existing {jp}→{en} broken"

    def test_no_impact_on_color_extraction(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("猫と赤い花のある城")
        assert "cat" in result.filters.motif_tags
        assert "castle" in result.filters.motif_tags
        assert "red" in result.filters.color_tags


class TestColorFalsePositiveAvoidance:
    """漢字1文字キーの複合語誤爆を回避するテスト。"""

    def test_metallic_does_not_trigger_gold(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("金属の光沢があるような")
        assert "gold" not in result.filters.color_tags

    def test_silver_compound_does_not_trigger_silver(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("銀河の絵")
        assert "silver" not in result.filters.color_tags

    def test_explicit_gold_color_still_works(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("金色の仏像")
        assert "gold" in result.filters.color_tags


class TestTextureExpansion:
    """質感キーワードを semantic_query に英訳ヒントとして追記するテスト。"""

    def test_metallic_glossy_expansion(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("金属の光沢があるような")
        assert "metallic surface" in result.semantic_query
        assert "glossy shiny surface" in result.semantic_query

    def test_no_texture_no_expansion(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("青い空")
        assert result.semantic_query == "青い空"

    def test_matte_does_not_also_trigger_glossy(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("つや消しの器")
        assert "matte surface" in result.semantic_query
        assert "glossy" not in result.semantic_query

    def test_sparkle_terms_become_texture_not_brightness(self) -> None:
        """擬態語「きらきら」等は brightness ではなく sparkle 質感として
        semantic_query に英語ヒントを足し、brightness_min は発火しない。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for jp, hint in [
            ("きらきら", "sparkling"),
            ("キラキラ", "sparkling"),
            ("輝く星", "shining"),
            ("煌めく夜", "sparkling"),
            ("眩しい朝日", "dazzling"),
        ]:
            result = parser.parse(jp)
            assert hint in result.semantic_query, f"{jp} → expected '{hint}' hint"
            assert result.boosts.brightness_min is None, (
                f"{jp} should not trigger brightness_min filter"
            )


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
        result = parser.parse("やさしい感じで、緑と金色が入っていて、空っぽい作品")
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
