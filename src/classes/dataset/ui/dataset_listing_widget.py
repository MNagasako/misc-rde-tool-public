"""Dataset listing widget for the DatasetTabWidget "一覧" tab."""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from qt_compat.core import Qt, QDate, QUrl, QThread, Signal
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

from PySide6.QtCore import QObject, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QTimer, QAbstractProxyModel
from PySide6.QtGui import QKeySequence, QBrush, QFont, QDesktopServices
from PySide6.QtWidgets import QTableView

from classes.dataset.ui.spinner_overlay import SpinnerOverlay

from classes.dataset.util.dataset_list_table_records import (
    DatasetListColumn,
    build_dataset_list_rows_from_files,
)

from classes.dataset.util.dataset_listing_export_filename import (
    build_dataset_listing_export_default_filename,
)

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import get_dynamic_file_path


_ACTIVE_DATASET_LISTING_RELOAD_THREADS: set[QThread] = set()
_ACTIVE_DATASET_LISTING_STATS_THREADS: set[QThread] = set()


class DatasetListTableModel(QAbstractTableModel):
    def __init__(self, columns: List[DatasetListColumn], rows: List[Dict[str, Any]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._columns = columns
        self._rows = rows

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def update_row_fields(self, row_index: int, updates: Dict[str, Any]) -> None:
        if row_index < 0 or row_index >= len(self._rows):
            return
        if not isinstance(updates, dict) or not updates:
            return

        row = self._rows[row_index]
        changed_cols: List[int] = []
        for col_index, col in enumerate(self._columns):
            if col.key not in updates:
                continue
            new_val = updates.get(col.key)
            if row.get(col.key) == new_val:
                continue
            row[col.key] = new_val
            changed_cols.append(col_index)

        if not changed_cols:
            return

        for col_index in changed_cols:
            try:
                top_left = self.index(row_index, col_index)
                self.dataChanged.emit(top_left, top_left)
            except Exception:
                continue

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
            if col.key == "file_size":
                # 値は bytes(int) で保持し、表示用文字列はここで整形する。
                try:
                    from classes.dataset.util.data_entry_summary import format_size_with_bytes

                    if isinstance(value, int):
                        return format_size_with_bytes(value)
                except Exception:
                    pass
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
        self._tile_count_min: Optional[int] = None
        self._tile_count_max: Optional[int] = None
        self._file_count_min: Optional[int] = None
        self._file_count_max: Optional[int] = None
        self._tag_count_min: Optional[int] = None
        self._tag_count_max: Optional[int] = None
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

    def set_tile_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._tile_count_min = min_value
        self._tile_count_max = max_value
        self.invalidateFilter()

    def set_file_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._file_count_min = min_value
        self._file_count_max = max_value
        self.invalidateFilter()

    def set_tag_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._tag_count_min = min_value
        self._tag_count_max = max_value
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

        # tile count range
        if self._tile_count_min is not None or self._tile_count_max is not None:
            tile_col = self._find_column_by_label("タイル数")
            if tile_col >= 0:
                idx = model.index(source_row, tile_col, source_parent)
                val = model.data(idx, Qt.UserRole)
                try:
                    n = int(val)
                except Exception:
                    n = None
                if n is None:
                    return False
                if self._tile_count_min is not None and n < self._tile_count_min:
                    return False
                if self._tile_count_max is not None and n > self._tile_count_max:
                    return False

        # file count range
        if self._file_count_min is not None or self._file_count_max is not None:
            file_col = self._find_column_by_label("ファイル数")
            if file_col >= 0:
                idx = model.index(source_row, file_col, source_parent)
                val = model.data(idx, Qt.UserRole)
                try:
                    n = int(val)
                except Exception:
                    n = None
                if n is None:
                    return False
                if self._file_count_min is not None and n < self._file_count_min:
                    return False
                if self._file_count_max is not None and n > self._file_count_max:
                    return False

        # tag count range
        if self._tag_count_min is not None or self._tag_count_max is not None:
            tag_col = self._find_column_by_label("TAG数")
            if tag_col >= 0:
                idx = model.index(source_row, tag_col, source_parent)
                val = model.data(idx, Qt.UserRole)
                try:
                    n = int(val)
                except Exception:
                    n = None
                if n is None:
                    return False
                if self._tag_count_min is not None and n < self._tag_count_min:
                    return False
                if self._tag_count_max is not None and n > self._tag_count_max:
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

        # 数値列はUserRoleが数値なら数値として比較（DisplayRole文字列比較の誤ソートを避ける）
        try:
            l_num = model.data(left, Qt.UserRole)
            r_num = model.data(right, Qt.UserRole)
            if isinstance(l_num, (int, float)) and isinstance(r_num, (int, float)):
                return l_num < r_num
        except Exception:
            pass

        return super().lessThan(left, right)

    def _find_column_by_label(self, label: str) -> int:
        model = self.sourceModel()
        if model is None:
            return -1
        for i in range(model.columnCount()):
            if model.headerData(i, Qt.Horizontal, Qt.DisplayRole) == label:
                return i
        return -1


class PaginationProxyModel(QAbstractProxyModel):
    """Proxy model that slices the source rows into pages.

    - Source model should already apply filtering/sorting.
    - This model only selects the current page range.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page_size = 100  # 0 = all
        self._page = 1  # 1-based

    def set_page_size(self, page_size: int) -> None:
        size = max(0, int(page_size))
        if self._page_size == size:
            return
        self.beginResetModel()
        self._page_size = size
        self._page = 1
        self.endResetModel()

    def set_page(self, page: int) -> None:
        p = max(1, int(page))
        if self._page == p:
            return
        self.beginResetModel()
        self._page = p
        self.endResetModel()

    def page_size(self) -> int:
        return self._page_size

    def page(self) -> int:
        return self._page

    def total_rows(self) -> int:
        src = self.sourceModel()
        return int(src.rowCount()) if src is not None else 0

    def total_pages(self) -> int:
        total = self.total_rows()
        if self._page_size <= 0:
            return 1 if total >= 0 else 1
        if total <= 0:
            return 1
        return max(1, (total + self._page_size - 1) // self._page_size)

    def _page_start(self) -> int:
        if self._page_size <= 0:
            return 0
        return (max(1, self._page) - 1) * self._page_size

    def _page_end(self) -> int:
        if self._page_size <= 0:
            return self.total_rows()
        return min(self.total_rows(), self._page_start() + self._page_size)

    def setSourceModel(self, source_model) -> None:  # noqa: N802
        old = self.sourceModel()
        if old is source_model:
            return

        if old is not None:
            try:
                old.modelReset.disconnect(self._on_source_changed)
                old.layoutChanged.disconnect(self._on_source_changed)
                old.rowsInserted.disconnect(self._on_source_changed)
                old.rowsRemoved.disconnect(self._on_source_changed)
            except Exception:
                pass

        self.beginResetModel()
        super().setSourceModel(source_model)
        self._page = 1
        self.endResetModel()

        if source_model is not None:
            try:
                source_model.modelReset.connect(self._on_source_changed)
                source_model.layoutChanged.connect(self._on_source_changed)
                source_model.rowsInserted.connect(self._on_source_changed)
                source_model.rowsRemoved.connect(self._on_source_changed)
            except Exception:
                pass

    def _on_source_changed(self, *_args: object) -> None:
        # Clamp page to new total pages.
        max_page = self.total_pages()
        if self._page > max_page:
            self._page = max_page
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        src = self.sourceModel()
        if src is None:
            return 0
        start = self._page_start()
        end = self._page_end()
        return max(0, end - start)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        src = self.sourceModel()
        return int(src.columnCount()) if src is not None else 0

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:  # noqa: N802
        if parent.isValid():
            return QModelIndex()
        if row < 0 or column < 0:
            return QModelIndex()
        if row >= self.rowCount() or column >= self.columnCount():
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, _child: QModelIndex = QModelIndex()) -> QModelIndex:  # noqa: N802
        return QModelIndex()

    def mapToSource(self, proxy_index: QModelIndex) -> QModelIndex:  # noqa: N802
        if not proxy_index.isValid():
            return QModelIndex()
        src = self.sourceModel()
        if src is None:
            return QModelIndex()
        src_row = self._page_start() + proxy_index.row()
        return src.index(src_row, proxy_index.column())

    def mapFromSource(self, source_index: QModelIndex) -> QModelIndex:  # noqa: N802
        if not source_index.isValid():
            return QModelIndex()
        start = self._page_start()
        end = self._page_end()
        if source_index.row() < start or source_index.row() >= end:
            return QModelIndex()
        return self.index(source_index.row() - start, source_index.column())

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: N802
        src = self.sourceModel()
        if src is None:
            return None
        src_index = self.mapToSource(index)
        return src.data(src_index, role)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        src = self.sourceModel()
        if src is None:
            return None
        return src.headerData(section, orientation, role)

    def flags(self, index: QModelIndex):  # noqa: N802
        src = self.sourceModel()
        if src is None:
            return Qt.NoItemFlags
        return src.flags(self.mapToSource(index))

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:  # noqa: N802
        src = self.sourceModel()
        if src is None:
            return
        try:
            src.sort(column, order)
        except Exception:
            pass


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
        self._limit_proxy = PaginationProxyModel(self)

        self._filter_edits_by_key: Dict[str, QLineEdit] = {}
        self._filters_container: Optional[QWidget] = None
        self._filters_layout: Optional[QVBoxLayout] = None
        self._filters_summary_label: Optional[QLabel] = None
        self._filters_collapsed: bool = False
        self._toggle_filters_button: Optional[QPushButton] = None
        self._range_filters_container: Optional[QWidget] = None
        self._range_filters_layout: Optional[QGridLayout] = None
        self._text_filters_container: Optional[QWidget] = None
        self._text_filters_layout: Optional[QGridLayout] = None

        self._desc_len_min = QSpinBox(self)
        self._desc_len_max = QSpinBox(self)
        self._related_cnt_min = QSpinBox(self)
        self._related_cnt_max = QSpinBox(self)
        self._tile_cnt_min = QSpinBox(self)
        self._tile_cnt_max = QSpinBox(self)
        self._file_cnt_min = QSpinBox(self)
        self._file_cnt_max = QSpinBox(self)
        self._tag_cnt_min = QSpinBox(self)
        self._tag_cnt_max = QSpinBox(self)
        self._tool_open_callback = None

        # Debounce filter application to keep the table responsive while typing/clicking.
        self._filter_proxy = DatasetFilterProxyModel(self)
        self._reload_thread: Optional[QThread] = None
        self._reload_worker: Optional[QObject] = None

        self._stats_thread: Optional[QThread] = None
        self._stats_worker: Optional[QObject] = None
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(350)
        self._filter_apply_timer.timeout.connect(self._apply_filters_now)

        # Range filter containers (must be kept as instance attrs).
        # If we create these widgets inside `_rebuild_filters_panel()`, they can be GC'ed after
        # removal from the layout, which deletes their children (QSpinBox/QDateEdit) on Qt side.
        self._range_desc_widget: Optional[QWidget] = None
        self._range_tag_widget: Optional[QWidget] = None
        self._range_related_widget: Optional[QWidget] = None
        self._range_embargo_widget: Optional[QWidget] = None

        # Range filter relayout on resize (wrap when narrow)
        self._range_wrap_mode: Optional[bool] = None
        self._range_relayout_timer = QTimer(self)
        self._range_relayout_timer.setSingleShot(True)
        self._range_relayout_timer.setInterval(200)
        self._range_relayout_timer.timeout.connect(self._maybe_relayout_range_filters)

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

        buttons_row.addWidget(QLabel("ページ:"))
        self._page = QSpinBox(self)
        self._page.setObjectName("dataset_listing_page")
        self._page.setMinimum(1)
        self._page.setMaximum(1)
        self._page.setValue(1)
        try:
            from PySide6.QtWidgets import QAbstractSpinBox

            self._page.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        except Exception:
            pass
        buttons_row.addWidget(self._page)

        buttons_row.addWidget(QLabel("/"))
        self._total_pages = QLabel("1")
        self._total_pages.setObjectName("dataset_listing_total_pages")
        buttons_row.addWidget(self._total_pages)

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

        self._toggle_filters_button = QPushButton("フィルタ最小化", self)
        self._toggle_filters_button.setObjectName("dataset_listing_toggle_filters")
        buttons_row.addWidget(self._toggle_filters_button)

        root.addLayout(buttons_row)

        # Row 2: filters (must be directly above the table)
        # 要件: 縦スクロールバーは表示しない（必要ならテーブル領域を狭くする）
        self._filters_container = QWidget(self)
        self._filters_container.setObjectName("dataset_listing_filters_container")
        self._filters_layout = QVBoxLayout(self._filters_container)
        self._filters_layout.setContentsMargins(0, 0, 0, 0)
        self._filters_layout.setSpacing(6)

        # Summary label shown when filters are collapsed.
        self._filters_summary_label = QLabel("", self._filters_container)
        self._filters_summary_label.setObjectName("dataset_listing_filters_summary")
        try:
            self._filters_summary_label.setWordWrap(True)
        except Exception:
            pass
        self._filters_layout.addWidget(self._filters_summary_label)

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

            self._tile_cnt_min.setObjectName("dataset_listing_tile_cnt_min")
            self._tile_cnt_min.setMinimum(0)
            self._tile_cnt_min.setMaximum(999999)
            self._tile_cnt_min.setSpecialValueText("未設定")
            self._tile_cnt_min.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._tile_cnt_min.setValue(0)
            self._tile_cnt_max.setObjectName("dataset_listing_tile_cnt_max")
            self._tile_cnt_max.setMinimum(0)
            self._tile_cnt_max.setMaximum(999999)
            self._tile_cnt_max.setSpecialValueText("未設定")
            self._tile_cnt_max.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._tile_cnt_max.setValue(0)

            self._file_cnt_min.setObjectName("dataset_listing_file_cnt_min")
            self._file_cnt_min.setMinimum(0)
            self._file_cnt_min.setMaximum(999999)
            self._file_cnt_min.setSpecialValueText("未設定")
            self._file_cnt_min.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._file_cnt_min.setValue(0)
            self._file_cnt_max.setObjectName("dataset_listing_file_cnt_max")
            self._file_cnt_max.setMinimum(0)
            self._file_cnt_max.setMaximum(999999)
            self._file_cnt_max.setSpecialValueText("未設定")
            self._file_cnt_max.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._file_cnt_max.setValue(0)

            self._tag_cnt_min.setObjectName("dataset_listing_tag_cnt_min")
            self._tag_cnt_min.setMinimum(0)
            self._tag_cnt_min.setMaximum(999999)
            self._tag_cnt_min.setSpecialValueText("未設定")
            self._tag_cnt_min.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._tag_cnt_min.setValue(0)
            self._tag_cnt_max.setObjectName("dataset_listing_tag_cnt_max")
            self._tag_cnt_max.setMinimum(0)
            self._tag_cnt_max.setMaximum(999999)
            self._tag_cnt_max.setSpecialValueText("未設定")
            self._tag_cnt_max.setButtonSymbols(QAbstractSpinBox.PlusMinus)
            self._tag_cnt_max.setValue(0)

            # Keep range inputs from becoming too large, but avoid truncation.
            for sb in (
                self._desc_len_min,
                self._desc_len_max,
                self._tag_cnt_min,
                self._tag_cnt_max,
                self._related_cnt_min,
                self._related_cnt_max,
                self._tile_cnt_min,
                self._tile_cnt_max,
                self._file_cnt_min,
                self._file_cnt_max,
            ):
                try:
                    sb.setMinimumWidth(90)
                    sb.setMaximumWidth(140)
                except Exception:
                    pass

            for de in (self._embargo_from, self._embargo_to):
                try:
                    de.setMinimumWidth(110)
                    de.setMaximumWidth(160)
                except Exception:
                    pass
        except Exception:
            pass

        # Build persistent range filter containers.
        self._range_desc_widget = QWidget(self)
        desc_layout = QHBoxLayout(self._range_desc_widget)
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.addWidget(self._desc_len_min)
        desc_layout.addWidget(QLabel("～"))
        desc_layout.addWidget(self._desc_len_max)

        self._range_tag_widget = QWidget(self)
        tag_layout = QHBoxLayout(self._range_tag_widget)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.addWidget(self._tag_cnt_min)
        tag_layout.addWidget(QLabel("～"))
        tag_layout.addWidget(self._tag_cnt_max)

        self._range_related_widget = QWidget(self)
        rel_layout = QHBoxLayout(self._range_related_widget)
        rel_layout.setContentsMargins(0, 0, 0, 0)
        rel_layout.addWidget(self._related_cnt_min)
        rel_layout.addWidget(QLabel("～"))
        rel_layout.addWidget(self._related_cnt_max)

        self._range_embargo_widget = QWidget(self)
        emb_layout = QHBoxLayout(self._range_embargo_widget)
        emb_layout.setContentsMargins(0, 0, 0, 0)
        emb_layout.addWidget(self._embargo_from)
        emb_layout.addWidget(QLabel("～"))
        emb_layout.addWidget(self._embargo_to)

        self._clear_filters = QPushButton("フィルタクリア", self)

        self._range_tile_widget = QWidget(self)
        tile_layout = QHBoxLayout(self._range_tile_widget)
        tile_layout.setContentsMargins(0, 0, 0, 0)
        tile_layout.addWidget(self._tile_cnt_min)
        tile_layout.addWidget(QLabel("～"))
        tile_layout.addWidget(self._tile_cnt_max)

        self._range_file_widget = QWidget(self)
        file_layout = QHBoxLayout(self._range_file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self._file_cnt_min)
        file_layout.addWidget(QLabel("～"))
        file_layout.addWidget(self._file_cnt_max)

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

        self._spinner_overlay = SpinnerOverlay(self._table)

        # Theme styling
        self._apply_theme()

        # Wiring
        self._row_limit.valueChanged.connect(self._apply_row_limit)
        self._page.valueChanged.connect(self._apply_page)
        self._embargo_from.dateChanged.connect(self._schedule_apply_filters)
        self._embargo_to.dateChanged.connect(self._schedule_apply_filters)
        self._desc_len_min.valueChanged.connect(self._schedule_apply_filters)
        self._desc_len_max.valueChanged.connect(self._schedule_apply_filters)
        self._tag_cnt_min.valueChanged.connect(self._schedule_apply_filters)
        self._tag_cnt_max.valueChanged.connect(self._schedule_apply_filters)
        self._related_cnt_min.valueChanged.connect(self._schedule_apply_filters)
        self._related_cnt_max.valueChanged.connect(self._schedule_apply_filters)
        self._tile_cnt_min.valueChanged.connect(self._schedule_apply_filters)
        self._tile_cnt_max.valueChanged.connect(self._schedule_apply_filters)
        self._file_cnt_min.valueChanged.connect(self._schedule_apply_filters)
        self._file_cnt_max.valueChanged.connect(self._schedule_apply_filters)
        self._clear_filters.clicked.connect(self._clear_all_filters)
        self._select_columns.clicked.connect(self._open_column_selector)
        self._reset_columns.clicked.connect(self._reset_column_visibility)
        self._export_csv.clicked.connect(lambda: self._export("csv"))
        self._export_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self._reload.clicked.connect(self.reload_data)

        if self._toggle_filters_button is not None:
            self._toggle_filters_button.clicked.connect(self._toggle_filters_collapsed)

        self._table.clicked.connect(self._on_table_clicked)

        # Initialize
        # 初回表示の体感を改善するため、ウィジェット描画後に読み込みを開始する。
        self._status.setText("読み込み中...")
        # NOTE: reload_data() 呼び出し前でも、初回表示待ちが目立つためスピナーを即表示する。
        # reload_data() 内でも _show_loading() するが、二重呼び出しは許容する。
        self._show_loading()
        if os.environ.get("PYTEST_CURRENT_TEST"):
            # テストは決定性を優先して同期で読み込む
            self.reload_data()
        else:
            try:
                QTimer.singleShot(0, self.reload_data)
            except Exception:
                self.reload_data()

        # Ensure initial state
        self._set_filters_collapsed(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self._range_relayout_timer.start()
        except Exception:
            self._maybe_relayout_range_filters()

    def _compute_should_wrap_range_filters(self) -> bool:
        # 要件: 範囲フィルタ群は常に2行で表示する。
        return True

    def _maybe_relayout_range_filters(self) -> None:
        wrap = self._compute_should_wrap_range_filters()
        if self._range_wrap_mode is None or self._range_wrap_mode != wrap:
            self._range_wrap_mode = wrap
            self._relayout_range_filters(wrap)

    def _relayout_range_filters(self, wrap: bool) -> None:
        if self._range_filters_layout is None:
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

        entries: List[tuple[str, Optional[QWidget]]] = [
            ("説明文字数", self._range_desc_widget),
            ("TAG数", self._range_tag_widget),
            ("関連データセット", self._range_related_widget),
            ("タイル数", self._range_tile_widget),
            ("ファイル数", self._range_file_widget),
            ("エンバーゴ期間終了日", self._range_embargo_widget),
        ]
        entries = [(lbl, w) for (lbl, w) in entries if w is not None]

        r = 0
        c = 0
        per_row = 3 if wrap else len(entries)
        for i, (lbl, w) in enumerate(entries):
            if wrap and i > 0 and (i % per_row) == 0:
                r += 1
                c = 0
            self._range_filters_layout.addWidget(bold_label(lbl), r, c)
            c += 1
            self._range_filters_layout.addWidget(w, r, c)
            c += 1

        if self._clear_filters is not None:
            # 範囲フィルタが2行になる場合でも、クリアボタンは3行目に落とさず
            # 最終行の末尾に配置する。
            self._range_filters_layout.addWidget(self._clear_filters, r, c)

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

        # Filters container background
        try:
            # Add padding via QSS for better visibility.
            filters_qss = (
                f"QWidget#dataset_listing_filters_container {{"
                f"  background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};"
                f"  border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};"
                f"  border-radius: 4px;"
                f"  padding: 6px;"
                f"}}"
            )
            self.setStyleSheet(self.styleSheet() + filters_qss)
        except Exception:
            pass

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

    def _is_running_under_pytest(self) -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST"))

    def _show_loading(self) -> None:
        try:
            self._status.setText("読み込み中...")
        except Exception:
            pass
        try:
            self._spinner_overlay.show_message("読み込み中…")
            self._spinner_overlay.start()
        except Exception:
            pass

    def _hide_loading(self) -> None:
        try:
            self._spinner_overlay.stop()
        except Exception:
            pass

    def _cancel_stats_fill(self) -> None:
        worker = self._stats_worker
        thread = self._stats_thread

        if worker is not None:
            try:
                getattr(worker, "cancel")()
            except Exception:
                pass

        if thread is not None and thread.isRunning():
            try:
                thread.quit()
            except Exception:
                pass

        self._stats_thread = None
        self._stats_worker = None

    class _StatsFillWorker(QObject):
        row_ready = Signal(int, object, object, object)
        finished = Signal()

        def __init__(self, tasks: List[tuple[int, str]]):
            super().__init__()
            self._tasks = tasks
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            from config.common import get_dynamic_file_path
            from classes.dataset.util.data_entry_summary import compute_summary_from_payload

            import json
            import os

            for row_index, dataset_id in self._tasks:
                if self._cancelled:
                    break

                dsid = str(dataset_id or "").strip()
                if not dsid:
                    continue

                try:
                    path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dsid}.json")
                    if not path or not os.path.exists(path):
                        continue
                    with open(path, "r", encoding="utf-8") as fh:
                        payload = json.load(fh)
                except Exception:
                    continue

                if not isinstance(payload, dict):
                    continue

                tiles = payload.get("data")
                tile_count = len(tiles) if isinstance(tiles, list) else 0

                shared2_file_count = None
                file_size_bytes = None
                try:
                    summary = compute_summary_from_payload(payload, prefer_cached_files=False)
                except Exception:
                    summary = None

                shared2 = summary.get("shared2") if isinstance(summary, dict) else None
                if isinstance(shared2, dict):
                    try:
                        shared2_file_count = int(shared2.get("count", 0) or 0)
                    except Exception:
                        shared2_file_count = None

                    try:
                        shared2_bytes = int(shared2.get("bytes", 0) or 0)
                    except Exception:
                        shared2_bytes = None

                    if shared2_bytes is not None:
                        file_size_bytes = shared2_bytes

                if self._cancelled:
                    break

                try:
                    self.row_ready.emit(row_index, tile_count, shared2_file_count, file_size_bytes)
                except Exception:
                    continue

            try:
                self.finished.emit()
            except Exception:
                pass

    def _on_stats_row_ready(self, row_index: int, tile_count: object, file_count: object, file_size_bytes: object) -> None:
        if self._model is None:
            return
        try:
            updates = {
                "tile_count": tile_count,
                "file_count": file_count,
                # NOTE: file_size は表示文字列ではなく bytes(int) を保持する。
                "file_size": file_size_bytes,
            }
            self._model.update_row_fields(int(row_index), updates)
        except Exception:
            return

    def _on_stats_fill_finished(self) -> None:
        # Re-evaluate filters once after bulk stats fill.
        try:
            self._filter_proxy.invalidateFilter()
        except Exception:
            pass

        self._stats_thread = None
        self._stats_worker = None

    def _start_stats_fill_async(self, rows: List[Dict[str, Any]]) -> None:
        if self._is_running_under_pytest():
            return
        if self._model is None:
            return
        if self._stats_thread is not None and self._stats_thread.isRunning():
            return

        tasks: List[tuple[int, str]] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid:
                continue
            # Already computed
            file_size_val = row.get("file_size")
            file_size_is_filled = file_size_val is not None and str(file_size_val).strip() != ""
            if row.get("tile_count") is not None and row.get("file_count") is not None and file_size_is_filled:
                continue
            tasks.append((i, dsid))

        if not tasks:
            return

        thread = QThread()
        worker = DatasetListingWidget._StatsFillWorker(tasks)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.row_ready.connect(self._on_stats_row_ready)
        worker.finished.connect(self._on_stats_fill_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._stats_worker = worker
        self._stats_thread = thread

        _ACTIVE_DATASET_LISTING_STATS_THREADS.add(thread)
        try:
            setattr(thread, "_stats_worker", worker)
        except Exception:
            pass
        try:
            thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_STATS_THREADS.discard(thread))
        except Exception:
            pass

        thread.start()

    class _ReloadWorker(QObject):
        finished = Signal(object, object, object)

        def run(self) -> None:
            try:
                columns, rows = build_dataset_list_rows_from_files()
                self.finished.emit(columns, rows, None)
            except Exception as exc:
                self.finished.emit(None, None, str(exc))

    def _update_table_data(self, columns, rows) -> None:
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

        # Large workspaces may skip expensive stats during initial load.
        # Fill tile/file stats in background to restore legacy behavior without blocking UI.
        try:
            self._start_stats_fill_async(rows)
        except Exception:
            pass

        # 改行表示がある列のため、表示行数が少ない場合のみ行高を内容に合わせる
        try:
            limit = int(self._row_limit.value())
            if limit <= 0 or limit <= 200:
                self._table.resizeRowsToContents()
        except Exception:
            pass

    def _on_reload_thread_finished(self) -> None:
        self._reload_thread = None
        self._reload_worker = None

    def _on_reload_finished(self, columns, rows, error_message) -> None:
        self._hide_loading()
        if error_message:
            try:
                self._status.setText("読み込み失敗")
            except Exception:
                pass
            return
        if columns is None or rows is None:
            return
        self._update_table_data(columns, rows)

    def _start_reload_async(self) -> None:
        if self._reload_thread is not None and self._reload_thread.isRunning():
            return

        self._cancel_stats_fill()

        self._show_loading()

        # ウィジェット破棄と同時にスレッドが破棄されると
        # "QThread: Destroyed while thread '' is still running" の原因になる。
        # 親を付けず、明示的に参照を保持して寿命を管理する。
        thread = QThread()
        worker = DatasetListingWidget._ReloadWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_reload_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_reload_thread_finished)

        # 参照保持（GC/ウィジェット破棄に伴う不意な破棄を避ける）
        self._reload_worker = worker
        _ACTIVE_DATASET_LISTING_RELOAD_THREADS.add(thread)
        try:
            setattr(thread, "_reload_worker", worker)
        except Exception:
            pass
        try:
            thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_RELOAD_THREADS.discard(thread))
        except Exception:
            pass

        self._reload_thread = thread
        thread.start()

    def _reload_data_sync(self) -> None:
        self._cancel_stats_fill()
        self._show_loading()
        try:
            columns, rows = build_dataset_list_rows_from_files()
        except Exception:
            self._hide_loading()
            try:
                self._status.setText("読み込み失敗")
            except Exception:
                pass
            return
        self._hide_loading()
        self._update_table_data(columns, rows)

    def reload_data(self) -> None:
        if self._is_running_under_pytest():
            self._reload_data_sync()
        else:
            self._start_reload_async()

    def _apply_row_limit(self) -> None:
        self._limit_proxy.set_page_size(int(self._row_limit.value()))
        self._update_pagination_controls()

    def _apply_page(self) -> None:
        try:
            self._limit_proxy.set_page(int(self._page.value()))
        except Exception:
            return

    def _clear_all_filters(self) -> None:
        for edit in self._filter_edits_by_key.values():
            edit.setText("")
        # Use 0/invalid as "no filter" by setting both to minimum and then disabling via internal state.
        self._embargo_from.setDate(QDate(2000, 1, 1))
        self._embargo_to.setDate(QDate(2000, 1, 1))
        try:
            self._desc_len_min.setValue(0)
            self._desc_len_max.setValue(0)
            self._tag_cnt_min.setValue(0)
            self._tag_cnt_max.setValue(0)
            self._related_cnt_min.setValue(0)
            self._related_cnt_max.setValue(0)
            self._tile_cnt_min.setValue(0)
            self._tile_cnt_max.setValue(0)
            self._file_cnt_min.setValue(0)
            self._file_cnt_max.setValue(0)
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

        # Tile count range
        tile_min = int(self._tile_cnt_min.value())
        tile_max = int(self._tile_cnt_max.value())
        self._filter_proxy.set_tile_count_range(
            None if tile_min <= 0 else tile_min,
            None if tile_max <= 0 else tile_max,
        )

        # File count range
        file_min = int(self._file_cnt_min.value())
        file_max = int(self._file_cnt_max.value())
        self._filter_proxy.set_file_count_range(
            None if file_min <= 0 else file_min,
            None if file_max <= 0 else file_max,
        )

        # Tag count range
        tag_min = int(self._tag_cnt_min.value())
        tag_max = int(self._tag_cnt_max.value())
        self._filter_proxy.set_tag_count_range(
            None if tag_min <= 0 else tag_min,
            None if tag_max <= 0 else tag_max,
        )

        self._update_pagination_controls()

        self._update_filters_summary()

    def _toggle_filters_collapsed(self) -> None:
        self._set_filters_collapsed(not self._filters_collapsed)

    def _set_filters_collapsed(self, collapsed: bool) -> None:
        self._filters_collapsed = bool(collapsed)

        if self._range_filters_container is not None:
            self._range_filters_container.setVisible(not self._filters_collapsed)
        if self._text_filters_container is not None:
            self._text_filters_container.setVisible(not self._filters_collapsed)

        if self._filters_summary_label is not None:
            self._filters_summary_label.setVisible(self._filters_collapsed)

        if self._toggle_filters_button is not None:
            self._toggle_filters_button.setText("フィルタ表示" if self._filters_collapsed else "フィルタ最小化")

        self._update_filters_summary()

    def _update_filters_summary(self) -> None:
        if self._filters_summary_label is None:
            return
        if not self._filters_collapsed:
            self._filters_summary_label.setText("")
            return

        parts: List[str] = []

        def _format_range(min_text: str, max_text: str) -> str:
            if min_text and max_text:
                return f"{min_text}～{max_text}"
            if min_text and not max_text:
                return f"{min_text}～"
            if not min_text and max_text:
                return f"～{max_text}"
            return ""

        # 説明文字数
        try:
            min_v = int(self._desc_len_min.value())
            max_v = int(self._desc_len_max.value())
            min_txt = "" if min_v <= 0 else str(min_v)
            max_txt = "" if max_v <= 0 else str(max_v)
            rng = _format_range(min_txt, max_txt)
            if rng:
                parts.append(f"説明文字数:{rng}")
        except Exception:
            pass

        # TAG数
        try:
            min_v = int(self._tag_cnt_min.value())
            max_v = int(self._tag_cnt_max.value())
            min_txt = "" if min_v <= 0 else str(min_v)
            max_txt = "" if max_v <= 0 else str(max_v)
            rng = _format_range(min_txt, max_txt)
            if rng:
                parts.append(f"TAG数:{rng}")
        except Exception:
            pass

        # 関連データセット
        try:
            min_v = int(self._related_cnt_min.value())
            max_v = int(self._related_cnt_max.value())
            min_txt = "" if min_v <= 0 else str(min_v)
            max_txt = "" if max_v <= 0 else str(max_v)
            rng = _format_range(min_txt, max_txt)
            if rng:
                parts.append(f"関連データセット:{rng}")
        except Exception:
            pass

        # エンバーゴ期間終了日
        try:
            date_from = self._qdate_to_date(self._embargo_from.date())
            date_to = self._qdate_to_date(self._embargo_to.date())
            if date_from == datetime.date(2000, 1, 1):
                date_from = None
            if date_to == datetime.date(2000, 1, 1):
                date_to = None
            min_txt = "" if date_from is None else date_from.isoformat()
            max_txt = "" if date_to is None else date_to.isoformat()
            rng = _format_range(min_txt, max_txt)
            if rng:
                parts.append(f"エンバーゴ期間終了日:{rng}")
        except Exception:
            pass

        # タイル数
        try:
            min_v = int(self._tile_cnt_min.value())
            max_v = int(self._tile_cnt_max.value())
            min_txt = "" if min_v <= 0 else str(min_v)
            max_txt = "" if max_v <= 0 else str(max_v)
            rng = _format_range(min_txt, max_txt)
            if rng:
                parts.append(f"タイル数:{rng}")
        except Exception:
            pass

        # ファイル数
        try:
            min_v = int(self._file_cnt_min.value())
            max_v = int(self._file_cnt_max.value())
            min_txt = "" if min_v <= 0 else str(min_v)
            max_txt = "" if max_v <= 0 else str(max_v)
            rng = _format_range(min_txt, max_txt)
            if rng:
                parts.append(f"ファイル数:{rng}")
        except Exception:
            pass

        # テキストフィルタ
        try:
            key_to_label = {c.key: c.label for c in self._columns}
            for key, edit in self._filter_edits_by_key.items():
                text = (edit.text() or "").strip()
                if not text:
                    continue
                label = key_to_label.get(key, key)
                parts.append(f"{label}:{text}")
        except Exception:
            pass

        self._filters_summary_label.setText(" / ".join(parts))

    def _update_pagination_controls(self) -> None:
        try:
            total_pages = int(self._limit_proxy.total_pages())
        except Exception:
            total_pages = 1
        if total_pages <= 0:
            total_pages = 1

        try:
            self._total_pages.setText(str(total_pages))
        except Exception:
            pass

        # Disable paging controls for "全件"
        try:
            page_size = int(self._row_limit.value())
        except Exception:
            page_size = 0

        try:
            if page_size <= 0:
                self._page.blockSignals(True)
                self._page.setMaximum(1)
                self._page.setValue(1)
                self._page.setEnabled(False)
                self._limit_proxy.set_page(1)
                self._page.blockSignals(False)
                return
        except Exception:
            pass

        try:
            self._page.setEnabled(True)
            self._page.blockSignals(True)
            self._page.setMaximum(total_pages)
            if self._page.value() > total_pages:
                self._page.setValue(total_pages)
            if self._page.value() < 1:
                self._page.setValue(1)
            self._limit_proxy.set_page(int(self._page.value()))
            self._page.blockSignals(False)
        except Exception:
            try:
                self._page.blockSignals(False)
            except Exception:
                pass

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

        default_name = build_dataset_listing_export_default_filename(fmt)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存",
            default_name,
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

        data_rows: List[List[Any]] = []
        for r in range(model.rowCount()):
            row_values: List[Any] = []
            for c in visible_cols:
                idx = model.index(r, c)
                col_key = ""
                try:
                    col_key = self._columns[c].key
                except Exception:
                    col_key = ""

                if col_key == "file_size":
                    # エクスポートでは表示用の複合文字列ではなく bytes(int) を出力する。
                    raw = model.data(idx, Qt.UserRole)
                    if isinstance(raw, int):
                        row_values.append(raw)
                        continue

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

        # --- Range filters (non-text): wrap when narrow ---
        self._relayout_range_filters(self._compute_should_wrap_range_filters())

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
            # NOTE: range-filter columns and non-meaningful text-filter columns are excluded.
            # - tool_open: 列は維持するが、列フィルタ(テキスト)は不要。
            # - file_size: bytes(int) を保持するため、列フィルタ(テキスト)は不要。
            # - tag_count: 数値範囲フィルタで扱う。
            if cdef.key in {
                "description_len",
                "related_datasets_count",
                "embargo_date",
                "tile_count",
                "file_count",
                "tag_count",
                "tool_open",
                "file_size",
            }:
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

        self._update_filters_summary()

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
