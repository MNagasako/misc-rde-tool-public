"""Subgroup listing widget for the Subgroup "一覧" tab."""

from __future__ import annotations

import datetime
import json
import os
import re
import webbrowser
from typing import Any, Dict, List, Optional

import pandas as pd

from qt_compat.core import Qt, QUrl, QThread, Signal
from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QScrollArea,
    QFileDialog,
    QMessageBox,
    QCheckBox,
    QShortcut,
    QSizePolicy,
)

from PySide6.QtCore import (
    QObject,
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    QTimer,
    QAbstractProxyModel,
    QRect,
)
from PySide6.QtGui import QKeySequence, QBrush, QFont, QDesktopServices
from PySide6.QtWidgets import QTableView, QStyledItemDelegate, QStyle

from classes.subgroup.util.subgroup_list_table_records import (
    SubgroupListColumn,
    build_subgroup_list_rows_from_files,
)
from classes.dataset.ui.spinner_overlay import SpinnerOverlay
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color, get_qcolor
from config.common import get_dynamic_file_path


_ACTIVE_SUBGROUP_LISTING_RELOAD_THREADS: set[QThread] = set()


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
    def __init__(self, parent: QWidget, columns: List[SubgroupListColumn], visible_by_key: Dict[str, bool]):
        super().__init__(parent)
        self.setWindowTitle("列選択")
        self._columns = columns

        self._default_visible_by_key: Dict[str, bool] = {
            c.key: bool(getattr(c, "default_visible", True)) for c in columns
        }

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

        quick_buttons = QHBoxLayout()

        self._btn_select_all = QPushButton("全選択", self)
        self._btn_select_all.setObjectName("column_selector_select_all")
        self._btn_select_all.clicked.connect(self._select_all)
        quick_buttons.addWidget(self._btn_select_all)

        self._btn_select_none = QPushButton("全非選択", self)
        self._btn_select_none.setObjectName("column_selector_select_none")
        self._btn_select_none.clicked.connect(self._select_none)
        quick_buttons.addWidget(self._btn_select_none)

        self._btn_reset = QPushButton("列リセット", self)
        self._btn_reset.setObjectName("column_selector_reset")
        self._btn_reset.clicked.connect(self._reset_to_default)
        quick_buttons.addWidget(self._btn_reset)

        quick_buttons.addStretch(1)
        layout.addLayout(quick_buttons)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_all(self) -> None:
        for cb in self._checkbox_by_key.values():
            try:
                cb.setChecked(True)
            except Exception:
                pass

    def _select_none(self) -> None:
        for cb in self._checkbox_by_key.values():
            try:
                cb.setChecked(False)
            except Exception:
                pass

    def _reset_to_default(self) -> None:
        for key, cb in self._checkbox_by_key.items():
            try:
                cb.setChecked(bool(self._default_visible_by_key.get(key, True)))
            except Exception:
                pass

    def get_visible_by_key(self) -> Dict[str, bool]:
        return {k: cb.isChecked() for k, cb in self._checkbox_by_key.items()}


