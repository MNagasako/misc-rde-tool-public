from __future__ import annotations

from datetime import datetime

from qt_compat.core import Qt, QThread, Signal
from qt_compat.widgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from classes.core.cache_registry import build_cache_runtime_context, get_cache_registry


class _CacheRefreshThread(QThread):
    progress = Signal(str, int, int, str)
    completed = Signal(str, bool, str)

    def __init__(self, cache_id: str, registry, runtime_context, parent=None):
        super().__init__(parent)
        self._cache_id = str(cache_id or "")
        self._registry = registry
        self._runtime_context = runtime_context

    def run(self) -> None:  # noqa: D401
        try:
            result = self._registry.refresh_cache(
                self._cache_id,
                self._runtime_context,
                progress_callback=lambda current, total, message: self.progress.emit(
                    self._cache_id,
                    int(current),
                    int(total),
                    str(message),
                ),
            )
            self.completed.emit(self._cache_id, bool(result.refreshed), str(result.message or ""))
        except Exception as exc:
            self.completed.emit(self._cache_id, False, str(exc))


class CacheManagementTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings_direct_tab = True
        self._registry = get_cache_registry()
        self._row_cache_ids: list[str] = []
        self._snapshots_by_id: dict[str, object] = {}
        self._operation_states: dict[str, tuple[str, str]] = {}
        self._refresh_threads: dict[str, _CacheRefreshThread] = {}
        self._setup_ui()
        try:
            self.destroyed.connect(self._on_destroyed)
        except Exception:
            pass
        self.refresh_caches()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel("キャッシュ")
        header.setObjectName("cacheManagementHeader")
        layout.addWidget(header)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton("再読み込み")
        self.refresh_button.clicked.connect(self.refresh_caches)
        self.clear_safe_button = QPushButton("安全なキャッシュを全てクリア")
        self.clear_safe_button.clicked.connect(self._clear_safe_caches)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.clear_safe_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.operation_label = QLabel("")
        self.operation_label.setWordWrap(True)
        self.operation_label.setVisible(False)
        layout.addWidget(self.operation_label)

        self.operation_progress = QProgressBar(self)
        self.operation_progress.setVisible(False)
        self.operation_progress.setRange(0, 0)
        layout.addWidget(self.operation_progress)

        self.table = QTableWidget(0, 11, self)
        self.table.setHorizontalHeaderLabels([
            "名前",
            "対象機能",
            "種別",
            "保存先",
            "作成",
            "更新",
            "サイズ",
            "件数",
            "状態",
            "備考",
            "操作",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setMinimumHeight(320)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(9, QHeaderView.Stretch)
        header_view.setSectionResizeMode(10, QHeaderView.ResizeToContents)

        layout.addWidget(self.table, 1)

    def _runtime_context(self):
        return build_cache_runtime_context(settings_widget=self)

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "-"
        try:
            return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        value = float(max(0, int(size_bytes or 0)))
        unit = units[0]
        for candidate in units:
            unit = candidate
            if value < 1024.0 or candidate == units[-1]:
                break
            value /= 1024.0
        if unit == "B":
            return f"{int(value)} {unit}"
        return f"{value:.1f} {unit}"

    def refresh_caches(self) -> None:
        snapshots = self._registry.get_snapshots(self._runtime_context())
        self._snapshots_by_id = {snapshot.cache_id: snapshot for snapshot in snapshots}
        self._row_cache_ids = [snapshot.cache_id for snapshot in snapshots]
        self.table.setRowCount(len(snapshots))

        active_count = 0
        total_size = 0
        any_busy = bool(self._refresh_threads)
        for row, snapshot in enumerate(snapshots):
            if snapshot.active:
                active_count += 1
            total_size += int(snapshot.size_bytes or 0)

            operation_state, operation_message = self._operation_states.get(snapshot.cache_id, ("", ""))
            status_text = "有効" if snapshot.active else "空"
            if operation_state == "running":
                status_text = f"{status_text} / 更新中"
            elif operation_state == "success":
                status_text = f"{status_text} / 更新済"
            elif operation_state == "error":
                status_text = f"{status_text} / 更新失敗"

            values = [
                snapshot.name,
                snapshot.feature,
                snapshot.cache_type,
                snapshot.storage_path or "-",
                self._format_datetime(snapshot.created_at),
                self._format_datetime(snapshot.updated_at),
                self._format_size(snapshot.size_bytes),
                "-" if snapshot.item_count is None else str(snapshot.item_count),
                status_text,
                snapshot.notes or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {6, 7, 8}:
                    item.setTextAlignment(Qt.AlignCenter)
                if column in {3, 9}:
                    item.setToolTip(str(value))
                if column == 8 and operation_message:
                    item.setToolTip(operation_message)
                self.table.setItem(row, column, item)

            self.table.setCellWidget(row, 10, self._build_action_widget(snapshot, disable_all=any_busy))

        self.summary_label.setText(
            f"対象 {len(snapshots)} 件 / 有効 {active_count} 件 / 合計サイズ {self._format_size(total_size)}"
        )
        self.table.resizeRowsToContents()
        self.clear_safe_button.setEnabled(not any_busy)
        self._sync_operation_widgets()

    def _build_action_widget(self, snapshot, *, disable_all: bool) -> QWidget:
        container = QWidget(self.table)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if snapshot.refreshable:
            refresh_button = QPushButton("更新")
            refresh_button.setEnabled(not disable_all)
            refresh_button.clicked.connect(
                lambda _checked=False, cache_id=snapshot.cache_id: self._start_refresh_cache(cache_id)
            )
            refresh_button.setToolTip(str(snapshot.refresh_reason or "キャッシュを再取得・再集計します"))
            layout.addWidget(refresh_button)
        else:
            refresh_label = QLabel("更新不可")
            refresh_label.setToolTip(str(snapshot.refresh_reason or "再生成経路がありません"))
            layout.addWidget(refresh_label)

        if snapshot.clearable:
            clear_button = QPushButton("クリア")
            clear_button.setEnabled(not disable_all)
            clear_button.clicked.connect(lambda _checked=False, cache_id=snapshot.cache_id: self._clear_cache(cache_id))
            layout.addWidget(clear_button)

        layout.addStretch(1)
        return container

    def _sync_operation_widgets(self) -> None:
        running = next(iter(self._refresh_threads.keys()), None)
        if running:
            self.operation_label.setVisible(True)
            if not self.operation_label.text().strip():
                snapshot = self._snapshots_by_id.get(running)
                name = getattr(snapshot, "name", running)
                self.operation_label.setText(f"{name} を更新中...")
            self.operation_progress.setVisible(True)
            return

        self.operation_progress.setVisible(False)
        self.operation_progress.setRange(0, 0)
        self.operation_progress.setValue(0)
        self.operation_label.setVisible(bool(self.operation_label.text().strip()))

    def _start_refresh_cache(self, cache_id: str) -> None:
        if self._refresh_threads:
            QMessageBox.warning(self, "キャッシュ更新", "他のキャッシュ更新が実行中です。完了後に再試行してください。")
            return

        snapshot = self._snapshots_by_id.get(cache_id)
        if snapshot is None or not bool(getattr(snapshot, "refreshable", False)):
            QMessageBox.warning(self, "キャッシュ更新", "選択したキャッシュは更新できません。")
            return

        self._operation_states[cache_id] = ("running", "更新中")
        self.operation_label.setText(f"{snapshot.name} を更新中...")
        self.operation_label.setVisible(True)
        self.operation_progress.setRange(0, 0)
        self.operation_progress.setVisible(True)

        thread = _CacheRefreshThread(cache_id, self._registry, self._runtime_context())
        thread.progress.connect(self._on_refresh_progress)
        thread.completed.connect(self._on_refresh_completed)
        thread.finished.connect(self._on_refresh_thread_finished)
        self._refresh_threads[cache_id] = thread
        self.refresh_caches()
        thread.start()

    def _on_refresh_progress(self, cache_id: str, current: int, total: int, message: str) -> None:
        snapshot = self._snapshots_by_id.get(cache_id)
        name = getattr(snapshot, "name", cache_id)
        self._operation_states[cache_id] = ("running", str(message))
        self.operation_label.setText(f"{name}: {message}")
        self.operation_label.setVisible(True)
        if total > 0:
            self.operation_progress.setRange(0, int(total))
            self.operation_progress.setValue(max(0, min(int(current), int(total))))
        else:
            self.operation_progress.setRange(0, 0)
        self.operation_progress.setVisible(True)

    def _on_refresh_completed(self, cache_id: str, success: bool, message: str) -> None:
        self._operation_states[cache_id] = (("success" if success else "error"), str(message or ""))
        self.operation_label.setText(str(message or ""))
        self.operation_label.setVisible(bool(message))
        self.refresh_caches()

    def _on_refresh_thread_finished(self) -> None:
        thread = self.sender()
        cache_id = None
        for candidate_id, candidate_thread in list(self._refresh_threads.items()):
            if candidate_thread is thread:
                cache_id = candidate_id
                self._refresh_threads.pop(candidate_id, None)
                break
        try:
            if isinstance(thread, QThread):
                thread.wait(1000)
                thread.deleteLater()
        except Exception:
            pass
        if cache_id is not None and cache_id not in self._operation_states:
            self._operation_states[cache_id] = ("", "")
        self._sync_operation_widgets()
        self.refresh_caches()

    def _on_destroyed(self, *_args) -> None:
        for thread in list(self._refresh_threads.values()):
            try:
                thread.wait(5000)
            except Exception:
                pass

    def _clear_cache(self, cache_id: str) -> None:
        if self._refresh_threads:
            QMessageBox.warning(self, "キャッシュクリア", "キャッシュ更新中はクリアできません。")
            return

        reply = QMessageBox.question(
            self,
            "キャッシュクリア確認",
            "選択したキャッシュをクリアします。よろしいですか。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        result = self._registry.clear_cache(cache_id, self._runtime_context())
        if result.cleared:
            QMessageBox.information(self, "キャッシュクリア", result.message)
        else:
            QMessageBox.warning(self, "キャッシュクリア", result.message)
        self.refresh_caches()

    def _clear_safe_caches(self) -> None:
        if self._refresh_threads:
            QMessageBox.warning(self, "キャッシュクリア", "キャッシュ更新中は一括クリアできません。")
            return

        reply = QMessageBox.question(
            self,
            "安全なキャッシュの一括クリア確認",
            "安全なキャッシュを一括でクリアします。よろしいですか。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        results = self._registry.clear_safe_caches(self._runtime_context())
        success_count = sum(1 for result in results if result.cleared)
        failure_messages = [result.message for result in results if not result.cleared]
        message = f"{success_count} 件のキャッシュをクリアしました。"
        if failure_messages:
            message += "\n" + "\n".join(failure_messages)
        QMessageBox.information(self, "キャッシュクリア", message)
        self.refresh_caches()