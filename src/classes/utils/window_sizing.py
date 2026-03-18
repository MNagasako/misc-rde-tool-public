"""Main-window sizing helpers shared across UI modules."""

from __future__ import annotations

MAIN_WINDOW_MIN_WIDTH = 200
MAIN_WINDOW_MIN_HEIGHT = 540
UNBOUNDED_QT_SIZE = 16777215


def get_available_screen_geometry(window):
    """Return the available geometry of the window's current screen."""

    try:
        screen = None
        if window is not None and hasattr(window, "screen"):
            screen = window.screen()
        if screen is None and window is not None and hasattr(window, "frameGeometry"):
            try:
                from qt_compat.widgets import QApplication

                screen = QApplication.screenAt(window.frameGeometry().center())
            except Exception:
                screen = None
        if screen is None:
            try:
                from qt_compat.widgets import QApplication

                screen = QApplication.primaryScreen()
            except Exception:
                screen = None
        return screen.availableGeometry() if screen is not None else None
    except Exception:
        return None


def _get_window_frame_extra_size(window) -> tuple[int, int]:
    """Best-effort frame extra size: title bar and outer border included by the OS."""

    if window is None:
        return 0, 0
    try:
        if not hasattr(window, "frameGeometry"):
            return 0, 0
        frame = window.frameGeometry()
        frame_width = int(frame.width())
        frame_height = int(frame.height())
        client_width = int(window.width()) if hasattr(window, "width") else frame_width
        client_height = int(window.height()) if hasattr(window, "height") else frame_height
        return max(0, frame_width - client_width), max(0, frame_height - client_height)
    except Exception:
        return 0, 0


def get_main_window_min_height() -> int:
    """Return the unified main-window minimum height."""

    return MAIN_WINDOW_MIN_HEIGHT


def is_window_maximized(window) -> bool:
    """Best-effort maximized-state check."""

    if window is None or not hasattr(window, "isMaximized"):
        return False
    try:
        return bool(window.isMaximized())
    except Exception:
        return False


def set_main_window_minimum_size(window, min_width: int = MAIN_WINDOW_MIN_WIDTH) -> None:
    """Apply the shared main-window minimum size."""

    if window is None:
        return
    try:
        if hasattr(window, "setMinimumSize"):
            window.setMinimumSize(int(min_width), MAIN_WINDOW_MIN_HEIGHT)
            return
        if hasattr(window, "setMinimumWidth"):
            window.setMinimumWidth(int(min_width))
        if hasattr(window, "setMinimumHeight"):
            window.setMinimumHeight(MAIN_WINDOW_MIN_HEIGHT)
    except Exception:
        return


def clear_main_window_size_constraints(window, min_width: int = MAIN_WINDOW_MIN_WIDTH) -> None:
    """Release fixed-size constraints while preserving the shared minimum height."""

    if window is None:
        return

    try:
        if hasattr(window, "_fixed_aspect_ratio"):
            window._fixed_aspect_ratio = None
    except Exception:
        pass

    set_main_window_minimum_size(window, min_width=min_width)

    try:
        if hasattr(window, "setMaximumSize"):
            window.setMaximumSize(UNBOUNDED_QT_SIZE, UNBOUNDED_QT_SIZE)
    except Exception:
        pass

    try:
        if hasattr(window, "setMinimumWidth"):
            window.setMinimumWidth(int(min_width))
        if hasattr(window, "setMaximumWidth"):
            window.setMaximumWidth(UNBOUNDED_QT_SIZE)
    except Exception:
        pass


def center_main_window_horizontally(window) -> bool:
    """Center a top-level window horizontally on its current screen while preserving Y."""

    if window is None or not hasattr(window, "move"):
        return False
    if is_window_maximized(window):
        return False

    try:
        available = get_available_screen_geometry(window)
        if available is None:
            return False
        frame = window.frameGeometry() if hasattr(window, "frameGeometry") else None
        frame_width = int(frame.width()) if frame is not None else int(window.width())
        frame_height = int(frame.height()) if frame is not None else int(window.height())
        current_y = int(frame.y()) if frame is not None else int(window.y())

        target_x = int(available.x() + (available.width() - frame_width) / 2)
        min_y = int(available.y())
        max_y = int(available.y() + available.height() - frame_height)
        clamped_y = min(max(current_y, min_y), max_y if max_y >= min_y else min_y)
        window.move(target_x, clamped_y)
        return True
    except Exception:
        return False


def center_window_on_screen(window) -> bool:
    """Center a top-level window on its current screen while keeping the full frame visible."""

    if window is None or not hasattr(window, "move"):
        return False
    if is_window_maximized(window):
        return False

    try:
        available = get_available_screen_geometry(window)
        if available is None:
            return False

        frame = window.frameGeometry() if hasattr(window, "frameGeometry") else None
        frame_width = int(frame.width()) if frame is not None else int(window.width())
        frame_height = int(frame.height()) if frame is not None else int(window.height())

        max_x = int(available.x() + available.width() - frame_width)
        max_y = int(available.y() + available.height() - frame_height)
        target_x = int(available.x() + max(0, (available.width() - frame_width) / 2))
        target_y = int(available.y() + max(0, (available.height() - frame_height) / 2))
        clamped_x = min(max(target_x, int(available.x())), max_x if max_x >= int(available.x()) else int(available.x()))
        clamped_y = min(max(target_y, int(available.y())), max_y if max_y >= int(available.y()) else int(available.y()))
        window.move(clamped_x, clamped_y)
        return True
    except Exception:
        return False


def fit_main_window_height_to_screen(window) -> bool:
    """Resize the main window height to the current screen while preserving resize freedom."""

    if window is None or not hasattr(window, "resize"):
        return False
    if is_window_maximized(window):
        return False

    try:
        available = get_available_screen_geometry(window)
        if available is None:
            return False

        _, frame_extra_height = _get_window_frame_extra_size(window)
        target_height = max(MAIN_WINDOW_MIN_HEIGHT, int(available.height()) - int(frame_extra_height))
        current_width = int(window.width()) if hasattr(window, "width") else None
        if current_width is None:
            return False
        window.resize(current_width, target_height)
        return True
    except Exception:
        return False


def resize_main_window(window, width: int | None = None, height: int | None = None) -> bool:
    """Resize a window unless it is currently maximized."""

    if window is None or not hasattr(window, "resize"):
        return False
    if is_window_maximized(window):
        return False

    try:
        current_size = window.size() if hasattr(window, "size") else None
        target_width = int(width) if width is not None else int(current_size.width())
        target_height = int(height) if height is not None else int(current_size.height())
        window.resize(target_width, target_height)
        if width is not None:
            center_main_window_horizontally(window)
        return True
    except Exception:
        return False