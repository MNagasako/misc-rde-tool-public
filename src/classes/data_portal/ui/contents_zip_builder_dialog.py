from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from qt_compat.widgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from qt_compat.core import Qt

from classes.theme import ThemeKey, get_color
from classes.utils.themed_checkbox_delegate import ThemedCheckboxDelegate


@dataclass
class ContentsZipCandidate:
    checked: bool
    file_id: str
    file_name: str
    file_type: str
    file_size: int
    data_entry_id: str
    tile_name: str
    tile_number: str
    local_path: str
    exists_locally: bool


def _format_bytes(num_bytes: int) -> str:
    size = float(max(0, int(num_bytes or 0)))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(num_bytes)} B"


class ContentsZipBuilderDialog(QDialog):
    """コンテンツZIP自動作成用: 対象ファイル選択ダイアログ"""

    COL_CHECK = 0
    COL_TYPE = 1
    COL_NAME = 2
    COL_SIZE = 3
    COL_TILE = 4
    COL_EXISTS = 5

    def __init__(self, parent, candidates: List[ContentsZipCandidate]):
        super().__init__(parent)
        self.setWindowTitle("コンテンツZIP 自動作成 - 対象ファイル選択")
        self._candidates: List[ContentsZipCandidate] = list(candidates or [])

        layout = QVBoxLayout()

        info = QLabel(
            "NONSHARED_RAW は除外済みです。\n"
            "チェックを外したファイルはZIPに含めません。"
        )
        info.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        layout.addWidget(info)

        layout.addWidget(self._create_bulk_ops_group())

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["", "タイプ", "ファイル名", "サイズ", "タイル", "既存"])
        self.table.setRowCount(len(self._candidates))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)

        # チェック列の見分けやすさ改善（テーマ対応）
        try:
            self.table.setItemDelegateForColumn(self.COL_CHECK, ThemedCheckboxDelegate(self.table))
        except Exception:
            pass

        self._populate_table()
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.table)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        layout.addWidget(self.summary_label)
        self._refresh_summary()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self.setMinimumWidth(900)

    def _create_bulk_ops_group(self) -> QGroupBox:
        group = QGroupBox("一括操作")
        h = QHBoxLayout()

        self.type_combo = QComboBox()
        self.type_combo.addItem("すべて", userData=None)
        for ft in sorted({c.file_type for c in self._candidates}):
            self.type_combo.addItem(ft, userData=ft)
        h.addWidget(QLabel("対象タイプ:"))
        h.addWidget(self.type_combo)

        self.check_btn = QPushButton("全チェック")
        self.uncheck_btn = QPushButton("全解除")
        self.check_btn.clicked.connect(lambda: self._set_checked_for_selected_type(True))
        self.uncheck_btn.clicked.connect(lambda: self._set_checked_for_selected_type(False))
        h.addWidget(self.check_btn)
        h.addWidget(self.uncheck_btn)

        h.addStretch()

        self.check_all_btn = QPushButton("全タイプ: 全チェック")
        self.uncheck_all_btn = QPushButton("全タイプ: 全解除")
        self.check_all_btn.clicked.connect(lambda: self._set_checked_all(True))
        self.uncheck_all_btn.clicked.connect(lambda: self._set_checked_all(False))
        h.addWidget(self.check_all_btn)
        h.addWidget(self.uncheck_all_btn)

        group.setLayout(h)
        return group

    def _populate_table(self) -> None:
        self.table.blockSignals(True)
        try:
            for row, c in enumerate(self._candidates):
                # Check
                check_item = QTableWidgetItem()
                check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                check_item.setCheckState(Qt.Checked if c.checked else Qt.Unchecked)
                self.table.setItem(row, self.COL_CHECK, check_item)

                # Type
                self.table.setItem(row, self.COL_TYPE, QTableWidgetItem(str(c.file_type)))

                # Name
                name_item = QTableWidgetItem(str(c.file_name))
                name_item.setToolTip(c.local_path)
                self.table.setItem(row, self.COL_NAME, name_item)

                # Size
                self.table.setItem(row, self.COL_SIZE, QTableWidgetItem(_format_bytes(c.file_size)))

                # Tile
                tile = f"{c.tile_number}_{c.tile_name}" if c.tile_name or c.tile_number else "-"
                self.table.setItem(row, self.COL_TILE, QTableWidgetItem(tile))

                # Exists
                self.table.setItem(row, self.COL_EXISTS, QTableWidgetItem("既存" if c.exists_locally else "-"))
        finally:
            self.table.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item is None:
            return
        if item.column() != self.COL_CHECK:
            return
        row = item.row()
        if 0 <= row < len(self._candidates):
            self._candidates[row].checked = item.checkState() == Qt.Checked
            self._refresh_summary()

    def _set_checked_all(self, checked: bool) -> None:
        self.table.blockSignals(True)
        try:
            for row, c in enumerate(self._candidates):
                c.checked = checked
                it = self.table.item(row, self.COL_CHECK)
                if it is not None:
                    it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self.table.blockSignals(False)
        self._refresh_summary()

    def _set_checked_for_selected_type(self, checked: bool) -> None:
        selected_type = self.type_combo.currentData()
        if not selected_type:
            self._set_checked_all(checked)
            return

        self.table.blockSignals(True)
        try:
            for row, c in enumerate(self._candidates):
                if c.file_type != selected_type:
                    continue
                c.checked = checked
                it = self.table.item(row, self.COL_CHECK)
                if it is not None:
                    it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self.table.blockSignals(False)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        selected = [c for c in self._candidates if c.checked]
        total_size = sum(int(c.file_size or 0) for c in selected)
        types: Dict[str, int] = {}
        for c in selected:
            types[c.file_type] = types.get(c.file_type, 0) + 1

        type_text = ", ".join([f"{k}:{v}件" for k, v in sorted(types.items())]) if types else "(選択なし)"
        self.summary_label.setText(
            f"選択: {len(selected)}件 / 合計: {_format_bytes(total_size)} / {type_text}"
        )

    def get_selected(self) -> List[ContentsZipCandidate]:
        return [c for c in self._candidates if c.checked]
