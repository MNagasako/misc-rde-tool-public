"""
データセット データエントリー専用ウィジェット（最小版）
※修正タブの構造を参考にした安全な実装
Bearer Token統一管理システム対応
"""
import os
import json
import datetime
import time
import logging
from typing import Iterable, Callable, Optional
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QMessageBox, QComboBox, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QCheckBox, QRadioButton, QProgressDialog, QApplication,
    QLineEdit, QButtonGroup, QGridLayout
)
from qt_compat.core import Qt, QTimer, QUrl
from qt_compat.gui import QDesktopServices
from config.common import get_dynamic_file_path
from core.bearer_token_manager import BearerTokenManager
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from classes.dataset.util.show_event_refresh import RefreshOnShowWidget
from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload

# ロガー設定
logger = logging.getLogger(__name__)


def relax_dataset_dataentry_filters_for_launch(
    all_radio,
    other_radios: Optional[Iterable] = None,
    grant_filter_input=None,
    reload_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """Force the loosest filter selection before applying dataset handoff."""
    controls = []
    for control in filter(None, [all_radio, grant_filter_input]):
        if hasattr(control, 'blockSignals'):
            controls.append((control, control.blockSignals(True)))
    for radio in other_radios or []:
        if hasattr(radio, 'blockSignals'):
            controls.append((radio, radio.blockSignals(True)))

    changed = False
    try:
        if all_radio is not None and hasattr(all_radio, 'isChecked') and not all_radio.isChecked():
            all_radio.setChecked(True)
            changed = True
        if grant_filter_input is not None and hasattr(grant_filter_input, 'text'):
            if grant_filter_input.text().strip():
                if hasattr(grant_filter_input, 'clear'):
                    grant_filter_input.clear()
                    changed = True
    finally:
        for control, previous in controls:
            control.blockSignals(previous)

    if changed and callable(reload_callback):
        try:
            reload_callback()
        except Exception:  # pragma: no cover - defensive fallback
            logger.debug("dataset_dataentry: filter reload failed", exc_info=True)
    return changed


def create_dataset_dataentry_widget(parent, title, create_auto_resize_button):
    """データセット データエントリー専用ウィジェット（最小版）"""
    widget = RefreshOnShowWidget()
    widget.dataset_map = {}
    layout = QVBoxLayout()

    # フィルタUI
    filter_widget = QWidget()
    filter_layout = QVBoxLayout()
    filter_layout.setContentsMargins(0, 0, 0, 0)

    filter_type_widget = QWidget()
    filter_type_layout = QHBoxLayout()
    filter_type_layout.setContentsMargins(0, 0, 0, 0)

    filter_type_label = QLabel("表示対象:")
    filter_type_label.setMinimumWidth(120)
    filter_type_label.setStyleSheet("font-weight: bold;")

    filter_user_only_radio = QRadioButton("所属のみ")
    filter_others_only_radio = QRadioButton("その他のみ")
    filter_all_radio = QRadioButton("すべて")
    filter_user_only_radio.setChecked(True)

    filter_button_group = QButtonGroup(widget)
    filter_button_group.addButton(filter_user_only_radio)
    filter_button_group.addButton(filter_others_only_radio)
    filter_button_group.addButton(filter_all_radio)

    filter_type_layout.addWidget(filter_type_label)
    filter_type_layout.addWidget(filter_user_only_radio)
    filter_type_layout.addWidget(filter_others_only_radio)
    filter_type_layout.addWidget(filter_all_radio)
    filter_type_layout.addStretch()

    filter_type_widget.setLayout(filter_type_layout)
    filter_layout.addWidget(filter_type_widget)

    grant_filter_widget = QWidget()
    grant_filter_layout = QHBoxLayout()
    grant_filter_layout.setContentsMargins(0, 0, 0, 0)

    grant_filter_label = QLabel("課題番号フィルタ:")
    grant_filter_label.setMinimumWidth(120)
    grant_filter_label.setStyleSheet("font-weight: bold;")

    grant_filter_input = QLineEdit()
    grant_filter_input.setPlaceholderText("課題番号 (例: 22XXXXXX)")
    grant_filter_input.setMinimumWidth(200)

    grant_filter_layout.addWidget(grant_filter_label)
    grant_filter_layout.addWidget(grant_filter_input)
    grant_filter_layout.addStretch()

    grant_filter_widget.setLayout(grant_filter_layout)
    filter_layout.addWidget(grant_filter_widget)

    filter_widget.setLayout(filter_layout)
    layout.addWidget(filter_widget)

    # データセット選択UI
    dataset_selection_widget = QWidget()
    dataset_selection_layout = QHBoxLayout()
    dataset_selection_layout.setContentsMargins(0, 0, 0, 0)

    dataset_label = QLabel("データエントリー対象データセット:")
    dataset_label.setMinimumWidth(200)

    dataset_combo = QComboBox()
    dataset_combo.setObjectName("datasetDataEntryCombo")
    dataset_combo.setMinimumWidth(650)
    dataset_combo.setEditable(True)
    dataset_combo.setInsertPolicy(QComboBox.NoInsert)
    dataset_combo.setMaxVisibleItems(12)

    show_all_btn = QPushButton("▼")
    show_all_btn.setToolTip("全件リスト表示")
    show_all_btn.setFixedWidth(28)
    show_all_btn.clicked.connect(dataset_combo.showPopup)

    dataset_selection_layout.addWidget(dataset_label)
    dataset_selection_layout.addWidget(dataset_combo)
    dataset_selection_layout.addWidget(show_all_btn)
    dataset_selection_widget.setLayout(dataset_selection_layout)
    layout.addWidget(dataset_selection_widget)
    widget.dataset_combo = dataset_combo  # type: ignore[attr-defined]

    launch_controls_widget = QWidget()
    launch_controls_layout = QHBoxLayout()
    launch_controls_layout.setContentsMargins(0, 0, 0, 0)
    launch_label = QLabel("他機能連携:")
    launch_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;")
    launch_controls_layout.addWidget(launch_label)

    launch_button_style = f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
            border-radius: 4px;
            padding: 4px 10px;
            border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
        }}
        QPushButton:hover {{
            background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """

    launch_targets = [
        ("data_fetch2", "データ取得2"),
    #    ("dataset_edit", "データセット修正"),
        ("data_register", "データ登録"),
        ("data_register_batch", "データ登録(一括)"),
    ]

    launch_buttons = []

    def _has_dataset_selection() -> bool:
        idx = dataset_combo.currentIndex()
        if idx <= 0:
            return False
        data = dataset_combo.itemData(idx)
        return bool(data)

    def _update_launch_button_state() -> None:
        enabled = _has_dataset_selection()
        for button in launch_buttons:
            button.setEnabled(enabled)

    def _load_dataset_record(dataset_id: str):
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        if not dataset_id or not os.path.exists(dataset_path):
            return None
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            items = data.get('data') if isinstance(data, dict) else data
            for dataset in items or []:
                if isinstance(dataset, dict) and dataset.get('id') == dataset_id:
                    return dataset
        except Exception as exc:
            logger.debug("dataset_dataentry: dataset.json読み込み失敗 %s", exc)
        return None

    def _get_current_dataset_payload():
        idx = dataset_combo.currentIndex()
        if idx <= 0:
            QMessageBox.warning(widget, "データセット未選択", "連携するデータセットを選択してください。")
            return None
        dataset_id = dataset_combo.itemData(idx)
        if not dataset_id:
            QMessageBox.warning(widget, "データセット未選択", "連携するデータセットを選択してください。")
            return None
        display_text = dataset_combo.itemText(idx) or dataset_id
        dataset_map = getattr(widget, 'dataset_map', {}) or {}
        raw_dataset = dataset_map.get(dataset_id)
        if raw_dataset is None:
            raw_dataset = _load_dataset_record(dataset_id)
            if raw_dataset:
                dataset_map[dataset_id] = raw_dataset
                widget.dataset_map = dataset_map
        return {
            "dataset_id": dataset_id,
            "display_text": display_text,
            "raw_dataset": raw_dataset,
        }

    def _handle_launch(target_key: str):
        payload = _get_current_dataset_payload()
        if not payload:
            return
        DatasetLaunchManager.instance().request_launch(
            target_key=target_key,
            dataset_id=payload["dataset_id"],
            display_text=payload["display_text"],
            raw_dataset=payload["raw_dataset"],
            source_name="dataset_dataentry",
        )

    for target_key, caption in launch_targets:
        btn = QPushButton(caption)
        btn.setStyleSheet(launch_button_style)
        btn.clicked.connect(lambda _=None, key=target_key: _handle_launch(key))
        launch_controls_layout.addWidget(btn)
        launch_buttons.append(btn)

    launch_controls_layout.addStretch()
    launch_controls_widget.setLayout(launch_controls_layout)
    layout.addWidget(launch_controls_widget)
    widget._dataset_launch_buttons = launch_buttons  # type: ignore[attr-defined]

    # 操作ボタン
    control_widget = QWidget()
    control_layout = QHBoxLayout()
    control_layout.setContentsMargins(0, 0, 0, 0)

    fetch_button = QPushButton("データエントリー取得")
    refresh_dataset_button = QPushButton("データセット一覧更新")
    info_bg = get_color(ThemeKey.BUTTON_INFO_BACKGROUND)
    info_text = get_color(ThemeKey.BUTTON_INFO_TEXT)
    info_border = get_color(ThemeKey.BUTTON_INFO_BORDER)
    info_hover = get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)
    info_pressed = get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)
    common_button_style = f"""
        QPushButton {{
            background-color: {info_bg};
            color: {info_text};
            font-weight: bold;
            border-radius: 6px;
            padding: 8px 16px;
            border: 1px solid {info_border};
        }}
        QPushButton:hover {{
            background-color: {info_hover};
        }}
        QPushButton:pressed {{
            background-color: {info_pressed};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """.strip()
    fetch_button.setStyleSheet(common_button_style)
    refresh_dataset_button.setStyleSheet(common_button_style)

    show_all_entries_button = QPushButton("全エントリー表示")
    show_all_entries_button.setStyleSheet(f"""
        background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
        font-weight: bold;
        border-radius: 6px;
        padding: 8px 16px;
    """)

    control_layout.addWidget(fetch_button)
    control_layout.addWidget(refresh_dataset_button)
    control_layout.addWidget(show_all_entries_button)

    force_refresh_checkbox = QCheckBox("強制更新")
    force_refresh_checkbox.setToolTip("既存のJSONファイルが5分以内でも強制的に再取得します")
    force_refresh_checkbox.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_WARNING)}; font-weight: bold;")
    control_layout.addWidget(force_refresh_checkbox)
    control_layout.addStretch()

    control_widget.setLayout(control_layout)
    layout.addWidget(control_widget)
    
    # データエントリー情報表示エリア
    info_group = QGroupBox("データエントリー情報")
    info_layout = QVBoxLayout()
    
    # 基本情報表示
    basic_info_widget = QWidget()
    basic_info_layout = QVBoxLayout()
    basic_info_layout.setContentsMargins(0, 0, 0, 0)
    
    dataset_info_label = QLabel("データセット: 未選択")
    dataset_info_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)}; margin: 5px;")
    
    entry_count_label = QLabel("データエントリー件数: -")
    entry_count_label.setStyleSheet(f"font-size: 12px; color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px;")
    
    last_updated_label = QLabel("最終取得: -")
    last_updated_label.setStyleSheet(f"font-size: 12px; color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px;")
    
    basic_info_layout.addWidget(dataset_info_label)
    basic_info_layout.addWidget(entry_count_label)
    basic_info_layout.addWidget(last_updated_label)
    
    basic_info_widget.setLayout(basic_info_layout)
    info_layout.addWidget(basic_info_widget)
    
    # データエントリー一覧テーブル
    # --- fileTypeごとのカラム拡張 ---
    from classes.data_fetch2.conf.file_filter_config import FILE_TYPES
    # ファイルタイプごとの短い日本語ラベル
    FILE_TYPE_LABELS = {
        "MAIN_IMAGE": "MAIN",
        "STRUCTURED": "STRCT",
        "NONSHARED_RAW": "NOSHARE",
        "RAW": "RAW",
        "META": "META",
        "ATTACHEMENT": "ATTACH",
        "THUMBNAIL": "THUMB",
        "OTHER": "OTHER"
    }
    DISPLAY_FILE_TYPES = FILE_TYPES + (["OTHER"] if "OTHER" not in FILE_TYPES else [])
    IMAGE_FILE_TYPES = {"MAIN_IMAGE", "THUMBNAIL"}
    base_headers = ["No", "名前", "説明", "ファイル", "画像", "作成日"]
    filetype_headers = [f"{FILE_TYPE_LABELS.get(ft, ft)}" for ft in DISPLAY_FILE_TYPES]
    all_headers = base_headers + filetype_headers + ["ブラウザ"]
    base_col_count = len(base_headers)
    browser_column_index = len(all_headers) - 1
    entry_table = EntryTableWidget()
    entry_table.setColumnCount(len(all_headers))
    entry_table.setHorizontalHeaderLabels(all_headers)
    header = entry_table.horizontalHeader()
    for col in range(len(all_headers)):
        header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
    header.setStretchLastSection(False)
    entry_table.setAlternatingRowColors(True)
    entry_table.setSelectionBehavior(QTableWidget.SelectRows)
    entry_table.setSortingEnabled(True)
    entry_table.setMinimumHeight(300)
    entry_table.horizontalHeader().setDefaultAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
    entry_table.setWordWrap(True)
    entry_table.setStyleSheet("QHeaderView::section { padding: 4px; white-space: normal; }")
    info_layout.addWidget(entry_table)
    info_group.setLayout(info_layout)
    layout.addWidget(info_group)

    summary_group = QGroupBox("データエントリー情報集計")
    summary_layout = QGridLayout()
    summary_layout.addWidget(QLabel("項目"), 0, 0)
    summary_layout.addWidget(QLabel("ファイル数"), 0, 1)
    summary_layout.addWidget(QLabel("サイズ合計"), 0, 2)
    summary_value_labels = {}
    summary_rows = [
        ("files", "ファイル"),
        ("images", "画像"),
    ] + [(ft, FILE_TYPE_LABELS.get(ft, ft)) for ft in DISPLAY_FILE_TYPES] + [
        ("total", "総計"),
        ("shared1", "共用合計１"),
        ("shared2", "共用合計２(〇非共有構造化ファイル＆サムネ除外)"),
        ("shared3", "共用合計３"),
    ]
    for row_idx, (key, label_text) in enumerate(summary_rows, start=1):
        summary_layout.addWidget(QLabel(label_text), row_idx, 0)
        count_label = QLabel("-")
        size_label = QLabel("-")
        count_label.setObjectName(f"summary_{key}_count")
        size_label.setObjectName(f"summary_{key}_size")
        summary_layout.addWidget(count_label, row_idx, 1)
        summary_layout.addWidget(size_label, row_idx, 2)
        summary_value_labels[key] = (count_label, size_label)
    summary_group.setLayout(summary_layout)
    layout.addWidget(summary_group)

    def safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def format_size_short(num_bytes):
        if not num_bytes:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(num_bytes)
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024
            idx += 1
        return f"{size:.2f} {units[idx]}"

    def format_size_with_bytes(num_bytes):
        formatted = format_size_short(num_bytes)
        return f"{formatted} ({num_bytes:,} B)"

    def reset_summary_display():
        for count_label, size_label in summary_value_labels.values():
            count_label.setText("-")
            size_label.setText("-")

    def create_empty_summary():
        return {
            "files": {"count": 0, "bytes": 0},
            "images": {"count": 0, "bytes": 0},
            "filetypes": {ft: {"count": 0, "bytes": 0} for ft in DISPLAY_FILE_TYPES},
            "total": {"count": 0, "bytes": 0},
            "shared1": {"count": 0, "bytes": 0},
            "shared2": {"count": 0, "bytes": 0},
            "shared3": {"count": 0, "bytes": 0},
        }

    def finalize_summary(summary):
        total_count = sum(item["count"] for item in summary["filetypes"].values())
        total_bytes = sum(item["bytes"] for item in summary["filetypes"].values())
        summary["total"]["count"] = total_count
        summary["total"]["bytes"] = total_bytes
        shared_sets = {
            "shared1": {"exclude": {"NONSHARED_RAW"}},
            "shared2": {"exclude": {"NONSHARED_RAW", "THUMBNAIL"}},
            "shared3": {"exclude": {"NONSHARED_RAW", "THUMBNAIL", "OTHER"}},
        }

        def accumulate_shared(key, exclude_types):
            include_types = [ft for ft in DISPLAY_FILE_TYPES if ft not in exclude_types]
            summary[key]["count"] = sum(summary["filetypes"][ft]["count"] for ft in include_types)
            summary[key]["bytes"] = sum(summary["filetypes"][ft]["bytes"] for ft in include_types)

        for shared_key, config in shared_sets.items():
            accumulate_shared(shared_key, config["exclude"])

        summary["files"]["bytes"] = total_bytes
        return summary

    def update_summary_display(summary):
        if not summary:
            reset_summary_display()
            return

        def set_labels(key, data):
            count_label, size_label = summary_value_labels[key]
            count_label.setText(f"{data['count']:,}")
            size_label.setText(format_size_with_bytes(data["bytes"]))

        set_labels("files", summary["files"])
        set_labels("images", summary["images"])
        for ft in DISPLAY_FILE_TYPES:
            set_labels(ft, summary["filetypes"][ft])
        set_labels("total", summary["total"])
        set_labels("shared1", summary["shared1"])
        set_labels("shared2", summary["shared2"])
        set_labels("shared3", summary["shared3"])

    def clear_entry_table_widgets():
        for row in range(entry_table.rowCount()):
            for col in range(entry_table.columnCount()):
                widget = entry_table.cellWidget(row, col)
                if widget is not None:
                    widget.deleteLater()
                    entry_table.setCellWidget(row, col, None)

    def classify_file_type(raw_type):
        if raw_type in DISPLAY_FILE_TYPES:
            return raw_type
        return "OTHER"

    def analyze_entry_files(entry, file_lookup):
        rel_files = entry.get("relationships", {}).get("files", {}).get("data", [])
        counts = {ft: 0 for ft in DISPLAY_FILE_TYPES}
        sizes = {ft: 0 for ft in DISPLAY_FILE_TYPES}
        image_bytes = 0
        for rel in rel_files:
            file_id = rel.get("id")
            file_info = file_lookup.get(file_id)
            if not file_info:
                continue
            file_attr = file_info.get("attributes", {})
            raw_type = file_attr.get("fileType")
            ft_key = classify_file_type(raw_type)
            file_size = safe_int(file_attr.get("fileSize", 0))
            counts[ft_key] += 1
            sizes[ft_key] += file_size
            is_image = file_attr.get("isImageFile")
            if is_image is None:
                is_image = raw_type in IMAGE_FILE_TYPES
            if is_image:
                image_bytes += file_size
        return counts, sizes, image_bytes

    def open_entry_in_browser(entry_id):
        url = f"https://rde.nims.go.jp/rde/datasets/data/{entry_id}"
        QDesktopServices.openUrl(QUrl(url))

    def populate_entry_row(row_index, context, summary):
        entry = context["entry"]
        dataset_id = context["dataset_id"]
        prefix_dataset = context["prefix_dataset"]
        file_lookup = context["file_lookup"]
        attributes = entry.get("attributes", {})
        data_number = str(attributes.get("dataNumber", ""))
        if prefix_dataset:
            data_number = f"{dataset_id}-{data_number}"
        entry_table.setItem(row_index, 0, QTableWidgetItem(data_number))
        entry_table.setItem(row_index, 1, QTableWidgetItem(attributes.get("name", "")))
        entry_table.setItem(row_index, 2, QTableWidgetItem(attributes.get("description", "")))
        num_files = safe_int(attributes.get("numberOfFiles", 0))
        entry_table.setItem(row_index, 3, QTableWidgetItem(str(num_files)))
        num_image_files = safe_int(attributes.get("numberOfImageFiles", 0))
        entry_table.setItem(row_index, 4, QTableWidgetItem(str(num_image_files)))
        created_at = attributes.get("createdAt") or attributes.get("created") or ""
        if created_at:
            try:
                dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                formatted_date = dt.strftime('%Y-%m-%d')
            except Exception:
                formatted_date = created_at
        else:
            formatted_date = "--"
        entry_table.setItem(row_index, 5, QTableWidgetItem(formatted_date))

        filetype_counts, filetype_sizes, image_bytes = analyze_entry_files(entry, file_lookup)
        for i, ft in enumerate(DISPLAY_FILE_TYPES):
            entry_table.setItem(row_index, base_col_count + i, QTableWidgetItem(str(filetype_counts[ft])))
            summary["filetypes"][ft]["count"] += filetype_counts[ft]
            summary["filetypes"][ft]["bytes"] += filetype_sizes[ft]

        summary["files"]["count"] += num_files
        summary["files"]["bytes"] += sum(filetype_sizes.values())
        summary["images"]["count"] += num_image_files
        summary["images"]["bytes"] += image_bytes

        entry_id = entry.get("id", "")
        link_button = QPushButton("開く")
        link_button.setStyleSheet(f"""
            background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 3px;
        """)
        link_button.clicked.connect(lambda _, eid=entry_id: open_entry_in_browser(eid))
        entry_table.setCellWidget(row_index, browser_column_index, link_button)

    def create_bold_item(text=""):
        item = QTableWidgetItem(text)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def add_total_row(row_index, summary):
        entry_table.setItem(row_index, 0, create_bold_item("合計"))
        entry_table.setItem(row_index, 1, create_bold_item())
        entry_table.setItem(row_index, 2, create_bold_item())
        entry_table.setItem(row_index, 3, create_bold_item(str(summary["files"]["count"])))
        entry_table.setItem(row_index, 4, create_bold_item(str(summary["images"]["count"])))
        entry_table.setItem(row_index, 5, create_bold_item())
        for i, ft in enumerate(DISPLAY_FILE_TYPES):
            entry_table.setItem(row_index, base_col_count + i, create_bold_item(str(summary["filetypes"][ft]["count"])))
        entry_table.setItem(row_index, browser_column_index, create_bold_item())
        entry_table.set_footer_row_index(row_index)

    def populate_entry_table_rows(entry_contexts):
        entry_table.setSortingEnabled(False)
        clear_entry_table_widgets()
        entry_table.clear_footer_row()
        summary = create_empty_summary()
        if not entry_contexts:
            entry_table.setRowCount(0)
            entry_table.clear_footer_row()
            finalize_summary(summary)
            update_summary_display(summary)
            entry_table.setSortingEnabled(True)
            return summary

        entry_table.setRowCount(len(entry_contexts) + 1)
        for row_index, context in enumerate(entry_contexts):
            populate_entry_row(row_index, context, summary)
        finalize_summary(summary)
        add_total_row(len(entry_contexts), summary)
        update_summary_display(summary)
        entry_table.setSortingEnabled(True)
        return summary
    
    # データセットキャッシュシステム（最小版）
    dataset_cache = {
        "raw_data": None,
        "last_modified": None,
        "user_grant_numbers": None,
        "filtered_datasets": {},
        "display_data": {}
    }
    
    def load_subgroups():
        """サブグループ情報を読み込んでコンボボックスに設定"""
        try:
            # サブグループフィルタ除去
            
            # subGroup.jsonから読み込み
            subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
            if os.path.exists(subgroup_path):
                with open(subgroup_path, 'r', encoding='utf-8') as f:
                    subgroup_data = json.load(f)
                
                # 正しいデータ構造から読み込み: {"data": {...}, "included": [...]}
                subgroups = subgroup_data.get("included", [])
                
                for subgroup in subgroups:
                    # データ構造の検証
                    if not isinstance(subgroup, dict):
                        logger.warning("サブグループデータが辞書でない - スキップ")
                        continue
                    
                    attrs = subgroup.get("attributes", {})
                    if not isinstance(attrs, dict):
                        logger.warning("サブグループのattributesが辞書でない - スキップ")
                        continue
                    
                    subgroup_id = subgroup.get("id", "")
                    subgroup_name = attrs.get("name", "")
                    display_text = f"{subgroup_name} ({subgroup_id})"
                    # サブグループフィルタ除去
            
            # サブグループフィルタ除去
            
        except Exception as e:
            logger.error("サブグループ読み込みエラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def get_user_grant_numbers():
        """
        ログインユーザーが属するサブグループのgrantNumberリストを取得
        修正タブと同様の処理
        """
        sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
        self_path = get_dynamic_file_path('output/rde/data/self.json')
        user_grant_numbers = set()
        
        logger.debug("サブグループファイルパス: %s", sub_group_path)
        logger.debug("セルフファイルパス: %s", self_path)
        logger.debug("サブグループファイル存在: %s", os.path.exists(sub_group_path))
        logger.debug("セルフファイル存在: %s", os.path.exists(self_path))
        
        try:
            # ログインユーザーID取得
            with open(self_path, encoding="utf-8") as f:
                self_data = json.load(f)
            user_id = self_data.get("data", {}).get("id", None)
            logger.debug("ユーザーID: %s", user_id)
            
            if not user_id:
                logger.error("self.jsonからユーザーIDが取得できませんでした。")
                return user_grant_numbers
            
            # ユーザーが属するサブグループを抽出
            with open(sub_group_path, encoding="utf-8") as f:
                sub_group_data = json.load(f)
            
            groups_count = 0
            for item in sub_group_data.get("included", []):
                if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                    groups_count += 1
                    roles = item.get("attributes", {}).get("roles", [])
                    # ユーザーがこのグループのメンバーかチェック
                    user_in_group = False
                    for r in roles:
                        if r.get("userId") == user_id:
                            user_in_group = True
                            break
                    
                    if user_in_group:
                        # このグループのgrantNumbersを取得
                        subjects = item.get("attributes", {}).get("subjects", [])
                        group_name = item.get("attributes", {}).get("name", "不明")
                        logger.debug("ユーザーが所属するグループ: '%s' (課題数: %s)", group_name, len(subjects))
                        
                        for subject in subjects:
                            grant_number = subject.get("grantNumber", "")
                            if grant_number:
                                user_grant_numbers.add(grant_number)
                                logger.debug("課題番号追加: %s", grant_number)
            
            logger.debug("検査したTEAMグループ数: %s", groups_count)
            logger.debug("最終的なユーザー課題番号: %s", sorted(user_grant_numbers))
        
        except Exception as e:
            logger.error("ユーザーgrantNumber取得に失敗: %s", e)
            import traceback
            traceback.print_exc()
        
        return user_grant_numbers

    def populate_dataset_combo_with_filter(preserve_selection_id: str | None = None):
        """フィルタリングを適用してデータセットコンボボックスを更新"""
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        
        if not os.path.exists(dataset_path):
            dataset_combo.clear()
            dataset_combo.addItem("-- データセット情報がありません --", "")
            QMessageBox.warning(widget, "注意", "データセット情報が見つかりません。\n基本情報取得を実行してください。")
            return
        
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            datasets = data.get('data', []) if isinstance(data, dict) else data
            
            # フィルタリング適用
            filtered_datasets = []
            
            # ユーザー所属・その他・すべてのフィルタ
            filter_type = "user_only"
            if filter_others_only_radio.isChecked():
                filter_type = "others_only"
            elif filter_all_radio.isChecked():
                filter_type = "all"
            
            # サブグループフィルタ
            # サブグループフィルタ除去
            
            # ユーザーのgrantNumber一覧を取得
            user_grant_numbers = get_user_grant_numbers()
            
            # グラント番号フィルタ
            grant_filter_text = grant_filter_input.text().strip().lower()
            
            # フィルタリング処理
            filtered_datasets = []
            user_datasets = []
            other_datasets = []
            
            for dataset in datasets:
                attrs = dataset.get("attributes", {})
                dataset_id = dataset.get("id", "")
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                
                # グラント番号フィルタを先に適用
                if grant_filter_text and grant_filter_text not in grant_number.lower():
                    continue
                
                # ユーザー所属かどうかで分類
                if grant_number in user_grant_numbers:
                    user_datasets.append(dataset)
                else:
                    other_datasets.append(dataset)
            
            # フィルタタイプに基づいて表示対象を決定
            if filter_type == "user_only":
                filtered_datasets = user_datasets
                logger.debug("フィルタ適用: ユーザー所属のみ (%s件)", len(filtered_datasets))
            elif filter_type == "others_only":
                filtered_datasets = other_datasets
                logger.debug("フィルタ適用: その他のみ (%s件)", len(filtered_datasets))
            elif filter_type == "all":
                filtered_datasets = user_datasets + other_datasets
                logger.debug("フィルタ適用: すべて (ユーザー所属: %s件, その他: %s件, 合計: %s件)", len(user_datasets), len(other_datasets), len(filtered_datasets))
            
            try:
                widget.dataset_map = {
                    dataset.get("id"): dataset
                    for dataset in filtered_datasets
                    if isinstance(dataset, dict) and dataset.get("id")
                }
            except Exception:
                widget.dataset_map = {}

            # コンボボックス更新
            dataset_combo.blockSignals(True)
            dataset_combo.clear()
            dataset_combo.addItem("-- データセットを選択 --", "")
            
            for dataset in filtered_datasets:
                attrs = dataset.get("attributes", {})
                dataset_id = dataset.get("id", "")
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if grant_number in user_grant_numbers:
                    display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
                else:
                    display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                
                if dataset_type:
                    display_text += f" [{dataset_type}]"
                
                dataset_combo.addItem(display_text, dataset_id)
            
            dataset_combo.blockSignals(False)
            _restore_dataentry_dataset_selection(preserve_selection_id)
            
            logger.info("フィルタ適用後のデータセット: %s件 (全%s件中)", len(filtered_datasets), len(datasets))
            
        except Exception as e:
            logger.error("dataset.json読み込みエラー: %s", e)
            dataset_combo.clear()
            dataset_combo.addItem("-- データセット読み込みエラー --", "")

    def _find_dataset_index(dataset_id: str) -> int:
        if not dataset_id:
            return -1
        for idx in range(dataset_combo.count()):
            if dataset_combo.itemData(idx) == dataset_id:
                return idx
        return -1

    def _restore_dataentry_dataset_selection(dataset_id: str | None) -> None:
        if dataset_combo.count() == 0:
            dataset_combo.setCurrentIndex(-1)
            return
        if not dataset_id:
            dataset_combo.setCurrentIndex(0)
            return
        target_index = _find_dataset_index(dataset_id)
        if target_index < 0:
            dataset_combo.setCurrentIndex(0)
            return
        previous_index = dataset_combo.currentIndex()
        dataset_combo.setCurrentIndex(target_index)
        if previous_index == target_index:
            try:
                update_dataentry_display(dataset_id)
            except Exception:
                logger.debug("dataset_dataentry: manual refresh after restore failed", exc_info=True)
        _update_launch_button_state()

    def _format_dataset_display(dataset_dict: dict | None, fallback: str) -> str:
        if not isinstance(dataset_dict, dict):
            return fallback
        attrs = dataset_dict.get("attributes", {})
        grant = attrs.get("grantNumber") or ""
        name = attrs.get("name") or ""
        parts = [part for part in (grant, name) if part]
        return " - ".join(parts) if parts else fallback

    def refresh_dataset_sources(reason="manual", preserve_selection=True):
        """サブグループとデータセット一覧をまとめて再読み込みする"""
        logger.debug("データエントリータブ: refresh_dataset_sources reason=%s", reason)
        selection_id = get_selected_dataset_id() if preserve_selection else None
        load_subgroups()
        populate_dataset_combo_with_filter(selection_id)
    
    def get_selected_dataset_id():
        """選択されたデータセットのIDを取得"""
        return dataset_combo.currentData()
    
    def update_dataentry_display(dataset_id=None, force_refresh=False):
        """データエントリー情報の表示を更新"""
        if not dataset_id:
            dataset_id = get_selected_dataset_id()
        
        if not dataset_id:
            dataset_info_label.setText("データセット: 未選択")
            entry_count_label.setText("データエントリー件数: -")
            last_updated_label.setText("最終取得: -")
            clear_entry_table_widgets()
            entry_table.setRowCount(0)
            entry_table.clear_footer_row()
            update_summary_display(finalize_summary(create_empty_summary()))
            return
        
        # JSONファイルの存在確認と更新チェック
        dataentry_file = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
        
        needs_fetch = True
        if os.path.exists(dataentry_file) and not force_refresh:
            # ファイルの更新時刻をチェック（5分以内なら取得スキップ）
            file_mtime = os.path.getmtime(dataentry_file)
            current_time = time.time()
            
            if current_time - file_mtime < 300:  # 5分 = 300秒
                needs_fetch = False
            logger.debug("[データエントリーキャッシュ] needs_fetch=%s now=%s file=%s 最終更新: %s", needs_fetch, current_time, dataentry_file, datetime.datetime.fromtimestamp(file_mtime))
        if needs_fetch:
            # データエントリー情報を取得する必要がある
            dataset_info_label.setText(f"データセット: {dataset_id} (取得中...)")
            entry_count_label.setText("データエントリー件数: 取得中...")
            last_updated_label.setText("最終取得: 取得中...")
            entry_table.setRowCount(0)
            logger.debug("[データエントリー取得] fetch_dataentry_info(%s, %s)", dataset_id, force_refresh)
                # 少し遅延させてから取得処理を実行
            QTimer.singleShot(100, lambda: fetch_dataentry_info(dataset_id, force_refresh))
        else:
            # 既存のJSONファイルを読み込んで表示
            load_and_display_dataentry_info(dataset_id)
    
    def fetch_dataentry_info(dataset_id, force_refresh=False):
        """データエントリー情報をAPIから取得"""
        
        try:
            # プログレスダイアログを表示
            progress = QProgressDialog("データエントリー情報を取得中...", "キャンセル", 0, 100, widget)
            progress.setWindowModality(Qt.WindowModal)
            progress.setAutoClose(True)
            progress.setValue(10)
            QApplication.processEvents()
            
            # Bearer Token統一管理システムで取得
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
            if not bearer_token:
                QMessageBox.warning(widget, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
                return
            
            progress.setValue(30)
            QApplication.processEvents()
            
            # データエントリー取得API呼び出し（実際のAPI呼び出しコードに置き換える）
            # ここから先を修正。basic モジュールとかのデータエントリー取得機能を使うといいと思う。
            
            from classes.dataset.core.dataset_dataentry_logic import fetch_dataset_dataentry
            
            progress.setValue(50)
            QApplication.processEvents()
            
            success = fetch_dataset_dataentry(dataset_id, bearer_token, force_refresh)
            #return #debug 一時的
            progress.setValue(90)
            QApplication.processEvents()
            logger.debug("fetch_dataset_dataentry result: %s", success)
            if success:
                # 取得成功、表示を更新
                load_and_display_dataentry_info(dataset_id)
                progress.setValue(100)
                QTimer.singleShot(100, progress.close)
            else:
                progress.close()
                QMessageBox.warning(widget, "取得エラー", "データエントリー情報の取得に失敗しました。")
            
        except ImportError:
            logger.warning("データエントリーロジックモジュールが見つかりません。ダミーデータで対応します。")
            # データエントリーロジックモジュールが見つからない場合、ダミーデータで対応
            progress.close()
            # QMessageBox.information(widget, "開発中", "データエントリー取得機能は開発中です。\n既存のJSONファイルがあれば表示されます。")
            load_and_display_dataentry_info(dataset_id)
            
        except Exception as e:
            logger.error("データエントリー取得エラー: %s", e, exc_info=True)
            if progress:
                progress.close()
            dataset_info_label.setText(f"データセット: {dataset_id} (取得エラー)")
            entry_count_label.setText("データエントリー件数: エラー")
            last_updated_label.setText("最終取得: エラー")

            try:
                bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
                if not bearer_token:
                    QMessageBox.warning(widget, "エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
                    return

                from classes.basic.core.basic_info_logic import fetch_data_entry_info_from_api
                output_dir = get_dynamic_file_path("output/rde/data/dataEntry")

                if force_refresh:
                    dataentry_file = os.path.join(output_dir, f"{dataset_id}.json")
                    if os.path.exists(dataentry_file):
                        os.remove(dataentry_file)
                        logger.info("強制更新のため既存ファイルを削除: %s", dataentry_file)

                fetch_data_entry_info_from_api(bearer_token, dataset_id, output_dir)
                QTimer.singleShot(500, lambda: load_and_display_dataentry_info(dataset_id))
            except Exception as fallback_error:
                logger.error("データエントリー取得フォールバックも失敗: %s", fallback_error, exc_info=True)
                QMessageBox.critical(widget, "エラー", f"データエントリー情報の取得に失敗しました:\n{fallback_error}")
    
    def load_and_display_dataentry_info(dataset_id):
        """JSONファイルからデータエントリー情報を読み込んで表示"""
        try:
            dataentry_file = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")

            if not os.path.exists(dataentry_file):
                dataset_info_label.setText(f"データセット: {dataset_id} (データなし)")
                entry_count_label.setText("データエントリー件数: 0")
                last_updated_label.setText("最終取得: なし")
                clear_entry_table_widgets()
                entry_table.setRowCount(0)
                entry_table.clear_footer_row()
                update_summary_display(finalize_summary(create_empty_summary()))
                return

            with open(dataentry_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            entry_count = len(data.get('data', []))
            file_mtime = os.path.getmtime(dataentry_file)
            last_updated = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')

            dataset_info_label.setText(f"データセット: {dataset_id}")
            entry_count_label.setText(f"データエントリー件数: {entry_count}件")
            last_updated_label.setText(f"最終取得: {last_updated} path: {dataentry_file}")

            included_files = {
                item.get('id'): item
                for item in data.get('included', [])
                if item.get('type') == 'file' and item.get('id')
            }
            entry_contexts = [
                {
                    "entry": entry,
                    "dataset_id": dataset_id,
                    "file_lookup": included_files,
                    "prefix_dataset": False,
                }
                for entry in data.get('data', [])
            ]
            populate_entry_table_rows(entry_contexts)

        except Exception as e:
            logger.error("データエントリー情報表示エラー: %s", e, exc_info=True)
            QMessageBox.critical(widget, "エラー", f"データエントリー情報の表示に失敗しました:\n{e}")
            dataset_info_label.setText(f"データセット: {dataset_id} (表示エラー)")
            entry_count_label.setText("データエントリー件数: エラー")
            last_updated_label.setText("最終取得: エラー")
            update_summary_display(finalize_summary(create_empty_summary()))
    
    def show_all_entries():
        """全データエントリーを表示"""
        try:
            dataentry_dir = get_dynamic_file_path("output/rde/data/dataEntry")
            if not os.path.exists(dataentry_dir):
                QMessageBox.warning(widget, "警告", "データエントリーディレクトリが見つかりません。")
                return
            
            entry_contexts = []
            json_files = [f for f in os.listdir(dataentry_dir) if f.endswith('.json')]
            for json_file in json_files:
                dataset_id = json_file[:-5]
                filepath = os.path.join(dataentry_dir, json_file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    included_files = {
                        item.get('id'): item
                        for item in data.get('included', [])
                        if item.get('type') == 'file' and item.get('id')
                    }
                    for entry in data.get('data', []):
                        entry_contexts.append({
                            "entry": entry,
                            "dataset_id": dataset_id,
                            "file_lookup": included_files,
                            "prefix_dataset": True,
                        })
                except Exception as e:
                    logger.error("%s 読み込みエラー: %s", json_file, e)

            dataset_info_label.setText("データセット: 全エントリー表示")
            entry_count_label.setText(f"データエントリー件数: {len(entry_contexts)}件")
            last_updated_label.setText("最終取得: 全ファイル統合")
            populate_entry_table_rows(entry_contexts)
            
        except Exception as e:
            QMessageBox.critical(widget, "エラー", f"全エントリー表示中にエラーが発生しました:\n{e}")
            update_summary_display(finalize_summary(create_empty_summary()))
    
    # イベントハンドラー
    def on_dataset_selection_changed():
        """データセット選択変更時のハンドラー"""
        _update_launch_button_state()
        update_dataentry_display()
    
    def on_fetch_button_clicked():
        """データエントリー取得ボタンクリック時のハンドラー"""
        dataset_id = get_selected_dataset_id()
        if not dataset_id:
            QMessageBox.warning(widget, "警告", "データセットを選択してください。")
            return
        
        force_refresh = force_refresh_checkbox.isChecked()
        update_dataentry_display(dataset_id, force_refresh)
    
    def on_refresh_dataset_clicked():
        """データセット一覧更新ボタンクリック時のハンドラー"""
        refresh_dataset_sources("button")
    
    def on_filter_changed():
        """フィルタ変更時のハンドラー"""
        populate_dataset_combo_with_filter()
    
    # イベント接続
    dataset_combo.currentTextChanged.connect(on_dataset_selection_changed)
    dataset_combo.currentIndexChanged.connect(lambda *_: _update_launch_button_state())
    fetch_button.clicked.connect(on_fetch_button_clicked)
    refresh_dataset_button.clicked.connect(on_refresh_dataset_clicked)
    show_all_entries_button.clicked.connect(show_all_entries)
    
    # フィルタ変更時のイベント接続
    filter_user_only_radio.toggled.connect(on_filter_changed)
    filter_others_only_radio.toggled.connect(on_filter_changed)
    filter_all_radio.toggled.connect(on_filter_changed)
    # サブグループフィルタ除去
    grant_filter_input.textChanged.connect(on_filter_changed)
    
    # 初期データ読み込みと表示時の自動更新をセット
    QTimer.singleShot(100, lambda: refresh_dataset_sources("initial"))
    _update_launch_button_state()

    def _apply_dataset_launch_payload(payload: DatasetPayload) -> bool:
        if not payload or not payload.id:
            return False
        relax_dataset_dataentry_filters_for_launch(
            filter_all_radio,
            (filter_user_only_radio, filter_others_only_radio),
            grant_filter_input,
            populate_dataset_combo_with_filter,
        )
        dataset_map = getattr(widget, 'dataset_map', {}) or {}
        if payload.raw:
            dataset_map[payload.id] = payload.raw
            widget.dataset_map = dataset_map

        index = _find_dataset_index(payload.id)
        if index < 0:
            try:
                filter_all_radio.setChecked(True)
                grant_filter_input.clear()
            except Exception:
                pass
            populate_dataset_combo_with_filter()
            index = _find_dataset_index(payload.id)

        if index < 0:
            dataset_dict = dataset_map.get(payload.id) or _load_dataset_record(payload.id)
            if dataset_dict is None:
                return False
            display_text = payload.display_text or _format_dataset_display(dataset_dict, payload.id)
            dataset_combo.blockSignals(True)
            dataset_combo.addItem(display_text, payload.id)
            dataset_combo.blockSignals(False)
            index = dataset_combo.count() - 1
            dataset_map[payload.id] = dataset_dict
            widget.dataset_map = dataset_map

        if index < 0:
            return False

        previous_index = dataset_combo.currentIndex()
        dataset_combo.setCurrentIndex(index)
        if previous_index == index:
            try:
                update_dataentry_display(payload.id)
            except Exception:
                logger.debug("dataset_dataentry: manual data refresh failed", exc_info=True)
        _update_launch_button_state()
        return True

    DatasetLaunchManager.instance().register_receiver("dataset_dataentry", _apply_dataset_launch_payload)

    # 他タブから明示的に再利用できるように属性公開
    widget.refresh_dataset_combo = refresh_dataset_sources
    widget.add_show_refresh_callback(lambda: refresh_dataset_sources("showEvent"))
    
    widget.setLayout(layout)
    return widget

from qt_compat.widgets import QWidget, QHBoxLayout, QComboBox, QPushButton, QLabel

class DatasetDataEntryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # ラベル
        label = QLabel("データエントリーを表示するデータセット:")
        layout.addWidget(label)

        # 横並びウィジェット
        h_widget = QWidget()
        h_layout = QHBoxLayout(h_widget)
        h_layout.setContentsMargins(0, 0, 0, 0)

        # コンボボックス
        self.dataset_combo = QComboBox()
        h_layout.addWidget(self.dataset_combo)

        # リスト表示ボタン
        self.show_all_btn = QPushButton("▼")
        self.show_all_btn.setToolTip("全件リスト表示")
        self.show_all_btn.setFixedWidth(28)
        h_layout.addWidget(self.show_all_btn)

        # 横並びウィジェットをレイアウトに追加
        layout.addWidget(h_widget)

        # ボタン押下時にドロップダウンを開く
        self.show_all_btn.clicked.connect(self.dataset_combo.showPopup)


class EntryTableWidget(QTableWidget):
    """データエントリー表示用テーブル（フッタ保持対応）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._footer_row_index = None

    def set_footer_row_index(self, row_index):
        self._footer_row_index = row_index

    def clear_footer_row(self):
        self._footer_row_index = None

    def sortItems(self, column, order=Qt.AscendingOrder):
        footer_items = None
        if self._footer_row_index is not None and 0 <= self._footer_row_index < self.rowCount():
            footer_items = []
            for col in range(self.columnCount()):
                footer_items.append(self.takeItem(self._footer_row_index, col))
            self.removeRow(self._footer_row_index)
            self._footer_row_index = None
        super().sortItems(column, order)
        if footer_items is not None:
            new_row = self.rowCount()
            self.insertRow(new_row)
            for col, item in enumerate(footer_items):
                if item is None:
                    item = QTableWidgetItem("")
                self.setItem(new_row, col, item)
            self._footer_row_index = new_row