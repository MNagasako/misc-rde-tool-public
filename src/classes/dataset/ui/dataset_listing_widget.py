"""Dataset listing widget for the DatasetTabWidget "一覧" tab."""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from qt_compat.core import Qt, QDate
from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QDateEdit,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QMessageBox,
    QShortcut,
    QScrollArea,
    QSizePolicy,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
)

from PySide6.QtCore import QObject, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QKeySequence, QBrush, QFont, QDesktopServices
from qt_compat.core import QUrl
from PySide6.QtWidgets import QTableView

from classes.dataset.util.dataset_list_table_records import (
    DatasetListColumn,
    build_dataset_list_rows_from_files,
)

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import get_dynamic_file_path


class DatasetListTableModel(QAbstractTableModel):
    def __init__(self, columns: List[DatasetListColumn], rows: List[Dict[str, Any]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._columns = columns
        self._rows = rows

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_columns(self) -> List[DatasetListColumn]:
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
            value = row.get(col.key)
            if isinstance(value, bool):
                return "True" if value else "False"
            return "" if value is None else str(value)

        if role == Qt.UserRole:
            if col.key == "embargo_date":
                embargo_obj = row.get("_embargo_date_obj")
                return embargo_obj
            if col.key == "dataset_name":
                dataset_id = row.get("dataset_id")
                dataset_id = str(dataset_id).strip() if dataset_id is not None else ""
                if dataset_id:
                    return f"https://rde.nims.go.jp/rde/datasets/{dataset_id}"
                return ""
            if col.key == "subgroup_name":
                subgroup_id = row.get("subgroup_id")
                subgroup_id = str(subgroup_id).strip() if subgroup_id is not None else ""
                if subgroup_id:
                    return f"https://rde.nims.go.jp/rde/datasets/groups/{subgroup_id}"
                return ""
            if col.key == "tool_open":
                dataset_id = row.get("dataset_id")
                dataset_id = str(dataset_id).strip() if dataset_id is not None else ""
                return dataset_id
            return row.get(col.key)

        if role == Qt.ForegroundRole:
            if col.key in {"dataset_name", "instrument_names", "tool_open"}:
                return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key == "subgroup_name":
                subgroup_id = row.get("subgroup_id")
                subgroup_id = str(subgroup_id).strip() if subgroup_id is not None else ""
                if subgroup_id:
                    return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key == "manager_name":
                if not bool(row.get("_manager_resolved")):
                    return QBrush(get_color(ThemeKey.TEXT_DISABLED))
            if col.key == "applicant_name":
                if not bool(row.get("_applicant_resolved")):
                    return QBrush(get_color(ThemeKey.TEXT_DISABLED))

        if role == Qt.FontRole:
            if col.key in {"dataset_name", "instrument_names", "tool_open"}:
                f = QFont()
                f.setUnderline(True)
                return f
            if col.key == "subgroup_name":
                subgroup_id = row.get("subgroup_id")
                subgroup_id = str(subgroup_id).strip() if subgroup_id is not None else ""
                if subgroup_id:
                    f = QFont()
                    f.setUnderline(True)
                    return f

        if role == Qt.TextAlignmentRole:
            if col.key in {"description_len", "related_datasets_count", "tile_count", "file_count", "tag_count"}:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


class DatasetFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: Dict[int, str] = {}
        self._column_filter_patterns: Dict[int, List[re.Pattern]] = {}
        self._embargo_from: Optional[datetime.date] = None
        self._embargo_to: Optional[datetime.date] = None
        self._description_len_min: Optional[int] = None
        self._description_len_max: Optional[int] = None
        self._related_count_min: Optional[int] = None
        self._related_count_max: Optional[int] = None
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    @staticmethod
    def _split_filter_terms(text: str) -> List[str]:
        # Delimiters: comma, semicolon, half-width space
        # (e.g. "abc,def ghi;xyz")
        raw = (text or "").strip()
        if not raw:
            return []
        normalized = raw.replace(",", " ").replace(";", " ")
        return [t for t in (p.strip() for p in normalized.split(" ")) if t]

    @staticmethod
    def _compile_wildcard_pattern(term: str) -> Optional[re.Pattern]:
        t = (term or "").strip()
        if not t:
            return None
        # Interpret '*' as wildcard (match any chars). Other chars are literal.
        escaped = re.escape(t)
        escaped = escaped.replace(r"\*", ".*")
        try:
            return re.compile(escaped, re.IGNORECASE)
        except Exception:
            return None

    @classmethod
    def _compile_terms(cls, text: str) -> List[re.Pattern]:
        patterns: List[re.Pattern] = []
        for term in cls._split_filter_terms(text):
            pat = cls._compile_wildcard_pattern(term)
            if pat is not None:
                patterns.append(pat)
        return patterns

    def set_column_filters(self, filters_by_col_index: Dict[int, str]) -> None:
        # keys: source-model column index, value: text filter
        cleaned: Dict[int, str] = {}
        compiled: Dict[int, List[re.Pattern]] = {}
        for k, v in (filters_by_col_index or {}).items():
            try:
                idx = int(k)
            except Exception:
                continue
            text = (v or "").strip()
            if text:
                cleaned[idx] = text
                compiled[idx] = self._compile_terms(text)
        self._column_filters = cleaned
        self._column_filter_patterns = {k: v for k, v in compiled.items() if v}
        self.invalidateFilter()

    def set_embargo_range(self, date_from: Optional[datetime.date], date_to: Optional[datetime.date]) -> None:
        self._embargo_from = date_from
        self._embargo_to = date_to
        self.invalidateFilter()

    def set_description_len_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._description_len_min = min_value
        self._description_len_max = max_value
        self.invalidateFilter()

    def set_related_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._related_count_min = min_value
        self._related_count_max = max_value
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True

        # embargo range filter (applies to the "エンバーゴ期間終了日" column when present)
        if self._embargo_from or self._embargo_to:
            embargo_col = self._find_column_by_label("エンバーゴ期間終了日")
            if embargo_col >= 0:
                idx = model.index(source_row, embargo_col, source_parent)
                embargo_obj = model.data(idx, Qt.UserRole)
                if not isinstance(embargo_obj, datetime.date):
                    return False
                if self._embargo_from and embargo_obj < self._embargo_from:
                    return False
                if self._embargo_to and embargo_obj > self._embargo_to:
                    return False

        # per-column text filters
        # - delimiters: ',', ';', ' '
        # - wildcard: '*' matches any chars
        # Semantics:
        # - terms within a column: OR
        # - multiple columns with filters: AND
        if self._column_filter_patterns:
            for col_idx, patterns in self._column_filter_patterns.items():
                if col_idx < 0 or col_idx >= model.columnCount():
                    continue
                idx = model.index(source_row, col_idx, source_parent)
                hay = str(model.data(idx, Qt.DisplayRole) or "")
                if not any(p.search(hay) for p in patterns):
                    return False

        # description length range
        if self._description_len_min is not None or self._description_len_max is not None:
            desc_col = self._find_column_by_label("説明文字数")
            if desc_col >= 0:
                idx = model.index(source_row, desc_col, source_parent)
                val = model.data(idx, Qt.UserRole)
                try:
                    n = int(val)
                except Exception:
                    n = None
                if n is None:
                    return False
                if self._description_len_min is not None and n < self._description_len_min:
                    return False
                if self._description_len_max is not None and n > self._description_len_max:
                    return False

        # related datasets count range
        if self._related_count_min is not None or self._related_count_max is not None:
            rel_col = self._find_column_by_label("関連データセット")
            if rel_col >= 0:
                idx = model.index(source_row, rel_col, source_parent)
                val = model.data(idx, Qt.UserRole)
                try:
                    n = int(val)
                except Exception:
                    n = None
                if n is None:
                    return False
                if self._related_count_min is not None and n < self._related_count_min:
                    return False
                if self._related_count_max is not None and n > self._related_count_max:
                    return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)

        # Sort embargo date as date when possible.
        try:
            label = model.headerData(left.column(), Qt.Horizontal, Qt.DisplayRole)
        except Exception:
            label = None

        if label == "エンバーゴ期間終了日":
            l = model.data(left, Qt.UserRole)
            r = model.data(right, Qt.UserRole)
            if isinstance(l, datetime.date) and isinstance(r, datetime.date):
                return l < r
            if isinstance(l, datetime.date) and r is None:
                return False
            if l is None and isinstance(r, datetime.date):
                return True

        return super().lessThan(left, right)

    def _find_column_by_label(self, label: str) -> int:
        model = self.sourceModel()
        if model is None:
            return -1
        for i in range(model.columnCount()):
            if model.headerData(i, Qt.Horizontal, Qt.DisplayRole) == label:
                return i
        return -1


class RowLimitProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_limit = 100  # 0 = all

    def set_row_limit(self, limit: int) -> None:
        self._row_limit = max(0, int(limit))
        self.invalidate()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        total = super().rowCount(parent)
        if self._row_limit <= 0:
            return total
        return min(total, self._row_limit)


class ColumnSelectorDialog(QDialog):
    def __init__(self, parent: QWidget, columns: List[DatasetListColumn], visible_by_key: Dict[str, bool]):
        super().__init__(parent)
        self.setWindowTitle("列選択")
        self._columns = columns

        self._checkbox_by_key: Dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(0)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)

        for col in columns:
            cb = QCheckBox(col.label, body)
            cb.setChecked(bool(visible_by_key.get(col.key, True)))
            self._checkbox_by_key[col.key] = cb
            body_layout.addWidget(cb)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_visible_by_key(self) -> Dict[str, bool]:
        return {k: cb.isChecked() for k, cb in self._checkbox_by_key.items()}


