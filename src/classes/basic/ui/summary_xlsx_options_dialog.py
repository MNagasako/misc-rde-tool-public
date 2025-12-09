from __future__ import annotations

"""Dialog helpers for selecting the summary XLSX export mode."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from qt_compat import QtCore
from qt_compat.widgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from classes.basic.conf.summary_export_options import (
    SummaryExportMode,
    SummaryExportOptions,
)
from classes.theme import ThemeManager, ThemeKey, get_color
from config.common import GROUP_ORGNIZATION_DIR
from .project_file_selection_dialog import (
    ProjectFileSelectionDialog,
    scan_default_project_files,
)

logger = logging.getLogger(__name__)


@dataclass
class GroupDisplayItem:
    group_id: str
    name: str
    source_file: str


def parse_group_display_items(json_path: Path) -> List[GroupDisplayItem]:
    with json_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    items: List[GroupDisplayItem] = []
    for included in data.get("included", []):
        if included.get("type") != "group":
            continue
        group_id = included.get("id")
        if not group_id:
            continue
        attrs = included.get("attributes", {})
        name = attrs.get("name") or f"(ID:{group_id})"
        items.append(GroupDisplayItem(group_id=group_id, name=name, source_file=json_path.name))
    return items


def load_group_display_items() -> List[GroupDisplayItem]:
    """Read every ``groupOrgnizations`` file and extract TEAM groups."""

    base_dir = Path(GROUP_ORGNIZATION_DIR)
    items: List[GroupDisplayItem] = []
    if not base_dir.exists():
        return items

    seen_ids: set[str] = set()
    for json_path in sorted(base_dir.glob("*.json")):
        try:
            file_items = parse_group_display_items(json_path)
        except Exception as exc:
            # Keep going even if one file is broken.
            logger.warning("group JSON読み込み失敗: %s (%s)", json_path, exc)
            continue

        for item in file_items:
            if item.group_id in seen_ids:
                continue
            items.append(item)
            seen_ids.add(item.group_id)
    return items


class SummaryXlsxOptionsDialog(QDialog):
    """Collects user preferences for the summary export."""

    def __init__(self, groups: List[GroupDisplayItem], parent=None):
        super().__init__(parent)
        self._base_group_items = list(groups)
        self._extra_project_files: List[str] = []
        self._extra_group_items: Dict[str, List[GroupDisplayItem]] = {}
        self._project_file_infos = scan_default_project_files()
        if self._project_file_infos:
            self._selected_project_files = [info.file_name for info in self._project_file_infos]
        else:
            self._selected_project_files = sorted({item.source_file for item in self._base_group_items})
        self._theme = ThemeManager.instance()
        self._mode_radios: Dict[SummaryExportMode, QRadioButton] = {}
        self._group_list: QListWidget
        self._filter_input: QLineEdit
        self._suffix_input: QLineEdit
        self._project_summary_label: QLabel
        self._build_ui()
        self._apply_theme(self._theme.get_mode())
        self._theme.theme_changed.connect(self._apply_theme)

    # ------------------------------------------------------------------
    # Qt UI helpers
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.setWindowTitle("まとめXLSXの出力設定")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("出力モードを選択してください。"))

        self._mode_radios = {
            SummaryExportMode.MERGED: QRadioButton("統合モード (従来通り1ファイル)"),
            SummaryExportMode.PER_FILE: QRadioButton("プロジェクトファイルごとに分割"),
            SummaryExportMode.CUSTOM_SELECTION: QRadioButton("任意のサブグループのみ出力"),
        }
        self._mode_radios[SummaryExportMode.MERGED].setChecked(True)

        for radio in self._mode_radios.values():
            layout.addWidget(radio)
            radio.toggled.connect(self._handle_mode_change)

        if not self._base_group_items:
            # Disable modes that require group metadata.
            self._mode_radios[SummaryExportMode.PER_FILE].setEnabled(False)
            self._mode_radios[SummaryExportMode.CUSTOM_SELECTION].setEnabled(False)

        project_row = QHBoxLayout()
        project_row.addWidget(QLabel("プロジェクトファイル"))
        self._project_summary_label = QLabel(self._format_project_summary())
        project_row.addWidget(self._project_summary_label, 1)
        project_button = QPushButton("選択…")
        project_button.clicked.connect(self._open_project_file_dialog)
        project_row.addWidget(project_button)
        layout.addLayout(project_row)

        # Selection panel for the custom mode
        selection_box = QVBoxLayout()
        selection_header = QHBoxLayout()
        selection_label = QLabel("サブグループを複数選択 (カスタムモード専用)")
        selection_header.addWidget(selection_label)
        selection_box.addLayout(selection_header)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("名称やファイル名でフィルタ")
        self._filter_input.textChanged.connect(self._apply_filter)
        selection_box.addWidget(self._filter_input)

        self._group_list = QListWidget()
        self._group_list.setSelectionMode(QListWidget.MultiSelection)
        self._populate_group_list()
        selection_box.addWidget(self._group_list)

        self._suffix_input = QLineEdit()
        self._suffix_input.setPlaceholderText("ファイル名サフィックス (例: physics_team)")
        selection_box.addWidget(self._suffix_input)

        layout.addLayout(selection_box)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Initial state
        self._set_custom_controls_enabled(False)

    def _apply_theme(self, mode):
        palette_color = get_color(ThemeKey.TEXT_PRIMARY)
        self.setStyleSheet(f"color: {palette_color};")

    def _handle_mode_change(self):
        enable = self._mode_radios[SummaryExportMode.CUSTOM_SELECTION].isChecked()
        self._set_custom_controls_enabled(enable)

    def _set_custom_controls_enabled(self, enabled: bool):
        self._group_list.setEnabled(enabled)
        self._filter_input.setEnabled(enabled)
        self._suffix_input.setEnabled(enabled)

    def _apply_filter(self, text: str):
        pattern = text.strip().lower()
        for index in range(self._group_list.count()):
            item = self._group_list.item(index)
            data: GroupDisplayItem = item.data(QtCore.Qt.ItemDataRole.UserRole)
            visible = not pattern or pattern in data.name.lower() or pattern in data.source_file.lower()
            item.setHidden(not visible)

    def _handle_accept(self):
        mode = self.selected_mode
        if mode == SummaryExportMode.CUSTOM_SELECTION:
            selected = self._selected_group_ids
            if not selected:
                QMessageBox.warning(self, "サブグループ未選択", "カスタムモードでは1件以上選択してください。")
                return
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def selected_mode(self) -> SummaryExportMode:
        for mode, radio in self._mode_radios.items():
            if radio.isChecked():
                return mode
        return SummaryExportMode.MERGED

    @property
    def _selected_group_ids(self) -> List[str]:
        ids: List[str] = []
        for item_index in range(self._group_list.count()):
            item = self._group_list.item(item_index)
            if item.isSelected():
                data: GroupDisplayItem = item.data(QtCore.Qt.ItemDataRole.UserRole)
                ids.append(data.group_id)
        return ids

    def build_options(self) -> SummaryExportOptions:
        options = SummaryExportOptions(
            mode=self.selected_mode,
            selected_group_ids=self._selected_group_ids,
            custom_suffix=self._suffix_input.text().strip() or None,
            extra_project_files=list(self._extra_project_files),
            project_files=list(self._selected_project_files),
        )
        return options.with_sanitized_suffix()

    def all_groups(self) -> List[GroupDisplayItem]:
        return self._collect_group_items()

    def extra_project_files(self) -> List[str]:
        return list(self._extra_project_files)

    def _collect_group_items(self) -> List[GroupDisplayItem]:
        allowed_defaults = {name.lower() for name in self._selected_project_files if name}
        if allowed_defaults:
            items = [item for item in self._base_group_items if item.source_file.lower() in allowed_defaults]
        else:
            items = []
        for values in self._extra_group_items.values():
            items.extend(values)
        return items

    def _populate_group_list(self):
        selected_ids = set(self._selected_group_ids)
        self._group_list.clear()
        for item in self._collect_group_items():
            list_item = QListWidgetItem(f"{item.name} ({item.source_file})")
            list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item)
            self._group_list.addItem(list_item)
            if item.group_id in selected_ids:
                list_item.setSelected(True)
        self._apply_filter(self._filter_input.text())

    def _format_project_summary(self) -> str:
        count_default = len(self._selected_project_files)
        count_extra = len(self._extra_project_files)
        if count_default == 0 and count_extra == 0:
            return "(未選択)"
        parts = []
        if count_default:
            parts.append(f"既定:{count_default}件")
        if count_extra:
            parts.append(f"追加:{count_extra}件")
        return " / ".join(parts)

    def _open_project_file_dialog(self):
        dialog = ProjectFileSelectionDialog(
            self._project_file_infos,
            selected_file_names=self._selected_project_files,
            external_files=self._extra_project_files,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        default_files, external_files = dialog.selected_files()
        self._selected_project_files = default_files
        self._extra_project_files = external_files
        self._project_summary_label.setText(self._format_project_summary())
        self._reload_extra_groups()

    def _reload_extra_groups(self):
        previous_selection = set(self._selected_group_ids)
        self._extra_group_items = {}
        errors: List[str] = []
        for file_path in self._extra_project_files:
            json_path = Path(file_path)
            if not json_path.exists():
                errors.append(f"{json_path.name}: ファイルが存在しません")
                continue
            try:
                items = parse_group_display_items(json_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("追加プロジェクト読み込み失敗: %s (%s)", json_path, exc)
                errors.append(f"{json_path.name}: 読み込みに失敗しました")
                continue
            self._extra_group_items[file_path] = items
        if errors:
            QMessageBox.warning(self, "読み込みエラー", "\n".join(errors[:5]))
        self._populate_group_list()
        self._restore_group_selection(previous_selection)

    def _restore_group_selection(self, selected_ids: set[str]):
        if not selected_ids:
            return
        for index in range(self._group_list.count()):
            item = self._group_list.item(index)
            data: GroupDisplayItem = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if data.group_id in selected_ids:
                item.setSelected(True)


def prompt_summary_export_options(parent=None) -> Optional[SummaryExportOptions]:
    """Show the dialog and return the resulting options."""

    groups = load_group_display_items()
    dialog = SummaryXlsxOptionsDialog(groups, parent=parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        options = dialog.build_options()
        return options.ensure_valid_selection(g.group_id for g in dialog.all_groups())
    return None
