"""バッチ処理のログ記録・進捗管理。"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class BatchLogger:
    """バッチ処理の開始・終了・処理件数・エラー件数を構造化ログで記録する。"""

    def __init__(self) -> None:
        self._total = 0
        self._processed = 0
        self._errors = 0
        self._error_details: list[dict[str, str]] = []
        self._start_time: float = 0
        self._end_time: float = 0

    def start(self, total: int) -> None:
        """バッチ処理開始を記録する。"""
        self._total = total
        self._start_time = time.time()
        logger.info(
            "Batch start: total=%d",
            total,
            extra={"batch_event": "start", "total": total},
        )

    def record_success(self) -> None:
        """処理成功を記録する。"""
        self._processed += 1

    def record_error(self, artwork_id: str, error: str) -> None:
        """処理エラーを記録する。"""
        self._errors += 1
        self._error_details.append({"artwork_id": artwork_id, "error": error})
        logger.warning(
            "Batch error: artwork_id=%s error=%s",
            artwork_id,
            error,
        )

    def finish(self) -> None:
        """バッチ処理終了を記録する。"""
        self._end_time = time.time()
        s = self.summary()
        logger.info(
            "Batch finish: processed=%d errors=%d duration=%.1fs",
            s["processed"],
            s["errors"],
            s["duration_seconds"],
        )

    def summary(self) -> dict[str, Any]:
        """バッチ処理サマリーを返す（JSON直列化可能）。"""
        elapsed = (self._end_time or time.time()) - self._start_time if self._start_time else 0
        return {
            "total": self._total,
            "processed": self._processed,
            "errors": self._errors,
            "duration_seconds": round(elapsed, 2),
            "error_details": self._error_details,
        }