class InstrumentLinkSelectorDialog(QDialog):
    def __init__(self, parent: QWidget, items: List[Dict[str, str]]):
        super().__init__(parent)
        self.setWindowTitle("設備を選択")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("開く設備を選択してください"))

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        for it in items:
            label = (it.get("label") or "").strip()
            url = (it.get("url") or "").strip()
            if not label or not url:
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, url)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        try:
            self._list.itemDoubleClicked.connect(lambda _: self.accept())
        except Exception:
            pass

        # Theme
        try:
            self.setStyleSheet(
                f"QDialog {{ background-color: {get_color(ThemeKey.BACKGROUND_PRIMARY)}; }}"
                f"QLabel {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
                f"QListWidget {{"
                f"  background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};"
                f"  color: {get_color(ThemeKey.INPUT_TEXT)};"
                f"  border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};"
                f"}}"
                f"QListWidget::item:selected {{"
                f"  background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)};"
                f"  color: {get_color(ThemeKey.TABLE_ROW_TEXT_SELECTED)};"
                f"}}"
            )
        except Exception:
            pass

    def selected_url(self) -> str:
        item = self._list.currentItem()
        url = item.data(Qt.UserRole) if item is not None else ""
        return url if isinstance(url, str) else ""


class DatasetListingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._columns: List[DatasetListColumn] = []
        self._model: Optional[DatasetListTableModel] = None
        self._filter_proxy = DatasetFilterProxyModel(self)
        self._limit_proxy = RowLimitProxyModel(self)

        self._filter_edits_by_key: Dict[str, QLineEdit] = {}
        self._filters_container: Optional[QWidget] = None
        self._filters_layout: Optional[QVBoxLayout] = None
        self._range_filters_container: Optional[QWidget] = None
        self._range_filters_layout: Optional[QGridLayout] = None
        self._text_filters_container: Optional[QWidget] = None
        self._text_filters_layout: Optional[QGridLayout] = None

        self._desc_len_min = QSpinBox(self)
        self._desc_len_max = QSpinBox(self)
        self._related_cnt_min = QSpinBox(self)
        self._related_cnt_max = QSpinBox(self)
        self._tool_open_callback = None

        # Debounce filter application to keep the table responsive while typing/clicking.
        # Slight delay is acceptable per requirement.
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(350)
        self._filter_apply_timer.timeout.connect(self._apply_filters_now)

        # Range filter containers (must be kept as instance attrs).
        # If we create these widgets inside `_rebuild_filters_panel()`, they can be GC'ed after
        # removal from the layout, which deletes their children (QSpinBox/QDateEdit) on Qt side.
        self._range_desc_widget: Optional[QWidget] = None
        self._range_related_widget: Optional[QWidget] = None
        self._range_embargo_widget: Optional[QWidget] = None

        root = QVBoxLayout(self)

        # Row 1: buttons / counters
        buttons_row = QHBoxLayout()
        self._status = QLabel("")
        buttons_row.addWidget(self._status, 1)

        buttons_row.addWidget(QLabel("表示行数:"))
        self._row_limit = QSpinBox(self)
        self._row_limit.setMinimum(0)
        self._row_limit.setMaximum(999999)
        self._row_limit.setValue(100)
        self._row_limit.setSpecialValueText("全件")
        try:
            from PySide6.QtWidgets import QAbstractSpinBox

            self._row_limit.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        except Exception:
            pass
        buttons_row.addWidget(self._row_limit)

        self._select_columns = QPushButton("列選択", self)
        buttons_row.addWidget(self._select_columns)

        self._reset_columns = QPushButton("列リセット", self)
        buttons_row.addWidget(self._reset_columns)

        self._export_csv = QPushButton("CSV出力", self)
        self._export_xlsx = QPushButton("XLSX出力", self)
        buttons_row.addWidget(self._export_csv)
        buttons_row.addWidget(self._export_xlsx)

        self._reload = QPushButton("更新", self)
        buttons_row.addWidget(self._reload)

        root.addLayout(buttons_row)

        # Row 2: filters (must be directly above the table)
        # 要件: 縦スクロールバーは表示しない（必要ならテーブル領域を狭くする）
        self._filters_container = QWidget(self)
        self._filters_layout = QVBoxLayout(self._filters_container)
        self._filters_layout.setContentsMargins(0, 0, 0, 0)
        self._filters_layout.setSpacing(6)

        self._range_filters_container = QWidget(self._filters_container)
        self._range_filters_layout = QGridLayout(self._range_filters_container)
        self._range_filters_layout.setContentsMargins(0, 0, 0, 0)
        self._range_filters_layout.setHorizontalSpacing(8)
        self._range_filters_layout.setVerticalSpacing(6)
        self._filters_layout.addWidget(self._range_filters_container)

        self._text_filters_container = QWidget(self._filters_container)
        self._text_filters_layout = QGridLayout(self._text_filters_container)
        self._text_filters_layout.setContentsMargins(0, 0, 0, 0)
        self._text_filters_layout.setHorizontalSpacing(8)
        self._text_filters_layout.setVerticalSpacing(6)
        self._filters_layout.addWidget(self._text_filters_container)

        # Embargo range widgets are constant.
        self._embargo_from = QDateEdit(self)
        self._embargo_from.setObjectName("dataset_listing_embargo_from")
        self._embargo_from.setDisplayFormat("yyyy-MM-dd")
        self._embargo_from.setCalendarPopup(True)
        self._embargo_from.setSpecialValueText("未設定")
        self._embargo_from.setDate(QDate(2000, 1, 1))
        self._embargo_from.setMinimumDate(QDate(2000, 1, 1))
        self._embargo_from.setMaximumDate(QDate(2999, 12, 31))
        self._embargo_to = QDateEdit(self)
        self._embargo_to.setObjectName("dataset_listing_embargo_to")
        self._embargo_to.setDisplayFormat("yyyy-MM-dd")
        self._embargo_to.setCalendarPopup(True)
        self._embargo_to.setSpecialValueText("未設定")
        self._embargo_to.setDate(QDate(2000, 1, 1))
        self._embargo_to.setMinimumDate(QDate(2000, 1, 1))
        self._embargo_to.setMaximumDate(QDate(2999, 12, 31))

        # Range filter inputs default settings
        try:
            from PySide6.QtWidgets import QAbstractSpinBox

            # Use 0 as the special (unset) value so the first click becomes 1.
            self._desc_len_min.setObjectName("dataset_listing_desc_len_min")
            self._desc_len_min.setMinimum(0)
            self._desc_len_min.setMaximum(999999)
            self._desc_len_min.setSpecialValueText("未設定")
            self._desc_len_min.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._desc_len_min.setValue(0)
            self._desc_len_max.setObjectName("dataset_listing_desc_len_max")
            self._desc_len_max.setMinimum(0)
            self._desc_len_max.setMaximum(999999)
            self._desc_len_max.setSpecialValueText("未設定")
            self._desc_len_max.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._desc_len_max.setValue(0)

            self._related_cnt_min.setObjectName("dataset_listing_related_cnt_min")
            self._related_cnt_min.setMinimum(0)
            self._related_cnt_min.setMaximum(999999)
            self._related_cnt_min.setSpecialValueText("未設定")
            self._related_cnt_min.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._related_cnt_min.setValue(0)
            self._related_cnt_max.setObjectName("dataset_listing_related_cnt_max")
            self._related_cnt_max.setMinimum(0)
            self._related_cnt_max.setMaximum(999999)
            self._related_cnt_max.setSpecialValueText("未設定")
            self._related_cnt_max.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._related_cnt_max.setValue(0)
        except Exception:
            pass

        # Build persistent range filter containers.
        self._range_desc_widget = QWidget(self)
        desc_layout = QHBoxLayout(self._range_desc_widget)
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.addWidget(QLabel("以上"))
        desc_layout.addWidget(self._desc_len_min)
        desc_layout.addWidget(QLabel("以下"))
        desc_layout.addWidget(self._desc_len_max)

        self._range_related_widget = QWidget(self)
        rel_layout = QHBoxLayout(self._range_related_widget)
        rel_layout.setContentsMargins(0, 0, 0, 0)
        rel_layout.addWidget(QLabel("以上"))
        rel_layout.addWidget(self._related_cnt_min)
        rel_layout.addWidget(QLabel("以下"))
        rel_layout.addWidget(self._related_cnt_max)

        self._range_embargo_widget = QWidget(self)
        emb_layout = QHBoxLayout(self._range_embargo_widget)
        emb_layout.setContentsMargins(0, 0, 0, 0)
        emb_layout.addWidget(QLabel("以降"))
        emb_layout.addWidget(self._embargo_from)
        emb_layout.addWidget(QLabel("以前"))
        emb_layout.addWidget(self._embargo_to)

        self._clear_filters = QPushButton("クリア", self)

        try:
            self._filters_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass

        root.addWidget(self._filters_container)

        # Table
        self._table = QTableView(self)
        self._table.setSortingEnabled(True)
        # Read-only but allow copy/paste via selection.
        from PySide6.QtWidgets import QAbstractItemView

        self._table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        try:
            self._table.setWordWrap(True)
        except Exception:
            pass
        root.addWidget(self._table, 1)

        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        # Copy to clipboard (Ctrl+C)
        self._copy_shortcut = QShortcut(QKeySequence.Copy, self._table)
        self._copy_shortcut.activated.connect(self._copy_selection_to_clipboard)

        # Theme styling
        self._apply_theme()

        # Wiring
        self._row_limit.valueChanged.connect(self._apply_row_limit)
        self._embargo_from.dateChanged.connect(self._schedule_apply_filters)
        self._embargo_to.dateChanged.connect(self._schedule_apply_filters)
        self._desc_len_min.valueChanged.connect(self._schedule_apply_filters)
        self._desc_len_max.valueChanged.connect(self._schedule_apply_filters)
        self._related_cnt_min.valueChanged.connect(self._schedule_apply_filters)
        self._related_cnt_max.valueChanged.connect(self._schedule_apply_filters)
        self._clear_filters.clicked.connect(self._clear_all_filters)
        self._select_columns.clicked.connect(self._open_column_selector)
        self._reset_columns.clicked.connect(self._reset_column_visibility)
        self._export_csv.clicked.connect(lambda: self._export("csv"))
        self._export_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self._reload.clicked.connect(self.reload_data)

        self._table.clicked.connect(self._on_table_clicked)

        # Initialize
        self.reload_data()

    def _schedule_apply_filters(self) -> None:
        # Avoid repeated heavy filtering while user is typing/clicking.
        try:
            self._filter_apply_timer.start()
        except Exception:
            self._apply_filters_now()

    def _apply_theme(self) -> None:
        try:
            input_border_w = get_color(ThemeKey.INPUT_BORDER_WIDTH)
        except Exception:
            input_border_w = "1px"

        # Inputs / buttons
        base_qss = (
            f"QLabel {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
            f"QLineEdit, QComboBox, QDateEdit {{"
            f"  background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.INPUT_TEXT)};"
            f"  border: {input_border_w} solid {get_color(ThemeKey.INPUT_BORDER)};"
            f"}}"
            f"QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{"
            f"  background-color: {get_color(ThemeKey.INPUT_BACKGROUND_FOCUS)};"
            f"  border: {get_color(ThemeKey.INPUT_BORDER_FOCUS_WIDTH)} solid {get_color(ThemeKey.INPUT_BORDER_FOCUS)};"
            f"}}"
            f"QPushButton {{"
            f"  background-color: {get_color(ThemeKey.BUTTON_DEFAULT_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.BUTTON_DEFAULT_TEXT)};"
            f"  border: 1px solid {get_color(ThemeKey.BUTTON_DEFAULT_BORDER)};"
            f"  padding: 4px 8px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {get_color(ThemeKey.BUTTON_DEFAULT_BACKGROUND_HOVER)}; }}"
            f"QCheckBox {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
        )
        self.setStyleSheet(base_qss)

        # Table
        table_qss = (
            f"QTableView {{"
            f"  background-color: {get_color(ThemeKey.TABLE_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.TABLE_ROW_TEXT)};"
            f"  border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};"
            f"  gridline-color: {get_color(ThemeKey.TABLE_BORDER)};"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};"
            f"  border: 1px solid {get_color(ThemeKey.TABLE_HEADER_BORDER)};"
            f"  padding: 4px;"
            f"}}"
            f"QTableView::item:selected {{"
            f"  background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)};"
            f"  color: {get_color(ThemeKey.TABLE_ROW_TEXT_SELECTED)};"
            f"}}"
            f"QTableView::item:alternate {{ background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE)}; }}"
        )
        try:
            self._table.setAlternatingRowColors(True)
        except Exception:
            pass
        self._table.setStyleSheet(table_qss)

    def _copy_selection_to_clipboard(self) -> None:
        try:
            selection = self._table.selectionModel()
            if selection is None:
                return
            indexes = selection.selectedIndexes()
            if not indexes:
                return

            model = self._table.model()
            if model is None:
                return

            # Bounding box copy (spreadsheet-like)
            rows = [i.row() for i in indexes]
            cols = [i.column() for i in indexes]
            min_row, max_row = min(rows), max(rows)
            min_col, max_col = min(cols), max(cols)

            header = self._table.horizontalHeader()
            visible_cols = [
                c
                for c in range(min_col, max_col + 1)
                if not self._table.isColumnHidden(c)
            ]
            visible_cols.sort(key=lambda c: header.visualIndex(c))

            index_set = {(i.row(), i.column()): i for i in indexes}
            lines: List[str] = []
            for r in range(min_row, max_row + 1):
                cells: List[str] = []
                for c in visible_cols:
                    idx = index_set.get((r, c))
                    if idx is None:
                        cells.append("")
                    else:
                        cells.append(str(model.data(idx, Qt.DisplayRole) or ""))
                lines.append("\t".join(cells))

            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText("\n".join(lines))
        except Exception:
            return

    def reload_data(self) -> None:
        columns, rows = build_dataset_list_rows_from_files()
        self._columns = columns

        if self._model is None:
            self._model = DatasetListTableModel(columns, rows, parent=self)
            self._filter_proxy.setSourceModel(self._model)
            self._limit_proxy.setSourceModel(self._filter_proxy)
            self._table.setModel(self._limit_proxy)
        else:
            self._model.set_rows(rows)

        self._status.setText(f"{len(rows)}件")

        self._rebuild_filters_panel()

        # Apply saved column visibility (fallback: defaults)
        visible_by_key = self._load_column_visibility() or {c.key: c.default_visible for c in columns}
        self._apply_column_visibility(visible_by_key, persist=False)

        self._apply_row_limit()
        self._apply_filters_now()

        # 改行表示がある列のため、表示行数が少ない場合のみ行高を内容に合わせる
        try:
            limit = int(self._row_limit.value())
            if limit <= 0 or limit <= 200:
                self._table.resizeRowsToContents()
        except Exception:
            pass

    def _apply_row_limit(self) -> None:
        self._limit_proxy.set_row_limit(int(self._row_limit.value()))

    def _clear_all_filters(self) -> None:
        for edit in self._filter_edits_by_key.values():
            edit.setText("")
        # Use 0/invalid as "no filter" by setting both to minimum and then disabling via internal state.
        self._embargo_from.setDate(QDate(2000, 1, 1))
        self._embargo_to.setDate(QDate(2000, 1, 1))
        try:
            self._desc_len_min.setValue(0)
            self._desc_len_max.setValue(0)
            self._related_cnt_min.setValue(0)
            self._related_cnt_max.setValue(0)
        except Exception:
            pass
        self._filter_proxy.set_embargo_range(None, None)
        self._apply_filters_now()

    def _apply_filters_now(self) -> None:
        filters_by_index: Dict[int, str] = {}
        key_to_index = {c.key: i for i, c in enumerate(self._columns)}
        for key, edit in self._filter_edits_by_key.items():
            if key in {"description_len", "related_datasets_count", "embargo_date"}:
                # 範囲フィルタは専用UIで扱う
                continue
            idx = key_to_index.get(key)
            if idx is None:
                continue
            text = (edit.text() or "").strip()
            if text:
                filters_by_index[idx] = text
        self._filter_proxy.set_column_filters(filters_by_index)

        # Only enable embargo filter when user selected meaningful values.
        date_from = self._qdate_to_date(self._embargo_from.date())
        date_to = self._qdate_to_date(self._embargo_to.date())

        # Treat the default 2000-01-01 as "unset".
        if date_from == datetime.date(2000, 1, 1):
            date_from = None
        if date_to == datetime.date(2000, 1, 1):
            date_to = None

        self._filter_proxy.set_embargo_range(date_from, date_to)

        # Description length range
        min_v = int(self._desc_len_min.value())
        max_v = int(self._desc_len_max.value())
        self._filter_proxy.set_description_len_range(
            None if min_v <= 0 else min_v,
            None if max_v <= 0 else max_v,
        )

        # Related datasets count range
        rel_min = int(self._related_cnt_min.value())
        rel_max = int(self._related_cnt_max.value())
        self._filter_proxy.set_related_count_range(
            None if rel_min <= 0 else rel_min,
            None if rel_max <= 0 else rel_max,
        )

    def _open_column_selector(self) -> None:
        visible_by_key = self._get_current_visible_by_key()
        dlg = ColumnSelectorDialog(self, self._columns, visible_by_key)

        # Dialog theme
        try:
            dlg.setStyleSheet(
                f"QDialog {{ background-color: {get_color(ThemeKey.BACKGROUND_PRIMARY)}; }}"
                f"QLabel, QCheckBox {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; }}"
            )
        except Exception:
            pass

        if dlg.exec() == QDialog.Accepted:
            self._apply_column_visibility(dlg.get_visible_by_key(), persist=True)

    def _get_current_visible_by_key(self) -> Dict[str, bool]:
        # We use current view state (hidden columns) as the source of truth.
        result: Dict[str, bool] = {}
        for idx, col in enumerate(self._columns):
            result[col.key] = not self._table.isColumnHidden(idx)
        return result

    def _apply_column_visibility(self, visible_by_key: Dict[str, bool], persist: bool) -> None:
        for idx, col in enumerate(self._columns):
            self._table.setColumnHidden(idx, not bool(visible_by_key.get(col.key, True)))
        if persist:
            self._save_column_visibility(visible_by_key)

    def _column_visibility_path(self) -> str:
        return get_dynamic_file_path("config/dataset_listing_columns.json")

    def _load_column_visibility(self) -> Optional[Dict[str, bool]]:
        try:
            path = self._column_visibility_path()
            if not path or not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return None
            result: Dict[str, bool] = {}
            for k, v in data.items():
                if isinstance(k, str):
                    result[k] = bool(v)
            return result
        except Exception:
            return None

    def _save_column_visibility(self, visible_by_key: Dict[str, bool]) -> None:
        try:
            path = self._column_visibility_path()
            if not path:
                return
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(visible_by_key, handle, ensure_ascii=False, indent=2)
        except Exception:
            return

    def _reset_column_visibility(self) -> None:
        try:
            path = self._column_visibility_path()
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
            visible_by_key = {c.key: c.default_visible for c in self._columns}
            self._apply_column_visibility(visible_by_key, persist=False)
        except Exception:
            return

    def _export(self, fmt: str) -> None:
        model = self._table.model()
        if model is None:
            return

        if fmt not in {"csv", "xlsx"}:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存",
            "",
            "CSV (*.csv)" if fmt == "csv" else "Excel (*.xlsx)",
        )
        if not path:
            return

        try:
            df = self._build_dataframe_from_view()
            if fmt == "csv":
                df.to_csv(path, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(path, index=False)
            QMessageBox.information(self, "出力", f"出力しました: {path}")
        except Exception as e:
            QMessageBox.critical(self, "出力エラー", str(e))

    def _build_dataframe_from_view(self) -> pd.DataFrame:
        model = self._table.model()
        header = self._table.horizontalHeader()
        if model is None:
            return pd.DataFrame()

        # Determine visible columns in visual order.
        visible_cols: List[int] = []
        for logical in range(model.columnCount()):
            if self._table.isColumnHidden(logical):
                continue
            visible_cols.append(logical)

        visible_cols.sort(key=lambda logical: header.visualIndex(logical))
        col_labels = [str(model.headerData(c, Qt.Horizontal, Qt.DisplayRole) or "") for c in visible_cols]

        data_rows: List[List[str]] = []
        for r in range(model.rowCount()):
            row_values: List[str] = []
            for c in visible_cols:
                idx = model.index(r, c)
                row_values.append(str(model.data(idx, Qt.DisplayRole) or ""))
            data_rows.append(row_values)

        return pd.DataFrame(data_rows, columns=col_labels)

    @staticmethod
    def _qdate_to_date(qdate: QDate) -> datetime.date:
        return datetime.date(qdate.year(), qdate.month(), qdate.day())

    def _rebuild_filters_panel(self) -> None:
        if (
            self._filters_container is None
            or self._filters_layout is None
            or self._range_filters_layout is None
            or self._text_filters_layout is None
        ):
            return

        def clear_layout(layout: QGridLayout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)

        def bold_label(text: str) -> QLabel:
            lbl = QLabel(text)
            try:
                f = lbl.font()
                f.setBold(True)
                lbl.setFont(f)
            except Exception:
                pass
            return lbl

        clear_layout(self._range_filters_layout)
        clear_layout(self._text_filters_layout)
        self._filter_edits_by_key = {}

        # --- Range filters (non-text) on their own rows ---
        r = 0
        if self._range_desc_widget is not None:
            self._range_filters_layout.addWidget(bold_label("説明文字数:"), r, 0)
            self._range_filters_layout.addWidget(self._range_desc_widget, r, 1)
            r += 1

        if self._range_related_widget is not None:
            self._range_filters_layout.addWidget(bold_label("関連データセット:"), r, 0)
            self._range_filters_layout.addWidget(self._range_related_widget, r, 1)
            r += 1

        if self._range_embargo_widget is not None:
            self._range_filters_layout.addWidget(bold_label("エンバーゴ期間終了日:"), r, 0)
            self._range_filters_layout.addWidget(self._range_embargo_widget, r, 1)
            r += 1

        # Clear button row
        self._range_filters_layout.addWidget(QLabel(""), r, 0)
        self._range_filters_layout.addWidget(self._clear_filters, r, 1)

        # Make range layout behave
        try:
            self._range_filters_layout.setColumnStretch(0, 0)
            self._range_filters_layout.setColumnStretch(1, 1)
        except Exception:
            pass

        # --- Text filters only: 5 columns with equal widths ---
        max_cols = 5
        try:
            for c in range(max_cols):
                self._text_filters_layout.setColumnStretch(c, 1)
        except Exception:
            pass

        row = 0
        col = 0
        for cdef in self._columns:
            if cdef.key in {"description_len", "related_datasets_count", "embargo_date"}:
                continue

            pair = QWidget(self)
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(6)

            lbl = bold_label(f"{cdef.label}:")
            edit = QLineEdit(self)
            edit.setPlaceholderText("フィルタ")
            edit.textChanged.connect(self._schedule_apply_filters)
            self._filter_edits_by_key[cdef.key] = edit

            try:
                edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                pair.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            except Exception:
                pass

            pair_layout.addWidget(lbl)
            pair_layout.addWidget(edit, 1)

            self._text_filters_layout.addWidget(pair, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _on_table_clicked(self, index: QModelIndex) -> None:
        try:
            if not index.isValid() or self._model is None:
                return

            # Map through proxies to source model
            idx1 = self._limit_proxy.mapToSource(index)
            idx2 = self._filter_proxy.mapToSource(idx1)
            if not idx2.isValid():
                return

            col = self._columns[idx2.column()] if 0 <= idx2.column() < len(self._columns) else None
            if col is None or col.key not in {"dataset_name", "instrument_names", "subgroup_name", "tool_open"}:
                return

            if col.key in {"dataset_name", "subgroup_name"}:
                url = self._model.data(idx2, Qt.UserRole)
                if not isinstance(url, str) or not url:
                    return
                QDesktopServices.openUrl(QUrl(url))
                return

            if col.key == "tool_open":
                dataset_id = self._model.data(idx2, Qt.UserRole)
                dataset_id = dataset_id if isinstance(dataset_id, str) else ""
                dataset_id = dataset_id.strip()
                if dataset_id and callable(self._tool_open_callback):
                    try:
                        self._tool_open_callback(dataset_id)
                    except Exception:
                        return
                return

            # instrument_names: selection when multiple
            rows = self._model.get_rows()
            row = rows[idx2.row()] if 0 <= idx2.row() < len(rows) else {}
            inst_ids = row.get("_instrument_ids")
            inst_names = row.get("_instrument_names")
            if not isinstance(inst_ids, list) or not inst_ids:
                return
            if not isinstance(inst_names, list):
                inst_names = []

            options: List[Dict[str, str]] = []
            for i, inst_id in enumerate(inst_ids):
                inst_id_str = str(inst_id).strip()
                if not inst_id_str:
                    continue
                label = ""
                try:
                    if i < len(inst_names):
                        label = str(inst_names[i]).strip()
                except Exception:
                    label = ""
                if not label:
                    label = inst_id_str
                url = f"https://rde-instrument.nims.go.jp/instruments/instruments/{inst_id_str}?isNewTab=true"
                options.append({"label": label, "url": url})

            if not options:
                return
            if len(options) == 1:
                QDesktopServices.openUrl(QUrl(options[0]["url"]))
                return

            dlg = InstrumentLinkSelectorDialog(self, options)
            if dlg.exec() == QDialog.Accepted:
                url = dlg.selected_url()
                if url:
                    QDesktopServices.openUrl(QUrl(url))
        except Exception:
            return

    def set_tool_open_callback(self, callback) -> None:
        self._tool_open_callback = callback


def create_dataset_listing_widget(parent=None, title: str = "一覧") -> QWidget:
    _ = title
    return DatasetListingWidget(parent)
