"""共有データモデルのテスト。"""

import pytest
from pydantic import ValidationError

from shared.models.artwork import ArtworkPayload
from shared.models.ingestion import IndexRequest, IndexResponse
from shared.models.search import (
    ParsedQuery,
    QueryBoosts,
    QueryFilters,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)


def _valid_payload_kwargs() -> dict:
    """ArtworkPayloadの有効なパラメータセットを返すヘルパー。"""
    return dict(
        artwork_id="art_001",
        title="Evening Light",
        artist_name="A. Example",
        image_url="https://example.com/image.jpg",
        thumbnail_url="https://example.com/thumb.jpg",
        caption="A soft luminous sky.",
        mood_tags=["やさしい"],
        motif_tags=["空"],
        style_tags=[],
        subject_tags=[],
        freeform_keywords=["lighthouse", "windmill"],
        color_tags=["green", "gold"],
        palette_hex=["#A8C66C"],
        brightness_score=0.78,
        saturation_score=0.42,
        warmth_score=0.61,
        is_abstract=True,
        has_character=False,
        taxonomy_version="v1",
        ingested_at="2026-03-18T10:00:00Z",
        updated_at="2026-03-18T10:00:00Z",
    )


class TestArtworkPayload:
    def test_create_valid_payload(self) -> None:
        payload = ArtworkPayload(**_valid_payload_kwargs())
        assert payload.artwork_id == "art_001"
        assert payload.brightness_score == 0.78
        assert "green" in payload.color_tags

    def test_payload_to_dict(self) -> None:
        payload = ArtworkPayload(**_valid_payload_kwargs())
        d = payload.model_dump()
        assert d["artwork_id"] == "art_001"
        assert isinstance(d["mood_tags"], list)

    def test_empty_artwork_id_rejected(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["artwork_id"] = ""
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)

    def test_brightness_score_out_of_range(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["brightness_score"] = 1.5
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)

    def test_saturation_score_negative(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["saturation_score"] = -0.1
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)

    def test_invalid_palette_hex(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["palette_hex"] = ["not-a-color"]
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)

    def test_valid_palette_hex(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["palette_hex"] = ["#A8C66C", "#D9B44A", "#EDE7D1"]
        payload = ArtworkPayload(**kwargs)
        assert len(payload.palette_hex) == 3

    def test_freeform_keywords_field(self) -> None:
        payload = ArtworkPayload(**_valid_payload_kwargs())
        assert payload.freeform_keywords == ["lighthouse", "windmill"]

    def test_freeform_keywords_required(self) -> None:
        kwargs = _valid_payload_kwargs()
        del kwargs["freeform_keywords"]
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)

    def test_invalid_image_url_rejected(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["image_url"] = "not-a-url"
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)

    def test_datetime_fields_parsed(self) -> None:
        payload = ArtworkPayload(**_valid_payload_kwargs())
        from datetime import datetime

        assert isinstance(payload.ingested_at, datetime)
        assert isinstance(payload.updated_at, datetime)

    def test_invalid_datetime_rejected(self) -> None:
        kwargs = _valid_payload_kwargs()
        kwargs["ingested_at"] = "not-a-date"
        with pytest.raises(ValidationError):
            ArtworkPayload(**kwargs)


class TestSearchModels:
    def test_search_request_defaults(self) -> None:
        req = SearchRequest(query="やさしい緑の作品")
        assert req.query == "やさしい緑の作品"
        assert req.limit == 24

    def test_search_request_custom_limit(self) -> None:
        req = SearchRequest(query="test", limit=10)
        assert req.limit == 10

    def test_search_request_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="")

    def test_search_request_limit_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="test", limit=0)

    def test_search_request_limit_over_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="test", limit=101)

    def test_query_filters_defaults(self) -> None:
        filters = QueryFilters()
        assert filters.motif_tags == []
        assert filters.color_tags == []

    def test_query_boosts_defaults(self) -> None:
        boosts = QueryBoosts()
        assert boosts.brightness_min is None

    def test_query_boosts_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QueryBoosts(brightness_min=1.5)

    def test_parsed_query(self) -> None:
        pq = ParsedQuery(
            semantic_query="やさしい 穏やか",
            filters=QueryFilters(motif_tags=["空"], color_tags=["green"]),
            boosts=QueryBoosts(brightness_min=0.55),
        )
        assert pq.semantic_query == "やさしい 穏やか"
        assert pq.filters.motif_tags == ["空"]
        assert pq.boosts.brightness_min == 0.55

    def test_search_result_item(self) -> None:
        item = SearchResultItem(
            artwork_id="art_001",
            title="Evening Light",
            artist_name="A. Example",
            thumbnail_url="https://example.com/thumb.jpg",
            score=0.92,
            match_reasons=["やさしい雰囲気が近い", "空モチーフ一致"],
        )
        assert item.score == 0.92
        assert len(item.match_reasons) == 2

    def test_search_response(self) -> None:
        resp = SearchResponse(
            parsed_query=ParsedQuery(
                semantic_query="test",
                filters=QueryFilters(),
                boosts=QueryBoosts(),
            ),
            items=[],
        )
        assert resp.items == []


class TestIngestionModels:
    def test_index_request_valid(self) -> None:
        req = IndexRequest(
            artwork_id="art_001",
            image_url="https://example.com/image.jpg",
            title="Evening Light",
            artist_name="A. Example",
        )
        assert req.artwork_id == "art_001"

    def test_index_request_empty_artwork_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IndexRequest(
                artwork_id="",
                image_url="https://example.com/image.jpg",
                title="Test",
                artist_name="Test",
            )

    def test_index_request_invalid_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IndexRequest(
                artwork_id="art_001",
                image_url="not-a-url",
                title="Test",
                artist_name="Test",
            )

    def test_index_response_created(self) -> None:
        resp = IndexResponse(artwork_id="art_001", status="created")
        assert resp.status == "created"

    def test_index_response_updated(self) -> None:
        resp = IndexResponse(artwork_id="art_001", status="updated")
        assert resp.status == "updated"
