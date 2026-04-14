"""Blue/Green 再インデックスの E2E 統合テスト。

実 Qdrant コンテナ (localhost:6333) を使用。docker compose up -d qdrant
実行後に `pytest tests/test_reindex_e2e.py` で走る。

Qdrant が起動していない場合はモジュール全体がスキップされる。
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Iterator
from datetime import datetime

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    PointStruct,
    VectorParams,
)

from shared.models.artwork import ArtworkPayload
from shared.qdrant.alias_admin import (
    AliasAdmin,
    PhysicalCollectionInUseError,
)
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.resolver import CollectionResolver
from shared.qdrant.validation import ValidationGate
from services.ingestion.reindex import ReindexOrchestrator

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
VECTOR_DIM = 8  # 短いベクトルで高速化 (本番 1152 とは別)
ALIAS = "reindex_e2e_alias"
COLL_A = "reindex_e2e_a"
COLL_B = "reindex_e2e_b"


def _qdrant_available() -> bool:
    try:
        QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=2).get_collections()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _qdrant_available(), reason="Qdrant (localhost:6333) is not reachable"
)


def _artwork_id_to_point_id(artwork_id: str) -> int:
    h = hashlib.sha256(artwork_id.encode()).hexdigest()
    return int(h[:16], 16)


def _payload(artwork_id: str, title: str) -> ArtworkPayload:
    return ArtworkPayload(
        artwork_id=artwork_id,
        title=title,
        artist_name="E2E Artist",
        image_url="https://example.com/a.jpg",
        thumbnail_url="https://example.com/thumb.jpg",
        caption="e2e",
        mood_tags=["calm"],
        motif_tags=["sky"],
        style_tags=["test"],
        subject_tags=["test"],
        freeform_keywords=[],
        color_tags=["blue"],
        palette_hex=["#0000FF"],
        brightness_score=0.5,
        saturation_score=0.5,
        warmth_score=0.5,
        is_abstract=False,
        has_character=False,
        taxonomy_version="v1",
        ingested_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _upsert(client: QdrantClient, collection: str, artwork_id: str, title: str) -> None:
    client.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=_artwork_id_to_point_id(artwork_id),
                vector={
                    "image_semantic": [0.1] * VECTOR_DIM,
                    "text_semantic": [0.2] * VECTOR_DIM,
                },
                payload=_payload(artwork_id, title).model_dump(mode="json"),
            )
        ],
    )


def _create_collection(client: QdrantClient, name: str) -> None:
    if client.collection_exists(collection_name=name):
        client.delete_collection(collection_name=name)
    client.create_collection(
        collection_name=name,
        vectors_config={
            "image_semantic": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            "text_semantic": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        },
    )


def _create_alias(client: QdrantClient, alias: str, target: str) -> None:
    existing = {a.alias_name for a in client.get_aliases().aliases}
    if alias in existing:
        # 既存を削除して張り直す (冪等)
        from qdrant_client.models import DeleteAlias, DeleteAliasOperation

        client.update_collection_aliases(
            change_aliases_operations=[
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)),
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        alias_name=alias, collection_name=target
                    )
                ),
            ]
        )
    else:
        client.update_collection_aliases(
            change_aliases_operations=[
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        alias_name=alias, collection_name=target
                    )
                )
            ]
        )


@pytest.fixture
def client() -> Iterator[QdrantClient]:
    c = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    yield c
    # cleanup
    from qdrant_client.models import DeleteAlias, DeleteAliasOperation

    existing = {a.alias_name for a in c.get_aliases().aliases}
    if ALIAS in existing:
        try:
            c.update_collection_aliases(
                change_aliases_operations=[
                    DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=ALIAS))
                ]
            )
        except Exception:
            pass
    for coll in (COLL_A, COLL_B):
        if c.collection_exists(collection_name=coll):
            c.delete_collection(collection_name=coll)


class TestBlueGreenSwap:
    """フル Blue/Green フロー: A→B 切替 + ロールバック + 削除拒否。"""

    def test_swap_alters_search_target_atomically(
        self, client: QdrantClient
    ) -> None:
        # 1) A を作って alias を A に張り、A へ 1 件投入
        _create_collection(client, COLL_A)
        _create_alias(client, ALIAS, COLL_A)
        _upsert(client, COLL_A, "art-a1", "from A")

        resolver = CollectionResolver(client=client, alias_name=ALIAS)
        repo = QdrantRepository(client=client, resolver=resolver, vector_dim=VECTOR_DIM)

        # Repository 経由の検索は A を見る
        results = repo.search(
            query_vector=[0.2] * VECTOR_DIM, filters=None, limit=10
        )
        titles = {r.title for r in results}
        assert "from A" in titles

        # 2) B を作って別データを投入
        _create_collection(client, COLL_B)
        _upsert(client, COLL_B, "art-b1", "from B")

        # 3) ValidationGate で検証 (ほぼ同件数なので pass)
        gate = ValidationGate(client=client, sample_ratio_threshold=0.5)
        report = gate.validate(old=COLL_A, new=COLL_B, sample_queries=[])
        assert report.passed is True

        # 4) AliasAdmin.swap で原子切替
        admin = AliasAdmin(client=client)
        swap_result = admin.swap(ALIAS, COLL_B)
        assert swap_result.previous_target == COLL_A
        assert swap_result.new_target == COLL_B

        # 5) Repository の検索結果が B に切り替わる
        results_after = repo.search(
            query_vector=[0.2] * VECTOR_DIM, filters=None, limit=10
        )
        titles_after = {r.title for r in results_after}
        assert "from B" in titles_after
        assert "from A" not in titles_after

    def test_rollback_returns_search_to_previous_collection(
        self, client: QdrantClient
    ) -> None:
        _create_collection(client, COLL_A)
        _create_collection(client, COLL_B)
        _upsert(client, COLL_A, "art-a1", "from A")
        _upsert(client, COLL_B, "art-b1", "from B")
        _create_alias(client, ALIAS, COLL_A)

        resolver = CollectionResolver(client=client, alias_name=ALIAS)
        repo = QdrantRepository(client=client, resolver=resolver, vector_dim=VECTOR_DIM)
        admin = AliasAdmin(client=client)

        # A → B へ swap
        admin.swap(ALIAS, COLL_B)
        assert {r.title for r in repo.search([0.2] * VECTOR_DIM, None, 10)} == {"from B"}

        # B → A へ rollback
        admin.rollback(ALIAS, previous_target=COLL_A)
        assert {r.title for r in repo.search([0.2] * VECTOR_DIM, None, 10)} == {"from A"}

    def test_drop_current_target_is_refused(self, client: QdrantClient) -> None:
        _create_collection(client, COLL_A)
        _upsert(client, COLL_A, "art-a1", "from A")
        _create_alias(client, ALIAS, COLL_A)

        admin = AliasAdmin(client=client)
        with pytest.raises(PhysicalCollectionInUseError):
            admin.drop_physical_collection(COLL_A, alias=ALIAS)

        # まだ存在している
        assert client.collection_exists(collection_name=COLL_A)


class TestSwapUnderContinuousSearch:
    """swap 前後の連続検索が 500 を起こさず、かつ応答が壊れない。"""

    def test_no_search_failure_during_swap(self, client: QdrantClient) -> None:
        _create_collection(client, COLL_A)
        _create_collection(client, COLL_B)
        _upsert(client, COLL_A, "art-a1", "from A")
        _upsert(client, COLL_B, "art-b1", "from B")
        _create_alias(client, ALIAS, COLL_A)

        resolver = CollectionResolver(client=client, alias_name=ALIAS)
        repo = QdrantRepository(client=client, resolver=resolver, vector_dim=VECTOR_DIM)
        admin = AliasAdmin(client=client)

        errors: list[Exception] = []
        search_counts = [0, 0, 0]
        stop = threading.Event()

        def _continuous_search(idx: int) -> None:
            while not stop.is_set():
                try:
                    repo.search([0.2] * VECTOR_DIM, None, 10)
                    search_counts[idx] += 1
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

        searchers = [
            threading.Thread(target=_continuous_search, args=(i,)) for i in range(3)
        ]
        for t in searchers:
            t.start()
        time.sleep(0.2)
        admin.swap(ALIAS, COLL_B)
        time.sleep(0.2)
        stop.set()
        for t in searchers:
            t.join(timeout=2.0)

        assert errors == [], f"search errors during swap: {errors!r}"
        # 各スレッドが swap 前後で実際に検索していないと、このテストは
        # カバレッジなしで trivial pass になる。最低 5 回ずつは走っていることを
        # 保証する (sleep 0.2s × 2 + 3 スレッドなら通常数十〜数百回走る)。
        assert min(search_counts) >= 5, (
            f"searches did not run enough during swap window: {search_counts}"
        )


class TestReindexOrchestratorHappyPath:
    """ReindexOrchestrator.run の実 Qdrant での happy path。"""

    def test_run_creates_populates_validates_and_swaps(
        self, client: QdrantClient
    ) -> None:
        # 旧コレクション + alias 準備
        _create_collection(client, COLL_A)
        _upsert(client, COLL_A, "art-a1", "from A")
        _create_alias(client, ALIAS, COLL_A)

        resolver = CollectionResolver(client=client, alias_name=ALIAS)
        repo = QdrantRepository(client=client, resolver=resolver, vector_dim=VECTOR_DIM)
        admin = AliasAdmin(client=client)
        gate = ValidationGate(client=client, sample_ratio_threshold=0.5)
        orch = ReindexOrchestrator(
            client=client,
            repository=repo,
            alias_admin=admin,
            validation_gate=gate,
            alias_name=ALIAS,
            progress_interval=5,
        )

        def _populate(target: str):
            for i in range(3):
                artwork_id = f"art-b{i}"
                client.upsert(
                    collection_name=target,
                    points=[
                        PointStruct(
                            id=_artwork_id_to_point_id(artwork_id),
                            vector={
                                "image_semantic": [0.1] * VECTOR_DIM,
                                "text_semantic": [0.2] * VECTOR_DIM,
                            },
                            payload=_payload(artwork_id, f"from B {i}").model_dump(
                                mode="json"
                            ),
                        )
                    ],
                )
                yield True

        # `force_recreate=True` の挙動を E2E で確認するため、COLL_B を事前に
        # 作成してから orchestrator に delete → ensure_collection で再生成
        # させる。orchestrator.run が既存を適切に壊して作り直すこと + 作り直し後に
        # populate が走ることを検証する。
        repo.ensure_collection(COLL_B)

        result = orch.run(
            target_collection=COLL_B,
            populate=_populate,
            sample_query_vectors=[],
            force_recreate=True,
        )

        assert result.swapped is True
        assert result.processed_count == 3
        assert admin.current_target(ALIAS) == COLL_B


class TestReadyzResolvesAliasChanges:
    """/readyz が alias の実在状態と連動する (Req 7.1 / 8.5)。"""

    def test_readyz_toggles_with_alias_delete_and_recreate(
        self, client: QdrantClient
    ) -> None:
        """/readyz と /healthz の alias 連動挙動を 1 テスト内で検証する。

        Note:
            同一 FastAPI TestClient を複数テストで再入すると anyio の
            lifespan タスク管理で RecursionError を起こすため、readiness の
            4 フェーズと liveness 非依存検証を単一テストにまとめる。失敗時の
            切り分けが楽になるよう、各 assertion にフェーズ識別メッセージを
            付ける。

        Phases:
            1. 初期 /readyz 200 + alias/collection の正しさ
            2. alias 削除 → /readyz 503
            3. alias 再作成 → /readyz 200
            4. alias 再削除中でも /healthz 200 (liveness 非依存)
        """
        from unittest.mock import MagicMock, patch

        from fastapi.testclient import TestClient

        # Qdrant 側: コレクション + alias を用意
        _create_collection(client, COLL_A)
        _upsert(client, COLL_A, "art-a1", "from A")
        _create_alias(client, ALIAS, COLL_A)

        # app の依存を差し替え: 実 Qdrant 接続を使い、その他は no-op
        from shared.qdrant import factory as real_factory

        # patch 対象と衝突しないよう、元関数への参照をローカルに捕捉しておく
        _original_build = real_factory.build_repository

        # qdrant_alias を ALIAS に上書きした Settings でファクトリを呼ぶ
        def _build(_settings):
            mock_settings = MagicMock()
            mock_settings.qdrant_host = QDRANT_HOST
            mock_settings.qdrant_port = QDRANT_PORT
            mock_settings.qdrant_alias = ALIAS
            mock_settings.qdrant_api_key = None
            mock_settings.vector_dim = VECTOR_DIM
            return _original_build(mock_settings)

        with patch(
            "shared.qdrant.factory.build_repository", side_effect=_build
        ), patch(
            "shared.logging.configure_logging"
        ):
            from services.search.app import app

            with TestClient(app) as tc:
                # --- Phase 1: 初期 /readyz 200 ---
                r1 = tc.get("/readyz")
                assert r1.status_code == 200, f"Phase 1 (initial readyz): {r1.text}"
                body1 = r1.json()
                assert body1["alias"] == ALIAS, "Phase 1 (alias label)"
                assert (
                    body1["collection"] == COLL_A
                ), f"Phase 1 (collection): {body1!r}"

                # --- Phase 2: alias 削除 → /readyz 503 ---
                client.update_collection_aliases(
                    change_aliases_operations=[
                        DeleteAliasOperation(
                            delete_alias=DeleteAlias(alias_name=ALIAS)
                        )
                    ]
                )
                r2 = tc.get("/readyz")
                assert r2.status_code == 503, (
                    f"Phase 2 (alias deleted, expected 503): {r2.status_code}"
                )

                # --- Phase 3: alias 再作成 → /readyz 200 ---
                client.update_collection_aliases(
                    change_aliases_operations=[
                        CreateAliasOperation(
                            create_alias=CreateAlias(
                                alias_name=ALIAS, collection_name=COLL_A
                            )
                        )
                    ]
                )
                r3 = tc.get("/readyz")
                assert r3.status_code == 200, (
                    f"Phase 3 (alias recreated): {r3.text}"
                )
                assert (
                    r3.json()["collection"] == COLL_A
                ), "Phase 3 (collection after recreate)"

                # --- Phase 4: /healthz は alias 状態非依存で常に 200 ---
                assert (
                    tc.get("/healthz").status_code == 200
                ), "Phase 4a (healthz with alias present)"
                client.update_collection_aliases(
                    change_aliases_operations=[
                        DeleteAliasOperation(
                            delete_alias=DeleteAlias(alias_name=ALIAS)
                        )
                    ]
                )
                assert (
                    tc.get("/healthz").status_code == 200
                ), "Phase 4b (healthz after alias deleted)"