class SubgroupListTableModel(QAbstractTableModel):
    RAW_TEXT_ROLE = int(Qt.UserRole) + 100
    _MAX_ITEM_TEXT_LEN = 60

    @classmethod
    def _truncate_multiline(cls, text: str) -> tuple[str, bool]:
        s = "" if text is None else str(text)
        if not s:
            return "", False
        lines = s.splitlines() or [s]
        truncated = False
        out: List[str] = []
        max_len = int(cls._MAX_ITEM_TEXT_LEN)
        for line in lines:
            ln = "" if line is None else str(line)
            if max_len > 0 and len(ln) > max_len:
                out.append(ln[: max_len - 1] + "…")
                truncated = True
            else:
                out.append(ln)
        return "\n".join(out), truncated
    def __init__(
        self,
        columns: List[SubgroupListColumn],
        rows: List[Dict[str, Any]],
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._columns = columns
        self._rows = rows

    def set_columns_and_rows(self, columns: List[SubgroupListColumn], rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._columns = columns
        self._rows = rows
        self.endResetModel()

    def get_columns(self) -> List[SubgroupListColumn]:
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
        if orientation == Qt.Horizontal and 0 <= section < len(self._columns):
            return self._columns[section].label
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        col = self._columns[index.column()]

        raw_value = row.get(col.key)

        if role == Qt.DisplayRole:
            value = "" if raw_value is None else str(raw_value)
            if col.key in {"members", "related_datasets", "related_samples"}:
                display, _truncated = self._truncate_multiline(value)
                return display
            return value

        if role == self.RAW_TEXT_ROLE:
            return "" if raw_value is None else str(raw_value)

        if role == Qt.ToolTipRole:
            if col.key in {"members", "related_datasets", "related_samples"}:
                value = "" if raw_value is None else str(raw_value)
                _display, truncated = self._truncate_multiline(value)
                return value if truncated else None
            return None

        if role == Qt.UserRole:
            if col.key == "subgroup_name":
                subgroup_id = str(row.get("subgroup_id") or "").strip()
                if subgroup_id:
                    return f"https://rde.nims.go.jp/rde/datasets/groups/{subgroup_id}"
                return ""
            if col.key == "related_samples":
                ids = row.get("related_sample_ids")
                if isinstance(ids, list):
                    urls = [
                        f"https://rde-material.nims.go.jp/samples/samples/{str(sid).strip()}"
                        for sid in ids
                        if isinstance(sid, str) and sid.strip()
                    ]
                    return urls
                return []
            if col.key == "related_datasets":
                ids = row.get("related_dataset_ids")
                if isinstance(ids, list):
                    urls = [
                        f"https://rde.nims.go.jp/rde/datasets/{str(did).strip()}"
                        for did in ids
                        if isinstance(did, str) and did.strip()
                    ]
                    return urls
                return []
            return row.get(col.key)

        if role == Qt.ForegroundRole:
            if col.key == "subgroup_name":
                subgroup_id = str(row.get("subgroup_id") or "").strip()
                if subgroup_id:
                    return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key in {"related_samples", "related_datasets"}:
                urls = row.get("related_sample_ids") if col.key == "related_samples" else row.get("related_dataset_ids")
                if isinstance(urls, list) and any(isinstance(x, str) and x.strip() for x in urls):
                    return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key.endswith("_count"):
                return QBrush(get_color(ThemeKey.TEXT_PRIMARY))

        if role == Qt.FontRole:
            if col.key == "subgroup_name":
                subgroup_id = str(row.get("subgroup_id") or "").strip()
                if subgroup_id:
                    f = QFont()
                    f.setUnderline(True)
                    return f
            if col.key in {"related_samples", "related_datasets"}:
                ids = row.get("related_sample_ids") if col.key == "related_samples" else row.get("related_dataset_ids")
                if isinstance(ids, list) and any(isinstance(x, str) and x.strip() for x in ids):
                    f = QFont()
                    f.setUnderline(True)
                    return f

        if role == Qt.TextAlignmentRole:
            if col.key.endswith("_count"):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            if col.key in {"members", "related_datasets", "related_samples"}:
                return int(Qt.AlignLeft | Qt.AlignTop)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


class SubgroupFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: Dict[int, str] = {}
        self._column_filter_patterns: Dict[int, List[re.Pattern]] = {}

        self._subject_min: Optional[int] = None
        self._subject_max: Optional[int] = None
        self._fund_min: Optional[int] = None
        self._fund_max: Optional[int] = None
        self._member_min: Optional[int] = None
        self._member_max: Optional[int] = None
        self._rel_ds_min: Optional[int] = None
        self._rel_ds_max: Optional[int] = None
        self._rel_sample_min: Optional[int] = None
        self._rel_sample_max: Optional[int] = None

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    @staticmethod
    def _split_filter_terms(text: str) -> List[str]:
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
        escaped = re.escape(t).replace(r"\*", ".*")
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

    def set_subject_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._subject_min = min_value
        self._subject_max = max_value
        self.invalidateFilter()

    def set_fund_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._fund_min = min_value
        self._fund_max = max_value
        self.invalidateFilter()

    def set_member_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._member_min = min_value
        self._member_max = max_value
        self.invalidateFilter()

    def set_related_datasets_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._rel_ds_min = min_value
        self._rel_ds_max = max_value
        self.invalidateFilter()

    def set_related_samples_count_range(self, min_value: Optional[int], max_value: Optional[int]) -> None:
        self._rel_sample_min = min_value
        self._rel_sample_max = max_value
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if model is None:
            return True

        # per-column text filters: OR within a column, AND across columns
        if self._column_filter_patterns:
            for col_idx, patterns in self._column_filter_patterns.items():
                if col_idx < 0 or col_idx >= model.columnCount():
                    continue
                idx = model.index(source_row, col_idx, source_parent)
                hay = str(
                    model.data(idx, SubgroupListTableModel.RAW_TEXT_ROLE)
                    or model.data(idx, Qt.DisplayRole)
                    or ""
                )
                if not any(p.search(hay) for p in patterns):
                    return False

        def _range(label: str, mn: Optional[int], mx: Optional[int]) -> bool:
            if mn is None and mx is None:
                return True
            col = self._find_column_by_label(label)
            if col < 0:
                return True
            idx = model.index(source_row, col, source_parent)
            val = model.data(idx, Qt.UserRole)
            try:
                n = int(val)
            except Exception:
                return False
            if mn is not None and n < mn:
                return False
            if mx is not None and n > mx:
                return False
            return True

        if not _range("課題数", self._subject_min, self._subject_max):
            return False
        if not _range("研究資金数", self._fund_min, self._fund_max):
            return False
        if not _range("メンバー数", self._member_min, self._member_max):
            return False
        if not _range("関連データセット数", self._rel_ds_min, self._rel_ds_max):
            return False
        if not _range("関連試料数", self._rel_sample_min, self._rel_sample_max):
            return False

        return True

    def _find_column_by_label(self, label: str) -> int:
        model = self.sourceModel()
        if model is None:
            return -1
        for i in range(model.columnCount()):
            if model.headerData(i, Qt.Horizontal, Qt.DisplayRole) == label:
                return i
        return -1


class SubgroupListingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._columns: List[SubgroupListColumn] = []
        self._rows: List[Dict[str, Any]] = []
        self._model: Optional[SubgroupListTableModel] = None
        self._filter_proxy = SubgroupFilterProxyModel(self)
        self._limit_proxy = PaginationProxyModel(self)

        self._status: Optional[QLabel] = None
        self._row_limit: Optional[QSpinBox] = None
        self._page: Optional[QSpinBox] = None
        self._total_pages: Optional[QLabel] = None
        self._select_columns: Optional[QPushButton] = None
        self._reset_columns: Optional[QPushButton] = None
        self._export_csv: Optional[QPushButton] = None
        self._export_xlsx: Optional[QPushButton] = None

        self._filters_collapsed = False
        self._filter_edits_by_key: Dict[str, QLineEdit] = {}

        self._spinner_overlay: Optional[SpinnerOverlay] = None
        self._reload_thread: Optional[QThread] = None
        self._reload_worker: Optional[QObject] = None

        self._filters_container: Optional[QWidget] = None
        self._filters_summary_label: Optional[QLabel] = None
        self._range_filters_container: Optional[QWidget] = None
        self._range_filters_layout: Optional[QGridLayout] = None
        self._text_filters_container: Optional[QWidget] = None
        self._text_filters_layout: Optional[QGridLayout] = None
        self._toggle_filters_button: Optional[QPushButton] = None
        self._reload: Optional[QPushButton] = None

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.timeout.connect(self._apply_filters_now)

        # Row height relayout on column resize / data changes
        self._row_height_timer = QTimer(self)
        self._row_height_timer.setSingleShot(True)
        self._row_height_timer.setInterval(200)
        self._row_height_timer.timeout.connect(self._adjust_row_heights_to_max_lines)

        # Range filter relayout on resize (wrap when narrow)
        self._range_wrap_mode: Optional[bool] = None
        self._range_relayout_timer = QTimer(self)
        self._range_relayout_timer.setSingleShot(True)
        self._range_relayout_timer.setInterval(200)
        self._range_relayout_timer.timeout.connect(self._maybe_relayout_range_filters)

        # Range spinboxes
        self._subject_min = QSpinBox(self)
        self._subject_max = QSpinBox(self)
        self._fund_min = QSpinBox(self)
        self._fund_max = QSpinBox(self)
        self._member_min = QSpinBox(self)
        self._member_max = QSpinBox(self)
        self._rel_ds_min = QSpinBox(self)
        self._rel_ds_max = QSpinBox(self)
        self._rel_sample_min = QSpinBox(self)
        self._rel_sample_max = QSpinBox(self)

        self._range_subject_widget: Optional[QWidget] = None
        self._range_fund_widget: Optional[QWidget] = None
        self._range_member_widget: Optional[QWidget] = None
        self._range_rel_ds_widget: Optional[QWidget] = None
        self._range_rel_sample_widget: Optional[QWidget] = None

        self._setup_ui()
        self._set_filters_collapsed(False)

        # 初回表示の体感を改善するため、ウィジェット描画後に読み込みを開始する。
        try:
            if self._status is not None:
                self._status.setText("読み込み中...")
        except Exception:
            pass

        if os.environ.get("PYTEST_CURRENT_TEST"):
            # テストは決定性を優先して同期で読み込む
            self.reload_data()
        else:
            try:
                QTimer.singleShot(0, self.reload_data)
            except Exception:
                self.reload_data()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

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
        self._page.setObjectName("subgroup_listing_page")
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
        self._total_pages.setObjectName("subgroup_listing_total_pages")
        buttons_row.addWidget(self._total_pages)

        self._select_columns = QPushButton("列選択", self)
        buttons_row.addWidget(self._select_columns)

        self._reset_columns = QPushButton("列リセット", self)
        buttons_row.addWidget(self._reset_columns)

        self._export_csv = QPushButton("CSV出力", self)
        self._export_xlsx = QPushButton("XLSX出力", self)
        buttons_row.addWidget(self._export_csv)
        buttons_row.addWidget(self._export_xlsx)

        self._adjust_row_heights_btn = QPushButton("行高さ調整", self)
        self._adjust_row_heights_btn.setObjectName("subgroup_listing_adjust_row_heights")
        buttons_row.addWidget(self._adjust_row_heights_btn)

        self._reload = QPushButton("更新", self)
        buttons_row.addWidget(self._reload)

        self._toggle_filters_button = QPushButton("フィルタ最小化", self)
        self._toggle_filters_button.setObjectName("subgroup_listing_toggle_filters")
        buttons_row.addWidget(self._toggle_filters_button)

        root.addLayout(buttons_row)

        # Filters container
        self._filters_container = QWidget(self)
        self._filters_container.setObjectName("subgroup_listing_filters_container")
        filters_layout = QVBoxLayout(self._filters_container)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(6)

        self._filters_summary_label = QLabel("", self._filters_container)
        self._filters_summary_label.setObjectName("subgroup_listing_filters_summary")
        try:
            self._filters_summary_label.setWordWrap(True)
        except Exception:
            pass
        filters_layout.addWidget(self._filters_summary_label)

        self._range_filters_container = QWidget(self._filters_container)
        self._range_filters_layout = QGridLayout(self._range_filters_container)
        self._range_filters_layout.setContentsMargins(0, 0, 0, 0)
        self._range_filters_layout.setHorizontalSpacing(8)
        self._range_filters_layout.setVerticalSpacing(6)
        filters_layout.addWidget(self._range_filters_container)

        self._text_filters_container = QWidget(self._filters_container)
        self._text_filters_layout = QGridLayout(self._text_filters_container)
        self._text_filters_layout.setContentsMargins(0, 0, 0, 0)
        self._text_filters_layout.setHorizontalSpacing(8)
        self._text_filters_layout.setVerticalSpacing(6)
        filters_layout.addWidget(self._text_filters_container)

        self._clear_filters = QPushButton("フィルタクリア", self)

        self._init_range_spinboxes()
        self._rebuild_range_filters_panel()

        try:
            self._filters_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        root.addWidget(self._filters_container)

        # Table
        self._table = QTableView(self)
        self._table.setSortingEnabled(True)
        try:
            # Avoid word-wrap driven huge row heights; we control row heights explicitly.
            self._table.setWordWrap(False)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QAbstractItemView

            self._table.setSelectionBehavior(QAbstractItemView.SelectItems)
            self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        except Exception:
            pass
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        try:
            header.sectionResized.connect(lambda *_args: self._schedule_adjust_row_heights())
        except Exception:
            pass
        self._table.setModel(self._limit_proxy)
        root.addWidget(self._table, 1)

        # Per-line link clicks inside multi-line cells
        try:
            self._link_delegate = MultiLineLinkDelegate(self._table)
            self._table.setItemDelegate(self._link_delegate)
            # Hover tracking for link-level background highlight
            try:
                self._table.setMouseTracking(True)
                self._table.viewport().setMouseTracking(True)
                self._table.viewport().installEventFilter(self._link_delegate)
            except Exception:
                pass
        except Exception:
            pass

        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        # Copy selection (Ctrl+C)
        self._copy_shortcut = QShortcut(QKeySequence.Copy, self._table)
        self._copy_shortcut.activated.connect(self._copy_selection_to_clipboard)

        self._spinner_overlay = SpinnerOverlay(self._table)

        # Theme styling
        self._apply_theme()
        self._bind_theme_refresh()

        # Wiring
        if self._row_limit is not None:
            self._row_limit.valueChanged.connect(self._apply_row_limit)
        if self._page is not None:
            self._page.valueChanged.connect(self._apply_page)

        if self._reload is not None:
            self._reload.clicked.connect(self.reload_data)
        if self._toggle_filters_button is not None:
            self._toggle_filters_button.clicked.connect(self._toggle_filters_collapsed)
        self._clear_filters.clicked.connect(self._clear_all_filters)
        if self._select_columns is not None:
            self._select_columns.clicked.connect(self._open_column_selector)
        if self._reset_columns is not None:
            self._reset_columns.clicked.connect(self._reset_column_visibility)
        if self._export_csv is not None:
            self._export_csv.clicked.connect(lambda: self._export("csv"))
        if self._export_xlsx is not None:
            self._export_xlsx.clicked.connect(lambda: self._export("xlsx"))

        try:
            self._adjust_row_heights_btn.clicked.connect(self._adjust_row_heights_to_max_lines)
        except Exception:
            pass

        self._table.clicked.connect(self._on_table_clicked)

        for sb in (
            self._subject_min,
            self._subject_max,
            self._fund_min,
            self._fund_max,
            self._member_min,
            self._member_max,
            self._rel_ds_min,
            self._rel_ds_max,
            self._rel_sample_min,
            self._rel_sample_max,
        ):
            sb.valueChanged.connect(self._schedule_apply_filters)

    def _bind_theme_refresh(self) -> None:
        """テーマ切替時に、このウィジェット固有のQSSを再適用する。

        NOTE: この一覧タブは self.setStyleSheet(...) でサブツリーに配色を固定しているため、
        QApplication全体のQSS/palette変更だけでは配色が更新されない。
        """
        try:
            tm = ThemeManager.instance()
        except Exception:
            return

        def _on_theme_changed(*_args) -> None:
            try:
                self._apply_theme()
            except Exception:
                pass

        try:
            tm.theme_changed.connect(_on_theme_changed)
        except Exception:
            return

        # Keep a reference so the slot isn't GC'd.
        try:
            self._rde_theme_refresh_slot = _on_theme_changed  # type: ignore[attr-defined]
        except Exception:
            pass

        def _disconnect(*_args) -> None:
            try:
                tm.theme_changed.disconnect(_on_theme_changed)
            except Exception:
                pass

        try:
            self.destroyed.connect(_disconnect)
        except Exception:
            pass

    def _init_range_spinboxes(self) -> None:
        try:
            from PySide6.QtWidgets import QAbstractSpinBox

            for name, sb in (
                ("subgroup_listing_subject_min", self._subject_min),
                ("subgroup_listing_subject_max", self._subject_max),
                ("subgroup_listing_fund_min", self._fund_min),
                ("subgroup_listing_fund_max", self._fund_max),
                ("subgroup_listing_member_min", self._member_min),
                ("subgroup_listing_member_max", self._member_max),
                ("subgroup_listing_rel_ds_min", self._rel_ds_min),
                ("subgroup_listing_rel_ds_max", self._rel_ds_max),
                ("subgroup_listing_rel_sample_min", self._rel_sample_min),
                ("subgroup_listing_rel_sample_max", self._rel_sample_max),
            ):
                sb.setObjectName(name)
                sb.setMinimum(0)
                sb.setMaximum(999999)
                sb.setSpecialValueText("未設定")
                sb.setButtonSymbols(QAbstractSpinBox.PlusMinus)
                sb.setValue(0)

                # Keep inputs from becoming too large, but avoid truncation.
                try:
                    sb.setMinimumWidth(90)
                    sb.setMaximumWidth(140)
                except Exception:
                    pass
        except Exception:
            pass

    def _rebuild_range_filters_panel(self) -> None:
        def bold_label(text: str) -> QLabel:
            lbl = QLabel(text, self)
            try:
                f = lbl.font()
                f.setBold(True)
                lbl.setFont(f)
            except Exception:
                pass
            return lbl

        if self._range_filters_layout is None:
            return

        self._ensure_range_widgets()

        # Clear layout
        persistent_widgets = {
            self._range_subject_widget,
            self._range_fund_widget,
            self._range_member_widget,
            self._range_rel_ds_widget,
            self._range_rel_sample_widget,
            self._clear_filters,
        }
        while self._range_filters_layout.count():
            item = self._range_filters_layout.takeAt(0)
            w = item.widget() if item is not None else None
            # Keep persistent widgets; dispose transient labels/wrappers to avoid overlap.
            if w is not None and w not in persistent_widgets:
                w.setParent(None)

        wrap = self._compute_should_wrap_range_filters()

        entries = [
            ("課題数", self._range_subject_widget),
            ("研究資金数", self._range_fund_widget),
            ("メンバー数", self._range_member_widget),
            ("関連データセット数", self._range_rel_ds_widget),
            ("関連試料数", self._range_rel_sample_widget),
        ]
        entries = [(lbl, w) for (lbl, w) in entries if w is not None]

        r = 0
        c = 0
        per_row = 3 if wrap else len(entries)
        for i, (label, widget) in enumerate(entries):
            if wrap and i > 0 and (i % per_row) == 0:
                r += 1
                c = 0
            self._range_filters_layout.addWidget(bold_label(label), r, c)
            c += 1
            self._range_filters_layout.addWidget(widget, r, c)
            c += 1

        # Clear button at the end
        if wrap:
            r += 1
            c = 0
        self._range_filters_layout.addWidget(self._clear_filters, r, c)

        try:
            if self._range_filters_container is not None:
                self._range_filters_container.updateGeometry()
        except Exception:
            pass

    def _ensure_range_widgets(self) -> None:
        def make_range_widget(min_sb: QSpinBox, max_sb: QSpinBox) -> QWidget:
            parent = self._range_filters_container if self._range_filters_container is not None else self
            w = QWidget(parent)
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lay.addWidget(min_sb)
            lay.addWidget(QLabel("～", w))
            lay.addWidget(max_sb)
            return w

        if self._range_subject_widget is None:
            self._range_subject_widget = make_range_widget(self._subject_min, self._subject_max)
        if self._range_fund_widget is None:
            self._range_fund_widget = make_range_widget(self._fund_min, self._fund_max)
        if self._range_member_widget is None:
            self._range_member_widget = make_range_widget(self._member_min, self._member_max)
        if self._range_rel_ds_widget is None:
            self._range_rel_ds_widget = make_range_widget(self._rel_ds_min, self._rel_ds_max)
        if self._range_rel_sample_widget is None:
            self._range_rel_sample_widget = make_range_widget(self._rel_sample_min, self._rel_sample_max)

    # ------------------------------------------------------------------
    # Data / filtering
    # ------------------------------------------------------------------
    def reload_data(self) -> None:
        if self._is_running_under_pytest():
            self._reload_data_sync()
        else:
            self._start_reload_async()

    def _is_running_under_pytest(self) -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST"))

    def _show_loading(self) -> None:
        try:
            if self._status is not None:
                self._status.setText("読み込み中...")
        except Exception:
            pass
        try:
            if self._spinner_overlay is not None:
                self._spinner_overlay.set_message("読み込み中…")
                self._spinner_overlay.start()
        except Exception:
            pass

    def _hide_loading(self) -> None:
        try:
            if self._spinner_overlay is not None:
                self._spinner_overlay.stop()
        except Exception:
            pass

    class _ReloadWorker(QObject):
        finished = Signal(object, object, object)

        def run(self) -> None:
            try:
                columns, rows = build_subgroup_list_rows_from_files()
                self.finished.emit(columns, rows, None)
            except Exception as exc:
                self.finished.emit(None, None, str(exc))

    def _update_table_data(self, columns, rows) -> None:
        self._columns = columns
        self._rows = rows

        if self._model is None:
            self._model = SubgroupListTableModel(columns, rows, self)
            self._filter_proxy.setSourceModel(self._model)
            self._limit_proxy.setSourceModel(self._filter_proxy)
        else:
            self._model.set_columns_and_rows(columns, rows)

        self._apply_column_visibility(
            self._load_column_visibility() or {c.key: c.default_visible for c in columns},
            persist=False,
        )

        self._rebuild_text_filters_panel()
        self._apply_row_limit()
        self._apply_filters_now()

        try:
            limit = int(self._row_limit.value()) if self._row_limit is not None else 0
            if limit <= 0 or limit <= 200:
                self._adjust_row_heights_to_max_lines()
            else:
                self._schedule_adjust_row_heights()
        except Exception:
            pass

    def _on_reload_thread_finished(self) -> None:
        self._reload_thread = None
        self._reload_worker = None

    def _on_reload_finished(self, columns, rows, error_message) -> None:
        self._hide_loading()
        if error_message:
            try:
                if self._status is not None:
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

        self._show_loading()

        # ウィジェット破棄と同時にスレッドが破棄されると
        # "QThread: Destroyed while thread '' is still running" の原因になる。
        # 親を付けず、明示的に参照を保持して寿命を管理する。
        thread = QThread()
        worker = SubgroupListingWidget._ReloadWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_reload_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_reload_thread_finished)

        # 参照保持（GC/ウィジェット破棄に伴う不意な破棄を避ける）
        self._reload_worker = worker
        _ACTIVE_SUBGROUP_LISTING_RELOAD_THREADS.add(thread)
        try:
            setattr(thread, "_reload_worker", worker)
        except Exception:
            pass
        try:
            thread.finished.connect(lambda: _ACTIVE_SUBGROUP_LISTING_RELOAD_THREADS.discard(thread))
        except Exception:
            pass

        self._reload_thread = thread
        thread.start()

    def _reload_data_sync(self) -> None:
        self._show_loading()
        try:
            columns, rows = build_subgroup_list_rows_from_files()
        except Exception:
            self._hide_loading()
            try:
                if self._status is not None:
                    self._status.setText("読み込み失敗")
            except Exception:
                pass
            return
        self._hide_loading()
        self._update_table_data(columns, rows)

    def _schedule_adjust_row_heights(self) -> None:
        try:
            self._row_height_timer.start()
        except Exception:
            try:
                self._adjust_row_heights_to_max_lines()
            except Exception:
                return

    def _row_max_height_px(self) -> int:
        try:
            from qt_compat.widgets import QApplication

            screen = QApplication.primaryScreen()
            if screen:
                h = int(screen.geometry().height())
                if h > 0:
                    return max(80, int(h * 0.50))
        except Exception:
            pass
        return 600

    def _adjust_row_heights_to_max_lines(self) -> None:
        if not hasattr(self, "_table") or self._table is None:
            return
        model = self._table.model()
        if model is None:
            return

        try:
            row_count = int(model.rowCount())
            col_count = int(model.columnCount())
        except Exception:
            return

        # Avoid heavy recalculation on extremely large views.
        if row_count > 2000:
            return

        fm = self._table.fontMetrics()
        line_h = max(1, int(fm.height()))
        max_h = int(self._row_max_height_px())
        padding = 8

        visible_cols = []
        for c in range(col_count):
            try:
                if self._table.isColumnHidden(c):
                    continue
            except Exception:
                pass
            visible_cols.append(c)

        for r in range(row_count):
            max_lines = 1
            for c in visible_cols:
                try:
                    idx = model.index(r, c)
                    txt = str(model.data(idx, Qt.DisplayRole) or "")
                    lines = max(1, len(txt.splitlines()))
                    if lines > max_lines:
                        max_lines = lines
                except Exception:
                    continue
            desired = max_lines * line_h + padding
            if desired > max_h:
                desired = max_h
            self._table.setRowHeight(r, int(desired))

    def _rebuild_text_filters_panel(self) -> None:
        if self._text_filters_layout is None:
            return

        # Clear layout
        while self._text_filters_layout.count():
            item = self._text_filters_layout.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)

        self._filter_edits_by_key = {}

        def bold_label(text: str) -> QLabel:
            lbl = QLabel(text, self)
            try:
                f = lbl.font()
                f.setBold(True)
                lbl.setFont(f)
            except Exception:
                pass
            return lbl

        # 5 columns grid like dataset listing
        max_cols = 5
        try:
            for c in range(max_cols):
                self._text_filters_layout.setColumnStretch(c, 1)
        except Exception:
            pass

        skip_keys = {
            "subject_count",
            "fund_count",
            "member_count",
            "related_datasets_count",
            "related_samples_count",
        }

        row = 0
        col = 0
        for cdef in self._columns:
            if cdef.key in skip_keys:
                continue

            pair = QWidget(self)
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(6)

            lbl = bold_label(f"{cdef.label}:")
            edit = QLineEdit(self)
            edit.setObjectName(f"subgroup_listing_filter_{cdef.key}")
            edit.setPlaceholderText("フィルタ")

            edit.textChanged.connect(self._schedule_apply_filters)

            pair_layout.addWidget(lbl)
            pair_layout.addWidget(edit, 1)

            self._filter_edits_by_key[cdef.key] = edit

            self._text_filters_layout.addWidget(pair, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _schedule_apply_filters(self) -> None:
        try:
            self._apply_timer.start(250)
        except Exception:
            self._apply_filters_now()

    def _apply_filters_now(self) -> None:
        # Column filters
        filters_by_col: Dict[int, str] = {}
        key_to_index = {c.key: i for i, c in enumerate(self._columns)}
        for key, edit in (self._filter_edits_by_key or {}).items():
            txt = (edit.text() or "").strip()
            if not txt:
                continue
            col_idx = key_to_index.get(key)
            if col_idx is None:
                continue
            filters_by_col[col_idx] = txt

        self._filter_proxy.set_column_filters(filters_by_col)

        def spin_to_optional(sb: QSpinBox) -> Optional[int]:
            try:
                v = int(sb.value())
            except Exception:
                return None
            return None if v <= 0 else v

        self._filter_proxy.set_subject_count_range(spin_to_optional(self._subject_min), spin_to_optional(self._subject_max))
        self._filter_proxy.set_fund_count_range(spin_to_optional(self._fund_min), spin_to_optional(self._fund_max))
        self._filter_proxy.set_member_count_range(spin_to_optional(self._member_min), spin_to_optional(self._member_max))
        self._filter_proxy.set_related_datasets_count_range(
            spin_to_optional(self._rel_ds_min), spin_to_optional(self._rel_ds_max)
        )
        self._filter_proxy.set_related_samples_count_range(
            spin_to_optional(self._rel_sample_min), spin_to_optional(self._rel_sample_max)
        )

        self._update_pagination_controls()

        self._update_filters_summary()

    def _clear_all_filters(self) -> None:
        for edit in (self._filter_edits_by_key or {}).values():
            try:
                edit.blockSignals(True)
                edit.setText("")
            finally:
                try:
                    edit.blockSignals(False)
                except Exception:
                    pass

        for sb in (
            self._subject_min,
            self._subject_max,
            self._fund_min,
            self._fund_max,
            self._member_min,
            self._member_max,
            self._rel_ds_min,
            self._rel_ds_max,
            self._rel_sample_min,
            self._rel_sample_max,
        ):
            try:
                sb.blockSignals(True)
                sb.setValue(0)
            finally:
                try:
                    sb.blockSignals(False)
                except Exception:
                    pass

        self._apply_filters_now()

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

        def fmt_range(min_v: Optional[int], max_v: Optional[int]) -> str:
            mn = "" if not min_v else str(min_v)
            mx = "" if not max_v else str(max_v)
            if mn and mx:
                return f"{mn}～{mx}"
            if mn and not mx:
                return f"{mn}～"
            if not mn and mx:
                return f"～{mx}"
            return ""

        rng = fmt_range(self._opt(self._subject_min), self._opt(self._subject_max))
        if rng:
            parts.append(f"課題数:{rng}")
        rng = fmt_range(self._opt(self._fund_min), self._opt(self._fund_max))
        if rng:
            parts.append(f"研究資金数:{rng}")
        rng = fmt_range(self._opt(self._member_min), self._opt(self._member_max))
        if rng:
            parts.append(f"メンバー数:{rng}")
        rng = fmt_range(self._opt(self._rel_ds_min), self._opt(self._rel_ds_max))
        if rng:
            parts.append(f"関連データセット数:{rng}")
        rng = fmt_range(self._opt(self._rel_sample_min), self._opt(self._rel_sample_max))
        if rng:
            parts.append(f"関連試料数:{rng}")

        for key, edit in (self._filter_edits_by_key or {}).items():
            txt = (edit.text() or "").strip()
            if not txt:
                continue
            label = next((c.label for c in self._columns if c.key == key), key)
            parts.append(f"{label}:{txt}")

        self._filters_summary_label.setText(" / ".join(parts))

    def _apply_row_limit(self) -> None:
        if self._row_limit is None:
            return
        self._limit_proxy.set_page_size(int(self._row_limit.value()))
        self._update_pagination_controls()

    def _apply_page(self) -> None:
        if self._page is None:
            return
        try:
            self._limit_proxy.set_page(int(self._page.value()))
        except Exception:
            return

    def _update_pagination_controls(self) -> None:
        if self._page is None or self._total_pages is None or self._row_limit is None:
            return

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
            else:
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

        # Status (total + filtered)
        try:
            total_all = len(self._rows)
            total_filtered = int(self._filter_proxy.rowCount())
            if self._status is not None:
                self._status.setText(f"総数:{total_all}件 / 抽出:{total_filtered}件")
        except Exception:
            pass

    def _open_column_selector(self) -> None:
        visible_by_key = self._get_current_visible_by_key()
        dlg = ColumnSelectorDialog(self, self._columns, visible_by_key)

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
        return get_dynamic_file_path("config/subgroup_listing_columns.json")

    def _load_column_visibility(self) -> Optional[Dict[str, bool]]:
        try:
            # テストは決定性を優先して、ユーザー設定（永続ファイル）に依存しない。
            if self._is_running_under_pytest():
                return None
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
            # テストは副作用（ファイル書き込み）を避ける。
            if self._is_running_under_pytest():
                return
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

    def _export_default_filename(self, fmt: str) -> str:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "csv" if fmt == "csv" else "xlsx"
        return f"subgroup_listing_{ts}.{suffix}"

    def _export(self, fmt: str) -> None:
        if fmt not in {"csv", "xlsx"}:
            return

        default_name = self._export_default_filename(fmt)
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
                row_values.append(
                    str(
                        model.data(idx, SubgroupListTableModel.RAW_TEXT_ROLE)
                        or model.data(idx, Qt.DisplayRole)
                        or ""
                    )
                )
            data_rows.append(row_values)

        return pd.DataFrame(data_rows, columns=col_labels)

    def _apply_theme(self) -> None:
        try:
            input_border_w = get_color(ThemeKey.INPUT_BORDER_WIDTH)
        except Exception:
            input_border_w = "1px"

        base_qss = (
            f"QLabel {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
            f"QLineEdit, QComboBox {{"
            f"  background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.INPUT_TEXT)};"
            f"  border: {input_border_w} solid {get_color(ThemeKey.INPUT_BORDER)};"
            f"}}"
            f"QLineEdit:focus, QComboBox:focus {{"
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

        try:
            filters_qss = (
                f"QWidget#subgroup_listing_filters_container {{"
                f"  background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};"
                f"  border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};"
                f"  border-radius: 4px;"
                f"  padding: 6px;"
                f"}}"
            )
            self.setStyleSheet(self.styleSheet() + filters_qss)
        except Exception:
            pass

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
        try:
            w = int(self.width())
        except Exception:
            w = 0
        return w > 0 and w < 980

    def _maybe_relayout_range_filters(self) -> None:
        wrap = self._compute_should_wrap_range_filters()
        if self._range_wrap_mode is None or self._range_wrap_mode != wrap:
            self._range_wrap_mode = wrap
            # Rebuild only the range panel; spinbox values are preserved.
            self._rebuild_range_filters_panel()

    @staticmethod
    def _opt(sb: QSpinBox) -> Optional[int]:
        try:
            v = int(sb.value())
        except Exception:
            return None
        return None if v <= 0 else v

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------
    def _on_table_clicked(self, index: QModelIndex) -> None:
        try:
            if not index.isValid():
                return
            col = self._columns[index.column()] if 0 <= index.column() < len(self._columns) else None
            if col is None:
                return
            # related_* are handled by delegate for per-item click
            if col.key != "subgroup_name":
                return
            urls = index.data(Qt.UserRole)
            # QDesktopServices can fail silently on some Windows envs; webbrowser is more reliable.
            if isinstance(urls, str):
                if urls:
                    webbrowser.open(urls)
                return
        except Exception:
            return

    def _copy_selection_to_clipboard(self) -> None:
        try:
            selection = self._table.selectionModel().selectedIndexes()
            if not selection:
                return
            selection.sort(key=lambda i: (i.row(), i.column()))

            # build TSV
            rows: List[List[str]] = []
            current_row = None
            current: List[str] = []
            for idx in selection:
                if current_row is None:
                    current_row = idx.row()
                if idx.row() != current_row:
                    rows.append(current)
                    current = []
                    current_row = idx.row()
                current.append(str(self._filter_proxy.data(idx, Qt.DisplayRole) or ""))
            if current:
                rows.append(current)

            tsv = "\n".join("\t".join(r) for r in rows)
            from qt_compat.widgets import QApplication

            QApplication.clipboard().setText(tsv)
        except Exception:
            return


class MultiLineLinkDelegate(QStyledItemDelegate):
    """Open the clicked line's URL for multi-line related columns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover: tuple[int, int, int] | None = None  # (row, col, line_idx)

    def _calc_hover_line(self, view: QTableView, index: QModelIndex, pos) -> int | None:
        try:
            rect = view.visualRect(index)
            if not rect.isValid() or not rect.contains(pos):
                return None
            fm = view.fontMetrics()
            line_h = max(1, int(fm.height()))
            y_in = int(pos.y()) - int(rect.top())
            return int(y_in // line_h)
        except Exception:
            return None

    def _set_hover(self, view: QTableView, hover_tuple: tuple[int, int, int] | None) -> None:
        old = self._hover
        if old == hover_tuple:
            return
        self._hover = hover_tuple

        def _update_cell(cell: tuple[int, int, int] | None) -> None:
            if cell is None:
                return
            r, c, _l = cell
            try:
                view.viewport().update(view.visualRect(view.model().index(r, c)))
            except Exception:
                return

        _update_cell(old)
        _update_cell(hover_tuple)

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            from PySide6.QtCore import QEvent

            view = self.parent()
            if not isinstance(view, QTableView):
                return False

            if event.type() == QEvent.Leave:
                self._set_hover(view, None)
                return False

            if event.type() != QEvent.MouseMove:
                return False

            try:
                pos = event.position().toPoint()
            except Exception:
                pos = event.pos()

            index = view.indexAt(pos)
            if not index.isValid():
                self._set_hover(view, None)
                return False

            urls = index.data(Qt.UserRole)
            if not (isinstance(urls, list) and urls):
                self._set_hover(view, None)
                return False

            line = self._calc_hover_line(view, index, pos)
            if line is None:
                self._set_hover(view, None)
                return False
            if line < 0 or line >= len(urls):
                self._set_hover(view, None)
                return False

            u = urls[line]
            if not (isinstance(u, str) and u.strip()):
                self._set_hover(view, None)
                return False

            self._set_hover(view, (int(index.row()), int(index.column()), int(line)))
            return False
        except Exception:
            return False

    def paint(self, painter, option, index):  # noqa: N802
        super().paint(painter, option, index)

        try:
            if self._hover is None:
                return
            if option.state & QStyle.State_Selected:
                return
            r, c, line_idx = self._hover
            if index.row() != r or index.column() != c:
                return

            urls = index.data(Qt.UserRole)
            if not (isinstance(urls, list) and urls):
                return
            if line_idx < 0 or line_idx >= len(urls):
                return
            if not (isinstance(urls[line_idx], str) and urls[line_idx].strip()):
                return

            fm = option.fontMetrics
            line_h = max(1, int(fm.height()))
            rect = option.rect
            top = int(rect.top()) + int(line_h * int(line_idx))
            line_rect = QRect(int(rect.left()), top, int(rect.width()), int(line_h))

            col = get_qcolor(ThemeKey.TEXT_LINK_HOVER_BACKGROUND)
            try:
                col.setAlpha(96)
            except Exception:
                pass
            painter.save()
            painter.fillRect(line_rect, col)
            painter.restore()
        except Exception:
            return

    def editorEvent(self, event, model, option, index):  # noqa: N802
        try:
            from PySide6.QtCore import QEvent

            if event.type() != QEvent.MouseButtonRelease:
                return super().editorEvent(event, model, option, index)
        except Exception:
            return super().editorEvent(event, model, option, index)

        try:
            urls = index.data(Qt.UserRole)
            if not isinstance(urls, list) or not urls:
                return super().editorEvent(event, model, option, index)

            text = str(index.data(Qt.DisplayRole) or "")
            lines = text.splitlines() if text else []

            fm = option.fontMetrics
            line_h = max(1, int(fm.height()))

            try:
                y = int(event.position().y())
                x = int(event.position().x())
            except Exception:
                y = int(event.pos().y())
                x = int(event.pos().x())

            if not option.rect.contains(x, y):
                return super().editorEvent(event, model, option, index)

            if not lines:
                u0 = urls[0]
                if isinstance(u0, str) and u0:
                    webbrowser.open(u0)
                return True

            y_in = y - int(option.rect.top())
            line_idx = int(y_in // line_h)
            if line_idx < 0:
                return True
            if line_idx >= len(urls):
                return True

            u = urls[line_idx]
            if isinstance(u, str) and u:
                webbrowser.open(u)
            return True
        except Exception:
            return super().editorEvent(event, model, option, index)


def create_subgroup_listing_widget(parent=None, title: str = "一覧") -> QWidget:
    _ = title
    qparent = parent if isinstance(parent, QWidget) else None
    return SubgroupListingWidget(qparent)
