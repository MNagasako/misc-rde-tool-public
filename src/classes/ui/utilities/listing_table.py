"""Reusable Qt widgets for filterable listing tabs."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from classes.ui.utilities.listing_support import ListingColumn, prepare_display_value

from qt_compat import QtCore, QtGui
from qt_compat.core import Qt
from qt_compat.widgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QtWidgets,
    QVBoxLayout,
    QWidget,
)

LOGGER = logging.getLogger(__name__)

QTableView = QtWidgets.QTableView
QStandardItemModel = QtGui.QStandardItemModel
QStandardItem = QtGui.QStandardItem
QSortFilterProxyModel = QtCore.QSortFilterProxyModel


class ListingFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that supports all-column filtering."""

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._filter_text = ""
        self._filter_column = -1
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_filter_text(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self.invalidateFilter()

    def set_filter_column(self, column: int) -> None:
        self._filter_column = column
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:  # type: ignore[override]
        if not self._filter_text:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        if self._filter_column >= 0:
            value = model.index(source_row, self._filter_column, source_parent).data()
            return self._matches(value)
        for column in range(model.columnCount()):
            value = model.index(source_row, column, source_parent).data()
            if self._matches(value):
                return True
        return False

    def _matches(self, value: object) -> bool:
        if value is None:
            return False
        return self._filter_text in str(value).lower()


class ListingTabBase(QWidget):
    """Abstract tab that shows filterable, sortable listing tables."""

    title_text: str = ""
    empty_state_message: str = "データが見つかりません"
    columns: Sequence[ListingColumn] = ()

    def __init__(self, parent: Optional[QWidget] = None, *, defer_initial_refresh: bool = False):
        super().__init__(parent)
        self._current_source: Optional[Path] = None
        self._raw_records: List[dict] = []
        self._setup_ui()
        if defer_initial_refresh:
            # 初期表示を軽くするため、初回読み込みはイベントループに戻してから実行する。
            # 直接refreshすると、タブ切替やウィジェット生成がブロックされやすい。
            try:
                from qt_compat.core import QTimer

                self.status_label.setText("読み込み中...")
                QTimer.singleShot(0, self.refresh_from_disk)
            except Exception:
                self.refresh_from_disk()
        else:
            self.refresh_from_disk()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        if self.title_text:
            title_label = QLabel(self.title_text)
            title_label.setObjectName("listingTitle")
            layout.addWidget(title_label)

        control_layout = QHBoxLayout()
        control_layout.setSpacing(6)
        layout.addLayout(control_layout)

        self.filter_column_combo = QComboBox()
        self.filter_column_combo.addItem("全列", -1)
        for index, column in enumerate(self.columns):
            self.filter_column_combo.addItem(column.label, index)
        self.filter_column_combo.currentIndexChanged.connect(self._on_filter_column_changed)
        control_layout.addWidget(self.filter_column_combo)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("キーワードで絞り込み")
        self.filter_input.textChanged.connect(self._on_filter_text_changed)
        control_layout.addWidget(self.filter_input, stretch=1)

        self.clear_filter_button = QPushButton("クリア")
        self.clear_filter_button.clicked.connect(self._on_clear_filter)
        control_layout.addWidget(self.clear_filter_button)

        self.reload_button = QPushButton("最新を再読込")
        self.reload_button.clicked.connect(self.refresh_from_disk)
        control_layout.addWidget(self.reload_button)

        self.export_csv_button = QPushButton("CSV出力")
        self.export_csv_button.clicked.connect(lambda: self._export("csv"))
        control_layout.addWidget(self.export_csv_button)

        self.export_xlsx_button = QPushButton("XLSX出力")
        self.export_xlsx_button.clicked.connect(lambda: self._export("xlsx"))
        control_layout.addWidget(self.export_xlsx_button)

        self.count_label = QLabel("0件")
        control_layout.addWidget(self.count_label)

        self.status_label = QLabel(self.empty_state_message)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table_model = QStandardItemModel(0, len(self.columns), self)
        header_labels = [column.label for column in self.columns]
        self.table_model.setHorizontalHeaderLabels(header_labels)

        self.proxy_model = ListingFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.modelReset.connect(self._update_count_label)
        self.proxy_model.rowsInserted.connect(self._update_count_label)
        self.proxy_model.rowsRemoved.connect(self._update_count_label)
        self.proxy_model.layoutChanged.connect(self._update_count_label)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionsMovable(True)
        self.table_view.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        self.table_view.verticalHeader().setVisible(False)
        layout.addWidget(self.table_view)

        self._apply_column_widths()
        self._update_count_label()

    def _apply_column_widths(self) -> None:
        header = self.table_view.horizontalHeader()
        for index, column in enumerate(self.columns):
            if column.width:
                self.table_view.setColumnWidth(index, column.width)
            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeToContents)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def _on_filter_column_changed(self) -> None:
        column_data = self.filter_column_combo.currentData()
        column_index = int(column_data) if column_data is not None else -1
        self.proxy_model.set_filter_column(column_index)
        self._update_count_label()

    def _on_filter_text_changed(self, text: str) -> None:
        self.proxy_model.set_filter_text(text)
        self._update_count_label()

    def _on_clear_filter(self) -> None:
        self.filter_input.clear()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def refresh_from_disk(self) -> None:
        try:
            records, source_path = self.load_records_from_disk()
        except Exception as exc:  # pragma: no cover - unexpected errors are logged
            LOGGER.exception("Listing tab refresh failed")
            self._raw_records = []
            self._current_source = None
            self.status_label.setText(f"⚠️ 読み込み失敗: {exc}")
            self._populate_model([])
            return

        self._raw_records = list(records)
        self._current_source = source_path
        self._populate_model(self._raw_records)
        self._update_status_label()

    def _populate_model(self, records: Iterable[dict]) -> None:
        self.table_model.removeRows(0, self.table_model.rowCount())
        for record in records:
            row_items = []
            for column in self.columns:
                display, tooltip = prepare_display_value(
                    record.get(column.key, ""),
                    column.preview_limit,
                )
                item = QStandardItem(display)
                item.setEditable(False)

                # Keep raw value for exports (avoid preview truncation).
                try:
                    item.setData(record.get(column.key, ""), int(Qt.ItemDataRole.UserRole) + 1)
                except Exception:
                    pass
                if tooltip and tooltip != display:
                    item.setToolTip(tooltip)
                row_items.append(item)
            if row_items:
                self.table_model.appendRow(row_items)
        self._update_count_label()

    def _export(self, kind: str) -> None:
        kind = str(kind or "").strip().lower()
        if kind not in {"csv", "xlsx"}:
            return

        visible_cols = list(range(int(self.proxy_model.columnCount())))
        headers: list[str] = []
        for col in visible_cols:
            header = self.proxy_model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            headers.append(str(header or ""))

        rows: list[dict[str, object]] = []
        raw_role = int(Qt.ItemDataRole.UserRole) + 1
        for row_idx in range(int(self.proxy_model.rowCount())):
            out: dict[str, object] = {}
            for col_idx, header in zip(visible_cols, headers, strict=False):
                idx = self.proxy_model.index(row_idx, int(col_idx))
                if not idx.isValid():
                    continue
                val = idx.data(raw_role)
                if val is None:
                    val = idx.data(Qt.ItemDataRole.DisplayRole)
                out[header] = val
            if out:
                rows.append(out)

        if not rows:
            QMessageBox.information(self, "出力", "出力対象の行がありません")
            return

        import time

        default_name = f"listing_{time.strftime('%Y%m%d_%H%M%S')}"
        if kind == "csv":
            suggested = f"{default_name}.csv"
            path, _ = QFileDialog.getSaveFileName(self, "CSV出力", suggested, "CSV Files (*.csv)")
        else:
            suggested = f"{default_name}.xlsx"
            path, _ = QFileDialog.getSaveFileName(self, "XLSX出力", suggested, "Excel Files (*.xlsx)")

        if not path:
            return

        try:
            import pandas as pd

            df = pd.DataFrame(rows)
            if kind == "csv":
                df.to_csv(path, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(path, index=False)
            QMessageBox.information(self, "出力", f"出力しました: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "出力失敗", f"出力に失敗しました: {exc}")

    def _update_status_label(self) -> None:
        if self._current_source and self._current_source.exists():
            try:
                mtime = datetime.fromtimestamp(self._current_source.stat().st_mtime)
                timestamp = mtime.strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                timestamp = ""
            path_text = self._current_source.name
            details = f"最終更新: {timestamp}" if timestamp else ""
            self.status_label.setText(f"読み込み元: {path_text} {details}")
        else:
            self.status_label.setText(self.empty_state_message)

    def _update_count_label(self) -> None:
        total = self.table_model.rowCount()
        visible = self.proxy_model.rowCount()
        if total == visible:
            self.count_label.setText(f"{total}件")
        else:
            self.count_label.setText(f"{visible}/{total}件")

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    def load_records_from_disk(self) -> Tuple[Iterable[dict], Optional[Path]]:
        """Return listing records and the source path."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Theme hooks
    # ------------------------------------------------------------------
    def refresh_theme(self) -> None:
        """Placeholder for subclasses; exists for symmetry with other tabs."""
        self.update()
