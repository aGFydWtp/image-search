"""統合テスト。

実コンポーネントを結合し、外部サービス（VLM/SigLIP2/Qdrant）のみモックして
パイプライン全体の動作を検証する。
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from shared.models.vlm import VLMExtractionResult
from shared.qdrant.repository import SearchResult


def _make_test_image(width: int = 400, height: int = 300) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 200, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
# IngestionService 統合テスト
# 実コンポーネント: ImagePreprocessor, ColorExtractor, TaxonomyMapper
# モック: VLMClient, EmbeddingClient, QdrantRepository
# ──────────────────────────────────────────────────────────────

class TestIngestionServiceIntegration:
    """IngestionService の統合テスト: 実前処理+色抽出+Taxonomy、モックVLM/Embed/Qdrant。"""

    def test_full_pipeline_with_real_preprocessor_and_color(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor
        from services.ingestion.image_preprocessor import ImagePreprocessor
        from services.ingestion.pipeline import IngestionService
        from shared.taxonomy.mapper import TaxonomyMapper

        vlm = MagicMock()
        vlm.extract_metadata.return_value = VLMExtractionResult(
            caption="A green field under blue sky",
            motif_candidates=["field", "sky"],
            style_candidates=["realism"],
            subject_candidates=["landscape"],
            mood_candidates=["calm", "peaceful"],
        )

        embedding = MagicMock()
        embedding.embed_image.return_value = [0.1] * 1152
        embedding.embed_text.return_value = [0.2] * 1152

        qdrant = MagicMock()

        svc = IngestionService(
            vlm_client=vlm,
            embedding_client=embedding,
            qdrant_repo=qdrant,
            preprocessor=ImagePreprocessor(),
            color_extractor=ColorExtractor(),
            taxonomy_mapper=TaxonomyMapper(),
        )

        result = svc.process_artwork(
            artwork_id="int-001",
            image_bytes=_make_test_image(),
            image_url="https://example.com/int-001.jpg",
            title="Green Field",
            artist_name="Tester",
        )

        assert result is True

        # Qdrant upsert が呼ばれたことを検証
        qdrant.upsert_artwork.assert_called_once()
        call_kwargs = qdrant.upsert_artwork.call_args.kwargs

        # Payload のフィールド検証
        payload = call_kwargs["payload"]
        assert payload.artwork_id == "int-001"
        assert payload.caption == "A green field under blue sky"
        assert "calm" in payload.mood_tags  # TaxonomyMapper が "peaceful" → "calm" に正規化
        assert "field" in payload.motif_tags
        assert "sky" in payload.motif_tags
        assert payload.taxonomy_version == "v1"

        # ColorExtractor の実結果が反映
        assert len(payload.color_tags) > 0
        assert 0.0 <= payload.brightness_score <= 1.0
        assert 0.0 <= payload.saturation_score <= 1.0

        # ベクトルが渡された
        assert len(call_kwargs["image_vector"]) == 1152
        assert len(call_kwargs["text_vector"]) == 1152

    def test_vlm_failure_skips_artwork(self) -> None:
        from services.ingestion.color_extractor import ColorExtractor
        from services.ingestion.image_preprocessor import ImagePreprocessor
        from services.ingestion.pipeline import IngestionService
        from shared.clients.vlm import VLMExtractionError
        from shared.taxonomy.mapper import TaxonomyMapper

        vlm = MagicMock()
        vlm.extract_metadata.side_effect = VLMExtractionError("model timeout")

        embedding = MagicMock()
        embedding.embed_image.return_value = [0.1] * 1152
        qdrant = MagicMock()

        svc = IngestionService(
            vlm_client=vlm,
            embedding_client=embedding,
            qdrant_repo=qdrant,
            preprocessor=ImagePreprocessor(),
            color_extractor=ColorExtractor(),
            taxonomy_mapper=TaxonomyMapper(),
        )

        result = svc.process_artwork(
            artwork_id="int-fail",
            image_bytes=_make_test_image(),
            image_url="https://example.com/fail.jpg",
            title="Fail",
            artist_name="A",
        )

        assert result is False
        qdrant.upsert_artwork.assert_not_called()


# ──────────────────────────────────────────────────────────────
# SearchService 統合テスト
# 実コンポーネント: QueryParser, Reranker
# モック: EmbeddingClient, QdrantRepository
# ──────────────────────────────────────────────────────────────

class TestSearchServiceIntegration:
    """SearchService の統合テスト: 実QueryParser+Reranker、モックEmbed/Qdrant。"""

    def test_japanese_query_end_to_end(self) -> None:
        from services.search.query_parser import QueryParser
        from services.search.reranker import Reranker

        embedding = MagicMock()
        embedding.embed_text.return_value = [0.1] * 1152

        qdrant = MagicMock()
        qdrant.search.return_value = [
            SearchResult(
                artwork_id="art-001",
                title="Sky Painting",
                artist_name="Artist A",
                thumbnail_url="https://example.com/a.jpg",
                score=0.92,
                payload={
                    "motif_tags": ["sky", "sea"],
                    "color_tags": ["blue", "green"],
                    "brightness_score": 0.7,
                },
            ),
            SearchResult(
                artwork_id="art-002",
                title="Forest",
                artist_name="Artist B",
                thumbnail_url="https://example.com/b.jpg",
                score=0.85,
                payload={
                    "motif_tags": ["tree"],
                    "color_tags": ["green"],
                    "brightness_score": 0.4,
                },
            ),
        ]

        with (
            patch("services.search.app._query_parser", QueryParser()),
            patch("services.search.app._embedding_client", embedding),
            patch("services.search.app._qdrant_repo", qdrant),
            patch("services.search.app._reranker", Reranker()),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/artworks/search",
                json={"query": "穏やかな青い空と海のある絵", "limit": 10},
            )

        assert response.status_code == 200
        data = response.json()

        # QueryParser が日本語を正しく分解
        pq = data["parsed_query"]
        assert "blue" in pq["filters"]["color_tags"]
        assert "sky" in pq["filters"]["motif_tags"]
        assert "sea" in pq["filters"]["motif_tags"]

        # Qdrant にフィルタが渡された
        call_kwargs = qdrant.search.call_args.kwargs
        assert call_kwargs["filters"].motif_tags == ["sky", "sea"]
        assert call_kwargs["filters"].color_tags == ["blue"]
        assert call_kwargs["limit"] == 10

        # Reranker がスコア合成してソート
        items = data["items"]
        assert len(items) == 2
        assert items[0]["artwork_id"] == "art-001"  # motif+color一致でブースト
        assert len(items[0]["match_reasons"]) > 0

    def test_pure_mood_query(self) -> None:
        """ムードのみクエリ: フィルタなし、semantic searchのみ。"""
        from services.search.query_parser import QueryParser
        from services.search.reranker import Reranker

        embedding = MagicMock()
        embedding.embed_text.return_value = [0.1] * 1152

        qdrant = MagicMock()
        qdrant.search.return_value = [
            SearchResult("art-001", "Calm", "A", "url", 0.9,
                         {"motif_tags": [], "color_tags": [], "brightness_score": 0.5}),
        ]

        with (
            patch("services.search.app._query_parser", QueryParser()),
            patch("services.search.app._embedding_client", embedding),
            patch("services.search.app._qdrant_repo", qdrant),
            patch("services.search.app._reranker", Reranker()),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/artworks/search", json={"query": "穏やかな雰囲気"})

        assert response.status_code == 200
        call_kwargs = qdrant.search.call_args.kwargs
        assert call_kwargs["filters"] is None  # フィルタなし


# ──────────────────────────────────────────────────────────────
# API エンドポイント統合テスト
# ──────────────────────────────────────────────────────────────

class TestAPIEndpointIntegration:
    """FastAPI TestClient を使った API 統合テスト。"""

    def test_search_response_schema(self) -> None:
        """SearchResponse の全フィールドが正しい型で返る。"""
        from services.search.query_parser import QueryParser
        from services.search.reranker import Reranker

        embedding = MagicMock()
        embedding.embed_text.return_value = [0.1] * 1152

        qdrant = MagicMock()
        qdrant.search.return_value = [
            SearchResult("art-001", "Title", "Artist", "https://example.com/t.jpg", 0.9,
                         {"motif_tags": ["sky"], "color_tags": ["blue"], "brightness_score": 0.7}),
        ]

        with (
            patch("services.search.app._query_parser", QueryParser()),
            patch("services.search.app._embedding_client", embedding),
            patch("services.search.app._qdrant_repo", qdrant),
            patch("services.search.app._reranker", Reranker()),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/api/artworks/search", json={"query": "青い空"})

        data = response.json()
        # Schema validation
        assert isinstance(data["parsed_query"]["semantic_query"], str)
        assert isinstance(data["parsed_query"]["filters"]["motif_tags"], list)
        assert isinstance(data["parsed_query"]["filters"]["color_tags"], list)
        assert isinstance(data["items"], list)
        item = data["items"][0]
        assert isinstance(item["artwork_id"], str)
        assert isinstance(item["title"], str)
        assert isinstance(item["score"], float)
        assert isinstance(item["match_reasons"], list)

    def test_index_endpoint_integration(self) -> None:
        """POST /internal/artworks/index の統合テスト。"""
        ingestion_svc = MagicMock()
        ingestion_svc.process_artwork.return_value = True

        qdrant = MagicMock()
        qdrant.exists.return_value = False

        http_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_test_image()
        mock_resp.raise_for_status = MagicMock()
        http_client.get.return_value = mock_resp

        with (
            patch("services.search.app._ingestion_service", ingestion_svc),
            patch("services.search.app._qdrant_repo", qdrant),
            patch("services.search.app._index_http_client", http_client),
        ):
            from services.search.app import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/internal/artworks/index", json={
                "artwork_id": "int-test",
                "image_url": "https://example.com/test.jpg",
                "title": "Integration Test",
                "artist_name": "Tester",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["artwork_id"] == "int-test"
        assert data["status"] == "created"

        # パイプラインに画像バイトが渡された
        call_kwargs = ingestion_svc.process_artwork.call_args.kwargs
        assert isinstance(call_kwargs["image_bytes"], bytes)
        assert len(call_kwargs["image_bytes"]) > 0


# ──────────────────────────────────────────────────────────────
# QdrantRepository 統合テスト（Qdrant稼働時のみ実行）
# ──────────────────────────────────────────────────────────────

def _qdrant_available() -> bool:
    """Qdrant がローカルで稼働しているか確認する。"""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host="localhost", port=6333, timeout=2)
        client.get_collections()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _qdrant_available(), reason="Qdrant not running")
class TestQdrantRepositoryIntegration:
    """QdrantRepository の統合テスト（実Qdrantコンテナ使用）。"""

    def _make_repo(self):
        from qdrant_client import QdrantClient

        from shared.config import Settings
        from shared.qdrant.repository import QdrantRepository

        settings = Settings(qdrant_collection="test_artworks_integration")
        client = QdrantClient(host="localhost", port=6333)
        repo = QdrantRepository(client=client, settings=settings)
        # テスト用コレクション作成
        repo.ensure_collection()
        return repo, client, settings

    def _cleanup(self, client, collection: str) -> None:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    def test_upsert_and_exists(self) -> None:
        from datetime import datetime, timezone

        from shared.models.artwork import ArtworkPayload

        repo, client, settings = self._make_repo()
        try:
            payload = ArtworkPayload(
                artwork_id="qdrant-int-001",
                title="Integration Test",
                artist_name="Tester",
                image_url="https://example.com/img.jpg",
                thumbnail_url="https://example.com/thumb.jpg",
                caption="A test artwork",
                mood_tags=["calm"],
                motif_tags=["sky"],
                style_tags=[],
                subject_tags=["landscape"],
                color_tags=["blue"],
                palette_hex=["#0000FF"],
                brightness_score=0.7,
                saturation_score=0.5,
                warmth_score=0.4,
                is_abstract=False,
                has_character=False,
                taxonomy_version="v1",
                ingested_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            repo.upsert_artwork(
                artwork_id="qdrant-int-001",
                image_vector=[0.1] * 1152,
                text_vector=[0.2] * 1152,
                payload=payload,
            )

            assert repo.exists("qdrant-int-001") is True
            assert repo.exists("nonexistent") is False
        finally:
            self._cleanup(client, settings.qdrant_collection)

    def test_search_returns_results(self) -> None:
        from datetime import datetime, timezone

        from shared.models.artwork import ArtworkPayload

        repo, client, settings = self._make_repo()
        try:
            payload = ArtworkPayload(
                artwork_id="qdrant-int-002",
                title="Searchable Art",
                artist_name="Tester",
                image_url="https://example.com/img.jpg",
                thumbnail_url="https://example.com/thumb.jpg",
                caption="Calm blue sky",
                mood_tags=["calm"],
                motif_tags=["sky"],
                style_tags=[],
                subject_tags=[],
                color_tags=["blue"],
                palette_hex=["#0000FF"],
                brightness_score=0.8,
                saturation_score=0.6,
                warmth_score=0.3,
                is_abstract=False,
                has_character=False,
                taxonomy_version="v1",
                ingested_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            repo.upsert_artwork(
                artwork_id="qdrant-int-002",
                image_vector=[0.1] * 1152,
                text_vector=[0.2] * 1152,
                payload=payload,
            )

            results = repo.search(
                query_vector=[0.2] * 1152,
                filters=None,
                limit=5,
            )

            assert len(results) >= 1
            assert results[0].artwork_id == "qdrant-int-002"
        finally:
            self._cleanup(client, settings.qdrant_collection)
