"""軽量パフォーマンス計測ユーティリティ。

目的:
- 実機ログから「どこが遅いか」を自動で切り分けられるようにする
- UI/非同期(イベント駆動)でも使える start/end マーカーと、同期区間の span を提供

方針:
- 依存を増やさず、logging へ出力
- DEBUG 時 or 明示有効化時のみ出力（過剰なログ増加を避ける）
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class PerfEvent:
    name: str
    duration_sec: float
    thread: str
    extra: Dict[str, Any]


class PerfMonitor:
    _t0 = time.perf_counter()
    _last_mark = _t0
    _enabled: Optional[bool] = None
    _lock = threading.Lock()
    _starts: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    _events: List[PerfEvent] = []

    @classmethod
    def _log(cls, logger: logging.Logger, level: int, msg: str, *args: Any) -> None:
        # NOTE: This app often uses LogManager-managed loggers (propagate=False).
        # Under pytest, caplog captures via the root logger handler; if propagate=False,
        # records won't reach caplog and tests become order-dependent.
        if os.environ.get("PYTEST_CURRENT_TEST") and getattr(logger, "propagate", True) is False:
            original_propagate = logger.propagate
            logger.propagate = True
            try:
                logger.log(level, msg, *args)
            finally:
                logger.propagate = original_propagate
            return

        logger.log(level, msg, *args)

    @classmethod
    def enable(cls, enabled: bool = True) -> None:
        cls._enabled = bool(enabled)

    @classmethod
    def is_enabled(cls, logger: Optional[logging.Logger] = None) -> bool:
        if cls._enabled is not None:
            return cls._enabled
        # 明示環境変数があればそれを優先
        env = os.environ.get("RDE_PERF")
        if env is not None:
            return env.strip() not in ("", "0", "false", "False")
        # デフォルトは DEBUG 時のみ
        if logger is not None:
            try:
                return logger.getEffectiveLevel() <= logging.DEBUG
            except Exception:
                return False
        return False

    @classmethod
    def mark(cls, label: str, *, logger: Optional[logging.Logger] = None, level: int = logging.INFO, **extra: Any) -> None:
        logger = logger or logging.getLogger("RDE_WebView")
        if not cls.is_enabled(logger):
            return
        now = time.perf_counter()
        since_start = now - cls._t0
        since_last = now - cls._last_mark
        cls._last_mark = now
        payload = {"since_start_sec": round(since_start, 6), "since_last_sec": round(since_last, 6)}
        payload.update(extra)
        cls._log(logger, level, "[PERF-MARK] %s %s", label, payload)

    @classmethod
    @contextmanager
    def span(
        cls,
        name: str,
        *,
        logger: Optional[logging.Logger] = None,
        level: int = logging.INFO,
        **extra: Any,
    ) -> Iterator[None]:
        logger = logger or logging.getLogger("RDE_WebView")
        if not cls.is_enabled(logger):
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            cls._record(name, dt, extra)
            cls._log(logger, level, "[PERF] %s: %.3f sec %s", name, dt, extra if extra else "")

    @classmethod
    def start(cls, key: str, *, logger: Optional[logging.Logger] = None, **extra: Any) -> None:
        logger = logger or logging.getLogger("RDE_WebView")
        if not cls.is_enabled(logger):
            return
        with cls._lock:
            # 既に開始済みなら二重計測しない（最初の開始を優先）
            if key in cls._starts:
                return
            cls._starts[key] = (time.perf_counter(), dict(extra))

    @classmethod
    def end(cls, key: str, *, logger: Optional[logging.Logger] = None, level: int = logging.INFO, **extra: Any) -> Optional[float]:
        logger = logger or logging.getLogger("RDE_WebView")
        if not cls.is_enabled(logger):
            return None
        with cls._lock:
            item = cls._starts.pop(key, None)
        if not item:
            return None
        t0, start_extra = item
        dt = time.perf_counter() - t0
        merged = dict(start_extra)
        merged.update(extra)
        cls._record(key, dt, merged)
        cls._log(logger, level, "[PERF] %s: %.3f sec %s", key, dt, merged if merged else "")
        return dt

    @classmethod
    def _record(cls, name: str, duration: float, extra: Dict[str, Any]) -> None:
        try:
            thread_name = threading.current_thread().name
        except Exception:
            thread_name = "?"
        with cls._lock:
            cls._events.append(PerfEvent(name=name, duration_sec=float(duration), thread=thread_name, extra=dict(extra)))

    @classmethod
    def dump_summary(cls, *, logger: Optional[logging.Logger] = None, top: int = 20) -> None:
        logger = logger or logging.getLogger("RDE_WebView")
        if not cls.is_enabled(logger):
            return
        with cls._lock:
            events = list(cls._events)
        if not events:
            return

        events_sorted = sorted(events, key=lambda e: e.duration_sec, reverse=True)
        total = sum(e.duration_sec for e in events)
        cls._log(logger, logging.INFO, "[PERF-SUMMARY] events=%s total_recorded_sec=%.3f", len(events), total)
        for e in events_sorted[: max(1, int(top))]:
            cls._log(
                logger,
                logging.INFO,
                "[PERF-TOP] %s: %.3f sec thread=%s extra=%s",
                e.name,
                e.duration_sec,
                e.thread,
                e.extra,
            )


def _atexit_dump() -> None:
    try:
        # pytest closes its capture streams before interpreter shutdown;
        # logging from atexit can therefore raise 'I/O operation on closed file'
        # and produce noisy 'Logging error' blocks. Skip atexit dumping under pytest.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        PerfMonitor.dump_summary(logger=logging.getLogger("RDE_WebView"))
    except Exception:
        pass


atexit.register(_atexit_dump)
