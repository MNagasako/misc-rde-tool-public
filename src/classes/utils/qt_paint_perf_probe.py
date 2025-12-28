from __future__ import annotations

import logging
import time
from typing import Callable, Optional


class QtPaintPerfProbe:
    """Qtの描画(PAINT)とレイアウト更新が落ち着くまでの時間を計測する。

    目的:
    - モード切替などで「処理は終わっているが描画が続く」問題を切り分ける
    - 初回Paintと、一定時間イベントが発生しない(収束)までをログ化する

    実装方針:
    - QApplication へ eventFilter を仕掛け、root配下のWidgetイベントを監視
    - PERF有効時のみログを出す（PerfMonitor側でゲート）
    """

    def __init__(
        self,
        root_widget,
        *,
        label: str,
        logger: Optional[logging.Logger] = None,
        settle_ms: int = 250,
        timeout_ms: int = 15000,
        switch_t0: Optional[float] = None,
        on_finished: Optional[Callable[["QtPaintPerfProbe"], None]] = None,
    ) -> None:
        self._root = root_widget
        self._label = str(label)
        self._logger = logger or logging.getLogger("RDE_WebView")
        self._settle_ms = int(settle_ms)
        self._timeout_ms = int(timeout_ms)
        self._switch_t0 = float(switch_t0) if switch_t0 is not None else None
        self._on_finished = on_finished

        self._installed = False
        self._finished = False

        self._first_paint_at: Optional[float] = None
        now = time.perf_counter()
        self._last_activity_at = now
        self._start_at = now

        self._qt = None
        self._app = None
        self._settle_timer = None
        self._timeout_timer = None

    @property
    def finished(self) -> bool:
        return bool(self._finished)

    def start(self) -> bool:
        """プローブを開始する。Qtが利用できない場合はFalse。"""
        if self._finished:
            return False
        try:
            from qt_compat.core import QObject, QEvent, QTimer
            from qt_compat.widgets import QApplication, QWidget
        except Exception:
            return False

        if self._root is None:
            return False
        if not isinstance(self._root, QWidget):
            return False

        app = QApplication.instance()
        if app is None:
            return False

        self._qt = (QObject, QEvent, QTimer, QWidget)
        self._app = app

        # destroyed されたら安全に終了
        try:
            self._root.destroyed.connect(lambda *_: self.finish(reason="destroyed"))
        except Exception:
            pass

        # eventFilter は QObject を継承している必要があるため、内部QObjectを用意
        QObject, _, QTimer, _ = self._qt

        class _Filter(QObject):
            def __init__(self, outer: "QtPaintPerfProbe") -> None:
                super().__init__()
                self._outer = outer

            def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
                return self._outer._event_filter(obj, event)

        self._filter = _Filter(self)
        app.installEventFilter(self._filter)
        self._installed = True

        self._settle_timer = QTimer(self._filter)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._on_settle_timer)

        self._timeout_timer = QTimer(self._filter)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(lambda: self.finish(reason="timeout"))
        self._timeout_timer.start(self._timeout_ms)

        # 初回チェックを予約
        self._schedule_settle_check()

        # Ensure at least one update happens *after* the filter is installed.
        # On Windows, forcing an immediate repaint can trigger a fatal SEH in some
        # test/COM timing scenarios (e.g. 0x8001010d). Prefer a deferred update.
        try:
            if getattr(self._root, "isVisible", None) and self._root.isVisible():
                _, _, QTimer, _ = self._qt
                QTimer.singleShot(0, self._root.update)
        except Exception:
            pass
        return True

    def finish(self, *, reason: str) -> None:
        if self._finished:
            return
        self._finished = True

        try:
            if self._timeout_timer is not None:
                self._timeout_timer.stop()
        except Exception:
            pass
        try:
            if self._settle_timer is not None:
                self._settle_timer.stop()
        except Exception:
            pass

        try:
            if self._installed and self._app is not None and getattr(self, "_filter", None) is not None:
                self._app.removeEventFilter(self._filter)
        except Exception:
            pass

        # timeout のときだけ明示ログ（通常はfirst+settledが出る）
        try:
            if reason == "timeout":
                from classes.utils.perf_monitor import PerfMonitor

                PerfMonitor.mark(
                    f"ui:paint:timeout:{self._label}",
                    logger=self._logger,
                    elapsed_sec=round(time.perf_counter() - self._start_at, 6),
                )
        except Exception:
            pass

        try:
            if self._on_finished is not None:
                self._on_finished(self)
        except Exception:
            pass

    def _is_in_scope(self, obj) -> bool:
        if self._qt is None:
            return False
        _, _, _, QWidget = self._qt
        if obj is None or not isinstance(obj, QWidget):
            return False

        # In long-running widget test suites on Windows, Qt objects can be in a
        # transitional teardown state while still delivering events. Calling Qt
        # APIs (e.g. isAncestorOf) on such objects can crash the interpreter.
        try:
            from shiboken6 import isValid as _qt_is_valid  # type: ignore
        except Exception:
            _qt_is_valid = None

        try:
            if _qt_is_valid is not None:
                if not _qt_is_valid(self._root):
                    return False
                if not _qt_is_valid(obj):
                    return False
        except Exception:
            return False
        try:
            return obj is self._root or self._root.isAncestorOf(obj)
        except Exception:
            return False

    def _event_filter(self, obj, event) -> bool:
        if self._finished:
            return False
        if not self._is_in_scope(obj):
            return False

        try:
            _, QEvent, _, _ = self._qt
            et = event.type()
        except Exception:
            return False

        # Paint だけでなく Layout/UpdateRequest/Resize も「まだ落ち着いていない」サイン
        interesting = {
            QEvent.Paint,
            QEvent.LayoutRequest,
            QEvent.UpdateRequest,
            QEvent.Resize,
        }
        if et not in interesting:
            return False

        now = time.perf_counter()
        self._last_activity_at = now

        if et == QEvent.Paint and self._first_paint_at is None:
            self._first_paint_at = now
            try:
                from classes.utils.perf_monitor import PerfMonitor

                payload = {
                    "elapsed_sec": round(now - self._start_at, 6),
                }
                if self._switch_t0 is not None:
                    payload["since_switch_sec"] = round(now - self._switch_t0, 6)
                PerfMonitor.mark(f"ui:paint:first:{self._label}", logger=self._logger, **payload)
            except Exception:
                pass

        self._schedule_settle_check()
        return False

    def _schedule_settle_check(self) -> None:
        if self._finished or self._settle_timer is None:
            return
        try:
            self._settle_timer.start(self._settle_ms)
        except Exception:
            pass

    def _on_settle_timer(self) -> None:
        if self._finished:
            return
        now = time.perf_counter()
        idle_sec = now - self._last_activity_at
        settle_sec = self._settle_ms / 1000.0

        # まだ初回Paintが来ていないうちは収束扱いにしない
        if self._first_paint_at is None:
            self._schedule_settle_check()
            return

        if idle_sec < settle_sec:
            self._schedule_settle_check()
            return

        try:
            from classes.utils.perf_monitor import PerfMonitor

            payload = {
                "elapsed_sec": round(now - self._start_at, 6),
                "idle_sec": round(idle_sec, 6),
            }
            if self._switch_t0 is not None:
                payload["since_switch_sec"] = round(now - self._switch_t0, 6)
            PerfMonitor.mark(f"ui:paint:settled:{self._label}", logger=self._logger, **payload)
        except Exception:
            pass

        self.finish(reason="settled")
