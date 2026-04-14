"""E2Eテスト: インジェスション→検索の一気通貫テスト。

ホスト側MLサービス（LM Studio + SigLIP2）と Qdrant が稼働している環境でのみ実行。
実行: pytest tests/test_e2e.py -v
"""

from pathlib import Path

import httpx
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# テスト画像セット: (ファイル名, artwork_id, title, artist_name)
_TEST_IMAGES = [
    ("blue_sky_green_field.jpg", "e2e-sky-field", "Blue Sky Green Field", "E2E Artist"),
    ("sunset_warm.jpg", "e2e-sunset", "Warm Sunset", "E2E Artist"),
    ("dark_forest.jpg", "e2e-dark-forest", "Dark Forest", "E2E Artist"),
    ("calm_ocean.jpg", "e2e-ocean", "Calm Ocean", "E2E Artist"),
    ("red_flowers_bright.jpg", "e2e-red-flowers", "Red Flowers", "E2E Artist"),
]

# 評価クエリセット: (クエリ, 期待されるartwork_idのいずれか)
_EVAL_QUERIES = [
    ("青い空", ["e2e-sky-field", "e2e-ocean"]),
    ("赤い花", ["e2e-red-flowers"]),
    ("暗い森", ["e2e-dark-forest"]),
    ("穏やかな海", ["e2e-ocean"]),
    ("温かい夕焼け", ["e2e-sunset"]),
    ("緑の風景", ["e2e-sky-field", "e2e-dark-forest"]),
    ("明るい花", ["e2e-red-flowers", "e2e-sky-field"]),
]


def _services_available() -> bool:
    """LM Studio, SigLIP2 embedding service, Qdrant が全て稼働しているか確認。"""
    try:
        # Qdrant
        r = httpx.get("http://localhost:6333/readyz", timeout=2)
        if r.status_code != 200:
            return False

        # SigLIP2 embedding service
        r = httpx.get("http://localhost:8100/health", timeout=2)
        if r.status_code != 200:
            return False

        # LM Studio
        r = httpx.get("http://localhost:1234/v1/models", timeout=2)
        if r.status_code != 200:
            return False

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _services_available(),
    reason="E2E: LM Studio, SigLIP2, and Qdrant must all be running",
)


@pytest.fixture(scope="module")
def e2e_setup():
    """E2Eテスト用のサービスとコレクションをセットアップする。"""
    from qdrant_client import QdrantClient

    from services.ingestion.color_extractor import ColorExtractor
    from services.ingestion.image_preprocessor import ImagePreprocessor
    from services.ingestion.pipeline import IngestionService
    from services.search.query_parser import QueryParser
    from services.search.reranker import Reranker
    from shared.clients.embedding import EmbeddingClient
    from shared.clients.vlm import VLMClient
    from shared.config import Settings
    from shared.qdrant.repository import QdrantRepository
    from shared.qdrant.resolver import CollectionResolver
    from shared.taxonomy.mapper import TaxonomyMapper

    settings = Settings(
        qdrant_collection="e2e_test_artworks",
        qdrant_alias="e2e_test_artworks_alias",
    )

    from qdrant_client.models import CreateAlias, CreateAliasOperation

    qdrant_client = QdrantClient(host="localhost", port=6333)
    resolver = CollectionResolver(client=qdrant_client, alias_name=settings.qdrant_alias)
    qdrant_repo = QdrantRepository(
        client=qdrant_client, resolver=resolver, vector_dim=settings.vector_dim
    )
    qdrant_repo.ensure_collection(settings.qdrant_collection)
    existing_aliases = {a.alias_name for a in qdrant_client.get_aliases().aliases}
    if settings.qdrant_alias not in existing_aliases:
        qdrant_client.update_collection_aliases(
            change_aliases_operations=[
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        alias_name=settings.qdrant_alias,
                        collection_name=settings.qdrant_collection,
                    )
                )
            ]
        )

    vlm = VLMClient(settings=settings)
    embedding = EmbeddingClient(settings=settings)

    ingestion = IngestionService(
        vlm_client=vlm,
        embedding_client=embedding,
        qdrant_repo=qdrant_repo,
        preprocessor=ImagePreprocessor(),
        color_extractor=ColorExtractor(),
        taxonomy_mapper=TaxonomyMapper(),
    )

    query_parser = QueryParser()
    reranker = Reranker()

    yield {
        "ingestion": ingestion,
        "qdrant_repo": qdrant_repo,
        "embedding": embedding,
        "query_parser": query_parser,
        "reranker": reranker,
        "vlm": vlm,
    }

    # Cleanup
    vlm.close()
    embedding.close()
    try:
        qdrant_client.delete_collection("e2e_test_artworks")
    except Exception:
        pass


