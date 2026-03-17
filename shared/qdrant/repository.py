"""QdrantRepository: Qdrantコレクション管理・CRUD・検索操作。"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from shared.config import Settings
from shared.models.artwork import ArtworkPayload

logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    """Qdrant検索時のpayloadフィルタ条件。"""

    motif_tags: list[str] = field(default_factory=list)
    color_tags: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Qdrant検索結果の1件分。"""

    artwork_id: str
    title: str
    artist_name: str
    thumbnail_url: str
    score: float
    payload: dict[str, Any]


def _artwork_id_to_point_id(artwork_id: str) -> int:
    """artwork_idからQdrant point IDを決定論的に生成する。"""
    h = hashlib.sha256(artwork_id.encode()).hexdigest()
    return int(h[:16], 16)


class QdrantRepository:
    """Qdrant artworks_v1コレクションのCRUD・検索操作を集約する。"""

    def __init__(self, client: QdrantClient, settings: Settings) -> None:
        self._client = client
        self._collection = settings.qdrant_collection
        self._vector_dim = settings.vector_dim

    def ensure_collection(self) -> None:
        """コレクションが存在しなければ作成し、payload indexを設定する。"""
        if self._client.collection_exists(collection_name=self._collection):
            logger.info("Collection %s already exists, skipping creation", self._collection)
            return

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "image_semantic": VectorParams(size=self._vector_dim, distance=Distance.COSINE),
                "text_semantic": VectorParams(size=self._vector_dim, distance=Distance.COSINE),
            },
        )
        logger.info("Created collection %s", self._collection)

        for tag_field in ("mood_tags", "motif_tags", "color_tags"):
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name=tag_field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

        self._client.create_payload_index(
            collection_name=self._collection,
            field_name="brightness_score",
            field_schema=PayloadSchemaType.FLOAT,
        )
        logger.info("Created payload indexes for %s", self._collection)

    def upsert_artwork(
        self,
        artwork_id: str,
        image_vector: list[float],
        text_vector: list[float],
        payload: ArtworkPayload,
    ) -> None:
        """アートワークをQdrantにupsertする。"""
        point_id = _artwork_id_to_point_id(artwork_id)
        payload_dict = payload.model_dump(mode="json")

        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector={
                        "image_semantic": image_vector,
                        "text_semantic": text_vector,
                    },
                    payload=payload_dict,
                )
            ],
        )
        logger.info("Upserted artwork %s (point_id=%d)", artwork_id, point_id)

    def exists(self, artwork_id: str) -> bool:
        """artwork_idがコレクション内に存在するか確認する。"""
        point_id = _artwork_id_to_point_id(artwork_id)
        results = self._client.retrieve(
            collection_name=self._collection,
            ids=[point_id],
            with_payload=False,
            with_vectors=False,
        )
        return len(results) > 0

    def search(
        self,
        query_vector: list[float],
        filters: SearchFilters | None,
        limit: int,
    ) -> list[SearchResult]:
        """prefilter + vector searchを実行する。"""
        query_filter = self._build_filter(filters) if filters else None

        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            using="text_semantic",
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        return [
            SearchResult(
                artwork_id=point.payload.get("artwork_id", ""),
                title=point.payload.get("title", ""),
                artist_name=point.payload.get("artist_name", ""),
                thumbnail_url=point.payload.get("thumbnail_url", ""),
                score=point.score,
                payload=dict(point.payload),
            )
            for point in response.points
        ]

    def _build_filter(self, filters: SearchFilters) -> Filter | None:
        """SearchFiltersからQdrant Filterを構築する。"""
        conditions = []

        if filters.motif_tags:
            conditions.append(
                FieldCondition(key="motif_tags", match=MatchAny(any=filters.motif_tags))
            )
        if filters.color_tags:
            conditions.append(
                FieldCondition(key="color_tags", match=MatchAny(any=filters.color_tags))
            )

        return Filter(must=conditions) if conditions else None
