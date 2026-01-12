"""Portal status cell spinner delegate.

Used by DatasetListingWidget portal column to show an in-cell spinner while
refreshing portal status asynchronously.

- Uses ThemeManager colors (no hardcoded QColor).
- Disables animation timer under pytest to avoid flaky native crashes.
"""

from __future__ import annotations

import os
import weakref
from typing import Optional

from qt_compat.core import Qt, QTimer
from qt_compat.gui import QBrush, QFont
from PySide6.QtWidgets import QStyledItemDelegate

from classes.theme import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color


class PortalStatusSpinnerDelegate(QStyledItemDelegate):
    """QTableView delegate that prepends an animated spinner while loading."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent=None, *, is_loading_callback=None, view=None):
        super().__init__(parent)
        self._is_loading_callback = is_loading_callback
        self._spinner_index = 0
        self._test_mode = bool(os.environ.get("PYTEST_CURRENT_TEST"))

        self._view_ref = weakref.ref(view) if view is not None else None

        # Theme refresh
        self._theme_manager: Optional[ThemeManager] = None
        try:
            self._theme_manager = ThemeManager.instance()
            self_ref = weakref.ref(self)

            def _safe_refresh_theme(*_):
                obj = self_ref()
                if obj is None:
                    return
                try:
                    obj._on_theme_changed()
                except RuntimeError:
                    return

            self._theme_changed_handler = _safe_refresh_theme
            self._theme_manager.theme_changed.connect(self._theme_changed_handler)
        except Exception:
            self._theme_manager = None

        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        if not self._test_mode:
            self._timer.start()

    def _on_theme_changed(self) -> None:
        # Paint uses get_color() each time; just request repaint.
        self._request_viewport_update()

    def _request_viewport_update(self) -> None:
        try:
            view = self._view_ref() if self._view_ref is not None else None
            if view is not None and hasattr(view, "viewport"):
                view.viewport().update()
        except Exception:
            return

    def _tick(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
        self._request_viewport_update()

    def paint(self, painter, option, index):  # noqa: N802
        try:
            is_loading = False
            if callable(self._is_loading_callback):
                try:
                    is_loading = bool(self._is_loading_callback(index))
                except Exception:
                    is_loading = False

            if not is_loading:
                return super().paint(painter, option, index)

            # Build text: spinner + existing label (or "確認中")
            try:
                base_text = str(index.data(Qt.DisplayRole) or "").strip()
            except Exception:
                base_text = ""

            spinner = self.SPINNER_FRAMES[self._spinner_index] if self.SPINNER_FRAMES else ""
            shown = f"{spinner} {base_text}".strip() if base_text else f"{spinner} 確認中"

            opt = option
            try:
                # copy option to avoid mutating shared object
                from PySide6.QtWidgets import QStyleOptionViewItem

                opt = QStyleOptionViewItem(option)
            except Exception:
                opt = option

            try:
                self.initStyleOption(opt, index)
            except Exception:
                pass

            opt.text = shown
            try:
                f: QFont = opt.font
                f.setBold(True)
                opt.font = f
            except Exception:
                pass

            # Prefer theme text color.
            try:
                opt.palette.setColor(opt.palette.Text, get_color(ThemeKey.TABLE_ROW_TEXT))
            except Exception:
                pass

            # Visible "in-progress" highlight (theme-based).
            try:
                opt.backgroundBrush = QBrush(get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER))
            except Exception:
                pass

            super().paint(painter, opt, index)
        except Exception:
            # Failsafe: never break table paint.
            return super().paint(painter, option, index)
