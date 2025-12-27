"""Native window frame theming helpers.

Standard window frames (title bars) stay enabled while matching the
current theme as much as the OS allows (Windows immersive dark mode).
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from .theme_keys import ThemeKey
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
        if sys.platform.startswith("win"):
            _apply_windows_titlebar(widget, effective_mode, theme_manager)
        else:  # pragma: no cover - other OS keep default frame colors
            logger.debug("Native title bar theming is not implemented for this platform")


def _iter_target_widgets(target: Optional[QWidget]) -> Iterable[QWidget]:
    if target is not None:
        return (target,)
    app = QApplication.instance()
    if not app:
        return tuple()
    return tuple(widget for widget in app.topLevelWidgets() if isinstance(widget, QWidget))


def _apply_windows_titlebar(widget: QWidget, mode: ThemeMode, theme_manager: ThemeManager) -> None:
    try:
        import ctypes
    except ImportError:  # pragma: no cover - ctypes always available on CPython
        logger.debug("ctypes is unavailable; skipping title bar theming")
        return

    hwnd = _get_hwnd(widget)
    if not hwnd:
        logger.debug("Window handle unavailable for %s; deferring title bar theming", widget.objectName())
        return

    dark_enabled = ctypes.c_int(1 if mode == ThemeMode.DARK else 0)
    size = ctypes.sizeof(dark_enabled)

    try:
        dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - dwmapi should exist on Windows 10+
        logger.debug("dwmapi not available; cannot update immersive dark mode")
        return

    # Windows 11 prefers DWMWA_USE_IMMERSIVE_DARK_MODE = 20, older builds use 19.
    immersive_attrs = (20, 19)
    applied = False
    for attr in immersive_attrs:
        result = dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark_enabled), size)
        if result == 0:
            applied = True
            break

    if not applied:
        logger.debug("DwmSetWindowAttribute failed for immersive mode: hwnd=%s", hwnd)

    _apply_caption_palette(dwmapi, hwnd, mode, theme_manager)


def _get_hwnd(widget: QWidget) -> int:
    # NOTE:
    # QWidget.winId() は未生成のネイティブハンドルを生成し得る。
    # その結果 WinIdChange 等が再発火して eventFilter が再入し、
    # 環境によっては stack overflow になることがあるため、生成済みの場合のみ参照する。
    try:
        if not widget.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            return 0
    except Exception:
        # testAttribute が使えない/失敗する場合は安全側に倒す
        return 0

    try:
        win_id = widget.winId()
    except Exception:
        return 0
    try:
        return int(win_id)
    except Exception:
        return 0


def _apply_caption_palette(dwmapi, hwnd: int, mode: ThemeMode, theme_manager: ThemeManager) -> None:
    try:
        import ctypes
    except ImportError:  # pragma: no cover
        return

    if mode == ThemeMode.DARK:
        caption_color = _colorref_from_theme(theme_manager.get_color(ThemeKey.WINDOW_BACKGROUND))
        text_color = _colorref_from_theme(theme_manager.get_color(ThemeKey.TEXT_PRIMARY))
        border_color = _colorref_from_theme(theme_manager.get_color(ThemeKey.BORDER_DARK))
    else:
        caption_color = None
        text_color = None
        border_color = None

    _set_dwm_color(dwmapi, hwnd, 35, caption_color)  # DWMWA_CAPTION_COLOR
    _set_dwm_color(dwmapi, hwnd, 36, text_color)  # DWMWA_TEXT_COLOR
    _set_dwm_color(dwmapi, hwnd, 34, border_color)  # DWMWA_BORDER_COLOR


def _set_dwm_color(dwmapi, hwnd: int, attr: int, colorref: Optional[int]) -> None:
    try:
        import ctypes
    except ImportError:  # pragma: no cover
        return

    COLOR_UNSET = 0xFFFFFFFF
    value = COLOR_UNSET if colorref is None else colorref
    color_value = ctypes.c_int(value)
    result = dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(color_value), ctypes.sizeof(color_value))
    if result != 0:
        logger.debug("DwmSetWindowAttribute attr=%s failed with code=%s", attr, result)


def _colorref_from_theme(color_text: str) -> Optional[int]:
    if not color_text:
        return None
    color_text = color_text.strip()
    try:
        if color_text.startswith("#") and len(color_text) >= 7:
            r = int(color_text[1:3], 16)
            g = int(color_text[3:5], 16)
            b = int(color_text[5:7], 16)
        elif color_text.startswith("rgba"):
            numbers = re.findall(r"[0-9.]+", color_text)
            if len(numbers) < 3:
                return None
            r, g, b = (int(float(numbers[i])) for i in range(3))
        else:
            return None
    except (ValueError, TypeError):
        return None
    return (b << 16) | (g << 8) | r
