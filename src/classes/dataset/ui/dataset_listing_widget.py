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
from PySide6.QtWidgets import QMenu, QTableView

from classes.dataset.ui.spinner_overlay import SpinnerOverlay
from classes.dataset.ui.portal_status_spinner_delegate import PortalStatusSpinnerDelegate

from classes.dataset.util.dataset_list_table_records import (
    DatasetListColumn,
    build_dataset_list_rows_from_files,
)

from classes.dataset.util.dataset_listing_export_filename import (
    build_dataset_listing_export_default_filename,
)

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color
from config.common import get_dynamic_file_path


_ACTIVE_DATASET_LISTING_RELOAD_THREADS: set[QThread] = set()
_ACTIVE_DATASET_LISTING_STATS_THREADS: set[QThread] = set()
_ACTIVE_DATASET_LISTING_PORTAL_THREADS: set[QThread] = set()


_ACTIVE_DATASET_LISTING_PORTAL_CSV_THREADS: set[QThread] = set()


def _build_user_profile_url(user_id: str) -> str:
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    return f"https://rde-user.nims.go.jp/rde-user-profile/users/{uid}"


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
            if col.key == "portal_open":
                dataset_id = str(row.get("dataset_id") or "").strip()
                return "カタログ" if dataset_id else ""
            if col.key == "portal_status":
                status = "" if value is None else str(value)
                checked_at = str(row.get("portal_checked_at") or "").strip()
                if status and checked_at:
                    return f"{status}（{checked_at}）"
                return status
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
            if col.key == "open_at_date":
                return row.get("_open_at_date_obj")
            if col.key == "modified_date":
                return row.get("_modified_date_obj")
            if col.key == "created_date":
                return row.get("_created_date_obj")
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
            if col.key == "portal_open":
                dataset_id = row.get("dataset_id")
                dataset_id = str(dataset_id).strip() if dataset_id is not None else ""
                return dataset_id
            if col.key == "manager_name":
                manager_id = str(row.get("_manager_id") or "").strip()
                return _build_user_profile_url(manager_id)
            if col.key == "applicant_name":
                applicant_id = str(row.get("_applicant_id") or "").strip()
                return _build_user_profile_url(applicant_id)
            if col.key == "data_owner_names":
                owner_ids = row.get("_data_owner_ids")
                owner_labels = row.get("_data_owner_labels")
                if not isinstance(owner_ids, list) or not owner_ids:
                    return ""
                if not isinstance(owner_labels, list):
                    owner_labels = []
                items: List[Dict[str, str]] = []
                for i, oid in enumerate(owner_ids):
                    oid_str = str(oid or "").strip()
                    if not oid_str:
                        continue
                    label = ""
                    try:
                        if i < len(owner_labels):
                            label = str(owner_labels[i] or "").strip()
                    except Exception:
                        label = ""
                    if not label or label == "Unknown":
                        label = f"Unknown ({i + 1})"
                    items.append({"label": label, "url": _build_user_profile_url(oid_str)})
                if not items:
                    return ""
                if len(items) == 1:
                    return items[0].get("url") or ""
                return items
            return row.get(col.key)

        if role == Qt.ForegroundRole:
            if col.key in {"dataset_name", "instrument_names", "tool_open", "portal_open"}:
                return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key == "subgroup_name":
                subgroup_id = row.get("subgroup_id")
                subgroup_id = str(subgroup_id).strip() if subgroup_id is not None else ""
                if subgroup_id:
                    return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key == "manager_name":
                manager_id = str(row.get("_manager_id") or "").strip()
                if manager_id:
                    return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key == "applicant_name":
                applicant_id = str(row.get("_applicant_id") or "").strip()
                if applicant_id:
                    return QBrush(get_color(ThemeKey.TEXT_LINK))
            if col.key == "data_owner_names":
                owner_ids = row.get("_data_owner_ids")
                if isinstance(owner_ids, list) and any(str(x or "").strip() for x in owner_ids):
                    return QBrush(get_color(ThemeKey.TEXT_LINK))

        if role == Qt.FontRole:
            if col.key in {"dataset_name", "instrument_names", "tool_open", "portal_open"}:
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
            if col.key in {"manager_name", "applicant_name", "data_owner_names"}:
                url = self.data(index, Qt.UserRole)
                if isinstance(url, str) and url:
                    f = QFont()
                    f.setUnderline(True)
                    return f
                if isinstance(url, list) and url:
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
        self._exact_match_column_indices: set[int] = set()
        self._embargo_from: Optional[datetime.date] = None
        self._embargo_to: Optional[datetime.date] = None
        self._open_at_from: Optional[datetime.date] = None
        self._open_at_to: Optional[datetime.date] = None
        self._modified_from: Optional[datetime.date] = None
        self._modified_to: Optional[datetime.date] = None
        self._created_from: Optional[datetime.date] = None
        self._created_to: Optional[datetime.date] = None
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

    def set_exact_match_columns(self, column_indices: set[int]) -> None:
        self._exact_match_column_indices = {int(i) for i in (column_indices or set())}
        self.invalidateFilter()

    def _match_any_term_for_column(self, *, col_idx: int, hay: str, patterns: List[re.Pattern], raw_filter: str) -> bool:
        """Return True if hay matches filter for the given column.

        For most columns: substring match via compiled regex patterns.
        For exact-match columns (e.g., portal_status): full-string match (still supports '*').
        """

        text = str(hay or "")
        if int(col_idx) not in (self._exact_match_column_indices or set()):
            return any(p.search(text) for p in (patterns or []))

        # exact-match semantics: compare against the whole cell text.
        # NOTE: portal_status はセル側に「ステータス（日時）」、フィルタ側に「ステータス（件数）」
        # のような装飾が入るため、括弧以降は無視してステータス部分のみで一致判定する。
        cell = text.strip()
        cell_key = self._strip_parenthetical_suffix(cell)
        for term in self._split_filter_terms(raw_filter or ""):
            t = (term or "").strip()
            if not t:
                continue
            t_key = self._strip_parenthetical_suffix(t)
            if "*" in t:
                pat = self._compile_wildcard_pattern(t_key)
                if pat is not None and pat.fullmatch(cell_key):
                    return True
            else:
                if cell_key.lower() == t_key.lower():
                    return True
        return False

    @staticmethod
    def _strip_parenthetical_suffix(text: str) -> str:
        """括弧で始まるサフィックス（例: （日時）, （件数））を除去してステータス部分だけ返す。"""
        raw = (text or "").strip()
        if not raw:
            return ""
        for sep in ("（", "("):
            pos = raw.find(sep)
            if pos > 0:
                return raw[:pos].strip()
        return raw

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

    def set_open_at_range(self, date_from: Optional[datetime.date], date_to: Optional[datetime.date]) -> None:
        self._open_at_from = date_from
        self._open_at_to = date_to
        self.invalidateFilter()

    def set_modified_range(self, date_from: Optional[datetime.date], date_to: Optional[datetime.date]) -> None:
        self._modified_from = date_from
        self._modified_to = date_to
        self.invalidateFilter()

    def set_created_range(self, date_from: Optional[datetime.date], date_to: Optional[datetime.date]) -> None:
        self._created_from = date_from
        self._created_to = date_to
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

    def get_column_filters(self) -> Dict[int, str]:
        return dict(self._column_filters or {})

    def accepts_row_ignoring_text_filter_columns(self, source_row: int, ignore_columns: set[int]) -> bool:
        """filterAcceptsRow相当だが、指定列のテキストフィルタだけ無視して判定する。"""
        model = self.sourceModel()
        if model is None:
            return True

        source_parent = QModelIndex()

        # embargo range filter
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

        # created range filter
        if self._created_from or self._created_to:
            col = self._find_column_by_label("開設日")
            if col >= 0:
                idx = model.index(source_row, col, source_parent)
                d = model.data(idx, Qt.UserRole)
                if not isinstance(d, datetime.date):
                    return False
                if self._created_from and d < self._created_from:
                    return False
                if self._created_to and d > self._created_to:
                    return False
                
        # modified range filter
        if self._modified_from or self._modified_to:
            col = self._find_column_by_label("更新日")
            if col >= 0:
                idx = model.index(source_row, col, source_parent)
                d = model.data(idx, Qt.UserRole)
                if not isinstance(d, datetime.date):
                    return False
                if self._modified_from and d < self._modified_from:
                    return False
                if self._modified_to and d > self._modified_to:
                    return False

        # openAt range filter
        if self._open_at_from or self._open_at_to:
            col = self._find_column_by_label("公開日")
            if col >= 0:
                idx = model.index(source_row, col, source_parent)
                d = model.data(idx, Qt.UserRole)
                if not isinstance(d, datetime.date):
                    return False
                if self._open_at_from and d < self._open_at_from:
                    return False
                if self._open_at_to and d > self._open_at_to:
                    return False
                                
        if self._column_filter_patterns:
            for col_idx, patterns in self._column_filter_patterns.items():
                if col_idx in (ignore_columns or set()):
                    continue
                if col_idx < 0 or col_idx >= model.columnCount():
                    continue
                idx = model.index(source_row, col_idx, source_parent)
                hay = str(model.data(idx, Qt.DisplayRole) or "")
                raw_filter = (self._column_filters or {}).get(int(col_idx), "")
                if not self._match_any_term_for_column(col_idx=int(col_idx), hay=hay, patterns=patterns, raw_filter=raw_filter):
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

        # openAt range filter
        if self._open_at_from or self._open_at_to:
            col = self._find_column_by_label("公開日")
            if col >= 0:
                idx = model.index(source_row, col, source_parent)
                d = model.data(idx, Qt.UserRole)
                if not isinstance(d, datetime.date):
                    return False
                if self._open_at_from and d < self._open_at_from:
                    return False
                if self._open_at_to and d > self._open_at_to:
                    return False

        # modified range filter
        if self._modified_from or self._modified_to:
            col = self._find_column_by_label("更新日")
            if col >= 0:
                idx = model.index(source_row, col, source_parent)
                d = model.data(idx, Qt.UserRole)
                if not isinstance(d, datetime.date):
                    return False
                if self._modified_from and d < self._modified_from:
                    return False
                if self._modified_to and d > self._modified_to:
                    return False

        # created range filter
        if self._created_from or self._created_to:
            col = self._find_column_by_label("開設日")
            if col >= 0:
                idx = model.index(source_row, col, source_parent)
                d = model.data(idx, Qt.UserRole)
                if not isinstance(d, datetime.date):
                    return False
                if self._created_from and d < self._created_from:
                    return False
                if self._created_to and d > self._created_to:
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
                raw_filter = (self._column_filters or {}).get(int(col_idx), "")
                if not self._match_any_term_for_column(col_idx=int(col_idx), hay=hay, patterns=patterns, raw_filter=raw_filter):
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

        if label in {"エンバーゴ期間終了日", "開設日", "更新日", "公開日"}:
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

        # NOTE: portal_status のみ選択式(QComboBox)にするため、QWidget で保持する。
        self._filter_edits_by_key: Dict[str, QWidget] = {}
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
        self._portal_open_callback = None

        # Debounce filter application to keep the table responsive while typing/clicking.
        self._filter_proxy = DatasetFilterProxyModel(self)
        self._reload_thread: Optional[QThread] = None
        self._reload_worker: Optional[QObject] = None

        self._stats_thread: Optional[QThread] = None
        self._stats_worker: Optional[QObject] = None

        self._portal_thread: Optional[QThread] = None
        self._portal_worker: Optional[QObject] = None
        self._portal_fill_environment: Optional[str] = None
        self._portal_global_fill_cursor: int = 0

        self._portal_csv_thread: Optional[QThread] = None
        self._portal_csv_worker: Optional[QObject] = None

        self._portal_force_refresh_btn: Optional[QPushButton] = None

        # Force refresh state (bulk portal status refresh)
        self._portal_force_refresh_inflight: bool = False
        self._portal_force_refresh_pending_parts: set[str] = set()

        # Force refresh progress (spinner overlay)
        self._portal_force_refresh_progress_total: Optional[int] = None
        self._portal_force_refresh_progress_done: int = 0

        # UI counters refresh (debounced)
        self._portal_ui_counts_refresh_timer = QTimer(self)
        self._portal_ui_counts_refresh_timer.setSingleShot(True)
        self._portal_ui_counts_refresh_timer.setInterval(150)
        self._portal_ui_counts_refresh_timer.timeout.connect(self._refresh_portal_ui_counts)

        # Auto fetch portal statuses while visible and there are unchecked rows.
        self._portal_auto_fetch_timer = QTimer(self)
        self._portal_auto_fetch_timer.setInterval(2000)
        self._portal_auto_fetch_timer.timeout.connect(self._auto_fetch_portal_statuses_if_needed)
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self._portal_auto_fetch_timer.start()

        # Apply cached portal statuses across the whole model (batched, UI-thread).
        self._portal_cache_apply_cursor: int = 0
        self._portal_cache_apply_timer = QTimer(self)
        self._portal_cache_apply_timer.setSingleShot(True)
        self._portal_cache_apply_timer.setInterval(0)
        self._portal_cache_apply_timer.timeout.connect(self._apply_cached_portal_statuses_batch)

        # Per-row portal status refresh (click on portal cell)
        self._portal_status_loading_model_rows: set[int] = set()
        self._portal_status_refresh_inflight_dataset_ids: set[str] = set()
        self._portal_status_refresh_threads: set[QThread] = set()
        self._portal_status_delegate: Optional[PortalStatusSpinnerDelegate] = None
        self._portal_status_retry_counts_by_dataset_id: Dict[str, int] = {}
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

        self._portal_force_refresh_btn = QPushButton("データカタログステータス強制更新", self)
        try:
            # Provide a small menu: full refresh vs non-public-only refresh.
            menu = QMenu(self._portal_force_refresh_btn)
            act_all = menu.addAction("全件強制更新")
            act_all.triggered.connect(self._confirm_and_force_refresh_portal_statuses)
            act_unconfirmed = menu.addAction("未確認のみ更新")
            act_unconfirmed.triggered.connect(self._confirm_and_force_refresh_portal_statuses_nonpublic_only)
            self._portal_force_refresh_btn.setMenu(menu)
        except Exception:
            pass
        buttons_row.addWidget(self._portal_force_refresh_btn)

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

        # OpenAt/Modified/Created range widgets
        self._open_at_from = QDateEdit(self)
        self._open_at_from.setObjectName("dataset_listing_open_at_from")
        self._open_at_from.setDisplayFormat("yyyy-MM-dd")
        self._open_at_from.setCalendarPopup(True)
        self._open_at_from.setSpecialValueText("未設定")
        self._open_at_from.setDate(QDate(2000, 1, 1))
        self._open_at_from.setMinimumDate(QDate(2000, 1, 1))
        self._open_at_from.setMaximumDate(QDate(2999, 12, 31))
        self._open_at_to = QDateEdit(self)
        self._open_at_to.setObjectName("dataset_listing_open_at_to")
        self._open_at_to.setDisplayFormat("yyyy-MM-dd")
        self._open_at_to.setCalendarPopup(True)
        self._open_at_to.setSpecialValueText("未設定")
        self._open_at_to.setDate(QDate(2000, 1, 1))
        self._open_at_to.setMinimumDate(QDate(2000, 1, 1))
        self._open_at_to.setMaximumDate(QDate(2999, 12, 31))

        self._modified_from = QDateEdit(self)
        self._modified_from.setObjectName("dataset_listing_modified_from")
        self._modified_from.setDisplayFormat("yyyy-MM-dd")
        self._modified_from.setCalendarPopup(True)
        self._modified_from.setSpecialValueText("未設定")
        self._modified_from.setDate(QDate(2000, 1, 1))
        self._modified_from.setMinimumDate(QDate(2000, 1, 1))
        self._modified_from.setMaximumDate(QDate(2999, 12, 31))
        self._modified_to = QDateEdit(self)
        self._modified_to.setObjectName("dataset_listing_modified_to")
        self._modified_to.setDisplayFormat("yyyy-MM-dd")
        self._modified_to.setCalendarPopup(True)
        self._modified_to.setSpecialValueText("未設定")
        self._modified_to.setDate(QDate(2000, 1, 1))
        self._modified_to.setMinimumDate(QDate(2000, 1, 1))
        self._modified_to.setMaximumDate(QDate(2999, 12, 31))

        self._created_from = QDateEdit(self)
        self._created_from.setObjectName("dataset_listing_created_from")
        self._created_from.setDisplayFormat("yyyy-MM-dd")
        self._created_from.setCalendarPopup(True)
        self._created_from.setSpecialValueText("未設定")
        self._created_from.setDate(QDate(2000, 1, 1))
        self._created_from.setMinimumDate(QDate(2000, 1, 1))
        self._created_from.setMaximumDate(QDate(2999, 12, 31))
        self._created_to = QDateEdit(self)
        self._created_to.setObjectName("dataset_listing_created_to")
        self._created_to.setDisplayFormat("yyyy-MM-dd")
        self._created_to.setCalendarPopup(True)
        self._created_to.setSpecialValueText("未設定")
        self._created_to.setDate(QDate(2000, 1, 1))
        self._created_to.setMinimumDate(QDate(2000, 1, 1))
        self._created_to.setMaximumDate(QDate(2999, 12, 31))

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

            for de in (
                self._embargo_from,
                self._embargo_to,
                self._open_at_from,
                self._open_at_to,
                self._modified_from,
                self._modified_to,
                self._created_from,
                self._created_to,
            ):
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

        self._range_open_at_widget = QWidget(self)
        open_at_layout = QHBoxLayout(self._range_open_at_widget)
        open_at_layout.setContentsMargins(0, 0, 0, 0)
        open_at_layout.addWidget(self._open_at_from)
        open_at_layout.addWidget(QLabel("～"))
        open_at_layout.addWidget(self._open_at_to)

        self._range_modified_widget = QWidget(self)
        modified_layout = QHBoxLayout(self._range_modified_widget)
        modified_layout.setContentsMargins(0, 0, 0, 0)
        modified_layout.addWidget(self._modified_from)
        modified_layout.addWidget(QLabel("～"))
        modified_layout.addWidget(self._modified_to)

        self._range_created_widget = QWidget(self)
        created_layout = QHBoxLayout(self._range_created_widget)
        created_layout.setContentsMargins(0, 0, 0, 0)
        created_layout.addWidget(self._created_from)
        created_layout.addWidget(QLabel("～"))
        created_layout.addWidget(self._created_to)

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

        # NOTE: 初回読み込みは「空白に見える」時間が出やすいので、少し大きめのスピナーを使用する。
        self._spinner_overlay = SpinnerOverlay(
            self._table,
            message="読み込み中…",
            spinner_point_size=34,
            message_point_size=14,
        )

        # Theme styling
        self._apply_theme()
        self._bind_theme_refresh()

        # Wiring
        self._row_limit.valueChanged.connect(self._apply_row_limit)
        self._page.valueChanged.connect(self._apply_page)
        self._embargo_from.dateChanged.connect(self._schedule_apply_filters)
        self._embargo_to.dateChanged.connect(self._schedule_apply_filters)
        self._open_at_from.dateChanged.connect(self._schedule_apply_filters)
        self._open_at_to.dateChanged.connect(self._schedule_apply_filters)
        self._modified_from.dateChanged.connect(self._schedule_apply_filters)
        self._modified_to.dateChanged.connect(self._schedule_apply_filters)
        self._created_from.dateChanged.connect(self._schedule_apply_filters)
        self._created_to.dateChanged.connect(self._schedule_apply_filters)
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

        # NOTE: portal force refresh button uses an attached menu when available.

        if self._toggle_filters_button is not None:
            self._toggle_filters_button.clicked.connect(self._toggle_filters_collapsed)

        self._table.clicked.connect(self._on_table_clicked)
        try:
            # Some Qt environments are more reliable with `pressed` than `clicked`.
            # Handle portal_status refresh here only (avoid double URL opens etc.).
            self._table.pressed.connect(self._on_table_pressed)
        except Exception:
            pass
        try:
            self._table.doubleClicked.connect(self._on_table_double_clicked)
        except Exception:
            pass

        # Click fallback: QTableView.clicked/pressed can be flaky in some environments.
        # Use a viewport eventFilter to reliably detect portal_status clicks.
        try:
            self._table.viewport().installEventFilter(self)
        except Exception:
            pass

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

    def _bind_theme_refresh(self) -> None:
        """テーマ切替時に、このウィジェット固有のQSSを再適用する。"""
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

    def resizeEvent(self, event) -> None:  # noqa: N802
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self._range_relayout_timer.start()
        except Exception:
            self._maybe_relayout_range_filters()

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            if self._table is not None and obj is self._table.viewport():
                from PySide6.QtCore import QEvent

                if event is not None and event.type() == QEvent.Type.MouseButtonRelease:
                    try:
                        btn = event.button()
                    except Exception:
                        btn = None
                    if btn == Qt.LeftButton:
                        try:
                            idx = self._table.indexAt(event.pos())
                        except Exception:
                            idx = None
                        if idx is not None and idx.isValid():
                            self._on_portal_status_cell_activated(idx)
        except Exception:
            pass

        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

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
            ("公開日", self._range_open_at_widget),
            ("更新日", self._range_modified_widget),
            ("開設日", self._range_created_widget),
        ]
        entries = [(lbl, w) for (lbl, w) in entries if w is not None]

        r = 0
        c = 0
        # 要件: 範囲フィルタ群は常に2行で表示する。
        per_row = (max(1, (len(entries) + 1) // 2)) if wrap else len(entries)
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

    def _cancel_portal_fill(self) -> None:
        worker = self._portal_worker
        thread = self._portal_thread

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

        self._portal_thread = None
        self._portal_worker = None

    def _cancel_portal_csv_fill(self) -> None:
        thread = self._portal_csv_thread
        if thread is not None and thread.isRunning():
            try:
                thread.quit()
            except Exception:
                pass
        self._portal_csv_thread = None
        self._portal_csv_worker = None

    def _portal_checked_at_column_index(self) -> Optional[int]:
        try:
            for i, c in enumerate(self._columns or []):
                if getattr(c, "key", None) == "portal_checked_at":
                    return int(i)
        except Exception:
            return None
        return None

    @staticmethod
    def _format_portal_checked_at(epoch: object) -> str:
        try:
            v = float(epoch)
        except Exception:
            return ""
        if v <= 0:
            return ""
        try:
            jst = datetime.timezone(datetime.timedelta(hours=9))
            dt = datetime.datetime.fromtimestamp(v, tz=jst)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    @staticmethod
    def _public_output_json_mtime_epoch() -> Optional[float]:
        try:
            from classes.data_portal.util.public_output_paths import get_public_data_portal_root_dir

            path = get_public_data_portal_root_dir() / "output.json"
            return float(path.stat().st_mtime)
        except Exception:
            return None

    def _apply_public_output_json_classification_to_all_rows(self) -> None:
        if self._model is None:
            return

        try:
            from classes.dataset.util.portal_status_resolver import PRIVATE_MANAGED_LABEL
            from classes.dataset.util.portal_status_resolver import PUBLIC_MANAGED_LABEL
            from classes.dataset.util.portal_status_resolver import PUBLIC_PUBLISHED_LABEL
        except Exception:
            PUBLIC_MANAGED_LABEL = "公開"
            PRIVATE_MANAGED_LABEL = "非公開"
            PUBLIC_PUBLISHED_LABEL = "公開2"

        try:
            from classes.utils.data_portal_public import get_public_published_dataset_ids

            public_ids = get_public_published_dataset_ids()
        except Exception:
            public_ids = set()

        # Tests should be deterministic; avoid real workspace output.json affecting behavior.
        if self._is_running_under_pytest():
            public_ids = set()

        if not public_ids:
            return

        checked_at_txt = ""
        try:
            checked_at_txt = self._format_portal_checked_at(self._public_output_json_mtime_epoch())
        except Exception:
            checked_at_txt = ""

        rows = self._model.get_rows()
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid or dsid not in public_ids:
                continue

            current = str(row.get("portal_status") or "").strip()
            if current in {PUBLIC_MANAGED_LABEL, PRIVATE_MANAGED_LABEL}:
                continue

            updates: Dict[str, Any] = {"portal_status": PUBLIC_PUBLISHED_LABEL}
            if checked_at_txt:
                updates["portal_checked_at"] = checked_at_txt
            self._model.update_row_fields(i, updates)

        try:
            self._filter_proxy.invalidateFilter()
        except Exception:
            pass
        try:
            self._schedule_refresh_portal_ui_counts()
        except Exception:
            pass

    def _finalize_portal_force_refresh_part(self, part: str) -> None:
        if not self._portal_force_refresh_inflight:
            return

        try:
            self._portal_force_refresh_pending_parts.discard(str(part))
        except Exception:
            return

        if self._portal_force_refresh_pending_parts:
            return

        # Stop overlay spinner/progress
        try:
            self._portal_force_refresh_progress_total = None
            self._portal_force_refresh_progress_done = 0
            if hasattr(self, "_spinner_overlay") and self._spinner_overlay is not None:
                self._spinner_overlay.stop()
        except Exception:
            pass

        self._portal_force_refresh_inflight = False
        # Final pass to ensure public(output.json) classification survives bulk refresh.
        try:
            self._apply_public_output_json_classification_to_all_rows()
        except Exception:
            pass

    def _collect_visible_portal_tasks(self) -> List[tuple[int, str]]:
        """Collect (model_row_index, dataset_id) for currently visible page."""
        if self._model is None:
            return []

        try:
            proxy_rows = int(self._limit_proxy.rowCount())
        except Exception:
            proxy_rows = 0
        if proxy_rows <= 0:
            return []

        tasks: List[tuple[int, str]] = []
        seen: set[str] = set()

        for pr in range(proxy_rows):
            try:
                proxy_index = self._limit_proxy.index(pr, 0)
                if not proxy_index.isValid():
                    continue
                filter_index = self._limit_proxy.mapToSource(proxy_index)
                model_index = self._filter_proxy.mapToSource(filter_index)
                model_row = int(model_index.row())
            except Exception:
                continue

            try:
                row = self._model.get_rows()[model_row]
            except Exception:
                continue

            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid or dsid in seen:
                continue
            seen.add(dsid)
            tasks.append((model_row, dsid))

        return tasks

    class _PortalFillWorker(QObject):
        row_ready = Signal(int, object)
        finished = Signal()

        def __init__(self, tasks: List[tuple[int, str]], environment: str):
            super().__init__()
            self._tasks = tasks
            self._environment = environment
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            from classes.data_portal.core.auth_manager import get_auth_manager
            from classes.data_portal.core.portal_client import PortalClient
            from classes.data_portal.core.portal_entry_status import (
                get_portal_entry_status_cache,
                parse_portal_entry_search_html,
            )

            env = str(self._environment or "production").strip() or "production"

            auth_manager = get_auth_manager()
            try:
                credentials = auth_manager.get_credentials(env)
            except Exception:
                credentials = None

            if credentials is None:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            try:
                client = PortalClient(env)
                client.set_credentials(credentials)
            except Exception:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            try:
                login_ok, _msg = client.login()
            except Exception:
                login_ok = False
            if not login_ok:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            cache = get_portal_entry_status_cache()

            for row_index, dataset_id in self._tasks:
                if self._cancelled:
                    break

                dsid = str(dataset_id or "").strip()
                if not dsid:
                    continue

                # Cache re-check
                try:
                    cached = cache.get_label(dsid, env)
                except Exception:
                    cached = None
                if cached:
                    try:
                        self.row_ready.emit(int(row_index), cached)
                    except Exception:
                        pass
                    continue

                data = {
                    "mode": "theme",
                    "keyword": dsid,
                    "search_inst": "",
                    "search_license_level": "",
                    "search_status": "",
                    "page": "1",
                }

                try:
                    ok, resp = client.post("main.php", data=data)
                except Exception:
                    continue
                if not ok or not hasattr(resp, "text"):
                    continue

                html = resp.text or ""
                if "ログイン" in html or "Login" in html or "loginArea" in html:
                    try:
                        relogin_ok, _msg = client.login()
                    except Exception:
                        relogin_ok = False
                    if not relogin_ok:
                        continue
                    try:
                        ok, resp = client.post("main.php", data=data)
                    except Exception:
                        continue
                    if not ok or not hasattr(resp, "text"):
                        continue
                    html = resp.text or ""

                parsed = parse_portal_entry_search_html(html, dsid, environment=env)
                label = parsed.listing_label()
                try:
                    from classes.dataset.util.portal_status_resolver import normalize_logged_in_portal_label

                    label = normalize_logged_in_portal_label(label)
                except Exception:
                    pass
                try:
                    cache.set_label(dsid, label, env)
                except Exception:
                    pass

                if self._cancelled:
                    break
                try:
                    self.row_ready.emit(int(row_index), label)
                except Exception:
                    continue

            try:
                self.finished.emit()
            except Exception:
                pass

    class _PortalStatusRefreshWorker(QObject):
        """Refresh portal status for one dataset_id using both logged-in and public checks."""

        result_ready = Signal(int, object, object, object, object)
        finished = Signal()

        def __init__(self, model_row: int, dataset_id: str, *, env_candidates: List[str], worker_env: str):
            super().__init__()
            self._model_row = int(model_row)
            self._dataset_id = str(dataset_id or "").strip()
            self._env_candidates = [str(e or "").strip() for e in (env_candidates or []) if str(e or "").strip()]
            self._worker_env = str(worker_env or "production").strip() or "production"

        def run(self) -> None:
            dsid = self._dataset_id
            if not dsid:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            logged_in_label = None
            logged_in_checked = False
            error_text: str = ""

            # Logged-in check (if credentials available)
            try:
                from classes.data_portal.core.auth_manager import get_auth_manager
                from classes.data_portal.core.portal_client import PortalClient
                from classes.data_portal.core.portal_entry_status import (
                    get_portal_entry_status_cache,
                    parse_portal_entry_search_html,
                )

                auth_manager = get_auth_manager()
                try:
                    credentials = auth_manager.get_credentials(self._worker_env)
                except Exception:
                    credentials = None

                if credentials is not None:
                    logged_in_checked = True
                    client = PortalClient(self._worker_env)
                    client.set_credentials(credentials)
                    try:
                        login_ok, _msg = client.login()
                    except Exception as exc:
                        login_ok = False
                        error_text = f"データポータルログインに失敗しました ({self._worker_env}): {exc}"

                    if login_ok:
                        data = {
                            "mode": "theme",
                            "keyword": dsid,
                            "search_inst": "",
                            "search_license_level": "",
                            "search_status": "",
                            "page": "1",
                        }

                        try:
                            ok, resp = client.post("main.php", data=data)
                        except Exception as exc:
                            ok = False
                            resp = None
                            if not error_text:
                                error_text = f"データポータル検索に失敗しました ({self._worker_env}): {exc}"

                        if ok and hasattr(resp, "text"):
                            html = resp.text or ""
                            if "ログイン" in html or "Login" in html or "loginArea" in html:
                                try:
                                    relogin_ok, _msg = client.login()
                                except Exception as exc:
                                    relogin_ok = False
                                    if not error_text:
                                        error_text = f"データポータル再ログインに失敗しました ({self._worker_env}): {exc}"

                                if relogin_ok:
                                    try:
                                        ok, resp = client.post("main.php", data=data)
                                    except Exception as exc:
                                        ok = False
                                        resp = None
                                        if not error_text:
                                            error_text = f"データポータル再検索に失敗しました ({self._worker_env}): {exc}"

                                    if ok and hasattr(resp, "text"):
                                        html = resp.text or ""

                            parsed = parse_portal_entry_search_html(html, dsid, environment=self._worker_env)
                            raw_label = parsed.listing_label()
                            try:
                                from classes.dataset.util.portal_status_resolver import normalize_logged_in_portal_label

                                logged_in_label = normalize_logged_in_portal_label(raw_label)
                            except Exception:
                                logged_in_label = str(raw_label).strip() if raw_label is not None else ""

                            # Save to cache for future listing fill.
                            try:
                                cache = get_portal_entry_status_cache()
                                cache.set_label(dsid, logged_in_label, self._worker_env)
                            except Exception:
                                pass
                        elif logged_in_checked and not error_text:
                            error_text = f"データポータル検索のレスポンスが不正です ({self._worker_env})"
            except Exception:
                logged_in_label = None
                if not error_text:
                    error_text = "データポータル確認処理でエラーが発生しました"

            # Public (no-login) check
            public_published = False
            try:
                from classes.utils.data_portal_public import get_public_published_dataset_ids

                public_published = dsid in get_public_published_dataset_ids()
            except Exception:
                public_published = False

            # If not found in output.json, best-effort live probe (production -> test)
            if not public_published:
                try:
                    from classes.utils.data_portal_public import search_public_arim_data, fetch_public_arim_data_details

                    for env in ("production", "test"):
                        links = search_public_arim_data(
                            keyword=dsid,
                            environment=env,
                            timeout=15,
                            max_pages=1,
                            start_page=1,
                            end_page=1,
                        )
                        if not links:
                            continue

                        details = fetch_public_arim_data_details(
                            links,
                            environment=env,
                            timeout=15,
                            max_items=3,
                            max_workers=1,
                            cache_enabled=True,
                        )
                        for detail in details:
                            try:
                                fields = detail.fields if hasattr(detail, "fields") else {}
                                if isinstance(fields, dict) and str(fields.get("dataset_id") or "").strip() == dsid:
                                    public_published = True
                                    break
                            except Exception:
                                continue
                        if public_published:
                            break
                except Exception:
                    public_published = False

            # If neither path produced a determination and we had credentials, surface a hint.
            if logged_in_checked and not (str(logged_in_label or "").strip()) and not public_published and not error_text:
                error_text = "データポータル確認に失敗しました（公開/非公開の判定ができませんでした）"

            try:
                self.result_ready.emit(self._model_row, logged_in_label, public_published, logged_in_checked, error_text)
            except Exception:
                pass

            try:
                self.finished.emit()
            except Exception:
                pass

    def _portal_status_column_index(self) -> Optional[int]:
        try:
            for i, c in enumerate(self._columns or []):
                if getattr(c, "key", None) == "portal_status":
                    return int(i)
        except Exception:
            return None
        return None

    def _install_portal_status_delegate(self) -> None:
        col_idx = self._portal_status_column_index()
        if col_idx is None or self._table is None:
            return

        # Reuse one delegate instance.
        if self._portal_status_delegate is None:
            self._portal_status_delegate = PortalStatusSpinnerDelegate(
                self,
                is_loading_callback=self._is_portal_status_loading_for_proxy_index,
                view=self._table,
                activate_callback=self._on_portal_status_cell_activated,
            )
        try:
            self._table.setItemDelegateForColumn(int(col_idx), self._portal_status_delegate)
        except Exception:
            return

    def _on_portal_status_cell_activated(self, proxy_index: QModelIndex) -> None:
        """Portal status cell click handler invoked from the delegate.

        Using a delegate callback avoids relying solely on QTableView.clicked/pressed
        which can be flaky in some environments.
        """

        try:
            if proxy_index is None or (not proxy_index.isValid()) or self._model is None:
                return

            idx2 = self._map_view_index_to_model_index(proxy_index)
            if idx2 is None or (not idx2.isValid()):
                return

            col = self._columns[idx2.column()] if 0 <= idx2.column() < len(self._columns) else None
            if col is None or col.key != "portal_status":
                return

            rows = self._model.get_rows()
            row = rows[idx2.row()] if 0 <= idx2.row() < len(rows) else {}
            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid:
                return

            try:
                from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
            except Exception:
                UNCHECKED_LABEL = "未確認"

            current = str(row.get("portal_status") or "").strip()
            if self._is_running_under_pytest() or (not current) or (current == UNCHECKED_LABEL):
                self._start_portal_status_refresh_for_model_row(int(idx2.row()), dsid)
        except Exception:
            return

    def _is_portal_status_loading_for_proxy_index(self, proxy_index: QModelIndex) -> bool:
        try:
            if not proxy_index.isValid() or self._model is None:
                return False
            idx1 = self._limit_proxy.mapToSource(proxy_index)
            idx2 = self._filter_proxy.mapToSource(idx1)
            if not idx2.isValid():
                return False
            model_row = int(idx2.row())
            return model_row in self._portal_status_loading_model_rows
        except Exception:
            return False

    def _collect_env_candidates_for_portal(self) -> List[str]:
        env_candidates: List[str] = ["production", "test"]
        try:
            from classes.data_portal.conf.config import get_data_portal_config

            cfg_envs = get_data_portal_config().get_available_environments()
            if isinstance(cfg_envs, list) and cfg_envs:
                ordered: List[str] = []
                for known in ("production", "test"):
                    if known in cfg_envs and known not in ordered:
                        ordered.append(known)
                for e in cfg_envs:
                    if e not in ordered:
                        ordered.append(str(e))
                if ordered:
                    env_candidates = ordered
        except Exception:
            pass
        return env_candidates

    def _pick_worker_env_with_credentials(self, env_candidates: List[str]) -> str:
        worker_env = env_candidates[0] if env_candidates else "production"
        try:
            from classes.data_portal.core.auth_manager import get_auth_manager

            auth_manager = get_auth_manager()
            for candidate in env_candidates:
                try:
                    cred = auth_manager.get_credentials(str(candidate))
                except Exception:
                    cred = None
                if cred is not None:
                    worker_env = str(candidate)
                    break
        except Exception:
            pass
        return str(worker_env or "production").strip() or "production"

    def _start_portal_status_refresh_for_model_row(self, model_row: int, dataset_id: str) -> None:
        if self._model is None:
            return

        dsid = str(dataset_id or "").strip()
        if not dsid:
            return

        # Avoid duplicate in-flight refresh.
        if dsid in self._portal_status_refresh_inflight_dataset_ids:
            return

        self._portal_status_refresh_inflight_dataset_ids.add(dsid)
        self._portal_status_loading_model_rows.add(int(model_row))
        try:
            if self._table is not None:
                self._table.viewport().update()
        except Exception:
            pass

        # Under pytest, avoid network/threading; simulate a short wait to exercise spinner.
        if self._is_running_under_pytest():
            def _finish_pytest() -> None:
                try:
                    self._on_portal_status_refresh_result(int(model_row), None, False, True, None)
                finally:
                    self._on_portal_status_refresh_finished(int(model_row), dsid)

            try:
                QTimer.singleShot(150, _finish_pytest)
            except Exception:
                _finish_pytest()
            return

        env_candidates = self._collect_env_candidates_for_portal()
        worker_env = self._pick_worker_env_with_credentials(env_candidates)

        thread = QThread()
        worker = DatasetListingWidget._PortalStatusRefreshWorker(
            int(model_row),
            dsid,
            env_candidates=env_candidates,
            worker_env=worker_env,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.result_ready.connect(self._on_portal_status_refresh_result)

        # Cleanup
        worker.finished.connect(lambda: self._on_portal_status_refresh_finished(int(model_row), dsid))
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._portal_status_refresh_threads.add(thread)
        _ACTIVE_DATASET_LISTING_PORTAL_THREADS.add(thread)
        try:
            setattr(thread, "_portal_status_refresh_worker", worker)
        except Exception:
            pass
        try:
            thread.finished.connect(lambda: self._portal_status_refresh_threads.discard(thread))
            thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_PORTAL_THREADS.discard(thread))
        except Exception:
            pass

        thread.start()

    def _on_portal_status_refresh_result(
        self,
        model_row: int,
        logged_in_label: object,
        public_published: object,
        logged_in_checked: object,
        error_message: object,
    ) -> None:
        if self._model is None:
            return

        try:
            row = self._model.get_rows()[int(model_row)]
        except Exception:
            row = None

        existing = None
        if isinstance(row, dict):
            existing = row.get("portal_status")
        existing_text = str(existing).strip() if existing is not None else ""

        logged_text = str(logged_in_label).strip() if logged_in_label is not None else ""
        public_ok = bool(public_published)
        checked = bool(logged_in_checked)
        err_text = str(error_message).strip() if error_message is not None else ""

        # Click refresh should follow the same precedence rules as listing.
        dsid_for_resolve = ""
        if isinstance(row, dict):
            dsid_for_resolve = str(row.get("dataset_id") or "").strip()

        new_label = None
        try:
            from classes.dataset.util.portal_status_resolver import resolve_portal_status_label

            resolved = resolve_portal_status_label(
                existing=existing_text,
                cached=logged_text if logged_text else None,
                dataset_id=dsid_for_resolve,
                public_published_dataset_ids={dsid_for_resolve} if (public_ok and dsid_for_resolve) else set(),
            )
            new_label = resolved if resolved is not None else existing_text
        except Exception:
            # Fallback (keep legacy behavior)
            if logged_text:
                new_label = logged_text
            elif public_ok:
                new_label = "公開2"
            elif checked:
                new_label = "管理外"
            else:
                new_label = existing_text

        checked_at_text = ""
        try:
            if logged_text or checked:
                # Cache set_label() stores checked_at; best-effort reflect it.
                from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

                env = str(self._portal_fill_environment or "production").strip() or "production"
                cache = get_portal_entry_status_cache()
                epoch = cache.get_checked_at_any_age(str(row.get("dataset_id") or "").strip(), env) if hasattr(cache, "get_checked_at_any_age") and isinstance(row, dict) else None
                if epoch is None:
                    epoch = datetime.datetime.now(datetime.timezone.utc).timestamp()
                checked_at_text = self._format_portal_checked_at(epoch)
            elif public_ok:
                checked_at_text = self._format_portal_checked_at(self._public_output_json_mtime_epoch())
        except Exception:
            checked_at_text = ""

        try:
            updates: Dict[str, Any] = {"portal_status": new_label}
            if checked_at_text:
                updates["portal_checked_at"] = checked_at_text
            self._model.update_row_fields(int(model_row), updates)
        except Exception:
            return

        # Retry while "未確認" until a determination is made.
        # This is primarily for transient login/network errors.
        try:
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
        except Exception:
            UNCHECKED_LABEL = "未確認"

        dsid = str(row.get("dataset_id") or "").strip() if isinstance(row, dict) else ""
        current_label = str(new_label or "").strip()
        is_unchecked = (not current_label) or (current_label == UNCHECKED_LABEL)
        if dsid and not is_unchecked:
            try:
                self._portal_status_retry_counts_by_dataset_id.pop(dsid, None)
            except Exception:
                pass

        if dsid and is_unchecked and checked:
            max_retries = 5
            count = int(self._portal_status_retry_counts_by_dataset_id.get(dsid, 0))
            self._portal_status_retry_counts_by_dataset_id[dsid] = count + 1

            # Show the error (once) for user-triggered refresh.
            if err_text and not self._is_running_under_pytest() and count == 0:
                try:
                    QMessageBox.warning(self, "ポータル確認エラー", f"ポータル確認に失敗しました。再試行します。\n\n{err_text}")
                except Exception:
                    pass

            if count + 1 < max_retries:
                try:
                    QTimer.singleShot(1200, lambda: self._start_portal_status_refresh_for_model_row(int(model_row), dsid))
                except Exception:
                    pass
            else:
                # Final failure: make sure the user sees it.
                if err_text and not self._is_running_under_pytest():
                    try:
                        QMessageBox.critical(self, "ポータル確認失敗", f"ポータル確認が繰り返し失敗しました。\n\n{err_text}")
                    except Exception:
                        pass

        try:
            self._schedule_refresh_portal_ui_counts()
        except Exception:
            pass

    def _on_portal_status_refresh_finished(self, model_row: int, dataset_id: str) -> None:
        try:
            self._portal_status_loading_model_rows.discard(int(model_row))
            self._portal_status_refresh_inflight_dataset_ids.discard(str(dataset_id or "").strip())
        except Exception:
            pass
        try:
            if self._table is not None:
                self._table.viewport().update()
        except Exception:
            pass

    def _on_portal_row_ready(self, row_index: int, label: object) -> None:
        if self._model is None:
            return

        # Force refresh progress update (best-effort)
        try:
            if self._portal_force_refresh_inflight and self._portal_force_refresh_progress_total:
                self._portal_force_refresh_progress_done = int(self._portal_force_refresh_progress_done or 0) + 1
                if hasattr(self, "_spinner_overlay") and self._spinner_overlay is not None:
                    self._spinner_overlay.set_progress(
                        int(self._portal_force_refresh_progress_done),
                        int(self._portal_force_refresh_progress_total),
                        prefix="処理済み",
                    )
        except Exception:
            pass
        try:
            # Resolve final listing label with public(output.json) precedence.
            try:
                row = self._model.get_rows()[int(row_index)]
            except Exception:
                row = None

            dsid = str(row.get("dataset_id") or "").strip() if isinstance(row, dict) else ""
            existing_text = str(row.get("portal_status") or "").strip() if isinstance(row, dict) else ""

            resolved = None
            public_ids: set[str] = set()
            try:
                from classes.utils.data_portal_public import get_public_published_dataset_ids

                public_ids = get_public_published_dataset_ids()
            except Exception:
                public_ids = set()

            try:
                from classes.dataset.util.portal_status_resolver import resolve_portal_status_label

                resolved = resolve_portal_status_label(
                    existing=existing_text,
                    cached=label,
                    dataset_id=dsid,
                    public_published_dataset_ids=public_ids,
                )
            except Exception:
                resolved = str(label).strip() if label is not None else ""

            updates: Dict[str, Any] = {"portal_status": resolved}

            # Fill checked_at from cache if available.
            try:
                # If classified as 公開2, use output.json mtime as checked_at.
                try:
                    from classes.dataset.util.portal_status_resolver import PUBLIC_PUBLISHED_LABEL

                    is_public2 = str(resolved).strip() == str(PUBLIC_PUBLISHED_LABEL)
                except Exception:
                    is_public2 = str(resolved).strip() == "公開2"

                if is_public2:
                    epoch_public = self._public_output_json_mtime_epoch()
                    txt_public = self._format_portal_checked_at(epoch_public)
                    if txt_public:
                        updates["portal_checked_at"] = txt_public
                elif dsid:
                    # Logged-in cache checked_at
                    try:
                        from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

                        env = str(self._portal_fill_environment or "production").strip() or "production"
                        cache = get_portal_entry_status_cache()
                        epoch = cache.get_checked_at_any_age(dsid, env) if hasattr(cache, "get_checked_at_any_age") else None
                        txt = self._format_portal_checked_at(epoch)
                        if txt:
                            updates["portal_checked_at"] = txt
                    except Exception:
                        pass
            except Exception:
                pass

            if dsid:
                try:
                    # Keep existing portal_checked_at if already set and this update didn't set it.
                    if isinstance(row, dict) and not updates.get("portal_checked_at"):
                        prev = str(row.get("portal_checked_at") or "").strip()
                        if prev:
                            updates["portal_checked_at"] = prev
                except Exception:
                    pass

            self._model.update_row_fields(int(row_index), updates)
        except Exception:
            return

        try:
            self._schedule_refresh_portal_ui_counts()
        except Exception:
            pass

    def _on_portal_fill_finished(self) -> None:
        self._portal_thread = None
        self._portal_worker = None
        try:
            self._finalize_portal_force_refresh_part("html")
        except Exception:
            pass

    def _start_portal_fill_async(self, *, mode: str = "visible") -> None:
        if self._is_running_under_pytest():
            return
        if self._model is None:
            return
        if self._portal_thread is not None and self._portal_thread.isRunning():
            return

        # Prefer production, but allow test env cache/credentials.
        env_candidates: List[str] = ["production", "test"]
        try:
            from classes.data_portal.conf.config import get_data_portal_config

            cfg_envs = get_data_portal_config().get_available_environments()
            if isinstance(cfg_envs, list) and cfg_envs:
                ordered: List[str] = []
                for known in ("production", "test"):
                    if known in cfg_envs and known not in ordered:
                        ordered.append(known)
                for e in cfg_envs:
                    if e not in ordered:
                        ordered.append(str(e))
                if ordered:
                    env_candidates = ordered
        except Exception:
            pass

        worker_env = env_candidates[0] if env_candidates else "production"
        try:
            from classes.data_portal.core.auth_manager import get_auth_manager

            auth_manager = get_auth_manager()
            for candidate in env_candidates:
                try:
                    cred = auth_manager.get_credentials(str(candidate))
                except Exception:
                    cred = None
                if cred is not None:
                    worker_env = str(candidate)
                    break
        except Exception:
            pass

        public_published_dataset_ids: set[str] = set()
        try:
            from classes.utils.data_portal_public import get_public_published_dataset_ids

            public_published_dataset_ids = get_public_published_dataset_ids()
        except Exception:
            public_published_dataset_ids = set()

        try:
            from classes.dataset.util.portal_status_resolver import resolve_portal_status_label
            from classes.dataset.util.portal_status_resolver import PUBLIC_PUBLISHED_LABEL as _PUBLIC_FALLBACK_LABEL
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL as _UNCHECKED_LABEL
            from classes.dataset.util.portal_status_resolver import pick_best_cached_label
            from classes.dataset.util.portal_status_resolver import NONPUBLIC_OR_UNREGISTERED_LABEL as _NONPUBLIC_LABEL
            from classes.dataset.util.portal_status_resolver import PUBLIC_MANAGED_LABEL as _PUBLIC_MANAGED_LABEL
            from classes.dataset.util.portal_status_resolver import PRIVATE_MANAGED_LABEL as _PRIVATE_MANAGED_LABEL
        except Exception:
            resolve_portal_status_label = None
            _PUBLIC_FALLBACK_LABEL = "公開2"
            _UNCHECKED_LABEL = "未確認"
            pick_best_cached_label = None
            _NONPUBLIC_LABEL = "管理外"
            _PUBLIC_MANAGED_LABEL = "公開"
            _PRIVATE_MANAGED_LABEL = "非公開"

        try:
            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

            cache = get_portal_entry_status_cache()
        except Exception:
            cache = None

        tasks: List[tuple[int, str]] = []
        resolved_updates = 0

        # Choose target rows.
        mode_text = str(mode or "visible").strip().lower()
        candidates: List[tuple[int, str]] = []
        if mode_text == "global":
            # Walk all rows, but only enqueue a limited number each cycle.
            max_candidates = 120
            rows = self._model.get_rows()
            if rows:
                start = int(self._portal_global_fill_cursor or 0)
                if start < 0:
                    start = 0
                n = len(rows)
                visited = 0
                idx = start
                while visited < n and len(candidates) < max_candidates:
                    row = rows[idx] if 0 <= idx < n else None
                    if isinstance(row, dict):
                        dsid = str(row.get("dataset_id") or "").strip()
                        if dsid:
                            st = str(row.get("portal_status") or "").strip()
                            # Background mode only cares about unchecked/blank.
                            if st in {"", _UNCHECKED_LABEL}:
                                candidates.append((int(idx), dsid))
                    idx = (idx + 1) % n
                    visited += 1
                self._portal_global_fill_cursor = idx
        else:
            candidates = self._collect_visible_portal_tasks()

        for model_row, dsid in candidates:
            try:
                row = self._model.get_rows()[model_row]
            except Exception:
                continue

            existing = row.get("portal_status")
            existing_text = str(existing).strip() if existing is not None else ""
            # Skip only when managed/public status is already confirmed.
            if existing_text in {_PUBLIC_MANAGED_LABEL, _PRIVATE_MANAGED_LABEL, _PUBLIC_FALLBACK_LABEL}:
                continue

            # In background/global mode, we only process unchecked entries.
            if mode_text == "global" and existing_text not in {"", _UNCHECKED_LABEL}:
                continue

            cached_label = None
            if cache is not None:
                if pick_best_cached_label is not None:
                    try:
                        cached_label = pick_best_cached_label(
                            dsid,
                            get_label=lambda d, e: cache.get_label_any_age(d, e) if hasattr(cache, "get_label_any_age") else cache.get_label(d, e),
                            environments=env_candidates,
                        )
                    except Exception:
                        cached_label = None
                else:
                    try:
                        cached_label = cache.get_label_any_age(dsid, worker_env) if hasattr(cache, "get_label_any_age") else cache.get_label(dsid, worker_env)
                    except Exception:
                        cached_label = None

            resolved = None
            if resolve_portal_status_label is not None:
                try:
                    resolved = resolve_portal_status_label(
                        existing=row.get("portal_status"),
                        cached=cached_label,
                        dataset_id=dsid,
                        public_published_dataset_ids=public_published_dataset_ids,
                    )
                except Exception:
                    resolved = None

            if resolved is None and cached_label:
                resolved = cached_label

            if resolved:
                try:
                    updates: Dict[str, Any] = {"portal_status": resolved}
                    if str(resolved) == _PUBLIC_FALLBACK_LABEL:
                        updates["portal_checked_at"] = self._format_portal_checked_at(self._public_output_json_mtime_epoch())
                    else:
                        try:
                            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

                            cache2 = get_portal_entry_status_cache()
                            epoch2 = cache2.get_checked_at_any_age(dsid, worker_env) if hasattr(cache2, "get_checked_at_any_age") else None
                            txt2 = self._format_portal_checked_at(epoch2)
                            if txt2:
                                updates["portal_checked_at"] = txt2
                        except Exception:
                            pass

                    self._model.update_row_fields(int(model_row), updates)
                    resolved_updates += 1
                except Exception:
                    pass
                # Keep using resolved/cached values; avoid automatic per-row portal access.
                continue

            # Limit tasks per cycle to keep UI responsive.
            if len(tasks) < 80:
                tasks.append((model_row, dsid))

        if resolved_updates:
            try:
                self._schedule_refresh_portal_ui_counts()
            except Exception:
                pass

        if not tasks:
            return

        self._portal_fill_environment = str(worker_env or "production").strip() or "production"

        thread = QThread()
        worker = DatasetListingWidget._PortalFillWorker(tasks, self._portal_fill_environment)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.row_ready.connect(self._on_portal_row_ready)
        worker.finished.connect(self._on_portal_fill_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._portal_worker = worker
        self._portal_thread = thread

        _ACTIVE_DATASET_LISTING_PORTAL_THREADS.add(thread)
        try:
            setattr(thread, "_portal_worker", worker)
        except Exception:
            pass
        try:
            thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_PORTAL_THREADS.discard(thread))
        except Exception:
            pass

        thread.start()

    class _PortalCsvFillWorker(QObject):
        mapping_ready = Signal(object, object)  # (environment, mapping)
        finished = Signal()

        def __init__(self, *, environment: str):
            super().__init__()
            self._environment = str(environment or "production").strip() or "production"

        def run(self) -> None:
            from classes.data_portal.core.auth_manager import get_auth_manager
            from classes.data_portal.core.portal_client import PortalClient

            env = self._environment
            auth_manager = get_auth_manager()
            try:
                credentials = auth_manager.get_credentials(env)
            except Exception:
                credentials = None

            if credentials is None:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            try:
                client = PortalClient(env)
                client.set_credentials(credentials)
            except Exception:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            try:
                ok, _msg = client.login()
            except Exception:
                ok = False
            if not ok:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            try:
                ok, resp = client.download_theme_csv()
            except Exception:
                ok = False
                resp = None
            if not ok or resp is None:
                try:
                    self.finished.emit()
                except Exception:
                    pass
                return

            payload = getattr(resp, "content", b"")
            try:
                from classes.data_portal.core.portal_csv_status import parse_portal_theme_csv_to_label_map

                mapping = parse_portal_theme_csv_to_label_map(payload)
            except Exception:
                mapping = {}

            try:
                self.mapping_ready.emit(env, mapping)
            except Exception:
                pass

            try:
                self.finished.emit()
            except Exception:
                pass

    def _start_portal_csv_fill_async(self) -> None:
        if self._is_running_under_pytest():
            return
        if self._model is None:
            return
        if self._portal_csv_thread is not None and self._portal_csv_thread.isRunning():
            return

        env_candidates = self._collect_env_candidates_for_portal()
        worker_env = self._pick_worker_env_with_credentials(env_candidates)

        # If no credentials found for any env, skip.
        try:
            from classes.data_portal.core.auth_manager import get_auth_manager

            auth_manager = get_auth_manager()
            cred = auth_manager.get_credentials(worker_env)
            if cred is None:
                return
        except Exception:
            return

        thread = QThread()
        worker = DatasetListingWidget._PortalCsvFillWorker(environment=worker_env)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.mapping_ready.connect(self._on_portal_csv_mapping_ready)
        worker.finished.connect(self._on_portal_csv_fill_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._portal_csv_worker = worker
        self._portal_csv_thread = thread

        _ACTIVE_DATASET_LISTING_PORTAL_CSV_THREADS.add(thread)
        try:
            setattr(thread, "_portal_csv_worker", worker)
        except Exception:
            pass
        try:
            thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_PORTAL_CSV_THREADS.discard(thread))
        except Exception:
            pass

        thread.start()

    def _on_portal_csv_mapping_ready(self, environment: object, mapping: object) -> None:
        if self._model is None:
            return

        env = str(environment or "production").strip() or "production"
        mp = mapping if isinstance(mapping, dict) else {}
        if not mp:
            return

        # Persist to portal status cache (once).
        try:
            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

            cache = get_portal_entry_status_cache()
            if hasattr(cache, "set_labels_bulk"):
                cache.set_labels_bulk(mp, env)
            else:
                for dsid, label in mp.items():
                    cache.set_label(dsid, str(label), env)
        except Exception:
            pass

        # Update current rows (do not force repaint of everything; update only changed rows).
        try:
            from classes.dataset.util.portal_status_resolver import PUBLIC_PUBLISHED_LABEL as _PUBLIC_FALLBACK_LABEL
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL as _UNCHECKED_LABEL
            from classes.dataset.util.portal_status_resolver import is_managed_public_label
            from classes.dataset.util.portal_status_resolver import is_managed_private_label
        except Exception:
            _PUBLIC_FALLBACK_LABEL = "公開2"
            _UNCHECKED_LABEL = "未確認"
            is_managed_public_label = lambda _x: False
            is_managed_private_label = lambda _x: False

        checked_at_txt = self._format_portal_checked_at(datetime.datetime.now(datetime.timezone.utc).timestamp())

        rows = self._model.get_rows()
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid:
                continue
            new_label = mp.get(dsid)
            if not new_label:
                continue
            existing = row.get("portal_status")
            existing_text = str(existing).strip() if existing is not None else ""

            # Always accept managed determination (公開/非公開).
            if is_managed_public_label(new_label) or is_managed_private_label(new_label):
                if existing_text != str(new_label):
                    self._model.update_row_fields(i, {"portal_status": str(new_label), "portal_checked_at": checked_at_txt})
                continue

            # For non-public labels, avoid overwriting already confirmed values.
            if existing_text and existing_text not in {_UNCHECKED_LABEL, _PUBLIC_FALLBACK_LABEL}:
                continue

            if existing_text != str(new_label):
                self._model.update_row_fields(i, {"portal_status": str(new_label), "portal_checked_at": checked_at_txt})

        try:
            self._schedule_refresh_portal_ui_counts()
        except Exception:
            pass

    def _on_portal_csv_fill_finished(self) -> None:
        self._portal_csv_thread = None
        self._portal_csv_worker = None
        try:
            self._finalize_portal_force_refresh_part("csv")
        except Exception:
            pass

    def _confirm_and_force_refresh_portal_statuses(self) -> None:
        if self._model is None:
            return
        if self._is_running_under_pytest():
            return

        reply = QMessageBox.question(
            self,
            "確認",
            "データカタログ（データポータル）ステータスを全件強制更新します。\n\n"
            "- キャッシュをクリアして再取得します\n"
            "- 件数が多い場合、完了まで時間がかかります\n\n"
            "実行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Mark force refresh in-flight.
        self._portal_force_refresh_inflight = True
        self._portal_force_refresh_pending_parts = set()

        # Stop background workers first.
        try:
            self._cancel_portal_fill()
        except Exception:
            pass
        try:
            self._cancel_portal_csv_fill()
        except Exception:
            pass

        # Clear cache (best-effort).
        try:
            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

            cache = get_portal_entry_status_cache()
            if hasattr(cache, "clear"):
                cache.clear(None)
        except Exception:
            pass

        # Reset current table values to unchecked.
        try:
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
        except Exception:
            UNCHECKED_LABEL = "未確認"

        rows = self._model.get_rows()
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            self._model.update_row_fields(i, {"portal_status": UNCHECKED_LABEL, "portal_checked_at": ""})

        # Baseline: apply public output.json classification immediately (no network, cheap).
        try:
            self._apply_public_output_json_classification_to_all_rows()
        except Exception:
            pass

        # Kick bulk CSV fill first (fast path).
        try:
            self._start_portal_csv_fill_async()
        except Exception:
            pass

        try:
            if self._portal_csv_thread is not None and self._portal_csv_thread.isRunning():
                self._portal_force_refresh_pending_parts.add("csv")
        except Exception:
            pass

        # Then run portal fill for all rows (logged-in HTML check).
        try:
            env_candidates = self._collect_env_candidates_for_portal()
            worker_env = self._pick_worker_env_with_credentials(env_candidates)
            self._portal_fill_environment = str(worker_env or "production").strip() or "production"

            tasks: List[tuple[int, str]] = []
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                dsid = str(row.get("dataset_id") or "").strip()
                if not dsid:
                    continue
                tasks.append((idx, dsid))

            if not tasks:
                self._portal_force_refresh_inflight = False
                self._portal_force_refresh_pending_parts = set()
                return

            # Start overlay spinner with progress (planned total / processed count)
            try:
                self._portal_force_refresh_progress_total = int(len(tasks))
                self._portal_force_refresh_progress_done = 0
                if hasattr(self, "_spinner_overlay") and self._spinner_overlay is not None:
                    self._spinner_overlay.show_message("データポータル確認中…")
                    self._spinner_overlay.set_progress(0, int(self._portal_force_refresh_progress_total), prefix="処理済み")
                    self._spinner_overlay.start()
            except Exception:
                pass

            thread = QThread()
            worker = DatasetListingWidget._PortalFillWorker(tasks, self._portal_fill_environment)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.row_ready.connect(self._on_portal_row_ready)
            worker.finished.connect(self._on_portal_fill_finished)
            worker.finished.connect(worker.deleteLater)
            worker.finished.connect(thread.quit)
            thread.finished.connect(thread.deleteLater)

            self._portal_worker = worker
            self._portal_thread = thread

            _ACTIVE_DATASET_LISTING_PORTAL_THREADS.add(thread)
            try:
                setattr(thread, "_portal_worker", worker)
            except Exception:
                pass
            try:
                thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_PORTAL_THREADS.discard(thread))
            except Exception:
                pass

            try:
                self._portal_force_refresh_pending_parts.add("html")
            except Exception:
                pass

            thread.start()
        except Exception:
            pass

        # If nothing started, finalize immediately.
        if not self._portal_force_refresh_pending_parts:
            self._portal_force_refresh_inflight = False
            try:
                self._portal_force_refresh_progress_total = None
                self._portal_force_refresh_progress_done = 0
                if hasattr(self, "_spinner_overlay") and self._spinner_overlay is not None:
                    self._spinner_overlay.stop()
            except Exception:
                pass

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

        # Ensure listing-specific fields exist (for new/old caches and tests).
        try:
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
        except Exception:
            UNCHECKED_LABEL = "未確認"

        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("portal_status") or "").strip() == "":
                row["portal_status"] = UNCHECKED_LABEL
            if row.get("portal_checked_at") is None:
                row["portal_checked_at"] = ""

        # Apply public output.json classification to all rows (cheap local operation).
        # - Managed (公開/非公開) stays as-is
        # - Otherwise if dataset_id is present in public output.json -> 公開2
        if not self._is_running_under_pytest():
            try:
                from classes.dataset.util.portal_status_resolver import PRIVATE_MANAGED_LABEL
                from classes.dataset.util.portal_status_resolver import PUBLIC_MANAGED_LABEL
                from classes.dataset.util.portal_status_resolver import PUBLIC_PUBLISHED_LABEL
            except Exception:
                PUBLIC_MANAGED_LABEL = "公開"
                PRIVATE_MANAGED_LABEL = "非公開"
                PUBLIC_PUBLISHED_LABEL = "公開2"

            try:
                from classes.utils.data_portal_public import get_public_published_dataset_ids

                public_ids = get_public_published_dataset_ids()
            except Exception:
                public_ids = set()

            if public_ids:
                checked_at_txt = ""
                try:
                    mtime = self._public_output_json_mtime_epoch()
                    checked_at_txt = self._format_portal_checked_at(mtime)
                except Exception:
                    checked_at_txt = ""

                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    dsid = str(row.get("dataset_id") or "").strip()
                    if not dsid or dsid not in public_ids:
                        continue
                    current = str(row.get("portal_status") or "").strip()
                    if current in {PUBLIC_MANAGED_LABEL, PRIVATE_MANAGED_LABEL}:
                        continue
                    row["portal_status"] = PUBLIC_PUBLISHED_LABEL
                    if checked_at_txt:
                        row["portal_checked_at"] = checked_at_txt

        if self._model is None:
            self._model = DatasetListTableModel(columns, rows, parent=self)
            self._filter_proxy.setSourceModel(self._model)
            self._limit_proxy.setSourceModel(self._filter_proxy)
            self._table.setModel(self._limit_proxy)
        else:
            self._model.set_rows(rows)

        # Apply cached portal statuses across ALL rows, even when not visible/paged.
        # This prevents "未確認" from reappearing after restart when cache already has values.
        try:
            self._reset_and_schedule_apply_cached_portal_statuses()
        except Exception:
            pass

        # portal_status filter should be exact-match ("公開" must not match "公開2").
        try:
            portal_col_idx = self._portal_status_column_index()
            if portal_col_idx is not None:
                self._filter_proxy.set_exact_match_columns({int(portal_col_idx)})
            else:
                self._filter_proxy.set_exact_match_columns(set())
        except Exception:
            pass

        self._update_top_counts_label(rows)
        self._rebuild_filters_panel()

        # Initial counts for portal filter (includes per-status counts).
        self._schedule_refresh_portal_ui_counts()

        # Portal column: show in-cell spinner during per-row refresh.
        try:
            self._install_portal_status_delegate()
        except Exception:
            pass

        # Apply saved column visibility (fallback: defaults)
        if self._is_running_under_pytest():
            visible_by_key = {c.key: c.default_visible for c in columns}
        else:
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

        # Fill portal status in background (visible page only).
        try:
            self._start_portal_fill_async()
        except Exception:
            pass

        # Bulk portal status via CSV (logged-in export)
        try:
            self._start_portal_csv_fill_async()
        except Exception:
            pass

        # 改行表示がある列のため、表示行数が少ない場合のみ行高を内容に合わせる
        try:
            limit = int(self._row_limit.value())
            if limit <= 0 or limit <= 200:
                self._adjust_row_heights_to_max_lines_visible_columns()
        except Exception:
            pass

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

    def _adjust_row_heights_to_max_lines_visible_columns(self) -> None:
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

        visible_cols = []
        for c in range(col_count):
            try:
                if self._table.isColumnHidden(c):
                    continue
            except Exception:
                pass
            visible_cols.append(c)

        fm = self._table.fontMetrics()
        line_h = max(1, int(fm.height()))
        max_h = int(self._row_max_height_px())
        padding = 8

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
        self._cancel_portal_fill()

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
        self._cancel_portal_fill()
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
        try:
            self._start_portal_fill_async()
        except Exception:
            pass

    def _apply_page(self) -> None:
        try:
            self._limit_proxy.set_page(int(self._page.value()))
        except Exception:
            return
        try:
            self._start_portal_fill_async()
        except Exception:
            pass

    def _clear_all_filters(self) -> None:
        for w in self._filter_edits_by_key.values():
            try:
                if isinstance(w, QComboBox):
                    w.setCurrentIndex(0)
                else:
                    w.setText("")
            except Exception:
                pass
        # Use 0/invalid as "no filter" by setting both to minimum and then disabling via internal state.
        self._embargo_from.setDate(QDate(2000, 1, 1))
        self._embargo_to.setDate(QDate(2000, 1, 1))
        self._open_at_from.setDate(QDate(2000, 1, 1))
        self._open_at_to.setDate(QDate(2000, 1, 1))
        self._modified_from.setDate(QDate(2000, 1, 1))
        self._modified_to.setDate(QDate(2000, 1, 1))
        self._created_from.setDate(QDate(2000, 1, 1))
        self._created_to.setDate(QDate(2000, 1, 1))
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
        self._filter_proxy.set_open_at_range(None, None)
        self._filter_proxy.set_modified_range(None, None)
        self._filter_proxy.set_created_range(None, None)
        self._apply_filters_now()

    def _apply_filters_now(self) -> None:
        filters_by_index: Dict[int, str] = {}
        key_to_index = {c.key: i for i, c in enumerate(self._columns)}
        for key, w in self._filter_edits_by_key.items():
            if key in {
                "description_len",
                "related_datasets_count",
                "embargo_date",
                "open_at_date",
                "modified_date",
                "created_date",
            }:
                # 範囲フィルタは専用UIで扱う
                continue
            idx = key_to_index.get(key)
            if idx is None:
                continue
            if isinstance(w, QComboBox):
                raw = w.currentData()
                text = (str(raw) if raw is not None else "").strip()
            else:
                text = (w.text() or "").strip()
            if text:
                filters_by_index[idx] = text
        self._filter_proxy.set_column_filters(filters_by_index)

        def _normalize_date_range(de_from: QDateEdit, de_to: QDateEdit) -> tuple[Optional[datetime.date], Optional[datetime.date]]:
            d_from = self._qdate_to_date(de_from.date())
            d_to = self._qdate_to_date(de_to.date())
            if d_from == datetime.date(2000, 1, 1):
                d_from = None
            if d_to == datetime.date(2000, 1, 1):
                d_to = None
            return d_from, d_to

        # Date ranges
        embargo_from, embargo_to = _normalize_date_range(self._embargo_from, self._embargo_to)
        self._filter_proxy.set_embargo_range(embargo_from, embargo_to)

        open_at_from, open_at_to = _normalize_date_range(self._open_at_from, self._open_at_to)
        self._filter_proxy.set_open_at_range(open_at_from, open_at_to)

        modified_from, modified_to = _normalize_date_range(self._modified_from, self._modified_to)
        self._filter_proxy.set_modified_range(modified_from, modified_to)

        created_from, created_to = _normalize_date_range(self._created_from, self._created_to)
        self._filter_proxy.set_created_range(created_from, created_to)

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
        self._schedule_refresh_portal_ui_counts()

    def _update_top_counts_label(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        if self._status is None:
            return
        if rows is None:
            rows = self._model.get_rows() if self._model is not None else []

        try:
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
        except Exception:
            UNCHECKED_LABEL = "未確認"

        total = 0
        confirmed = 0
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            total += 1
            s = str(row.get("portal_status") or "").strip()
            if s and s != UNCHECKED_LABEL:
                confirmed += 1

        self._status.setText(f"データセット/確認数 {total}/{confirmed} 件")

    def _schedule_refresh_portal_ui_counts(self) -> None:
        try:
            self._portal_ui_counts_refresh_timer.start()
        except Exception:
            pass

    def _reset_and_schedule_apply_cached_portal_statuses(self) -> None:
        """Apply cached portal statuses to all rows (batched).

        Rationale:
        - Historically, portal status auto-fill only touched visible/paged rows.
        - When cache already has labels, we should assign them regardless of table visibility.
        """

        self._portal_cache_apply_cursor = 0
        try:
            self._portal_cache_apply_timer.start()
        except Exception:
            # Best-effort fallback
            try:
                self._apply_cached_portal_statuses_batch()
            except Exception:
                pass

    def _apply_cached_portal_statuses_batch(self) -> None:
        if self._model is None:
            return

        rows = self._model.get_rows() if self._model is not None else []
        if not rows:
            return

        # Labels
        try:
            from classes.dataset.util.portal_status_resolver import (
                PUBLIC_MANAGED_LABEL as _PUBLIC_MANAGED_LABEL,
                PRIVATE_MANAGED_LABEL as _PRIVATE_MANAGED_LABEL,
                PUBLIC_PUBLISHED_LABEL as _PUBLIC_FALLBACK_LABEL,
                UNCHECKED_LABEL as _UNCHECKED_LABEL,
                pick_best_cached_label,
                resolve_portal_status_label,
            )
        except Exception:
            _PUBLIC_MANAGED_LABEL = "公開"
            _PRIVATE_MANAGED_LABEL = "非公開"
            _PUBLIC_FALLBACK_LABEL = "公開2"
            _UNCHECKED_LABEL = "未確認"
            pick_best_cached_label = None
            resolve_portal_status_label = None

        # Candidate environments for cache lookup
        env_candidates = self._collect_env_candidates_for_portal()
        if self._is_running_under_pytest():
            # Tests should not touch keyring/real credentials.
            worker_env = env_candidates[0] if env_candidates else "production"
        else:
            worker_env = self._pick_worker_env_with_credentials(env_candidates)

        # Public output.json IDs (cheap local)
        try:
            from classes.utils.data_portal_public import get_public_published_dataset_ids

            public_ids = get_public_published_dataset_ids()
        except Exception:
            public_ids = set()

        # Cache
        try:
            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

            cache = get_portal_entry_status_cache()
        except Exception:
            cache = None

        start = int(self._portal_cache_apply_cursor or 0)
        if start < 0:
            start = 0

        batch_size = 500
        end = min(start + batch_size, len(rows))

        updated = 0
        for i in range(start, end):
            row = rows[i] if 0 <= i < len(rows) else None
            if not isinstance(row, dict):
                continue

            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid:
                continue

            existing = row.get("portal_status")
            existing_text = str(existing).strip() if existing is not None else ""

            # Keep already-confirmed managed/public statuses.
            if existing_text in {_PUBLIC_MANAGED_LABEL, _PRIVATE_MANAGED_LABEL, _PUBLIC_FALLBACK_LABEL}:
                continue

            # Only fill when unchecked/blank.
            if existing_text and existing_text != _UNCHECKED_LABEL:
                continue

            # Public (no-login) published classification should be applied even when
            # logged-in cache has no label.
            if dsid in public_ids:
                updates: Dict[str, Any] = {"portal_status": _PUBLIC_FALLBACK_LABEL}
                try:
                    updates["portal_checked_at"] = self._format_portal_checked_at(self._public_output_json_mtime_epoch())
                except Exception:
                    pass
                try:
                    self._model.update_row_fields(int(i), updates)
                    updated += 1
                except Exception:
                    pass
                continue

            cached_label = None
            if cache is not None:
                if pick_best_cached_label is not None:
                    try:
                        cached_label = pick_best_cached_label(
                            dsid,
                            get_label=lambda d, e: cache.get_label_any_age(d, e) if hasattr(cache, "get_label_any_age") else cache.get_label(d, e),
                            environments=env_candidates,
                        )
                    except Exception:
                        cached_label = None
                else:
                    try:
                        cached_label = cache.get_label_any_age(dsid, worker_env) if hasattr(cache, "get_label_any_age") else cache.get_label(dsid, worker_env)
                    except Exception:
                        cached_label = None

            if not cached_label:
                continue

            resolved = None
            if resolve_portal_status_label is not None:
                try:
                    resolved = resolve_portal_status_label(
                        existing=existing_text,
                        cached=cached_label,
                        dataset_id=dsid,
                        public_published_dataset_ids=public_ids,
                    )
                except Exception:
                    resolved = None
            if resolved is None:
                resolved = str(cached_label).strip()

            updates: Dict[str, Any] = {"portal_status": resolved}
            # checked_at
            try:
                if str(resolved).strip() == _PUBLIC_FALLBACK_LABEL:
                    updates["portal_checked_at"] = self._format_portal_checked_at(self._public_output_json_mtime_epoch())
                else:
                    if cache is not None and hasattr(cache, "get_checked_at_any_age"):
                        epoch = cache.get_checked_at_any_age(dsid, worker_env)
                        txt = self._format_portal_checked_at(epoch)
                        if txt:
                            updates["portal_checked_at"] = txt
            except Exception:
                pass

            try:
                self._model.update_row_fields(int(i), updates)
                updated += 1
            except Exception:
                continue

        self._portal_cache_apply_cursor = end

        if updated:
            try:
                self._schedule_refresh_portal_ui_counts()
            except Exception:
                pass

        # Continue until all rows processed.
        if end < len(rows):
            try:
                # Give UI a breath.
                QTimer.singleShot(5, lambda: self._portal_cache_apply_timer.start())
            except Exception:
                try:
                    self._portal_cache_apply_timer.start()
                except Exception:
                    pass

    def _get_portal_status_filter_combo(self) -> Optional[QComboBox]:
        w = self._filter_edits_by_key.get("portal_status")
        return w if isinstance(w, QComboBox) else None

    def _refresh_portal_ui_counts(self) -> None:
        # Update top counts and portal filter counts.
        try:
            self._update_top_counts_label()
        except Exception:
            pass

        combo = self._get_portal_status_filter_combo()
        if combo is None or self._model is None:
            return

        portal_col_idx = self._portal_status_column_index()
        if portal_col_idx is None:
            return

        # Count within the current filter context excluding portal_status filter itself.
        counts: Dict[str, int] = {}
        total = 0
        for r in range(self._model.rowCount()):
            try:
                if not self._filter_proxy.accepts_row_ignoring_text_filter_columns(r, {int(portal_col_idx)}):
                    continue
            except Exception:
                continue

            total += 1
            idx = self._model.index(r, int(portal_col_idx))
            label = str(self._model.data(idx, Qt.DisplayRole) or "").strip()
            if label:
                # テーブル側の portal_status は「ステータス（日時）」形式なので、括弧以降は無視して集計する。
                key = DatasetFilterProxyModel._strip_parenthetical_suffix(label)
                if key:
                    counts[key] = counts.get(key, 0) + 1

        # Update item texts but keep itemData as the raw filter token.
        for i in range(combo.count()):
            data = combo.itemData(i)
            token = (str(data) if data is not None else "").strip()
            if not token:
                combo.setItemText(i, f"すべて ({total})")
                continue
            token_key = DatasetFilterProxyModel._strip_parenthetical_suffix(token)
            combo.setItemText(i, f"{token} ({counts.get(token_key, 0)})")

    def _auto_fetch_portal_statuses_if_needed(self) -> None:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        if self._model is None or not self.isVisible():
            return

        # Avoid piling up workers.
        if self._portal_thread is not None and self._portal_thread.isRunning():
            return

        try:
            from classes.dataset.util.portal_status_resolver import NONPUBLIC_OR_UNREGISTERED_LABEL
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
        except Exception:
            NONPUBLIC_OR_UNREGISTERED_LABEL = "管理外"
            UNCHECKED_LABEL = "未確認"

        # Apply cached labels globally (cheap, local) before deciding network access.
        try:
            self._reset_and_schedule_apply_cached_portal_statuses()
        except Exception:
            pass

        # Check ALL model rows (not only visible/page) so confirmation proceeds even when
        # rows are not currently displayed.
        needs_fetch = False
        try:
            rows = self._model.get_rows()
        except Exception:
            rows = []

        for row in rows or []:
            if not isinstance(row, dict):
                continue
            st = str(row.get("portal_status") or "").strip()
            if st in {"", UNCHECKED_LABEL}:
                needs_fetch = True
                break

        if not needs_fetch:
            return

        try:
            # Background fill should not depend on table visibility; let the fill logic pick tasks.
            self._start_portal_fill_async(mode="global")
        except Exception:
            pass

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
            for key, w in self._filter_edits_by_key.items():
                if isinstance(w, QComboBox):
                    raw = w.currentData()
                    text = (str(raw) if raw is not None else "").strip()
                else:
                    text = (w.text() or "").strip()
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
                "open_at_date",
                "modified_date",
                "created_date",
                "tile_count",
                "file_count",
                "tag_count",
                "portal_checked_at",
                "portal_open",
                "tool_open",
                "file_size",
            }:
                continue

            pair = QWidget(self)
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(6)

            lbl = bold_label(f"{cdef.label}:")
            if cdef.key == "portal_status":
                try:
                    from classes.dataset.util.portal_status_resolver import (
                        NONPUBLIC_OR_UNREGISTERED_LABEL,
                        PRIVATE_MANAGED_LABEL,
                        PUBLIC_MANAGED_LABEL,
                        PUBLIC_PUBLISHED_LABEL,
                        UNCHECKED_LABEL,
                    )
                except Exception:
                    UNCHECKED_LABEL = "未確認"
                    PUBLIC_MANAGED_LABEL = "公開"
                    PRIVATE_MANAGED_LABEL = "非公開"
                    PUBLIC_PUBLISHED_LABEL = "公開2"
                    NONPUBLIC_OR_UNREGISTERED_LABEL = "管理外"

                edit = QComboBox(self)
                edit.setObjectName("dataset_listing_filter_portal_status")
                edit.addItem("すべて", "")
                edit.addItem(UNCHECKED_LABEL, UNCHECKED_LABEL)
                edit.addItem(PUBLIC_MANAGED_LABEL, PUBLIC_MANAGED_LABEL)
                edit.addItem(PRIVATE_MANAGED_LABEL, PRIVATE_MANAGED_LABEL)
                edit.addItem(PUBLIC_PUBLISHED_LABEL, PUBLIC_PUBLISHED_LABEL)
                edit.addItem(NONPUBLIC_OR_UNREGISTERED_LABEL, NONPUBLIC_OR_UNREGISTERED_LABEL)
                edit.currentIndexChanged.connect(self._schedule_apply_filters)
                self._filter_edits_by_key[cdef.key] = edit
            elif cdef.key in {"is_anonymized", "is_data_entry_prohibited"}:
                edit = QComboBox(self)
                edit.addItem("すべて", "")
                edit.addItem("はい", "True")
                edit.addItem("いいえ", "False")
                edit.currentIndexChanged.connect(self._schedule_apply_filters)
                self._filter_edits_by_key[cdef.key] = edit
            elif cdef.key == "data_listing_type":
                edit = QComboBox(self)
                edit.addItem("すべて", "")
                values: List[str] = []
                try:
                    rows = self._model.get_rows() if self._model is not None else []
                    values = sorted({str(r.get("data_listing_type") or "").strip() for r in rows if isinstance(r, dict)})
                    values = [v for v in values if v]
                except Exception:
                    values = []
                for v in values:
                    edit.addItem(v, v)
                edit.currentIndexChanged.connect(self._schedule_apply_filters)
                self._filter_edits_by_key[cdef.key] = edit
            else:
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

    def _map_view_index_to_model_index(self, index: QModelIndex) -> Optional[QModelIndex]:
        """Map a view index to the underlying source model index.

        The view normally uses `self._limit_proxy`, but tests or future refactors may
        attach a different model. This helper makes click handlers more robust.
        """

        try:
            if index is None or (not index.isValid()) or self._model is None:
                return None
        except Exception:
            return None

        # Prefer walking the actual proxy chain from the index's model.
        # This avoids brittle identity checks between Python wrapper objects.
        try:
            current_index = index
            for _depth in range(6):
                if current_index is None or (not current_index.isValid()):
                    return None
                current_model = current_index.model()
                if current_model is self._model:
                    return current_index
                map_to_source = getattr(current_model, "mapToSource", None)
                if not callable(map_to_source):
                    break
                current_index = map_to_source(current_index)
            # Fallback: assume the standard limit->filter->model chain.
        except Exception:
            pass

        try:
            idx1 = self._limit_proxy.mapToSource(index)
            idx2 = self._filter_proxy.mapToSource(idx1)
            return idx2 if idx2 is not None and idx2.isValid() else None
        except Exception:
            return None

    def _on_table_clicked(self, index: QModelIndex) -> None:
        try:
            if not index.isValid() or self._model is None:
                return

            idx2 = self._map_view_index_to_model_index(index)
            if idx2 is None or (not idx2.isValid()):
                return

            col = self._columns[idx2.column()] if 0 <= idx2.column() < len(self._columns) else None
            if col is None:
                return

            if col.key == "portal_status":
                # Single click: only refresh when unchecked/blank.
                try:
                    rows = self._model.get_rows()
                    row = rows[idx2.row()] if 0 <= idx2.row() < len(rows) else {}
                    dsid = str(row.get("dataset_id") or "").strip()
                    if not dsid:
                        return
                    try:
                        from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
                    except Exception:
                        UNCHECKED_LABEL = "未確認"
                    current = str(row.get("portal_status") or "").strip()
                    if self._is_running_under_pytest() or (not current) or (current == UNCHECKED_LABEL):
                        self._start_portal_status_refresh_for_model_row(int(idx2.row()), dsid)
                except Exception:
                    return
                return

            if col.key not in {
                "dataset_name",
                "instrument_names",
                "subgroup_name",
                "tool_open",
                "portal_open",
                "manager_name",
                "applicant_name",
                "data_owner_names",
            }:
                return

            if col.key in {"dataset_name", "subgroup_name", "manager_name", "applicant_name", "data_owner_names"}:
                url = self._model.data(idx2, Qt.UserRole)
                if isinstance(url, str) and url:
                    QDesktopServices.openUrl(QUrl(url))
                    return
                if isinstance(url, list) and url:
                    # Multiple owners: let user choose.
                    try:
                        dlg = InstrumentLinkSelectorDialog(self, url)
                        dlg.setWindowTitle("ユーザーを選択")
                        if dlg.exec() == QDialog.Accepted:
                            chosen = dlg.selected_url()
                            if chosen:
                                QDesktopServices.openUrl(QUrl(chosen))
                    except Exception:
                        return
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

            if col.key == "portal_open":
                dataset_id = self._model.data(idx2, Qt.UserRole)
                dataset_id = dataset_id if isinstance(dataset_id, str) else ""
                dataset_id = dataset_id.strip()
                if dataset_id and callable(self._portal_open_callback):
                    try:
                        self._portal_open_callback(dataset_id)
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

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        """Double-click handler.

        Portal status confirmation is triggered on double click as well to make the UX
        resilient against selection/focus related click quirks.
        """

        try:
            if not index.isValid() or self._model is None:
                return

            idx2 = self._map_view_index_to_model_index(index)
            if idx2 is None or (not idx2.isValid()):
                return

            col = self._columns[idx2.column()] if 0 <= idx2.column() < len(self._columns) else None
            if col is None or col.key != "portal_status":
                return

            rows = self._model.get_rows()
            row = rows[idx2.row()] if 0 <= idx2.row() < len(rows) else {}
            dsid = str(row.get("dataset_id") or "").strip()
            if dsid:
                self._start_portal_status_refresh_for_model_row(int(idx2.row()), dsid)
        except Exception:
            return

    def _on_table_pressed(self, index: QModelIndex) -> None:
        """Mouse press handler (portal_status refresh only).

        Rationale:
        - Some environments can be flaky about `clicked` emission timing.
        - We restrict this handler to portal_status to avoid duplicate URL opens.
        """

        try:
            if not index.isValid() or self._model is None:
                return

            idx2 = self._map_view_index_to_model_index(index)
            if idx2 is None or (not idx2.isValid()):
                return

            col = self._columns[idx2.column()] if 0 <= idx2.column() < len(self._columns) else None
            if col is None or col.key != "portal_status":
                return

            rows = self._model.get_rows()
            row = rows[idx2.row()] if 0 <= idx2.row() < len(rows) else {}
            dsid = str(row.get("dataset_id") or "").strip()
            if not dsid:
                return

            try:
                from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL
            except Exception:
                UNCHECKED_LABEL = "未確認"

            current = str(row.get("portal_status") or "").strip()
            if self._is_running_under_pytest() or (not current) or (current == UNCHECKED_LABEL):
                self._start_portal_status_refresh_for_model_row(int(idx2.row()), dsid)
        except Exception:
            return

    def _confirm_and_force_refresh_portal_statuses_nonpublic_only(self) -> None:
        if self._model is None:
            return
        if self._is_running_under_pytest():
            return

        reply = QMessageBox.question(
            self,
            "確認",
            "データカタログ（データポータル）ステータスを『未確認のみ』強制更新します。\n\n"
            "- 対象: 未確認 / 非公開 / 管理外 / 空\n"
            "- 公開（公開/公開2）は原則スキップします\n"
            "- 対象のキャッシュのみクリアして再取得します\n\n"
            "実行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._force_refresh_portal_statuses_impl(scope="nonpublic")

    def _force_refresh_portal_statuses_impl(self, *, scope: str) -> None:
        """Force refresh portal statuses.

        scope:
            - "all": reset all rows and clear entire cache
            - "nonpublic": reset only non-public rows and clear cache for those dataset IDs
        """

        if self._model is None:
            return

        # Mark force refresh in-flight.
        self._portal_force_refresh_inflight = True
        self._portal_force_refresh_pending_parts = set()

        # Stop background workers first.
        try:
            self._cancel_portal_fill()
        except Exception:
            pass
        try:
            self._cancel_portal_csv_fill()
        except Exception:
            pass

        # Labels
        try:
            from classes.dataset.util.portal_status_resolver import (
                PUBLIC_MANAGED_LABEL,
                PUBLIC_PUBLISHED_LABEL,
                UNCHECKED_LABEL,
            )
        except Exception:
            PUBLIC_MANAGED_LABEL = "公開"
            PUBLIC_PUBLISHED_LABEL = "公開2"
            UNCHECKED_LABEL = "未確認"

        rows = self._model.get_rows()

        # Determine which dataset IDs/rows to reset.
        target_rows: List[int] = []
        target_dataset_ids: set[str] = set()
        if str(scope).strip() == "nonpublic":
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                dsid = str(row.get("dataset_id") or "").strip()
                if not dsid:
                    continue
                st = str(row.get("portal_status") or "").strip()
                if st in {PUBLIC_MANAGED_LABEL, PUBLIC_PUBLISHED_LABEL}:
                    continue
                target_rows.append(int(i))
                target_dataset_ids.add(dsid)
        else:
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                dsid = str(row.get("dataset_id") or "").strip()
                if not dsid:
                    continue
                target_rows.append(int(i))
                target_dataset_ids.add(dsid)

        if not target_rows:
            self._portal_force_refresh_inflight = False
            self._portal_force_refresh_pending_parts = set()
            return

        # Clear cache (best-effort).
        try:
            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

            cache = get_portal_entry_status_cache()
            if str(scope).strip() == "nonpublic" and hasattr(cache, "clear_dataset_ids"):
                cache.clear_dataset_ids(target_dataset_ids, None)
            elif hasattr(cache, "clear"):
                cache.clear(None)
        except Exception:
            pass

        # Reset target rows to unchecked.
        for i in target_rows:
            try:
                self._model.update_row_fields(int(i), {"portal_status": UNCHECKED_LABEL, "portal_checked_at": ""})
            except Exception:
                continue

        # Baseline: apply public output.json classification immediately (no network, cheap).
        try:
            self._apply_public_output_json_classification_to_all_rows()
        except Exception:
            pass

        # Kick bulk CSV fill first (fast path).
        try:
            self._start_portal_csv_fill_async()
        except Exception:
            pass

        try:
            if self._portal_csv_thread is not None and self._portal_csv_thread.isRunning():
                self._portal_force_refresh_pending_parts.add("csv")
        except Exception:
            pass

        # Then run portal fill for target rows (logged-in HTML check).
        try:
            env_candidates = self._collect_env_candidates_for_portal()
            worker_env = self._pick_worker_env_with_credentials(env_candidates)
            self._portal_fill_environment = str(worker_env or "production").strip() or "production"

            tasks: List[tuple[int, str]] = []
            for idx in target_rows:
                try:
                    row = rows[int(idx)]
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                dsid = str(row.get("dataset_id") or "").strip()
                if not dsid:
                    continue
                tasks.append((int(idx), dsid))

            if tasks:
                # Start overlay spinner with progress (planned total / processed count)
                try:
                    self._portal_force_refresh_progress_total = int(len(tasks))
                    self._portal_force_refresh_progress_done = 0
                    if hasattr(self, "_spinner_overlay") and self._spinner_overlay is not None:
                        self._spinner_overlay.show_message("データポータル確認中…")
                        self._spinner_overlay.set_progress(0, int(self._portal_force_refresh_progress_total), prefix="処理済み")
                        self._spinner_overlay.start()
                except Exception:
                    pass

            if tasks:
                thread = QThread()
                worker = DatasetListingWidget._PortalFillWorker(tasks, self._portal_fill_environment)
                worker.moveToThread(thread)

                thread.started.connect(worker.run)
                worker.row_ready.connect(self._on_portal_row_ready)
                worker.finished.connect(self._on_portal_fill_finished)
                worker.finished.connect(worker.deleteLater)
                worker.finished.connect(thread.quit)
                thread.finished.connect(thread.deleteLater)

                self._portal_worker = worker
                self._portal_thread = thread

                _ACTIVE_DATASET_LISTING_PORTAL_THREADS.add(thread)
                try:
                    setattr(thread, "_portal_worker", worker)
                except Exception:
                    pass
                try:
                    thread.finished.connect(lambda: _ACTIVE_DATASET_LISTING_PORTAL_THREADS.discard(thread))
                except Exception:
                    pass

                self._portal_force_refresh_pending_parts.add("html")
                thread.start()
        except Exception:
            pass

        # If nothing started, finalize immediately.
        if not self._portal_force_refresh_pending_parts:
            self._portal_force_refresh_inflight = False
            try:
                self._portal_force_refresh_progress_total = None
                self._portal_force_refresh_progress_done = 0
                if hasattr(self, "_spinner_overlay") and self._spinner_overlay is not None:
                    self._spinner_overlay.stop()
            except Exception:
                pass

    def set_tool_open_callback(self, callback) -> None:
        self._tool_open_callback = callback

    def set_portal_open_callback(self, callback) -> None:
        self._portal_open_callback = callback


def create_dataset_listing_widget(parent=None, title: str = "一覧") -> QWidget:
    _ = title
    return DatasetListingWidget(parent)
