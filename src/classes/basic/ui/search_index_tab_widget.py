from __future__ import annotations

from typing import Any

from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
)
from qt_compat.core import Qt

from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color
from classes.utils.button_styles import get_button_style
from classes.core.rde_search_index import (
    ensure_rde_search_index,
    get_index_overview,
)


class RdeSearchIndexTabWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._index_payload: dict[str, Any] = {}
        self._build_ui()
        self.reload_index(force_rebuild=False)

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("🔎 検索インデックス")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        root.addWidget(title)

        desc = QLabel("RDEデータの検索用インデックスを表示・列挙・更新します。")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        root.addWidget(desc)

        action_row = QHBoxLayout()
        self.reload_btn = QPushButton("再読み込み")
        self.rebuild_btn = QPushButton("再構築")
        self.reload_btn.setStyleSheet(get_button_style("secondary"))
        self.rebuild_btn.setStyleSheet(get_button_style("warning"))
        self.reload_btn.clicked.connect(lambda: self.reload_index(force_rebuild=False))
        self.rebuild_btn.clicked.connect(lambda: self.reload_index(force_rebuild=True))

        action_row.addWidget(self.reload_btn)
        action_row.addWidget(self.rebuild_btn)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.status = QLabel("待機中")
        root.addWidget(self.status)

        field_row = QHBoxLayout()
        field_label = QLabel("列挙フィールド")
        self.field_combo = QComboBox(self)
        self.field_combo.currentIndexChanged.connect(self._refresh_rows)
        field_row.addWidget(field_label)
        field_row.addWidget(self.field_combo, 1)
        root.addLayout(field_row)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["キー", "データセット件数"])
        root.addWidget(self.table, 1)

    def reload_index(self, force_rebuild: bool):
        self._index_payload = ensure_rde_search_index(force_rebuild=force_rebuild)
        overview = get_index_overview(self._index_payload)
        self.status.setText(
            f"更新: {overview.get('generated_at', '')} / dataset={overview.get('dataset_count', 0)}"
        )

        reverse = self._index_payload.get("reverse") if isinstance(self._index_payload.get("reverse"), dict) else {}
        fields = sorted([k for k, v in reverse.items() if isinstance(v, dict)])

        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        for field in fields:
            count = len(reverse.get(field, {}))
            self.field_combo.addItem(f"{field} ({count})", field)
        self.field_combo.blockSignals(False)

        if self.field_combo.count() > 0:
            self.field_combo.setCurrentIndex(0)
            self._refresh_rows()
        else:
            self.table.setRowCount(0)

    def _refresh_rows(self):
        reverse = self._index_payload.get("reverse") if isinstance(self._index_payload.get("reverse"), dict) else {}
        current_field = self.field_combo.currentData(Qt.UserRole)
        if not isinstance(current_field, str):
            current_field = self.field_combo.currentData()
        field_map = reverse.get(str(current_field or ""), {}) if isinstance(reverse, dict) else {}
        if not isinstance(field_map, dict):
            field_map = {}

        rows = []
        for key, dataset_ids in field_map.items():
            if not isinstance(dataset_ids, list):
                continue
            rows.append((str(key), len(dataset_ids)))
        rows.sort(key=lambda x: (-x[1], x[0]))

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for key, count in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            key_item = QTableWidgetItem(key)
            count_item = QTableWidgetItem(str(count))
            key_item.setFlags(key_item.flags() ^ Qt.ItemIsEditable)
            count_item.setFlags(count_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, count_item)

        self.table.setSortingEnabled(True)


def create_rde_search_index_tab(parent: QWidget | None = None) -> RdeSearchIndexTabWidget:
    return RdeSearchIndexTabWidget(parent)
