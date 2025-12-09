from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from qt_compat import QtCore
from qt_compat.widgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from classes.theme import ThemeKey, ThemeManager, get_color
from config.common import GROUP_ORGNIZATION_DIR

logger = logging.getLogger(__name__)


@dataclass
class ProjectFileInfo:
    path: Path
    file_name: str
    display_name: str
    group_names: List[str]
    organization_names: List[str]
    group_count: int
    source: str  # "default" or "external"


def _extract_group_name(entity: object) -> Optional[str]:
    if not isinstance(entity, dict):
        return None
    if entity.get("type") != "group":
        return None
    attrs = entity.get("attributes") or {}
    name = attrs.get("name") or entity.get("id")
    return str(name) if name else None


def parse_project_file(path: Path, source: str) -> Optional[ProjectFileInfo]:
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("プロジェクトファイル読み込み失敗: %s (%s)", path, exc)
        return None

    group_names: List[str] = []
    organization_names: List[str] = []
    root_data = data.get("data")
    root_display_name: Optional[str] = None
    if isinstance(root_data, list):
        for entry in root_data:
            root_display_name = _extract_group_name(entry)
            if root_display_name:
                break
    else:
        root_display_name = _extract_group_name(root_data)
    for item in data.get("included", []):
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes", {})
        if item.get("type") == "group":
            name = attrs.get("name") or item.get("id", "")
            if name:
                group_names.append(str(name))
        elif item.get("type") == "organization":
            name = attrs.get("nameJa") or attrs.get("nameEn") or item.get("id", "")
            if name:
                organization_names.append(str(name))

    display_name = root_display_name or (group_names[0] if group_names else path.stem)
    info = ProjectFileInfo(
        path=path,
        file_name=path.name,
        display_name=display_name,
        group_names=group_names,
        organization_names=organization_names,
        group_count=len(group_names),
        source=source,
    )
    return info


def scan_default_project_files() -> List[ProjectFileInfo]:
    base_dir = Path(GROUP_ORGNIZATION_DIR)
    if not base_dir.exists():
        return []
    infos: List[ProjectFileInfo] = []
    for json_path in sorted(base_dir.glob("*.json")):
        info = parse_project_file(json_path, source="default")
        if info:
            infos.append(info)
    return infos


