"""Data entry (tile) aggregated listing widget for DataRegisterTabWidget."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from qt_compat.core import Qt, QUrl
from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QGroupBox,
)

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QBrush, QDesktopServices, QFont
from PySide6.QtWidgets import QHeaderView, QTableView

from classes.data_entry.util.dataentry_tile_list_table_records import (
    DataEntryTileListColumn,
    build_dataentry_tile_list_rows_from_files,
)
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color


logger = logging.getLogger(__name__)


class DataEntryTileListTableModel(QAbstractTableModel):
    def __init__(
        self,
        columns: List[DataEntryTileListColumn],
        rows: List[Dict[str, Any]],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._columns = columns
        self._rows = rows

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_columns(self) -> List[DataEntryTileListColumn]:
        return self._columns

    def get_rows(self) -> List[Dict[str, Any]]:
        return self._rows

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._columns):
                return self._columns[section].label
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        col = self._columns[index.column()]

        if role == Qt.DisplayRole:
            v = row.get(col.key)
            return "" if v is None else str(v)

        if role == Qt.UserRole:
            if col.key == "tile_id":
                return row.get("_tile_url") or ""
            if col.key == "dataset_id":
                return row.get("_dataset_url") or ""
            if col.key == "subgroup_id":
                return row.get("_subgroup_url") or ""
            return row.get(col.key)

        if role == Qt.ForegroundRole:
            if col.key in {"tile_id", "dataset_id", "subgroup_id"}:
                url = self.data(index, Qt.UserRole)
                if str(url or "").strip():
                    return QBrush(get_color(ThemeKey.TEXT_LINK))

        if role == Qt.FontRole:
            if col.key in {"tile_id", "dataset_id", "subgroup_id"}:
                url = self.data(index, Qt.UserRole)
                if str(url or "").strip():
                    f = QFont()
                    f.setUnderline(True)
                    return f

        if role == Qt.TextAlignmentRole:
            if col.key in {"number_of_files", "number_of_image_files"}:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


class DataEntryTileFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: Dict[int, str] = {}
        self._column_filter_patterns: Dict[int, List[re.Pattern]] = {}
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_column_filters(self, filters_by_col_index: Dict[int, str]) -> None:
        self._column_filters = {int(k): str(v) for k, v in (filters_by_col_index or {}).items() if str(v).strip()}
        self._column_filter_patterns = {}
        for col_idx, text in self._column_filters.items():
            parts = [p.strip() for p in str(text).split() if p.strip()]
            patterns: List[re.Pattern] = []
            for p in parts:
                try:
                    patterns.append(re.compile(re.escape(p), re.IGNORECASE))
                except Exception:
                    continue
            if patterns:
                self._column_filter_patterns[col_idx] = patterns
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True

        for col_idx, patterns in self._column_filter_patterns.items():
            try:
                idx = model.index(source_row, col_idx, source_parent)
                txt = str(model.data(idx, Qt.DisplayRole) or "")
            except Exception:
                return False
            if any(p.search(txt) is None for p in patterns):
                return False
        return True


class DataEntryTileListingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: List[DataEntryTileListColumn] = []
        self._model: Optional[DataEntryTileListTableModel] = None
        self._filter_proxy = DataEntryTileFilterProxyModel(self)

        self._filter_edits_by_key: Dict[str, QLineEdit] = {}
        self._reload_button: Optional[QPushButton] = None
        self._status_label: Optional[QLabel] = None
        self._filter_mode_combo: Optional[QComboBox] = None
        self._grant_filter_edit: Optional[QLineEdit] = None

        self._table: Optional[QTableView] = None

        self._init_ui()
        self.reload_data()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top bar
        top = QHBoxLayout()
        self._status_label = QLabel("読み込み中...", self)
        top.addWidget(self._status_label, 1)

        self._reload_button = QPushButton("再読み込み", self)
        self._reload_button.clicked.connect(self.reload_data)
        top.addWidget(self._reload_button, 0)
        layout.addLayout(top)

        # Prefilter
        pre = QGroupBox("事前フィルタ", self)
        pre_layout = QGridLayout(pre)

        pre_layout.addWidget(QLabel("対象:", pre), 0, 0)
        self._filter_mode_combo = QComboBox(pre)
        self._filter_mode_combo.addItem("自分の課題のみ", "user_only")
        self._filter_mode_combo.addItem("自分以外", "others_only")
        self._filter_mode_combo.addItem("すべて", "all")
        self._filter_mode_combo.setCurrentIndex(0)
        pre_layout.addWidget(self._filter_mode_combo, 0, 1)

        pre_layout.addWidget(QLabel("課題番号:", pre), 0, 2)
        self._grant_filter_edit = QLineEdit(pre)
        self._grant_filter_edit.setPlaceholderText("例: 23XXXXXX")
        pre_layout.addWidget(self._grant_filter_edit, 0, 3)

        apply_btn = QPushButton("適用", pre)
        apply_btn.clicked.connect(self.reload_data)
        pre_layout.addWidget(apply_btn, 0, 4)

        layout.addWidget(pre)

        # Column filters
        filters = QGroupBox("列フィルタ（空白区切りでAND）", self)
        filters_layout = QGridLayout(filters)
        row = 0
        col = 0

        def _add_filter(key: str, label: str) -> None:
            nonlocal row, col
            lbl = QLabel(label + ":", filters)
            edit = QLineEdit(filters)
            edit.setPlaceholderText("例: abc")
            edit.textChanged.connect(self._apply_filters_now)
            self._filter_edits_by_key[key] = edit
            filters_layout.addWidget(lbl, row, col)
            filters_layout.addWidget(edit, row, col + 1)
            col += 2
            if col >= 6:
                row += 1
                col = 0

        _add_filter("subgroup_name", "サブグループ")
        _add_filter("grant_number", "課題番号")
        _add_filter("dataset_name", "データセット")
        _add_filter("data_number", "タイルNo")
        _add_filter("tile_name", "タイル名")
        _add_filter("tile_id", "タイルUUID")
        _add_filter("dataset_id", "データセットUUID")
        _add_filter("subgroup_id", "サブグループUUID")

        clear_btn = QPushButton("列フィルタ解除", filters)
        clear_btn.clicked.connect(self._clear_filters)
        filters_layout.addWidget(clear_btn, row + 1, 0, 1, 2)

        layout.addWidget(filters)

        # Table
        self._table = QTableView(self)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.clicked.connect(self._on_table_clicked)

        layout.addWidget(self._table, 1)

    def _clear_filters(self) -> None:
        for edit in self._filter_edits_by_key.values():
            try:
                edit.setText("")
            except Exception:
                pass
        self._apply_filters_now()

    def _apply_filters_now(self) -> None:
        if not self._columns:
            return
        key_to_index = {c.key: i for i, c in enumerate(self._columns)}
        filters_by_index: Dict[int, str] = {}
        for key, edit in self._filter_edits_by_key.items():
            idx = key_to_index.get(key)
            if idx is None:
                continue
            txt = (edit.text() or "").strip()
            if txt:
                filters_by_index[int(idx)] = txt
        self._filter_proxy.set_column_filters(filters_by_index)
        self._update_status_label()

    def _update_status_label(self) -> None:
        if self._status_label is None:
            return
        total = 0
        visible = 0
        try:
            if self._model is not None:
                total = len(self._model.get_rows())
        except Exception:
            total = 0
        try:
            visible = int(self._filter_proxy.rowCount())
        except Exception:
            visible = 0
        self._status_label.setText(f"タイル {visible}/{total} 件")

    def _on_table_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        try:
            url = self._table.model().data(index, Qt.UserRole)  # type: ignore[union-attr]
        except Exception:
            url = ""
        url = str(url or "").strip()
        if not url:
            return
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            return

    def reload_data(self) -> None:
        filter_mode = "user_only"
        grant_filter = ""
        try:
            if self._filter_mode_combo is not None:
                filter_mode = str(self._filter_mode_combo.currentData() or "user_only")
        except Exception:
            filter_mode = "user_only"
        try:
            if self._grant_filter_edit is not None:
                grant_filter = str(self._grant_filter_edit.text() or "")
        except Exception:
            grant_filter = ""

        try:
            columns, rows = build_dataentry_tile_list_rows_from_files(
                filter_mode=filter_mode,
                grant_number_filter=grant_filter,
            )
        except Exception as exc:
            logger.debug("tile listing reload failed: %s", exc)
            columns, rows = [], []

        self._columns = columns
        if self._model is None:
            self._model = DataEntryTileListTableModel(columns, rows, parent=self)
            self._filter_proxy.setSourceModel(self._model)
            if self._table is not None:
                self._table.setModel(self._filter_proxy)
        else:
            self._model.set_rows(rows)

        self._apply_filters_now()


def create_dataentry_tile_listing_widget(parent=None) -> DataEntryTileListingWidget:
    return DataEntryTileListingWidget(parent)
