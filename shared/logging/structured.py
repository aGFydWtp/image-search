"""Cloud Logging 互換の構造化 JSON ログ出力。

- `severity`, `message`, `time` 等を Cloud Logging の [structured logging](
  https://cloud.google.com/logging/docs/structured-logging) 仕様で出力する。
- `logging.googleapis.com/labels` / `trace` / `spanId` を採用し、
  ログベースメトリクスや Cloud Error Reporting にそのまま流せる形にする。

シークレット取り扱いの前提:
    ``extra`` で渡されたキーが ``api_key``/``password``/``secret``/
    ``token``/``credential`` 等を含む場合、値を再帰的に ``***`` に置換する。
    ただし ``message`` 本文（f-string の結果）はスキャン対象外のため、
    シークレットを文字列補間でメッセージに埋め込まないこと。必ず
    ``logger.info("msg", extra={"qdrant_api_key": key})`` のように
    構造化フィールドとして渡す。
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from shared.config import Settings

NOTICE = 25
logging.addLevelName(NOTICE, "NOTICE")

_SEVERITY_MAP: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    NOTICE: "NOTICE",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

_SECRET_KEY_PATTERNS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "credential",
)

_REDACTED = "***"

_ERROR_REPORTING_TYPE = (
    "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"
)

_RESERVED_LOG_RECORD_KEYS: frozenset[str] = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }
)


@dataclass(frozen=True)
class TraceContext:
    """Cloud Logging trace/span フィールドの値オブジェクト。"""

    trace: str
    span_id: str


_trace_context_var: ContextVar[TraceContext | None] = ContextVar(
    "structured_log_trace_context", default=None
)


def bind_trace_context(ctx: TraceContext | None) -> Token[TraceContext | None]:
    """現在のコンテキストに TraceContext をバインドする。戻り値の Token で解除可能。"""
    return _trace_context_var.set(ctx)


def current_trace_context() -> TraceContext | None:
    return _trace_context_var.get()


def extract_trace_context(
    headers: dict[str, str], project_id: str | None = None
) -> TraceContext | None:
    """HTTP ヘッダから TraceContext を抽出する。

    優先順: ``X-Cloud-Trace-Context`` → W3C ``traceparent``。
    抽出不可なら ``None``。``project_id`` が与えられた場合は
    ``projects/<id>/traces/<trace_id>`` 形式に整形する。
    """
    normalized = {k.lower(): v for k, v in headers.items()}

    gcp = normalized.get("x-cloud-trace-context")
    if gcp and "/" in gcp:
        trace_id, _, rest = gcp.partition("/")
        span_id = rest.split(";", 1)[0]
        if trace_id and span_id:
            return TraceContext(trace=_format_trace(trace_id, project_id), span_id=span_id)

    traceparent = normalized.get("traceparent")
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 4 and parts[1] and parts[2]:
            return TraceContext(trace=_format_trace(parts[1], project_id), span_id=parts[2])

    return None


def _format_trace(trace_id: str, project_id: str | None) -> str:
    if project_id:
        return f"projects/{project_id}/traces/{trace_id}"
    return trace_id


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(pat in lowered for pat in _SECRET_KEY_PATTERNS)


def _redact(key: str, value: Any) -> Any:
    """キー名がシークレット疑いなら ``***`` に置換し、dict/list は再帰的に辿る。"""
    if _is_secret_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(key, item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Cloud Logging 互換の JSON 1 行フォーマッタ。"""

    def __init__(self, *, service: str, env: str) -> None:
        super().__init__()
        self._service = service
        self._env = env

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, tz=timezone.utc)
        payload: dict[str, Any] = {
            "severity": _SEVERITY_MAP.get(record.levelno, record.levelname),
            "time": created.isoformat().replace("+00:00", "Z"),
            "message": record.getMessage(),
        }

        labels: dict[str, str] = {"service": self._service, "env": self._env}

        trace_override: str | None = None
        span_override: str | None = None

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_KEYS:
                continue
            if key == "labels" and isinstance(value, dict):
                for label_key, label_val in value.items():
                    label_key_str = str(label_key)
                    redacted_val = _redact(label_key_str, label_val)
                    labels[label_key_str] = str(redacted_val)
                continue
            if key == "event":
                labels["event"] = str(value)
                continue
            if key == "trace":
                trace_override = str(value)
                continue
            if key == "span_id":
                span_override = str(value)
                continue
            payload[key] = _redact(key, value)

        ctx = current_trace_context()
        trace_value = trace_override or (ctx.trace if ctx else None)
        span_value = span_override or (ctx.span_id if ctx else None)
        if trace_value:
            payload["logging.googleapis.com/trace"] = trace_value
        if span_value:
            payload["logging.googleapis.com/spanId"] = span_value

        payload["logging.googleapis.com/labels"] = labels

        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["@type"] = _ERROR_REPORTING_TYPE
            payload["stack_trace"] = "".join(
                traceback.format_exception(exc_type, exc_value, exc_tb)
            )

        return json.dumps(payload, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    """ローカル開発向けの人間可読フォールバック。"""

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)s %(name)s: %(message)s")


def configure_logging(settings: Settings) -> None:
    """Settings に従って root logger を構成する。繰り返し呼んでも冪等。"""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(
            JsonFormatter(service=settings.service_name, env=settings.env_name)
        )
    else:
        handler.setFormatter(_TextFormatter())

    root.addHandler(handler)
    root.setLevel(settings.log_level)