class TestE2EIngestion:
    """E2E インジェスションテスト。"""

    def test_ingest_all_test_images(self, e2e_setup) -> None:
        """全テスト画像をインジェストする。"""
        ingestion = e2e_setup["ingestion"]
        success_count = 0

        for filename, artwork_id, title, artist in _TEST_IMAGES:
            image_path = FIXTURE_DIR / filename
            assert image_path.exists(), f"Fixture not found: {image_path}"

            image_bytes = image_path.read_bytes()
            result = ingestion.process_artwork(
                artwork_id=artwork_id,
                image_bytes=image_bytes,
                image_url=f"https://example.com/{filename}",
                title=title,
                artist_name=artist,
            )

            if result:
                success_count += 1

        assert success_count == len(_TEST_IMAGES), f"Only {success_count}/{len(_TEST_IMAGES)} ingested"

    def test_all_artworks_exist_in_qdrant(self, e2e_setup) -> None:
        """インジェスト後、全artwork_idがQdrantに存在する。"""
        qdrant_repo = e2e_setup["qdrant_repo"]

        for _, artwork_id, _, _ in _TEST_IMAGES:
            assert qdrant_repo.exists(artwork_id), f"{artwork_id} not found in Qdrant"


class TestE2ESearch:
    """E2E 検索テスト。"""

    def test_search_returns_results(self, e2e_setup) -> None:
        """基本検索が結果を返す（フィルタなし）。"""
        qdrant_repo = e2e_setup["qdrant_repo"]
        embedding = e2e_setup["embedding"]

        query_vector = embedding.embed_text("青い空")
        candidates = qdrant_repo.search(
            query_vector=query_vector,
            filters=None,
            limit=5,
        )

        assert len(candidates) > 0, "No results returned even without filters"

    @pytest.mark.parametrize("query,expected_ids", _EVAL_QUERIES)
    def test_recall_at_k(self, e2e_setup, query: str, expected_ids: list[str]) -> None:
        """評価クエリセットに対するrecall@5を測定する（セマンティック検索のみ）。"""
        qdrant_repo = e2e_setup["qdrant_repo"]
        embedding = e2e_setup["embedding"]
        reranker = e2e_setup["reranker"]
        query_parser = e2e_setup["query_parser"]

        k = 5  # 5件中から探す（テスト画像は5枚のみ）

        parsed = query_parser.parse(query)
        query_vector = embedding.embed_text(parsed.semantic_query)

        # フィルタなしでセマンティック検索（ベクトル類似度のみ）
        candidates = qdrant_repo.search(
            query_vector=query_vector,
            filters=None,
            limit=k,
        )

        ranked = reranker.rerank(candidates, parsed)
        result_ids = [item.artwork_id for item in ranked[:k]]

        # recall@k: 期待IDのうち少なくとも1つがtop-kに含まれる
        hits = [eid for eid in expected_ids if eid in result_ids]

        assert len(hits) > 0, (
            f"Query '{query}': expected any of {expected_ids} in top-{k}, "
            f"got {result_ids}"
        )
