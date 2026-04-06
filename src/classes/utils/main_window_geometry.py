"""Mode/tab-scoped main-window geometry persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from qt_compat.core import QObject, QTimer

from classes.managers.app_config_manager import get_config_manager
from classes.utils.window_sizing import (
    MAIN_WINDOW_MIN_HEIGHT,
    MAIN_WINDOW_MIN_WIDTH,
    center_window_on_screen,
    clamp_window_geometry,
    get_available_screen_geometry,
    is_window_maximized,
    resolve_centered_window_geometry,
)


@dataclass(frozen=True)
class MainWindowGeometryContext:
    mode_key: str
    tab_index: Optional[int] = None
    tab_key: Optional[str] = None
    tab_title: Optional[str] = None


@dataclass(frozen=True)
class MainWindowGeometryPolicy:
    preferred_width: Optional[int] = None
    preferred_height: Optional[int] = None
    width_ratio: Optional[float] = None
    height_ratio: Optional[float] = 1.0
    fit_available_height_on_first_show: bool = False
    geometry_revision: int = 0
    min_width: int = MAIN_WINDOW_MIN_WIDTH
    min_height: int = MAIN_WINDOW_MIN_HEIGHT
    keep_current_width: bool = False
    keep_current_height: bool = False
    center_on_first_show: bool = True


def sanitize_geometry_key_part(value: str | None, fallback: str = "default") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return fallback
    result = []
    previous_dash = False
    for char in raw:
        if ("a" <= char <= "z") or ("0" <= char <= "9"):
            result.append(char)
            previous_dash = False
            continue
        if char in {"_", "-"}:
            if not previous_dash:
                result.append("-")
                previous_dash = True
            continue
        if not previous_dash:
            result.append("-")
            previous_dash = True
    normalized = "".join(result).strip("-")
    return normalized or fallback


class MainWindowGeometryManager(QObject):
    def __init__(self, window, config_manager=None):
        qt_parent = window if isinstance(window, QObject) else None
        super().__init__(qt_parent)
        self._window = window
        self._config_manager = config_manager or get_config_manager()
        self._mode_key: Optional[str] = None
        self._tab_widget = None
        self._tab_key_resolver: Optional[Callable[[int], str]] = None
        self._policy_resolver: Optional[Callable[[MainWindowGeometryContext], MainWindowGeometryPolicy]] = None
        self._current_tab_index: Optional[int] = None
        self._applying = False
        self._active = False
        self._suspend_capture_until_applied = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_config)
        try:
            self._window.installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API
        try:
            if not self._active or obj is not self._window:
                return False
            if self._suspend_capture_until_applied:
                return False
            event_type = event.type()
            if event_type in (event.Type.Move, event.Type.Resize, event.Type.WindowStateChange):
                if not self._applying and getattr(self._window, "isVisible", lambda: False)():
                    self.capture_current_geometry(schedule_save=True)
        except Exception:
            return False
        return False

    def configure(
        self,
        *,
        mode_key: str,
        tab_widget=None,
        tab_key_resolver: Optional[Callable[[int], str]] = None,
        policy_resolver: Optional[Callable[[MainWindowGeometryContext], MainWindowGeometryPolicy]] = None,
    ) -> None:
        self.save_current_geometry(force=True)
        self._disconnect_tab_widget()
        self._mode_key = sanitize_geometry_key_part(mode_key, fallback="mode")
        self._tab_widget = tab_widget
        self._tab_key_resolver = tab_key_resolver
        self._policy_resolver = policy_resolver
        self._current_tab_index = self._safe_current_tab_index()
        self._active = True
        self._suspend_capture_until_applied = True
        self._connect_tab_widget()

    def clear(self) -> None:
        self.save_current_geometry(force=True)
        self._disconnect_tab_widget()
        self._mode_key = None
        self._tab_widget = None
        self._tab_key_resolver = None
        self._policy_resolver = None
        self._current_tab_index = None
        self._active = False
        self._suspend_capture_until_applied = False

    def apply_current_geometry(self) -> None:
        context = self.current_context()
        if context is None:
            self._suspend_capture_until_applied = False
            return

        self._suspend_capture_until_applied = False
        policy = self._policy_for_context(context)
        prefix = self._context_prefix(context)
        stored_revision = 0
        try:
            stored_revision = int(self._config_manager.get(f"{prefix}.geometry_revision", 0) or 0)
        except Exception:
            stored_revision = 0
        saved_geometry_is_current = stored_revision >= int(policy.geometry_revision)

        maximized = bool(self._config_manager.get(f"{prefix}.maximized", False))
        if maximized and saved_geometry_is_current:
            try:
                self._window.showMaximized()
            except Exception:
                pass
            return

        size_data = self._config_manager.get(f"{prefix}.size", None)
        position_data = self._config_manager.get(f"{prefix}.position", None)
        if saved_geometry_is_current and isinstance(size_data, dict) and isinstance(position_data, dict):
            try:
                width = int(size_data.get("width", self._window.width()))
                height = int(size_data.get("height", self._window.height()))
                x = int(position_data.get("x", self._window.x()))
                y = int(position_data.get("y", self._window.y()))
                self._apply_geometry(width, height, x, y)
                return
            except Exception:
                pass

        default_width, default_height = self._default_size_for_context(context, policy=policy)
        if self._should_center_on_first_show(context, policy=policy):
            width, height, move_x, move_y = resolve_centered_window_geometry(
                self._window,
                default_width,
                default_height,
            )
        else:
            width, height, move_x, move_y = clamp_window_geometry(
                self._window,
                default_width,
                default_height,
                self._window.x() if hasattr(self._window, "x") else 0,
                self._window.y() if hasattr(self._window, "y") else 0,
            )
        self._apply_geometry(width, height, move_x, move_y)
        self.capture_current_geometry(schedule_save=True)

    def capture_current_geometry(self, *, schedule_save: bool = False, tab_index: Optional[int] = None) -> None:
        context = self.current_context(tab_index=tab_index)
        if context is None:
            return

        prefix = self._context_prefix(context)
        policy = self._policy_for_context(context)
        try:
            if is_window_maximized(self._window):
                self._config_manager.set(f"{prefix}.maximized", True)
            else:
                self._config_manager.set(f"{prefix}.maximized", False)
                self._config_manager.set(
                    f"{prefix}.size",
                    {"width": int(self._window.width()), "height": int(self._window.height())},
                )
                self._config_manager.set(
                    f"{prefix}.position",
                    {"x": int(self._window.x()), "y": int(self._window.y())},
                )
                self._config_manager.set(f"{prefix}.geometry_revision", int(policy.geometry_revision))
        except Exception:
            return

        if schedule_save:
            try:
                self._save_timer.start(150)
            except Exception:
                self._flush_config()

    def save_current_geometry(self, *, force: bool = False) -> None:
        self.capture_current_geometry(schedule_save=not force)
        if force:
            self._flush_config()

    def current_context(self, tab_index: Optional[int] = None) -> Optional[MainWindowGeometryContext]:
        if not self._active or not self._mode_key:
            return None
        if self._tab_widget is None:
            return MainWindowGeometryContext(mode_key=self._mode_key)

        index = self._safe_current_tab_index() if tab_index is None else int(tab_index)
        if index < 0:
            return MainWindowGeometryContext(mode_key=self._mode_key)
        tab_key = self._resolve_tab_key(index)
        tab_title = None
        try:
            tab_title = str(self._tab_widget.tabText(index) or "")
        except Exception:
            tab_title = None
        return MainWindowGeometryContext(
            mode_key=self._mode_key,
            tab_index=index,
            tab_key=tab_key,
            tab_title=tab_title,
        )

    def _connect_tab_widget(self) -> None:
        if self._tab_widget is None or not hasattr(self._tab_widget, "currentChanged"):
            return
        try:
            self._tab_widget.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

    def _disconnect_tab_widget(self) -> None:
        if self._tab_widget is None or not hasattr(self._tab_widget, "currentChanged"):
            return
        try:
            self._tab_widget.currentChanged.disconnect(self._on_tab_changed)
        except Exception:
            pass

    def _on_tab_changed(self, index: int) -> None:
        if self._applying:
            return
        previous_index = self._current_tab_index
        if previous_index is not None and previous_index != index:
            self.capture_current_geometry(schedule_save=True, tab_index=previous_index)
        self._current_tab_index = int(index)
        self._suspend_capture_until_applied = True
        self.apply_current_geometry()

    def _resolve_tab_key(self, index: int) -> str:
        if self._tab_key_resolver is not None:
            try:
                return sanitize_geometry_key_part(self._tab_key_resolver(index), fallback=f"tab-{index}")
            except Exception:
                pass
        try:
            title = str(self._tab_widget.tabText(index) or "")
        except Exception:
            title = ""
        return sanitize_geometry_key_part(f"tab-{index}-{title}", fallback=f"tab-{index}")

    def _safe_current_tab_index(self) -> Optional[int]:
        if self._tab_widget is None or not hasattr(self._tab_widget, "currentIndex"):
            return None
        try:
            return int(self._tab_widget.currentIndex())
        except Exception:
            return None

    def _context_prefix(self, context: MainWindowGeometryContext) -> str:
        base = f"ui.main_window.{context.mode_key}"
        if context.tab_key:
            return f"{base}.tabs.{context.tab_key}"
        return base

    def _policy_for_context(self, context: MainWindowGeometryContext) -> MainWindowGeometryPolicy:
        if self._policy_resolver is None:
            return MainWindowGeometryPolicy()
        try:
            policy = self._policy_resolver(context)
            if isinstance(policy, MainWindowGeometryPolicy):
                return policy
        except Exception:
            pass
        return MainWindowGeometryPolicy()

    def _default_size_for_context(
        self,
        context: MainWindowGeometryContext,
        *,
        policy: Optional[MainWindowGeometryPolicy] = None,
    ) -> tuple[int, int]:
        policy = policy or self._policy_for_context(context)
        available = get_available_screen_geometry(self._window)
        if available is None:
            return int(self._window.width()), int(self._window.height())

        frame_width = 0
        frame_height = 0
        try:
            frame = self._window.frameGeometry()
            frame_width = max(0, int(frame.width()) - int(self._window.width()))
            frame_height = max(0, int(frame.height()) - int(self._window.height()))
        except Exception:
            pass

        max_width = max(policy.min_width, int(available.width()) - frame_width)
        max_height = max(policy.min_height, int(available.height()) - frame_height)

        if policy.keep_current_width:
            width = int(self._window.width())
        elif policy.preferred_width is not None:
            width = int(policy.preferred_width)
        elif policy.width_ratio is not None:
            width = int(available.width() * float(policy.width_ratio))
        else:
            try:
                width = int(self._window.sizeHint().width())
            except Exception:
                width = int(self._window.width())

        if policy.keep_current_height:
            height = int(self._window.height())
        elif policy.preferred_height is not None:
            height = int(policy.preferred_height)
        elif policy.height_ratio is not None:
            height = int(available.height() * float(policy.height_ratio))
        else:
            height = max_height

        width = max(policy.min_width, min(width, max_width))
        height = max(policy.min_height, min(height, max_height))
        return width, height

    def _should_center_on_first_show(
        self,
        context: MainWindowGeometryContext,
        *,
        policy: Optional[MainWindowGeometryPolicy] = None,
    ) -> bool:
        policy = policy or self._policy_for_context(context)
        return bool(policy.center_on_first_show)

    def _apply_geometry(self, width: int, height: int, x: int, y: int) -> None:
        clamped_width, clamped_height, clamped_x, clamped_y = clamp_window_geometry(
            self._window,
            int(width),
            int(height),
            int(x),
            int(y),
        )
        self._applying = True
        try:
            self._window.resize(clamped_width, clamped_height)
            self._window.move(clamped_x, clamped_y)
        finally:
            self._applying = False

    def _flush_config(self) -> None:
        try:
            self._config_manager.save()
        except Exception:
            return