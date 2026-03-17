"""QdrantRepository のユニットテスト。

Qdrant の実挙動をモックして、Repository のロジックを検証する。
"""

from datetime import datetime
from unittest.mock import MagicMock

from qdrant_client.models import Distance, ScoredPoint

from shared.config import Settings
from shared.models.artwork import ArtworkPayload
from shared.qdrant.repository import QdrantRepository, SearchFilters, _artwork_id_to_point_id


def _make_settings(**overrides) -> Settings:
    defaults = {"qdrant_host": "localhost", "qdrant_port": 6333, "qdrant_collection": "artworks_v1", "vector_dim": 1152}
    defaults.update(overrides)
    return Settings(**defaults)


def _make_payload() -> ArtworkPayload:
    return ArtworkPayload(
        artwork_id="art-001",
        title="Sunset over the sea",
        artist_name="Test Artist",
        image_url="https://example.com/img.jpg",
        thumbnail_url="https://example.com/thumb.jpg",
        caption="A calm sunset over the ocean",
        mood_tags=["calm", "warm"],
        motif_tags=["sky", "sea"],
        style_tags=["impressionism"],
        subject_tags=["landscape"],
        color_tags=["orange", "blue"],
        palette_hex=["#FF8C00", "#4682B4"],
        brightness_score=0.7,
        saturation_score=0.6,
        warmth_score=0.8,
        is_abstract=False,
        has_character=False,
        taxonomy_version="v1",
        ingested_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _make_vector(dim: int = 1152, val: float = 0.1) -> list[float]:
    return [val] * dim


class TestEnsureCollection:
    """ensure_collection() のテスト。"""

    def test_creates_collection_when_not_exists(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = False
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        repo.ensure_collection()

        client.create_collection.assert_called_once()
        args = client.create_collection.call_args
        assert args.kwargs["collection_name"] == "artworks_v1"
        vectors_config = args.kwargs["vectors_config"]
        assert "image_semantic" in vectors_config
        assert "text_semantic" in vectors_config
        assert vectors_config["image_semantic"].size == 1152
        assert vectors_config["image_semantic"].distance == Distance.COSINE
        assert vectors_config["text_semantic"].size == 1152
        assert vectors_config["text_semantic"].distance == Distance.COSINE

    def test_skips_creation_when_collection_exists(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        repo.ensure_collection()

        client.create_collection.assert_not_called()

    def test_creates_payload_indexes(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = False
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        repo.ensure_collection()

        index_calls = client.create_payload_index.call_args_list
        indexed_fields = {c.kwargs["field_name"] for c in index_calls}
        assert "mood_tags" in indexed_fields
        assert "motif_tags" in indexed_fields
        assert "color_tags" in indexed_fields
        assert "brightness_score" in indexed_fields


class TestUpsertArtwork:
    """upsert_artwork() のテスト。"""

    def test_upserts_point_with_named_vectors(self) -> None:
        client = MagicMock()
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)
        payload = _make_payload()
        img_vec = _make_vector()
        txt_vec = _make_vector(val=0.2)

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=img_vec,
            text_vector=txt_vec,
            payload=payload,
        )

        client.upsert.assert_called_once()
        args = client.upsert.call_args
        assert args.kwargs["collection_name"] == "artworks_v1"
        points = args.kwargs["points"]
        assert len(points) == 1
        point = points[0]
        assert point.vector["image_semantic"] == img_vec
        assert point.vector["text_semantic"] == txt_vec

    def test_point_payload_contains_all_fields(self) -> None:
        client = MagicMock()
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)
        payload = _make_payload()

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=_make_vector(),
            text_vector=_make_vector(),
            payload=payload,
        )

        point = client.upsert.call_args.kwargs["points"][0]
        assert point.payload["artwork_id"] == "art-001"
        assert point.payload["title"] == "Sunset over the sea"
        assert point.payload["mood_tags"] == ["calm", "warm"]
        assert point.payload["brightness_score"] == 0.7

    def test_uses_artwork_id_hash_as_point_id(self) -> None:
        client = MagicMock()
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)
        payload = _make_payload()

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=_make_vector(),
            text_vector=_make_vector(),
            payload=payload,
        )

        point = client.upsert.call_args.kwargs["points"][0]
        expected_id = _artwork_id_to_point_id("art-001")
        assert point.id == expected_id

        # Same artwork_id should produce the same point id
        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=_make_vector(),
            text_vector=_make_vector(),
            payload=payload,
        )
        point2 = client.upsert.call_args.kwargs["points"][0]
        assert point.id == point2.id


