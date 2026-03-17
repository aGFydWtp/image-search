"""IngestionService: インジェスションパイプラインの統括。"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from shared.clients.embedding import EmbeddingClient, EmbeddingError
from shared.clients.vlm import DEFAULT_EXTRACTION_PROMPT, VLMClient, VLMExtractionError
from shared.models.artwork import ArtworkPayload
from shared.models.color import ColorInfo
from shared.models.vlm import VLMExtractionResult
from shared.qdrant.repository import QdrantRepository

logger = logging.getLogger(__name__)


class IngestionService:
    """画像取得→前処理→VLM+色抽出→Taxonomy→埋め込み→Qdrant保存のパイプライン。"""

    def __init__(
        self,
        vlm_client: VLMClient,
        embedding_client: EmbeddingClient,
        qdrant_repo: QdrantRepository,
        preprocessor,
        color_extractor,
        taxonomy_mapper,
    ) -> None:
        self._vlm = vlm_client
        self._embedding = embedding_client
        self._qdrant = qdrant_repo
        self._preprocessor = preprocessor
        self._color_extractor = color_extractor
        self._taxonomy = taxonomy_mapper

    def process_artwork(
        self,
        artwork_id: str,
        image_bytes: bytes,
        image_url: str,
        title: str,
        artist_name: str,
    ) -> bool:
        """単一アートワークのインジェスションパイプラインを実行する。

        Returns:
            True: 正常完了, False: エラーでスキップ
        """
        try:
            return self._run_pipeline(artwork_id, image_bytes, image_url, title, artist_name)
        except (VLMExtractionError, EmbeddingError) as e:
            logger.error("Pipeline failed for %s: %s", artwork_id, e)
            return False
        except Exception as e:
            logger.error("Unexpected error for %s: %s", artwork_id, e)
            return False

    def _run_pipeline(
        self,
        artwork_id: str,
        image_bytes: bytes,
        image_url: str,
        title: str,
        artist_name: str,
    ) -> bool:
        # 1. 前処理
        preprocessed = self._preprocessor.process(image_bytes)

        # 2. VLM推論 + 画像埋め込み + 色抽出（並列）
        vlm_result: VLMExtractionResult | None = None
        image_vector: list[float] | None = None
        color_info: ColorInfo | None = None

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self._vlm.extract_metadata, preprocessed.normalized, DEFAULT_EXTRACTION_PROMPT
                ): "vlm",
                executor.submit(self._embedding.embed_image, preprocessed.normalized): "embed_image",
                executor.submit(self._color_extractor.extract, image_bytes): "color",
            }

            for future in as_completed(futures):
                key = futures[future]
                result = future.result()  # Raises if failed
                if key == "vlm":
                    vlm_result = result
                elif key == "embed_image":
                    image_vector = result
                elif key == "color":
                    color_info = result

        if vlm_result is None or image_vector is None or color_info is None:
            raise RuntimeError("Parallel execution failed: missing VLM, embedding, or color result")

        # 3. Taxonomy正規化
        normalized = self._taxonomy.normalize(vlm_result)

        # 4. テキスト埋め込み（キャプション確定後に逐次実行）
        text_vector = self._embedding.embed_text(vlm_result.caption)

        # 5. Payload構築
        now = datetime.now(timezone.utc)
        # color_tagsをTaxonomy結果にマージ
        normalized.color_tags = color_info.color_tags

        payload = ArtworkPayload(
            artwork_id=artwork_id,
            title=title,
            artist_name=artist_name,
            image_url=image_url,
            thumbnail_url=image_url,  # サムネイルURLは別途管理、暫定で同じURL
            caption=vlm_result.caption,
            mood_tags=normalized.mood_tags,
            motif_tags=normalized.motif_tags,
            style_tags=normalized.style_tags,
            subject_tags=normalized.subject_tags,
            color_tags=normalized.color_tags,
            palette_hex=color_info.palette_hex,
            brightness_score=color_info.brightness_score,
            saturation_score=color_info.saturation_score,
            warmth_score=color_info.warmth_score,
            is_abstract=False,
            has_character=False,
            taxonomy_version=normalized.taxonomy_version,
            ingested_at=now,
            updated_at=now,
        )

        # 6. Qdrant upsert
        self._qdrant.upsert_artwork(
            artwork_id=artwork_id,
            image_vector=image_vector,
            text_vector=text_vector,
            payload=payload,
        )

        logger.info("Successfully processed artwork %s", artwork_id)
        return True
