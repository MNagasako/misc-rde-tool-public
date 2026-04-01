"""
外部アクセスモニター - UIウィジェット群

1. ExternalAccessMonitorBar  : メインウィンドウ下部のステータスバー (1行)
2. RecentAccessDialog        : 直近10件ダイアログ
3. FullAccessLogWindow       : 全アクセスログ表示ウィンドウ
"""

import logging
from typing import Optional

from qt_compat.core import Qt, QTimer, Signal, QObject
from qt_compat.widgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QLineEdit,
)
from classes.theme import ThemeKey, get_color, ThemeManager
from classes.core.external_access_monitor import (
    AccessRecord,
    ExternalAccessMonitorStore,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. ボトムモニターバー
# ---------------------------------------------------------------------------


class ExternalAccessMonitorBar(QWidget):
    """メインウィンドウ下部に配置する1行ステータスバー。

    クリックで最近10件ダイアログを開く。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("external_access_monitor_bar")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._icon_label = QLabel("🌐")
        self._icon_label.setFixedWidth(18)
        layout.addWidget(self._icon_label)

        self._text_label = QLabel("外部アクセス待機中...")
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._text_label)

        self.setLayout(layout)
        self._apply_theme()

        # テーマ変更時の更新
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

        # ストアのリスナーに登録
        store = ExternalAccessMonitorStore.instance()
        store.add_listener(self._on_new_record)

    # -- テーマ ---------------------------------------------------------------

    def _apply_theme(self) -> None:
        bg = get_color(ThemeKey.STATUS_BACKGROUND)
        fg = get_color(ThemeKey.STATUS_TEXT)
        border = get_color(ThemeKey.STATUS_BORDER)
        self.setStyleSheet(
            f"""
            #external_access_monitor_bar {{
                background-color: {bg};
                color: {fg};
                border-top: 1px solid {border};
            }}
            #external_access_monitor_bar QLabel {{
                color: {fg};
                font-size: 11px;
            }}
            """
        )

    # -- 更新 ---------------------------------------------------------------

    def _on_new_record(self, record: AccessRecord) -> None:
        """ストアからの通知 (ワーカースレッドから呼ばれる可能性あり)"""
        QTimer.singleShot(0, lambda: self._update_display(record))

    @staticmethod
    def _truncate_url(url: str, max_len: int = 60) -> str:
        """URLを表示用に切り詰める"""
        if not url or len(url) <= max_len:
            return url
        return url[:max_len - 3] + "..."

    def _update_display(self, record: AccessRecord) -> None:
        time_part = record.created_at[-8:] if len(record.created_at) >= 8 else record.created_at
        short_url = self._truncate_url(record.url, 60)
        if record.error_text:
            color = get_color(ThemeKey.STATUS_ERROR)
            text = f"{time_part}  {record.method} {record.host} — エラー  {short_url}"
        elif record.status_code >= 400:
            color = get_color(ThemeKey.STATUS_WARNING)
            text = f"{time_part}  {record.method} {record.host} — {record.status_code}  {short_url}"
        elif record.source_kind == "webview":
            color = get_color(ThemeKey.STATUS_SUCCESS)
            text = f"{time_part}  [WebView] {record.method} {record.host}  {short_url}"
        else:
            color = get_color(ThemeKey.STATUS_SUCCESS)
            text = (
                f"{time_part}  {record.method} {record.host} — "
                f"{record.status_code}  {record.duration_ms:.0f}ms  {short_url}"
            )
        self._text_label.setText(text)
        self._text_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    # -- クリック → 最近10件ダイアログ ----------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            dlg = RecentAccessDialog(self)
            dlg.exec()
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# 2. 最近10件ダイアログ
# ---------------------------------------------------------------------------


class RecentAccessDialog(QDialog):
    """直近10件のアクセスログを表示するモーダルダイアログ"""

    _COL_LABELS = ["日時", "メソッド", "ホスト", "ステータス", "時間(ms)", "URL"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("最近の外部アクセス (10件)")
        self.setMinimumSize(900, 340)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout()

        # テーブル
        self._table = QTableWidget()
        self._table.setColumnCount(len(self._COL_LABELS))
        self._table.setHorizontalHeaderLabels(self._COL_LABELS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._open_full_btn = QPushButton("全アクセスログを開く")
        self._open_full_btn.clicked.connect(self._open_full_log)
        btn_row.addWidget(self._open_full_btn)

        self._close_btn = QPushButton("閉じる")
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)
        self._apply_theme()
        self._load_data()

        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self) -> None:
        bg = get_color(ThemeKey.PANEL_BACKGROUND)
        fg = get_color(ThemeKey.TEXT_PRIMARY)
        self.setStyleSheet(
            f"QDialog {{ background-color: {bg}; color: {fg}; }}"
        )

    @staticmethod
    def _truncate_url(url: str, max_len: int = 80) -> str:
        if not url or len(url) <= max_len:
            return url
        return url[:max_len - 3] + "..."

    def _load_data(self) -> None:
        store = ExternalAccessMonitorStore.instance()
        records = store.get_recent(10)
        self._table.setRowCount(len(records))
        for i, rec in enumerate(records):
            self._table.setItem(i, 0, QTableWidgetItem(rec.created_at))
            self._table.setItem(i, 1, QTableWidgetItem(rec.method))
            self._table.setItem(i, 2, QTableWidgetItem(rec.host))
            if rec.source_kind == "webview":
                status_text = "WebView"
            elif rec.status_code:
                status_text = str(rec.status_code)
            else:
                status_text = rec.error_text[:30]
            status_item = QTableWidgetItem(status_text)
            self._table.setItem(i, 3, status_item)
            self._table.setItem(i, 4, QTableWidgetItem(f"{rec.duration_ms:.0f}"))
            self._table.setItem(i, 5, QTableWidgetItem(self._truncate_url(rec.url)))
        self._table.resizeColumnsToContents()

    def _open_full_log(self) -> None:
        self.close()
        win = FullAccessLogWindow(self.parent())
        win.show()


# ---------------------------------------------------------------------------
# 3. 全アクセスログウィンドウ
# ---------------------------------------------------------------------------


class FullAccessLogWindow(QDialog):
    """全アクセスログ表示ウィンドウ (モードレス)"""

    _COL_LABELS = [
        "ID", "日時", "メソッド", "ホスト", "URL",
        "ステータス", "時間(ms)", "ソース", "エラー",
    ]
    _PAGE_SIZE = 200

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("外部アクセスログ")
        self.setMinimumSize(900, 500)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.Window
        )

        self._offset = 0

        main_layout = QVBoxLayout()

        # フィルタ行
        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("メソッド:"))
        self._method_combo = QComboBox()
        self._method_combo.addItems(["", "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
        self._method_combo.setFixedWidth(90)
        filter_row.addWidget(self._method_combo)

        filter_row.addWidget(QLabel("ホスト:"))
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("部分一致フィルタ")
        self._host_edit.setFixedWidth(200)
        filter_row.addWidget(self._host_edit)

        self._search_btn = QPushButton("検索")
        self._search_btn.clicked.connect(self._search)
        filter_row.addWidget(self._search_btn)

        self._reload_btn = QPushButton("更新")
        self._reload_btn.clicked.connect(self._reload)
        filter_row.addWidget(self._reload_btn)

        filter_row.addStretch()

        self._count_label = QLabel("")
        filter_row.addWidget(self._count_label)

        main_layout.addLayout(filter_row)

        # テーブル
        self._table = QTableWidget()
        self._table.setColumnCount(len(self._COL_LABELS))
        self._table.setHorizontalHeaderLabels(self._COL_LABELS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)
        main_layout.addWidget(self._table)

        # ページングボタン
        page_row = QHBoxLayout()
        self._prev_btn = QPushButton("◀ 前")
        self._prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self._prev_btn)

        self._page_label = QLabel("")
        page_row.addWidget(self._page_label)

        self._next_btn = QPushButton("次 ▶")
        self._next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self._next_btn)

        page_row.addStretch()

        self._close_btn = QPushButton("閉じる")
        self._close_btn.clicked.connect(self.close)
        page_row.addWidget(self._close_btn)

        main_layout.addLayout(page_row)

        self.setLayout(main_layout)
        self._apply_theme()
        self._reload()

        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self) -> None:
        bg = get_color(ThemeKey.PANEL_BACKGROUND)
        fg = get_color(ThemeKey.TEXT_PRIMARY)
        self.setStyleSheet(
            f"QDialog {{ background-color: {bg}; color: {fg}; }}"
        )

    # -- データ ---------------------------------------------------------------

    def _reload(self) -> None:
        self._offset = 0
        self._load_data()

    def _search(self) -> None:
        self._offset = 0
        self._load_data()

    def _prev_page(self) -> None:
        self._offset = max(0, self._offset - self._PAGE_SIZE)
        self._load_data()

    def _next_page(self) -> None:
        self._offset += self._PAGE_SIZE
        self._load_data()

    def _load_data(self) -> None:
        store = ExternalAccessMonitorStore.instance()
        total = store.get_total_count()
        self._count_label.setText(f"全 {total} 件")

        method_filter = self._method_combo.currentText()
        host_filter = self._host_edit.text().strip()

        records = store.get_all(
            method_filter=method_filter,
            host_filter=host_filter,
            limit=self._PAGE_SIZE,
            offset=self._offset,
        )

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(records))
        for i, rec in enumerate(records):
            self._table.setItem(i, 0, _numeric_item(rec.id))
            self._table.setItem(i, 1, QTableWidgetItem(rec.created_at))
            self._table.setItem(i, 2, QTableWidgetItem(rec.method))
            self._table.setItem(i, 3, QTableWidgetItem(rec.host))
            self._table.setItem(i, 4, QTableWidgetItem(rec.url))
            self._table.setItem(i, 5, _numeric_item(rec.status_code))
            self._table.setItem(i, 6, _numeric_item(rec.duration_ms))
            self._table.setItem(i, 7, QTableWidgetItem(rec.source_kind))
            self._table.setItem(i, 8, QTableWidgetItem(rec.error_text))
        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()

        # ページング状態更新
        page_no = (self._offset // self._PAGE_SIZE) + 1
        max_page = max(1, (total + self._PAGE_SIZE - 1) // self._PAGE_SIZE)
        self._page_label.setText(f"{page_no} / {max_page}")
        self._prev_btn.setEnabled(self._offset > 0)
        self._next_btn.setEnabled(self._offset + self._PAGE_SIZE < total)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


class _NumericTableItem(QTableWidgetItem):
    """数値ソート対応 QTableWidgetItem"""

    def __init__(self, value) -> None:
        super().__init__(str(value))
        self._sort_value = float(value) if value is not None else 0.0

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        if isinstance(other, _NumericTableItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


def _numeric_item(value) -> _NumericTableItem:
    return _NumericTableItem(value)
