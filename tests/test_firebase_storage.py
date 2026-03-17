"""Firebase Storage連携とバッチ処理基盤のテスト。"""

import json
import logging
from unittest.mock import MagicMock, patch

_FB_PATCH = {
    "admin": "services.ingestion.firebase_storage.firebase_admin",
    "creds": "services.ingestion.firebase_storage.fb_credentials",
    "storage": "services.ingestion.firebase_storage.fb_storage",
}


class _MockFirebase:  # noqa: N801
    """firebase_admin, fb_credentials, fb_storage をまとめてモックするコンテキストマネージャ。"""

    def __enter__(self):
        self._p_admin = patch(_FB_PATCH["admin"])
        self._p_creds = patch(_FB_PATCH["creds"])
        self._p_storage = patch(_FB_PATCH["storage"])
        admin = self._p_admin.__enter__()
        creds = self._p_creds.__enter__()
        storage = self._p_storage.__enter__()
        return admin, creds, storage

    def __exit__(self, *args):
        self._p_storage.__exit__(*args)
        self._p_creds.__exit__(*args)
        self._p_admin.__exit__(*args)


class TestFirebaseStorageClient:
    """FirebaseStorageClient のテスト。"""

    def test_init_initializes_firebase(self) -> None:
        from services.ingestion.firebase_storage import FirebaseStorageClient

        with _MockFirebase() as (mock_admin, mock_creds, mock_storage):
            mock_admin.get_app.side_effect = ValueError("not initialized")
            mock_bucket = MagicMock()
            mock_storage.bucket.return_value = mock_bucket

            FirebaseStorageClient(
                credentials_path="/tmp/creds.json",
                bucket_name="test-bucket",
            )

            mock_admin.initialize_app.assert_called_once()
            mock_creds.Certificate.assert_called_once_with("/tmp/creds.json")

    def test_init_reuses_existing_app(self) -> None:
        from services.ingestion.firebase_storage import FirebaseStorageClient

        with _MockFirebase() as (mock_admin, mock_creds, mock_storage):
            mock_admin.get_app.return_value = MagicMock()
            mock_storage.bucket.return_value = MagicMock()

            FirebaseStorageClient(
                credentials_path="/tmp/creds.json",
                bucket_name="test-bucket",
            )

            mock_admin.initialize_app.assert_not_called()

    def test_list_images_returns_blob_names(self) -> None:
        from services.ingestion.firebase_storage import FirebaseStorageClient

        with _MockFirebase() as (mock_admin, mock_creds, mock_storage):
            mock_admin.get_app.return_value = MagicMock()
            mock_bucket = MagicMock()
            mock_storage.bucket.return_value = mock_bucket

            blob1 = MagicMock()
            blob1.name = "artworks/art-001.jpg"
            blob2 = MagicMock()
            blob2.name = "artworks/art-002.png"
            blob3 = MagicMock()
            blob3.name = "artworks/readme.txt"
            mock_bucket.list_blobs.return_value = [blob1, blob2, blob3]

            client = FirebaseStorageClient(
                credentials_path="/tmp/creds.json",
                bucket_name="test-bucket",
            )
            images = client.list_images(prefix="artworks/")

            assert len(images) == 2
            assert "artworks/art-001.jpg" in images
            assert "artworks/art-002.png" in images

    def test_download_image_returns_bytes(self) -> None:
        from services.ingestion.firebase_storage import FirebaseStorageClient

        with _MockFirebase() as (mock_admin, mock_creds, mock_storage):
            mock_admin.get_app.return_value = MagicMock()
            mock_bucket = MagicMock()
            mock_storage.bucket.return_value = mock_bucket

            mock_blob = MagicMock()
            mock_blob.download_as_bytes.return_value = b"\x89PNG\r\n\x1a\n"
            mock_bucket.blob.return_value = mock_blob

            client = FirebaseStorageClient(
                credentials_path="/tmp/creds.json",
                bucket_name="test-bucket",
            )
            data = client.download_image("artworks/art-001.jpg")

            assert data == b"\x89PNG\r\n\x1a\n"

    def test_get_public_url(self) -> None:
        from services.ingestion.firebase_storage import FirebaseStorageClient

        with _MockFirebase() as (mock_admin, mock_creds, mock_storage):
            mock_admin.get_app.return_value = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.name = "test-bucket"
            mock_storage.bucket.return_value = mock_bucket

            client = FirebaseStorageClient(
                credentials_path="/tmp/creds.json",
                bucket_name="test-bucket",
            )
            url = client.get_public_url("artworks/art-001.jpg")

            assert "art-001.jpg" in url
            assert "test-bucket" in url

    def test_extract_artwork_id_from_path(self) -> None:
        from services.ingestion.firebase_storage import FirebaseStorageClient

        assert FirebaseStorageClient.extract_artwork_id("artworks/art-001.jpg") == "art-001"
        assert FirebaseStorageClient.extract_artwork_id("images/my_painting.png") == "my_painting"
        assert FirebaseStorageClient.extract_artwork_id("photo.webp") == "photo"


class TestBatchLogger:
    """バッチ処理ログのテスト。"""

    def test_log_start(self, caplog) -> None:
        from services.ingestion.batch import BatchLogger

        with caplog.at_level(logging.INFO):
            blog = BatchLogger()
            blog.start(total=10)

        assert any("start" in r.message.lower() for r in caplog.records)

    def test_log_finish_includes_counts(self, caplog) -> None:
        from services.ingestion.batch import BatchLogger

        with caplog.at_level(logging.INFO):
            blog = BatchLogger()
            blog.start(total=10)
            blog.record_success()
            blog.record_success()
            blog.record_error("art-003", "VLM failed")
            blog.finish()

        finish_records = [r for r in caplog.records if "finish" in r.message.lower()]
        assert len(finish_records) == 1

    def test_summary_returns_counts(self) -> None:
        from services.ingestion.batch import BatchLogger

        blog = BatchLogger()
        blog.start(total=5)
        blog.record_success()
        blog.record_success()
        blog.record_error("art-003", "timeout")

        summary = blog.summary()
        assert summary["total"] == 5
        assert summary["processed"] == 2
        assert summary["errors"] == 1

    def test_structured_json_log(self) -> None:
        from services.ingestion.batch import BatchLogger

        blog = BatchLogger()
        blog.start(total=3)
        blog.record_success()
        blog.finish()

        summary = blog.summary()
        json_str = json.dumps(summary)
        parsed = json.loads(json_str)
        assert "total" in parsed
