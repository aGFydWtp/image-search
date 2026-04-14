"""run.py (BatchRunner) の単体テスト。

TDD RED: BatchRunner をテストファーストで実装する。
Firebase Storage からの画像一覧取得 → IngestionService パイプライン実行 → BatchLogger 記録。
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, call, patch

import pytest
from PIL import Image

from services.ingestion.batch import BatchLogger
from services.ingestion.run import BatchRunner


def _make_image_bytes() -> bytes:
    """テスト用の小さなPNG画像バイト列を生成する。"""
    img = Image.new("RGB", (10, 10), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestBatchRunnerInit:
    """BatchRunner の初期化テスト。"""

    def test_creates_with_settings(self) -> None:
        """Settings からすべての依存を組み立てられる。"""
        with patch("services.ingestion.run.Settings") as mock_settings_cls, \
             patch("services.ingestion.run.configure_logging"):
            mock_settings = MagicMock()
            mock_settings.firebase_credentials_path = "/tmp/cred.json"
            mock_settings.firebase_storage_bucket = "test-bucket"
            mock_settings.firebase_storage_prefix = "generated_arts/"
            mock_settings.lm_studio_url = "http://localhost:1234"
            mock_settings.embedding_service_url = "http://localhost:8100"
            mock_settings.vector_dim = 1152
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 6333
            mock_settings.qdrant_collection = "artworks_v1"
            mock_settings_cls.return_value = mock_settings

            with patch("services.ingestion.run.FirebaseStorageClient"), \
                 patch("services.ingestion.run.QdrantClient"), \
                 patch("services.ingestion.run.QdrantRepository"), \
                 patch("services.ingestion.run.VLMClient"), \
                 patch("services.ingestion.run.EmbeddingClient"):
                runner = BatchRunner()

            assert runner._prefix == "generated_arts/"

    def test_configures_structured_logging_once_on_init(self) -> None:
        """BatchRunner 初期化時に configure_logging が 1 度だけ呼ばれる。"""
        with patch("services.ingestion.run.Settings") as mock_settings_cls, \
             patch("services.ingestion.run.configure_logging") as mock_configure:
            mock_settings = MagicMock()
            mock_settings.firebase_storage_prefix = "generated_arts/"
            mock_settings.vector_dim = 1152
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 6333
            mock_settings.qdrant_alias = "artworks_current"
            mock_settings.qdrant_collection = "artworks_v1"
            mock_settings_cls.return_value = mock_settings

            with patch("services.ingestion.run.FirebaseStorageClient"), \
                 patch("services.ingestion.run.QdrantClient"), \
                 patch("services.ingestion.run.QdrantRepository"), \
                 patch("services.ingestion.run.CollectionResolver"), \
                 patch("services.ingestion.run.VLMClient"), \
                 patch("services.ingestion.run.EmbeddingClient"):
                BatchRunner()

            mock_configure.assert_called_once_with(mock_settings)


class TestBatchRunnerAliasMismatch:
    """差分 ingestion 起動時に alias 先と qdrant_collection の不一致を検知する。"""

    def _build(
        self,
        *,
        alias_target: str | None,
        qdrant_collection: str = "artworks_v1",
    ) -> MagicMock:
        settings = MagicMock()
        settings.firebase_storage_prefix = "generated_arts/"
        settings.vector_dim = 1152
        settings.qdrant_host = "localhost"
        settings.qdrant_port = 6333
        settings.qdrant_alias = "artworks_current"
        settings.qdrant_collection = qdrant_collection

        resolver = MagicMock()
        if alias_target is None:
            from shared.qdrant.resolver import AliasNotFoundError

            resolver.resolve.side_effect = AliasNotFoundError("no alias yet")
        else:
            resolver.resolve.return_value = alias_target
        return settings, resolver

    def _run_init(
        self, settings: MagicMock, resolver: MagicMock
    ) -> None:
        with patch("services.ingestion.run.Settings", return_value=settings), \
             patch("services.ingestion.run.configure_logging"), \
             patch("services.ingestion.run.FirebaseStorageClient"), \
             patch("services.ingestion.run.QdrantClient"), \
             patch("services.ingestion.run.QdrantRepository"), \
             patch(
                 "services.ingestion.run.CollectionResolver",
                 return_value=resolver,
             ), \
             patch("services.ingestion.run.VLMClient"), \
             patch("services.ingestion.run.EmbeddingClient"):
            BatchRunner()

    def test_warns_once_when_alias_target_differs_from_qdrant_collection(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings, resolver = self._build(
            alias_target="artworks_v2", qdrant_collection="artworks_v1"
        )
        caplog.set_level("WARNING")
        self._run_init(settings, resolver)

        mismatch_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "ingestion.alias.mismatch"
        ]
        assert len(mismatch_records) == 1
        rec = mismatch_records[0]
        assert getattr(rec, "alias_target", None) == "artworks_v2"
        assert getattr(rec, "configured_collection", None) == "artworks_v1"

    def test_does_not_warn_when_alias_matches(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings, resolver = self._build(
            alias_target="artworks_v1", qdrant_collection="artworks_v1"
        )
        caplog.set_level("WARNING")
        self._run_init(settings, resolver)

        mismatch_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "ingestion.alias.mismatch"
        ]
        assert mismatch_records == []

    def test_does_not_warn_when_alias_undefined(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """初回導入時などエイリアス未作成は警告しない (init-alias で立ち上がる前)。"""
        settings, resolver = self._build(alias_target=None)
        caplog.set_level("WARNING")
        self._run_init(settings, resolver)

        mismatch_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "ingestion.alias.mismatch"
        ]
        assert mismatch_records == []


class TestBatchRunnerExecute:
    """BatchRunner.execute() のテスト。"""

    @staticmethod
    def _make_runner(
        image_list: list[str] | None = None,
        process_results: list[bool] | None = None,
    ) -> tuple[BatchRunner, MagicMock, MagicMock]:
        """テスト用の BatchRunner を依存注入で組み立てる。"""
        firebase_client = MagicMock()
        firebase_client.list_images.return_value = image_list or []
        firebase_client.download_image.return_value = _make_image_bytes()
        firebase_client.get_public_url.side_effect = lambda p: f"https://storage/{p}"
        firebase_client.extract_artwork_id.side_effect = lambda p: p.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        ingestion_service = MagicMock()
        if process_results:
            ingestion_service.process_artwork.side_effect = process_results
        else:
            ingestion_service.process_artwork.return_value = True

        qdrant_repo = MagicMock()
        qdrant_repo.exists.return_value = False

        runner = BatchRunner.__new__(BatchRunner)
        runner._firebase = firebase_client
        runner._ingestion = ingestion_service
        runner._qdrant = qdrant_repo
        runner._prefix = "generated_arts/"
        runner._physical_collection = "artworks_v1"
        runner._batch_logger = BatchLogger()

        return runner, firebase_client, ingestion_service

    def test_execute_empty_list(self) -> None:
        """画像が0件のとき正常終了し、summary.total が 0。"""
        runner, _, _ = self._make_runner(image_list=[])
        summary = runner.execute()

        assert summary["total"] == 0
        assert summary["processed"] == 0
        assert summary["errors"] == 0

    def test_execute_processes_all_images(self) -> None:
        """画像一覧の全件に対して process_artwork が呼ばれる。"""
        images = ["generated_arts/art-001.png", "generated_arts/art-002.jpg"]
        runner, _, ingestion = self._make_runner(image_list=images)

        summary = runner.execute()

        assert ingestion.process_artwork.call_count == 2
        assert summary["total"] == 2
        assert summary["processed"] == 2
        assert summary["errors"] == 0

    def test_execute_passes_correct_arguments(self) -> None:
        """process_artwork に artwork_id, image_bytes, image_url, title, artist_name が渡される。"""
        images = ["generated_arts/my-art.png"]
        runner, firebase, ingestion = self._make_runner(image_list=images)

        runner.execute()

        ingestion.process_artwork.assert_called_once()
        call_kwargs = ingestion.process_artwork.call_args
        assert call_kwargs.kwargs["artwork_id"] == "my-art"
        assert call_kwargs.kwargs["image_url"] == "https://storage/generated_arts/my-art.png"
        assert isinstance(call_kwargs.kwargs["image_bytes"], bytes)

    def test_execute_records_errors(self) -> None:
        """process_artwork が False を返した場合、エラーとして記録される。"""
        images = ["generated_arts/ok.png", "generated_arts/fail.png"]
        runner, _, _ = self._make_runner(
            image_list=images,
            process_results=[True, False],
        )

        summary = runner.execute()

        assert summary["processed"] == 1
        assert summary["errors"] == 1

    def test_execute_handles_download_exception(self) -> None:
        """download_image が例外を投げた場合、エラー記録して継続する。"""
        images = ["generated_arts/bad.png", "generated_arts/good.png"]
        runner, firebase, ingestion = self._make_runner(image_list=images)
        firebase.download_image.side_effect = [
            RuntimeError("download failed"),
            _make_image_bytes(),
        ]

        summary = runner.execute()

        assert summary["errors"] == 1
        assert summary["processed"] == 1
        # 2件目は正常に処理される
        assert ingestion.process_artwork.call_count == 1

    def test_execute_uses_prefix(self) -> None:
        """list_images に prefix が渡される。"""
        runner, firebase, _ = self._make_runner()

        runner.execute()

        firebase.list_images.assert_called_once_with(prefix="generated_arts/")

    def test_execute_skips_already_indexed(self) -> None:
        """Qdrant に既存の artwork_id はスキップされる。"""
        images = ["generated_arts/existing.png", "generated_arts/new.png"]
        runner, _, ingestion = self._make_runner(image_list=images)
        # exists() を追加
        qdrant_repo = MagicMock()
        qdrant_repo.exists.side_effect = [True, False]
        runner._qdrant = qdrant_repo

        summary = runner.execute()

        # existing はスキップ、new だけ処理
        assert ingestion.process_artwork.call_count == 1
        assert summary["total"] == 2
        assert summary["processed"] == 1

    def test_execute_returns_summary_dict(self) -> None:
        """execute() は summary dict を返す。"""
        runner, _, _ = self._make_runner(image_list=["generated_arts/a.png"])

        summary = runner.execute()

        assert "total" in summary
        assert "processed" in summary
        assert "errors" in summary
        assert "duration_seconds" in summary
