from __future__ import annotations

import datetime
from typing import Optional

from qt_compat.core import Qt, QTimer, QUrl, Signal, Slot
from qt_compat.gui import QDesktopServices
from qt_compat.widgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
)


def open_url_in_browser(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        if QDesktopServices.openUrl(QUrl(u)):
            return True
    except Exception:
        pass

    # QDesktopServices can fail silently on some Windows envs; webbrowser is more reliable.
    try:
        import webbrowser

        return bool(webbrowser.open(u))
    except Exception:
        return False


class UpdateDownloadDialog(QDialog):
    """アプリ更新: ダウンロード/検証/インストール準備の進捗＋通信ログを表示する。"""

    log_line = Signal(str)
    status_changed = Signal(str)
    detail_changed = Signal(str)
    progress_bytes_changed = Signal(int, int, str)
    progress_percent_changed = Signal(int, str)
    finished_success = Signal(str)
    finished_error = Signal(str)

    def __init__(self, *, title: str = "更新", release_url: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)

        self._cancelled = False
        self._release_url = str(release_url or "").strip()

        root = QVBoxLayout(self)

        self._status = QLabel("準備中...", self)
        self._status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._status)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)  # indeterminate by default
        self._progress.setValue(0)
        root.addWidget(self._progress)

        self._detail = QLabel("", self)
        self._detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._detail)

        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        try:
            self._log.setMaximumBlockCount(2000)
        except Exception:
            pass
        root.addWidget(self._log, 1)

        btns = QHBoxLayout()

        self._open_site_btn = QPushButton("更新サイトを開く", self)
        self._open_site_btn.setEnabled(bool(self._release_url))
        self._open_site_btn.clicked.connect(self._on_open_site)
        btns.addWidget(self._open_site_btn)

        btns.addStretch(1)

        self._cancel_btn = QPushButton("キャンセル", self)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btns.addWidget(self._cancel_btn)

        root.addLayout(btns)

        # UIが固まって見えないよう、経過秒を最低限更新する
        self._started_at = datetime.datetime.now(datetime.timezone.utc)
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(500)
        self._heartbeat.timeout.connect(self._tick)
        self._heartbeat.start()

        # Thread-safe UI updates: any thread may emit these signals.
        self.log_line.connect(self._on_log_line, Qt.ConnectionType.QueuedConnection)
        self.status_changed.connect(self._on_status_changed, Qt.ConnectionType.QueuedConnection)
        self.detail_changed.connect(self._on_detail_changed, Qt.ConnectionType.QueuedConnection)
        self.progress_bytes_changed.connect(self._on_progress_bytes, Qt.ConnectionType.QueuedConnection)
        self.progress_percent_changed.connect(self._on_progress_percent, Qt.ConnectionType.QueuedConnection)
        self.finished_success.connect(self._on_finished_success, Qt.ConnectionType.QueuedConnection)
        self.finished_error.connect(self._on_finished_error, Qt.ConnectionType.QueuedConnection)

    def is_cancelled(self) -> bool:
        return bool(self._cancelled)

    def append_log(self, line: str) -> None:
        self.log_line.emit(str(line or ""))

    def set_status(self, text: str) -> None:
        self.status_changed.emit(str(text or ""))

    def set_detail(self, text: str) -> None:
        self.detail_changed.emit(str(text or ""))

    def set_indeterminate_toggle(self, indeterminate: bool) -> None:
        try:
            if indeterminate:
                if not (self._progress.minimum() == 0 and self._progress.maximum() == 0):
                    self._progress.setRange(0, 0)
                    self._progress.setValue(0)
            else:
                if self._progress.maximum() == 0 and self._progress.minimum() == 0:
                    self._progress.setRange(0, 100)
        except Exception:
            pass

    def set_progress_bytes(self, current: int, total: int, *, message: str = "") -> None:
        self.progress_bytes_changed.emit(int(current or 0), int(total or 0), str(message or ""))

    def set_progress_percent(self, percent: int, *, message: str = "") -> None:
        self.progress_percent_changed.emit(int(percent or 0), str(message or ""))

    def finish_success(self, message: str = "完了") -> None:
        self.finished_success.emit(str(message or ""))

    def finish_error(self, message: str) -> None:
        self.finished_error.emit(str(message or ""))

    def _tick(self) -> None:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            sec = int((now - self._started_at).total_seconds())
            title = self.windowTitle()
            if "(" in title:
                return
            # 余計なチラつきを避けるため、タイトルは触らない
            _ = sec
        except Exception:
            pass

    def _on_cancel(self) -> None:
        self._cancelled = True
        try:
            self._cancel_btn.setEnabled(False)
        except Exception:
            pass

    def _on_open_site(self) -> None:
        try:
            open_url_in_browser(self._release_url)
        except Exception:
            pass

    @Slot(str)
    def _on_log_line(self, line: str) -> None:
        text = str(line or "").rstrip("\n")
        if not text:
            return
        try:
            self._log.appendPlainText(text)
        except Exception:
            pass

    @Slot(str)
    def _on_status_changed(self, text: str) -> None:
        try:
            self._status.setText(str(text or ""))
        except Exception:
            pass

    @Slot(str)
    def _on_detail_changed(self, text: str) -> None:
        try:
            self._detail.setText(str(text or ""))
        except Exception:
            pass

    @Slot(int, int, str)
    def _on_progress_bytes(self, current: int, total: int, message: str) -> None:
        cur = int(current or 0)
        tot = int(total or 0)

        if tot > 0 and tot <= 2_000_000_000:
            try:
                if not (self._progress.minimum() == 0 and self._progress.maximum() == tot):
                    self._progress.setRange(0, tot)
                self._progress.setValue(max(0, min(cur, tot)))
            except Exception:
                pass
            pct = int((cur / tot) * 100) if tot else 0
            try:
                self._detail.setText(f"{cur:,}/{tot:,} bytes ({pct}%)")
            except Exception:
                pass
        else:
            self.set_indeterminate_toggle(True)
            try:
                self._detail.setText(f"{cur:,} bytes")
            except Exception:
                pass

        if message:
            try:
                self._status.setText(str(message))
            except Exception:
                pass

    @Slot(int, str)
    def _on_progress_percent(self, percent: int, message: str) -> None:
        p = max(0, min(int(percent or 0), 100))
        try:
            if not (self._progress.minimum() == 0 and self._progress.maximum() == 100):
                self._progress.setRange(0, 100)
            self._progress.setValue(p)
        except Exception:
            pass
        if message:
            try:
                self._status.setText(str(message))
            except Exception:
                pass

    @Slot(str)
    def _on_finished_success(self, message: str) -> None:
        try:
            self._heartbeat.stop()
        except Exception:
            pass
        try:
            self._status.setText(str(message or "完了"))
        except Exception:
            pass
        try:
            if not (self._progress.minimum() == 0 and self._progress.maximum() == 100):
                self._progress.setRange(0, 100)
            self._progress.setValue(100)
        except Exception:
            pass

    @Slot(str)
    def _on_finished_error(self, message: str) -> None:
        try:
            self._heartbeat.stop()
        except Exception:
            pass
        try:
            self._status.setText(str(message or "エラー"))
        except Exception:
            pass
        try:
            self.set_indeterminate_toggle(False)
        except Exception:
            pass