class ProjectFileSelectionDialog(QDialog):
    """Allow users to pick which project files should be included."""

    def __init__(
        self,
        default_files: List[ProjectFileInfo],
        selected_file_names: Iterable[str],
        external_files: Sequence[str],
        parent=None,
    ):
        super().__init__(parent)
        self._theme = ThemeManager.instance()
        self._default_files = default_files
        self._selected_names = {name.lower() for name in selected_file_names}
        self._items: List[ProjectFileInfo] = [*default_files]
        self._list_widget: QListWidget
        self._details: QTextEdit
        self._button_box: QDialogButtonBox
        self._build_ui()
        self._import_external_files(external_files)
        self._refresh_details()

    def _build_ui(self):
        self.setWindowTitle("プロジェクトファイルの選択")
        self.resize(640, 480)
        layout = QVBoxLayout(self)

        desc = QLabel("出力対象のプロジェクトファイルを選択してください。")
        layout.addWidget(desc)

        self._list_widget = QListWidget()
        self._list_widget.itemSelectionChanged.connect(self._refresh_details)
        self._list_widget.itemChanged.connect(self._sync_button_state)
        layout.addWidget(self._list_widget, 1)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("すべて選択")
        select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(select_all_btn)

        clear_btn = QPushButton("選択解除")
        clear_btn.clicked.connect(self._clear_selection)
        btn_row.addWidget(clear_btn)

        add_btn = QPushButton("外部ファイルを追加…")
        add_btn.clicked.connect(self._handle_add_external)
        btn_row.addWidget(add_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setMinimumHeight(140)
        layout.addWidget(self._details)

        self._button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._populate_list()
        self._apply_theme(self._theme.get_mode())
        self._theme.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, mode):  # noqa: D401
        palette_color = get_color(ThemeKey.TEXT_PRIMARY)
        bg_color = get_color(ThemeKey.WINDOW_BACKGROUND)
        self.setStyleSheet(f"color: {palette_color}; background-color: {bg_color};")

    def _populate_list(self):
        self._list_widget.clear()
        for info in self._items:
            self._add_list_item(info)

    def _add_list_item(self, info: ProjectFileInfo):
        label = f"{info.display_name} ({info.group_count}件)"
        if info.source == "external":
            label = f"[追加] {label}"
        item = QListWidgetItem(label)
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsSelectable)
        checked = info.source == "external" or info.file_name.lower() in self._selected_names
        item.setCheckState(QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, info)
        item.setToolTip("\n".join(info.group_names[:10]))
        self._list_widget.addItem(item)

    def _refresh_details(self):
        item = self._list_widget.currentItem()
        if not item:
            self._details.setPlainText("ファイルを選択すると詳細を表示します。")
            return
        info: ProjectFileInfo = item.data(QtCore.Qt.ItemDataRole.UserRole)
        orgs = info.organization_names[:10]
        groups = info.group_names[:10]
        lines = [
            f"ファイル: {info.file_name}",
            f"パス: {info.path}",
            f"種類: {'既定' if info.source == 'default' else '追加'}",
            f"グループ数: {info.group_count}",
        ]
        if groups:
            lines.append("")
            lines.append("グループ名 (最大10件):")
            lines.extend(f"  - {name}" for name in groups)
        if orgs:
            lines.append("")
            lines.append("組織名 (最大10件):")
            lines.extend(f"  - {name}" for name in orgs)
        self._details.setPlainText("\n".join(lines))

    def _select_all(self):
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            item.setCheckState(QtCore.Qt.CheckState.Checked)

    def _clear_selection(self):
        for index in range(self._list_widget.count()):
            info: ProjectFileInfo = self._list_widget.item(index).data(QtCore.Qt.ItemDataRole.UserRole)
            if info.source == "default":
                self._list_widget.item(index).setCheckState(QtCore.Qt.CheckState.Unchecked)

    def _handle_add_external(self):
        start_dir = Path(GROUP_ORGNIZATION_DIR)
        if not start_dir.exists():
            start_dir = Path.home()
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "プロジェクトファイルを追加",
            str(start_dir),
            "JSON Files (*.json);;All Files (*)",
        )
        if not paths:
            return
        added = 0
        for path_str in paths:
            new_info = self._parse_external_file(path_str)
            if new_info:
                self._items.append(new_info)
                self._add_list_item(new_info)
                added += 1
        if added:
            self._list_widget.setCurrentRow(self._list_widget.count() - 1)
            self._refresh_details()

    def _parse_external_file(self, path_str: str) -> Optional[ProjectFileInfo]:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "ファイルがありません", f"指定されたファイルが存在しません:\n{path}")
            return None
        info = parse_project_file(path, source="external")
        if not info:
            QMessageBox.warning(self, "読み込み失敗", f"プロジェクトファイルの読み込みに失敗しました:\n{path}")
            return None
        for existing in self._items:
            if existing.path.resolve() == info.path.resolve():
                QMessageBox.information(self, "既に追加済み", "このファイルは既にリストに存在します。")
                return None
        return info

    def _sync_button_state(self):  # noqa: D401
        # Placeholder for future validation if needed.
        pass

    def _import_external_files(self, paths: Sequence[str]):
        for path_str in paths:
            info = self._parse_external_file(path_str)
            if info:
                # Replace duplicate if found
                self._items.append(info)
                self._add_list_item(info)

    def selected_files(self) -> Tuple[List[str], List[str]]:
        default_files: List[str] = []
        external_files: List[str] = []
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            if item.checkState() != QtCore.Qt.CheckState.Checked:
                continue
            info: ProjectFileInfo = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if info.source == "default":
                default_files.append(info.file_name)
            else:
                external_files.append(str(info.path))
        return default_files, external_files
