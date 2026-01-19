"""共通情報取得2: 取得対象/条件の事前選択ダイアログ

- 既存「共通情報のみ取得」は維持し、新ボタンで本ダイアログを使用する。
- 選択状態は app_config.json に永続化する。

注意:
- HTTPアクセスはここでは行わない（実行は core 側）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from qt_compat.widgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qt_compat.core import Qt

from classes.theme import ThemeManager, ThemeKey, get_color
from classes.managers.app_config_manager import get_config_manager

from ..core.common_info_selection_logic import (
    CommonInfo2Keys,
    build_common_info2_target_specs,
    compute_local_status_for_target,
    compute_local_timestamp_for_target,
)

logger = logging.getLogger(__name__)


_CONFIG_KEY = "basic.common_info2"


def load_common_info2_selection_state() -> Dict[str, Any]:
    cfg = get_config_manager()
    state = cfg.get(_CONFIG_KEY, None)
    if isinstance(state, dict):
        return state
    return {}


def save_common_info2_selection_state(state: Dict[str, Any]) -> None:
    cfg = get_config_manager()
    cfg.set(_CONFIG_KEY, state)
    cfg.save()


@dataclass(frozen=True)
class _RowBinding:
    target_id: str
    checkbox: QCheckBox
    mode_combo: QComboBox


class CommonInfoSelectionDialog(QDialog):
    """共通情報取得2の事前選択ダイアログ"""

    _DEFAULT_MODE = "older"

    def __init__(self, parent=None, initial_state: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("共通情報取得2 - 取得対象の選択")
        self.setMinimumWidth(980)
        self.setMinimumHeight(520)

        self._theme_manager = ThemeManager.instance()
        self._row_bindings: list[_RowBinding] = []

        self._state: Dict[str, Any] = dict(initial_state or {})
        self._state.setdefault("targets", {})
        self._state.setdefault("include_dataset_details", False)
        self._state.setdefault("outdated_policy", "bca")
        self._state.setdefault("stale_days", 30)

        self._build_ui()
        self._theme_manager.theme_changed.connect(self._apply_theme)
        self._apply_theme(self._theme_manager.get_mode())

        self._refresh_table()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        hint = QLabel(
            "取得対象ごとに『上書き/古い場合/無い場合/スキップ』を選択できます。\n"
            "一覧JSONは要素数、個別JSONはファイル数を表示します。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        controls = QHBoxLayout()

        self.include_dataset_checkbox = QCheckBox("個別JSONにデータセット詳細(datasets/*.json)を含める")
        self.include_dataset_checkbox.setChecked(bool(self._state.get("include_dataset_details")))
        self.include_dataset_checkbox.stateChanged.connect(lambda _v: self._refresh_table())
        controls.addWidget(self.include_dataset_checkbox)

        controls.addWidget(QLabel("古い判定:"))
        self.outdated_policy_combo = QComboBox()
        self.outdated_policy_combo.addItem("JSON内日時→取得記録→mtime (B→C→A)", userData="bca")
        self.outdated_policy_combo.addItem("取得記録→mtime (C→A)", userData="ca")
        self.outdated_policy_combo.addItem("mtimeのみ (A)", userData="a")
        self._select_combo_by_user_data(self.outdated_policy_combo, self._state.get("outdated_policy", "bca"))
        controls.addWidget(self.outdated_policy_combo)

        controls.addWidget(QLabel("古い閾値(日):"))
        self.stale_days_spin = QSpinBox()
        self.stale_days_spin.setRange(0, 3650)
        self.stale_days_spin.setValue(int(self._state.get("stale_days", 30) or 0))
        self.stale_days_spin.setToolTip("『古い場合に取得』の判定に使用します（0=常に古い扱いになりやすいので注意）")
        controls.addWidget(self.stale_days_spin)

        controls.addStretch(1)
        root.addLayout(controls)

        bulk = QHBoxLayout()

        self.select_all_button = QPushButton("全て選択")
        self.select_all_button.clicked.connect(lambda: self._set_all_enabled(True))
        bulk.addWidget(self.select_all_button)

        self.clear_all_button = QPushButton("全て解除")
        self.clear_all_button.clicked.connect(lambda: self._set_all_enabled(False))
        bulk.addWidget(self.clear_all_button)

        bulk.addSpacing(12)
        bulk.addWidget(QLabel("取得条件一括:"))
        self.bulk_mode_combo = QComboBox()
        self.bulk_mode_combo.addItem("上書き取得", userData="overwrite")
        self.bulk_mode_combo.addItem("古い場合に取得", userData="older")
        self.bulk_mode_combo.addItem("ローカルに無い場合に取得", userData="missing")
        self.bulk_mode_combo.addItem("スキップ", userData="skip")
        self._select_combo_by_user_data(self.bulk_mode_combo, self._DEFAULT_MODE)
        bulk.addWidget(self.bulk_mode_combo)

        self.apply_bulk_mode_button = QPushButton("適用")
        self.apply_bulk_mode_button.clicked.connect(lambda: self._set_all_modes(str(self.bulk_mode_combo.currentData())))
        bulk.addWidget(self.apply_bulk_mode_button)

        bulk.addStretch(1)
        root.addLayout(bulk)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            [
                "取得",
                "対象",
                "種別",
                "一覧要素数",
                "個別ファイル数",
                "ローカル",
                "タイムスタンプ",
                "取得条件",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    @staticmethod
    def _select_combo_by_user_data(combo: QComboBox, user_data: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == user_data:
                combo.setCurrentIndex(i)
                return

    def _apply_theme(self, _mode: str) -> None:
        # テーブルはQtの標準に任せつつ、最低限の可読性だけ担保
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
            }}
            QHeaderView::section {{
                background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                padding: 6px;
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
            }}
            QTableWidget {{
                gridline-color: {get_color(ThemeKey.BORDER_DEFAULT)};
                alternate-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE)};
            }}
            """
        )

    def _set_all_enabled(self, enabled: bool) -> None:
        for binding in self._row_bindings:
            binding.checkbox.setChecked(enabled)

    def _set_all_modes(self, mode: str) -> None:
        for binding in self._row_bindings:
            self._select_combo_by_user_data(binding.mode_combo, mode)

    @staticmethod
    def _format_timestamp(dt: Optional[datetime]) -> str:
        if not dt:
            return ""
        try:
            jst = timezone(timedelta(hours=9))
            return dt.astimezone(jst).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""

    def _refresh_table(self) -> None:
        include_dataset_details = bool(self.include_dataset_checkbox.isChecked())
        self._state["include_dataset_details"] = include_dataset_details

        targets = build_common_info2_target_specs(include_dataset_details=include_dataset_details)

        self.table.setRowCount(len(targets))
        self._row_bindings = []

        targets_state: Dict[str, Any] = self._state.get("targets", {})

        for row, spec in enumerate(targets):
            # 取得チェック
            enabled_default = True
            row_state = targets_state.get(spec.target_id, {}) if isinstance(targets_state, dict) else {}
            enabled = bool(row_state.get("enabled", enabled_default))

            checkbox = QCheckBox()
            checkbox.setChecked(enabled)
            checkbox_widget = QWidget()
            hl = QHBoxLayout(checkbox_widget)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setAlignment(Qt.AlignCenter)
            hl.addWidget(checkbox)
            self.table.setCellWidget(row, 0, checkbox_widget)

            self.table.setItem(row, 1, QTableWidgetItem(spec.label))
            self.table.setItem(row, 2, QTableWidgetItem(spec.kind_label))

            local_status = compute_local_status_for_target(spec)

            list_count_item = QTableWidgetItem("" if local_status.list_count is None else str(local_status.list_count))
            list_count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, list_count_item)

            file_count_item = QTableWidgetItem("" if local_status.file_count is None else str(local_status.file_count))
            file_count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, file_count_item)

            self.table.setItem(row, 5, QTableWidgetItem(local_status.status_label))

            latest_ts = compute_local_timestamp_for_target(spec)
            ts_item = QTableWidgetItem(self._format_timestamp(latest_ts))
            ts_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 6, ts_item)

            mode_combo = QComboBox()
            mode_combo.addItem("上書き取得", userData="overwrite")
            mode_combo.addItem("古い場合に取得", userData="older")
            mode_combo.addItem("ローカルに無い場合に取得", userData="missing")
            mode_combo.addItem("スキップ", userData="skip")

            self._select_combo_by_user_data(mode_combo, str(row_state.get("mode", self._DEFAULT_MODE)))
            self.table.setCellWidget(row, 7, mode_combo)

            self._row_bindings.append(_RowBinding(spec.target_id, checkbox, mode_combo))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def get_state(self) -> Dict[str, Any]:
        # 最新のUI状態をstateへ反映
        targets: Dict[str, Any] = {}
        for binding in self._row_bindings:
            targets[binding.target_id] = {
                "enabled": bool(binding.checkbox.isChecked()),
                "mode": str(binding.mode_combo.currentData()),
            }

        self._state["targets"] = targets
        self._state["include_dataset_details"] = bool(self.include_dataset_checkbox.isChecked())
        self._state["outdated_policy"] = str(self.outdated_policy_combo.currentData())
        self._state["stale_days"] = int(self.stale_days_spin.value())
        return dict(self._state)
