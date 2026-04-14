"""QdrantRepository: CRUD / 検索操作をエイリアス解決経由で行う。

Read 経路は :class:`CollectionResolver` に委譲して毎リクエストで物理コレクション名を
解決し、切替にプロセス再起動なしで追従する。Write 経路は明示物理名指定 (再インデックス)
と Resolver 経由 (差分 ingestion) の両方をサポートする。
"""

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

from shared.models.artwork import ArtworkPayload
from shared.qdrant.resolver import CollectionResolver

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
    """エイリアス経由で Qdrant を操作するリポジトリ。"""

    def __init__(
        self,
        client: QdrantClient,
        resolver: CollectionResolver,
        vector_dim: int,
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._vector_dim = vector_dim

    def ensure_collection(self, physical_name: str) -> None:
        """指定された物理コレクションが無ければ作成し、payload index を設定する。"""
        if self._client.collection_exists(collection_name=physical_name):
            logger.info(
                "Collection %s already exists, skipping creation", physical_name
            )
            return

        self._client.create_collection(
            collection_name=physical_name,
            vectors_config={
                "image_semantic": VectorParams(
                    size=self._vector_dim, distance=Distance.COSINE
                ),
                "text_semantic": VectorParams(
                    size=self._vector_dim, distance=Distance.COSINE
                ),
            },
        )
        logger.info("Created collection %s", physical_name)

        for tag_field in ("mood_tags", "motif_tags", "color_tags", "freeform_keywords"):
            self._client.create_payload_index(
                collection_name=physical_name,
                field_name=tag_field,
                field_schema=PayloadSchemaType.KEYWORD,
            )

        self._client.create_payload_index(
            collection_name=physical_name,
            field_name="brightness_score",
            field_schema=PayloadSchemaType.FLOAT,
        )
        logger.info("Created payload indexes for %s", physical_name)

    def upsert_artwork(
        self,
        artwork_id: str,
        image_vector: list[float],
        text_vector: list[float],
        payload: ArtworkPayload,
        target_collection: str | None = None,
    ) -> None:
        """アートワークを upsert する。

        ``target_collection`` が与えられればその物理コレクションへ、
        ``None`` なら Resolver が返す現在のエイリアスターゲットへ書き込む。
        """
        collection = (
            target_collection
            if target_collection is not None
            else self._resolver.resolve()
        )
        point_id = _artwork_id_to_point_id(artwork_id)
        payload_dict = payload.model_dump(mode="json")

        self._client.upsert(
            collection_name=collection,
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
        logger.info(
            "Upserted artwork %s (point_id=%d) into %s",
            artwork_id,
            point_id,
            collection,
        )

    def exists(self, artwork_id: str) -> bool:
        """artwork_id が現在のエイリアスターゲットに存在するか確認する。"""
        collection = self._resolver.resolve()
        point_id = _artwork_id_to_point_id(artwork_id)
        results = self._client.retrieve(
            collection_name=collection,
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
        """prefilter + vector search を現在のエイリアスターゲットに対して実行する。"""
        collection = self._resolver.resolve()
        query_filter = self._build_filter(filters) if filters else None

        response = self._client.query_points(
            collection_name=collection,
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

    def count(self, physical_name: str | None = None) -> int:
        """指定物理名 (None なら Resolver 経由) のポイント件数を正確に返す。

        検証ゲートで新旧コレクションの件数比を計算する用途。
        """
        collection = (
            physical_name if physical_name is not None else self._resolver.resolve()
        )
        result = self._client.count(collection_name=collection, exact=True)
        return result.count

    def _build_filter(self, filters: SearchFilters) -> Filter | None:
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
