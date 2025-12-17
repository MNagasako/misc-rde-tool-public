"""Shared dataset filter helper for combo boxes.

Provides grant/program/text filters (mirroring the Data Fetch 2 UX minus
wide-share/member controls) while keeping combo population logic reusable.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from qt_compat.core import Qt, QObject
from qt_compat.widgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from classes.dataset.util.dataset_dropdown_util import get_dataset_type_display_map
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)


class DatasetFilterFetcher(QObject):
    """Create and manage dataset filters bound to a combo box."""

    def __init__(
        self,
        dataset_json_path: str,
        info_json_path: Optional[str] = None,
        combo: Optional[QComboBox] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.dataset_json_path = dataset_json_path
        self.info_json_path = info_json_path
        self.combo = combo
        self._filter_widget: Optional[QWidget] = None
        self._program_combo: Optional[QComboBox] = None
        self._grant_edit: Optional[QLineEdit] = None
        self._search_edit: Optional[QLineEdit] = None
        self._count_label: Optional[QLabel] = None
        self._datasets: List[Dict] = []
        self._filtered_datasets: List[Dict] = []
        self._suppress_filters = False
        self._load_dataset_items()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_filter_panel(self, parent: Optional[QWidget] = None) -> QWidget:
        """Return (and lazily create) the filter panel widget."""

        if self._filter_widget:
            return self._filter_widget

        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        filters_layout = QHBoxLayout()
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(10)

        program_label = QLabel("プログラム / タイプ:")
        program_label.setStyleSheet("font-weight: bold;")
        program_combo = QComboBox()
        program_combo.setMinimumWidth(180)
        self._program_combo = program_combo
        self._populate_programs()
        self._program_combo.setCurrentIndex(0)

        grant_label = QLabel("課題番号:")
        grant_label.setStyleSheet("font-weight: bold;")
        grant_edit = QLineEdit()
        grant_edit.setPlaceholderText("部分一致で絞り込み (例: JPMXP1234)")
        grant_edit.setMinimumWidth(200)
        self._grant_edit = grant_edit

        search_label = QLabel("テキスト検索:")
        search_label.setStyleSheet("font-weight: bold;")
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("名前・タイトル・説明で検索")
        search_edit.setMinimumWidth(220)
        self._search_edit = search_edit

        filters_layout.addWidget(program_label)
        filters_layout.addWidget(program_combo)
        filters_layout.addWidget(grant_label)
        filters_layout.addWidget(grant_edit)
        filters_layout.addWidget(search_label)
        filters_layout.addWidget(search_edit)
        filters_layout.addStretch()

        layout.addLayout(filters_layout)

        count_label = QLabel("表示中: 0/0 件")
        count_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        count_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-weight: bold;"
        )
        self._count_label = count_label
        layout.addWidget(count_label)

        self._connect_filter_signals()
        self._filter_widget = container
        self.apply_filters()
        return container

    def apply_filters(self) -> None:
        """Apply current filters and refresh the combo box."""

        program_raw = self._program_combo.currentData() if self._program_combo else "all"
        program_filter = program_raw or "all"
        grant_filter = (self._grant_edit.text().strip() if self._grant_edit else "").lower()
        search_filter = (
            self._search_edit.text().strip() if self._search_edit else ""
        ).lower()

        filtered: List[Dict] = []
        for dataset in self._datasets:
            attr = dataset.get("attributes", {})
            dataset_type = attr.get("datasetType", "")
            grant_number = attr.get("grantNumber", "")
            search_blob = dataset.get("_search_blob", "")

            if program_filter != "all" and dataset_type != program_filter:
                continue
            if grant_filter and grant_filter not in grant_number.lower():
                continue
            if search_filter and search_filter not in search_blob:
                continue
            filtered.append(dataset)

        self._filtered_datasets = filtered
        self._update_combo()
        self._update_count_label()

    def show_all(self) -> None:
        """Reset filters and open the combo popup."""

        if self._program_combo:
            self._program_combo.setCurrentIndex(0)
        if self._grant_edit:
            self._grant_edit.clear()
        if self._search_edit:
            self._search_edit.clear()
        self.apply_filters()
        if self.combo and not os.environ.get("PYTEST_CURRENT_TEST"):
            self.combo.showPopup()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_dataset_items(self) -> None:
        if not self.dataset_json_path or not os.path.exists(self.dataset_json_path):
            logger.warning("dataset.json が見つかりません: %s", self.dataset_json_path)
            self._datasets = []
            return

        try:
            with open(self.dataset_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("dataset.json の読み込みに失敗: %s", exc)
            self._datasets = []
            return

        if isinstance(data, dict) and "data" in data:
            items = data["data"]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        datasets: List[Dict] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            attr = entry.get("attributes", {})
            search_parts = [
                attr.get("name", ""),
                attr.get("grantNumber", ""),
                attr.get("subjectTitle", ""),
                attr.get("description", ""),
            ]
            search_blob = " ".join(part for part in search_parts if part).lower()
            entry["_search_blob"] = search_blob
            datasets.append(entry)

        self._datasets = datasets

    def _populate_programs(self) -> None:
        if not self._program_combo:
            return

        type_map = get_dataset_type_display_map()
        self._program_combo.clear()
        self._program_combo.addItem("全て", "all")

        seen = set()
        for dataset in self._datasets:
            dtype = dataset.get("attributes", {}).get("datasetType")
            if dtype and dtype not in seen:
                seen.add(dtype)

        for dtype in sorted(seen):
            label = type_map.get(dtype, dtype)
            self._program_combo.addItem(label, dtype)

    def _connect_filter_signals(self) -> None:
        if self._program_combo:
            self._program_combo.currentIndexChanged.connect(lambda _: self.apply_filters())
        if self._grant_edit:
            self._grant_edit.textChanged.connect(lambda _: self.apply_filters())
        if self._search_edit:
            self._search_edit.textChanged.connect(self._on_search_text_changed)

    def _on_search_text_changed(self, text: str) -> None:
        if self._suppress_filters:
            return
        if self.combo and self.combo.lineEdit():
            self.combo.lineEdit().setText(text)
        self.apply_filters()

    def _update_combo(self) -> None:
        if not self.combo:
            return

        selected_id = self._current_selection_id()
        self._suppress_filters = True
        try:
            self.combo.blockSignals(True)
            self.combo.clear()

            display_list: List[str] = []
            for dataset in self._filtered_datasets:
                text = self._format_display_text(dataset)
                display_list.append(text)
                self.combo.addItem(text, dataset)

            if not self._filtered_datasets:
                placeholder = "-- 該当するデータセットがありません --"
                self.combo.addItem(placeholder, None)
                display_list.append(placeholder)

            completer = QCompleter(display_list, self.combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            popup_view = completer.popup()
            popup_view.setMinimumHeight(240)
            popup_view.setMaximumHeight(240)
            self.combo.setCompleter(completer)

            if selected_id:
                self._restore_selection(selected_id)
            else:
                self.combo.setCurrentIndex(-1)

            if self.combo.lineEdit():
                total = len(self._filtered_datasets)
                overall = len(self._datasets)
                placeholder = f"データセットを検索・選択 ({total}/{overall}件)"
                self.combo.lineEdit().setPlaceholderText(placeholder)
        finally:
            self.combo.blockSignals(False)
            self._suppress_filters = False

    def _current_selection_id(self) -> Optional[str]:
        if not self.combo:
            return None
        current_data = self.combo.currentData()
        if isinstance(current_data, dict):
            return current_data.get("id")
        return None

    def _restore_selection(self, dataset_id: str) -> None:
        if not self.combo or not dataset_id:
            return
        for index in range(self.combo.count()):
            data = self.combo.itemData(index)
            if isinstance(data, dict) and data.get("id") == dataset_id:
                self.combo.setCurrentIndex(index)
                return
        # If selection no longer exists, keep combo cleared
        self.combo.setCurrentIndex(-1)

    def _format_display_text(self, dataset: Dict) -> str:
        attr = dataset.get("attributes", {})
        grant = attr.get("grantNumber", "")
        subject = attr.get("subjectTitle", "")
        name = attr.get("name", "名前なし")
        dtype = attr.get("datasetType", "")
        type_map = get_dataset_type_display_map()
        type_label = type_map.get(dtype, dtype)

        parts: List[str] = []
        if grant:
            parts.append(grant)
        if subject:
            truncated_subject = subject[:30] + ("…" if len(subject) > 30 else "")
            parts.append(truncated_subject)
        truncated_name = name[:40] + ("…" if len(name) > 40 else "")
        parts.append(truncated_name)
        if type_label:
            parts.append(f"[{type_label}]")
        return " ".join(parts)

    def _update_count_label(self) -> None:
        if not self._count_label:
            return
        filtered = len(self._filtered_datasets)
        total = len(self._datasets)
        self._count_label.setText(f"表示中: {filtered}/{total} 件")
