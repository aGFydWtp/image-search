"""Ingestion Service エントリポイント（バッチ実行用）。"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient

from shared.clients.embedding import EmbeddingClient
from shared.clients.vlm import VLMClient
from shared.config import Settings
from shared.qdrant.repository import QdrantRepository
from shared.qdrant.resolver import CollectionResolver
from shared.taxonomy.mapper import TaxonomyMapper

from services.ingestion.batch import BatchLogger
from services.ingestion.color_extractor import ColorExtractor
from services.ingestion.firebase_storage import FirebaseStorageClient
from services.ingestion.image_preprocessor import ImagePreprocessor
from services.ingestion.pipeline import IngestionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class BatchRunner:
    """Firebase Storage から画像を取得し、バッチでインジェスションを実行する。"""

    def __init__(self) -> None:
        settings = Settings()
        self._prefix = settings.firebase_storage_prefix

        self._firebase = FirebaseStorageClient(
            credentials_path=settings.firebase_credentials_path,
            bucket_name=settings.firebase_storage_bucket,
        )

        vlm_client = VLMClient(settings=settings)
        embedding_client = EmbeddingClient(settings=settings)
        qdrant_client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        resolver = CollectionResolver(
            client=qdrant_client, alias_name=settings.qdrant_alias
        )
        self._qdrant = QdrantRepository(
            client=qdrant_client, resolver=resolver, vector_dim=settings.vector_dim
        )
        self._physical_collection = settings.qdrant_collection
        preprocessor = ImagePreprocessor()
        color_extractor = ColorExtractor()
        taxonomy_mapper = TaxonomyMapper()

        self._ingestion = IngestionService(
            vlm_client=vlm_client,
            embedding_client=embedding_client,
            qdrant_repo=self._qdrant,
            preprocessor=preprocessor,
            color_extractor=color_extractor,
            taxonomy_mapper=taxonomy_mapper,
        )
        self._batch_logger = BatchLogger()

    def execute(self) -> dict[str, Any]:
        """バッチインジェスションを実行し、サマリーを返す。"""
        self._qdrant.ensure_collection(self._physical_collection)
        blob_paths = self._firebase.list_images(prefix=self._prefix)
        self._batch_logger.start(len(blob_paths))

        for blob_path in blob_paths:
            artwork_id = FirebaseStorageClient.extract_artwork_id(blob_path)

            # 既にインデックス済みならスキップ
            if self._qdrant.exists(artwork_id):
                logger.info("Skipping already indexed: %s", artwork_id)
                continue

            try:
                image_bytes = self._firebase.download_image(blob_path)
            except Exception as e:
                logger.error("Download failed for %s: %s", artwork_id, e)
                self._batch_logger.record_error(artwork_id, str(e))
                continue

            image_url = self._firebase.get_public_url(blob_path)

            success = self._ingestion.process_artwork(
                artwork_id=artwork_id,
                image_bytes=image_bytes,
                image_url=image_url,
                title=artwork_id,
                artist_name="Unknown",
            )

            if success:
                self._batch_logger.record_success()
            else:
                self._batch_logger.record_error(artwork_id, "pipeline returned False")

        self._batch_logger.finish()
        return self._batch_logger.summary()


def main() -> None:
    runner = BatchRunner()
    summary = runner.execute()
    logger.info("Batch summary: %s", summary)


if __name__ == "__main__":
    main()
