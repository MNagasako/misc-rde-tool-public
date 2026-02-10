"""
データポータル 一括タブ

データカタログ向けの一括操作テーブルを提供する。
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from qt_compat.core import Qt, QTimer
from qt_compat.gui import QIcon, QPixmap
from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QRadioButton,
    QCheckBox,
    QButtonGroup,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDialog,
    QDialogButtonBox,
    QScrollArea,
    QFileDialog,
    QMenu,
)

from classes.managers.log_manager import get_logger
from classes.theme import ThemeKey, get_color, get_qcolor
from classes.utils.button_styles import get_button_style
from config.common import get_dynamic_file_path

from classes.dataset.util.dataset_list_table_records import build_dataset_list_rows_from_files


def _check_global_sharing_enabled(dataset_item: Dict[str, Any]) -> bool:
    global_share = dataset_item.get("attributes", {}).get("globalShareDataset")
    is_open = dataset_item.get("attributes", {}).get("isOpen", False)
    return bool(global_share) if global_share is not None else bool(is_open)


def _get_current_user_id() -> str:
    try:
        self_path = get_dynamic_file_path("output/rde/data/self.json")
        with open(self_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return str(data.get("data", {}).get("id") or "").strip()
    except Exception:
        return ""


def _check_user_is_member(dataset_item: Dict[str, Any], user_id: str) -> bool:
    if not user_id:
        return False
    relationships = dataset_item.get("relationships", {})

    manager = relationships.get("manager", {}).get("data", {})
    if isinstance(manager, dict) and manager.get("id") == user_id:
        return True

    data_owners = relationships.get("dataOwners", {}).get("data", [])
    if isinstance(data_owners, list):
        for owner in data_owners:
            if isinstance(owner, dict) and owner.get("id") == user_id:
                return True

    applicant = relationships.get("applicant", {}).get("data", {})
    if isinstance(applicant, dict) and applicant.get("id") == user_id:
        return True

    return False


def _check_dataset_type_match(dataset_item: Dict[str, Any], dataset_type_filter: str) -> bool:
    if dataset_type_filter == "all":
        return True
    dataset_type = dataset_item.get("attributes", {}).get("datasetType", "")
    return dataset_type == dataset_type_filter


def _check_grant_number_match(dataset_item: Dict[str, Any], grant_number_filter: str) -> bool:
    if not grant_number_filter:
        return True
    grant_number = dataset_item.get("attributes", {}).get("grantNumber", "")
    return str(grant_number_filter).lower() in str(grant_number).lower()


def _get_dataset_type_display_map() -> Dict[str, str]:
    return {
        "ANALYSIS": "解析",
        "RECIPE": "レシピ",
        "MEASUREMENT": "測定",
        "SIMULATION": "シミュレーション",
        "OTHERS": "その他",
    }

logger = get_logger("DataPortal.BulkTab")


@dataclass(frozen=True)
class _BulkColumnDef:
    key: str
    label: str
    default_visible: bool = True


class _BulkColumnSelectDialog(QDialog):
    def __init__(self, columns: list[_BulkColumnDef], visible_keys: set[str], parent: Optional[QWidget] = None):
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

    def get_selected_keys(self) -> set[str]:
        selected: set[str] = set()
        for key, cb in (self._checkbox_by_key or {}).items():
            try:
                if cb.isChecked():
                    selected.add(key)
            except Exception:
                continue
        return selected


class DataPortalBulkTab(QWidget):
    """データポータル一括操作タブ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._portal_widget = parent
        self._rows_by_id: Dict[str, Dict[str, Any]] = {}
        self._rows_list: list[Dict[str, Any]] = []
        self._filtered_ids: list[str] = []
        self._user_name_by_id: Dict[str, str] = {}
        self._user_org_by_id: Dict[str, str] = {}
        self._refresh_timer: Optional[QTimer] = None
        self._cache_dirty = True
        self._filter_signature: Tuple[str, str, str, str, str, str, str, str] | None = None
        self._org_options: list[str] = []
        self._portal_client = None
        self._portal_client_env: Optional[str] = None
        self._portal_client_ready = False
        self._portal_client_failed = False
        self._image_count_cache: Dict[Tuple[str, str], Tuple[int, Optional[int]]] = {}
        self._t_code_cache: Dict[Tuple[str, str], str] = {}
        self._existing_images_cache: Dict[Tuple[str, str], set[str]] = {}
        self._page_size = 50
        self._current_page = 1
        self._total_pages = 1
        self._current_environment: str = "production"
        self._column_defs = self._build_column_defs()
        self._visible_columns = {c.key for c in self._column_defs if c.default_visible}
        self._display_mode = "default"
        self._report_institute_by_task: Dict[str, str] = {}
        self._report_institute_by_code: Dict[str, str] = {}
        self._json_status_options: list[str] = []
        self._json_action_options: list[str] = []
        self._init_ui()
        self._schedule_refresh()

        try:
            from classes.theme.theme_manager import ThemeManager

            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        env_group = self._create_environment_group()
        layout.addWidget(env_group)

        filter_group = self._create_filter_group()
        layout.addWidget(filter_group)

        controls_row = self._create_display_controls_row()
        layout.addLayout(controls_row)

        self.table = QTableWidget(0, len(self._column_defs), self)
        self.table.setHorizontalHeaderLabels([col.label for col in self._column_defs])
        self.table.setSortingEnabled(True)
        if self._display_mode != "default":
            self._apply_display_mode(self._display_mode, force=True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(True)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(60)

        self._apply_table_column_sizes()
        self._apply_table_style()
        self._apply_column_visibility()

        layout.addWidget(self.table, 1)

        pagination_row = self._create_pagination_row()
        layout.addLayout(pagination_row)

        self._connect_filter_signals()

    def _create_environment_group(self) -> QGroupBox:
        group = QGroupBox("環境選択")
        layout = QHBoxLayout(group)

        layout.addWidget(QLabel("対象環境:"))

        self.env_combo = QComboBox()
        self.env_combo.currentIndexChanged.connect(self._on_environment_changed)
        layout.addWidget(self.env_combo)

        self.env_status_label = QLabel("")
        self.env_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        layout.addWidget(self.env_status_label)
        layout.addStretch()

        self._load_environments()
        self._sync_environment_from_parent()
        return group

    def _create_filter_group(self) -> QGroupBox:
        group = QGroupBox("データセット抽出")
        layout = QVBoxLayout(group)

        radio_style = (
            f"QRadioButton {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }} "
            f"QRadioButton::indicator {{ width:16px; height:16px; border:1px solid {get_color(ThemeKey.INPUT_BORDER)}; "
            f"background:{get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius:8px; }} "
            f"QRadioButton::indicator:checked {{ background:{get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}"
        )

        share_row = QHBoxLayout()
        share_row.addWidget(QLabel("広域シェア:"))
        self.share_button_group = QButtonGroup(self)
        self.share_both_radio = QRadioButton("両方")
        self.share_both_radio.setStyleSheet(radio_style)
        self.share_enabled_radio = QRadioButton("有効のみ")
        self.share_enabled_radio.setStyleSheet(radio_style)
        self.share_disabled_radio = QRadioButton("無効のみ")
        self.share_disabled_radio.setStyleSheet(radio_style)
        self.share_button_group.addButton(self.share_both_radio, 0)
        self.share_button_group.addButton(self.share_enabled_radio, 1)
        self.share_button_group.addButton(self.share_disabled_radio, 2)
        self.share_both_radio.setChecked(True)
        share_row.addWidget(self.share_both_radio)
        share_row.addWidget(self.share_enabled_radio)
        share_row.addWidget(self.share_disabled_radio)
        share_row.addStretch()
        layout.addLayout(share_row)

        member_row = QHBoxLayout()
        member_row.addWidget(QLabel("関係メンバー:"))
        self.member_button_group = QButtonGroup(self)
        self.member_both_radio = QRadioButton("両方")
        self.member_both_radio.setStyleSheet(radio_style)
        self.member_only_radio = QRadioButton("メンバーのみ")
        self.member_only_radio.setStyleSheet(radio_style)
        self.member_non_radio = QRadioButton("非メンバーのみ")
        self.member_non_radio.setStyleSheet(radio_style)
        self.member_button_group.addButton(self.member_both_radio, 0)
        self.member_button_group.addButton(self.member_only_radio, 1)
        self.member_button_group.addButton(self.member_non_radio, 2)
        self.member_both_radio.setChecked(True)
        member_row.addWidget(self.member_both_radio)
        member_row.addWidget(self.member_only_radio)
        member_row.addWidget(self.member_non_radio)
        member_row.addStretch()
        layout.addLayout(member_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("データセットタイプ:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("全て", "all")
        for dtype, label in _get_dataset_type_display_map().items():
            self.type_combo.addItem(label, dtype)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        layout.addLayout(type_row)

        grant_row = QHBoxLayout()
        grant_row.addWidget(QLabel("課題番号:"))
        self.grant_edit = QLineEdit()
        self.grant_edit.setPlaceholderText("部分一致で検索（例: JPMXP1234）")
        self.grant_edit.setMinimumWidth(260)
        grant_row.addWidget(self.grant_edit)
        grant_row.addStretch()
        layout.addLayout(grant_row)

        org_row = QHBoxLayout()
        org_row.addWidget(QLabel("実施機関:"))
        self.org_combo = QComboBox()
        self.org_combo.addItem("全て", "all")
        self.org_combo.setMinimumWidth(320)
        org_row.addWidget(self.org_combo)
        org_row.addStretch()
        layout.addLayout(org_row)

        json_action_row = QHBoxLayout()
        json_action_row.addWidget(QLabel("書誌情報JSON:"))
        self.json_action_combo = QComboBox()
        self.json_action_combo.addItem("全て", "all")
        self.json_action_combo.setMinimumWidth(320)
        json_action_row.addWidget(self.json_action_combo)
        json_action_row.addStretch()
        layout.addLayout(json_action_row)

        json_status_row = QHBoxLayout()
        json_status_row.addWidget(QLabel("状態:"))
        self.json_status_combo = QComboBox()
        self.json_status_combo.addItem("全て", "all")
        self.json_status_combo.setMinimumWidth(240)
        json_status_row.addWidget(self.json_status_combo)
        json_status_row.addStretch()
        layout.addLayout(json_status_row)

        registrant_row = QHBoxLayout()
        registrant_row.addWidget(QLabel("登録者:"))
        self.registrant_edit = QLineEdit()
        self.registrant_edit.setPlaceholderText("部分一致で検索")
        self.registrant_edit.setMinimumWidth(200)
        registrant_row.addWidget(self.registrant_edit)
        registrant_row.addStretch()
        layout.addLayout(registrant_row)

        refresh_row = QHBoxLayout()
        self.refresh_btn = QPushButton("一覧更新")
        self.refresh_btn.setStyleSheet(get_button_style("secondary"))
        self.refresh_btn.clicked.connect(self._invalidate_cache)
        refresh_row.addWidget(self.refresh_btn)

        self.count_label = QLabel("表示件数: 0")
        self.count_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        refresh_row.addWidget(self.count_label)
        refresh_row.addStretch()
        layout.addLayout(refresh_row)

        return group

    def _create_pagination_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.prev_page_btn = QPushButton("◀ 前へ")
        self.prev_page_btn.setStyleSheet(get_button_style("secondary"))
        self.prev_page_btn.clicked.connect(self._go_prev_page)
        row.addWidget(self.prev_page_btn)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self._on_page_changed)
        row.addWidget(self.page_spin)

        self.page_total_label = QLabel("/ 1")
        self.page_total_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        row.addWidget(self.page_total_label)

        self.next_page_btn = QPushButton("次へ ▶")
        self.next_page_btn.setStyleSheet(get_button_style("secondary"))
        self.next_page_btn.clicked.connect(self._go_next_page)
        row.addWidget(self.next_page_btn)

        row.addStretch()

        row.addWidget(QLabel("件数/ページ:"))
        self.page_size_combo = QComboBox()
        for size in (50, 100, 200, 500):
            self.page_size_combo.addItem(str(size), size)
        self.page_size_combo.setCurrentText(str(self._page_size))
        self.page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        row.addWidget(self.page_size_combo)

        self.page_range_label = QLabel("")
        self.page_range_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        row.addWidget(self.page_range_label)

        return row

    def _apply_table_column_sizes(self) -> None:
        try:
            self.table.setColumnWidth(0, 140)
            self.table.setColumnWidth(1, 100)
            self.table.setColumnWidth(2, 110)
            self.table.setColumnWidth(3, 220)
            self.table.setColumnWidth(4, 220)
            self.table.setColumnWidth(5, 160)
            self.table.setColumnWidth(6, 220)
            self.table.setColumnWidth(7, 140)
            self.table.setColumnWidth(8, 160)
            self.table.setColumnWidth(9, 170)
            self.table.setColumnWidth(10, 120)
            self.table.setColumnWidth(11, 120)
            for col in range(12, 17):
                self.table.setColumnWidth(col, 170)
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        except Exception:
            pass

    def _apply_table_style(self) -> None:
        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                gridline-color: {get_color(ThemeKey.BORDER_DEFAULT)};
            }}
            QHeaderView::section {{
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_SECONDARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                padding: 4px 6px;
                font-weight: bold;
            }}
            QTableWidget::item:selected {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
            }}
            """
        )

    def _connect_filter_signals(self) -> None:
        self.share_button_group.buttonClicked.connect(self._on_filter_changed)
        self.member_button_group.buttonClicked.connect(self._on_filter_changed)
        self.type_combo.currentTextChanged.connect(self._on_filter_changed)
        self.grant_edit.textChanged.connect(self._on_filter_changed)
        self.org_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.registrant_edit.textChanged.connect(self._on_filter_changed)
        self.json_action_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.json_status_combo.currentIndexChanged.connect(self._on_filter_changed)

    def _build_column_defs(self) -> list[_BulkColumnDef]:
        return [
            _BulkColumnDef("json_action", "書誌情報JSON"),
            _BulkColumnDef("json_status", "状態"),
            _BulkColumnDef("grant_number", "課題番号"),
            _BulkColumnDef("task_name", "課題名"),
            _BulkColumnDef("dataset_name", "データセット名"),
            _BulkColumnDef("subgroup_name", "サブグループ"),
            _BulkColumnDef("subgroup_description", "サブグループ説明"),
            _BulkColumnDef("registrant_name", "登録者"),
            _BulkColumnDef("registrant_org", "登録者所属"),
            _BulkColumnDef("institution", "実施機関"),
            _BulkColumnDef("image_downloaded", "画像取得済"),
            _BulkColumnDef("image_uploaded", "画像UP済"),
            _BulkColumnDef("image_action", "画像ファイル"),
            _BulkColumnDef("zip_action", "コンテンツZIPアップロード"),
            _BulkColumnDef("edit_action", "データカタログ修正"),
            _BulkColumnDef("open_action", "ブラウザで表示"),
            _BulkColumnDef("status_action", "ステータス変更"),
        ]

    def _create_display_controls_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.select_columns_btn = QPushButton("表示列…", self)
        self.select_columns_btn.clicked.connect(self._on_select_columns)
        row.addWidget(self.select_columns_btn)

        row.addSpacing(12)

        row.addWidget(QLabel("表示切替:"))
        self.compact_rows_btn = QPushButton("1行表示", self)
        self.compact_rows_btn.clicked.connect(lambda: self._apply_display_mode("compact"))
        row.addWidget(self.compact_rows_btn)

        self.equal_columns_btn = QPushButton("列幅そろえ", self)
        self.equal_columns_btn.clicked.connect(lambda: self._apply_display_mode("equal"))
        row.addWidget(self.equal_columns_btn)

        export_menu = QMenu(self)
        export_csv = export_menu.addAction("CSV出力")
        export_csv.triggered.connect(lambda: self._export("csv"))
        export_xlsx = export_menu.addAction("XLSX出力")
        export_xlsx.triggered.connect(lambda: self._export("xlsx"))

        self.export_btn = QPushButton("エクスポート", self)
        self.export_btn.setMenu(export_menu)
        row.addWidget(self.export_btn)

        row.addStretch()
        return row

    def _load_environments(self) -> None:
        from ..conf.config import get_data_portal_config

        config = get_data_portal_config()
        environments = config.get_available_environments()

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
            portal = self._portal_widget
            login_tab = getattr(portal, "login_settings_tab", None) if portal else None
            combo = getattr(login_tab, "env_combo", None) if login_tab else None
            env = combo.currentData() if combo is not None else None
        except Exception:
            env = None

        env = str(env or "production").strip() or "production"
        self._current_environment = env
        self._apply_environment_label(env)

        for idx in range(self.env_combo.count()):
            if self.env_combo.itemData(idx) == env:
                self.env_combo.setCurrentIndex(idx)
                break

    def _apply_environment_label(self, env: str) -> None:
        if env == "test":
            self.env_status_label.setText("🧪 テスト環境")
        else:
            self.env_status_label.setText("✅ 本番環境")

    def _on_environment_changed(self, _index: int) -> None:
        try:
            env = self.env_combo.currentData()
        except Exception:
            env = None
        env = str(env or "production").strip() or "production"
        self._current_environment = env
        self._apply_environment_label(env)

        try:
            portal = self._portal_widget
            login_tab = getattr(portal, "login_settings_tab", None) if portal else None
            combo = getattr(login_tab, "env_combo", None) if login_tab else None
            if combo is not None:
                for idx in range(combo.count()):
                    if combo.itemData(idx) == env:
                        combo.setCurrentIndex(idx)
                        break
        except Exception:
            pass

        self._portal_client_failed = False
        self._portal_client_ready = False
        self._portal_client = None
        self._portal_client_env = None
        self._schedule_refresh()

    def _invalidate_cache(self) -> None:
        self._cache_dirty = True
        self._image_count_cache.clear()
        self._t_code_cache.clear()
        self._existing_images_cache.clear()
        self._report_institute_by_task = {}
        self._report_institute_by_code = {}
        self._json_status_options = []
        self._json_action_options = []
        self._schedule_refresh()

    def _on_filter_changed(self) -> None:
        self._current_page = 1
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._refresh_table)
        self._refresh_timer.start(120)

    def refresh_theme(self) -> None:
        self._apply_table_style()
        self.count_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        self.env_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        self.page_total_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        self.page_range_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        self.refresh_btn.setStyleSheet(get_button_style("secondary"))
        self.prev_page_btn.setStyleSheet(get_button_style("secondary"))
        self.next_page_btn.setStyleSheet(get_button_style("secondary"))
        self.select_columns_btn.setStyleSheet(get_button_style("secondary"))
        self.compact_rows_btn.setStyleSheet(get_button_style("secondary"))
        self.equal_columns_btn.setStyleSheet(get_button_style("secondary"))
        self.export_btn.setStyleSheet(get_button_style("secondary"))
        self.update()

    def _refresh_table(self) -> None:
        try:
            self._ensure_dataset_cache()
            self._refresh_json_action_options()
            self._refresh_json_status_options()
            self._update_filtered_ids()
            self._render_page()
        except Exception as exc:
            logger.error("Bulk table refresh failed: %s", exc)
            QMessageBox.warning(self, "エラー", "一括テーブルの更新に失敗しました")
        finally:
            try:
                self.table.setSortingEnabled(True)
            except Exception:
                pass

    def _ensure_dataset_cache(self) -> None:
        if not self._cache_dirty:
            return

        _cols, rows = build_dataset_list_rows_from_files()
        self._rows_list = list(rows)
        self._rows_by_id = {
            str(row.get("dataset_id") or "").strip(): row
            for row in rows
            if str(row.get("dataset_id") or "").strip()
        }
        self._ensure_raw_payloads()
        self._load_user_maps()
        self._ensure_report_institute_cache()
        self._refresh_org_options()
        self._refresh_json_status_options()
        self._cache_dirty = False

    def _ensure_report_institute_cache(self) -> None:
        task_map, code_map = self._build_report_institute_map()
        self._report_institute_by_task = task_map
        self._report_institute_by_code = code_map

    def _build_report_institute_map(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        try:
            from classes.dataset.util.report_listing_helper import load_latest_report_records
        except Exception:
            return {}, {}

        records = load_latest_report_records()
        mapping: Dict[str, str] = {}
        code_mapping: Dict[str, str] = {}
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            task_number = self._first_non_empty_in_record(
                rec,
                (
                    "課題番号",
                    "課題番号 / Project Issue Number",
                    "ARIMNO",
                ),
            )
            institute = self._first_non_empty_in_record(
                rec,
                (
                    "利用した実施機関 / Support Institute",
                    "利用した実施機関",
                    "Support Institute",
                ),
            )
            task_number = str(task_number or "").strip()
            institute = self._normalize_institute_name(str(institute or "").strip())
            if not task_number or not institute:
                continue
            for key in self._expand_task_number_keys(task_number):
                mapping.setdefault(key, institute)
            inst_code = self._extract_institution_code_from_task(task_number)
            if inst_code and inst_code not in code_mapping:
                code_mapping[inst_code] = institute
        return mapping, code_mapping

    @staticmethod
    def _first_non_empty_in_record(record: Dict[str, Any], keys: Tuple[str, ...]) -> str:
        for key in keys:
            value = record.get(key)
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _expand_task_number_keys(task_number: str) -> set[str]:
        raw = str(task_number or "").strip()
        if not raw:
            return set()
        keys = {raw}
        if raw.startswith("JPMXP12"):
            keys.add(raw.replace("JPMXP12", "", 1))
        return keys

    @staticmethod
    def _extract_institution_code_from_task(task_number: str) -> str:
        raw = str(task_number or "").strip()
        if not raw:
            return ""
        text = raw
        if text.startswith("JPMXP12"):
            text = text.replace("JPMXP12", "", 1)
        match = re.search(r"^(\d{2})([A-Z]{2})", text)
        if match:
            return match.group(2)
        match = re.search(r"JPMXP12\d{2}([A-Z]{2})", raw)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _normalize_institute_name(name: str) -> str:
        text = str(name or "").strip()
        if not text:
            return ""
        if "/" in text:
            text = text.split("/", 1)[0]
        return text.strip()

    def _resolve_institution_name(self, grant_number: str) -> str:
        task = str(grant_number or "").strip()
        if not task:
            return ""
        for key in self._expand_task_number_keys(task):
            name = self._report_institute_by_task.get(key)
            if name:
                return str(name).strip()
        inst_code = self._extract_institution_code_from_task(task)
        if inst_code:
            name = self._report_institute_by_code.get(inst_code)
            if name:
                return str(name).strip()
        return ""

    def _refresh_org_options(self) -> None:
        orgs: list[str] = []
        seen = set()

        for row in self._rows_list:
            grant_number = str(row.get("grant_number") or "").strip()
            org = self._resolve_institution_name(grant_number)
            org = str(org or "").strip()
            if not org or org in seen:
                continue
            seen.add(org)
            orgs.append(org)

        orgs.sort()
        self._org_options = orgs

        current = str(self.org_combo.currentData() or "all") if hasattr(self, "org_combo") else "all"
        self.org_combo.blockSignals(True)
        self.org_combo.clear()
        self.org_combo.addItem("全て", "all")
        for org in orgs:
            self.org_combo.addItem(org, org)
        if current != "all":
            for idx in range(self.org_combo.count()):
                if self.org_combo.itemData(idx) == current:
                    self.org_combo.setCurrentIndex(idx)
                    break
        self.org_combo.blockSignals(False)

    def _refresh_json_status_options(self) -> None:
        labels: list[str] = []
        seen = set()

        for row in self._rows_list:
            dataset_id = str(row.get("dataset_id") or "").strip()
            if not dataset_id:
                continue
            label = str(self._get_json_upload_status_label(dataset_id) or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            labels.append(label)

        labels.sort()
        self._json_status_options = labels

        if not hasattr(self, "json_status_combo"):
            return
        current = str(self.json_status_combo.currentData() or "all")
        self.json_status_combo.blockSignals(True)
        self.json_status_combo.clear()
        self.json_status_combo.addItem("全て", "all")
        for label in labels:
            self.json_status_combo.addItem(label, label)
        if current != "all":
            for idx in range(self.json_status_combo.count()):
                if self.json_status_combo.itemData(idx) == current:
                    self.json_status_combo.setCurrentIndex(idx)
                    break
        self.json_status_combo.blockSignals(False)

    def _refresh_json_action_options(self) -> None:
        labels: list[str] = []
        seen = set()

        for row in self._rows_list:
            dataset_id = str(row.get("dataset_id") or "").strip()
            if not dataset_id:
                continue
            status_label = str(self._get_json_upload_status_label(dataset_id) or "").strip()
            action_label, _style, _icon = self._get_json_action_presentation(status_label)
            action_label = str(action_label or "").strip()
            if not action_label or action_label in seen:
                continue
            seen.add(action_label)
            labels.append(action_label)

        labels.sort()
        self._json_action_options = labels

        if not hasattr(self, "json_action_combo"):
            return
        current = str(self.json_action_combo.currentData() or "all")
        self.json_action_combo.blockSignals(True)
        self.json_action_combo.clear()
        self.json_action_combo.addItem("全て", "all")
        for label in labels:
            self.json_action_combo.addItem(label, label)
        if current != "all":
            for idx in range(self.json_action_combo.count()):
                if self.json_action_combo.itemData(idx) == current:
                    self.json_action_combo.setCurrentIndex(idx)
                    break
        self.json_action_combo.blockSignals(False)

    def _ensure_raw_payloads(self) -> None:
        if not self._rows_list:
            return

        needs_raw = any(not isinstance(row.get("_raw"), dict) for row in self._rows_list)
        if not needs_raw:
            return

        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        try:
            with open(dataset_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            logger.warning("Bulk tab could not load dataset.json: %s", exc)
            return

        data_items = []
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            data_items = [it for it in payload.get("data") if isinstance(it, dict)]
        elif isinstance(payload, list):
            data_items = [it for it in payload if isinstance(it, dict)]

        if not data_items:
            return

        raw_by_id = {
            str(item.get("id") or "").strip(): item
            for item in data_items
            if str(item.get("id") or "").strip()
        }

        if not raw_by_id:
            return

        for row in self._rows_list:
            if isinstance(row.get("_raw"), dict):
                continue
            dataset_id = str(row.get("dataset_id") or "").strip()
            if not dataset_id:
                continue
            raw_item = raw_by_id.get(dataset_id)
            if isinstance(raw_item, dict):
                row["_raw"] = raw_item

    def _update_filtered_ids(self) -> None:
        share_filter_types = {0: "both", 1: "enabled", 2: "disabled"}
        member_filter_types = {0: "both", 1: "member", 2: "non_member"}

        share_filter = share_filter_types.get(self.share_button_group.checkedId(), "both")
        member_filter = member_filter_types.get(self.member_button_group.checkedId(), "both")
        dtype_filter = str(self.type_combo.currentData() or "all")
        grant_filter = str(self.grant_edit.text() or "").strip()
        org_filter = str(self.org_combo.currentData() or "all")
        registrant_filter = str(self.registrant_edit.text() or "").strip()
        if hasattr(self, "json_action_combo"):
            json_action_filter = str(self.json_action_combo.currentData() or "all")
        else:
            json_action_filter = "all"
        if hasattr(self, "json_status_combo"):
            json_filter = str(self.json_status_combo.currentData() or "all")
        else:
            json_filter = "all"

        signature = (
            share_filter,
            member_filter,
            dtype_filter,
            grant_filter,
            org_filter,
            registrant_filter,
            json_action_filter,
            json_filter,
        )
        if signature == self._filter_signature and self._filtered_ids:
            return
        self._filter_signature = signature

        user_id = _get_current_user_id() or ""

        filtered: list[str] = []
        for row in self._rows_list:
            dataset_id = str(row.get("dataset_id") or "").strip()
            if not dataset_id:
                continue
            raw_item = row.get("_raw")
            if not isinstance(raw_item, dict):
                continue

            is_share_enabled = _check_global_sharing_enabled(raw_item)
            if share_filter == "enabled" and not is_share_enabled:
                continue
            if share_filter == "disabled" and is_share_enabled:
                continue

            is_member = _check_user_is_member(raw_item, user_id) if user_id else False
            if member_filter == "member" and not is_member:
                continue
            if member_filter == "non_member" and is_member:
                continue

            if not _check_dataset_type_match(raw_item, dtype_filter):
                continue
            if not _check_grant_number_match(raw_item, grant_filter):
                continue

            registrant_name, registrant_org = self._resolve_registrant_info(row)
            grant_number = str(row.get("grant_number") or raw_item.get("attributes", {}).get("grantNumber") or "").strip()
            institute_name = self._resolve_institution_name(grant_number)
            if org_filter != "all" and institute_name != org_filter:
                continue
            if registrant_filter:
                if registrant_filter.lower() not in str(registrant_name or "").lower():
                    continue
            if json_action_filter != "all":
                status_label = str(self._get_json_upload_status_label(dataset_id) or "").strip()
                action_label, _style, _icon = self._get_json_action_presentation(status_label)
                if str(action_label or "").strip() != json_action_filter:
                    continue
            if json_filter != "all":
                status_label = str(self._get_json_upload_status_label(dataset_id) or "").strip()
                if status_label != json_filter:
                    continue

            filtered.append(dataset_id)

        self._filtered_ids = filtered
        self._current_page = 1

    def _render_page(self) -> None:
        total = len(self._filtered_ids)
        self.count_label.setText(f"表示件数: {total}")

        self._total_pages = max(1, int(math.ceil(total / max(self._page_size, 1))))
        self._current_page = max(1, min(self._current_page, self._total_pages))

        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(self._total_pages)
        self.page_spin.setValue(self._current_page)
        self.page_spin.blockSignals(False)
        self.page_total_label.setText(f"/ {self._total_pages}")

        start_index = (self._current_page - 1) * self._page_size
        end_index = min(start_index + self._page_size, total)
        self.page_range_label.setText(f"表示範囲: {start_index + 1 if total else 0}-{end_index} / {total}")

        page_ids = self._filtered_ids[start_index:end_index]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(page_ids))

        for row_index, dataset_id in enumerate(page_ids):
            row = self._rows_by_id.get(dataset_id, {})
            dataset_item = row.get("_raw")
            if not isinstance(dataset_item, dict):
                dataset_item = {}
            attrs = dataset_item.get("attributes") if isinstance(dataset_item.get("attributes"), dict) else {}

            grant_number = str(row.get("grant_number") or attrs.get("grantNumber") or "").strip()
            task_name = str(
                row.get("subject_title")
                or row.get("subjectTitle")
                or attrs.get("subjectTitle")
                or ""
            ).strip()
            if not task_name:
                task_name = str(row.get("subgroup_name") or "").strip()
            dataset_name = str(row.get("dataset_name") or attrs.get("name") or "").strip()
            subgroup_name = str(row.get("subgroup_name") or "").strip()
            subgroup_description = str(row.get("subgroup_description") or "").strip()

            registrant_name, registrant_org = self._resolve_registrant_info(row)
            registrant_org = registrant_org or ""
            org_name = self._resolve_institution_name(grant_number)
            json_status_label = self._get_json_upload_status_label(dataset_id)

            downloaded_count, uploaded_count = self._get_image_counts(dataset_id, grant_number, dataset_name)
            downloaded_text = f"{downloaded_count}" if downloaded_count is not None else "-"
            uploaded_text = f"{uploaded_count}" if uploaded_count is not None else "-"

            json_button_label, json_style_kind, json_icon = self._get_json_action_presentation(json_status_label)

            self._set_action_cell(
                row_index,
                0,
                dataset_id,
                json_button_label,
                json_style_kind,
                "upload_json",
                icon=json_icon,
                tooltip=json_status_label,
            )
            self._set_item(row_index, 1, json_status_label)
            self._set_item(row_index, 2, grant_number)
            self._set_item(row_index, 3, task_name)
            self._set_item(row_index, 4, dataset_name)
            self._set_item(row_index, 5, subgroup_name)
            self._set_item(row_index, 6, subgroup_description)
            self._set_item(row_index, 7, registrant_name)
            self._set_item(row_index, 8, registrant_org)
            self._set_item(row_index, 9, org_name)
            self._set_item(row_index, 10, downloaded_text)
            self._set_item(row_index, 11, uploaded_text)
            self._set_action_cell(
                row_index,
                12,
                dataset_id,
                "一括取得",
                "info",
                "bulk_download",
            )
            self._set_action_cell(
                row_index,
                13,
                dataset_id,
                "コンテンツZIP",
                "info",
                "upload_zip",
            )
            self._set_action_cell(
                row_index,
                14,
                dataset_id,
                "データカタログ修正",
                "info",
                "edit_portal",
            )
            self._set_action_cell(
                row_index,
                15,
                dataset_id,
                "ブラウザ表示",
                "info",
                "open_public_view",
            )
            self._set_action_cell(
                row_index,
                16,
                dataset_id,
                "ステータス変更",
                "warning",
                "toggle_status",
            )

        self.table.setSortingEnabled(True)

    def _set_item(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text or "")
        item.setToolTip(text or "")
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, col, item)

    def _set_action_cell(
        self,
        row: int,
        col: int,
        dataset_id: str,
        label: str,
        style_kind: str,
        action: str,
        icon: Optional[QIcon] = None,
        tooltip: str = "",
    ) -> None:
        container = QWidget(self.table)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        button = QPushButton(label)
        button.setStyleSheet(get_button_style(style_kind))
        if icon is not None:
            try:
                button.setIcon(icon)
            except Exception:
                pass
        if tooltip:
            try:
                button.setToolTip(tooltip)
            except Exception:
                pass

        button.clicked.connect(lambda _checked=False, dsid=dataset_id, act=action: self._handle_action(dsid, act))

        layout.addWidget(button)
        layout.addStretch()
        self.table.setCellWidget(row, col, container)

    def _build_status_icon(self, color_key: ThemeKey) -> Optional[QIcon]:
        try:
            pixmap = QPixmap(10, 10)
            pixmap.fill(get_qcolor(color_key))
            return QIcon(pixmap)
        except Exception:
            return None

    def _get_json_action_presentation(self, status_label: str) -> Tuple[str, str, Optional[QIcon]]:
        label_text = str(status_label or "").strip()
        if self._is_json_uploaded_label(label_text):
            return "✓ UP済", "success", self._build_status_icon(ThemeKey.BUTTON_SUCCESS_BACKGROUND)
        if label_text in {"未確認", ""}:
            return "? 未確認", "secondary", self._build_status_icon(ThemeKey.TEXT_MUTED)
        return "↑ UPLOAD", "warning", self._build_status_icon(ThemeKey.BUTTON_WARNING_BACKGROUND)

    def _handle_action(self, dataset_id: str, action: str) -> None:
        upload_tab = self._prepare_upload_tab(dataset_id)
        if upload_tab is None:
            return

        try:
            if action == "upload_json":
                anonymize = self._ask_anonymize_choice()
                if anonymize is None:
                    return
                if hasattr(upload_tab, "anonymize_checkbox"):
                    try:
                        upload_tab.anonymize_checkbox.setChecked(anonymize)
                    except Exception:
                        pass
                upload_tab._on_upload()
            elif action == "upload_zip":
                upload_tab._on_upload_zip()
            elif action == "bulk_download":
                upload_tab._on_bulk_download()
            elif action == "edit_portal":
                upload_tab._on_edit_portal()
            elif action == "open_public_view":
                upload_tab._on_open_public_view()
            elif action == "toggle_status":
                upload_tab._on_toggle_status()
        except Exception as exc:
            logger.error("Bulk action failed: %s", exc)
            QMessageBox.warning(self, "エラー", "操作の実行中にエラーが発生しました")

    def _prepare_upload_tab(self, dataset_id: str):
        upload_tab = self._get_upload_tab()
        if upload_tab is None:
            QMessageBox.warning(self, "エラー", "データカタログタブを初期化できません")
            return None

        self._sync_environment(upload_tab)

        if not upload_tab.select_dataset_id(dataset_id):
            QMessageBox.warning(self, "エラー", "データセット選択に失敗しました")
            return None

        return upload_tab

    def _ask_anonymize_choice(self) -> Optional[bool]:
        message = QMessageBox(self)
        message.setWindowTitle("匿名化設定")
        message.setText("書誌情報JSONを匿名化してアップロードしますか？")
        anonymize_btn = message.addButton("匿名化してUPLOAD", QMessageBox.AcceptRole)
        plain_btn = message.addButton("匿名化しないでUPLOAD", QMessageBox.NoRole)
        cancel_btn = message.addButton("キャンセル", QMessageBox.RejectRole)
        message.setIcon(QMessageBox.Question)
        message.exec()

        clicked = message.clickedButton()
        if clicked == cancel_btn or clicked is None:
            return None
        return clicked == anonymize_btn

    def _get_upload_tab(self):
        portal = self._portal_widget
        if portal is None:
            return None

        ensure = getattr(portal, "_ensure_upload_tab", None)
        if callable(ensure):
            try:
                ensure(set_current=False)
            except TypeError:
                ensure()
        return getattr(portal, "dataset_upload_tab", None)

    def _sync_environment(self, upload_tab) -> None:
        env = self._current_environment
        if not env:
            return

        try:
            combo = getattr(upload_tab, "env_combo", None)
            if combo is None:
                return
            for idx in range(combo.count()):
                if combo.itemData(idx) == env:
                    combo.setCurrentIndex(idx)
                    break
        except Exception:
            pass

    def _load_user_maps(self) -> None:
        info_path = get_dynamic_file_path("output/rde/data/info.json")
        try:
            with open(info_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            payload = None

        self._user_name_by_id, self._user_org_by_id = self._build_user_maps(payload)

    @staticmethod
    def _build_user_maps(payload: Any) -> Tuple[Dict[str, str], Dict[str, str]]:
        name_map: Dict[str, str] = {}
        org_map: Dict[str, str] = {}

        records = []
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            records = [r for r in payload.get("data") if isinstance(r, dict)]
        elif isinstance(payload, list):
            records = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            for key, value in payload.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                name = str(value.get("userName") or value.get("name") or "").strip()
                org = str(value.get("organizationName") or "").strip()
                if name:
                    name_map[key] = name
                if org:
                    org_map[key] = org
            return name_map, org_map

        for record in records:
            user_id = str(record.get("id") or "").strip()
            attrs = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
            if not user_id:
                continue
            name = str(attrs.get("userName") or attrs.get("name") or "").strip() if isinstance(attrs, dict) else ""
            org = str(attrs.get("organizationName") or "").strip() if isinstance(attrs, dict) else ""
            if name:
                name_map[user_id] = name
            if org:
                org_map[user_id] = org

        return name_map, org_map

    def _resolve_registrant_info(self, row: Dict[str, Any]) -> Tuple[str, str]:
        manager_id = str(row.get("_manager_id") or "").strip()
        label = str(row.get("manager_name") or "").strip()

        name = self._user_name_by_id.get(manager_id, "") if manager_id else ""
        org = self._user_org_by_id.get(manager_id, "") if manager_id else ""

        if not name or not org:
            parsed_name, parsed_org = self._split_user_label(label)
            name = name or parsed_name
            org = org or parsed_org

        return name, org

    def _get_json_upload_status_label(self, dataset_id: str) -> str:
        try:
            from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache
            from classes.dataset.util.portal_status_resolver import UNCHECKED_LABEL, normalize_logged_in_portal_label

            env = self._current_environment or "production"
            cache = get_portal_entry_status_cache()
            cached = cache.get_label_any_age(dataset_id, env)
            normalized = normalize_logged_in_portal_label(cached)
            return normalized or UNCHECKED_LABEL
        except Exception:
            return "未確認"

    @staticmethod
    def _is_json_uploaded_label(label: str) -> bool:
        text = str(label or "").strip()
        return text in {"公開", "非公開", "公開2", "公開済", "UP済"}

    def _get_image_counts(self, dataset_id: str, grant_number: str, dataset_name: str) -> Tuple[Optional[int], Optional[int]]:
        env = self._current_environment or "production"
        key = (env, dataset_id)
        if key in self._image_count_cache:
            return self._image_count_cache[key]

        files_exist, file_count, file_list = self._check_files_exist(dataset_id, grant_number, dataset_name)
        if not files_exist:
            self._image_count_cache[key] = (0, 0)
            return 0, 0

        uploaded_count = self._get_uploaded_image_count(dataset_id, file_list)
        result = (file_count, uploaded_count)
        self._image_count_cache[key] = result
        return result

    def _check_files_exist(self, dataset_id: str, grant_number: str, dataset_name: str) -> Tuple[bool, int, list[Dict[str, Any]]]:
        try:
            if not grant_number or not dataset_name:
                return False, 0, []

            def replace_invalid_path_chars(text: str) -> str:
                if not text:
                    return ""
                table = str.maketrans(
                    {
                        "\\": "￥",
                        "/": "／",
                        ":": "：",
                        "*": "＊",
                        "?": "？",
                        '"': '"',
                        "<": "＜",
                        ">": "＞",
                        "|": "｜",
                    }
                )
                return text.translate(table)

            safe_grant_number = replace_invalid_path_chars(grant_number)
            safe_dataset_name = replace_invalid_path_chars(dataset_name)
            base_dir = get_dynamic_file_path(f"output/rde/data/dataFiles/{safe_grant_number}/{safe_dataset_name}")

            if not os.path.exists(base_dir):
                return False, 0, []

            file_list = []
            for root, _dirs, files in os.walk(base_dir):
                for filename in files:
                    if filename.endswith(".json"):
                        continue
                    filepath = os.path.join(root, filename)
                    file_list.append(
                        {
                            "name": filename,
                            "size": os.path.getsize(filepath),
                            "path": filepath,
                            "relative_path": os.path.relpath(filepath, base_dir),
                        }
                    )

            return len(file_list) > 0, len(file_list), file_list
        except Exception:
            return False, 0, []

    def _get_uploaded_image_count(self, dataset_id: str, file_list: list[Dict[str, Any]]) -> Optional[int]:
        env = self._current_environment or "production"
        cache_key = (env, dataset_id)

        if cache_key in self._existing_images_cache:
            existing_images = self._existing_images_cache[cache_key]
            return self._count_uploaded_images(existing_images, file_list)

        client = self._get_portal_client(env)
        if client is None:
            return None

        t_code = self._get_t_code_for_dataset(client, dataset_id, env)
        if not t_code:
            return None

        existing_images = self._get_existing_images(client, t_code)
        self._existing_images_cache[cache_key] = existing_images
        return self._count_uploaded_images(existing_images, file_list)

    def _count_uploaded_images(self, existing_images: set[str], file_list: list[Dict[str, Any]]) -> int:
        count = 0
        for file_info in file_list:
            caption = str(file_info.get("name") or "").strip()
            if not caption:
                continue
            if caption in existing_images:
                count += 1
        return count

    def _get_portal_client(self, env: str):
        if self._portal_client_ready and self._portal_client_env == env:
            return self._portal_client
        if self._portal_client_failed and self._portal_client_env == env:
            return None

        try:
            from classes.data_portal.core.auth_manager import get_auth_manager
            from classes.data_portal.core.portal_client import PortalClient

            auth_manager = get_auth_manager()
            credentials = auth_manager.get_credentials(env)
            if credentials is None:
                self._portal_client_failed = True
                self._portal_client_env = env
                return None

            client = PortalClient(env)
            client.set_credentials(credentials)
            login_ok, _msg = client.login()
            if not login_ok:
                self._portal_client_failed = True
                self._portal_client_env = env
                return None

            self._portal_client = client
            self._portal_client_env = env
            self._portal_client_ready = True
            self._portal_client_failed = False
            return client
        except Exception:
            self._portal_client_failed = True
            self._portal_client_env = env
            return None

    def _get_t_code_for_dataset(self, client, dataset_id: str, env: str) -> str:
        key = (env, dataset_id)
        cached = self._t_code_cache.get(key)
        if cached is not None:
            return cached

        try:
            success, response = client.post("main.php", data={"mode": "theme", "page": "1"})
            if not success or not hasattr(response, "text"):
                return ""
            text = response.text or ""
            pattern = rf'<td class="l">{re.escape(dataset_id)}</td>.*?name="t_code" value="(\d+)"'
            match = re.search(pattern, text, re.DOTALL)
            t_code = match.group(1) if match else ""
            self._t_code_cache[key] = t_code
            return t_code
        except Exception:
            return ""

    def _get_existing_images(self, client, t_code: str) -> set[str]:
        try:
            data = {
                "mode": "theme",
                "mode2": "image",
                "t_code": t_code,
                "keyword": "",
                "search_inst": "",
                "search_license_level": "",
                "search_status": "",
                "page": "1",
            }

            success, response = client.post("main.php", data=data)
            if not success or not hasattr(response, "text"):
                return set()
            pattern = r'<td class="l">([^<]+)</td>'
            matches = re.findall(pattern, response.text or "")
            return set(matches)
        except Exception:
            return set()

    @staticmethod
    def _split_user_label(label: str) -> Tuple[str, str]:
        text = str(label or "").strip()
        if not text:
            return "", ""
        if "(" in text and text.endswith(")"):
            head, _, tail = text.rpartition("(")
            name = head.strip()
            org = tail[:-1].strip()
            if name or org:
                return name, org
        return text, ""

    def _on_page_changed(self, value: int) -> None:
        self._current_page = max(1, int(value or 1))
        self._render_page()

    def _on_page_size_changed(self) -> None:
        try:
            self._page_size = int(self.page_size_combo.currentData() or 50)
        except Exception:
            self._page_size = 50
        self._current_page = 1
        self._render_page()

    def _apply_column_visibility(self) -> None:
        if not hasattr(self, "table"):
            return
        for idx, col in enumerate(self._column_defs):
            visible = col.key in self._visible_columns
            try:
                self.table.setColumnHidden(idx, not visible)
            except Exception:
                pass

    def _on_select_columns(self) -> None:
        dialog = _BulkColumnSelectDialog(self._column_defs, self._visible_columns, self)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = dialog.get_selected_keys()
        if not selected:
            return
        self._visible_columns = selected
        self._apply_column_visibility()

    def _apply_display_mode(self, mode: str, *, force: bool = False) -> None:
        mode = str(mode or "").strip().lower()
        if mode not in {"compact", "equal", "default"}:
            mode = "default"
        if mode == self._display_mode and not force:
            return
        self._display_mode = mode

        try:
            if mode == "compact":
                self.table.setWordWrap(False)
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
                row_h = int(self.table.fontMetrics().height() * 1.6)
                if row_h > 0:
                    self.table.verticalHeader().setDefaultSectionSize(row_h)
            elif mode == "equal":
                self.table.setWordWrap(True)
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self._apply_equal_column_widths()
            else:
                self.table.setWordWrap(True)
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        except Exception:
            pass

        try:
            self.table.resizeRowsToContents()
        except Exception:
            pass

    def _apply_equal_column_widths(self) -> None:
        try:
            header = self.table.horizontalHeader()
            count = int(self.table.columnCount())
            if count <= 0:
                return
            available = int(self.table.viewport().width())
            if available <= 0:
                return
            visible_count = 0
            for col in range(count):
                if not self.table.isColumnHidden(col):
                    visible_count += 1
            per_col = max(80, int(available // max(visible_count, 1)))
            for col in range(count):
                if self.table.isColumnHidden(col):
                    continue
                header.resizeSection(col, per_col)
        except Exception:
            pass

    def _export(self, kind: str) -> None:
        kind = str(kind or "").strip().lower()
        if kind not in {"csv", "xlsx"}:
            return

        visible_cols: list[int] = []
        headers: list[str] = []
        for col in range(int(self.table.columnCount())):
            try:
                if self.table.isColumnHidden(col):
                    continue
            except Exception:
                pass
            header = self.table.horizontalHeaderItem(col)
            headers.append(str(header.text() if header else ""))
            visible_cols.append(int(col))

        if not visible_cols:
            return

        rows: list[dict[str, object]] = []
        for row_idx in range(int(self.table.rowCount())):
            out: dict[str, object] = {}
            for col_idx, header in zip(visible_cols, headers, strict=False):
                item = self.table.item(row_idx, int(col_idx))
                if item is not None:
                    value = item.text()
                else:
                    widget = self.table.cellWidget(row_idx, int(col_idx))
                    value = self._extract_cell_widget_text(widget)
                out[header] = value
            if out:
                rows.append(out)

        if not rows:
            QMessageBox.information(self, "出力", "出力対象の行がありません")
            return

        import time

        default_name = f"data_portal_bulk_{time.strftime('%Y%m%d_%H%M%S')}"
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

    @staticmethod
    def _extract_cell_widget_text(widget: Optional[QWidget]) -> str:
        if widget is None:
            return ""
        try:
            buttons = widget.findChildren(QPushButton)
            if buttons:
                return str(buttons[0].text() or "")
        except Exception:
            pass
        return ""

    def _go_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._render_page()

    def _go_next_page(self) -> None:
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._render_page()
