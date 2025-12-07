import logging
from typing import Callable, List

from qt_compat.widgets import QWidget

logger = logging.getLogger(__name__)


class RefreshOnShowWidget(QWidget):
    """QWidget that automatically reruns callbacks every time it becomes visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._show_refresh_callbacks: List[Callable[[], None]] = []
        self._auto_refresh_enabled: bool = True

    def add_show_refresh_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback that is invoked whenever the widget is shown."""
        if not callable(callback):
            return
        if callback not in self._show_refresh_callbacks:
            self._show_refresh_callbacks.append(callback)

    def trigger_show_refresh(self, reason: str = "manual") -> None:
        """Run all registered callbacks immediately."""
        if not self._show_refresh_callbacks:
            return
        for callback in list(self._show_refresh_callbacks):
            try:
                callback()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Show refresh callback failed (%s): %s", reason, exc, exc_info=True)

    def set_auto_refresh_enabled(self, enabled: bool) -> None:
        self._auto_refresh_enabled = bool(enabled)

    def showEvent(self, event):  # noqa: N802 - Qt API requires camelCase
        super().showEvent(event)
        if self._auto_refresh_enabled and self.isVisible():
            self.trigger_show_refresh("showEvent")