class TestExists:
    """exists() のテスト。"""

    def test_returns_true_when_point_found(self) -> None:
        client = MagicMock()
        client.retrieve.return_value = [MagicMock()]
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        assert repo.exists("art-001") is True

    def test_returns_false_when_point_not_found(self) -> None:
        client = MagicMock()
        client.retrieve.return_value = []
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        assert repo.exists("art-999") is False

    def test_uses_point_id_lookup(self) -> None:
        client = MagicMock()
        client.retrieve.return_value = []
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        repo.exists("art-001")

        args = client.retrieve.call_args
        assert args.kwargs["collection_name"] == "artworks_v1"
        expected_id = _artwork_id_to_point_id("art-001")
        assert args.kwargs["ids"] == [expected_id]
        assert args.kwargs["with_payload"] is False
        assert args.kwargs["with_vectors"] is False


class TestSearch:
    """search() のテスト。"""

    def test_search_returns_results(self) -> None:
        client = MagicMock()
        scored = ScoredPoint(
            id=1,
            version=0,
            score=0.95,
            payload={
                "artwork_id": "art-001",
                "title": "Sunset",
                "artist_name": "Artist",
                "thumbnail_url": "https://example.com/thumb.jpg",
                "mood_tags": ["calm"],
                "motif_tags": ["sky"],
                "color_tags": ["orange"],
                "brightness_score": 0.7,
            },
            vector=None,
        )
        client.query_points.return_value = MagicMock(points=[scored])
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        results = repo.search(
            query_vector=_make_vector(),
            filters=None,
            limit=10,
        )

        assert len(results) == 1
        assert results[0].artwork_id == "art-001"
        assert results[0].score == 0.95

    def test_search_with_filters(self) -> None:
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)
        filters = SearchFilters(motif_tags=["sky"], color_tags=["blue"])

        repo.search(
            query_vector=_make_vector(),
            filters=filters,
            limit=10,
        )

        args = client.query_points.call_args
        query_filter = args.kwargs.get("query_filter")
        assert query_filter is not None

    def test_search_without_filters(self) -> None:
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        repo.search(
            query_vector=_make_vector(),
            filters=None,
            limit=5,
        )

        args = client.query_points.call_args
        assert args.kwargs["limit"] == 5

    def test_search_uses_text_semantic_vector(self) -> None:
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)
        vec = _make_vector(val=0.5)

        repo.search(query_vector=vec, filters=None, limit=10)

        args = client.query_points.call_args
        assert args.kwargs["collection_name"] == "artworks_v1"
        assert args.kwargs["using"] == "text_semantic"
        assert args.kwargs["query"] == vec

    def test_search_result_contains_payload(self) -> None:
        client = MagicMock()
        scored = ScoredPoint(
            id=1,
            version=0,
            score=0.8,
            payload={
                "artwork_id": "art-002",
                "title": "Forest",
                "artist_name": "Artist B",
                "thumbnail_url": "https://example.com/thumb2.jpg",
                "mood_tags": ["peaceful"],
                "motif_tags": ["tree"],
                "color_tags": ["green"],
                "brightness_score": 0.5,
            },
            vector=None,
        )
        client.query_points.return_value = MagicMock(points=[scored])
        settings = _make_settings()
        repo = QdrantRepository(client=client, settings=settings)

        results = repo.search(query_vector=_make_vector(), filters=None, limit=10)

        assert results[0].title == "Forest"
        assert results[0].artist_name == "Artist B"
        assert results[0].payload["motif_tags"] == ["tree"]
