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
from datetime import datetime
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
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from classes.data_portal.util.public_output_paths import get_public_data_portal_cache_dir
from classes.data_portal.util.managed_csv_paths import build_managed_csv_path, find_latest_managed_csv, format_mtime_jst, format_size
from classes.data_portal.util.managed_suffix_grouping import add_grouped_suffix_columns
from classes.ui.utilities.listing_support import prepare_display_value
from classes.ui.utilities.listing_table import ListingFilterProxyModel

from classes.theme import ThemeKey, get_color
from classes.theme import get_qcolor

from classes.data_portal.core.portal_csv_full import (
    extract_code as extract_managed_code,
    extract_dataset_id as extract_managed_dataset_id,
    parse_portal_csv_payload_to_records,
)
from classes.data_portal.core.portal_entry_merge import merge_public_and_managed

LOGGER = logging.getLogger(__name__)


class _SourceAwareProxyModel(ListingFilterProxyModel):
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

        self._columns: list[_ColumnDef] = []
        self._visible_columns: set[str] = set()
        self._column_index: dict[str, int] = {}

        self._filters_container: Optional[QWidget] = None
        self._filters_layout: Optional[QGridLayout] = None
        self._filters_scroll: Optional[QScrollArea] = None
        self._filter_field_widgets: list[tuple[str, QWidget]] = []
        self._filter_edits_by_key: dict[str, QLineEdit] = {}
        self._filters_collapsed: bool = False
        self._filter_apply_timer: Optional[QtCore.QTimer] = None

        self._filter_mode: str = "all"  # all | group
        self._filter_group_kind: str = "fixed"  # fixed | managed_group | managed_raw
        self._did_apply_initial_width: bool = False

        self._setup_ui()
        self.refresh_public_from_disk()
        self.refresh_managed_from_disk()

        # 認証情報が保存済みなら、初回表示から管理CSV取得まで自動で進める
        # （接続テストや「保存」操作を必須にしない）
        if not self._is_running_under_pytest():
            try:
                from qt_compat.core import QTimer

                QTimer.singleShot(0, self.refresh_managed_from_portal)
            except Exception:
                pass

    @staticmethod
    def _is_running_under_pytest() -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST"))

    def set_portal_client(self, portal_client: Any) -> None:
        self._portal_client = portal_client

    def set_environment(self, environment: str) -> None:
        env = str(environment or "production").strip() or "production"
        if env == self._environment:
            return
        self._environment = env
        # 環境が切り替わったら、管理側は取り直し（別環境の結果を混ぜない）
        self._managed_records = []
        self._portal_client = None
        self.status_label.setText(f"環境切替: {env}（管理CSVは未取得）")
        self.refresh_public_from_disk()
        self.refresh_managed_from_disk()
        if not self._is_running_under_pytest():
            try:
                from qt_compat.core import QTimer

                QTimer.singleShot(0, self.refresh_managed_from_portal)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("📋 データポータル 一覧（公開 + 管理）")
        title.setObjectName("portalListingTitle")
        layout.addWidget(title)

        controls = QHBoxLayout()
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

        self.toggle_filters_btn = QPushButton("フィルタ最小化", self)
        self.toggle_filters_btn.clicked.connect(self._toggle_filters_panel)
        controls.addWidget(self.toggle_filters_btn)

        self.filters_all_btn = QPushButton("全体表示", self)
        self.filters_all_btn.setCheckable(True)
        self.filters_all_btn.setChecked(True)
        self.filters_all_btn.clicked.connect(lambda: self._set_filter_mode("all"))
        controls.addWidget(self.filters_all_btn)

        self.filters_group_btn = QPushButton("グル", self)
        self.filters_group_btn.setCheckable(True)
        self.filters_group_btn.setChecked(False)
        self.filters_group_btn.clicked.connect(lambda: self._set_filter_mode("group"))
        controls.addWidget(self.filters_group_btn)

        self.filters_group_combo = QComboBox(self)
        self.filters_group_combo.addItem("基本", "fixed")
        self.filters_group_combo.addItem("管理(結合)", "managed_group")
        self.filters_group_combo.addItem("管理(その他)", "managed_raw")
        self.filters_group_combo.setVisible(False)
        self.filters_group_combo.currentIndexChanged.connect(self._on_filter_group_changed)
        controls.addWidget(self.filters_group_combo)

        self.reload_public = QPushButton("公開cache再読込")
        self.reload_public.clicked.connect(self.refresh_public_from_disk)
        controls.addWidget(self.reload_public)

        self.reload_managed = QPushButton("管理CSV更新")
        self.reload_managed.clicked.connect(self.refresh_managed_from_portal)
        controls.addWidget(self.reload_managed)

        self.select_columns_btn = QPushButton("表示列…")
        self.select_columns_btn.clicked.connect(self._on_select_columns)
        controls.addWidget(self.select_columns_btn)

        self.count_label = QLabel("0件")
        controls.addWidget(self.count_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Per-column filters (visible columns only)
        self.filters_group_box = QGroupBox("列フィルタ", self)
        self.filters_group_box.setCheckable(True)
        self.filters_group_box.setChecked(True)
        self.filters_group_box.toggled.connect(self._on_filters_group_toggled)

        filters_outer = QVBoxLayout(self.filters_group_box)
        filters_outer.setContentsMargins(8, 8, 8, 8)
        filters_outer.setSpacing(6)

        self._filters_scroll = QScrollArea(self.filters_group_box)
        self._filters_scroll.setWidgetResizable(True)
        self._filters_scroll.setFrameStyle(0)
        try:
            self._filters_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._filters_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        except Exception:
            pass
        self._filters_container = QWidget(self._filters_scroll)
        self._filters_container.setObjectName("portal_listing_filters_container")
        self._filters_layout = QGridLayout(self._filters_container)
        self._filters_layout.setContentsMargins(0, 0, 0, 0)
        self._filters_layout.setHorizontalSpacing(8)
        self._filters_layout.setVerticalSpacing(6)
        self._filters_scroll.setWidget(self._filters_container)
        filters_outer.addWidget(self._filters_scroll)

        layout.addWidget(self.filters_group_box)

        from qt_compat.widgets import QtWidgets

        self.table_model = QtGui.QStandardItemModel(0, 0, self)

        self.proxy_model = _SourceAwareProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.modelReset.connect(self._update_count)
        self.proxy_model.layoutChanged.connect(self._update_count)
        self.proxy_model.rowsInserted.connect(self._update_count)
        self.proxy_model.rowsRemoved.connect(self._update_count)

        self.table_view = QtWidgets.QTableView()
        self.table_view.setModel(self.proxy_model)
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
        self.table_view.verticalHeader().setVisible(False)
        try:
            self.table_view.doubleClicked.connect(self._on_table_double_clicked)
        except Exception:
            pass
        layout.addWidget(self.table_view, stretch=1)

        # Debounce filter application to keep the table responsive.
        self._filter_apply_timer = QtCore.QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.timeout.connect(self._apply_filters_now)

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._did_apply_initial_width or self._is_running_under_pytest():
            return
        self._did_apply_initial_width = True
        try:
            win = self.window()
            screen = win.screen() if win is not None else None
            if screen is None:
                screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            target_w = int(avail.width() * 0.9)
            if target_w > 0 and win is not None:
                win.resize(target_w, win.height())
        except Exception:
            pass

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

    def refresh_theme(self) -> None:
        # Theme integration for this tab is minimal; widgets inherit palette/QSS.
        try:
            self.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def refresh_public_from_disk(self) -> None:
        public = self._load_public_cache_records()
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

    def refresh_managed_from_portal(self) -> None:
        if self._is_running_under_pytest():
            # テスト環境ではネットワークアクセスを避け、保存済みCSVのみ読む
            self.refresh_managed_from_disk()
            return
        # PortalClient が無い/環境が違う場合は、保存済み認証情報から自動生成する。
        if self._portal_client is None or str(getattr(self._portal_client, "environment", "")) != self._environment:
            try:
                from classes.data_portal.core.auth_manager import get_auth_manager
                from classes.data_portal.core.portal_client import PortalClient

                auth = get_auth_manager()
                cred = auth.get_credentials(self._environment)
                if cred is None:
                    self.status_label.setText(
                        f"⚠️ 管理CSV更新: {self._environment} の認証情報が未登録です（ログイン設定で保存してください）"
                    )
                    return
                client = PortalClient(self._environment)
                client.set_credentials(cred)
                self._portal_client = client
            except Exception as exc:
                self.status_label.setText(f"⚠️ 管理CSV更新: PortalClient生成に失敗: {exc}")
                return
        if self._thread is not None and self._thread.isRunning():
            self.status_label.setText("管理CSVを取得中...（処理中）")
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

    def _load_public_cache_records(self) -> list[dict]:
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
        return records

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

        # Columns already mapped into fixed keys should not be shown as redundant managed:* columns.
        # (These are the most common overlaps between managed CSV and public cache.)
        suppressed_managed_keys = set(suppressed_managed_keys or set())
        suppressed_managed_keys.update(
            {
                "managed:機関",
                "managed:実施機関",
                "managed:登録日",
                "managed:エンバーゴ解除日",
                "managed:エンバーゴ期間終了日",
                "managed:ライセンス",
                "managed:ライセンスレベル",
                "managed:キーワードタグ",
                "managed:タグ",
                "managed:URL",
                "managed:リンク",
                "managed:タイトル",
                "managed:課題名",
                "managed:要約",
            }
        )

        # Build columns (fixed + CSV-derived)
        fixed = [
            _ColumnDef("source", "範囲", preview_limit=16, default_visible=False),
            _ColumnDef("code", "code", preview_limit=64, default_visible=True),
            _ColumnDef("dataset_id", "dataset_id", preview_limit=120, default_visible=True),
            _ColumnDef("managed_status", "管理ステータス", preview_limit=64, default_visible=True),
            _ColumnDef("title", "タイトル", preview_limit=180, default_visible=True),
            _ColumnDef("url", "URL", preview_limit=220, default_visible=False),
            _ColumnDef("organization", "実施機関", preview_limit=120, default_visible=True),
            _ColumnDef("registered_date", "登録日", preview_limit=64, default_visible=True),
            _ColumnDef("embargo_release_date", "エンバーゴ解除日", preview_limit=64, default_visible=False),
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

    def _toggle_filters_panel(self, *, force: Optional[bool] = None) -> None:
        if force is None:
            self._filters_collapsed = not self._filters_collapsed
        else:
            self._filters_collapsed = bool(force)

        try:
            if hasattr(self, "filters_group_box") and self.filters_group_box is not None:
                self.filters_group_box.blockSignals(True)
                self.filters_group_box.setChecked(not self._filters_collapsed)
                self.filters_group_box.blockSignals(False)
        except Exception:
            pass

        if self._filters_scroll is not None:
            self._filters_scroll.setVisible(not self._filters_collapsed)
        try:
            self.toggle_filters_btn.setText("フィルタ表示" if self._filters_collapsed else "フィルタ最小化")
        except Exception:
            pass

    def _on_filters_group_toggled(self, checked: bool) -> None:
        # checked=True means expanded (not collapsed)
        self._filters_collapsed = not bool(checked)
        if self._filters_scroll is not None:
            self._filters_scroll.setVisible(not self._filters_collapsed)
        try:
            self.toggle_filters_btn.setText("フィルタ表示" if self._filters_collapsed else "フィルタ最小化")
        except Exception:
            pass

    def _set_filter_mode(self, mode: str) -> None:
        m = str(mode or "all")
        if m not in ("all", "group"):
            m = "all"
        self._filter_mode = m
        try:
            self.filters_all_btn.setChecked(m == "all")
            self.filters_group_btn.setChecked(m == "group")
            self.filters_group_combo.setVisible(m == "group")
        except Exception:
            pass
        self._rebuild_filters_panel([c for c in self._columns if c.key in self._visible_columns or c.key == "source"])

    def _on_filter_group_changed(self) -> None:
        try:
            self._filter_group_kind = str(self.filters_group_combo.currentData() or "fixed")
        except Exception:
            self._filter_group_kind = "fixed"
        self._rebuild_filters_panel([c for c in self._columns if c.key in self._visible_columns or c.key == "source"])

    @staticmethod
    def _format_filter_label(label: str) -> str:
        text = str(label or "")
        if text.startswith("管理:"):
            inner = text.replace("管理:", "", 1)
            return f"【{inner}】"
        return text

    def _relayout_filter_fields(self) -> None:
        if self._filters_layout is None or not self._filter_field_widgets:
            return

        available_w = 0
        try:
            if self._filters_scroll is not None:
                available_w = int(self._filters_scroll.viewport().width())
        except Exception:
            available_w = 0
        if available_w <= 0:
            try:
                available_w = int(self.width())
            except Exception:
                available_w = 600

        field_w = min(300, max(220, available_w))
        per_row = max(1, int(max(available_w, 1) // max(field_w, 1)))

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

        # Auto-shrink filter area height when fewer filter fields are shown.
        try:
            hint_h = int(self._filters_container.sizeHint().height())
            cap = 220
            target = max(60, min(hint_h + 8, cap))
            if self._filters_scroll is not None:
                self._filters_scroll.setMaximumHeight(target)
        except Exception:
            pass

    def _populate(self, rows: list[dict[str, Any]]) -> None:
        from qt_compat import QtGui

        visible_cols = [c for c in self._columns if c.key in self._visible_columns or c.key == "source"]
        self._column_index = {c.key: idx for idx, c in enumerate(visible_cols)}

        self._rebuild_filters_panel(visible_cols)

        self.table_model.clear()
        self.table_model.setColumnCount(len(visible_cols))
        self.table_model.setHorizontalHeaderLabels([c.label for c in visible_cols])

        for row in rows:
            items = []
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
                        if col.key in ("keyword_tags",) and "," in val and "\n" not in val:
                            parts = [p.strip() for p in val.split(",") if p.strip()]
                            if len(parts) >= 2:
                                val = "\n".join([f"・{p}" for p in parts])
                except Exception:
                    pass

                display, tooltip = prepare_display_value(val, col.preview_limit)
                item = QtGui.QStandardItem(display)
                item.setEditable(False)

                # Title behaves like a link (opens row URL) even when URL column is hidden.
                if col.key == "title":
                    try:
                        url = str(row.get("url") or "").strip()
                        if url:
                            item.setData(url, Qt.ItemDataRole.UserRole)
                            f = item.font()
                            f.setUnderline(True)
                            item.setFont(f)
                            item.setForeground(QtGui.QBrush(get_qcolor(ThemeKey.TEXT_LINK)))
                            extra = f"URL: {url}"
                            tooltip = (tooltip + "\n\n" if tooltip else "") + extra
                    except Exception:
                        pass

                try:
                    origin = (row.get("_cell_origin") or {}).get(col.key)
                    diff = (row.get("_cell_diff") or {}).get(col.key)
                    if diff:
                        item.setBackground(QtGui.QBrush(get_qcolor(ThemeKey.PANEL_INFO_BACKGROUND)))
                        note = f"公開: {diff.get('public','')}\n管理: {diff.get('managed','')}"
                        tooltip = (tooltip + "\n\n" if tooltip else "") + note
                    elif origin == "public":
                        item.setBackground(QtGui.QBrush(get_qcolor(ThemeKey.PANEL_WARNING_BACKGROUND)))
                        note = "管理CSVに値が無いため公開cache由来です"
                        tooltip = (tooltip + "\n\n" if tooltip else "") + note
                except Exception:
                    pass

                if tooltip and tooltip != display:
                    item.setToolTip(tooltip)
                items.append(item)
            self.table_model.appendRow(items)

        try:
            self.table_view.resizeRowsToContents()
        except Exception:
            pass

        # Keep source hidden even after rebuild
        src_idx = self._column_index.get("source", -1)
        if src_idx >= 0:
            self.table_view.setColumnHidden(src_idx, True)
            self.proxy_model.set_source_column(src_idx)

        # Apply current filters after model rebuild
        self._schedule_apply_filters()

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
        self._update_count()

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
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
