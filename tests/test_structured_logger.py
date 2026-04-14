"""Cloud Logging 互換 StructuredLogger のテスト。"""

from __future__ import annotations

import io
import json
import logging
from unittest.mock import patch

import pytest

from shared.config import Settings
from shared.logging.structured import (
    NOTICE,
    JsonFormatter,
    TraceContext,
    bind_trace_context,
    configure_logging,
    extract_trace_context,
)


def _make_logger_with_json(service: str = "svc", env: str = "local") -> tuple[logging.Logger, io.StringIO]:
    """テスト用に JsonFormatter を付けたロガーを組み立てる。"""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter(service=service, env=env))
    logger = logging.getLogger(f"test_{id(buf)}")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, buf


def _parse(buf: io.StringIO) -> dict:
    return json.loads(buf.getvalue().strip())


class TestSeverityMapping:
    """Python logging レベル → Cloud Logging severity のマップ。"""

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (NOTICE, "NOTICE"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ],
    )
    def test_severity_mapping(self, level: int, expected: str) -> None:
        logger, buf = _make_logger_with_json()
        logger.log(level, "hello")
        assert _parse(buf)["severity"] == expected


class TestLabels:
    """Cloud Logging labels の合成。"""

    def test_labels_contain_service_and_env(self) -> None:
        logger, buf = _make_logger_with_json(service="ingestion", env="staging")
        logger.info("hi")
        labels = _parse(buf)["logging.googleapis.com/labels"]
        assert labels["service"] == "ingestion"
        assert labels["env"] == "staging"

    def test_labels_include_event_from_extra(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("swapped", extra={"event": "reindex.alias.swap"})
        labels = _parse(buf)["logging.googleapis.com/labels"]
        assert labels["event"] == "reindex.alias.swap"

    def test_labels_merge_additional_labels(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("hi", extra={"labels": {"foo": "bar"}})
        labels = _parse(buf)["logging.googleapis.com/labels"]
        assert labels["foo"] == "bar"
        assert labels["service"] == "svc"


class TestTraceContext:
    """X-Cloud-Trace-Context / traceparent からの抽出。"""

    def test_extract_from_x_cloud_trace_header(self) -> None:
        headers = {"X-Cloud-Trace-Context": "abc123def456/789;o=1"}
        ctx = extract_trace_context(headers, project_id="my-proj")
        assert ctx == TraceContext(trace="projects/my-proj/traces/abc123def456", span_id="789")

    def test_extract_from_x_cloud_trace_header_without_project(self) -> None:
        headers = {"X-Cloud-Trace-Context": "abc/789;o=1"}
        ctx = extract_trace_context(headers)
        assert ctx == TraceContext(trace="abc", span_id="789")

    def test_extract_from_traceparent_header(self) -> None:
        headers = {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"}
        ctx = extract_trace_context(headers, project_id="my-proj")
        assert ctx is not None
        assert ctx.trace == "projects/my-proj/traces/0af7651916cd43dd8448eb211c80319c"
        assert ctx.span_id == "b7ad6b7169203331"

    def test_extract_returns_none_when_headers_missing(self) -> None:
        assert extract_trace_context({}) is None

    def test_extract_returns_none_for_malformed_header(self) -> None:
        assert extract_trace_context({"X-Cloud-Trace-Context": "no-slash"}) is None

    def test_formatter_emits_trace_fields_from_context_var(self) -> None:
        logger, buf = _make_logger_with_json()
        token = bind_trace_context(TraceContext(trace="trc-1", span_id="sp-1"))
        try:
            logger.info("hi")
        finally:
            from shared.logging.structured import _trace_context_var

            _trace_context_var.reset(token)
        payload = _parse(buf)
        assert payload["logging.googleapis.com/trace"] == "trc-1"
        assert payload["logging.googleapis.com/spanId"] == "sp-1"

    def test_formatter_omits_trace_fields_when_no_context(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("hi")
        payload = _parse(buf)
        assert "logging.googleapis.com/trace" not in payload
        assert "logging.googleapis.com/spanId" not in payload


class TestSecretRedaction:
    """シークレット疑いのキーは *** に置換する。"""

    @pytest.mark.parametrize(
        "key",
        ["qdrant_api_key", "password", "api_token", "credential", "SECRET_VALUE"],
    )
    def test_known_secret_keys_are_redacted(self, key: str) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("boot", extra={key: "super-secret-value"})
        payload = _parse(buf)
        assert payload[key] == "***"
        assert "super-secret-value" not in buf.getvalue()

    def test_non_secret_keys_are_not_redacted(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("boot", extra={"collection": "artworks_v1"})
        assert _parse(buf)["collection"] == "artworks_v1"

    def test_nested_dict_secret_is_redacted(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("boot", extra={"config": {"qdrant_api_key": "super-secret"}})
        payload = _parse(buf)
        assert payload["config"]["qdrant_api_key"] == "***"
        assert "super-secret" not in buf.getvalue()

    def test_nested_list_of_dicts_secret_is_redacted(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info(
            "boot",
            extra={"items": [{"name": "ok"}, {"password": "hunter2"}]},
        )
        payload = _parse(buf)
        assert payload["items"][1]["password"] == "***"
        assert "hunter2" not in buf.getvalue()

    def test_secret_in_labels_dict_is_redacted(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("hi", extra={"labels": {"api_token": "leaky"}})
        labels = _parse(buf)["logging.googleapis.com/labels"]
        assert labels["api_token"] == "***"
        assert "leaky" not in buf.getvalue()


class TestExceptionReporting:
    """未補足例外を Cloud Error Reporting 互換で出力。"""

    def test_exc_info_adds_error_reporting_type(self) -> None:
        logger, buf = _make_logger_with_json()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("failed")
        payload = _parse(buf)
        assert (
            payload["@type"]
            == "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"
        )
        assert "RuntimeError: boom" in payload["stack_trace"]
        assert payload["severity"] == "ERROR"

    def test_normal_info_log_has_no_error_reporting_type(self) -> None:
        logger, buf = _make_logger_with_json()
        logger.info("ok")
        payload = _parse(buf)
        assert "@type" not in payload
        assert "stack_trace" not in payload


class TestConfigureLogging:
    """configure_logging は Settings に基づき root logger を構成する。"""

    def _clean_root(self) -> None:
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

    def test_json_mode_installs_json_formatter(self) -> None:
        self._clean_root()
        with patch.dict("os.environ", {"LOG_FORMAT": "json"}, clear=True):
            settings = Settings(_env_file=None)
        configure_logging(settings)
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        self._clean_root()

    def test_text_mode_installs_plain_formatter(self) -> None:
        self._clean_root()
        with patch.dict("os.environ", {"LOG_FORMAT": "text"}, clear=True):
            settings = Settings(_env_file=None)
        configure_logging(settings)
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JsonFormatter)
        self._clean_root()

    def test_configure_is_idempotent(self) -> None:
        self._clean_root()
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)
        configure_logging(settings)
        configure_logging(settings)
        root = logging.getLogger()
        assert len(root.handlers) == 1
        self._clean_root()

    def test_log_level_is_applied(self) -> None:
        self._clean_root()
        with patch.dict("os.environ", {"LOG_LEVEL": "WARNING"}, clear=True):
            settings = Settings(_env_file=None)
        configure_logging(settings)
        assert logging.getLogger().level == logging.WARNING
        self._clean_root()
