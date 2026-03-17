"""IngestionService パイプライン統合テスト。

全依存をモックして、パイプラインのオーケストレーションを検証する。
"""

from io import BytesIO
from unittest.mock import MagicMock

from PIL import Image

from shared.models.color import ColorInfo
from shared.models.preprocessing import PreprocessedImage
from shared.models.taxonomy import NormalizedTags
from shared.models.vlm import VLMExtractionResult


def _make_image_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_vlm_result() -> VLMExtractionResult:
    return VLMExtractionResult(
        caption="A calm sunset",
        motif_candidates=["sky", "sea"],
        style_candidates=["impressionism"],
        subject_candidates=["landscape"],
        mood_candidates=["calm"],
    )


def _make_color_info() -> ColorInfo:
    return ColorInfo(
        color_tags=["orange", "blue"],
        palette_hex=["#FF8C00", "#4682B4"],
        brightness_score=0.7,
        saturation_score=0.6,
        warmth_score=0.8,
    )


def _make_normalized_tags() -> NormalizedTags:
    return NormalizedTags(
        mood_tags=["calm"],
        motif_tags=["sky", "sea"],
        style_tags=["impressionism"],
        subject_tags=["landscape"],
        color_tags=["orange", "blue"],
        taxonomy_version="v1",
    )


def _make_preprocessed() -> PreprocessedImage:
    return PreprocessedImage(
        normalized=_make_image_bytes(),
        thumbnail=_make_image_bytes(),
        width=100,
        height=100,
        aspect_ratio=1.0,
    )


def _make_vector(val: float = 0.1) -> list[float]:
    return [val] * 1152


def _mock_dependencies():
    """全依存をモックしたdictを返す。"""
    vlm = MagicMock()
    vlm.extract_metadata.return_value = _make_vlm_result()

    embedding = MagicMock()
    embedding.embed_image.return_value = _make_vector(0.1)
    embedding.embed_text.return_value = _make_vector(0.2)

    qdrant = MagicMock()
    qdrant.exists.return_value = False

    preprocessor = MagicMock()
    preprocessor.process.return_value = _make_preprocessed()

    color_extractor = MagicMock()
    color_extractor.extract.return_value = _make_color_info()

    taxonomy = MagicMock()
    taxonomy.normalize.return_value = _make_normalized_tags()

    return {
        "vlm_client": vlm,
        "embedding_client": embedding,
        "qdrant_repo": qdrant,
        "preprocessor": preprocessor,
        "color_extractor": color_extractor,
        "taxonomy_mapper": taxonomy,
    }


class TestIngestionServiceProcessArtwork:
    """IngestionService.process_artwork() のテスト。"""

    def test_full_pipeline_succeeds(self) -> None:
        from services.ingestion.pipeline import IngestionService

        deps = _mock_dependencies()
        svc = IngestionService(**deps)

        result = svc.process_artwork(
            artwork_id="art-001",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/art-001.jpg",
            title="Sunset",
            artist_name="Artist",
        )

        assert result is True
        deps["preprocessor"].process.assert_called_once()
        deps["vlm_client"].extract_metadata.assert_called_once()
        deps["color_extractor"].extract.assert_called_once()
        deps["taxonomy_mapper"].normalize.assert_called_once()
        deps["embedding_client"].embed_image.assert_called_once()
        deps["embedding_client"].embed_text.assert_called_once()
        deps["qdrant_repo"].upsert_artwork.assert_called_once()

    def test_upsert_called_with_correct_artwork_id(self) -> None:
        from services.ingestion.pipeline import IngestionService

        deps = _mock_dependencies()
        svc = IngestionService(**deps)

        svc.process_artwork(
            artwork_id="art-042",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/art-042.jpg",
            title="Forest",
            artist_name="Painter",
        )

        call_kwargs = deps["qdrant_repo"].upsert_artwork.call_args.kwargs
        assert call_kwargs["artwork_id"] == "art-042"

    def test_vlm_and_embedding_both_called(self) -> None:
        from services.ingestion.pipeline import IngestionService

        deps = _mock_dependencies()
        svc = IngestionService(**deps)

        svc.process_artwork(
            artwork_id="art-001",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/img.jpg",
            title="T",
            artist_name="A",
        )

        # VLM called with normalized image
        deps["vlm_client"].extract_metadata.assert_called_once()
        # Image embedding called
        deps["embedding_client"].embed_image.assert_called_once()
        # Text embedding called after caption ready
        deps["embedding_client"].embed_text.assert_called_once()

    def test_text_embedding_uses_caption(self) -> None:
        from services.ingestion.pipeline import IngestionService

        deps = _mock_dependencies()
        svc = IngestionService(**deps)

        svc.process_artwork(
            artwork_id="art-001",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/img.jpg",
            title="T",
            artist_name="A",
        )

        text_arg = deps["embedding_client"].embed_text.call_args.args[0]
        assert "calm sunset" in text_arg.lower()


class TestIngestionServiceErrorHandling:
    """エラーハンドリングのテスト。"""

    def test_vlm_failure_returns_false(self) -> None:
        from services.ingestion.pipeline import IngestionService
        from shared.clients.vlm import VLMExtractionError

        deps = _mock_dependencies()
        deps["vlm_client"].extract_metadata.side_effect = VLMExtractionError("VLM down")
        svc = IngestionService(**deps)

        result = svc.process_artwork(
            artwork_id="art-fail",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/fail.jpg",
            title="T",
            artist_name="A",
        )

        assert result is False
        deps["qdrant_repo"].upsert_artwork.assert_not_called()

    def test_embedding_failure_returns_false(self) -> None:
        from services.ingestion.pipeline import IngestionService
        from shared.clients.embedding import EmbeddingError

        deps = _mock_dependencies()
        deps["embedding_client"].embed_image.side_effect = EmbeddingError("SigLIP2 down")
        svc = IngestionService(**deps)

        result = svc.process_artwork(
            artwork_id="art-fail",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/fail.jpg",
            title="T",
            artist_name="A",
        )

        assert result is False
        deps["qdrant_repo"].upsert_artwork.assert_not_called()


class TestIngestionServicePayload:
    """Qdrant payloadの構築テスト。"""

    def test_payload_contains_all_required_fields(self) -> None:
        from services.ingestion.pipeline import IngestionService

        deps = _mock_dependencies()
        svc = IngestionService(**deps)

        svc.process_artwork(
            artwork_id="art-001",
            image_bytes=_make_image_bytes(),
            image_url="https://example.com/img.jpg",
            title="Sunset",
            artist_name="Artist",
        )

        call_kwargs = deps["qdrant_repo"].upsert_artwork.call_args.kwargs
        payload = call_kwargs["payload"]

        assert payload.artwork_id == "art-001"
        assert payload.title == "Sunset"
        assert payload.artist_name == "Artist"
        assert payload.caption == "A calm sunset"
        assert payload.mood_tags == ["calm"]
        assert payload.motif_tags == ["sky", "sea"]
        assert payload.color_tags == ["orange", "blue"]
        assert payload.brightness_score == 0.7
        assert payload.taxonomy_version == "v1"
