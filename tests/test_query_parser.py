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


class TestNormalizeHelper:
    """_normalize() の単体テスト: 表記揺れ正規化の核。"""

    def test_katakana_to_hiragana(self) -> None:
        from services.search.query_parser import _normalize

        assert _normalize("ネコ") == "ねこ"
        assert _normalize("オレンジ") == "おれんじ"

    def test_hiragana_unchanged(self) -> None:
        from services.search.query_parser import _normalize

        assert _normalize("ねこ") == "ねこ"

    def test_kanji_unchanged(self) -> None:
        from services.search.query_parser import _normalize

        assert _normalize("猫") == "猫"
        assert _normalize("山岳") == "山岳"

    def test_halfwidth_katakana_normalized(self) -> None:
        """半角カナ → 全角ひらがな (NFKC + kata→hira)。"""
        from services.search.query_parser import _normalize

        assert _normalize("ﾈｺ") == "ねこ"

    def test_ascii_lowercased(self) -> None:
        from services.search.query_parser import _normalize

        assert _normalize("CAT") == "cat"

    def test_mixed_query(self) -> None:
        from services.search.query_parser import _normalize

        assert _normalize("ネコの絵") == "ねこの絵"


class TestKanaNormalizationMatching:
    """カナ正規化により表記揺れを吸収するテスト。"""

    def test_hiragana_query_matches_katakana_alias(self) -> None:
        """JSON に「ネコ」エイリアスがあれば「ねこ」クエリでも cat にヒット。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("ねこのいる風景")
        assert "cat" in result.filters.motif_tags

    def test_katakana_query_matches_hiragana_alias(self) -> None:
        """逆方向: 「とり」エイリアスがあれば「トリ」クエリで bird にヒット。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("トリの絵")
        assert "bird" in result.filters.motif_tags

    def test_hiragana_color_query(self) -> None:
        """「おれんじ色の夕焼け」が orange に正規化されてヒット。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("おれんじ色の夕焼け")
        assert "orange" in result.filters.color_tags

    def test_katakana_texture_query(self) -> None:
        """「キンゾク」(金属) のような表記でも metallic ヒントが付く想定。
        ※ 金属は漢字なのでこのケースは別途エイリアス必要。代わりに
        「ツヤ消し」「つやけし」「つや消し」が同一視されることを確認。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        result = parser.parse("ツヤけしの器")
        assert "matte surface" in result.semantic_query
        assert "glossy" not in result.semantic_query

    def test_katakana_brightness(self) -> None:
        """「アカルイ」が brightness_min=0.6 を発火 (現状 _BRIGHTNESS_BRIGHT に
        「明るい」のみ。カタカナ表記もヒットする想定)。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        # 「明るい」のひらがな表記は通常 「あかるい」 だが、
        # カナ正規化後に「明るい」とは合致しない (漢字→かなの変換は別)。
        # ここでは確実な kata→hira 変換のみ検証する: 「ダーク」→「だーく」
        result = parser.parse("だーくな絵")
        assert result.boosts.brightness_min == 0.0


class TestMotifSynonyms:
    """motif_jp_map.json への同義語追加で表記揺れを吸収するテスト。

    短い純ひらがな (やま/うみ/はな/ほし/つき/しろ 等) は他語との衝突
    (やまない・話す・欲しい・続き・面白い等) を起こすため意図的に
    エイリアスから除外している。同義語は3文字以上 or 漢字+カナの
    曖昧さの少ないものに限定する。
    """

    def test_mountain_synonyms(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for q in ["山岳の風景", "マウンテン", "峰の連なり"]:
            result = parser.parse(q)
            assert "mountain" in result.filters.motif_tags, f"{q!r} did not match mountain"

    def test_sky_synonyms(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for q in ["天空の絵", "スカイラインの絵"]:
            result = parser.parse(q)
            assert "sky" in result.filters.motif_tags, f"{q!r} did not match sky"

    def test_sea_synonyms(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for q in ["海洋の絵", "オーシャン"]:
            result = parser.parse(q)
            assert "sea" in result.filters.motif_tags, f"{q!r} did not match sea"

    def test_flower_synonyms(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for q in ["華やかな庭", "華麗な作品", "ブロッサム"]:
            result = parser.parse(q)
            assert "flower" in result.filters.motif_tags, f"{q!r} did not match flower"

    def test_flower_does_not_falsely_match_unrelated_compounds(self) -> None:
        """「中華」「華族」のような flower と無関係な複合語で誤爆しない。"""
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for q in ["中華料理の絵", "華族の肖像"]:
            result = parser.parse(q)
            assert "flower" not in result.filters.motif_tags, (
                f"{q!r} should not match flower"
            )

    def test_star_moon_sun_synonyms(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        assert "star" in parser.parse("スターの輝き").filters.motif_tags
        assert "moon" in parser.parse("ムーンライト").filters.motif_tags
        assert "sun" in parser.parse("おひさま").filters.motif_tags

    def test_castle_synonyms(self) -> None:
        from services.search.query_parser import QueryParser

        parser = QueryParser()
        for q in ["キャッスル", "城郭の絵"]:
            result = parser.parse(q)
            assert "castle" in result.filters.motif_tags, f"{q!r} did not match castle"


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
