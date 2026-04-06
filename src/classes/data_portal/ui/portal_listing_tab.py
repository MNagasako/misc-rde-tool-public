"""Authenticated Data Portal listing tab (merged public+managed).

Implementation notes:
- This tab intentionally does NOT modify the existing public (no-login) listing tab.
- It reuses the same table behaviour pattern as the public listing:
  filter + sort + preview truncation.
  (See `classes.data_portal.ui.public_listing_tab.PublicDataPortalListingTab`)

Future maintenance:
- We may want to refactor common parts between public_listing_tab and this tab.
  For now, keep behaviour aligned but isolated to avoid regressions.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from qt_compat import QtCore, QtGui
from qt_compat.core import Qt, QThread, Signal, QUrl
from qt_compat.widgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QtWidgets,
    QVBoxLayout,
    QWidget,
)

from classes.data_portal.util.public_output_paths import get_public_data_portal_cache_dir
from classes.data_portal.util.managed_csv_paths import build_managed_csv_path, find_latest_managed_csv, format_mtime_jst, format_size
from classes.data_portal.util.managed_suffix_grouping import add_grouped_suffix_columns
from classes.ui.utilities.listing_support import prepare_display_value
from classes.ui.utilities.listing_table import ListingFilterProxyModel
from classes.ui.utilities.table_export import write_record_export

from classes.theme import ThemeKey, get_color
from classes.theme import get_qcolor
from classes.utils.button_styles import get_button_style
from classes.data_portal.core.portal_csv_full import (
    extract_code as extract_managed_code,
    extract_dataset_id as extract_managed_dataset_id,
    parse_portal_csv_payload_to_records,
)
from classes.data_portal.core.portal_entry_merge import merge_public_and_managed

LOGGER = logging.getLogger(__name__)

_ITEM_THEME_FOREGROUND_ROLE = int(Qt.ItemDataRole.UserRole) + 20
_ITEM_THEME_BACKGROUND_ROLE = int(Qt.ItemDataRole.UserRole) + 21


class _SemanticColorDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index) -> None:  # type: ignore[override]
        super().initStyleOption(option, index)

        if bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected):
            return

        foreground_kind = str(index.data(_ITEM_THEME_FOREGROUND_ROLE) or "").strip()
        if foreground_kind == "link":
            option.palette.setColor(QtGui.QPalette.ColorRole.Text, get_qcolor(ThemeKey.TEXT_LINK))
            option.palette.setColor(QtGui.QPalette.ColorRole.WindowText, get_qcolor(ThemeKey.TEXT_LINK))
        elif foreground_kind == "primary":
            option.palette.setColor(QtGui.QPalette.ColorRole.Text, get_qcolor(ThemeKey.TEXT_PRIMARY))
            option.palette.setColor(QtGui.QPalette.ColorRole.WindowText, get_qcolor(ThemeKey.TEXT_PRIMARY))

        background_kind = str(index.data(_ITEM_THEME_BACKGROUND_ROLE) or "").strip()
        if background_kind == "info":
            option.backgroundBrush = QtGui.QBrush(get_qcolor(ThemeKey.PANEL_INFO_BACKGROUND))
        elif background_kind == "warning":
            option.backgroundBrush = QtGui.QBrush(get_qcolor(ThemeKey.PANEL_WARNING_BACKGROUND))


class _SourceAwareProxyModel(ListingFilterProxyModel):
    _RANGE_DATE_LABELS: set[str] = {
        "開始日",
        "開設日",
        "登録日",
        "エンバーゴ解除日",
        "データ最終更新日",
        "データ登録日",
        "最終更新日",
    }
    _RANGE_NUMERIC_LABELS: set[str] = {
        "データタイル数",
        "DL数",
        "ダウンロード数",
        "ファイルサイズ",
        "ファイル数",
        "ページビュー",
        "閲覧数",
    }
    _SORT_NUMERIC_LABELS: set[str] = {
        "データタイル数",
        "DL数",
        "ダウンロード数",
        "ファイルサイズ",
        "ファイル数",
        "ページビュー",
        "閲覧数",
    }
    _SORT_NATURAL_LABELS: set[str] = {
        "code",
    }

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        # all: 全て（公開+管理）
        # public_with_managed: 公開①（管理に含まれているものを含む = public+both）
        # public_only: 公開②（管理に含まれているものは除く = publicのみ）
        # managed: 管理（管理CSVに含まれているもののみ = managed+both）
        self._range_mode = "all"
        self._source_column = -1

        self._column_filters: dict[int, str] = {}
        self._column_filter_patterns: dict[int, list[re.Pattern]] = {}

    @classmethod
    def _normalize_header_label(cls, label: str) -> str:
        text = str(label or "").strip()
        if text.startswith("【") and text.endswith("】") and len(text) > 2:
            text = text[1:-1]
        text = text.replace(" ", "").replace("　", "")
        return text

    @classmethod
    def _is_date_range_label(cls, label: str) -> bool:
        return cls._normalize_header_label(label) in cls._RANGE_DATE_LABELS

    @classmethod
    def _is_numeric_range_label(cls, label: str) -> bool:
        return cls._normalize_header_label(label) in cls._RANGE_NUMERIC_LABELS

    @staticmethod
    def _is_structured_range_query(text: str) -> bool:
        raw = str(text or "")
        return any(token in raw for token in (">=", "<=", "..", "〜", "～", "~")) or raw.strip().startswith((">", "<", "="))

    @staticmethod
    def _parse_date_value(value: str) -> Optional[date]:
        text = str(value or "").strip()
        if not text:
            return None
        matched = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if not matched:
            return None
        try:
            return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
        except Exception:
            return None

    @staticmethod
    def _parse_numeric_value(value: str) -> Optional[float]:
        text = str(value or "").strip()
        if not text:
            return None

        bytes_match = re.search(r"([\d,]+)\s*bytes", text, flags=re.IGNORECASE)
        if bytes_match:
            try:
                return float(bytes_match.group(1).replace(",", ""))
            except Exception:
                pass

        size_match = re.search(r"([-+]?\d[\d,]*(?:\.\d+)?)\s*([kmgtpe]?i?b|bytes?)\b", text, flags=re.IGNORECASE)
        if size_match:
            try:
                num = float(size_match.group(1).replace(",", ""))
                unit = str(size_match.group(2) or "").strip().lower()
                multipliers = {
                    "b": 1.0,
                    "byte": 1.0,
                    "bytes": 1.0,
                    "kb": 1024.0,
                    "kib": 1024.0,
                    "mb": 1024.0 ** 2,
                    "mib": 1024.0 ** 2,
                    "gb": 1024.0 ** 3,
                    "gib": 1024.0 ** 3,
                    "tb": 1024.0 ** 4,
                    "tib": 1024.0 ** 4,
                    "pb": 1024.0 ** 5,
                    "pib": 1024.0 ** 5,
                    "eb": 1024.0 ** 6,
                    "eib": 1024.0 ** 6,
                }
                factor = float(multipliers.get(unit, 1.0))
                return num * factor
            except Exception:
                pass

        matched = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text)
        if not matched:
            return None
        try:
            return float(matched.group(0).replace(",", ""))
        except Exception:
            return None

    @classmethod
    def _is_numeric_sort_label(cls, label: str) -> bool:
        return cls._normalize_header_label(label) in cls._SORT_NUMERIC_LABELS

    @classmethod
    def _is_natural_sort_label(cls, label: str) -> bool:
        return cls._normalize_header_label(label).lower() in {s.lower() for s in cls._SORT_NATURAL_LABELS}

    @staticmethod
    def _natural_sort_key(value: Any) -> list[Any]:
        text = str(value or "")
        parts = re.split(r"(\d+)", text)
        key: list[Any] = []
        for part in parts:
            if part.isdigit():
                key.append((0, int(part)))
            else:
                key.append((1, part.lower()))
        return key

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:  # type: ignore[override] # noqa: N802
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)

        column = int(left.column())
        header = str(model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
        raw_role = int(Qt.ItemDataRole.UserRole) + 1
        left_raw = model.data(left, raw_role)
        right_raw = model.data(right, raw_role)
        if left_raw is None:
            left_raw = model.data(left, Qt.ItemDataRole.DisplayRole)
        if right_raw is None:
            right_raw = model.data(right, Qt.ItemDataRole.DisplayRole)

        if self._is_numeric_sort_label(header):
            left_num = self._parse_numeric_value(str(left_raw or ""))
            right_num = self._parse_numeric_value(str(right_raw or ""))
            if left_num is None and right_num is None:
                return self._natural_sort_key(left_raw) < self._natural_sort_key(right_raw)
            if left_num is None:
                return False
            if right_num is None:
                return True
            if left_num == right_num:
                return self._natural_sort_key(left_raw) < self._natural_sort_key(right_raw)
            return left_num < right_num

        if self._is_natural_sort_label(header):
            return self._natural_sort_key(left_raw) < self._natural_sort_key(right_raw)

        return super().lessThan(left, right)

    @staticmethod
    def _split_range_query(text: str) -> Optional[tuple[str, str]]:
        raw = str(text or "").strip()
        if ".." in raw:
            lhs, rhs = raw.split("..", 1)
            return lhs.strip(), rhs.strip()
        for sep in ("〜", "～", "~"):
            if sep in raw:
                lhs, rhs = raw.split(sep, 1)
                return lhs.strip(), rhs.strip()
        return None

    def _matches_date_range(self, cell_value: str, query: str) -> Optional[bool]:
        if not self._is_structured_range_query(query):
            return None
        current = self._parse_date_value(cell_value)
        if current is None:
            return False

        range_parts = self._split_range_query(query)
        if range_parts is not None:
            from_s, to_s = range_parts
            from_d = self._parse_date_value(from_s)
            to_d = self._parse_date_value(to_s)
            if from_d is None and to_d is None:
                return None
            if from_d is not None and current < from_d:
                return False
            if to_d is not None and current > to_d:
                return False
            return True

        expr = str(query or "").strip()
        for op in (">=", "<=", ">", "<", "="):
            if not expr.startswith(op):
                continue
            target = self._parse_date_value(expr[len(op) :].strip())
            if target is None:
                return None
            if op == ">=":
                return current >= target
            if op == "<=":
                return current <= target
            if op == ">":
                return current > target
            if op == "<":
                return current < target
            return current == target
        return None

    def _matches_numeric_range(self, cell_value: str, query: str) -> Optional[bool]:
        if not self._is_structured_range_query(query):
            return None
        current = self._parse_numeric_value(cell_value)
        if current is None:
            return False

        range_parts = self._split_range_query(query)
        if range_parts is not None:
            from_s, to_s = range_parts
            from_n = self._parse_numeric_value(from_s)
            to_n = self._parse_numeric_value(to_s)
            if from_n is None and to_n is None:
                return None
            if from_n is not None and current < from_n:
                return False
            if to_n is not None and current > to_n:
                return False
            return True

        expr = str(query or "").strip()
        for op in (">=", "<=", ">", "<", "="):
            if not expr.startswith(op):
                continue
            target = self._parse_numeric_value(expr[len(op) :].strip())
            if target is None:
                return None
            if op == ">=":
                return current >= target
            if op == "<=":
                return current <= target
            if op == ">":
                return current > target
            if op == "<":
                return current < target
            return current == target
        return None

    def set_source_column(self, column: int) -> None:
        self._source_column = int(column)
        self.invalidateFilter()

    def set_range_mode(self, mode: str) -> None:
        self._range_mode = str(mode or "all")
        self.invalidateFilter()

    @staticmethod
    def _split_filter_terms(text: str) -> list[str]:
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
    def _compile_terms(cls, text: str) -> list[re.Pattern]:
        patterns: list[re.Pattern] = []
        for term in cls._split_filter_terms(text):
            pat = cls._compile_wildcard_pattern(term)
            if pat is not None:
                patterns.append(pat)
        return patterns

    def set_column_filters(self, filters_by_col_index: dict[int, str]) -> None:
        cleaned: dict[int, str] = {}
        compiled: dict[int, list[re.Pattern]] = {}
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

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:  # type: ignore[override]
        if not super().filterAcceptsRow(source_row, source_parent):
            return False

        if self._range_mode == "all" or self._source_column < 0:
            range_ok = True
        else:
            model = self.sourceModel()
            if model is None:
                range_ok = True
            else:
                value = model.index(source_row, self._source_column, source_parent).data()
                src = str(value or "")
                if self._range_mode == "public_with_managed":
                    range_ok = src in ("public", "both")
                elif self._range_mode == "public_only":
                    range_ok = src == "public"
                elif self._range_mode == "managed":
                    range_ok = src in ("managed", "both")
                else:
                    range_ok = True

        if not range_ok:
            return False

        if not self._column_filter_patterns:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        for col_idx, patterns in (self._column_filter_patterns or {}).items():
            if col_idx < 0 or col_idx >= model.columnCount():
                continue
            idx = model.index(source_row, int(col_idx), source_parent)
            hay = str(model.data(idx, Qt.DisplayRole) or "")
            raw_filter = str((self._column_filters or {}).get(int(col_idx), "") or "").strip()

            header = str(model.headerData(int(col_idx), Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
            range_result: Optional[bool] = None
            if self._is_date_range_label(header):
                range_result = self._matches_date_range(hay, raw_filter)
            elif self._is_numeric_range_label(header):
                range_result = self._matches_numeric_range(hay, raw_filter)

            if range_result is not None:
                if not range_result:
                    return False
                continue

            if not any(p.search(hay) for p in (patterns or [])):
                return False
        return True


@dataclass(frozen=True)
class _ColumnDef:
    key: str
    label: str
    preview_limit: int = 180
    default_visible: bool = True


class _ColumnSelectDialog(QDialog):
    def __init__(self, columns: list[_ColumnDef], visible_keys: set[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("列選択")
        self._columns = list(columns or [])
        self._visible_keys = set(visible_keys or set())
        self._default_visible_by_key: dict[str, bool] = {c.key: bool(c.default_visible) for c in self._columns}
        self._checkbox_by_key: dict[str, QCheckBox] = {}
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(0)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)

        for col in self._columns:
            cb = QCheckBox(col.label, body)
            cb.setChecked(bool(col.key in self._visible_keys))
            self._checkbox_by_key[col.key] = cb
            body_layout.addWidget(cb)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        quick = QHBoxLayout()
        btn_all = QPushButton("全選択", self)
        btn_all.clicked.connect(self._select_all)
        quick.addWidget(btn_all)

        btn_none = QPushButton("全非選択", self)
        btn_none.clicked.connect(self._select_none)
        quick.addWidget(btn_none)

        btn_reset = QPushButton("列リセット", self)
        btn_reset.clicked.connect(self._reset_to_default)
        quick.addWidget(btn_reset)

        quick.addStretch(1)
        layout.addLayout(quick)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_theme(self) -> None:
        try:
            self.setStyleSheet(
                f"QDialog {{ background-color: {get_color(ThemeKey.BACKGROUND_PRIMARY)}; }}"
                f"QLabel {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
                f"QScrollArea {{ background-color: {get_color(ThemeKey.BACKGROUND_PRIMARY)}; }}"
                f"QWidget {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
                f"QCheckBox {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}"
            )
        except Exception:
            pass

    def _select_all(self) -> None:
        for cb in (self._checkbox_by_key or {}).values():
            try:
                cb.setChecked(True)
            except Exception:
                pass

    def _select_none(self) -> None:
        for cb in (self._checkbox_by_key or {}).values():
            try:
                cb.setChecked(False)
            except Exception:
                pass

    def _reset_to_default(self) -> None:
        for key, cb in (self._checkbox_by_key or {}).items():
            try:
                cb.setChecked(bool(self._default_visible_by_key.get(key, True)))
            except Exception:
                pass

    def selected_keys(self) -> set[str]:
        out: set[str] = set()
        for key, cb in (self._checkbox_by_key or {}).items():
            try:
                if cb.isChecked():
                    out.add(key)
            except Exception:
                continue
        return out


class _ManagedFetchWorker(QtCore.QObject):
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, portal_client: Any, *, environment: str):
        super().__init__()
        self._client = portal_client
        self._environment = str(environment or "production").strip() or "production"

    def run(self) -> None:
        try:
            if self._client is None:
                self.failed.emit("PortalClientが未設定です")
                return
            ok, resp = self._client.download_theme_csv()
            if not ok:
                self.failed.emit(str(resp))
                return
            payload = getattr(resp, "content", None)
            if isinstance(payload, bytes):
                data = payload
            else:
                text = getattr(resp, "text", "")
                data = (text or "").encode("utf-8", errors="replace")

            if not data:
                self.failed.emit("CSVの内容が空です")
                return

            # ログイン設定タブと同じ場所へ保存して共通化
            try:
                path = build_managed_csv_path(self._environment, now=datetime.now())
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                path.write_bytes(data)
            except Exception:
                # 保存失敗でも画面更新は可能なため継続
                pass

            records = parse_portal_csv_payload_to_records(data)
            self.succeeded.emit(records)
        except Exception as exc:
            self.failed.emit(str(exc))


class PortalListingTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._portal_client = None
        self._environment: str = "production"
        self._managed_records: list[dict[str, str]] = []
        self._thread: Optional[QThread] = None

        self._public_cache_records: list[dict] = []
        self._public_cache_env: Optional[str] = None
        self._public_cache_loaded: bool = False
        self._auto_refresh_attempted_envs: set[str] = set()
        self._syncing_env_combo: bool = False
        self.env_combo: Optional[QComboBox] = None

        self._columns: list[_ColumnDef] = []
        self._visible_columns: set[str] = set()
        self._column_index: dict[str, int] = {}

        self._filters_container: Optional[QWidget] = None
        self._filters_summary_label: Optional[QLabel] = None
        self._filters_layout: Optional[QGridLayout] = None
        self._filters_scroll: Optional[QScrollArea] = None
        self._filter_field_widgets: list[tuple[str, QWidget]] = []
        self._filter_edits_by_key: dict[str, QLineEdit] = {}
        self._filters_collapsed: bool = False
        self._filter_apply_timer: Optional[QtCore.QTimer] = None

        self._ui_ready: bool = False

        self._filter_mode: str = "all"  # all | group
        self._filter_group_kind: str = "fixed"  # fixed | managed_group | managed_raw
        self._display_mode: str = "default"  # default | compact | equal
        self._did_apply_initial_layout: bool = False
        self._populate_token: int = 0
        self._pending_rows: list[dict[str, Any]] = []
        self._pending_visible_cols: list[_ColumnDef] = []
        self._pending_row_index: int = 0

        self._setup_ui()
        self.refresh_public_from_disk()
        self.refresh_managed_from_disk()
        self._maybe_auto_refresh_managed()

    def _build_base_stylesheet(self) -> str:
        return f"""
            QWidget#portalListingTabRoot QTableView#dataPortalListingTable {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                alternate-background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                gridline-color: {get_color(ThemeKey.BORDER_DEFAULT)};
                selection-background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                selection-color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
            }}
            QWidget#portalListingTabRoot QTableView#dataPortalListingTable::item {{
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
            }}
            QWidget#portalListingTabRoot QTableView#dataPortalListingTable QHeaderView::section {{
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_SECONDARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                padding: 4px 6px;
                font-weight: bold;
            }}
            QWidget#portalListingTabRoot QTableView#dataPortalListingTable QTableCornerButton::section {{
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
            }}
        """

    @staticmethod
    def _is_running_under_pytest() -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST"))

    def _needs_managed_refresh(self) -> bool:
        try:
            info = find_latest_managed_csv(self._environment)
        except Exception:
            info = None
        return info is None

    def _maybe_auto_refresh_managed(self) -> None:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        if self._is_running_under_pytest():
            return
        env = str(self._environment or "production").strip() or "production"
        if env in self._auto_refresh_attempted_envs:
            return
        self._auto_refresh_attempted_envs.add(env)
        if not self._needs_managed_refresh():
            return
        try:
            from qt_compat.core import QTimer

            QTimer.singleShot(0, lambda: self.refresh_managed_from_portal(user_initiated=False, skip_confirm=True))
        except Exception:
            pass

    def set_portal_client(self, portal_client: Any) -> None:
        self._portal_client = portal_client

    def set_environment(self, environment: str) -> None:
        env = str(environment or "production").strip() or "production"
        if env == self._environment:
            return
        self._environment = env
        self._set_env_combo(env)
        # 環境が切り替わったら、管理側は取り直し（別環境の結果を混ぜない）
        self._managed_records = []
        self._portal_client = None
        self.status_label.setText(f"環境切替: {env}（管理CSVは未取得）")
        self.refresh_public_from_disk()
        self.refresh_managed_from_disk()
        self._maybe_auto_refresh_managed()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setObjectName("portalListingTabRoot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("📋 データポータル 一覧（公開 + 管理）")
        title.setObjectName("portalListingTitle")
        layout.addWidget(title)

        env_group = self._create_environment_group()
        layout.addWidget(env_group)

        controls = QHBoxLayout()
        self._controls_layout = controls
        layout.addLayout(controls)

        controls.addWidget(QLabel("表示範囲:"))
        self.range_combo = QComboBox()
        self.range_combo.addItem("全て（公開+管理）", "all")
        self.range_combo.addItem("公開①（管理を含む）", "public_with_managed")
        self.range_combo.addItem("公開②（管理を除く）", "public_only")
        self.range_combo.addItem("管理（CSVのみ）", "managed")
        self.range_combo.currentIndexChanged.connect(self._on_range_changed)
        controls.addWidget(self.range_combo)

        controls.addSpacing(12)

        self.reload_public = QPushButton("公開cache再読込")
        self.reload_public.clicked.connect(self.refresh_public_from_disk)
        controls.addWidget(self.reload_public)

        self.reload_managed = QPushButton("管理CSV更新")
        self.reload_managed.clicked.connect(lambda: self.refresh_managed_from_portal(user_initiated=True))
        controls.addWidget(self.reload_managed)

        self.select_columns_btn = QPushButton("表示列…")
        self.select_columns_btn.clicked.connect(self._on_select_columns)
        controls.addWidget(self.select_columns_btn)

        controls.addSpacing(12)

        self.compact_rows_btn = QPushButton("1行表示", self)
        self.compact_rows_btn.clicked.connect(self._toggle_compact_rows)
        controls.addWidget(self.compact_rows_btn)

        self.equal_columns_btn = QPushButton("列幅そろえ", self)
        self.equal_columns_btn.clicked.connect(lambda: self._apply_display_mode("equal"))
        controls.addWidget(self.equal_columns_btn)

        export_menu = QMenu(self)
        export_csv = export_menu.addAction("CSV出力")
        export_csv.triggered.connect(lambda: self._export("csv"))
        export_xlsx = export_menu.addAction("XLSX出力")
        export_xlsx.triggered.connect(lambda: self._export("xlsx"))

        self.export_btn = QPushButton("エクスポート")
        self.export_btn.setMenu(export_menu)
        controls.addWidget(self.export_btn)

        controls.addWidget(QLabel("列フィルタ表示:"))
        self.filter_scope_combo = QComboBox(self)
        self.filter_scope_combo.addItem("すべて", "all")
        self.filter_scope_combo.addItem("基本", "fixed")
        self.filter_scope_combo.addItem("管理（結合）", "managed_group")
        self.filter_scope_combo.addItem("管理（その他）", "managed_raw")
        self.filter_scope_combo.currentIndexChanged.connect(self._on_filter_scope_changed)
        controls.addWidget(self.filter_scope_combo)

        self.toggle_filters_button = QPushButton("フィルタ最小化")
        self.toggle_filters_button.clicked.connect(self._toggle_filters_collapsed)
        controls.addWidget(self.toggle_filters_button)

        self.count_label = QLabel("0件")
        controls.addWidget(self.count_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Per-column filters (visible columns only)
        self.filters_group_box = QGroupBox("列フィルタ", self)
        self.filters_group_box.setObjectName("portalListingFilters")

        filters_outer = QVBoxLayout(self.filters_group_box)
        filters_outer.setContentsMargins(8, 8, 8, 8)
        filters_outer.setSpacing(6)

        self._filters_summary_label = QLabel("", self.filters_group_box)
        self._filters_summary_label.setObjectName("portal_listing_filters_summary")
        try:
            self._filters_summary_label.setWordWrap(True)
        except Exception:
            pass
        filters_outer.addWidget(self._filters_summary_label)

        self._filters_scroll = None
        self._filters_container = QWidget(self.filters_group_box)
        self._filters_container.setObjectName("portal_listing_filters_container")
        self._filters_layout = QGridLayout(self._filters_container)
        self._filters_layout.setContentsMargins(0, 0, 0, 0)
        self._filters_layout.setHorizontalSpacing(8)
        self._filters_layout.setVerticalSpacing(6)
        filters_outer.addWidget(self._filters_container)

        layout.addWidget(self.filters_group_box)
        self._set_filters_collapsed(False)
        self._apply_filters_theme()

        try:
            self.reload_public.setStyleSheet(get_button_style("info"))
            self.reload_managed.setStyleSheet(get_button_style("warning"))
            self.select_columns_btn.setStyleSheet(get_button_style("secondary"))
            self.compact_rows_btn.setStyleSheet(get_button_style("primary"))
            self.equal_columns_btn.setStyleSheet(get_button_style("secondary"))
            self.export_btn.setStyleSheet(get_button_style("success"))
            self.toggle_filters_button.setStyleSheet(get_button_style("secondary"))
        except Exception:
            pass

        self.table_model = QtGui.QStandardItemModel(0, 0, self)

        self.proxy_model = _SourceAwareProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.modelReset.connect(self._update_count)
        self.proxy_model.layoutChanged.connect(self._update_count)
        self.proxy_model.rowsInserted.connect(self._update_count)
        self.proxy_model.rowsRemoved.connect(self._update_count)

        self.table_view = QtWidgets.QTableView()
        self.table_view.setObjectName("dataPortalListingTable")
        self.table_view.setModel(self.proxy_model)
        self.table_view.setItemDelegate(_SemanticColorDelegate(self.table_view))
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_view.setWordWrap(True)
        try:
            self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        except Exception:
            pass
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionsMovable(True)
        self.table_view.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        try:
            header = self.table_view.horizontalHeader()
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(self._on_header_context_menu)
        except Exception:
            pass
        self.table_view.verticalHeader().setVisible(False)
        try:
            self.table_view.doubleClicked.connect(self._on_table_double_clicked)
        except Exception:
            pass
        layout.addWidget(self.table_view, stretch=1)
        self.setStyleSheet(self._build_base_stylesheet())

        # Debounce filter application to keep the table responsive.
        self._filter_apply_timer = QtCore.QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.timeout.connect(self._apply_filters_now)

        self._ui_ready = True

    def _create_environment_group(self) -> QGroupBox:
        group = QGroupBox("環境選択")
        layout = QHBoxLayout(group)

        layout.addWidget(QLabel("対象環境:"))

        self.env_combo = QComboBox()
        self.env_combo.currentIndexChanged.connect(self._on_environment_changed)
        layout.addWidget(self.env_combo)
        layout.addStretch()

        self._load_environments()
        self._sync_environment_from_parent()
        return group

    def _load_environments(self) -> None:
        from ..conf.config import get_data_portal_config

        config = get_data_portal_config()
        environments = config.get_available_environments()

        if self.env_combo is None:
            return

        self.env_combo.clear()
        for env in environments:
            if env == "production":
                display_name = "本番環境"
            elif env == "test":
                display_name = "テスト環境"
            else:
                continue
            self.env_combo.addItem(display_name, env)

    def _sync_environment_from_parent(self) -> None:
        try:
            portal = self.parent()
            login_tab = getattr(portal, "login_settings_tab", None) if portal else None
            combo = getattr(login_tab, "env_combo", None) if login_tab else None
            env = combo.currentData() if combo is not None else None
        except Exception:
            env = None

        env = str(env or self._environment or "production").strip() or "production"
        self._set_env_combo(env)

    def _set_env_combo(self, env: str) -> None:
        if self.env_combo is None:
            return
        env = str(env or "production").strip() or "production"
        self._syncing_env_combo = True
        try:
            for idx in range(self.env_combo.count()):
                if self.env_combo.itemData(idx) == env:
                    self.env_combo.setCurrentIndex(idx)
                    break
        finally:
            self._syncing_env_combo = False

    def _on_environment_changed(self, _index: int) -> None:
        if not self._ui_ready or not hasattr(self, "status_label"):
            return
        if self._syncing_env_combo:
            return
        try:
            env = self.env_combo.currentData() if self.env_combo is not None else None
        except Exception:
            env = None
        env = str(env or "production").strip() or "production"

        # login設定タブにも反映
        try:
            portal = self.parent()
            login_tab = getattr(portal, "login_settings_tab", None) if portal else None
            combo = getattr(login_tab, "env_combo", None) if login_tab else None
            if combo is not None:
                for idx in range(combo.count()):
                    if combo.itemData(idx) == env:
                        combo.setCurrentIndex(idx)
                        break
        except Exception:
            pass

        self.set_environment(env)

    def _export(self, kind: str) -> None:
        kind = str(kind or "").strip().lower()
        if kind not in {"csv", "xlsx"}:
            return

        # Export current view (filtered + sorted). Hidden columns are excluded.
        visible_cols: list[int] = []
        headers: list[str] = []
        for col in range(int(self.proxy_model.columnCount())):
            try:
                if self.table_view.isColumnHidden(col):
                    continue
            except Exception:
                pass
            header = self.proxy_model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            headers.append(str(header or ""))
            visible_cols.append(int(col))

        if not visible_cols:
            return

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
            from qt_compat.widgets import QMessageBox

            QMessageBox.information(self, "出力", "出力対象の行がありません")
            return

        from qt_compat.widgets import QFileDialog, QMessageBox
        import time

        default_name = f"data_portal_listing_{time.strftime('%Y%m%d_%H%M%S')}"
        if kind == "csv":
            suggested = f"{default_name}.csv"
            path, _ = QFileDialog.getSaveFileName(self, "CSV出力", suggested, "CSV Files (*.csv)")
        else:
            suggested = f"{default_name}.xlsx"
            path, _ = QFileDialog.getSaveFileName(self, "XLSX出力", suggested, "Excel Files (*.xlsx)")

        if not path:
            return

        try:
            write_record_export(path, kind, rows, headers=headers, sheet_name="portal_listing")
            QMessageBox.information(self, "出力", f"出力しました: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "出力失敗", f"出力に失敗しました: {exc}")

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        try:
            QtCore.QTimer.singleShot(0, self._relayout_filter_fields)
            QtCore.QTimer.singleShot(120, self._relayout_filter_fields)
        except Exception:
            pass
        self._apply_initial_layout_once()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout_filter_fields()

    def _on_table_double_clicked(self, index: QtCore.QModelIndex) -> None:
        try:
            if not index.isValid():
                return
            url = str(index.data(Qt.ItemDataRole.UserRole) or "").strip()
            if not url:
                return
            QtGui.QDesktopServices.openUrl(QUrl(url))
        except Exception:
            return

    def _apply_filters_theme(self) -> None:
        try:
            bg_raw = get_color(ThemeKey.PANEL_BACKGROUND)
            border_raw = get_color(ThemeKey.PANEL_BORDER)
            text_raw = get_color(ThemeKey.TEXT_PRIMARY)

            def _css_color(value: object) -> str:
                try:
                    name = value.name()  # type: ignore[attr-defined]
                    if isinstance(name, str) and name:
                        return name
                except Exception:
                    pass
                return str(value or "")

            bg = _css_color(bg_raw)
            border = _css_color(border_raw)
            text = _css_color(text_raw)
            if not bg or not border or not text:
                return
            self.filters_group_box.setStyleSheet(
                f"background-color: {bg}; border: 1px solid {border}; border-radius: 6px; margin-top: 10px; color: {text};"
            )
            if self._filters_container is not None:
                self._filters_container.setStyleSheet(f"background-color: {bg}; color: {text};")
        except Exception:
            pass

    def refresh_theme(self) -> None:
        # Theme integration for this tab is minimal; widgets inherit palette/QSS.
        try:
            self.setStyleSheet(self._build_base_stylesheet())
            self._apply_filters_theme()
            for button, kind in (
                (getattr(self, "reload_public", None), "info"),
                (getattr(self, "reload_managed", None), "warning"),
                (getattr(self, "select_columns_btn", None), "secondary"),
                (getattr(self, "compact_rows_btn", None), "primary"),
                (getattr(self, "equal_columns_btn", None), "secondary"),
                (getattr(self, "export_btn", None), "success"),
                (getattr(self, "toggle_filters_button", None), "secondary"),
            ):
                if button is not None:
                    button.setStyleSheet(get_button_style(kind))
            if getattr(self, "table_view", None) is not None:
                self.table_view.viewport().update()
                self.table_view.update()
            self.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def refresh_public_from_disk(self) -> None:
        public = self._load_public_cache_records(force=True)
        self._rebuild_table(public_records=public, managed_records=self._managed_records)

    def refresh_managed_from_disk(self) -> None:
        """保存済みの管理CSV（ログイン設定タブ/一覧タブ共通）から読み込む。"""

        info = None
        try:
            info = find_latest_managed_csv(self._environment)
        except Exception:
            info = None

        if info is None:
            self._managed_records = []
            # ステータスは公開cache側でも更新されるため、ここでは補助表示に留める
            return

        try:
            payload = Path(info.path).read_bytes()
            records = parse_portal_csv_payload_to_records(payload)
            safe: list[dict[str, str]] = []
            for r in records:
                if isinstance(r, dict):
                    safe.append({str(k): str(v) for k, v in r.items()})
            self._managed_records = safe
        except Exception:
            self._managed_records = []

        public = self._load_public_cache_records()
        self._rebuild_table(public_records=public, managed_records=self._managed_records)

        try:
            ts = format_mtime_jst(info.mtime)
            sz = format_size(info.size_bytes)
            self.status_label.setText(f"管理CSV(保存済み): {len(self._managed_records)}件 / {ts} / {sz}（{self._environment}）")
        except Exception:
            self.status_label.setText(f"管理CSV(保存済み): {len(self._managed_records)}件（{self._environment}）")

    def refresh_managed_from_portal(self, *, user_initiated: bool = True, skip_confirm: bool = False) -> None:
        if self._is_running_under_pytest():
            # テスト環境ではネットワークアクセスを避け、保存済みCSVのみ読む
            self.refresh_managed_from_disk()
            return
        if os.environ.get("PYTEST_CURRENT_TEST") and not user_initiated and skip_confirm:
            self.status_label.setText(f"管理CSV更新をスキップしました（{self._environment}）")
            return
        if user_initiated and not skip_confirm:
            if not self._confirm_managed_refresh():
                self.status_label.setText("管理CSV更新をキャンセルしました")
                return
        # PortalClient が無い/環境が違う場合は、保存済み認証情報から自動生成する。
        if self._portal_client is None or str(getattr(self._portal_client, "environment", "")) != self._environment:
            try:
                from classes.data_portal.core.auth_manager import get_auth_manager
                from classes.data_portal.core.portal_client import PortalClient

                auth = get_auth_manager()
                cred = auth.get_credentials(self._environment)
                if cred is None:
                    message = f"⚠️ 管理CSV更新: {self._environment} の認証情報が未登録です（ログイン設定で保存してください）"
                    self.status_label.setText(message)
                    if user_initiated:
                        try:
                            QMessageBox.information(self, "管理CSV更新", message)
                        except Exception:
                            pass
                    return
                client = PortalClient(self._environment)
                client.set_credentials(cred)
                self._portal_client = client
            except Exception as exc:
                message = f"⚠️ 管理CSV更新: PortalClient生成に失敗: {exc}"
                self.status_label.setText(message)
                if user_initiated:
                    try:
                        QMessageBox.warning(self, "管理CSV更新", message)
                    except Exception:
                        pass
                return
        if self._thread is not None and self._thread.isRunning():
            self.status_label.setText("管理CSVを取得中...（処理中）")
            if user_initiated:
                try:
                    QMessageBox.information(self, "管理CSV更新", "既に取得中です。しばらくお待ちください。")
                except Exception:
                    pass
            return

        self.reload_managed.setEnabled(False)
        self.status_label.setText(f"管理CSVを取得中...（{self._environment}）")

        thread = QThread()
        worker = _ManagedFetchWorker(self._portal_client, environment=self._environment)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_managed_records_ready)
        worker.failed.connect(self._on_managed_records_failed)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.failed.connect(lambda _msg: self.reload_managed.setEnabled(True))
        worker.succeeded.connect(lambda _records: self.reload_managed.setEnabled(True))
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        thread.start()

    def _confirm_managed_refresh(self) -> bool:
        try:
            from qt_compat.widgets import QMessageBox

            message = (
                "管理CSVをポータルから取得し、保存済みCSVを更新します。\n"
                "一覧タブの表示内容も更新されます。\n\n"
                f"環境: {self._environment}"
            )
            result = QMessageBox.question(
                self,
                "管理CSV更新",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return result == QMessageBox.StandardButton.Yes
        except Exception:
            return True

    def _on_managed_records_ready(self, records: list) -> None:
        safe: list[dict[str, str]] = []
        for r in records:
            if isinstance(r, dict):
                safe.append({str(k): str(v) for k, v in r.items()})
        self._managed_records = safe

        public = self._load_public_cache_records()
        self._rebuild_table(public_records=public, managed_records=self._managed_records)
        self.status_label.setText(f"管理CSV: {len(self._managed_records)}件（{self._environment}）")

    def _on_managed_records_failed(self, message: str) -> None:
        self.status_label.setText(f"⚠️ 管理CSV取得失敗（{self._environment}）: {message}")

    def _load_public_cache_records(self, *, force: bool = False) -> list[dict]:
        if (
            not force
            and self._public_cache_loaded
            and self._public_cache_env == self._environment
            and self._public_cache_records
        ):
            return list(self._public_cache_records)

        cache_dir = get_public_data_portal_cache_dir(self._environment)
        paths = sorted(cache_dir.glob("*.json"))
        records: list[dict] = []
        for path in paths:
            try:
                import json

                with path.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                if isinstance(payload, dict):
                    # Listing互換: url を用意
                    if "url" not in payload and "detail_url" in payload:
                        payload = dict(payload)
                        payload["url"] = payload.get("detail_url")
                    # 環境フィルタ（可能な範囲でURLから判定）
                    url = str(payload.get("url") or "")
                    if self._environment == "test":
                        if url and ("test.nanonet.go.jp" not in url and "/test.nanonet.go.jp/" not in url):
                            continue
                    elif self._environment == "production":
                        if url and "test.nanonet.go.jp" in url:
                            continue
                    records.append(payload)
            except Exception:
                continue

        # 管理側ステータスを上書きしないよう、公開cache件数は補助的に表示
        if not (self._thread is not None and self._thread.isRunning()):
            self.status_label.setText(f"公開cache: {len(records)}件（{self._environment} / {cache_dir}）")
        self._public_cache_records = list(records)
        self._public_cache_env = self._environment
        self._public_cache_loaded = True
        return records

    @staticmethod
    def _join_non_empty(parts: list[str], *, sep: str = ", ") -> str:
        out: list[str] = []
        for part in parts:
            p = str(part or "").strip()
            if p and p not in out:
                out.append(p)
        return sep.join(out)

    @staticmethod
    def _normalize_list_text(value: Any, *, output_sep: str = "、") -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace(";", ",").replace("，", ",")
        parts: list[str] = []
        for block in normalized.split("\n"):
            for part in block.split(","):
                p = str(part or "").strip()
                if p:
                    parts.append(p)
        deduped: list[str] = []
        for p in parts:
            if p not in deduped:
                deduped.append(p)
        return output_sep.join(deduped)

    @staticmethod
    def _canonical_managed_label(label: str) -> str:
        text = str(label or "").strip()
        if text.startswith("【") and text.endswith("】") and len(text) > 2:
            text = text[1:-1]
        text = text.replace("（", "(").replace("）", ")")
        text = text.replace(" ", "")
        return text.lower()

    @classmethod
    def _equipment_links_to_text(cls, row: dict[str, Any]) -> str:
        links = row.get("equipment_links")
        if not isinstance(links, list):
            return ""
        chunks: list[str] = []
        for item in links:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url:
                chunks.append(f"{title} ({url})")
            elif title:
                chunks.append(title)
            elif url:
                chunks.append(url)
        return cls._join_non_empty(chunks)

    @classmethod
    def _equipment_classification_text(cls, row: dict[str, Any]) -> str:
        links = row.get("equipment_links")
        if not isinstance(links, list):
            return ""
        classes: list[str] = []
        for item in links:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            # 例: "NR-304：高性能単結晶X線自動解析装置" -> "NR-304"
            if "：" in title:
                cls_name = title.split("：", 1)[0].strip()
            elif ":" in title:
                cls_name = title.split(":", 1)[0].strip()
            else:
                cls_name = title
            if cls_name and cls_name not in classes:
                classes.append(cls_name)
        return "、".join(classes)

    @classmethod
    def _thumbnails_to_text(cls, row: dict[str, Any]) -> str:
        values = row.get("thumbnails")
        if not isinstance(values, list):
            return ""
        urls = [str(v or "").strip() for v in values if str(v or "").strip()]
        return cls._join_non_empty(urls)

    @staticmethod
    def _infer_type_for_row(row: dict[str, Any]) -> str:
        has_rde = bool(row.get("_has_rde_detail"))
        if has_rde:
            return "RDE"
        source = str(row.get("source") or "").strip().lower()
        if source in {"managed", "both"}:
            return "CSV"
        return "スクレイピング"

    @classmethod
    def _managed_fallback_value_for_label(cls, label: str, row: dict[str, Any]) -> str:
        raw = str(label or "").strip()
        if not raw:
            return ""

        by_label_key: dict[str, str] = {
            "論文等": "outcomes_publications_and_use",
            "成果発表・成果利用": "outcomes_publications_and_use",
            "関連論文": "outcomes_publications_and_use",
            "論文": "outcomes_publications_and_use",
            "dl数": "download_count",
            "ダウンロード数": "download_count",
            "データセットdoi": "doi",
            "doi": "doi",
            "データ最終更新日": "updated_date",
            "最終更新日": "updated_date",
            "データ登録日": "registered_date",
            "登録日": "registered_date",
            "ファイルサイズ": "total_file_size",
            "ファイル数": "file_count",
            "ページビュー": "page_views",
            "閲覧数": "page_views",
            "マテリアルインデックス": "material_index",
            "横断技術領域": "crosscutting_technology_area",
            "重要技術領域(主)": "key_technology_area_primary",
            "重要技術領域（主）": "key_technology_area_primary",
            "重要技術領域(副)": "key_technology_area_secondary",
            "重要技術領域（副）": "key_technology_area_secondary",
            "重要技術領域主": "key_technology_area_primary",
            "重要技術領域副": "key_technology_area_secondary",
            "キーワードタグ": "keyword_tags",
        }

        normalized = cls._canonical_managed_label(raw)
        key = by_label_key.get(normalized)
        if key:
            value = str(row.get(key) or "").strip()
            if key == "keyword_tags":
                return cls._normalize_list_text(value, output_sep="、")
            return value

        if normalized.startswith("重要技術領域"):
            if "主" in normalized:
                return str(row.get("key_technology_area_primary") or "").strip()
            if "副" in normalized:
                return str(row.get("key_technology_area_secondary") or "").strip()

        if normalized in {"装置・プロセス", "装置", "プロセス"}:
            return cls._equipment_links_to_text(row)
        if normalized in {"設備分類", "装置分類"}:
            return cls._equipment_classification_text(row)
        if normalized in {"画像", "サムネイル", "thumbnail", "thumbnails"}:
            return cls._thumbnails_to_text(row)
        if normalized in {"画像url", "画像リンク", "サムネイルurl", "画像ｕｒｌ"}:
            return cls._thumbnails_to_text(row)
        if normalized in {"タイプ"}:
            return cls._infer_type_for_row(row)

        return ""

    def _apply_managed_fallback_values(self, row: dict[str, Any]) -> None:
        if not isinstance(row, dict):
            return
        for key in list(row.keys()):
            if not str(key).startswith("managed:"):
                continue
            current = str(row.get(key) or "").strip()
            if current and current.lower() not in {"-", "―", "nan", "none", "null"}:
                # キーワードタグのみ表示形式を統一（「、」区切り）
                label = str(key).replace("managed:", "", 1).strip()
                if self._canonical_managed_label(label) in {"キーワードタグ"}:
                    normalized_tags = self._normalize_list_text(current, output_sep="、")
                    if normalized_tags:
                        row[key] = normalized_tags
                continue
            label = str(key).replace("managed:", "", 1).strip()
            fallback = self._managed_fallback_value_for_label(label, row)
            if fallback:
                row[key] = fallback

    @classmethod
    def _hydrate_managed_fallback_columns(cls, rows: list[dict[str, Any]], managed_cols: list[_ColumnDef]) -> None:
        if not rows or not managed_cols:
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            for cdef in managed_cols:
                key = str(getattr(cdef, "key", "") or "").strip()
                if not key.startswith("managed:"):
                    continue
                current = str(row.get(key) or "").strip()
                if current and current.lower() not in {"-", "―", "nan", "none", "null"}:
                    # 既存値がある場合はキーワードタグの表記のみ整える
                    label = str(key).replace("managed:", "", 1).strip()
                    if cls._canonical_managed_label(label) == "キーワードタグ":
                        normalized_tags = cls._normalize_list_text(current, output_sep="、")
                        if normalized_tags:
                            row[key] = normalized_tags
                    continue

                label = str(getattr(cdef, "label", "") or "").strip()
                fallback = cls._managed_fallback_value_for_label(label, row)
                if fallback:
                    row[key] = fallback

    def _rebuild_table(self, *, public_records: list[dict], managed_records: list[dict[str, str]]) -> None:
        result = merge_public_and_managed(
            public_records,
            managed_records,
            managed_code_getter=extract_managed_code,
            managed_dataset_id_getter=extract_managed_dataset_id,
        )

        rows = result.rows

        # Collapse managed suffix columns (e.g. 管理:装置1..5, 管理:プロセス1..5) into a single column.
        # This mutates rows in-place and returns the member keys to suppress.
        suppressed_managed_keys = add_grouped_suffix_columns(rows)

        # managed:* 列でCSV値が空の場合、スクレイピング/RDE由来の正規化済み値で補完する。
        try:
            for row in rows:
                self._apply_managed_fallback_values(row)
        except Exception:
            pass

        # Columns already mapped into fixed keys should not be shown as redundant managed:* columns.
        # (These are the most common overlaps between managed CSV and public cache.)
        suppressed_managed_keys = set(suppressed_managed_keys or set())
        suppressed_managed_keys.update(
            {
                "managed:機関",
                "managed:実施機関",
                "managed:管理コード",
                "managed:データセットID",
                "managed:課題番号",
                "managed:登録日",
                "managed:開設日時",
                "managed:エンバーゴ解除日",
                "managed:エンバーゴ期間終了日",
                "managed:ライセンス",
                "managed:ライセンスレベル",
                "managed:キーワードタグ",
                "managed:タグ",
                "managed:タグ (2)",
                "managed:タグ(2)",
                "managed:データ数",
                "managed:データタイル数",
                "managed:URL",
                "managed:リンク",
                "managed:タイトル",
                "managed:サブタイトル",
                "managed:データセット名",
                "managed:課題名",
                "managed:要約",
                "managed:このバージョンでの閲覧数",
                "managed:ステータス",
                "managed:状態",
                "managed:公開状況",
            }
        )

        # Build columns (fixed + CSV-derived)
        fixed = [
            _ColumnDef("source", "範囲", preview_limit=16, default_visible=False),
            _ColumnDef("code", "code", preview_limit=64, default_visible=True),
            _ColumnDef("dataset_name", "データセット名", preview_limit=180, default_visible=True),
            _ColumnDef("project_number", "課題番号", preview_limit=120, default_visible=True),
            _ColumnDef("project_title", "課題名", preview_limit=180, default_visible=True),
            _ColumnDef("dataset_registrant", "登録者", preview_limit=160, default_visible=True),
            _ColumnDef("organization", "実施機関", preview_limit=120, default_visible=True),
            _ColumnDef("dataset_manager", "データセットにおける管理者", preview_limit=160, default_visible=True),
            _ColumnDef("opened_date", "開設日", preview_limit=64, default_visible=False),
            _ColumnDef("registered_date", "登録日", preview_limit=64, default_visible=True),
            _ColumnDef("embargo_release_date", "エンバーゴ解除日", preview_limit=64, default_visible=False),
            _ColumnDef("data_tile_count", "データタイル数", preview_limit=80, default_visible=False),
            _ColumnDef("url", "URL", preview_limit=220, default_visible=False),
            _ColumnDef("license", "ライセンス", preview_limit=120, default_visible=False),
            _ColumnDef("keyword_tags", "キーワードタグ", preview_limit=160, default_visible=False),
            _ColumnDef("summary", "概要", preview_limit=220, default_visible=False),
        ]

        managed_keys: set[str] = set()
        for r in rows:
            for k in r.keys():
                if k.startswith("managed:"):
                    managed_keys.add(k)

        def _managed_label_from_key(raw_key: str) -> str:
            base = str(raw_key).replace("managed:", "")
            return f"【{base}】"

        managed_cols = [
            _ColumnDef(k, _managed_label_from_key(k), preview_limit=140, default_visible=False)
            for k in sorted(managed_keys)
            if k not in (suppressed_managed_keys or set())
        ]

        # 公開-only行でも managed:* 列（【】列）が表示される場合、
        # キー欠落時にスクレイピング/RDE由来の正規化値を注入して空欄を減らす。
        try:
            self._hydrate_managed_fallback_columns(rows, managed_cols)
        except Exception:
            pass

        # Add grouped columns (created by add_grouped_suffix_columns)
        grouped_cols: list[_ColumnDef] = []
        try:
            for k in sorted({kk for r in rows for kk in r.keys() if str(kk).startswith("managed_group:")}):
                base = str(k).replace("managed_group:", "")
                grouped_cols.append(_ColumnDef(str(k), f"【{base}】", preview_limit=160, default_visible=False))
        except Exception:
            grouped_cols = []

        columns = fixed + grouped_cols + managed_cols
        if not self._columns:
            self._visible_columns = {c.key for c in columns if c.default_visible}

        self._columns = columns
        self._populate(rows)

        # Hide source column always (used for range filter)
        src_idx = self._column_index.get("source", -1)
        if src_idx >= 0:
            self.table_view.setColumnHidden(src_idx, True)
            self.proxy_model.set_source_column(src_idx)

        self._update_count()

    def _set_filters_collapsed(self, collapsed: bool) -> None:
        self._filters_collapsed = bool(collapsed)
        if self._filters_container is not None:
            self._filters_container.setVisible(not self._filters_collapsed)
        if self._filters_summary_label is not None:
            self._filters_summary_label.setVisible(self._filters_collapsed)
        if getattr(self, "toggle_filters_button", None) is not None:
            self.toggle_filters_button.setText("フィルタ表示" if self._filters_collapsed else "フィルタ最小化")
        self._update_filters_summary()

    def _toggle_filters_collapsed(self) -> None:
        self._set_filters_collapsed(not self._filters_collapsed)

    def _on_filter_scope_changed(self) -> None:
        try:
            scope = str(self.filter_scope_combo.currentData() or "all")
        except Exception:
            scope = "all"

        if scope == "all":
            self._filter_mode = "all"
            self._filter_group_kind = "fixed"
        else:
            self._filter_mode = "group"
            self._filter_group_kind = scope
        self._rebuild_filters_panel([c for c in self._columns if c.key in self._visible_columns or c.key == "source"])

    @staticmethod
    def _format_filter_label(label: str) -> str:
        text = str(label or "")
        if text.startswith("管理:"):
            inner = text.replace("管理:", "", 1)
            return f"【{inner}】"
        return text

    @staticmethod
    def _base_label(label: str) -> str:
        text = str(label or "")
        if text.startswith("【") and text.endswith("】") and len(text) > 2:
            return text[1:-1]
        return text

    def _should_format_date_column(self, cdef: _ColumnDef) -> bool:
        base = self._base_label(cdef.label)
        if cdef.key in ("registered_date", "embargo_release_date"):
            return True
        return base in {
            "登録日",
            "エンバーゴ解除日",
            "開設日",
            "開設日時",
            "データ最終更新日",
            "データ登録日",
            "最終更新日",
            "解説日時",
        }

    @staticmethod
    def _split_date_display(value: Any) -> tuple[Any, Optional[str]]:
        if not isinstance(value, str):
            return value, None
        text = value.strip()
        if not text:
            return value, None
        normalized = text.replace("T", " ")
        match = re.match(r"^(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s+(\d{1,2}:\d{2}(:\d{2})?.*)$", normalized)
        if match:
            return match.group(1), text
        return value, None

    def _relayout_filter_fields(self) -> None:
        if self._filters_layout is None or not self._filter_field_widgets:
            return

        available_w = 0
        try:
            if self._filters_container is not None:
                available_w = int(self._filters_container.width())
        except Exception:
            available_w = 0
        if available_w <= 0:
            try:
                available_w = int(self.width())
            except Exception:
                available_w = 600
        if available_w <= 1:
            try:
                QtCore.QTimer.singleShot(80, self._relayout_filter_fields)
            except Exception:
                pass
            return

        per_row = max(1, min(5, int(max(available_w, 1) // 260)))
        field_w = max(220, int(max(available_w, 1) // per_row) - 12)

        # Clear layout items without deleting widgets.
        while self._filters_layout.count():
            item = self._filters_layout.takeAt(0)
            if item is None:
                continue

        for i, (_key, field) in enumerate(self._filter_field_widgets):
            r = int(i // per_row)
            c = int(i % per_row)
            try:
                try:
                    field.setMaximumWidth(int(field_w))
                except Exception:
                    pass
                self._filters_layout.addWidget(field, r, c)
            except Exception:
                pass

    def _update_filters_summary(self) -> None:
        if self._filters_summary_label is None:
            return
        if not self._filters_collapsed:
            self._filters_summary_label.setText("")
            return

        parts: list[str] = []
        for cdef in self._columns:
            edit = self._filter_edits_by_key.get(cdef.key)
            if edit is None:
                continue
            try:
                text = str(edit.text() or "").strip()
            except Exception:
                text = ""
            if not text:
                continue
            parts.append(f"{self._format_filter_label(cdef.label)}={text}")

        self._filters_summary_label.setText(" / ".join(parts))

    def _populate(self, rows: list[dict[str, Any]]) -> None:
        try:
            from shiboken6 import isValid as _qt_is_valid  # type: ignore

            if not _qt_is_valid(self):
                return
        except Exception:
            pass

        visible_cols = [c for c in self._columns if c.key in self._visible_columns or c.key == "source"]
        self._column_index = {c.key: idx for idx, c in enumerate(visible_cols)}

        self._rebuild_filters_panel(visible_cols)

        self.table_model.clear()
        self.table_model.setColumnCount(len(visible_cols))
        self.table_model.setHorizontalHeaderLabels([c.label for c in visible_cols])

        # Keep source hidden even after rebuild
        src_idx = self._column_index.get("source", -1)
        if src_idx >= 0:
            self.table_view.setColumnHidden(src_idx, True)
            self.proxy_model.set_source_column(src_idx)

        self._pending_rows = list(rows)
        self._pending_visible_cols = list(visible_cols)
        self._pending_row_index = 0
        self._populate_token += 1
        token = self._populate_token

        QtCore.QTimer.singleShot(0, lambda: self._append_rows_batch(token))

    def _append_rows_batch(self, token: int) -> None:
        try:
            from shiboken6 import isValid as _qt_is_valid  # type: ignore

            if not _qt_is_valid(self) or not _qt_is_valid(self.table_model):
                return
        except Exception:
            pass

        if token != self._populate_token:
            return

        if not self._pending_rows:
            self._finalize_populate()
            return

        batch_size = 200
        start = self._pending_row_index
        end = min(start + batch_size, len(self._pending_rows))
        for row in self._pending_rows[start:end]:
            items = self._build_items_for_row(row, self._pending_visible_cols)
            self.table_model.appendRow(items)

        self._pending_row_index = end
        if end < len(self._pending_rows):
            QtCore.QTimer.singleShot(0, lambda: self._append_rows_batch(token))
            return

        self._finalize_populate()

    def _finalize_populate(self) -> None:
        try:
            self.table_view.resizeRowsToContents()
        except Exception:
            pass

        if self._display_mode != "default":
            self._apply_display_mode(self._display_mode, force=True)

        self._apply_initial_layout_once()
        self._schedule_apply_filters()

    def _build_items_for_row(self, row: dict[str, Any], visible_cols: list[_ColumnDef]) -> list[QtGui.QStandardItem]:
        items: list[QtGui.QStandardItem] = []

        for col in visible_cols:
            val = row.get(col.key, "")

            # Render grouped/CSV list-like values with line breaks to avoid horizontal scroll.
            try:
                if isinstance(val, str):
                    if str(col.key).startswith("managed_group:"):
                        parts = [p.strip() for p in val.replace("\r\n", "\n").replace("\r", "\n").split(",")]
                        parts = [p for p in parts if p]
                        if len(parts) >= 2 and "\n" not in val:
                            val = "\n".join([f"・{p}" for p in parts])
                    managed_label = ""
                    if str(col.key).startswith("managed:"):
                        managed_label = str(col.key).replace("managed:", "", 1).strip()
                    if col.key in ("keyword_tags",) or self._canonical_managed_label(managed_label) == "キーワードタグ":
                        normalized_tags = self._normalize_list_text(val, output_sep="、")
                        if normalized_tags:
                            val = normalized_tags
            except Exception:
                pass

            display_val = val
            time_tooltip = None
            if self._should_format_date_column(col):
                display_val, time_tooltip = self._split_date_display(val)

            display, tooltip = prepare_display_value(display_val, col.preview_limit)
            if time_tooltip:
                tooltip = time_tooltip
            item = QtGui.QStandardItem(display)
            item.setEditable(False)

            # Keep raw value for exports (and other non-truncated uses).
            try:
                item.setData(val, int(Qt.ItemDataRole.UserRole) + 1)
            except Exception:
                pass

            # Dataset name behaves like a link (opens row URL) even when URL column is hidden.
            if col.key == "dataset_name":
                try:
                    url = str(row.get("url") or "").strip()
                    if url:
                        item.setData(url, Qt.ItemDataRole.UserRole)
                        f = item.font()
                        f.setUnderline(True)
                        item.setFont(f)
                        item.setData("link", _ITEM_THEME_FOREGROUND_ROLE)
                        extra = f"URL: {url}"
                        tooltip = (tooltip + "\n\n" if tooltip else "") + extra
                except Exception:
                    pass

            try:
                origin = (row.get("_cell_origin") or {}).get(col.key)
                diff = (row.get("_cell_diff") or {}).get(col.key)
                if diff:
                    item.setData("info", _ITEM_THEME_BACKGROUND_ROLE)
                    note = f"公開: {diff.get('public','')}\n管理: {diff.get('managed','')}"
                    tooltip = (tooltip + "\n\n" if tooltip else "") + note
                elif origin == "public":
                    item.setData("warning", _ITEM_THEME_BACKGROUND_ROLE)
                    note = "管理CSVに値が無いため公開cache由来です"
                    tooltip = (tooltip + "\n\n" if tooltip else "") + note
            except Exception:
                pass

            if tooltip and tooltip != display:
                item.setToolTip(tooltip)
            items.append(item)

        return items

    def _apply_initial_layout_once(self) -> None:
        if self._did_apply_initial_layout:
            return
        if self.proxy_model.columnCount() <= 0:
            return
        self._did_apply_initial_layout = True
        self._apply_display_mode("equal", force=True)
        self._apply_display_mode("compact", force=True)

    def _rebuild_filters_panel(self, visible_cols: list[_ColumnDef]) -> None:
        if self._filters_container is None or self._filters_layout is None:
            return

        # Keep text values by key before rebuild
        existing_text_by_key: dict[str, str] = {}
        for key, edit in (self._filter_edits_by_key or {}).items():
            try:
                existing_text_by_key[key] = str(edit.text() or "")
            except Exception:
                continue

        # Clear layout & existing widgets (delete old fields)
        while self._filters_layout.count():
            item = self._filters_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)

        for _k, w in (self._filter_field_widgets or []):
            try:
                w.setParent(None)
            except Exception:
                pass

        self._filter_field_widgets = []
        self._filter_edits_by_key = {}

        # Build per-column filter inputs for currently visible columns.
        cols_all = [c for c in (visible_cols or []) if c.key != "source"]
        if not cols_all:
            return

        if self._filter_mode == "group":
            kind = str(self._filter_group_kind or "fixed")
            if kind == "fixed":
                cols = [c for c in cols_all if not (c.key.startswith("managed:") or c.key.startswith("managed_group:"))]
            elif kind == "managed_group":
                cols = [c for c in cols_all if c.key.startswith("managed_group:")]
            else:
                cols = [c for c in cols_all if c.key.startswith("managed:")]
        else:
            cols = cols_all

        if not cols:
            return

        for cdef in cols:
            field = QWidget(self._filters_container)
            try:
                field.setMaximumWidth(300)
            except Exception:
                pass

            h = QHBoxLayout(field)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)

            label = QLabel(self._format_filter_label(cdef.label), field)
            try:
                label.setMinimumWidth(80)
                label.setMaximumWidth(130)
            except Exception:
                pass
            edit = QLineEdit(field)
            edit.setPlaceholderText("絞り込み")
            edit.setText(existing_text_by_key.get(cdef.key, ""))
            edit.textChanged.connect(lambda _t, _key=cdef.key: self._schedule_apply_filters())

            h.addWidget(label)
            h.addWidget(edit, 1)

            self._filter_edits_by_key[cdef.key] = edit
            self._filter_field_widgets.append((cdef.key, field))

        self._relayout_filter_fields()

    def _schedule_apply_filters(self) -> None:
        if self._filter_apply_timer is None:
            self._apply_filters_now()
            return
        try:
            self._filter_apply_timer.start(150)
        except Exception:
            self._apply_filters_now()

    def _apply_filters_now(self) -> None:
        # Build filters dict by *source model* column indices.
        filters_by_index: dict[int, str] = {}
        for key, edit in (self._filter_edits_by_key or {}).items():
            try:
                text = str(edit.text() or "").strip()
            except Exception:
                continue
            if not text:
                continue
            idx = self._column_index.get(key, -1)
            if idx >= 0:
                filters_by_index[int(idx)] = text
        try:
            self.proxy_model.set_column_filters(filters_by_index)
        except Exception:
            pass
        self._update_filters_summary()
        self._update_count()

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    def _apply_display_mode(self, mode: str, *, force: bool = False) -> None:
        mode = str(mode or "").strip().lower()
        if mode not in {"compact", "equal", "default"}:
            mode = "default"
        if mode == self._display_mode and not force:
            return
        self._display_mode = mode

        try:
            if mode == "compact":
                self.table_view.setWordWrap(False)
                self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
                row_h = int(self.table_view.fontMetrics().height() * 1.6)
                if row_h > 0:
                    self.table_view.verticalHeader().setDefaultSectionSize(row_h)
                    try:
                        model = self.table_view.model()
                        if model is not None:
                            for r in range(int(model.rowCount())):
                                self.table_view.setRowHeight(r, row_h)
                    except Exception:
                        pass
            elif mode == "equal":
                self.table_view.setWordWrap(True)
                self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self._apply_equal_column_widths()
            else:
                self.table_view.setWordWrap(True)
                self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        except Exception:
            pass

        try:
            if mode == "compact":
                return
            self.table_view.resizeRowsToContents()
        except Exception:
            pass

    def _toggle_compact_rows(self) -> None:
        current = str(getattr(self, "_display_mode", "default")).strip().lower()
        target = "default" if current == "compact" else "compact"
        self._apply_display_mode(target)

    def _apply_equal_column_widths(self) -> None:
        try:
            header = self.table_view.horizontalHeader()
            count = int(self.proxy_model.columnCount())
            if count <= 0:
                return
            available = int(self.table_view.viewport().width())
            if available <= 0:
                return
            per_col = max(80, int(available // max(count, 1)))
            for col in range(count):
                header.resizeSection(col, per_col)
        except Exception:
            pass

    def _on_header_context_menu(self, pos: QtCore.QPoint) -> None:
        try:
            header = self.table_view.horizontalHeader()
            col = int(header.logicalIndexAt(pos))
        except Exception:
            return
        if col < 0:
            return

        key = self._column_key_for_index(col)
        if not key or key == "source":
            return

        menu = QMenu(self)
        action_hide = menu.addAction("この列を非表示")
        chosen = menu.exec(header.mapToGlobal(pos))
        if chosen == action_hide:
            self._hide_column_by_index(col)

    def _column_key_for_index(self, index: int) -> Optional[str]:
        for key, idx in (self._column_index or {}).items():
            if int(idx) == int(index):
                return key
        return None

    def _hide_column_by_index(self, index: int) -> None:
        key = self._column_key_for_index(index)
        if not key or key == "source":
            return
        if key in self._visible_columns:
            self._visible_columns.discard(key)
            public = self._load_public_cache_records()
            self._rebuild_table(public_records=public, managed_records=self._managed_records)

    def _on_range_changed(self) -> None:
        mode = str(self.range_combo.currentData() or "all")
        self.proxy_model.set_range_mode(mode)
        if mode == "managed" and not self._managed_records:
            self.status_label.setText("⚠️ 管理CSVが未取得です（ログイン後に『管理CSV更新』を実行してください）")
        self._update_count()

    def _on_select_columns(self) -> None:
        dialog = _ColumnSelectDialog(self._columns, self._visible_columns, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_keys()
        # Always keep `source` present for filtering (hidden in view)
        selected.add("source")
        self._visible_columns = selected

        public = self._load_public_cache_records()
        self._rebuild_table(public_records=public, managed_records=self._managed_records)

    def _update_count(self) -> None:
        total = self.table_model.rowCount()
        visible = self.proxy_model.rowCount()
        if total == visible:
            self.count_label.setText(f"{total}件")
        else:
            self.count_label.setText(f"{visible}/{total}件")
