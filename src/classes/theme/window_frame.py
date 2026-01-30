"""Native window frame theming helpers.

Standard window frames (title bars) stay enabled while matching the
current theme as much as the OS allows (Windows immersive dark mode).
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from PySide6.QtWidgets import QApplication, QWidget

from classes.core.platform import apply_native_titlebar_theme

from .theme_manager import ThemeManager, ThemeMode

logger = logging.getLogger(__name__)


def apply_window_frame_theme(target: Optional[QWidget] = None, *, mode: Optional[ThemeMode] = None) -> None:
    """Apply the active theme to native window frames.

    Args:
        target: Specific top-level widget to update. When omitted, all
            top-level widgets registered in the current QApplication are updated.
        mode: Optional theme mode override. Defaults to the current mode tracked
            by :class:`ThemeManager`.
    """
    theme_manager = ThemeManager.instance()
    effective_mode = mode or theme_manager.get_mode()
    widgets = _iter_target_widgets(target)

    for widget in widgets:
        if widget is None:
            continue
        apply_native_titlebar_theme(widget, effective_mode, theme_manager)


def _iter_target_widgets(target: Optional[QWidget]) -> Iterable[QWidget]:
    if target is not None:
        return (target,)
    app = QApplication.instance()
    if not app:
        return tuple()
    return tuple(widget for widget in app.topLevelWidgets() if isinstance(widget, QWidget))
