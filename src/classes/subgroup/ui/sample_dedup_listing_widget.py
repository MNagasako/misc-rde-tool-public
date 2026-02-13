"""Sample dedup listing widget."""

from __future__ import annotations

import os
import time
import webbrowser
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from qt_compat.core import Qt, QThread, Signal
from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCompleter,
    QSpinBox,
    QHeaderView,
    QMenu,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QScrollArea,
    QSizePolicy,
    QMessageBox,
    QApplication,
    QCheckBox,
)

from PySide6.QtCore import (
    QObject,
    QAbstractTableModel,
    QModelIndex,
    QSize,
    QSortFilterProxyModel,
    QTimer,
    QAbstractProxyModel,
    QEvent,
    QPoint,
    QRect,
)
from PySide6.QtGui import QBrush, QCursor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QTableView, QStyledItemDelegate, QToolTip, QStyle, QStyleOptionButton, QStyleOptionViewItem

from config.site_rde import URLS

from classes.subgroup.util.sample_dedup_table_records import (
    SampleDedupColumn,
    build_sample_dedup_rows_from_files,
    fetch_samples_for_subgroups,
    get_default_columns,
    compute_sample_listing_sources_signature,
    extract_cached_rows,
    is_sample_listing_cache_fresh,
    load_sample_listing_cache,
    merge_rows_into_cache,
    save_sample_listing_cache,
    update_sample_listing_cache_for_subgroups,
)
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color, get_qcolor
from classes.utils.button_styles import get_button_style

from classes.subgroup.ui.sample_entry_sample_relink_dialog import SampleEntrySampleRelinkDialog
from classes.subgroup.ui.sample_edit_dialog import SampleEditDialog
from classes.managers.log_manager import get_logger
from classes.dataset.ui.spinner_overlay import SpinnerOverlay


# NOTE: This app uses LogManager-managed loggers (propagate=False). If we use a
# module logger here, logs can disappear depending on global handler setup.
logger = get_logger("RDE_WebView")


class SampleDedupTableView(QTableView):
    """QTableView that exposes mouse click position for robust hit testing."""

    cell_clicked_with_pos = Signal(object, object)
    cell_double_clicked_with_pos = Signal(object, object)
    cell_hovered_with_pos = Signal(object, object)
    viewport_left = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._relink_diag_last_info_at: float = 0.0
        self._last_viewport_click_pos: QPoint | None = None
        self._last_viewport_click_at: float = 0.0

    def _event_pos(self, event: object) -> QPoint:
        try:
            # QMouseEvent (Qt6): position() -> QPointF
            return event.position().toPoint()  # type: ignore[attr-defined]
        except Exception:
            try:
                # Older API: pos() -> QPoint
                return event.pos()  # type: ignore[attr-defined]
            except Exception:
                return QPoint()

    def viewportEvent(self, event):  # type: ignore[override]
        """Intercept mouse events coming from the viewport.

        NOTE: In Qt, mouse events for item views are delivered to the viewport widget,
        so overriding mouseReleaseEvent on QTableView itself is not reliable.
        """
        try:
            et = event.type()
        except Exception:
            return super().viewportEvent(event)

        if et == QEvent.MouseButtonRelease:
            try:
                pos = self._event_pos(event)
                idx = self.indexAt(pos)
                try:
                    self._last_viewport_click_pos = pos
                    self._last_viewport_click_at = time.monotonic()
                except Exception:
                    pass
            except Exception:
                pos = QPoint()
                idx = QModelIndex()

            result = super().viewportEvent(event)

            try:
                # Emit a throttled INFO log so we can confirm clicks reach the view
                # even when DEBUG logs are filtered out.
                try:
                    now = time.monotonic()
                    if (now - float(getattr(self, "_relink_diag_last_info_at", 0.0))) >= 1.0:
                        self._relink_diag_last_info_at = now
                        logger.info(
                            "[RELINK] click received pos=(%s,%s) valid=%s row=%s col=%s",
                            int(pos.x()),
                            int(pos.y()),
                            bool(getattr(idx, "isValid", lambda: False)()),
                            int(idx.row()) if getattr(idx, "isValid", lambda: False)() else -1,
                            int(idx.column()) if getattr(idx, "isValid", lambda: False)() else -1,
                        )
                except Exception:
                    pass
                try:
                    logger.debug(
                        "[RELINK] viewport mouseRelease pos=(%s,%s) valid=%s row=%s col=%s",
                        int(pos.x()),
                        int(pos.y()),
                        bool(getattr(idx, "isValid", lambda: False)()),
                        int(idx.row()) if getattr(idx, "isValid", lambda: False)() else -1,
                        int(idx.column()) if getattr(idx, "isValid", lambda: False)() else -1,
                    )
                except Exception:
                    pass
                self.cell_clicked_with_pos.emit(idx, pos)
            except Exception:
                pass
            return result

        if et == QEvent.MouseButtonDblClick:
            try:
                pos = self._event_pos(event)
                idx = self.indexAt(pos)
                try:
                    self._last_viewport_click_pos = pos
                    self._last_viewport_click_at = time.monotonic()
                except Exception:
                    pass
            except Exception:
                pos = QPoint()
                idx = QModelIndex()

            result = super().viewportEvent(event)

            try:
                try:
                    logger.debug(
                        "[RELINK] viewport mouseDblClick pos=(%s,%s) valid=%s row=%s col=%s",
                        int(pos.x()),
                        int(pos.y()),
                        bool(getattr(idx, "isValid", lambda: False)()),
                        int(idx.row()) if getattr(idx, "isValid", lambda: False)() else -1,
                        int(idx.column()) if getattr(idx, "isValid", lambda: False)() else -1,
                    )
                except Exception:
                    pass
                self.cell_double_clicked_with_pos.emit(idx, pos)
            except Exception:
                pass
            return result

        if et in {QEvent.MouseMove, QEvent.HoverMove}:
            try:
                pos = self._event_pos(event)
                idx = self.indexAt(pos)
            except Exception:
                pos = QPoint()
                idx = QModelIndex()

            # Optional diagnostics (guarded): confirm hover events reach the view.
            try:
                if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                    now = time.monotonic()
                    if (now - float(getattr(self, "_hover_diag_last_info_at", 0.0))) >= 1.0:
                        self._hover_diag_last_info_at = now
                        logger.info(
                            "[HOVER] viewport %s pos=(%s,%s) valid=%s row=%s col=%s",
                            "HoverMove" if et == QEvent.HoverMove else "MouseMove",
                            int(pos.x()),
                            int(pos.y()),
                            bool(getattr(idx, "isValid", lambda: False)()),
                            int(idx.row()) if getattr(idx, "isValid", lambda: False)() else -1,
                            int(idx.column()) if getattr(idx, "isValid", lambda: False)() else -1,
                        )
            except Exception:
                pass

            result = super().viewportEvent(event)
            try:
                self.cell_hovered_with_pos.emit(idx, pos)
            except Exception:
                pass
            return result

        if et in {QEvent.Leave, QEvent.HoverLeave}:
            result = super().viewportEvent(event)
            try:
                self.viewport_left.emit()
            except Exception:
                pass
            return result

        return super().viewportEvent(event)


_SAMPLE_LISTING_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6h


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _row_key(row: Dict[str, Any]) -> str:
    subgroup_id = _safe_str(row.get("subgroup_id")).strip()
    sample_id = _safe_str(row.get("sample_id")).strip()
    # subgroup row without sample_id
    return f"{subgroup_id}::{sample_id}"


@dataclass(frozen=True)
class _PreFilterState:
    role_filter: str
    subgroup_id: str
    grant_number: str


