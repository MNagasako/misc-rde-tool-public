from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from config.common import ensure_directory_exists, get_dynamic_file_path

logger = logging.getLogger(__name__)


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "off", "no"}


def is_ui_responsiveness_enabled() -> bool:
    explicit = os.environ.get("RDE_UI_RESPONSIVENESS")
    if explicit is not None:
        return _is_truthy(explicit)
    perf_env = os.environ.get("RDE_PERF")
    if perf_env is not None:
        return _is_truthy(perf_env)
    return False


def get_ui_responsiveness_log_path() -> str:
    override = os.environ.get("RDE_UI_RESPONSIVENESS_LOG")
    if override:
        return override
    return get_dynamic_file_path("output/log/ui_responsiveness.jsonl")


def write_ui_responsiveness_event(payload: dict[str, Any]) -> None:
    if not is_ui_responsiveness_enabled():
        return

    path = get_ui_responsiveness_log_path()
    ensure_directory_exists(os.path.dirname(path))

    record = dict(payload)
    record.setdefault("timestamp", time.time())
    record.setdefault("thread", threading.current_thread().name)

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        logger.debug("ui responsiveness event write failed", exc_info=True)


@dataclass
class UIResponsivenessRun:
    screen: str
    target: str
    action: str
    context: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.perf_counter)
    interactive_marked: bool = False
    complete_marked: bool = False
    finished: bool = False

    def __post_init__(self) -> None:
        self.mark("requested")

    def mark(self, phase: str, **extra: Any) -> None:
        if not is_ui_responsiveness_enabled():
            return
        payload = dict(self.context)
        payload.update(extra)
        payload.update(
            {
                "run_id": self.run_id,
                "screen": self.screen,
                "target": self.target,
                "action": self.action,
                "phase": str(phase),
                "elapsed_ms": round((time.perf_counter() - self.started_at) * 1000.0, 3),
            }
        )
        write_ui_responsiveness_event(payload)

    def interactive(self, **extra: Any) -> None:
        if self.interactive_marked:
            return
        self.interactive_marked = True
        self.mark("interactive", **extra)

    def complete(self, **extra: Any) -> None:
        if self.complete_marked:
            return
        self.complete_marked = True
        self.mark("complete", **extra)

    def finish(self, *, success: bool = True, **extra: Any) -> None:
        if self.finished:
            return
        self.finished = True
        self.mark("finished", success=bool(success), **extra)


def start_ui_responsiveness_run(
    screen: str,
    target: str,
    action: str,
    **context: Any,
) -> UIResponsivenessRun:
    return UIResponsivenessRun(
        screen=str(screen),
        target=str(target),
        action=str(action),
        context=dict(context),
    )


def schedule_deferred_ui_task(owner, key: str, callback, *, delay_ms: int = 0) -> bool:
    """同一 owner/key の重複実行を防ぎつつ、UI タスクをイベントループへ戻してから実行する。"""

    try:
        from qt_compat.core import QTimer
    except Exception:
        try:
            callback()
            return True
        except Exception:
            logger.debug("deferred ui fallback callback failed", exc_info=True)
            return False

    if owner is None:
        try:
            QTimer.singleShot(max(0, int(delay_ms)), callback)
            return True
        except Exception:
            logger.debug("deferred ui singleShot failed", exc_info=True)
            return False

    store = getattr(owner, "_rde_deferred_ui_tasks", None)
    if store is None:
        store = {}
        try:
            setattr(owner, "_rde_deferred_ui_tasks", store)
        except Exception:
            store = {}

    if key in store:
        return False

    timer = QTimer(owner)
    timer.setSingleShot(True)
    store[key] = timer

    def _run() -> None:
        try:
            active_store = getattr(owner, "_rde_deferred_ui_tasks", None)
            if isinstance(active_store, dict):
                active_store.pop(key, None)
        except Exception:
            pass

        try:
            callback()
        except Exception:
            logger.debug("deferred ui callback failed: %s", key, exc_info=True)
        finally:
            try:
                timer.deleteLater()
            except Exception:
                pass

    timer.timeout.connect(_run)
    timer.start(max(0, int(delay_ms)))
    return True