"""Debug helper to identify transient top-level windows.

Some Windows environments briefly show an extra blank window titled "python".
This module installs a QApplication event filter that logs every top-level
widget shown, along with a trimmed Python stack trace that points to the
call site.

Enabled only in DEBUG runs (see arim_rde_tool.py) and skipped under pytest.
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Optional

from config.common import get_dynamic_file_path
from qt_compat.core import QObject, QEvent
from qt_compat.widgets import QApplication, QWidget


def _normalize_path(path: str) -> str:
    return path.replace("/", "\\").lower()


class _WindowShowProbe(QObject):
    def __init__(self, logger: logging.Logger, *, max_stack_lines: int = 12) -> None:
        super().__init__()
        self._logger = logger
        self._max_stack_lines = max_stack_lines
        self._seen: set[int] = set()

    def eventFilter(self, obj: object, event: object) -> bool:  # noqa: N802 - Qt override
        try:
            if not isinstance(obj, QWidget):
                return False
            if not isinstance(event, QEvent):
                return False

            etype = event.type()
            if etype == QEvent.Destroy:
                self._seen.discard(id(obj))
                return False

            if etype != QEvent.Show:
                return False

            if not obj.isWindow():
                return False

            # Avoid flooding: log each window object once.
            obj_id = id(obj)
            if obj_id in self._seen:
                return False
            self._seen.add(obj_id)

            title = ""
            try:
                title = obj.windowTitle() or ""
            except Exception:
                title = ""

            # Ignore the main app window.
            if "arim-rde-tool" in title.lower():
                return False

            cls_name = type(obj).__name__
            obj_name = ""
            try:
                obj_name = obj.objectName() or ""
            except Exception:
                obj_name = ""

            modality = "-"
            try:
                if hasattr(obj, "isModal"):
                    modality = "modal" if bool(getattr(obj, "isModal")()) else "nonmodal"
            except Exception:
                modality = "?"

            flags = "-"
            try:
                flags = hex(int(obj.windowFlags()))
            except Exception:
                flags = "?"

            size = "-"
            try:
                size = f"{obj.width()}x{obj.height()}"
            except Exception:
                size = "?"

            details: list[str] = []
            try:
                # Provide extra hints for common dialog classes.
                from qt_compat.widgets import QProgressDialog, QMessageBox, QDialog  # type: ignore

                if isinstance(obj, QProgressDialog):
                    try:
                        details.append(f"progress:label={obj.labelText()!r}")
                    except Exception:
                        pass
                    try:
                        details.append(f"progress:range=({obj.minimum()},{obj.maximum()})")
                    except Exception:
                        pass
                    try:
                        details.append(f"progress:minDuration={obj.minimumDuration()}ms")
                    except Exception:
                        pass
                elif isinstance(obj, QMessageBox):
                    try:
                        details.append(f"msgbox:text={obj.text()!r}")
                    except Exception:
                        pass
                elif isinstance(obj, QDialog):
                    details.append("dialog")
            except Exception:
                # qt_compat may not expose all symbols in some contexts.
                pass

            extra = " " + " ".join(details) if details else ""

            self._logger.warning(
                "[WINDOW-SHOW] cls=%s title=%r objectName=%r %s flags=%s size=%s%s",
                cls_name,
                title,
                obj_name,
                modality,
                flags,
                size,
                extra,
            )

            # Trim stack to repo frames only.
            src_root = get_dynamic_file_path("src")
            root = _normalize_path(os.path.join(src_root, ""))
            stack = traceback.extract_stack(limit=80)
            repo_frames: list[str] = []
            for frame in stack:
                fpath = _normalize_path(frame.filename)
                if root in fpath:
                    line = (frame.line or "").strip()
                    repo_frames.append(f"{frame.filename}:{frame.lineno} in {frame.name} -> {line}")

            if repo_frames:
                for line in repo_frames[-self._max_stack_lines :]:
                    self._logger.warning("[WINDOW-SHOW]   %s", line)

        except Exception:  # pragma: no cover - diagnostic tool
            self._logger.debug("window show probe failed", exc_info=True)
        return False


def install_window_show_probe(
    *,
    logger: Optional[logging.Logger] = None,
    logger_name: str = "RDE_WebView",
) -> None:
    """Install a global event filter that logs top-level window shows."""

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    app = QApplication.instance()
    if app is None:
        return

    probe_attr = "_rde_window_show_probe"
    if hasattr(app, probe_attr):
        return

    logger = logger or logging.getLogger(logger_name)
    probe = _WindowShowProbe(logger)
    app.installEventFilter(probe)
    setattr(app, probe_attr, probe)
