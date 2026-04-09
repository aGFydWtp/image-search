"""Firebase Storage エミュレーターを使った統合テスト。

前提: firebase emulators:start --only storage が起動済み (ポート9199)
実行: pytest tests/test_firebase_emulator.py -v
"""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

# エミュレーター未起動時はスキップ
pytestmark = pytest.mark.skipif(
    not os.environ.get("FIREBASE_STORAGE_EMULATOR_HOST"),
    reason="FIREBASE_STORAGE_EMULATOR_HOST not set — firebase emulator not running",
)


def _make_test_image() -> bytes:
    """テスト用のPNG画像バイト列。"""
    img = Image.new("RGB", (50, 50), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def storage_client():
    """Firebase Storage エミュレーターに接続するクライアント。"""
    import firebase_admin
    import firebase_admin.storage as fb_storage

    # エミュレーター用のダミー設定で初期化
    try:
        app = firebase_admin.get_app("emulator_test")
    except ValueError:
        app = firebase_admin.initialize_app(
            None,
            {"storageBucket": "test-bucket"},
            name="emulator_test",
        )
    bucket = fb_storage.bucket(app=app)
    yield bucket

    # テスト後のクリーンアップ
    blobs = list(bucket.list_blobs(prefix="generated_arts/test_"))
    for blob in blobs:
        blob.delete()


@pytest.fixture()
def upload_test_images(storage_client):
    """テスト画像をエミュレーターにアップロードする。"""
    image_bytes = _make_test_image()
    paths = [
        "generated_arts/test_art_001.png",
        "generated_arts/test_art_002.jpg",
        "generated_arts/other_folder/test_art_003.png",
    ]
    for path in paths:
        blob = storage_client.blob(path)
        blob.upload_from_string(image_bytes, content_type="image/png")
    return paths


class TestFirebaseStorageWithEmulator:
    """エミュレーターを使った FirebaseStorageClient の統合テスト。"""

    def test_list_images_with_prefix(self, storage_client, upload_test_images) -> None:
        """prefix 指定で画像一覧を取得できる。"""
        from services.ingestion.firebase_storage import FirebaseStorageClient

        # FirebaseStorageClient のバケットを直接差し替え
        client = FirebaseStorageClient.__new__(FirebaseStorageClient)
        client._bucket = storage_client

        images = client.list_images(prefix="generated_arts/")

        # generated_arts/ 直下の2件 + サブフォルダの1件
        test_images = [img for img in images if "test_art" in img]
        assert len(test_images) >= 2

    def test_download_image(self, storage_client, upload_test_images) -> None:
        """画像をバイナリでダウンロードできる。"""
        from services.ingestion.firebase_storage import FirebaseStorageClient

        client = FirebaseStorageClient.__new__(FirebaseStorageClient)
        client._bucket = storage_client

        data = client.download_image("generated_arts/test_art_001.png")

        assert isinstance(data, bytes)
        assert len(data) > 0
        # PNG magic bytes
        assert data[:4] == b"\x89PNG"

    def test_extract_artwork_id(self) -> None:
        """blob パスから artwork_id を抽出できる。"""
        from services.ingestion.firebase_storage import FirebaseStorageClient

        assert FirebaseStorageClient.extract_artwork_id("generated_arts/test_art_001.png") == "test_art_001"

    def test_list_images_excludes_non_images(self, storage_client) -> None:
        """画像以外のファイルは除外される。"""
        from services.ingestion.firebase_storage import FirebaseStorageClient

        # テキストファイルをアップロード
        blob = storage_client.blob("generated_arts/test_readme.txt")
        blob.upload_from_string(b"hello", content_type="text/plain")

        client = FirebaseStorageClient.__new__(FirebaseStorageClient)
        client._bucket = storage_client

        images = client.list_images(prefix="generated_arts/")

        txt_files = [img for img in images if img.endswith(".txt")]
        assert len(txt_files) == 0

        # クリーンアップ
        blob.delete()
