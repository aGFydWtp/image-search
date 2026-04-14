"""QdrantRepository のユニットテスト。

エイリアス解決経由で物理コレクション名を取得し、Read / Write を切替える挙動を検証する。
"""

from datetime import datetime
from unittest.mock import MagicMock

from qdrant_client.models import Distance, ScoredPoint

from shared.models.artwork import ArtworkPayload
from shared.qdrant.repository import (
    QdrantRepository,
    SearchFilters,
    _artwork_id_to_point_id,
)
from shared.qdrant.resolver import CollectionResolver


def _make_resolver(target: str = "artworks_v1") -> CollectionResolver:
    resolver = MagicMock(spec=CollectionResolver)
    resolver.resolve.return_value = target
    return resolver


def _make_repo(
    client: MagicMock,
    resolver_target: str = "artworks_v1",
    vector_dim: int = 1152,
) -> tuple[QdrantRepository, MagicMock]:
    resolver = _make_resolver(resolver_target)
    repo = QdrantRepository(client=client, resolver=resolver, vector_dim=vector_dim)
    return repo, resolver


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
        freeform_keywords=[],
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
    """ensure_collection(physical_name) は指定された物理名で作成する。"""

    def test_creates_collection_with_given_physical_name(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = False
        repo, _ = _make_repo(client)

        repo.ensure_collection("artworks_v2")

        client.create_collection.assert_called_once()
        args = client.create_collection.call_args
        assert args.kwargs["collection_name"] == "artworks_v2"
        vectors_config = args.kwargs["vectors_config"]
        assert vectors_config["image_semantic"].size == 1152
        assert vectors_config["image_semantic"].distance == Distance.COSINE
        assert vectors_config["text_semantic"].size == 1152

    def test_skips_creation_when_collection_exists(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = True
        repo, _ = _make_repo(client)

        repo.ensure_collection("artworks_v1")

        client.create_collection.assert_not_called()

    def test_creates_payload_indexes_for_given_physical_name(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = False
        repo, _ = _make_repo(client)

        repo.ensure_collection("artworks_v2")

        index_calls = client.create_payload_index.call_args_list
        collections = {c.kwargs["collection_name"] for c in index_calls}
        assert collections == {"artworks_v2"}
        fields = {c.kwargs["field_name"] for c in index_calls}
        assert {"mood_tags", "motif_tags", "color_tags", "brightness_score"} <= fields

    def test_does_not_use_resolver(self) -> None:
        client = MagicMock()
        client.collection_exists.return_value = False
        repo, resolver = _make_repo(client)

        repo.ensure_collection("artworks_v9")

        resolver.resolve.assert_not_called()


class TestUpsertArtwork:
    """upsert_artwork() の Resolver / 明示物理名の切替挙動。"""

    def test_upsert_without_target_uses_resolver(self) -> None:
        client = MagicMock()
        repo, resolver = _make_repo(client, resolver_target="artworks_v1")

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=_make_vector(),
            text_vector=_make_vector(val=0.2),
            payload=_make_payload(),
        )

        resolver.resolve.assert_called_once()
        assert client.upsert.call_args.kwargs["collection_name"] == "artworks_v1"

    def test_upsert_with_explicit_target_bypasses_resolver(self) -> None:
        client = MagicMock()
        repo, resolver = _make_repo(client)

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=_make_vector(),
            text_vector=_make_vector(),
            payload=_make_payload(),
            target_collection="artworks_v2",
        )

        resolver.resolve.assert_not_called()
        assert client.upsert.call_args.kwargs["collection_name"] == "artworks_v2"

    def test_upserts_named_vectors(self) -> None:
        client = MagicMock()
        repo, _ = _make_repo(client)
        img_vec = _make_vector(val=0.1)
        txt_vec = _make_vector(val=0.2)

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=img_vec,
            text_vector=txt_vec,
            payload=_make_payload(),
        )

        point = client.upsert.call_args.kwargs["points"][0]
        assert point.vector["image_semantic"] == img_vec
        assert point.vector["text_semantic"] == txt_vec

    def test_uses_artwork_id_hash_as_point_id(self) -> None:
        client = MagicMock()
        repo, _ = _make_repo(client)

        repo.upsert_artwork(
            artwork_id="art-001",
            image_vector=_make_vector(),
            text_vector=_make_vector(),
            payload=_make_payload(),
        )

        point = client.upsert.call_args.kwargs["points"][0]
        assert point.id == _artwork_id_to_point_id("art-001")


