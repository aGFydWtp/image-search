"""FirebaseStorageClient: Firebase Storageからの画像取得。"""

import logging
from pathlib import PurePosixPath
from urllib.parse import quote

import firebase_admin
import firebase_admin.credentials as fb_credentials
import firebase_admin.storage as fb_storage

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class FirebaseStorageClient:
    """Firebase Storage からの画像一覧取得・ダウンロード。"""

    def __init__(self, credentials_path: str, bucket_name: str) -> None:
        try:
            firebase_admin.get_app()
        except ValueError:
            cred = fb_credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)

        self._bucket = fb_storage.bucket(bucket_name)

    def list_images(self, prefix: str = "") -> list[str]:
        """指定prefixの画像ファイル一覧を返す。"""
        blobs = self._bucket.list_blobs(prefix=prefix)
        results = []
        for blob in blobs:
            ext = PurePosixPath(blob.name).suffix.lower()
            if ext in _IMAGE_EXTENSIONS:
                results.append(blob.name)
        return results

    def download_image(self, blob_path: str) -> bytes:
        """画像バイナリをダウンロードする。"""
        blob = self._bucket.blob(blob_path)
        return blob.download_as_bytes()

    def get_public_url(self, blob_path: str) -> str:
        """Firebase Storage の公開URLを生成する。"""
        encoded = quote(blob_path, safe="")
        return f"https://storage.googleapis.com/{self._bucket.name}/{encoded}?alt=media"

    @staticmethod
    def extract_artwork_id(blob_path: str) -> str:
        """blobパスからartwork_idを抽出する（拡張子なしのファイル名）。"""
        return PurePosixPath(blob_path).stem