class SampleDedupTableModel(QAbstractTableModel):
    def __init__(self, columns: List[SampleDedupColumn], rows: List[Dict[str, Any]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._columns = columns
        self._rows = rows

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_rows(self) -> List[Dict[str, Any]]:
        return self._rows

    def update_rows_partially(self, new_rows: List[Dict[str, Any]]) -> None:
        """Update rows in-place when possible to keep UI responsive."""
        if not isinstance(new_rows, list):
            return

        old_rows = self._rows
        if not isinstance(old_rows, list) or not old_rows:
            self.set_rows([r for r in new_rows if isinstance(r, dict)])
            return

        old_index_by_key: Dict[str, int] = {}
        for idx, row in enumerate(old_rows):
            if not isinstance(row, dict):
                continue
            old_index_by_key[_row_key(row)] = idx

        # If sizes are wildly different, a reset is cheaper.
        if abs(len(new_rows) - len(old_rows)) > max(200, len(old_rows) // 3):
            self.set_rows([r for r in new_rows if isinstance(r, dict)])
            return

        # Apply updates
        for new_row in new_rows:
            if not isinstance(new_row, dict):
                continue
            key = _row_key(new_row)
            if key not in old_index_by_key:
                continue
            row_index = old_index_by_key[key]
            old_row = old_rows[row_index]
            if not isinstance(old_row, dict):
                continue
            changed_cols: List[int] = []
            for col_index, col in enumerate(self._columns):
                if col.key not in new_row:
                    continue
                new_val = new_row.get(col.key)
                if old_row.get(col.key) == new_val:
                    continue
                old_row[col.key] = new_val
                changed_cols.append(col_index)
            for col_index in changed_cols:
                try:
                    top_left = self.index(row_index, col_index)
                    self.dataChanged.emit(top_left, top_left)
                except Exception:
                    continue

    def set_columns(self, columns: List[SampleDedupColumn]) -> None:
        self.beginResetModel()
        self._columns = columns
        self.endResetModel()

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
            value = raw_value
            if col.key == "sample_edit":
                return "試料編集" if _safe_str(row.get("sample_id")).strip() else ""
            if isinstance(value, bool):
                return "True" if value else "False"
            return "" if value is None else str(value)

        if role == Qt.ToolTipRole:
            # Show the corresponding UUID on name columns.
            if col.key == "subgroup_name":
                sid = _safe_str(row.get("subgroup_id")).strip()
                return sid or None
            if col.key == "dataset_names":
                dids = _safe_str(row.get("dataset_ids")).strip()
                return dids or None
            if col.key == "data_entry_names":
                eids = _safe_str(row.get("data_entry_ids")).strip()
                return eids or None
            if col.key == "sample_name":
                sid = _safe_str(row.get("sample_id")).strip()
                return sid or None
            return None

        if role == Qt.UserRole:
            # UUID columns open the corresponding entry page in browser.
            if col.key == "subgroup_id":
                subgroup_id = _safe_str(raw_value).strip()
                return f"https://rde.nims.go.jp/rde/datasets/groups/{subgroup_id}" if subgroup_id else ""
            if col.key == "dataset_ids":
                dataset_ids = [x.strip() for x in _safe_str(raw_value).splitlines() if x.strip()]
                if not dataset_ids:
                    return []
                tmpl = URLS["web"].get("dataset_page", "https://rde.nims.go.jp/rde/datasets/{id}")
                return [tmpl.format(id=did) for did in dataset_ids if did]
            if col.key == "data_entry_ids":
                entry_ids = [x.strip() for x in _safe_str(raw_value).splitlines() if x.strip()]
                if not entry_ids:
                    return []
                tmpl = URLS["web"].get("data_detail_page", "https://rde.nims.go.jp/rde/datasets/data/{id}")
                return [tmpl.format(id=eid) for eid in entry_ids if eid]
            if col.key == "sample_id":
                sample_id = _safe_str(raw_value).strip()
                return f"https://rde-material.nims.go.jp/samples/samples/{sample_id}" if sample_id else ""
            if col.key == "sample_edit":
                # Provide enough context to purge invalid entries (subgroup + sample).
                return {
                    "sample_id": _safe_str(row.get("sample_id")).strip(),
                    "subgroup_id": _safe_str(row.get("subgroup_id")).strip(),
                }
            if col.key == "tile_dataset_grant":
                links = row.get("tile_dataset_grant_links")
                if isinstance(links, list) and links:
                    return links

                # Fallback for older caches / partial rows:
                # derive per-line link mapping from the UUID columns.
                entry_ids = [x.strip() for x in _safe_str(row.get("data_entry_ids")).splitlines() if x.strip()]
                dataset_ids = [x.strip() for x in _safe_str(row.get("dataset_ids")).splitlines() if x.strip()]
                n = max(len(entry_ids), len(dataset_ids))
                if n <= 0:
                    return []
                derived: List[Dict[str, str]] = []
                for i in range(n):
                    derived.append(
                        {
                            "data_entry_id": entry_ids[i] if i < len(entry_ids) else "",
                            "dataset_id": dataset_ids[i] if i < len(dataset_ids) else "",
                        }
                    )
                return derived
            return None

        if role == Qt.ForegroundRole:
            # Render UUID cells as links.
            if col.key in {"subgroup_id", "dataset_ids", "data_entry_ids", "sample_id"}:
                url = self.data(index, Qt.UserRole)
                if (isinstance(url, str) and url) or (isinstance(url, list) and any(isinstance(x, str) and x for x in url)):
                    return QBrush(get_color(ThemeKey.TEXT_LINK))

        if role == Qt.FontRole:
            if col.key in {"subgroup_id", "dataset_ids", "data_entry_ids", "sample_id"}:
                url = self.data(index, Qt.UserRole)
                if (isinstance(url, str) and url) or (isinstance(url, list) and any(isinstance(x, str) and x for x in url)):
                    f = QFont()
                    f.setUnderline(True)
                    return f

        if role == Qt.TextAlignmentRole:
            if col.key in {"data_entry_count", "dataset_count", "grant_count", "subgroup_dataset_count"}:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


class SampleDedupFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._column_filters: Dict[int, str] = {}
        self._numeric_ranges: Dict[int, tuple[Optional[int], Optional[int]]] = {}
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_column_filter(self, column: int, text: str) -> None:
        text = "" if text is None else str(text)
        if self._column_filters.get(column) == text:
            return
        if text:
            self._column_filters[column] = text
        elif column in self._column_filters:
            self._column_filters.pop(column, None)
        self.invalidateFilter()

    def set_numeric_range(self, column: int, min_value: Optional[int], max_value: Optional[int]) -> None:
        col = int(column)
        mn = min_value if min_value is None else int(min_value)
        mx = max_value if max_value is None else int(max_value)
        if mn is None and mx is None:
            if col in self._numeric_ranges:
                self._numeric_ranges.pop(col, None)
                self.invalidateFilter()
            return
        self._numeric_ranges[col] = (mn, mx)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        source_model = self.sourceModel()
        if source_model is None:
            return True

        for col, (mn, mx) in (self._numeric_ranges or {}).items():
            if mn is None and mx is None:
                continue
            if col < 0 or col >= source_model.columnCount():
                continue
            idx = source_model.index(source_row, col, source_parent)
            data = source_model.data(idx, Qt.DisplayRole)
            try:
                n = int(str(data))
            except Exception:
                return False
            if mn is not None and n < mn:
                return False
            if mx is not None and n > mx:
                return False

        for col, pattern in self._column_filters.items():
            if not pattern:
                continue
            index = source_model.index(source_row, col, source_parent)
            data = source_model.data(index, Qt.DisplayRole)
            if data is None:
                return False
            if pattern.lower() not in str(data).lower():
                return False
        return True


class PaginationProxyModel(QAbstractProxyModel):
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._page_size = 100  # 0 = all
        self._page = 1  # 1-based
        self._source_model = None

    def setSourceModel(self, source_model):  # noqa: N802
        # Disconnect old
        try:
            old = self._source_model
            if old is not None:
                old.modelReset.disconnect(self._on_source_changed)
                old.rowsInserted.disconnect(self._on_source_changed)
                old.rowsRemoved.disconnect(self._on_source_changed)
                old.layoutChanged.disconnect(self._on_source_changed)
                old.dataChanged.disconnect(self._on_source_data_changed)
        except Exception:
            pass

        super().setSourceModel(source_model)
        self._source_model = source_model

        # Connect new
        try:
            if source_model is not None:
                source_model.modelReset.connect(self._on_source_changed)
                source_model.rowsInserted.connect(self._on_source_changed)
                source_model.rowsRemoved.connect(self._on_source_changed)
                source_model.layoutChanged.connect(self._on_source_changed)
                source_model.dataChanged.connect(self._on_source_data_changed)
        except Exception:
            pass

        # Ensure views re-query rowCount/indices.
        try:
            self.beginResetModel()
            self.endResetModel()
        except Exception:
            pass

    def _on_source_changed(self, *args):
        try:
            self.beginResetModel()
            self.endResetModel()
        except Exception:
            # As a fallback, emit a broad layout change.
            try:
                self.layoutChanged.emit()
            except Exception:
                pass

    def _on_source_data_changed(self, *_args):
        # Keep it simple: data changes are cheap enough to reset for this table size.
        self._on_source_changed()

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

    def _normalize_page(self) -> None:
        max_page = self.total_pages()
        if self._page > max_page:
            self._page = max_page
        if self._page < 1:
            self._page = 1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        self._normalize_page()
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


class MultiLineCompositeLinkDelegate(QStyledItemDelegate):
    """Paint tile/dataset/grant with different theme colors."""

    _SEP = " - "

    def _split_line(self, line: str) -> tuple[str, str, str]:
        try:
            parts = line.split(self._SEP)
            if len(parts) >= 3:
                tile = parts[0]
                dataset = parts[1]
                grant = self._SEP.join(parts[2:])
                return tile, dataset, grant
            if len(parts) == 2:
                return parts[0], parts[1], ""
            return line, "", ""
        except Exception:
            return line, "", ""

    def sizeHint(self, option, index):  # noqa: N802
        try:
            text = str(index.data(Qt.DisplayRole) or "")
            lines = [x for x in text.splitlines() if x] if text else []
            n = max(1, len(lines))
            fm = option.fontMetrics
            h = int(fm.height()) * n + 4
            return QSize(max(1, int(option.rect.width())), max(1, h))
        except Exception:
            return super().sizeHint(option, index)

    def helpEvent(self, event, view, option, index):  # noqa: N802
        # NOTE: Browser-link behavior for this column is intentionally removed.
        return super().helpEvent(event, view, option, index)

    def paint(self, painter, option, index):  # noqa: N802
        # Custom paint only for our composite column.
        text = str(index.data(Qt.DisplayRole) or "")
        if not text:
            return super().paint(painter, option, index)

        # Keep line splitting consistent with hover hit testing (which ignores empty lines).
        lines = [x for x in text.splitlines() if x]
        if not lines:
            return super().paint(painter, option, index)

        # Diagnostics: confirm paint is running at all.
        try:
            if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                now = time.monotonic()
                last_at = float(getattr(self, "_paint_any_last_info_at", 0.0))
                if (now - last_at) >= 2.0:
                    setattr(self, "_paint_any_last_info_at", now)
                    logger.info(
                        "[DELEGATE-PAINT] composite(any) row=%s col=%s state=%s",
                        int(index.row()),
                        int(index.column()),
                        str(getattr(option, "state", "?")),
                    )
        except Exception:
            pass

        # Draw item background/selection/focus ONLY.
        # NOTE: Do NOT call super().paint() here.
        # QStyledItemDelegate.paint() calls initStyleOption() internally and will
        # overwrite opt.text with DisplayRole again, causing double text rendering
        # (default + custom).
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        try:
            # We paint per-line hover ourselves.
            opt.state &= ~QStyle.State_MouseOver
        except Exception:
            pass
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        # Visual paint probe for environment-specific debugging.
        # If this tint does not appear, this delegate's paint() is not being used.
        try:
            if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_PAINT_PROBE"):
                probe_bg = get_qcolor(ThemeKey.TEXT_WARNING)
                try:
                    probe_bg.setAlpha(60)
                except Exception:
                    pass
                painter.save()
                painter.fillRect(option.rect, QBrush(probe_bg))
                try:
                    painter.setPen(QPen(get_qcolor(ThemeKey.TEXT_ERROR), 2))
                    painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
                except Exception:
                    pass
                painter.restore()
        except Exception:
            pass

        try:
            rect = option.rect
            fm = option.fontMetrics
            line_h = max(1, int(fm.height()))

            selected = bool(option.state & QStyle.State_Selected)

            # Prefer delegate-local state (always accessible), then fall back to widget/viewport properties.
            hover = getattr(self, "_hover_link_state", None)

            view = option.widget

            def _normalize_hover_state(value: object) -> object:
                # Qt property can come back as a wrapper (e.g., QVariant-like) depending on binding.
                try:
                    if value is not None and hasattr(value, "value") and callable(value.value):
                        value = value.value()  # type: ignore[assignment]
                except Exception:
                    pass
                return value

            def _read_hover_state(obj: object) -> object:
                try:
                    # Prefer Qt property (stored in C++ object, stable across wrappers).
                    v = obj.property("_hover_link_state")  # type: ignore[attr-defined]
                    if v is not None:
                        return _normalize_hover_state(v)
                except Exception:
                    pass
                try:
                    return _normalize_hover_state(getattr(obj, "_hover_link_state", None))
                except Exception:
                    return None

            # Hover state is tracked on the viewport (mouse events are delivered there).
            # Keep backward compatibility by also checking the view and its parent.
            if hover is None:
                candidates = []
                if view is not None:
                    try:
                        candidates.append(view.viewport())
                    except Exception:
                        pass
                    candidates.append(view)
                    try:
                        candidates.append(view.parent())
                    except Exception:
                        pass
                for cand in candidates:
                    hover = _read_hover_state(cand)
                    if hover is not None:
                        break
            hover_line_idx = -1
            if isinstance(hover, (tuple, list)) and len(hover) == 3:
                try:
                    if int(hover[0]) == int(index.row()) and int(hover[1]) == int(index.column()):
                        hover_line_idx = int(hover[2])
                except Exception:
                    hover_line_idx = -1

            # Fallback: if hover state isn't available/matching, derive hovered line from the actual cursor
            # position (more robust across platform/style variations).
            if hover_line_idx < 0:
                try:
                    if bool(option.state & QStyle.State_MouseOver) and view is not None:
                        vp = view.viewport() if hasattr(view, "viewport") else None
                        if vp is not None:
                            cur_pos = vp.mapFromGlobal(QCursor.pos())
                            idx2 = view.indexAt(cur_pos)
                            if idx2.isValid() and int(idx2.row()) == int(index.row()) and int(idx2.column()) == int(index.column()):
                                y_in = int(cur_pos.y()) - int(option.rect.top())
                                hover_line_idx = int(y_in // line_h)
                                if not (0 <= hover_line_idx < len(lines)):
                                    hover_line_idx = -1
                except Exception:
                    hover_line_idx = -1

            # Keep hover highlight purely visual: as long as the hovered line index is within
            # the rendered lines, paint it. (Link validity is handled elsewhere for click actions.)
            if not (0 <= hover_line_idx < len(lines)):
                hover_line_idx = -1

            # Diagnostics: confirm this delegate is painting the hovered cell.
            try:
                if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                    now = time.monotonic()
                    last_at = float(getattr(self, "_hover_cell_paint_last_info_at", 0.0))
                    if (now - last_at) >= 1.0:
                        setattr(self, "_hover_cell_paint_last_info_at", now)
                        logger.info(
                            "[HOVER-PAINT] composite(cell) row=%s col=%s hover_line=%s lines=%s hover=%s delegate_id=%s",
                            int(index.row()),
                            int(index.column()),
                            int(hover_line_idx),
                            int(len(lines)),
                            str(hover),
                            hex(id(self)),
                        )
            except Exception:
                pass

            if selected:
                try:
                    from PySide6.QtGui import QPalette

                    selected_text = option.palette.color(QPalette.HighlightedText)
                except Exception:
                    selected_text = get_qcolor(ThemeKey.TEXT_PRIMARY)
                tile_color = selected_text
                dataset_color = selected_text
                grant_color = selected_text
                sep_color = selected_text
            else:
                tile_color = get_qcolor(ThemeKey.TEXT_LINK)
                dataset_color = get_qcolor(ThemeKey.TEXT_INFO)
                grant_color = get_qcolor(ThemeKey.TEXT_WARNING)
                sep_color = get_qcolor(ThemeKey.TEXT_SECONDARY)

            painter.save()
            painter.setClipRect(rect)

            y = int(rect.top())
            for i, raw in enumerate(lines):
                if i == hover_line_idx:
                    try:
                        hover_bg = get_qcolor(ThemeKey.TEXT_LINK_HOVER_BACKGROUND)
                        try:
                            if hasattr(hover_bg, "isValid") and callable(hover_bg.isValid) and not hover_bg.isValid():
                                hover_bg = get_qcolor(ThemeKey.PANEL_WARNING_BACKGROUND)
                            elif hasattr(hover_bg, "alpha") and callable(hover_bg.alpha) and int(hover_bg.alpha()) == 0:
                                hover_bg = get_qcolor(ThemeKey.PANEL_WARNING_BACKGROUND)
                        except Exception:
                            pass
                        line_rect = QRect(int(rect.left()), int(y), int(rect.width()), int(line_h))
                        painter.fillRect(line_rect, QBrush(hover_bg))

                        # Draw a thin border to make hover visually obvious even if backgrounds are subtle.
                        try:
                            painter.setPen(QPen(get_qcolor(ThemeKey.TEXT_WARNING), 1))
                            painter.drawRect(line_rect.adjusted(0, 0, -1, -1))
                        except Exception:
                            pass

                        # Optional diagnostics: confirm paint is actually running for the hovered line.
                        try:
                            if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                                now = time.monotonic()
                                last_at = float(getattr(self, "_hover_paint_last_info_at", 0.0))
                                if (now - last_at) >= 1.0:
                                    setattr(self, "_hover_paint_last_info_at", now)
                                    logger.info(
                                        "[HOVER-PAINT] composite row=%s col=%s line=%s rect=%s bg=%s",
                                        int(index.row()),
                                        int(index.column()),
                                        int(hover_line_idx),
                                        f"{int(line_rect.x())},{int(line_rect.y())},{int(line_rect.width())},{int(line_rect.height())}",
                                        str(getattr(hover_bg, "name", lambda: "?")()),
                                    )
                        except Exception:
                            pass
                    except Exception:
                        pass
                tile, dataset, grant = self._split_line(raw)
                x = int(rect.left())

                # Tile
                painter.setPen(tile_color)
                painter.drawText(x, y + fm.ascent(), tile)
                x += fm.horizontalAdvance(tile)

                if dataset or grant:
                    painter.setPen(sep_color)
                    painter.drawText(x, y + fm.ascent(), self._SEP)
                    x += fm.horizontalAdvance(self._SEP)

                # Dataset
                if dataset:
                    painter.setPen(dataset_color)
                    painter.drawText(x, y + fm.ascent(), dataset)
                    x += fm.horizontalAdvance(dataset)

                if grant:
                    painter.setPen(sep_color)
                    painter.drawText(x, y + fm.ascent(), self._SEP)
                    x += fm.horizontalAdvance(self._SEP)

                    painter.setPen(grant_color)
                    painter.drawText(x, y + fm.ascent(), grant)

                y += line_h

            painter.restore()
        except Exception:
            return

    def editorEvent(self, event, model, option, index):  # noqa: N802
        # NOTE: Browser-link behavior for this column is intentionally removed.
        return super().editorEvent(event, model, option, index)


class MultiLineUuidLinkDelegate(QStyledItemDelegate):
    """Support multi-line UUID cells with per-line browser links + hover."""

    def sizeHint(self, option, index):  # noqa: N802
        try:
            text = str(index.data(Qt.DisplayRole) or "")
            lines = [x for x in text.splitlines() if x] if text else []
            n = max(1, len(lines))
            fm = option.fontMetrics
            h = int(fm.height()) * n + 4
            return QSize(max(1, int(option.rect.width())), max(1, h))
        except Exception:
            return super().sizeHint(option, index)

    def _urls(self, index) -> List[str]:
        try:
            ur = index.data(Qt.UserRole)
            if isinstance(ur, str):
                u = ur.strip()
                return [u] if u else []
            if isinstance(ur, list):
                return [str(x).strip() for x in ur if isinstance(x, str) and str(x).strip()]
        except Exception:
            return []
        return []

    def _line_index(self, option, event, lines_count: int) -> int:
        try:
            fm = option.fontMetrics
            line_h = max(1, int(fm.height()))
            pos = event.pos()
            y_in = int(pos.y()) - int(option.rect.top())
            idx = int(y_in // line_h)
            if 0 <= idx < lines_count:
                return idx
            return -1
        except Exception:
            return -1

    def helpEvent(self, event, view, option, index):  # noqa: N802
        try:
            text = str(index.data(Qt.DisplayRole) or "")
            lines = [x for x in text.splitlines() if x.strip()] if text else []
            urls = self._urls(index)
            if not lines or not urls:
                return super().helpEvent(event, view, option, index)

            line_idx = self._line_index(option, event, min(len(lines), len(urls)))
            if line_idx < 0:
                return super().helpEvent(event, view, option, index)

            url = urls[line_idx]
            if url:
                QToolTip.showText(event.globalPos(), url, view)
                return True
            return super().helpEvent(event, view, option, index)
        except Exception:
            return super().helpEvent(event, view, option, index)

    def paint(self, painter, option, index):  # noqa: N802
        text = str(index.data(Qt.DisplayRole) or "")
        if not text:
            return super().paint(painter, option, index)

        lines = [x for x in text.splitlines() if x.strip()]
        if not lines:
            return super().paint(painter, option, index)

        # Draw item background/selection/focus ONLY.
        # NOTE: Do NOT call super().paint() here.
        # QStyledItemDelegate.paint() calls initStyleOption() internally and will
        # overwrite opt.text with DisplayRole again, causing double text rendering
        # (default + custom).
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        try:
            # We paint per-line hover ourselves.
            opt.state &= ~QStyle.State_MouseOver
        except Exception:
            pass
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        # Visual paint probe for environment-specific debugging.
        # If this tint does not appear, this delegate's paint() is not being used.
        try:
            if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_PAINT_PROBE"):
                probe_bg = get_qcolor(ThemeKey.TEXT_WARNING)
                try:
                    probe_bg.setAlpha(60)
                except Exception:
                    pass
                painter.save()
                painter.fillRect(option.rect, QBrush(probe_bg))
                try:
                    painter.setPen(QPen(get_qcolor(ThemeKey.TEXT_ERROR), 2))
                    painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
                except Exception:
                    pass
                painter.restore()
        except Exception:
            pass

        # Diagnostics: confirm paint is running at all.
        try:
            if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                now = time.monotonic()
                last_at = float(getattr(self, "_paint_any_last_info_at", 0.0))
                if (now - last_at) >= 2.0:
                    setattr(self, "_paint_any_last_info_at", now)
                    logger.info(
                        "[DELEGATE-PAINT] uuid(any) row=%s col=%s state=%s",
                        int(index.row()),
                        int(index.column()),
                        str(getattr(option, "state", "?")),
                    )
        except Exception:
            pass

        try:
            selected = bool(option.state & QStyle.State_Selected)

            # Prefer delegate-local state (always accessible), then fall back to widget/viewport properties.
            hover = getattr(self, "_hover_link_state", None)

            view = option.widget

            def _normalize_hover_state(value: object) -> object:
                # Qt property can come back as a wrapper (e.g., QVariant-like) depending on binding.
                try:
                    if value is not None and hasattr(value, "value") and callable(value.value):
                        value = value.value()  # type: ignore[assignment]
                except Exception:
                    pass
                return value

            def _read_hover_state(obj: object) -> object:
                try:
                    # Prefer Qt property (stored in C++ object, stable across wrappers).
                    v = obj.property("_hover_link_state")  # type: ignore[attr-defined]
                    if v is not None:
                        return _normalize_hover_state(v)
                except Exception:
                    pass
                try:
                    return _normalize_hover_state(getattr(obj, "_hover_link_state", None))
                except Exception:
                    return None

            # Hover state is tracked on the viewport (mouse events are delivered there).
            # Keep backward compatibility by also checking the view and its parent.
            if hover is None:
                candidates = []
                if view is not None:
                    try:
                        candidates.append(view.viewport())
                    except Exception:
                        pass
                    candidates.append(view)
                    try:
                        candidates.append(view.parent())
                    except Exception:
                        pass
                for cand in candidates:
                    hover = _read_hover_state(cand)
                    if hover is not None:
                        break
            hover_line_idx = -1
            if isinstance(hover, (tuple, list)) and len(hover) == 3:
                try:
                    if int(hover[0]) == int(index.row()) and int(hover[1]) == int(index.column()):
                        hover_line_idx = int(hover[2])
                except Exception:
                    hover_line_idx = -1

            # Fallback: compute hovered line from actual cursor position.
            if hover_line_idx < 0:
                try:
                    if bool(option.state & QStyle.State_MouseOver) and view is not None:
                        vp = view.viewport() if hasattr(view, "viewport") else None
                        if vp is not None:
                            cur_pos = vp.mapFromGlobal(QCursor.pos())
                            idx2 = view.indexAt(cur_pos)
                            if idx2.isValid() and int(idx2.row()) == int(index.row()) and int(idx2.column()) == int(index.column()):
                                fm = option.fontMetrics
                                line_h = max(1, int(fm.height()))
                                y_in = int(cur_pos.y()) - int(option.rect.top())
                                hover_line_idx = int(y_in // line_h)
                                if not (0 <= hover_line_idx < len(lines)):
                                    hover_line_idx = -1
                except Exception:
                    hover_line_idx = -1

            # Keep hover highlight purely visual: as long as the hovered line index is within
            # the rendered lines, paint it. (URL validity is handled elsewhere for click actions.)
            if not (0 <= hover_line_idx < len(lines)):
                hover_line_idx = -1

            # Diagnostics: confirm this delegate is painting the hovered cell.
            try:
                if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG") and isinstance(hover, (tuple, list)) and len(hover) == 3:
                    if int(hover[0]) == int(index.row()) and int(hover[1]) == int(index.column()):
                        now = time.monotonic()
                        last_at = float(getattr(self, "_hover_cell_paint_last_info_at", 0.0))
                        if (now - last_at) >= 1.0:
                            setattr(self, "_hover_cell_paint_last_info_at", now)
                            logger.info(
                                "[HOVER-PAINT] uuid(cell) row=%s col=%s hover_line=%s",
                                int(index.row()),
                                int(index.column()),
                                int(hover_line_idx),
                            )
            except Exception:
                pass

            rect = option.rect
            fm = option.fontMetrics
            line_h = max(1, int(fm.height()))
            if selected:
                try:
                    from PySide6.QtGui import QPalette

                    selected_text = option.palette.color(QPalette.HighlightedText)
                except Exception:
                    selected_text = get_qcolor(ThemeKey.TEXT_PRIMARY)
                link_color = selected_text
                hover_color = selected_text
            else:
                link_color = get_qcolor(ThemeKey.TEXT_LINK)
                hover_color = get_qcolor(ThemeKey.TEXT_LINK_HOVER)
            hover_bg = get_qcolor(ThemeKey.TEXT_LINK_HOVER_BACKGROUND)

            painter.save()
            painter.setClipRect(rect)

            y = int(rect.top())
            for i, line in enumerate(lines):
                if i == hover_line_idx:
                    try:
                        line_rect = QRect(int(rect.left()), int(y), int(rect.width()), int(line_h))
                        painter.fillRect(line_rect, QBrush(hover_bg))

                        # Draw a thin border to make hover visually obvious.
                        try:
                            painter.setPen(QPen(get_qcolor(ThemeKey.TEXT_LINK_HOVER), 1))
                            painter.drawRect(line_rect.adjusted(0, 0, -1, -1))
                        except Exception:
                            pass

                        # Optional diagnostics: confirm paint is actually running for the hovered line.
                        try:
                            if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                                now = time.monotonic()
                                last_at = float(getattr(self, "_hover_paint_last_info_at", 0.0))
                                if (now - last_at) >= 1.0:
                                    setattr(self, "_hover_paint_last_info_at", now)
                                    logger.info(
                                        "[HOVER-PAINT] uuid row=%s col=%s line=%s rect=%s bg=%s",
                                        int(index.row()),
                                        int(index.column()),
                                        int(hover_line_idx),
                                        f"{int(line_rect.x())},{int(line_rect.y())},{int(line_rect.width())},{int(line_rect.height())}",
                                        str(getattr(hover_bg, "name", lambda: "?")()),
                                    )
                        except Exception:
                            pass
                    except Exception:
                        pass
                try:
                    painter.setPen(hover_color if i == hover_line_idx else link_color)
                except Exception:
                    painter.setPen(link_color)
                try:
                    f = QFont(option.font)
                    f.setUnderline(True)
                    painter.setFont(f)
                except Exception:
                    pass
                painter.drawText(int(rect.left()), int(y) + int(fm.ascent()), line)
                y += line_h

            painter.restore()
        except Exception:
            return

    def editorEvent(self, event, model, option, index):  # noqa: N802
        try:
            from PySide6.QtCore import QEvent

            if event.type() != QEvent.MouseButtonDblClick:
                return super().editorEvent(event, model, option, index)

            text = str(index.data(Qt.DisplayRole) or "")
            lines = [x for x in text.splitlines() if x.strip()] if text else []
            urls = self._urls(index)
            if not lines or not urls:
                return super().editorEvent(event, model, option, index)

            line_idx = self._line_index(option, event, min(len(lines), len(urls)))
            if line_idx < 0:
                return True

            url = urls[line_idx]
            if url:
                webbrowser.open(url)
            return True
        except Exception:
            return super().editorEvent(event, model, option, index)


class SampleEditButtonDelegate(QStyledItemDelegate):
    """Render a per-row button and open the sample edit dialog on click."""

    def __init__(self, parent: QObject, *, open_callback: Callable[[str, str], None]):
        super().__init__(parent)
        self._open_callback = open_callback

    def _button_rect(self, option) -> QRect:
        try:
            rect = option.rect
            margin = 3
            return rect.adjusted(margin, margin, -margin, -margin)
        except Exception:
            return option.rect

    def paint(self, painter, option, index):  # noqa: N802
        try:
            super().paint(painter, option, index)

            ur = index.data(Qt.UserRole)
            if isinstance(ur, dict):
                sample_id = str(ur.get("sample_id") or "").strip()
            else:
                sample_id = str(ur or "").strip()
            enabled = bool(sample_id)

            btn_opt = QStyleOptionButton()
            btn_opt.rect = self._button_rect(option)
            btn_opt.text = "試料編集"
            btn_opt.state = QStyle.State_Enabled if enabled else QStyle.State_None
            if option.state & QStyle.State_Selected:
                btn_opt.state |= QStyle.State_Selected

            style = option.widget.style() if option.widget is not None else QApplication.style()
            style.drawControl(QStyle.CE_PushButton, btn_opt, painter, option.widget)
        except Exception:
            return

    def editorEvent(self, event, model, option, index):  # noqa: N802
        try:
            from PySide6.QtCore import QEvent

            et = event.type()
            if et not in {QEvent.MouseButtonPress, QEvent.MouseButtonRelease}:
                return super().editorEvent(event, model, option, index)

            ur = index.data(Qt.UserRole)
            if isinstance(ur, dict):
                sample_id = str(ur.get("sample_id") or "").strip()
                subgroup_id = str(ur.get("subgroup_id") or "").strip()
            else:
                sample_id = str(ur or "").strip()
                subgroup_id = ""
            if not sample_id:
                return True

            btn_rect = self._button_rect(option)
            try:
                pos = event.position().toPoint()  # type: ignore[attr-defined]
            except Exception:
                try:
                    pos = event.pos()  # type: ignore[attr-defined]
                except Exception:
                    return True

            if not btn_rect.contains(pos):
                return super().editorEvent(event, model, option, index)

            if et == QEvent.MouseButtonRelease:
                try:
                    self._open_callback(sample_id, subgroup_id)
                except Exception:
                    pass
            return True
        except Exception:
            return super().editorEvent(event, model, option, index)

class ColumnSelectorDialog(QDialog):
    def __init__(self, parent: QWidget, columns: List[SampleDedupColumn], visible_by_key: Dict[str, bool]):
        super().__init__(parent)
        try:
            # 初回表示時の一瞬の黒/無色フラッシュを抑制するため、親のスタイルを先に適用する。
            self.setStyleSheet(parent.styleSheet())
        except Exception:
            pass
        try:
            self.setUpdatesEnabled(False)
        except Exception:
            pass
        self.setWindowTitle("列選択")
        self._columns = columns

        self._default_visible_by_key: Dict[str, bool] = {c.key: bool(getattr(c, "default_visible", True)) for c in columns}
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

        btn_select_all = QPushButton("全選択", self)
        btn_select_all.clicked.connect(self._select_all)
        quick_buttons.addWidget(btn_select_all)

        btn_select_none = QPushButton("全非選択", self)
        btn_select_none.clicked.connect(self._select_none)
        quick_buttons.addWidget(btn_select_none)

        btn_reset = QPushButton("列リセット", self)
        btn_reset.clicked.connect(self._reset_to_default)
        quick_buttons.addWidget(btn_reset)

        quick_buttons.addStretch(1)
        layout.addLayout(quick_buttons)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        try:
            self.setUpdatesEnabled(True)
        except Exception:
            pass

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


class SampleFetchThread(QThread):
    completed = Signal(str)

    def __init__(self, subgroup_ids: List[str], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._subgroup_ids = subgroup_ids

    def run(self):
        msg = ""
        try:
            msg = fetch_samples_for_subgroups(self._subgroup_ids)
        except Exception as e:
            msg = f"試料情報取得に失敗しました: {e}"
            try:
                logger.exception("[SAMPLE-FETCH] failed: %s", str(e))
            except Exception:
                pass
        try:
            self.completed.emit(str(msg or ""))
        except Exception:
            pass


class SampleDedupListingWidget(QWidget):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        title: str = "🧪 試料一覧",
        columns_provider: Callable[[], List[SampleDedupColumn]] = get_default_columns,
        rows_builder: Callable[[Optional[List[str]]], Any] = build_sample_dedup_rows_from_files,
        cache_enabled: bool = True,
        multiline_link_column_key: Optional[str] = None,
    ):
        super().__init__(parent)
        self._initial_window_size_applied: bool = False
        self._title = str(title)
        self._columns_provider = columns_provider
        self._rows_builder = rows_builder
        self._cache_enabled = bool(cache_enabled)
        self._multiline_link_column_key = str(multiline_link_column_key) if multiline_link_column_key else ""
        self._multiline_link_delegate: Optional[MultiLineCompositeLinkDelegate] = None
        self._multiline_uuid_delegate: Optional[MultiLineUuidLinkDelegate] = None
        self._columns: List[SampleDedupColumn] = []
        self._rows: List[Dict[str, Any]] = []
        self._filter_edits_by_col_index: Dict[int, QLineEdit] = {}
        self._filter_blocks_by_col_index: Dict[int, QWidget] = {}
        self._range_spins_by_col_index: Dict[int, tuple[QSpinBox, QSpinBox]] = {}
        self._fetch_thread: Optional[SampleFetchThread] = None
        self._refresh_thread: Optional[QThread] = None
        self._spinner_overlay: Optional[SpinnerOverlay] = None
        self._filters_collapsed: bool = False
        self._filter_relayout_timer = QTimer(self)
        self._filter_relayout_timer.setSingleShot(True)
        self._filter_relayout_timer.setInterval(150)
        self._filter_relayout_timer.timeout.connect(self._relayout_column_filters)
        self._ui_counts_timer = QTimer(self)
        self._ui_counts_timer.setSingleShot(True)
        self._ui_counts_timer.setInterval(50)
        self._ui_counts_timer.timeout.connect(self._refresh_counts)

        self._ui_row_resize_timer = QTimer(self)
        self._ui_row_resize_timer.setSingleShot(True)
        self._ui_row_resize_timer.setInterval(0)
        self._ui_row_resize_timer.timeout.connect(self._resize_rows_to_contents)

        self._suppress_prefilter_signals: bool = False
        self._prefilter_apply_timer = QTimer(self)
        self._prefilter_apply_timer.setSingleShot(True)
        self._prefilter_apply_timer.setInterval(250)
        self._prefilter_apply_timer.timeout.connect(self._apply_prefilters_now)

        # Avoid double-opening relink dialog on double click (Qt emits multiple mouse events).
        self._last_relink_open_at: float = 0.0

        # Hover state for per-line link highlighting: (row, col, line_idx) on the view's model.
        self._hover_link_state: tuple[int, int, int] | None = None

        self._hover_diag_enabled: bool = bool(os.environ.get("RDE_SAMPLE_DEDUP_HOVER_DIAG"))
        self._hover_diag_moves: int = 0
        self._hover_diag_hits: int = 0
        self._hover_diag_last: str = ""
        self._hover_diag_label = None

        self._init_ui()
        self._init_models()
        self._apply_columns()
        self._load_prefilter_choices()
        if self._cache_enabled:
            self._load_from_cache_and_refresh_if_needed(auto_fetch=not os.environ.get("PYTEST_CURRENT_TEST"))
        else:
            self._load_without_cache_and_refresh(auto_fetch=not os.environ.get("PYTEST_CURRENT_TEST"))

    def _line_index_in_cell(self, rect, y: int, lines_count: int) -> int:
        if lines_count <= 0:
            return -1
        try:
            y_in = int(y) - int(rect.top())
            if y_in < 0:
                return -1
            h = max(1, int(rect.height()))
            idx = int((y_in * lines_count) // h)
            if idx < 0:
                return -1
            if idx >= lines_count:
                return lines_count - 1
            return idx
        except Exception:
            return -1

    def _init_models(self) -> None:
        self._columns = list(self._columns_provider() or [])
        self._rows = []
        self._model = SampleDedupTableModel(self._columns, self._rows)
        self._filter_proxy = SampleDedupFilterProxyModel(self)
        self._filter_proxy.setSourceModel(self._model)
        self._paging_proxy = PaginationProxyModel(self)
        self._paging_proxy.setSourceModel(self._filter_proxy)
        self.table.setModel(self._paging_proxy)

        try:
            if self._multiline_link_column_key:
                logger.info(
                    "[RELINK] hook ready title=%s table=%s target_col=%s",
                    str(self._title),
                    type(self.table).__name__,
                    str(self._multiline_link_column_key),
                )
        except Exception:
            pass
        try:
            if hasattr(self.table, "cell_clicked_with_pos"):
                self.table.cell_clicked_with_pos.connect(self._on_table_cell_activated)  # type: ignore[attr-defined]
            if hasattr(self.table, "cell_double_clicked_with_pos"):
                self.table.cell_double_clicked_with_pos.connect(self._on_table_cell_activated)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.table.clicked.connect(self._on_table_clicked)
        except Exception:
            pass
        try:
            self._filter_proxy.rowsInserted.connect(lambda *_args: self._schedule_counts_refresh())
            self._filter_proxy.rowsRemoved.connect(lambda *_args: self._schedule_counts_refresh())
            self._filter_proxy.modelReset.connect(lambda *_args: self._schedule_counts_refresh())
        except Exception:
            pass
        try:
            self._paging_proxy.modelReset.connect(lambda *_args: self._schedule_row_resize())
            self._paging_proxy.layoutChanged.connect(lambda *_args: self._schedule_row_resize())
            self._paging_proxy.rowsInserted.connect(lambda *_args: self._schedule_row_resize())
            self._paging_proxy.rowsRemoved.connect(lambda *_args: self._schedule_row_resize())
        except Exception:
            pass
        self._rebuild_column_filters()

    def _open_sample_edit_dialog(self, sample_id: str, subgroup_id: str = "") -> None:
        sid = _safe_str(sample_id).strip()
        if not sid:
            return
        gid = _safe_str(subgroup_id).strip()
        if not gid:
            # Try to infer subgroup id from current model rows.
            try:
                for r in self._model.get_rows():
                    if not isinstance(r, dict):
                        continue
                    if _safe_str(r.get("sample_id")).strip() == sid:
                        gid = _safe_str(r.get("subgroup_id")).strip()
                        if gid:
                            break
            except Exception:
                gid = ""
        try:
            dlg = SampleEditDialog(self, sample_id=sid)
            if dlg.exec() == QDialog.Accepted:
                try:
                    # 編集結果を一覧へ反映
                    if self._cache_enabled:
                        self._load_from_cache_and_refresh_if_needed(auto_fetch=False, force_refresh=True)
                    else:
                        self._load_without_cache_and_refresh(auto_fetch=False)
                except Exception:
                    pass
            else:
                # If the dialog failed to load the sample (API error / no response),
                # treat it as a non-existent entry and purge from local sources.
                try:
                    load_failed = bool(getattr(dlg, "load_failed", lambda: False)())
                except Exception:
                    load_failed = False
                if load_failed:
                    self._purge_invalid_sample_entry(sample_id=sid, subgroup_id=gid)
        except Exception as e:
            logger.error("[SAMPLE-EDIT] Failed to open sample edit dialog: %s", str(e))

    def _purge_invalid_sample_entry(self, *, sample_id: str, subgroup_id: str) -> None:
        sid = _safe_str(sample_id).strip()
        gid = _safe_str(subgroup_id).strip()
        if not sid or not gid:
            return
        try:
            from classes.subgroup.util.sample_dedup_table_records import purge_invalid_sample_entry

            purge_invalid_sample_entry(subgroup_id=gid, sample_id=sid)
        except Exception as e:
            logger.error("[SAMPLE-PURGE] Failed to purge local sources: %s", str(e))

        # Remove from current UI model immediately.
        try:
            current = [r for r in self._model.get_rows() if isinstance(r, dict)]
            filtered = [r for r in current if _safe_str(r.get("sample_id")).strip() != sid]
            if len(filtered) != len(current):
                self._model.set_rows(filtered)
                self._apply_columns()
                self._schedule_counts_refresh()
        except Exception:
            pass

        # In real runs, also force-refresh to keep cache/proxies consistent.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        try:
            if self._cache_enabled:
                self._load_from_cache_and_refresh_if_needed(auto_fetch=False, force_refresh=True)
            else:
                self._load_without_cache_and_refresh(auto_fetch=False)
        except Exception:
            pass

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        self.header_label = QLabel(self._title)
        layout.addWidget(self.header_label)

        # Row 1: prefilters + actions
        top_row = QHBoxLayout()

        top_row.addWidget(QLabel("ロール:"))
        self._pref_role = QComboBox(self)
        self._pref_role.setObjectName("sample_dedup_prefilter_role")
        top_row.addWidget(self._pref_role)

        top_row.addWidget(QLabel("サブグループ:"))
        self._pref_subgroup = QComboBox(self)
        self._pref_subgroup.setObjectName("sample_dedup_prefilter_subgroup")
        self._pref_subgroup.setMinimumWidth(220)
        self._pref_subgroup.setEditable(True)
        self._pref_subgroup.setInsertPolicy(QComboBox.NoInsert)
        top_row.addWidget(self._pref_subgroup)

        top_row.addWidget(QLabel("課題番号:"))
        self._pref_grant = QComboBox(self)
        self._pref_grant.setObjectName("sample_dedup_prefilter_grant")
        self._pref_grant.setEditable(True)
        self._pref_grant.setInsertPolicy(QComboBox.NoInsert)
        self._pref_grant.setMinimumWidth(180)
        top_row.addWidget(self._pref_grant)

        # Auto apply: no apply button.

        top_row.addStretch(1)
        layout.addLayout(top_row)

        # Row 2: buttons / counters
        controls = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        controls.addWidget(self.status_label, 1)

        if self._hover_diag_enabled:
            try:
                self._hover_diag_label = QLabel("[HOVER-DIAG] enabled", self)
                self._hover_diag_label.setWordWrap(True)
                controls.addWidget(self._hover_diag_label, 1)
            except Exception:
                self._hover_diag_label = None

        controls.addWidget(QLabel("表示行数:"))
        self._row_limit = QSpinBox(self)
        self._row_limit.setMinimum(0)
        self._row_limit.setMaximum(999999)
        self._row_limit.setValue(100)
        self._row_limit.setSpecialValueText("全件")
        self._row_limit.valueChanged.connect(self._on_page_size_changed)
        controls.addWidget(self._row_limit)

        controls.addWidget(QLabel("ページ:"))
        self._page = QSpinBox(self)
        self._page.setObjectName("sample_dedup_page")
        self._page.setMinimum(1)
        self._page.setMaximum(1)
        self._page.setValue(1)
        self._page.valueChanged.connect(self._on_page_changed)
        controls.addWidget(self._page)

        controls.addWidget(QLabel("/"))
        self._total_pages = QLabel("1")
        self._total_pages.setObjectName("sample_dedup_total_pages")
        controls.addWidget(self._total_pages)

        self._select_columns = QPushButton("列選択", self)
        self._select_columns.clicked.connect(self._open_column_selector)
        controls.addWidget(self._select_columns)

        self._reset_columns = QPushButton("列リセット", self)
        self._reset_columns.clicked.connect(self._reset_columns_to_default)
        controls.addWidget(self._reset_columns)

        self._compact_rows_btn = QPushButton("1行表示", self)
        self._compact_rows_btn.clicked.connect(self._apply_compact_rows)
        controls.addWidget(self._compact_rows_btn)

        self._equal_columns_btn = QPushButton("列幅そろえ", self)
        self._equal_columns_btn.clicked.connect(self._apply_equal_columns)
        controls.addWidget(self._equal_columns_btn)

        export_menu = QMenu(self)
        export_csv = export_menu.addAction("CSV出力")
        export_csv.triggered.connect(lambda: self._export("csv"))
        export_xlsx = export_menu.addAction("XLSX出力")
        export_xlsx.triggered.connect(lambda: self._export("xlsx"))

        self._export_btn = QPushButton("エクスポート", self)
        self._export_btn.setMenu(export_menu)
        controls.addWidget(self._export_btn)

        self.reload_button = QPushButton("更新", self)
        self.reload_button.clicked.connect(lambda: self._load_from_cache_and_refresh_if_needed(auto_fetch=True, force_refresh=True))
        controls.addWidget(self.reload_button)

        self.fetch_button = QPushButton("不足試料を取得", self)
        self.fetch_button.clicked.connect(self._fetch_missing_samples)
        controls.addWidget(self.fetch_button)

        self._toggle_filters_button = QPushButton("フィルタ最小化", self)
        self._toggle_filters_button.clicked.connect(self._toggle_filters)
        controls.addWidget(self._toggle_filters_button)

        layout.addLayout(controls)

        # Row 3: column filters container
        self._filters_container = QWidget(self)
        self._filters_container.setObjectName("sample_dedup_filters_container")
        self._filters_layout = QVBoxLayout(self._filters_container)
        self._filters_layout.setContentsMargins(0, 0, 0, 0)
        self._filters_layout.setSpacing(6)

        self._filters_summary_label = QLabel("", self._filters_container)
        self._filters_summary_label.setWordWrap(True)
        self._filters_layout.addWidget(self._filters_summary_label)

        self._column_filters_grid = QGridLayout()
        self._column_filters_grid.setContentsMargins(0, 0, 0, 0)
        self._column_filters_grid.setHorizontalSpacing(10)
        self._column_filters_grid.setVerticalSpacing(6)
        self._filters_layout.addLayout(self._column_filters_grid)

        layout.addWidget(self._filters_container)

        self.table = SampleDedupTableView()
        self.table.setObjectName("sample_dedup_table")
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        try:
            # Enable hover effects in delegates.
            self.table.setMouseTracking(True)
            self.table.viewport().setMouseTracking(True)
            try:
                self.table.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                self.table.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            except Exception:
                # Fallback for older enum access
                try:
                    self.table.setAttribute(Qt.WA_Hover, True)
                    self.table.viewport().setAttribute(Qt.WA_Hover, True)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            # Ensure link-hover cursor works even when table hover styles are enabled.
            self.table.viewport().installEventFilter(self)
        except Exception:
            pass

        try:
            # MouseMove/Leave events are routed through QTableView.viewportEvent; use signals for reliable hover tracking.
            self.table.cell_hovered_with_pos.connect(self._on_table_cell_hovered)
            self.table.viewport_left.connect(self._on_table_viewport_left)
        except Exception:
            pass
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.table)

        try:
            self._spinner_overlay = SpinnerOverlay(self.table)
        except Exception:
            self._spinner_overlay = None

        self.setLayout(layout)
        self._apply_target_width()
        self._apply_theme()
        self._bind_theme_refresh()

        self._bind_prefilter_signals()

    def _on_table_cell_activated(self, index: object, pos: object) -> None:
        """Handle click/double click with position (robust against viewport eventFilter issues)."""
        try:
            if not isinstance(index, QModelIndex) or not index.isValid():
                logger.debug("[RELINK] activated ignored: invalid index type=%s", type(index))
                return
            if not (0 <= index.column() < len(self._columns)):
                logger.debug(
                    "[RELINK] activated ignored: col out of range col=%s columns=%s",
                    int(index.column()),
                    len(self._columns),
                )
                return
            col_key = self._columns[index.column()].key
            if not (self._multiline_link_column_key and col_key == self._multiline_link_column_key):
                logger.debug(
                    "[RELINK] activated ignored: col mismatch key=%s target=%s",
                    str(col_key),
                    str(self._multiline_link_column_key),
                )
                return

            # Debounce to avoid opening twice on double click.
            now = time.monotonic()
            if (now - float(self._last_relink_open_at or 0.0)) < 0.25:
                logger.debug("[RELINK] activated ignored: debounced")
                return

            rect = self.table.visualRect(index)

            text = str(index.data(Qt.DisplayRole) or "")
            lines = [x for x in text.splitlines() if x] if text else []
            if not lines:
                logger.info("[RELINK] ignored: no lines (DisplayRole)")
                return

            links = index.data(Qt.UserRole)
            if not isinstance(links, list):
                links = []

            # pos is viewport coordinates (QPoint)
            try:
                y = int(pos.y())  # type: ignore[union-attr]
            except Exception:
                y = 0

            max_lines = len(lines)
            if links:
                max_lines = min(max_lines, len(links))

            line_idx = self._line_index_in_cell(rect, y, max_lines)
            if line_idx < 0 or line_idx >= len(lines):
                logger.info(
                    "[RELINK] ignored: line_idx out of range line_idx=%s lines=%s links=%s rect_h=%s y=%s",
                    line_idx,
                    len(lines),
                    len(links),
                    int(rect.height()),
                    y,
                )
                return

            entry_id = ""
            dataset_id = ""

            # Primary: entry id is stored in tile_dataset_grant_links (UserRole)
            if links and 0 <= line_idx < len(links):
                item = links[line_idx]
                if isinstance(item, dict):
                    entry_id = str(item.get("data_entry_id") or "").strip()
                    dataset_id = str(item.get("dataset_id") or "").strip()
                else:
                    logger.info("[RELINK] ignored: link item not dict")

            # Fallback: derive entry id from the row's data_entry_ids column.
            if not entry_id:
                try:
                    eid_col = next((i for i, c in enumerate(self._columns) if c.key == "data_entry_ids"), -1)
                    if eid_col >= 0:
                        eid_text = str(index.siblingAtColumn(eid_col).data(Qt.DisplayRole) or "")
                        eids = [x.strip() for x in eid_text.splitlines() if x.strip()]
                        if 0 <= line_idx < len(eids):
                            entry_id = str(eids[line_idx]).strip()
                except Exception:
                    entry_id = ""

            if not dataset_id:
                try:
                    did_col = next((i for i, c in enumerate(self._columns) if c.key == "dataset_ids"), -1)
                    if did_col >= 0:
                        did_text = str(index.siblingAtColumn(did_col).data(Qt.DisplayRole) or "")
                        dids = [x.strip() for x in did_text.splitlines() if x.strip()]
                        if 0 <= line_idx < len(dids):
                            dataset_id = str(dids[line_idx]).strip()
                except Exception:
                    dataset_id = ""

            if not entry_id:
                logger.info("[RELINK] ignored: data_entry_id missing")
                return

            raw = lines[line_idx]
            tile, dataset, _grant = self._split_tile_dataset_grant_line(raw)

            subgroup_id = ""
            sample_id = ""
            try:
                sg_col = next((i for i, c in enumerate(self._columns) if c.key == "subgroup_id"), -1)
                if sg_col >= 0:
                    subgroup_id = str(index.siblingAtColumn(sg_col).data(Qt.DisplayRole) or "").strip()
            except Exception:
                subgroup_id = ""
            try:
                s_col = next((i for i, c in enumerate(self._columns) if c.key == "sample_id"), -1)
                if s_col >= 0:
                    sample_id = str(index.siblingAtColumn(s_col).data(Qt.DisplayRole) or "").strip()
            except Exception:
                sample_id = ""

            self._last_relink_open_at = now
            dlg = SampleEntrySampleRelinkDialog(
                self,
                subgroup_id=subgroup_id,
                current_sample_id=sample_id,
                entry_id=entry_id,
                tile_name=str(tile or "").strip(),
                dataset_name=str(dataset or "").strip(),
            )
            if dlg.exec() == QDialog.Accepted:
                # Refresh related local JSON + update cache, then reload view.
                def _reload_view() -> None:
                    try:
                        if self._cache_enabled:
                            self._load_from_cache_and_refresh_if_needed(auto_fetch=False, force_refresh=True)
                        else:
                            self._load_without_cache_and_refresh(auto_fetch=False)
                    except Exception:
                        pass

                if os.environ.get("PYTEST_CURRENT_TEST"):
                    _reload_view()
                    return

                class _RelinkRefreshThread(QThread):
                    completed = Signal(object)

                    def __init__(self, subgroup_id: str, dataset_id: str, parent: QObject):
                        super().__init__(parent)
                        self._subgroup_id = str(subgroup_id or "").strip()
                        self._dataset_id = str(dataset_id or "").strip()

                    def run(self):
                        result: Dict[str, Any] = {"dataset_refreshed": False, "cache_updated": False}
                        try:
                            if self._dataset_id:
                                from classes.dataset.core.dataset_dataentry_logic import fetch_dataset_dataentry

                                ok = bool(fetch_dataset_dataentry(self._dataset_id, force_refresh=True))
                                result["dataset_refreshed"] = ok
                        except Exception:
                            result["dataset_refreshed"] = False

                        try:
                            if self._subgroup_id:
                                result["cache_updated"] = bool(update_sample_listing_cache_for_subgroups([self._subgroup_id]))
                        except Exception:
                            result["cache_updated"] = False

                        self.completed.emit(result)

                self.status_label.setText("紐づけ変更を反映中...（ローカルJSON更新・キャッシュ更新）")
                t = _RelinkRefreshThread(subgroup_id, dataset_id, self)

                def _on_done(result: object) -> None:
                    try:
                        r = result if isinstance(result, dict) else {}
                        logger.info(
                            "[RELINK] post-refresh done dataset_id=%s refreshed=%s cache_updated=%s",
                            str(dataset_id),
                            bool(r.get("dataset_refreshed")),
                            bool(r.get("cache_updated")),
                        )
                    except Exception:
                        pass
                    _reload_view()

                t.completed.connect(_on_done)
                self._relink_refresh_thread = t  # type: ignore[attr-defined]
                t.start()
        except Exception:
            logger.exception("[RELINK] failed to handle table click")
            return

    def _apply_theme(self) -> None:
        color = ""
        try:
            raw = get_color(ThemeKey.TEXT_PRIMARY)
            try:
                color = raw.name()  # type: ignore[attr-defined]
            except Exception:
                color = str(raw or "")
        except Exception:
            color = ""

        try:
            self.header_label.setStyleSheet(f"font-weight: bold; color: {color};")
        except Exception:
            pass

        self._apply_button_styles()

    def _apply_button_styles(self) -> None:
        for button, kind in (
            (getattr(self, "_select_columns", None), "secondary"),
            (getattr(self, "_reset_columns", None), "secondary"),
            (getattr(self, "_compact_rows_btn", None), "primary"),
            (getattr(self, "_equal_columns_btn", None), "secondary"),
            (getattr(self, "_export_btn", None), "success"),
            (getattr(self, "reload_button", None), "info"),
            (getattr(self, "fetch_button", None), "warning"),
            (getattr(self, "_toggle_filters_button", None), "secondary"),
        ):
            if button is None:
                continue
            try:
                button.setStyleSheet(get_button_style(kind))
            except Exception:
                continue

    def _bind_theme_refresh(self) -> None:
        try:
            tm = ThemeManager.instance()
        except Exception:
            tm = None

        if tm is None:
            return

        def _on_theme_changed(*_args: object) -> None:
            self._apply_theme()

        try:
            tm.theme_changed.connect(_on_theme_changed)
            self._rde_theme_refresh_slot = _on_theme_changed  # type: ignore[attr-defined]
        except Exception:
            return

    def _apply_target_width(self) -> None:
        # NOTE: window resize is managed by the parent tab widget (tab-specific sizing).
        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            return

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------
    def _on_table_clicked(self, index: QModelIndex) -> None:
        try:
            if not index.isValid():
                return
            if not (0 <= index.column() < len(self._columns)):
                return
            col = self._columns[index.column()]

            # Fallback: even if our viewport/mouse hooks are swallowed in some envs,
            # QAbstractItemView still emits clicked when selection changes.
            if self._multiline_link_column_key and col.key == self._multiline_link_column_key:
                # If viewportEvent already captured the click position just now, let that
                # path drive relink (avoids double-trigger and line-index mismatch).
                try:
                    last_at = float(getattr(self.table, "_last_viewport_click_at", 0.0))
                    if last_at > 0 and (time.monotonic() - last_at) < 0.15:
                        return
                except Exception:
                    pass

                try:
                    vp = self.table.viewport().mapFromGlobal(QCursor.pos())
                except Exception:
                    vp = QPoint()
                self._on_table_cell_activated(index, vp)
                return

            if col.key not in {"subgroup_id", "dataset_ids", "data_entry_ids", "sample_id"}:
                return
            url = index.data(Qt.UserRole)
            # QDesktopServices can fail silently on some Windows envs; webbrowser is more reliable.
            if isinstance(url, str) and url:
                webbrowser.open(url)
            elif isinstance(url, list):
                urls = [str(x).strip() for x in url if isinstance(x, str) and str(x).strip()]
                # If the cell contains multiple UUIDs, single-click is ambiguous; use double click in delegate.
                if len(urls) == 1:
                    webbrowser.open(urls[0])
        except Exception:
            return

    def _schedule_row_resize(self) -> None:
        try:
            self._ui_row_resize_timer.start()
        except Exception:
            self._resize_rows_to_contents()

    def _resize_rows_to_contents(self) -> None:
        try:
            self.table.resizeRowsToContents()
        except Exception:
            return

    def _rebuild_filters(self) -> None:
        # deprecated
        self._rebuild_column_filters()

    def _clear_grid_layout(self, grid: QGridLayout) -> None:
        try:
            while grid.count():
                item = grid.takeAt(0)
                w = item.widget() if item else None
                # Do not de-parent: de-parenting a container destroys its children
                # (and will delete QLineEdit reused across relayout), causing:
                # RuntimeError: Internal C++ object ... already deleted.
                if w is not None:
                    try:
                        w.setVisible(False)
                    except Exception:
                        pass
        except Exception:
            return

    def _rebuild_column_filters(self) -> None:
        self._filter_edits_by_col_index.clear()
        self._range_spins_by_col_index.clear()
        # Dispose old blocks to avoid orphaned widgets when columns change.
        for block in self._filter_blocks_by_col_index.values():
            try:
                block.deleteLater()
            except Exception:
                pass
        self._filter_blocks_by_col_index.clear()
        self._clear_grid_layout(self._column_filters_grid)

        for col_index, col in enumerate(self._columns):
            if col.key == "sample_edit":
                continue
            block = QWidget(self._filters_container)
            block.setObjectName(f"sample_dedup_filter_block_{col.key}")
            block_layout = QHBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(6)

            label = QLabel(col.label, block)
            label.setObjectName(f"sample_dedup_filter_label_{col.key}")
            label.setMinimumWidth(90)

            block_layout.addWidget(label)

            # Numeric columns: range filter (min~max)
            if col.key in {"data_entry_count", "dataset_count", "grant_count"}:
                mn = QSpinBox(block)
                mx = QSpinBox(block)

                for sp, suffix in ((mn, "min"), (mx, "max")):
                    sp.setObjectName(f"sample_dedup_filter_{col.key}_{suffix}")
                    sp.setMinimum(-1)
                    sp.setMaximum(999999)
                    sp.setSpecialValueText("なし")
                    sp.setValue(-1)
                    sp.setMinimumWidth(90)

                sep = QLabel("～", block)
                sep.setObjectName(f"sample_dedup_filter_{col.key}_sep")

                def _apply_range(*_args: object, idx: int = col_index, mn_sp: QSpinBox = mn, mx_sp: QSpinBox = mx) -> None:
                    self._apply_numeric_range_filter(idx, mn_sp, mx_sp)

                mn.valueChanged.connect(_apply_range)
                mx.valueChanged.connect(_apply_range)

                block_layout.addWidget(mn)
                block_layout.addWidget(sep)
                block_layout.addWidget(mx)
                block_layout.addStretch(1)
                self._range_spins_by_col_index[col_index] = (mn, mx)
            else:
                edit = QLineEdit(block)
                edit.setObjectName(f"sample_dedup_filter_{col.key}")
                edit.setPlaceholderText("部分一致")
                edit.textChanged.connect(lambda text, idx=col_index: self._filter_proxy.set_column_filter(idx, text))
                edit.setMinimumWidth(160)
                block_layout.addWidget(edit, 1)
                self._filter_edits_by_col_index[col_index] = edit
            block.setLayout(block_layout)

            self._filter_blocks_by_col_index[col_index] = block

        self._relayout_column_filters()
        self._schedule_counts_refresh()

    def _apply_numeric_range_filter(self, col_index: int, mn_sp: QSpinBox, mx_sp: QSpinBox) -> None:
        try:
            mn_raw = int(mn_sp.value())
            mx_raw = int(mx_sp.value())
            mn = None if mn_raw < 0 else mn_raw
            mx = None if mx_raw < 0 else mx_raw

            if mn is not None and mx is not None and mn > mx:
                mx_sp.blockSignals(True)
                mx_sp.setValue(mn)
                mx_sp.blockSignals(False)
                mx = mn

            self._filter_proxy.set_numeric_range(int(col_index), mn, mx)
            self._refresh_filters_summary()
        except Exception:
            return

    def _relayout_column_filters(self) -> None:
        self._clear_grid_layout(self._column_filters_grid)

        try:
            available = max(300, int(self.width()))
        except Exception:
            available = 800

        # Estimate how many filter blocks can fit in one row.
        block_w = 260
        blocks_per_row = max(1, available // block_w)

        row = 0
        col = 0
        for col_index, column in enumerate(self._columns):
            block = self._filter_blocks_by_col_index.get(col_index)
            if block is None:
                continue

            # Keep label text in sync (columns can change)
            try:
                label = block.findChild(QLabel, f"sample_dedup_filter_label_{column.key}")
                if label is not None:
                    label.setText(column.label)
            except Exception:
                pass

            try:
                block.setVisible(True)
            except Exception:
                pass

            self._column_filters_grid.addWidget(block, row, col)
            col += 1
            if col >= blocks_per_row:
                col = 0
                row += 1

    def _apply_columns(self) -> None:
        for idx, col in enumerate(self._columns):
            self.table.setColumnHidden(idx, not col.default_visible)

        # Optional multi-line composite links (per-line click)
        if self._multiline_link_column_key:
            try:
                col_index = next(
                    (i for i, c in enumerate(self._columns) if c.key == self._multiline_link_column_key),
                    -1,
                )
            except Exception:
                col_index = -1
            if col_index >= 0:
                if self._multiline_link_delegate is None:
                    self._multiline_link_delegate = MultiLineCompositeLinkDelegate(self.table)
                try:
                    self.table.setItemDelegateForColumn(col_index, self._multiline_link_delegate)
                except Exception:
                    pass

        # UUID columns: per-line link + hover
        if self._multiline_uuid_delegate is None:
            self._multiline_uuid_delegate = MultiLineUuidLinkDelegate(self.table)
        for idx, col in enumerate(self._columns):
            if col.key in {"subgroup_id", "dataset_ids", "data_entry_ids", "sample_id"}:
                try:
                    self.table.setItemDelegateForColumn(idx, self._multiline_uuid_delegate)
                except Exception:
                    pass

        # Sample edit button column.
        for idx, col in enumerate(self._columns):
            if col.key == "sample_edit":
                try:
                    self.table.setItemDelegateForColumn(
                        idx,
                        SampleEditButtonDelegate(self.table, open_callback=self._open_sample_edit_dialog),
                    )
                except Exception:
                    pass

        # UUID columns initial width should be short.
        for idx, col in enumerate(self._columns):
            if col.key.endswith("_id") or col.key.endswith("_ids"):
                try:
                    self.table.setColumnWidth(idx, 140)
                except Exception:
                    pass
            if col.key == "grant_numbers":
                try:
                    self.table.setColumnWidth(idx, 140)
                except Exception:
                    pass
            if col.key == "sample_edit":
                try:
                    fm = QFontMetrics(self.table.font())
                    header_w = int(fm.horizontalAdvance(col.label)) + 24
                    self.table.setColumnWidth(idx, min(max(header_w, 72), 110))
                except Exception:
                    pass

            # 数値列は広がりすぎないよう上限を設ける（ヘッダ/内容ベースで最小幅は確保）
            if col.key in {"data_entry_count", "dataset_count", "subgroup_dataset_count", "grant_count"}:
                try:
                    fm = QFontMetrics(self.table.font())
                    header_w = int(fm.horizontalAdvance(col.label)) + 24
                    # 想定最大桁(～6桁程度) + 余白
                    digit_w = int(fm.horizontalAdvance("0"))
                    content_w = digit_w * 6 + 24
                    max_w = 110
                    # 「データセット数」は特に細く（過剰に幅を取らない）
                    if col.key == "dataset_count":
                        max_w = 90
                    self.table.setColumnWidth(idx, min(max(header_w, content_w, 60), max_w))
                except Exception:
                    pass

            # 主要列は省略が減るよう最低文字数を確保
            major_min_chars = {
                # 要望: できるだけ省略表示しない初期列幅
                "subgroup_name": 20,
                "subgroup_description": 20,
                # 課題番号: 半角15文字相当
                "grant_numbers": 15,
                "dataset_names": 20,
                "tile_name": 20,
                "sample_name": 20,
                "tile_dataset_grant": 20,
            }
            if col.key in major_min_chars:
                try:
                    fm = QFontMetrics(self.table.font())
                    # grant_numbers は「半角15文字」目安なので数字幅で計算する
                    if col.key == "grant_numbers":
                        char_w = max(5, int(fm.horizontalAdvance("0")))
                    else:
                        char_w = max(6, int(fm.horizontalAdvance("W")))
                    min_w = char_w * int(major_min_chars.get(col.key, 20)) + 24
                    self.table.setColumnWidth(idx, max(int(self.table.columnWidth(idx)), int(min_w)))
                except Exception:
                    pass

        self._schedule_row_resize()

    def _show_loading(self, message: str) -> None:
        try:
            self.status_label.setText(str(message))
        except Exception:
            pass
        try:
            if self._spinner_overlay is None:
                return

            msg = str(message or "")

            # テーブルが表示済みなのにスピナーが被さると「表示されているのに読み込み中」に見える。
            # 更新系メッセージでは、既に行がある場合はステータスだけ更新してスピナーは出さない。
            has_rows = False
            try:
                has_rows = int(self._model.rowCount()) > 0 or int(self._filter_proxy.rowCount()) > 0
            except Exception:
                has_rows = False

            force_overlay = ("不足試料" in msg)
            allow_overlay = force_overlay or (not has_rows)

            if allow_overlay:
                self._spinner_overlay.set_message("読み込み中…")
                self._spinner_overlay.start()
            else:
                # 念のため、既に動いている場合は止める
                try:
                    self._spinner_overlay.stop()
                except Exception:
                    pass
        except Exception:
            pass

    def _hide_loading(self) -> None:
        try:
            if self._spinner_overlay is not None:
                self._spinner_overlay.stop()
        except Exception:
            pass

    def _visible_by_key(self) -> Dict[str, bool]:
        visible: Dict[str, bool] = {}
        for idx, col in enumerate(self._columns):
            try:
                visible[col.key] = not bool(self.table.isColumnHidden(idx))
            except Exception:
                visible[col.key] = True
        return visible

    def _apply_visible_by_key(self, visible_by_key: Dict[str, bool]) -> None:
        for idx, col in enumerate(self._columns):
            try:
                self.table.setColumnHidden(idx, not bool(visible_by_key.get(col.key, True)))
            except Exception:
                continue

    def _open_column_selector(self) -> None:
        dlg = ColumnSelectorDialog(self, self._columns, self._visible_by_key())
        if dlg.exec() != QDialog.Accepted:
            return
        self._apply_visible_by_key(dlg.get_visible_by_key())

    def _reset_columns_to_default(self) -> None:
        self._apply_columns()

    def _toggle_filters(self) -> None:
        self._filters_collapsed = not self._filters_collapsed
        try:
            self._column_filters_grid.parentWidget().setVisible(not self._filters_collapsed)
        except Exception:
            pass
        self._filters_summary_label.setVisible(self._filters_collapsed)
        self._toggle_filters_button.setText("フィルタ表示" if self._filters_collapsed else "フィルタ最小化")
        self._refresh_filters_summary()

    def _apply_compact_rows(self) -> None:
        try:
            self.table.setWordWrap(False)
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
            row_h = int(self.table.fontMetrics().height() * 1.6)
            if row_h > 0:
                self.table.verticalHeader().setDefaultSectionSize(row_h)
        except Exception:
            pass

    def _apply_equal_columns(self) -> None:
        try:
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Interactive)
            visible_cols = [c for c in range(self.table.model().columnCount()) if not self.table.isColumnHidden(c)]
            if not visible_cols:
                return
            viewport_w = int(self.table.viewport().width())
            if viewport_w <= 0:
                return
            each_w = max(80, int(viewport_w / len(visible_cols)) - 2)
            for col in visible_cols:
                self.table.setColumnWidth(col, each_w)
        except Exception:
            pass

    def _refresh_filters_summary(self) -> None:
        if not self._filters_collapsed:
            self._filters_summary_label.setText("")
            return
        parts: List[str] = []
        for col_index, col in enumerate(self._columns):
            if col_index in self._range_spins_by_col_index:
                mn_sp, mx_sp = self._range_spins_by_col_index[col_index]
                try:
                    mn_raw = int(mn_sp.value())
                    mx_raw = int(mx_sp.value())
                    mn = None if mn_raw < 0 else mn_raw
                    mx = None if mx_raw < 0 else mx_raw
                    if mn is None and mx is None:
                        continue
                    if mn is not None and mx is not None:
                        parts.append(f"{col.label}={mn}～{mx}")
                    elif mn is not None:
                        parts.append(f"{col.label}>={mn}")
                    elif mx is not None:
                        parts.append(f"{col.label}<={mx}")
                except Exception:
                    continue
                continue
            edit = self._filter_edits_by_col_index.get(col_index)
            if edit is None:
                continue
            text = str(edit.text() or "").strip()
            if not text:
                continue
            parts.append(f"{col.label}='{text}'")
        self._filters_summary_label.setText(" / ".join(parts) if parts else "（フィルタなし）")

    def _split_tile_dataset_grant_line(self, line: str) -> tuple[str, str, str]:
        try:
            sep = MultiLineCompositeLinkDelegate._SEP
            parts = str(line).split(sep)
            if len(parts) >= 3:
                tile = parts[0]
                dataset = parts[1]
                grant = sep.join(parts[2:])
                return tile, dataset, grant
            if len(parts) == 2:
                return parts[0], parts[1], ""
            return str(line), "", ""
        except Exception:
            return str(line), "", ""

    def _on_table_cell_hovered(self, index: object, pos: object) -> None:
        try:
            from PySide6.QtCore import QPoint

            if not isinstance(pos, QPoint):
                return
            self._update_link_hover_from_viewport_pos(pos)
        except Exception:
            return

    def _on_table_viewport_left(self) -> None:
        self._clear_link_hover_state()

    def _clear_link_hover_state(self) -> None:
        try:
            try:
                self.table.viewport().unsetCursor()
            except Exception:
                pass

            prev = getattr(self, "_hover_link_state", None)
            self._hover_link_state = None
            try:
                if self._multiline_link_delegate is not None:
                    setattr(self._multiline_link_delegate, "_hover_link_state", None)
            except Exception:
                pass
            try:
                if self._multiline_uuid_delegate is not None:
                    setattr(self._multiline_uuid_delegate, "_hover_link_state", None)
            except Exception:
                pass
            try:
                self.table.setProperty("_hover_link_state", None)
            except Exception:
                pass
            try:
                self.table.viewport().setProperty("_hover_link_state", None)
            except Exception:
                pass

            if isinstance(prev, tuple) and len(prev) == 3:
                prev_idx = self.table.model().index(int(prev[0]), int(prev[1]))
                if prev_idx.isValid():
                    self.table.viewport().update(self.table.visualRect(prev_idx))

            try:
                if self._hover_diag_enabled and self._hover_diag_label is not None:
                    self._hover_diag_last = "cleared"
                    self._hover_diag_label.setText(
                        f"[HOVER-DIAG] moves={self._hover_diag_moves} hits={self._hover_diag_hits} last={self._hover_diag_last}"
                    )
            except Exception:
                pass
        except Exception:
            return

    def _update_link_hover_from_viewport_pos(self, pos) -> None:
        """Update per-line hover state based on a viewport-relative mouse position."""
        try:
            try:
                if self._hover_diag_enabled:
                    self._hover_diag_moves += 1
            except Exception:
                pass

            index = self.table.indexAt(pos)
            if not index.isValid() or not (0 <= index.column() < len(self._columns)):
                self._clear_link_hover_state()
                return

            col_key = self._columns[index.column()].key
            try:
                col_label = str(self._columns[index.column()].label)
            except Exception:
                col_label = ""
            rect = self.table.visualRect(index)

            is_link = False
            hover_line_idx = -1

            # Throttled probe log for diagnosing per-column behavior.
            # This runs even when state does not change, but only when explicitly enabled.
            probe_enabled = bool(os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"))
            probe_now = 0.0
            if probe_enabled:
                try:
                    probe_now = time.monotonic()
                except Exception:
                    probe_now = 0.0

            if col_key in {"subgroup_id", "dataset_ids", "data_entry_ids", "sample_id"}:
                ur = index.data(Qt.UserRole)
                urls: List[str] = []
                if isinstance(ur, str):
                    u = ur.strip()
                    urls = [u] if u else []
                elif isinstance(ur, list):
                    urls = [str(x).strip() for x in ur if isinstance(x, str) and str(x).strip()]

                if urls:
                    text = str(index.data(Qt.DisplayRole) or "")
                    lines = [x for x in text.splitlines() if x.strip()] if text else []
                    max_lines = min(len(urls), max(1, len(lines)))
                    if max_lines <= 0:
                        max_lines = len(urls)
                    line_idx = self._line_index_in_cell(rect, int(pos.y()), max_lines)
                    if 0 <= line_idx < len(urls):
                        is_link = True
                        hover_line_idx = line_idx

                if probe_enabled:
                    try:
                        last_at = float(getattr(self, "_hover_probe_last_info_at", 0.0))
                    except Exception:
                        last_at = 0.0
                    try:
                        if probe_now and (probe_now - last_at) >= 1.0:
                            setattr(self, "_hover_probe_last_info_at", probe_now)
                            logger.info(
                                "[HOVER] probe row=%s col=%s key=%s label=%s urls=%s is_link=%s line=%s",
                                int(index.row()),
                                int(index.column()),
                                str(col_key),
                                str(col_label),
                                int(len(urls)),
                                bool(is_link),
                                int(hover_line_idx),
                            )
                    except Exception:
                        pass

            if not is_link and self._multiline_link_column_key and col_key == self._multiline_link_column_key:
                links = index.data(Qt.UserRole)
                if isinstance(links, list) and links:
                    text = str(index.data(Qt.DisplayRole) or "")
                    lines = [x for x in text.splitlines() if x] if text else []
                    line_idx = self._line_index_in_cell(rect, int(pos.y()), min(len(lines), len(links)))
                    if 0 <= line_idx < len(lines) and 0 <= line_idx < len(links):
                        item = links[line_idx]
                        if isinstance(item, dict):
                            entry_id = str(item.get("data_entry_id") or "").strip()
                            is_link = bool(entry_id)
                            if is_link:
                                hover_line_idx = line_idx

                if probe_enabled:
                    try:
                        text = str(index.data(Qt.DisplayRole) or "")
                        lines_count = len([x for x in text.splitlines() if x]) if text else 0
                    except Exception:
                        lines_count = 0
                    try:
                        links_count = len(links) if isinstance(links, list) else 0
                    except Exception:
                        links_count = 0
                    try:
                        last_at = float(getattr(self, "_hover_probe_last_info_at", 0.0))
                    except Exception:
                        last_at = 0.0
                    try:
                        if probe_now and (probe_now - last_at) >= 1.0:
                            setattr(self, "_hover_probe_last_info_at", probe_now)
                            logger.info(
                                "[HOVER] probe row=%s col=%s key=%s label=%s lines=%s links=%s is_link=%s line=%s",
                                int(index.row()),
                                int(index.column()),
                                str(col_key),
                                str(col_label),
                                int(lines_count),
                                int(links_count),
                                bool(is_link),
                                int(hover_line_idx),
                            )
                    except Exception:
                        pass

            try:
                if self._hover_diag_enabled:
                    if is_link:
                        self._hover_diag_hits += 1
                    self._hover_diag_last = f"row={int(index.row())} col={int(index.column())} key={col_key} line={int(hover_line_idx)} link={bool(is_link)}"
                    if self._hover_diag_label is not None:
                        self._hover_diag_label.setText(
                            f"[HOVER-DIAG] moves={self._hover_diag_moves} hits={self._hover_diag_hits} last={self._hover_diag_last}"
                        )
            except Exception:
                pass

            prev = getattr(self, "_hover_link_state", None)
            new_state = (
                (int(index.row()), int(index.column()), int(hover_line_idx))
                if is_link and hover_line_idx >= 0
                else None
            )
            if prev != new_state:
                self._hover_link_state = new_state
                try:
                    if self._multiline_link_delegate is not None:
                        setattr(self._multiline_link_delegate, "_hover_link_state", new_state)
                except Exception:
                    pass
                try:
                    if self._multiline_uuid_delegate is not None:
                        setattr(self._multiline_uuid_delegate, "_hover_link_state", new_state)
                except Exception:
                    pass
                try:
                    self.table.setProperty("_hover_link_state", new_state)
                except Exception:
                    pass
                try:
                    self.table.viewport().setProperty("_hover_link_state", new_state)
                except Exception:
                    pass

                # Diagnostics: confirm delegate-local hover state is actually set.
                try:
                    if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                        now = time.monotonic()
                        last_at = float(getattr(self, "_hover_delegate_state_diag_last_info_at", 0.0))
                        if (now - last_at) >= 1.0:
                            setattr(self, "_hover_delegate_state_diag_last_info_at", now)
                            link_state = getattr(getattr(self, "_multiline_link_delegate", None), "_hover_link_state", None)
                            uuid_state = getattr(getattr(self, "_multiline_uuid_delegate", None), "_hover_link_state", None)
                            logger.info(
                                "[HOVER-DELEGATE-STATE] new=%s link_delegate=%s uuid_delegate=%s",
                                str(new_state),
                                str(link_state),
                                str(uuid_state),
                            )
                except Exception:
                    pass

                # Optional diagnostics (guarded): confirm per-line hover is computed.
                try:
                    if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                        try:
                            col_label = str(col_label)
                        except Exception:
                            col_label = ""
                        logger.info(
                            "[HOVER] state %s -> %s key=%s label=%s is_link=%s line=%s",
                            str(prev),
                            str(new_state),
                            str(col_key),
                            str(col_label),
                            bool(is_link),
                            int(hover_line_idx),
                        )
                except Exception:
                    pass

                if isinstance(prev, tuple) and len(prev) == 3:
                    prev_idx = self.table.model().index(int(prev[0]), int(prev[1]))
                    if prev_idx.isValid():
                        self.table.viewport().update(self.table.visualRect(prev_idx))
                self.table.viewport().update(rect)

                # Force a synchronous repaint in diagnostics mode to rule out update scheduling issues.
                try:
                    if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                        # If per-rect repaint does not trigger delegate paint on some platforms/styles,
                        # repaint the whole viewport (diagnostics only).
                        self.table.viewport().repaint(rect)
                        self.table.viewport().repaint()
                except Exception:
                    pass

                # Diagnostics: confirm which delegate Qt will use for this specific index.
                try:
                    if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                        now = time.monotonic()
                        last_at = float(getattr(self, "_hover_delegate_index_diag_last_info_at", 0.0))
                        if (now - last_at) >= 1.0:
                            setattr(self, "_hover_delegate_index_diag_last_info_at", now)
                            try:
                                idx_delegate = self.table.itemDelegateForIndex(index)
                            except Exception:
                                idx_delegate = None
                            logger.info(
                                "[HOVER-DELEGATE-INDEX] row=%s col=%s key=%s delegate=%s updatesEnabled(view)=%s updatesEnabled(vp)=%s rect=%s",
                                int(index.row()),
                                int(index.column()),
                                str(col_key),
                                (type(idx_delegate).__name__ if idx_delegate is not None else "None"),
                                bool(self.table.updatesEnabled()),
                                bool(self.table.viewport().updatesEnabled()),
                                f"{int(rect.x())},{int(rect.y())},{int(rect.width())},{int(rect.height())}",
                            )
                except Exception:
                    pass

                # Diagnostics: confirm which delegate is actually installed for this column.
                try:
                    if os.environ.get("RDE_SAMPLE_DEDUP_HOVER_LOG"):
                        now = time.monotonic()
                        last_at = float(getattr(self, "_hover_delegate_diag_last_info_at", 0.0))
                        if (now - last_at) >= 1.0:
                            setattr(self, "_hover_delegate_diag_last_info_at", now)
                            d = None
                            try:
                                d = self.table.itemDelegateForColumn(int(index.column()))
                            except Exception:
                                d = None
                            logger.info(
                                "[HOVER-DELEGATE] col=%s key=%s delegate=%s is_multiline_link=%s is_multiline_uuid=%s",
                                int(index.column()),
                                str(col_key),
                                (type(d).__name__ if d is not None else "None"),
                                bool(d is not None and d is getattr(self, "_multiline_link_delegate", None)),
                                bool(d is not None and d is getattr(self, "_multiline_uuid_delegate", None)),
                            )
                except Exception:
                    pass

            try:
                if is_link:
                    self.table.viewport().setCursor(Qt.PointingHandCursor)
                else:
                    self.table.viewport().unsetCursor()
            except Exception:
                pass
        except Exception:
            return

    def eventFilter(self, obj: QObject, event: QObject) -> bool:  # noqa: N802
        try:
            if getattr(self, "table", None) is None:
                return super().eventFilter(obj, event)
            if obj is not self.table.viewport():
                return super().eventFilter(obj, event)

            from PySide6.QtCore import QEvent

            if event.type() == QEvent.Leave:
                self._clear_link_hover_state()
                return False

            if event.type() != QEvent.MouseMove:
                return super().eventFilter(obj, event)

            pos = event.pos()
            self._update_link_hover_from_viewport_pos(pos)

            return False
        except Exception:
            return super().eventFilter(obj, event)

    def _on_page_size_changed(self, value: int) -> None:
        self._paging_proxy.set_page_size(int(value))
        self._page.blockSignals(True)
        self._page.setValue(1)
        self._page.blockSignals(False)
        self._schedule_counts_refresh()

    def _on_page_changed(self, value: int) -> None:
        self._paging_proxy.set_page(int(value))
        self._schedule_counts_refresh()

    def _schedule_counts_refresh(self) -> None:
        try:
            self._ui_counts_timer.start()
        except Exception:
            self._refresh_counts()

    def _refresh_counts(self) -> None:
        total = 0
        filtered = 0
        try:
            total = int(self._model.rowCount())
            filtered = int(self._filter_proxy.rowCount())
        except Exception:
            pass

        try:
            self._paging_proxy._normalize_page()
            total_pages = int(self._paging_proxy.total_pages())
        except Exception:
            total_pages = 1

        try:
            self._page.setMaximum(max(1, total_pages))
            self._total_pages.setText(str(max(1, total_pages)))
        except Exception:
            pass

        self.status_label.setText(f"表示件数: {filtered}/{total} 件")
        self._refresh_filters_summary()

    def reload_data(self, auto_fetch: bool = False) -> None:
        self._load_from_cache_and_refresh_if_needed(auto_fetch=auto_fetch, force_refresh=True)

    def _load_prefilter_choices(self) -> None:
        # Role choices mimic dataset_open_logic
        self._pref_role.clear()
        self._pref_role.addItem("管理者 または 管理者代理", "owner_assistant")
        self._pref_role.addItem("管理者 のみ", "owner")
        self._pref_role.addItem("管理者代理 のみ", "assistant")
        self._pref_role.addItem("フィルタなし（全て）", "none")
        self._pref_role.setCurrentIndex(0)

        self._pref_subgroup.clear()
        self._pref_subgroup.addItem("フィルタなし", "")

        self._pref_grant.clear()
        self._pref_grant.addItem("フィルタなし", "")

        self._install_combo_search(self._pref_subgroup, placeholder="サブグループを検索")
        self._install_combo_search(self._pref_grant, placeholder="課題番号を検索")

        # Initial cascade
        self._refresh_prefilter_choices(cascade_from="role")

    def _install_combo_search(self, combo: QComboBox, *, placeholder: str) -> None:
        try:
            le = combo.lineEdit()
            if le is not None:
                le.setPlaceholderText(placeholder)
        except Exception:
            pass

        try:
            # Build completer from current items.
            texts = [combo.itemText(i) for i in range(combo.count())]
            completer = QCompleter(texts, combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            popup = completer.popup()
            popup.setMinimumHeight(240)
            popup.setMaximumHeight(240)
            combo.setCompleter(completer)
        except Exception:
            return

    def _refresh_combo_completer(self, combo: QComboBox) -> None:
        try:
            completer = combo.completer()
            if completer is None:
                return
            texts = [combo.itemText(i) for i in range(combo.count())]
            completer.model().setStringList(texts)  # type: ignore[attr-defined]
        except Exception:
            # Fallback: replace completer
            self._install_combo_search(combo, placeholder="")

    def _bind_prefilter_signals(self) -> None:
        # Role changes affect subgroup list, which affects grant list.
        self._pref_role.currentIndexChanged.connect(lambda *_: self._on_prefilter_changed("role"))
        self._pref_subgroup.currentIndexChanged.connect(lambda *_: self._on_prefilter_changed("subgroup"))
        self._pref_grant.currentIndexChanged.connect(lambda *_: self._on_prefilter_changed("grant"))

        # Also react when user types (search) and commits.
        try:
            if self._pref_subgroup.lineEdit():
                self._pref_subgroup.lineEdit().editingFinished.connect(lambda: self._commit_combo_text(self._pref_subgroup))
        except Exception:
            pass
        try:
            if self._pref_grant.lineEdit():
                self._pref_grant.lineEdit().editingFinished.connect(lambda: self._commit_combo_text(self._pref_grant))
        except Exception:
            pass

        # Completer activation should also commit & apply.
        try:
            c = self._pref_subgroup.completer()
            if c is not None:
                c.activated.connect(lambda *_: self._commit_combo_text(self._pref_subgroup))
        except Exception:
            pass
        try:
            c = self._pref_grant.completer()
            if c is not None:
                c.activated.connect(lambda *_: self._commit_combo_text(self._pref_grant))
        except Exception:
            pass

    def _commit_combo_text(self, combo: QComboBox) -> None:
        # If the user typed exact text, select the matching item; otherwise keep current selection.
        try:
            text = _safe_str(combo.currentText()).strip()
            if not text or text == "フィルタなし":
                idx = combo.findData("")
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setCurrentIndex(0)
                return
            idx = combo.findText(text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        except Exception:
            return

    def _on_prefilter_changed(self, source: str) -> None:
        if self._suppress_prefilter_signals:
            return

        # Cascade lists.
        if source == "role":
            self._refresh_prefilter_choices(cascade_from="role")
        elif source == "subgroup":
            self._refresh_prefilter_choices(cascade_from="subgroup")

        # Auto apply (debounced).
        try:
            self._prefilter_apply_timer.start()
        except Exception:
            self._apply_prefilters_now()

    def _apply_prefilters_now(self) -> None:
        if self._suppress_prefilter_signals:
            return
        # Do not force refresh on every change; cache is still used.
        self._load_from_cache_and_refresh_if_needed(auto_fetch=False, force_refresh=False)

    def _refresh_prefilter_choices(self, *, cascade_from: str) -> None:
        state = self._current_prefilter_state()

        groups = self._load_subgroup_metadata()
        role_groups = self._filter_groups_by_role(groups, state.role_filter)
        if not role_groups and groups and state.role_filter not in {"none"}:
            role_groups = groups

        # Build subgroup list
        subgroup_order: List[str] = []
        subgroup_name_by_id: Dict[str, str] = {}
        subjects_by_id: Dict[str, List[Dict[str, Any]]] = {}
        for g in role_groups:
            gid = _safe_str(g.get("id")).strip()
            attrs = g.get("attributes") if isinstance(g.get("attributes"), dict) else {}
            name = _safe_str(attrs.get("name") or "").strip()
            subjects = attrs.get("subjects") if isinstance(attrs.get("subjects"), list) else []
            if gid:
                subgroup_order.append(gid)
                subgroup_name_by_id[gid] = name
                subjects_by_id[gid] = [s for s in subjects if isinstance(s, dict)]

        # Update subgroup combo when role changed.
        if cascade_from == "role":
            current_gid = state.subgroup_id
            self._suppress_prefilter_signals = True
            try:
                self._pref_subgroup.blockSignals(True)
                self._pref_subgroup.clear()
                self._pref_subgroup.addItem("フィルタなし", "")
                for gid in subgroup_order:
                    label = subgroup_name_by_id.get(gid) or gid
                    self._pref_subgroup.addItem(label, gid)
                if current_gid:
                    idx = self._pref_subgroup.findData(current_gid)
                    if idx >= 0:
                        self._pref_subgroup.setCurrentIndex(idx)
                    else:
                        self._pref_subgroup.setCurrentIndex(0)
            finally:
                try:
                    self._pref_subgroup.blockSignals(False)
                except Exception:
                    pass
                self._suppress_prefilter_signals = False
            self._refresh_combo_completer(self._pref_subgroup)

        # Grant list depends on subgroup selection (after subgroup combo is updated).
        selected_gid = _safe_str(self._pref_subgroup.currentData()).strip()
        if selected_gid:
            target_subjects = subjects_by_id.get(selected_gid, [])
        else:
            # All subgroups in role scope.
            target_subjects = []
            for gid in subgroup_order:
                target_subjects.extend(subjects_by_id.get(gid, []))

        grants: List[str] = []
        seen: set[str] = set()
        for s in target_subjects:
            gn = _safe_str(s.get("grantNumber")).strip()
            if not gn or gn in seen:
                continue
            seen.add(gn)
            grants.append(gn)

        # Update grant combo when role/subgroup changed.
        if cascade_from in {"role", "subgroup"}:
            current_grant_text = _safe_str(self._pref_grant.currentText()).strip()
            current_grant_data = _safe_str(self._pref_grant.currentData()).strip()
            current_grant = current_grant_data or ("" if current_grant_text == "フィルタなし" else current_grant_text)

            self._suppress_prefilter_signals = True
            try:
                self._pref_grant.blockSignals(True)
                self._pref_grant.clear()
                self._pref_grant.addItem("フィルタなし", "")
                for gn in grants:
                    self._pref_grant.addItem(gn, gn)
                if current_grant:
                    idx = self._pref_grant.findData(current_grant)
                    if idx >= 0:
                        self._pref_grant.setCurrentIndex(idx)
                    else:
                        # If previously selected grant no longer valid under subgroup selection, reset.
                        self._pref_grant.setCurrentIndex(0)
            finally:
                try:
                    self._pref_grant.blockSignals(False)
                except Exception:
                    pass
                self._suppress_prefilter_signals = False
            self._refresh_combo_completer(self._pref_grant)

    def _current_prefilter_state(self) -> _PreFilterState:
        grant_data = _safe_str(self._pref_grant.currentData()).strip()
        grant_text = _safe_str(self._pref_grant.currentText()).strip()
        grant_number = grant_data or ("" if grant_text == "フィルタなし" else grant_text)
        return _PreFilterState(
            role_filter=_safe_str(self._pref_role.currentData()).strip() or "owner_assistant",
            subgroup_id=_safe_str(self._pref_subgroup.currentData()).strip(),
            grant_number=grant_number,
        )

    def _load_subgroup_metadata(self) -> List[Dict[str, Any]]:
        """Read subGroup.json (local) and return TEAM group entries."""
        from config.common import get_dynamic_file_path
        import json

        path = get_dynamic_file_path("output/rde/data/subGroup.json")
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return []
        included = payload.get("included") if isinstance(payload, dict) else []
        if not isinstance(included, list):
            return []
        groups: List[Dict[str, Any]] = []
        for item in included:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "group":
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            if (attrs.get("groupType") or "") != "TEAM":
                continue
            groups.append(item)
        return groups

    def _filter_groups_by_role(self, groups: List[Dict[str, Any]], role_filter: str) -> List[Dict[str, Any]]:
        """Subset of dataset_open_logic.filter_groups_by_role (UI-free)."""
        role_filter = str(role_filter or "").strip() or "owner_assistant"
        if role_filter == "none":
            return groups

        user_id = ""
        try:
            from config.common import get_dynamic_file_path
            import json

            self_path = get_dynamic_file_path("output/rde/data/self.json")
            if self_path and os.path.exists(self_path):
                with open(self_path, "r", encoding="utf-8") as f:
                    self_payload = json.load(f)
                user_id = str((self_payload.get("data") or {}).get("id") or "").strip()
        except Exception:
            user_id = ""

        out: List[Dict[str, Any]] = []
        for g in groups:
            attrs = g.get("attributes") if isinstance(g.get("attributes"), dict) else {}
            roles = attrs.get("roles") if isinstance(attrs.get("roles"), list) else []
            user_role = None
            for r in roles:
                if not isinstance(r, dict):
                    continue
                if user_id and r.get("userId") != user_id:
                    continue
                user_role = r.get("role")
                break

            if role_filter == "owner_assistant":
                if user_role in ["OWNER", "ASSISTANT"]:
                    out.append(g)
            elif role_filter == "owner":
                if user_role == "OWNER":
                    out.append(g)
            elif role_filter == "assistant":
                if user_role == "ASSISTANT":
                    out.append(g)
            else:
                out.append(g)
        return out

    def _extract_grant_numbers(self, groups: List[Dict[str, Any]]) -> List[str]:
        grants: List[str] = []
        seen: set[str] = set()
        for g in groups:
            attrs = g.get("attributes") if isinstance(g.get("attributes"), dict) else {}
            subjects = attrs.get("subjects") if isinstance(attrs.get("subjects"), list) else []
            for s in subjects:
                if not isinstance(s, dict):
                    continue
                gn = _safe_str(s.get("grantNumber")).strip()
                if not gn or gn in seen:
                    continue
                seen.add(gn)
                grants.append(gn)
        return grants

    def _compute_target_subgroup_ids(self, state: _PreFilterState) -> tuple[List[str], List[str]]:
        # NOTE: combo population is handled by _refresh_prefilter_choices(), which is called
        # on role/subgroup changes. Here we only compute target subgroup ids.
        groups = self._load_subgroup_metadata()
        filtered_groups = self._filter_groups_by_role(groups, state.role_filter)
        if not filtered_groups and groups and state.role_filter not in {"none"}:
            filtered_groups = groups

        subgroup_order: List[str] = []
        subjects_by_id: Dict[str, List[Dict[str, Any]]] = {}
        for g in filtered_groups:
            gid = _safe_str(g.get("id")).strip()
            attrs = g.get("attributes") if isinstance(g.get("attributes"), dict) else {}
            subjects = attrs.get("subjects") if isinstance(attrs.get("subjects"), list) else []
            if gid:
                subgroup_order.append(gid)
                subjects_by_id[gid] = [s for s in subjects if isinstance(s, dict)]

        # Determine target subgroup ids
        selected_gid = state.subgroup_id
        selected_grant = state.grant_number

        if selected_gid:
            subgroup_ids = [selected_gid]
        else:
            subgroup_ids = list(subgroup_order)

        if selected_grant:
            # filter subgroup ids by grant number existence
            allowed: set[str] = set()
            for g in filtered_groups:
                gid = _safe_str(g.get("id")).strip()
                if not gid or gid not in set(subgroup_ids):
                    continue
                subjects = subjects_by_id.get(gid, [])
                if any(_safe_str(s.get("grantNumber")).strip() == selected_grant for s in subjects):
                    allowed.add(gid)
            subgroup_ids = [gid for gid in subgroup_ids if gid in allowed]

        return subgroup_ids, subgroup_order

    def _load_from_cache_and_refresh_if_needed(self, *, auto_fetch: bool, force_refresh: bool = False) -> None:
        state = self._current_prefilter_state()
        subgroup_ids, subgroup_order = self._compute_target_subgroup_ids(state)

        explicit_scope = bool(state.subgroup_id) or bool(state.grant_number)

        # If subgroup metadata is unavailable (or role-based filtering yields nothing),
        # subgroup_ids can become empty even though local sample files exist.
        # In that case, treat it as "show all" rather than "filter to nothing".
        allow_all_without_metadata = (not explicit_scope) and (not subgroup_ids)

        # Prefilter explicitly set to "none" should also show all.
        want_all = (not explicit_scope) and (state.role_filter in {"none"})

        # 1) Show cache immediately
        cache_payload = load_sample_listing_cache()
        cache_order = cache_payload.get("subgroup_order") if isinstance(cache_payload, dict) else []
        subgroup_order_for_cache = subgroup_order or (cache_order if isinstance(cache_order, list) else [])
        cached_rows = extract_cached_rows(
            cache_payload,
            subgroup_ids=([] if allow_all_without_metadata else subgroup_ids),
            subgroup_order=subgroup_order_for_cache,
        )
        if cached_rows:
            self._model.set_columns(self._columns)
            self._model.set_rows(cached_rows)
            self._apply_columns()
            self._schedule_counts_refresh()

        if os.environ.get("PYTEST_CURRENT_TEST"):
            return

        # 2) Refresh decision (signature -> TTL -> manual)
        signature = compute_sample_listing_sources_signature()
        cache_fresh = is_sample_listing_cache_fresh(cache_payload, sources_signature=signature, ttl_seconds=_SAMPLE_LISTING_CACHE_TTL_SECONDS)
        if force_refresh:
            cache_fresh = False

        if cache_fresh and cached_rows:
            # Still allow missing fetch if requested.
            if auto_fetch:
                self._maybe_auto_fetch_missing_from_current_model()
            return

        # Decide subgroup scope for the records layer.
        subgroup_scope: List[str] | None
        if want_all or allow_all_without_metadata:
            subgroup_scope = None
        else:
            subgroup_scope = subgroup_ids

        effective_order = subgroup_order or subgroup_order_for_cache
        self._start_refresh_thread(subgroup_ids=subgroup_scope, subgroup_order=effective_order, signature=signature, auto_fetch=auto_fetch)

    def _load_without_cache_and_refresh(self, *, auto_fetch: bool) -> None:
        state = self._current_prefilter_state()
        subgroup_ids, subgroup_order = self._compute_target_subgroup_ids(state)

        explicit_scope = bool(state.subgroup_id) or bool(state.grant_number)
        allow_all_without_metadata = (not explicit_scope) and (not subgroup_ids)
        want_all = (not explicit_scope) and (state.role_filter in {"none"})

        signature = compute_sample_listing_sources_signature()
        subgroup_scope: List[str] | None
        if want_all or allow_all_without_metadata:
            subgroup_scope = None
        else:
            subgroup_scope = subgroup_ids

        if os.environ.get("PYTEST_CURRENT_TEST"):
            return

        self._start_refresh_thread(subgroup_ids=subgroup_scope, subgroup_order=subgroup_order, signature=signature, auto_fetch=auto_fetch)

    def _maybe_auto_fetch_missing_from_current_model(self) -> None:
        # Try to detect missing_sample rows and auto-fetch.
        missing: List[str] = []
        for row in self._model._rows:
            if not isinstance(row, dict):
                continue
            if bool(row.get("missing_sample")):
                sid = _safe_str(row.get("subgroup_id")).strip()
                if sid:
                    missing.append(sid)
        if missing:
            self.fetch_button.setEnabled(True)
            self._start_fetch_thread(missing)
        else:
            self.fetch_button.setEnabled(False)

    def _start_refresh_thread(self, *, subgroup_ids: List[str] | None, subgroup_order: List[str], signature: Dict[str, Any], auto_fetch: bool) -> None:
        if self._refresh_thread is not None and self._refresh_thread.isRunning():
            return

        self._show_loading("試料一覧を更新中...")

        class _RefreshThread(QThread):
            completed = Signal(object, object, object, object)

            def __init__(self, subgroup_ids: List[str] | None, subgroup_order: List[str], signature: Dict[str, Any], parent: QObject):
                super().__init__(parent)
                self._subgroup_ids = list(subgroup_ids) if subgroup_ids is not None else None
                self._subgroup_order = list(subgroup_order)
                self._signature = dict(signature)

            def run(self):
                columns: object = []
                rows: object = []
                missing: object = []
                err = ""
                try:
                    columns, rows, missing = self.parent()._rows_builder(self._subgroup_ids)  # type: ignore[attr-defined]
                except Exception as e:
                    err = str(e)
                    try:
                        logger.exception("[SAMPLE-LIST] refresh failed: %s", err)
                    except Exception:
                        pass
                meta = {"subgroup_order": self._subgroup_order, "signature": self._signature}
                if err:
                    meta["error"] = err
                try:
                    self.completed.emit(columns, rows, missing, meta)
                except Exception:
                    pass

        self._refresh_thread = _RefreshThread(subgroup_ids, subgroup_order, signature, self)
        self._refresh_thread.completed.connect(lambda cols, rows, missing, meta: self._on_refresh_completed(cols, rows, missing, meta, auto_fetch))
        try:
            # Safety net: even if the thread crashes before emitting, hide the spinner.
            self._refresh_thread.finished.connect(self._hide_loading)
        except Exception:
            pass
        self._refresh_thread.start()

    def _on_refresh_completed(self, columns: object, rows: object, missing: object, meta: object, auto_fetch: bool) -> None:
        self._hide_loading()

        meta_dict = meta if isinstance(meta, dict) else {}
        err = str(meta_dict.get("error") or "").strip()
        if err:
            # Keep current table as-is and surface the error.
            try:
                self.status_label.setText(f"試料一覧更新に失敗: {err}")
            except Exception:
                pass
            return

        if isinstance(columns, list):
            self._columns = [c for c in columns if isinstance(c, SampleDedupColumn)]
        if isinstance(rows, list):
            new_rows = [r for r in rows if isinstance(r, dict)]
        else:
            new_rows = []

        # Update model
        self._model.set_columns(self._columns)
        self._model.update_rows_partially(new_rows)
        self._rebuild_column_filters()
        self._apply_columns()

        missing_ids = [str(x).strip() for x in (missing or []) if str(x).strip()]
        if missing_ids:
            self.fetch_button.setEnabled(True)
            if auto_fetch:
                self._start_fetch_thread(missing_ids)
        else:
            self.fetch_button.setEnabled(False)

        self._schedule_counts_refresh()

        if not self._cache_enabled:
            return

        # Merge into cache (partial refresh per subgroup)
        subgroup_order = meta_dict.get("subgroup_order") if isinstance(meta_dict.get("subgroup_order"), list) else []
        signature = meta_dict.get("signature") if isinstance(meta_dict.get("signature"), dict) else {}
        state = self._current_prefilter_state()
        subgroup_ids, _ = self._compute_target_subgroup_ids(state)
        cache_payload = load_sample_listing_cache()
        merged = merge_rows_into_cache(
            cache_payload,
            subgroup_ids=subgroup_ids,
            subgroup_order=subgroup_order,
            rows=new_rows,
            sources_signature=signature,
        )
        save_sample_listing_cache(merged)

    def _export(self, kind: str) -> None:
        kind = str(kind or "").strip().lower()
        if kind not in {"csv", "xlsx"}:
            return

        # Export filtered rows (ignores paging).
        visible_cols: List[SampleDedupColumn] = []
        for idx, col in enumerate(self._columns):
            if self.table.isColumnHidden(idx):
                continue
            visible_cols.append(col)

        data: List[Dict[str, Any]] = []
        for row_idx in range(int(self._filter_proxy.rowCount())):
            src_index = self._filter_proxy.index(row_idx, 0)
            if not src_index.isValid():
                continue
            base_row_idx = src_index.row()
            try:
                row_dict = self._model.get_rows()[base_row_idx]
            except Exception:
                continue
            out: Dict[str, Any] = {}
            for col in visible_cols:
                out[col.label] = row_dict.get(col.key)
            data.append(out)

        if not data:
            QMessageBox.information(self, "出力", "出力対象の行がありません")
            return

        default_name = f"sample_listing_{time.strftime('%Y%m%d_%H%M%S')}"
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

            df = pd.DataFrame(data)
            if kind == "csv":
                df.to_csv(path, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(path, index=False)
            QMessageBox.information(self, "出力", f"出力しました: {path}")
        except Exception as e:
            QMessageBox.warning(self, "出力失敗", f"出力に失敗しました: {e}")

    def _start_fetch_thread(self, missing: List[str]) -> None:
        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        self._show_loading("不足試料を取得中...")
        self._fetch_thread = SampleFetchThread(missing, self)
        self._fetch_thread.completed.connect(self._on_fetch_completed)
        self._fetch_thread.start()

    def _fetch_missing_samples(self) -> None:
        # Recompute missing for current prefilter scope.
        state = self._current_prefilter_state()
        subgroup_ids, _subgroup_order = self._compute_target_subgroup_ids(state)
        _columns, _rows, missing = self._rows_builder(subgroup_ids)
        missing = [str(x).strip() for x in (missing or []) if str(x).strip()]

        if not missing:
            QMessageBox.information(self, "試料取得", "不足試料はありません")
            self.fetch_button.setEnabled(False)
            return
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        self._start_fetch_thread(missing)

    def _on_fetch_completed(self, message: str) -> None:
        self._hide_loading()
        self.status_label.setText(message)
        self._load_from_cache_and_refresh_if_needed(auto_fetch=False, force_refresh=True)

    def resizeEvent(self, event):  # noqa: N802
        try:
            self._filter_relayout_timer.start()
        except Exception:
            pass
        return super().resizeEvent(event)