class TestExists:
    """exists() は毎回 Resolver を経由する。"""

    def test_exists_uses_resolver(self) -> None:
        client = MagicMock()
        client.retrieve.return_value = [MagicMock()]
        repo, resolver = _make_repo(client, resolver_target="artworks_v2")

        assert repo.exists("art-001") is True
        resolver.resolve.assert_called_once()
        assert client.retrieve.call_args.kwargs["collection_name"] == "artworks_v2"

    def test_exists_returns_false_when_not_found(self) -> None:
        client = MagicMock()
        client.retrieve.return_value = []
        repo, _ = _make_repo(client)

        assert repo.exists("art-999") is False

    def test_each_call_resolves_again(self) -> None:
        """切替の即時反映: 連続呼び出しで Resolver が毎回呼ばれる。"""
        client = MagicMock()
        client.retrieve.return_value = []
        repo, resolver = _make_repo(client)

        repo.exists("a")
        repo.exists("b")
        assert resolver.resolve.call_count == 2


class TestSearch:
    """search() は毎回 Resolver を経由する。"""

    def test_search_uses_resolver_collection(self) -> None:
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        repo, resolver = _make_repo(client, resolver_target="artworks_v5")

        repo.search(query_vector=_make_vector(), filters=None, limit=10)

        resolver.resolve.assert_called_once()
        assert client.query_points.call_args.kwargs["collection_name"] == "artworks_v5"

    def test_search_returns_mapped_results(self) -> None:
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
            },
            vector=None,
        )
        client.query_points.return_value = MagicMock(points=[scored])
        repo, _ = _make_repo(client)

        results = repo.search(query_vector=_make_vector(), filters=None, limit=10)

        assert len(results) == 1
        assert results[0].artwork_id == "art-001"
        assert results[0].score == 0.95

    def test_search_uses_text_semantic_vector(self) -> None:
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        repo, _ = _make_repo(client)

        repo.search(query_vector=_make_vector(), filters=None, limit=10)

        assert client.query_points.call_args.kwargs["using"] == "text_semantic"

    def test_search_applies_filters_when_provided(self) -> None:
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        repo, _ = _make_repo(client)

        repo.search(
            query_vector=_make_vector(),
            filters=SearchFilters(motif_tags=["sky"]),
            limit=5,
        )

        assert client.query_points.call_args.kwargs.get("query_filter") is not None


class TestCount:
    """count() は引数があればその物理名で、なければ Resolver で。"""

    def test_count_without_physical_name_uses_resolver(self) -> None:
        client = MagicMock()
        client.count.return_value = MagicMock(count=42)
        repo, resolver = _make_repo(client, resolver_target="artworks_v1")

        result = repo.count()

        resolver.resolve.assert_called_once()
        assert client.count.call_args.kwargs["collection_name"] == "artworks_v1"
        assert result == 42

    def test_count_with_physical_name_bypasses_resolver(self) -> None:
        client = MagicMock()
        client.count.return_value = MagicMock(count=100)
        repo, resolver = _make_repo(client)

        result = repo.count(physical_name="artworks_v2")

        resolver.resolve.assert_not_called()
        assert client.count.call_args.kwargs["collection_name"] == "artworks_v2"
        assert result == 100

    def test_count_uses_exact_true(self) -> None:
        client = MagicMock()
        client.count.return_value = MagicMock(count=0)
        repo, _ = _make_repo(client)

        repo.count("artworks_v1")

        assert client.count.call_args.kwargs["exact"] is True
