"""再インデックス CLI (python -m services.ingestion.reindex) のテスト。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from shared.qdrant.alias_admin import (
    AliasAdmin,
    PhysicalCollectionInUseError,
    SwapResult,
)
from shared.qdrant.validation import CheckResult, ValidationReport
from services.ingestion.reindex import (
    ReindexOrchestrator,
    ReindexResult,
    cli_main,
)


def _swap_result(new: str, prev: str | None = None) -> SwapResult:
    return SwapResult(
        alias="artworks_current",
        previous_target=prev,
        new_target=new,
        swapped_at=datetime.now(tz=timezone.utc),
    )


def _passed_validation() -> ValidationReport:
    return ValidationReport(
        passed=True,
        checks=(CheckResult(name="ok", passed=True, detail=""),),
    )


def _succeeded_result(target: str) -> ReindexResult:
    return ReindexResult(
        target_collection=target,
        processed_count=10,
        failed_count=0,
        validation_report=_passed_validation(),
        swap_result=_swap_result(target, prev="artworks_v1"),
        swapped=True,
    )


def _failed_validation_result(target: str) -> ReindexResult:
    return ReindexResult(
        target_collection=target,
        processed_count=10,
        failed_count=0,
        validation_report=ValidationReport(
            passed=False,
            checks=(CheckResult(name="x", passed=False, detail=""),),
        ),
        swap_result=None,
        swapped=False,
    )


class _Stubs:
    """テスト全体で使い回す依存スタブ集。"""

    def __init__(self) -> None:
        self.client = MagicMock()
        self.repo = MagicMock()
        self.admin = MagicMock(spec=AliasAdmin)
        self.admin.current_target.return_value = "artworks_v1"
        self.admin.rollback.return_value = _swap_result(
            "artworks_v1", prev="artworks_v2"
        )
        self.orchestrator = MagicMock(spec=ReindexOrchestrator)
        self.orchestrator.run.return_value = _succeeded_result("artworks_v2")
        self.settings = MagicMock()
        self.settings.qdrant_alias = "artworks_current"
        self.settings.qdrant_collection = "artworks_v1"
        self.settings.reindex_validation_ratio = 0.9
        self.settings.reindex_sample_queries_path = "/tmp/samples.json"
        self.settings.vector_dim = 1152


def _patched_main(argv: list[str], stubs: _Stubs) -> int:
    """CLI の重い依存を差し替えて cli_main を呼ぶ。"""
    with patch("services.ingestion.reindex.Settings", return_value=stubs.settings), \
         patch("services.ingestion.reindex.configure_logging"), \
         patch(
             "services.ingestion.reindex.build_repository",
             return_value=(stubs.client, MagicMock(), stubs.repo),
         ), \
         patch(
             "services.ingestion.reindex.AliasAdmin",
             return_value=stubs.admin,
         ), \
         patch(
             "services.ingestion.reindex.ReindexOrchestrator",
             return_value=stubs.orchestrator,
         ), \
         patch(
             "services.ingestion.reindex._build_populate",
             return_value=lambda target: iter([True, True]),
         ), \
         patch(
             "services.ingestion.reindex._load_sample_vectors",
             return_value=[[0.1] * 4],
         ):
        return cli_main(argv)


class TestRunCommand:
    def test_run_invokes_orchestrator_with_target(self) -> None:
        stubs = _Stubs()
        code = _patched_main(["run", "--target-version", "v2"], stubs)

        assert code == 0
        stubs.orchestrator.run.assert_called_once()
        call_kwargs = stubs.orchestrator.run.call_args.kwargs
        assert call_kwargs["target_collection"] == "artworks_v2"
        assert call_kwargs["force_recreate"] is False
        assert call_kwargs["dry_run"] is False
        assert call_kwargs["skip_validation"] is False

    def test_run_returns_nonzero_on_validation_failure(self) -> None:
        stubs = _Stubs()
        stubs.orchestrator.run.return_value = _failed_validation_result(
            "artworks_v2"
        )
        code = _patched_main(["run", "--target-version", "v2"], stubs)
        assert code != 0

    def test_run_dry_run_exit_zero(self) -> None:
        stubs = _Stubs()
        stubs.orchestrator.run.return_value = ReindexResult(
            target_collection="artworks_v2",
            processed_count=5,
            failed_count=0,
            validation_report=_passed_validation(),
            swap_result=None,
            swapped=False,
        )
        code = _patched_main(
            ["run", "--target-version", "v2", "--dry-run"], stubs
        )
        assert code == 0
        assert stubs.orchestrator.run.call_args.kwargs["dry_run"] is True

    def test_run_force_recreate_flag_is_forwarded(self) -> None:
        stubs = _Stubs()
        _patched_main(
            ["run", "--target-version", "v2", "--force-recreate"], stubs
        )
        assert stubs.orchestrator.run.call_args.kwargs["force_recreate"] is True

    def test_run_skip_validation_flag_is_forwarded(self) -> None:
        stubs = _Stubs()
        _patched_main(
            ["run", "--target-version", "v2", "--skip-validation"], stubs
        )
        assert (
            stubs.orchestrator.run.call_args.kwargs["skip_validation"] is True
        )

    def test_run_sample_ratio_flag_is_forwarded(self) -> None:
        stubs = _Stubs()
        with patch(
            "services.ingestion.reindex.ValidationGate"
        ) as mock_gate_cls:
            mock_gate_cls.return_value = MagicMock()
            _patched_main(
                ["run", "--target-version", "v2", "--sample-ratio", "0.75"],
                stubs,
            )
            assert (
                mock_gate_cls.call_args.kwargs["sample_ratio_threshold"]
                == 0.75
            )


class TestTargetVersionValidation:
    @pytest.mark.parametrize("bad", ["v2!", "v 2", "v/2", "", "../evil"])
    def test_invalid_target_version_rejected(
        self, bad: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            cli_main(["run", "--target-version", bad])
        err = capsys.readouterr().err
        assert "target-version" in err.lower() or "invalid" in err.lower()

    @pytest.mark.parametrize("good", ["v2", "v-2", "staging_3", "20260414"])
    def test_valid_target_version_accepted(self, good: str) -> None:
        stubs = _Stubs()
        code = _patched_main(["run", "--target-version", good], stubs)
        assert code == 0
        assert (
            stubs.orchestrator.run.call_args.kwargs["target_collection"]
            == f"artworks_{good}"
        )


class TestRollbackCommand:
    def test_rollback_calls_alias_admin(self) -> None:
        stubs = _Stubs()
        code = _patched_main(["rollback", "--to", "v1"], stubs)

        assert code == 0
        stubs.admin.rollback.assert_called_once_with(
            "artworks_current", previous_target="artworks_v1"
        )

    def test_rollback_returns_nonzero_on_failure(self) -> None:
        stubs = _Stubs()
        from shared.qdrant.alias_admin import CollectionNotFoundError

        stubs.admin.rollback.side_effect = CollectionNotFoundError(
            "artworks_v1 gone"
        )
        code = _patched_main(["rollback", "--to", "v1"], stubs)
        assert code != 0


class TestDropCollectionCommand:
    def test_drop_calls_alias_admin(self) -> None:
        stubs = _Stubs()
        code = _patched_main(
            ["drop-collection", "artworks_v0"], stubs
        )
        assert code == 0
        stubs.admin.drop_physical_collection.assert_called_once_with(
            "artworks_v0", alias="artworks_current"
        )

    def test_drop_returns_nonzero_when_in_use(self) -> None:
        stubs = _Stubs()
        stubs.admin.drop_physical_collection.side_effect = (
            PhysicalCollectionInUseError("in use")
        )
        code = _patched_main(
            ["drop-collection", "artworks_v1"], stubs
        )
        assert code != 0

    @pytest.mark.parametrize(
        "bad_name",
        ["not_prefixed", "artworks_v!", "artworks_", "; rm -rf /", "../evil"],
    )
    def test_drop_rejects_invalid_collection_name(self, bad_name: str) -> None:
        with pytest.raises(SystemExit):
            cli_main(["drop-collection", bad_name])


class TestInitAliasCommand:
    def test_init_alias_creates_alias_when_missing(self) -> None:
        stubs = _Stubs()
        stubs.admin.current_target.return_value = None
        code = _patched_main(["init-alias"], stubs)
        assert code == 0
        # Issues a CreateAliasOperation via client.update_collection_aliases
        stubs.client.update_collection_aliases.assert_called_once()

    def test_init_alias_is_noop_when_alias_exists(self) -> None:
        stubs = _Stubs()
        stubs.admin.current_target.return_value = "artworks_v1"
        code = _patched_main(["init-alias"], stubs)
        assert code == 0
        stubs.client.update_collection_aliases.assert_not_called()


class TestCatchupCommand:
    def test_catchup_invokes_orchestrator(self) -> None:
        stubs = _Stubs()
        stubs.orchestrator.catchup = MagicMock()
        code = _patched_main(
            [
                "catchup",
                "--source",
                "artworks_v1",
                "--target",
                "artworks_v2",
            ],
            stubs,
        )
        assert code == 0
        stubs.orchestrator.catchup.assert_called_once_with(
            source_collection="artworks_v1",
            target_collection="artworks_v2",
            batch_size=100,
        )

    def test_catchup_batch_size_is_forwarded(self) -> None:
        stubs = _Stubs()
        stubs.orchestrator.catchup = MagicMock()
        _patched_main(
            [
                "catchup",
                "--source",
                "artworks_v1",
                "--target",
                "artworks_v2",
                "--batch-size",
                "50",
            ],
            stubs,
        )
        assert (
            stubs.orchestrator.catchup.call_args.kwargs["batch_size"] == 50
        )

    def test_catchup_rejects_invalid_collection_name(self) -> None:
        with pytest.raises(SystemExit):
            cli_main(
                [
                    "catchup",
                    "--source",
                    "not_prefixed",
                    "--target",
                    "artworks_v2",
                ]
            )

    def test_catchup_returns_nonzero_on_invalid_args(self) -> None:
        stubs = _Stubs()
        stubs.orchestrator.catchup = MagicMock(
            side_effect=ValueError("source must differ from target")
        )
        code = _patched_main(
            [
                "catchup",
                "--source",
                "artworks_v1",
                "--target",
                "artworks_v2",
            ],
            stubs,
        )
        assert code != 0

    def test_catchup_returns_nonzero_on_qdrant_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        stubs = _Stubs()
        stubs.orchestrator.catchup = MagicMock(
            side_effect=ConnectionError("qdrant down")
        )
        caplog.set_level("ERROR")
        code = _patched_main(
            [
                "catchup",
                "--source",
                "artworks_v1",
                "--target",
                "artworks_v2",
            ],
            stubs,
        )
        assert code != 0
        failed = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "reindex.catchup.failed"
        ]
        assert len(failed) == 1
        assert getattr(failed[0], "error_type", None) == "ConnectionError"


class TestNoSubcommand:
    def test_missing_subcommand_returns_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            cli_main([])
