"""データ取得2: 一括取得（RDE）タブ"""

from __future__ import annotations

import csv
import glob
import json
import os
import shutil
import zipfile
from typing import Any

from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCompleter,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QCheckBox,
    QDialog,
    QProgressBar,
    QMenu,
    QApplication,
)
from qt_compat.core import Qt, QTimer

from config.common import get_dynamic_file_path
from classes.theme import ThemeKey, get_qcolor
from classes.theme.theme_manager import get_color
from classes.data_fetch2.conf.file_filter_config import get_default_filter
from classes.utils.button_styles import get_button_style
from classes.utils.facility_link_helper import (
    load_equipment_name_map_from_merged_data2,
    load_instrument_local_id_map_from_instruments_json,
)
from classes.core.rde_search_index import ensure_rde_search_index, search_dataset_ids


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _contains(value: str, needle: str) -> bool:
    if not needle:
        return True
    return needle.casefold() in (value or "").casefold()


def _collect_tags(dataset_obj: dict) -> str:
    attrs = dataset_obj.get("attributes", {}) if isinstance(dataset_obj, dict) else {}
    tags = attrs.get("tags") or attrs.get("tag") or []
    if isinstance(tags, str):
        return tags
    if not isinstance(tags, list):
        return ""
    out: list[str] = []
    for t in tags:
        if isinstance(t, dict):
            out.append(str(t.get("name") or t.get("label") or "").strip())
        else:
            out.append(str(t).strip())
    return ", ".join([x for x in out if x])


def _collect_related_dataset_ids(dataset_obj: dict) -> str:
    relationships = dataset_obj.get("relationships", {}) if isinstance(dataset_obj, dict) else {}
    rel = relationships.get("relatedDatasets", {}) if isinstance(relationships, dict) else {}
    data = rel.get("data", []) if isinstance(rel, dict) else []
    if isinstance(data, dict):
        data = [data]
    out: list[str] = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict):
            rid = str(item.get("id") or "").strip()
            if rid:
                out.append(rid)
    return ", ".join(out)


def _find_first(attrs: dict, keys: list[str]) -> str:
    for key in keys:
        value = attrs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _join_maybe_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join([str(v).strip() for v in value if str(v).strip()])
    if isinstance(value, str):
        return value.strip()
    return ""


def _build_tile_records(
    dataset_obj: dict,
    entries: list[dict],
    grant_to_subgroup_map: dict[str, dict[str, str]] | None = None,
    sample_info_map: dict[str, dict[str, str]] | None = None,
    instrument_info_map: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    attrs = dataset_obj.get("attributes", {}) if isinstance(dataset_obj, dict) else {}
    rels = dataset_obj.get("relationships", {}) if isinstance(dataset_obj, dict) else {}
    group_rel = rels.get("group", {}).get("data", {}) if isinstance(rels, dict) else {}
    template_rel = rels.get("template", {}).get("data", {}) if isinstance(rels, dict) else {}

    dataset_id = str(dataset_obj.get("id") or "")
    dataset_name = str(attrs.get("name") or "")
    grant_number = str(attrs.get("grantNumber") or "")
    subgroup_id = str(group_rel.get("id") or attrs.get("groupId") or "")
    subgroup_display = ""
    if not subgroup_id:
        grant_map = grant_to_subgroup_map if isinstance(grant_to_subgroup_map, dict) else {}
        sg_info = grant_map.get(grant_number, {})
        subgroup_id = str(sg_info.get("id") or "").strip()
        subgroup_display = _join_non_empty([
            str(sg_info.get("name") or "").strip(),
            str(sg_info.get("description") or "").strip(),
        ])
    template_id = str(template_rel.get("id") or attrs.get("templateId") or "")
    tags = _collect_tags(dataset_obj)
    related_ids = _collect_related_dataset_ids(dataset_obj)

    records: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        eattrs = entry.get("attributes", {}) if isinstance(entry.get("attributes"), dict) else {}
        erels = entry.get("relationships", {}) if isinstance(entry.get("relationships"), dict) else {}

        sample_rel = (erels.get("sample") or {}).get("data") if isinstance(erels, dict) else None
        sample_id = str(sample_rel.get("id") or "").strip() if isinstance(sample_rel, dict) else ""
        sample_info = (sample_info_map or {}).get(sample_id, {}) if sample_id else {}

        instrument_rel = (erels.get("instrument") or {}).get("data") if isinstance(erels, dict) else None
        instrument_id = str(instrument_rel.get("id") or "").strip() if isinstance(instrument_rel, dict) else ""
        instrument_info = (instrument_info_map or {}).get(instrument_id, {}) if instrument_id else {}

        sample_name = _join_maybe_list(
            eattrs.get("sampleNames")
            or eattrs.get("sample_names")
            or eattrs.get("sampleName")
            or eattrs.get("displayName")
        )
        if not sample_name:
            sample_name = str(sample_info.get("name") or "").strip()

        sample_uuid = _find_first(eattrs, ["sampleUuid", "sampleUUID", "uuid", "sample_id", "sampleId"])
        if not sample_uuid and sample_id:
            sample_uuid = sample_id

        equipment_name = _find_first(
            eattrs,
            ["instrumentName", "equipmentName", "instrument", "apparatusName", "deviceName"],
        )
        if not equipment_name:
            equipment_name = str(instrument_info.get("name") or "").strip()

        equipment_local_id = _find_first(
            eattrs,
            ["instrumentLocalId", "equipmentLocalId", "localId", "deviceLocalId"],
        )
        if not equipment_local_id:
            equipment_local_id = str(instrument_info.get("local_id") or "").strip()

        records.append(
            {
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "grant_number": grant_number,
                "subgroup": subgroup_id,
                "subgroup_display": subgroup_display,
                "template": template_id,
                "tags": tags,
                "related_datasets": related_ids,
                "tile_id": str(entry.get("id") or ""),
                "tile_name": str(eattrs.get("name") or ""),
                "tile_number": str(eattrs.get("dataNumber") or ""),
                "sample_name": sample_name,
                "sample_uuid": sample_uuid,
                "equipment_name": equipment_name,
                "equipment_local_id": equipment_local_id,
                "entry_obj": entry,
                "dataset_obj": dataset_obj,
            }
        )
    return records


def _load_json_list_or_data(path: str) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def _load_json_payload(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _safe_attr(item: dict, key: str, default: str = "") -> str:
    attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    return str(attrs.get(key) or default).strip()


def _join_non_empty(parts: list[str], sep: str = " | ") -> str:
    return sep.join([p for p in [str(x).strip() for x in parts] if p])


def _safe_path_component(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "_"
    for ch in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        text = text.replace(ch, "_")
    text = text.strip(" .")
    return text or "_"


class BulkSaveOptionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("一括取得の追加保存オプション")
        self.resize(720, 200)

        root = QVBoxLayout(self)

        self.flat_check = QCheckBox("階層フォルダに保存")
        self.zip_check = QCheckBox("ZIPとして保存")
        root.addWidget(self.flat_check)

        self.flat_path_edit = QLineEdit(self)
        self.flat_path_edit.setPlaceholderText("保存先フォルダ（サブグループ/課題番号/データセット/タイル）")
        flat_row = QHBoxLayout()
        flat_row.addWidget(self.flat_path_edit)
        self.flat_btn = QPushButton("参照")
        self.flat_btn.clicked.connect(self._pick_flat_dir)
        flat_row.addWidget(self.flat_btn)
        root.addLayout(flat_row)

        root.addWidget(self.zip_check)
        self.zip_path_edit = QLineEdit(self)
        self.zip_path_edit.setPlaceholderText("ZIP出力パス (.zip)")
        zip_row = QHBoxLayout()
        zip_row.addWidget(self.zip_path_edit)
        self.zip_btn = QPushButton("参照")
        self.zip_btn.clicked.connect(self._pick_zip_path)
        zip_row.addWidget(self.zip_btn)
        root.addLayout(zip_row)

        btn_row = QHBoxLayout()
        self.ok_btn = QPushButton("実行")
        cancel_btn = QPushButton("キャンセル")
        self.ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        self.flat_check.toggled.connect(self.flat_path_edit.setEnabled)
        self.flat_check.toggled.connect(self.flat_btn.setEnabled)
        self.zip_check.toggled.connect(self.zip_path_edit.setEnabled)
        self.zip_check.toggled.connect(self.zip_btn.setEnabled)

        self.flat_check.toggled.connect(lambda *_: self._update_execute_enabled())
        self.zip_check.toggled.connect(lambda *_: self._update_execute_enabled())
        self.flat_path_edit.textChanged.connect(lambda *_: self._update_execute_enabled())
        self.zip_path_edit.textChanged.connect(lambda *_: self._update_execute_enabled())

        self.flat_path_edit.setEnabled(False)
        self.zip_path_edit.setEnabled(False)
        self.flat_btn.setEnabled(False)
        self.zip_btn.setEnabled(False)
        self._update_execute_enabled()

    def _update_execute_enabled(self):
        flat_enabled = self.flat_check.isChecked()
        zip_enabled = self.zip_check.isChecked()
        flat_ok = (not flat_enabled) or bool(self.flat_path_edit.text().strip())
        zip_ok = (not zip_enabled) or bool(self.zip_path_edit.text().strip())
        at_least_one = flat_enabled or zip_enabled
        self.ok_btn.setEnabled(at_least_one and flat_ok and zip_ok)

    def _pick_flat_dir(self):
        path = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if path:
            self.flat_path_edit.setText(path)

    def _pick_zip_path(self):
        path, _ = QFileDialog.getSaveFileName(self, "ZIP保存先を選択", "", "ZIP (*.zip)")
        if path:
            if not path.lower().endswith(".zip"):
                path += ".zip"
            self.zip_path_edit.setText(path)

    def get_values(self) -> dict:
        return {
            "flat_enabled": self.flat_check.isChecked(),
            "flat_dir": self.flat_path_edit.text().strip(),
            "zip_enabled": self.zip_check.isChecked(),
            "zip_path": self.zip_path_edit.text().strip(),
        }


class DataFetch2BulkRdeTab(QWidget):
    COLUMNS = [
        "取得",
        "サブグループ",
        "課題番号",
        "データセット",
        "タイルNo",
        "タイル名",
        "タイルID",
        "試料(表示名)",
        "試料(UUID)",
        "装置名",
        "装置(ローカルID)",
        "タグ",
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_filter_config = get_default_filter()
        self._records: list[dict] = []
        self._all_records: list[dict] = []
        self._dataset_items_cache: list[dict] = []
        self._source_dataset_count = 0
        self._last_source_signature: tuple[str, str, str, str] | None = None
        self._record_exact_indexes: dict[str, dict[str, set[int]]] = {}
        self._subgroup_info_cache: dict[str, dict[str, str]] | None = None
        self._sample_info_cache: dict[str, dict[str, str]] | None = None
        self._instrument_info_cache: dict[str, dict[str, str]] | None = None
        self._last_subgroup_selected_uuid = ""
        self._records_dirty = True
        self._compact_rows_mode = False
        self._suppress_filter_dirty = False
        self._auto_rebuild_timer = QTimer(self)
        self._auto_rebuild_timer.setSingleShot(True)
        self._auto_rebuild_timer.setInterval(250)
        self._auto_rebuild_timer.timeout.connect(self._auto_rebuild_if_needed)
        self._build_ui()

    def set_filter_config(self, filter_config: dict):
        self.current_filter_config = dict(filter_config or get_default_filter())

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("一括取得（RDE）")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        root.addWidget(title)

        desc = QLabel(
            "検索条件でタイルを絞り込み、対象タイルを選択して一括取得します。"
            "\n実行時にファイルフィルタ適用有無を選択でき、通常保存に加えて「同一フォルダ保存」「ZIP保存」を選べます。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        root.addWidget(desc)

        filters_layout = QVBoxLayout()
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(6)

        self.f_subgroup = self._create_filter_combo(
            "候補から選択（部分一致可）", "bulkRdeSubgroupCombo"
        )
        self.f_grant = self._create_filter_combo(
            "候補から選択（部分一致可）", "bulkRdeGrantCombo"
        )
        self.f_sample_name = QLineEdit(self)
        self.f_sample_uuid = QLineEdit(self)
        self.f_template = self._create_filter_combo(
            "候補から選択（部分一致可）", "bulkRdeTemplateCombo"
        )
        self.f_equip_name = self._create_filter_combo(
            "候補から選択（部分一致可）", "bulkRdeEquipmentNameCombo"
        )
        self.f_equip_local = self._create_filter_combo(
            "候補から選択（部分一致可）", "bulkRdeEquipmentLocalCombo"
        )
        self.f_tags = QLineEdit(self)
        self.f_related = self._create_filter_combo(
            "候補から選択（部分一致可）", "bulkRdeRelatedDatasetCombo"
        )

        fields = [
            ("サブグループ", self.f_subgroup),
            ("課題番号", self.f_grant),
            ("試料（表示名）", self.f_sample_name),
            ("試料（UUID）", self.f_sample_uuid),
            ("データセットテンプレート", self.f_template),
            ("装置名", self.f_equip_name),
            ("装置（ローカルID）", self.f_equip_local),
            ("タグ", self.f_tags),
            ("関連データセット", self.f_related),
        ]
        for label_text, editor in fields:
            row = QHBoxLayout()
            row_label = QLabel(label_text)
            row_label.setMinimumWidth(140)
            row.addWidget(row_label)
            if isinstance(editor, QLineEdit):
                editor.setPlaceholderText("部分一致")
            row.addWidget(editor, 1)
            filters_layout.addLayout(row)

        self.auto_rebuild_check = QCheckBox("絞込み変更で対象タイル一覧を自動作成")
        self.auto_rebuild_check.setChecked(False)
        filters_layout.addWidget(self.auto_rebuild_check)
        root.addLayout(filters_layout)

        op_row = QHBoxLayout()
        self.search_btn = QPushButton("対象タイル一覧を作成")
        export_menu = QMenu(self)
        export_csv = export_menu.addAction("CSV出力")
        export_csv.triggered.connect(lambda: self._export("csv"))
        self.export_btn = QPushButton("エクスポート")
        self.export_btn.setMenu(export_menu)

        self.compact_rows_btn = QPushButton("1行表示")
        self.sel_all_btn = QPushButton("全選択")
        self.sel_clear_btn = QPushButton("全解除")
        self.sel_invert_btn = QPushButton("選択反転")
        self.sel_exclude_btn = QPushButton("選択除外")
        self.exec_btn = QPushButton("選択タイルを一括取得")

        for b in [
            self.search_btn,
            self.export_btn,
            self.compact_rows_btn,
            self.sel_all_btn,
            self.sel_clear_btn,
            self.sel_invert_btn,
            self.sel_exclude_btn,
            self.exec_btn,
        ]:
            op_row.addWidget(b)
        op_row.addStretch()
        root.addLayout(op_row)

        self._apply_button_group_styles()

        self.status = QLabel("待機中")
        root.addWidget(self.status)

        self.rebuild_progress = QProgressBar(self)
        self.rebuild_progress.setRange(0, 100)
        self.rebuild_progress.setValue(0)
        self.rebuild_progress.setVisible(False)
        root.addWidget(self.rebuild_progress)

        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(11, QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(int(self.table.fontMetrics().height() * 1.8))
        root.addWidget(self.table, 1)

        self.search_btn.clicked.connect(lambda: self.rebuild_tiles(force_source_refresh=True))
        self.compact_rows_btn.clicked.connect(self._toggle_row_height_mode)
        self.sel_all_btn.clicked.connect(lambda: self._set_checked_all(True, ensure_current=True))
        self.sel_clear_btn.clicked.connect(lambda: self._set_checked_all(False, ensure_current=True))
        self.sel_invert_btn.clicked.connect(lambda: self._invert_checks(ensure_current=True))
        self.sel_exclude_btn.clicked.connect(lambda: self._exclude_checked(ensure_current=True))
        self.exec_btn.clicked.connect(self.execute_bulk_download)
        self.table.itemChanged.connect(self._on_item_changed)

        self._connect_filter_change_signals()

        self._update_filter_options([])

    def _apply_button_group_styles(self):
        self.search_btn.setStyleSheet(get_button_style("primary"))
        self.export_btn.setStyleSheet(get_button_style("success"))
        self.compact_rows_btn.setStyleSheet(get_button_style("info"))

        self.sel_all_btn.setStyleSheet(get_button_style("success"))
        self.sel_clear_btn.setStyleSheet(get_button_style("neutral"))
        self.sel_invert_btn.setStyleSheet(get_button_style("warning"))
        self.sel_exclude_btn.setStyleSheet(get_button_style("danger"))

        self.exec_btn.setStyleSheet(get_button_style("api"))

    def _connect_filter_change_signals(self):
        editors: list[Any] = [
            self.f_subgroup,
            self.f_grant,
            self.f_sample_name,
            self.f_sample_uuid,
            self.f_template,
            self.f_equip_name,
            self.f_equip_local,
            self.f_tags,
            self.f_related,
        ]
        for editor in editors:
            if isinstance(editor, QComboBox):
                if editor is self.f_subgroup:
                    editor.currentIndexChanged.connect(lambda *_: self._on_subgroup_combo_index_changed())
                else:
                    editor.currentTextChanged.connect(lambda *_: self._mark_filters_dirty())
                    line_edit = editor.lineEdit()
                    if line_edit is not None:
                        line_edit.textEdited.connect(lambda *_: self._mark_filters_dirty())
            elif isinstance(editor, QLineEdit):
                editor.textChanged.connect(lambda *_: self._mark_filters_dirty())

    def _on_subgroup_combo_index_changed(self):
        selected_uuid = self._combo_selected_user_value(self.f_subgroup)
        if not selected_uuid:
            return
        if selected_uuid == self._last_subgroup_selected_uuid:
            return
        self._last_subgroup_selected_uuid = selected_uuid
        self._mark_filters_dirty()

    def _mark_filters_dirty(self):
        if self._suppress_filter_dirty:
            return
        self._records_dirty = True
        if not self.auto_rebuild_check.isChecked():
            return
        try:
            self._auto_rebuild_timer.start()
        except Exception:
            self._auto_rebuild_if_needed()

    def _has_effective_filter(self) -> bool:
        values = [
            self.f_subgroup.currentText().strip(),
            self.f_grant.currentText().strip(),
            self.f_sample_name.text().strip(),
            self.f_sample_uuid.text().strip(),
            self.f_template.currentText().strip(),
            self.f_equip_name.currentText().strip(),
            self.f_equip_local.currentText().strip(),
            self.f_tags.text().strip(),
            self.f_related.currentText().strip(),
        ]
        return any(values)

    def _auto_rebuild_if_needed(self):
        if not self.auto_rebuild_check.isChecked():
            return
        if not self._records_dirty:
            return
        if self._all_records and not self._dataset_prefilter_changed():
            self._apply_filters_to_cached_records(auto_trigger=True)
            return
        self.rebuild_tiles(auto_trigger=True, force_source_refresh=True)

    def _set_rebuild_progress(self, current: int, total: int, text: str):
        total_safe = max(1, int(total))
        current_safe = max(0, min(int(current), total_safe))
        ratio = int(current_safe * 100 / total_safe)
        self.rebuild_progress.setVisible(True)
        self.rebuild_progress.setValue(ratio)
        self.status.setText(text)
        try:
            QApplication.processEvents()
        except Exception:
            pass

    def _ensure_records_ready(self) -> bool:
        if self._records and not self._records_dirty:
            return True
        if self._all_records and not self._dataset_prefilter_changed():
            self._apply_filters_to_cached_records(auto_trigger=True)
            return True
        self.rebuild_tiles(auto_trigger=True, force_source_refresh=True)
        return True

    def _dataset_prefilter_signature(self) -> tuple[str, str, str, str]:
        return (
            self._combo_match_value(self.f_subgroup),
            self._combo_match_value(self.f_grant),
            self._combo_match_value(self.f_template),
            self._combo_match_value(self.f_related),
        )

    def _dataset_prefilter_changed(self) -> bool:
        current = self._dataset_prefilter_signature()
        return self._last_source_signature != current

    def _build_grant_to_subgroup_map(self) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        subgroup_info = self._load_subgroup_info_map()

        subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
        if not subgroup_path or not os.path.exists(subgroup_path):
            return result

        payload: Any = None
        try:
            with open(subgroup_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return result

        items: list[dict] = []
        if isinstance(payload, dict):
            included = payload.get("included")
            if isinstance(included, list):
                items.extend([x for x in included if isinstance(x, dict)])
            data_items = payload.get("data")
            if isinstance(data_items, list):
                items.extend([x for x in data_items if isinstance(x, dict)])
            elif isinstance(data_items, dict):
                items.append(data_items)
        elif isinstance(payload, list):
            items.extend([x for x in payload if isinstance(x, dict)])

        for item in items:
            if item.get("type") != "group":
                continue
            gid = str(item.get("id") or "").strip()
            if not gid:
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            if attrs.get("groupType") != "TEAM":
                continue

            info = subgroup_info.get(gid, {})
            subjects: list[Any] = []
            raw_subjects = attrs.get("subjects")
            if isinstance(raw_subjects, list):
                subjects = raw_subjects
            for subject in subjects:
                if not isinstance(subject, dict):
                    continue
                grant = str(subject.get("grantNumber") or "").strip()
                if not grant:
                    continue
                result[grant] = {
                    "id": gid,
                    "name": str(info.get("name") or attrs.get("name") or "").strip(),
                    "description": str(info.get("description") or attrs.get("description") or "").strip(),
                }

        return result

    def _matches_dataset_prefilter(
        self,
        dataset_obj: dict,
        grant_to_subgroup_map: dict[str, dict[str, str]] | None = None,
    ) -> bool:
        attrs = dataset_obj.get("attributes") if isinstance(dataset_obj.get("attributes"), dict) else {}
        rels = dataset_obj.get("relationships") if isinstance(dataset_obj.get("relationships"), dict) else {}

        subgroup_value = self._combo_match_value(self.f_subgroup)
        grant_value = self._combo_match_value(self.f_grant)
        template_value = self._combo_match_value(self.f_template)
        related_value = self._combo_match_value(self.f_related)

        group_data = (rels.get("group") or {}).get("data") if isinstance(rels, dict) else None
        subgroup_id = str(group_data.get("id") or attrs.get("groupId") or "").strip() if isinstance(group_data, dict) else str(attrs.get("groupId") or "").strip()
        subgroup_info = self._load_subgroup_info_map().get(subgroup_id, {})
        subgroup_display = _join_non_empty([
            str(subgroup_info.get("name") or "").strip(),
            str(subgroup_info.get("description") or "").strip(),
        ])
        template_data = (rels.get("template") or {}).get("data") if isinstance(rels, dict) else None
        template_id = str(template_data.get("id") or attrs.get("templateId") or "").strip() if isinstance(template_data, dict) else str(attrs.get("templateId") or "").strip()
        grant = str(attrs.get("grantNumber") or "").strip()

        if not subgroup_id and grant:
            grant_map = grant_to_subgroup_map if isinstance(grant_to_subgroup_map, dict) else {}
            sg_info = grant_map.get(grant, {})
            subgroup_id = str(sg_info.get("id") or "").strip()
            subgroup_display = _join_non_empty([
                str(sg_info.get("name") or "").strip(),
                str(sg_info.get("description") or "").strip(),
            ])

        related_ids: list[str] = []
        related_data = (rels.get("relatedDatasets") or {}).get("data") if isinstance(rels, dict) else []
        if isinstance(related_data, dict):
            related_data = [related_data]
        for item in related_data if isinstance(related_data, list) else []:
            if isinstance(item, dict):
                rid = str(item.get("id") or "").strip()
                if rid:
                    related_ids.append(rid)

        return (
            _contains(_join_non_empty([subgroup_id, subgroup_display]), subgroup_value)
            and _contains(grant, grant_value)
            and _contains(template_id, template_value)
            and _contains(", ".join(related_ids), related_value)
        )

    def _dataset_path(self) -> str:
        return get_dynamic_file_path("output/rde/data/dataset.json")

    def _entry_path(self, dataset_id: str) -> str:
        return get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")

    def _load_dataset_items(self) -> list[dict]:
        path = self._dataset_path()
        return _load_json_list_or_data(path)

    def _load_sample_info_map(self) -> dict[str, dict[str, str]]:
        if self._sample_info_cache is not None:
            return self._sample_info_cache

        result: dict[str, dict[str, str]] = {}
        samples_dir = get_dynamic_file_path("output/rde/data/samples")
        if not samples_dir or not os.path.isdir(samples_dir):
            self._sample_info_cache = result
            return result

        for path in glob.glob(os.path.join(samples_dir, "*.json")):
            payload = _load_json_payload(path)
            items: list[dict] = []
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, list):
                    items.extend([x for x in data if isinstance(x, dict)])
                elif isinstance(data, dict):
                    items.append(data)
            elif isinstance(payload, list):
                items.extend([x for x in payload if isinstance(x, dict)])

            for item in items:
                sample_id = str(item.get("id") or "").strip()
                if not sample_id:
                    continue
                attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
                names = attrs.get("names")
                display = ""
                if isinstance(names, list):
                    display = ", ".join([str(x).strip() for x in names if str(x).strip()])
                elif isinstance(names, str):
                    display = names.strip()
                if not display:
                    display = str(attrs.get("name") or attrs.get("description") or "").strip()
                result[sample_id] = {
                    "name": display,
                }

        self._sample_info_cache = result
        return result

    def _load_instrument_info_map(self) -> dict[str, dict[str, str]]:
        if self._instrument_info_cache is not None:
            return self._instrument_info_cache

        result: dict[str, dict[str, str]] = {}
        for item in _load_json_list_or_data(get_dynamic_file_path("output/rde/data/instruments.json")):
            instrument_id = str(item.get("id") or "").strip()
            if not instrument_id:
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            name = str(attrs.get("nameJa") or attrs.get("nameEn") or "").strip()
            local_id = ""
            raw_programs = attrs.get("programs")
            programs: list[Any] = raw_programs if isinstance(raw_programs, list) else []
            for program in programs:
                if not isinstance(program, dict):
                    continue
                local_id = str(program.get("localId") or "").strip()
                if local_id:
                    break
            result[instrument_id] = {
                "name": name,
                "local_id": local_id,
            }

        self._instrument_info_cache = result
        return result

    def _read_entry_items(self, dataset_id: str) -> list[dict]:
        path = self._entry_path(dataset_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            items = payload.get("data") if isinstance(payload, dict) else []
            return list(items or [])
        except Exception:
            return []

    def _matches_record(self, rec: dict) -> bool:
        subgroup_value = self._combo_match_value(self.f_subgroup)
        grant_value = self._combo_match_value(self.f_grant)
        template_value = self._combo_match_value(self.f_template)
        equip_name_value = self._combo_match_value(self.f_equip_name)
        equip_local_value = self._combo_match_value(self.f_equip_local)
        related_value = self._combo_match_value(self.f_related)
        subgroup_record_text = _join_non_empty([
            _to_text(rec.get("subgroup")),
            _to_text(rec.get("subgroup_display")),
            self._resolve_subgroup_display(rec.get("subgroup", "")),
        ])
        return (
            _contains(subgroup_record_text, subgroup_value)
            and _contains(_to_text(rec.get("grant_number")), grant_value)
            and _contains(_to_text(rec.get("sample_name")), self.f_sample_name.text().strip())
            and _contains(_to_text(rec.get("sample_uuid")), self.f_sample_uuid.text().strip())
            and _contains(_to_text(rec.get("template")), template_value)
            and _contains(_to_text(rec.get("equipment_name")), equip_name_value)
            and _contains(
                _join_non_empty([
                    _to_text(rec.get("equipment_local_id")),
                    _to_text(rec.get("equipment_name")),
                ]),
                equip_local_value,
            )
            and _contains(_to_text(rec.get("tags")), self.f_tags.text().strip())
            and _contains(_to_text(rec.get("related_datasets")), related_value)
        )

    def _combo_match_value(self, combo: QComboBox) -> str:
        text = combo.currentText().strip()
        if not text:
            return ""
        idx = combo.currentIndex()
        if idx >= 0 and combo.itemText(idx).strip() == text:
            user_value = combo.itemData(idx, Qt.UserRole)
            if isinstance(user_value, str) and user_value.strip():
                return user_value.strip()
        return text

    def _combo_selected_user_value(self, combo: QComboBox) -> str:
        text = combo.currentText().strip()
        if not text:
            return ""
        idx = combo.currentIndex()
        if idx < 0:
            return ""
        if combo.itemText(idx).strip() != text:
            return ""
        user_value = combo.itemData(idx, Qt.UserRole)
        if isinstance(user_value, str):
            return user_value.strip()
        return ""

    def _build_record_exact_indexes(self, records: list[dict]):
        indexes: dict[str, dict[str, set[int]]] = {
            "subgroup": {},
            "grant": {},
            "template": {},
            "equip_name": {},
            "equip_local": {},
            "related": {},
        }

        def add(field: str, value: str, row_idx: int):
            key = str(value or "").strip().casefold()
            if not key:
                return
            bucket = indexes[field].setdefault(key, set())
            bucket.add(row_idx)

        for i, rec in enumerate(records):
            add("subgroup", _to_text(rec.get("subgroup")), i)
            add("grant", _to_text(rec.get("grant_number")), i)
            add("template", _to_text(rec.get("template")), i)
            add("equip_name", _to_text(rec.get("equipment_name")), i)
            add("equip_local", _to_text(rec.get("equipment_local_id")), i)
            related_text = _to_text(rec.get("related_datasets"))
            for rel in [x.strip() for x in related_text.split(",") if x.strip()]:
                add("related", rel, i)

        self._record_exact_indexes = indexes

    def _candidate_records_from_exact_indexes(self) -> list[dict]:
        if not self._all_records or not self._record_exact_indexes:
            return self._all_records

        criteria: list[tuple[str, str]] = [
            ("subgroup", self._combo_selected_user_value(self.f_subgroup)),
            ("grant", self._combo_selected_user_value(self.f_grant)),
            ("template", self._combo_selected_user_value(self.f_template)),
            ("equip_name", self._combo_selected_user_value(self.f_equip_name)),
            ("equip_local", self._combo_selected_user_value(self.f_equip_local)),
            ("related", self._combo_selected_user_value(self.f_related)),
        ]

        candidate_rows: set[int] | None = None
        for field, value in criteria:
            if not value:
                continue
            key = value.casefold()
            current = self._record_exact_indexes.get(field, {}).get(key, set())
            if candidate_rows is None:
                candidate_rows = set(current)
            else:
                candidate_rows &= current
            if not candidate_rows:
                return []

        if candidate_rows is None:
            return self._all_records
        return [self._all_records[idx] for idx in sorted(candidate_rows)]

    def _build_all_records_from_sources(self) -> list[dict]:
        self._set_rebuild_progress(0, 100, "対象タイル一覧を作成中...")
        datasets = self._load_dataset_items()
        self._dataset_items_cache = list(datasets)
        self._source_dataset_count = len(datasets)
        grant_to_subgroup_map = self._build_grant_to_subgroup_map()
        sample_info_map = self._load_sample_info_map()
        instrument_info_map = self._load_instrument_info_map()
        records: list[dict] = []

        dataset_by_id: dict[str, dict] = {
            str(ds.get("id") or "").strip(): ds
            for ds in datasets
            if isinstance(ds, dict) and str(ds.get("id") or "").strip()
        }

        index_criteria = {
            "subgroup_id": self._combo_match_value(self.f_subgroup),
            "subgroup_name": self.f_subgroup.currentText().strip(),
            "grant_number": self._combo_match_value(self.f_grant),
            "template_id": self._combo_match_value(self.f_template),
            "related_dataset_id": self._combo_match_value(self.f_related),
            "equipment_name": self._combo_match_value(self.f_equip_name),
            "equipment_local_id": self._combo_match_value(self.f_equip_local),
        }

        candidate_dataset_ids: set[str] | None = None
        try:
            index_payload = ensure_rde_search_index(force_rebuild=False)
            candidate_dataset_ids = search_dataset_ids(index_payload, index_criteria)
        except Exception:
            candidate_dataset_ids = None

        if candidate_dataset_ids is not None:
            overlap = {dataset_id for dataset_id in candidate_dataset_ids if dataset_id in dataset_by_id}
            if overlap:
                candidate_dataset_ids = overlap
            else:
                equip_name_filter = self._combo_match_value(self.f_equip_name)
                equip_local_filter = self._combo_match_value(self.f_equip_local)
                has_equip_filter = bool(equip_name_filter or equip_local_filter)
                if has_equip_filter:
                    dataset_only_criteria = {
                        "subgroup_id": self._combo_match_value(self.f_subgroup),
                        "subgroup_name": self.f_subgroup.currentText().strip(),
                        "grant_number": self._combo_match_value(self.f_grant),
                        "template_id": self._combo_match_value(self.f_template),
                        "related_dataset_id": self._combo_match_value(self.f_related),
                    }
                    try:
                        fallback_ids = search_dataset_ids(index_payload, dataset_only_criteria)
                    except Exception:
                        fallback_ids = None
                    if fallback_ids is not None:
                        fallback_overlap = {dataset_id for dataset_id in fallback_ids if dataset_id in dataset_by_id}
                        candidate_dataset_ids = fallback_overlap if fallback_overlap else None
                    else:
                        candidate_dataset_ids = None
                else:
                    candidate_dataset_ids = None

        if candidate_dataset_ids is not None:
            prefiltered_datasets = [
                dataset_by_id[dataset_id]
                for dataset_id in sorted(candidate_dataset_ids)
                if dataset_id in dataset_by_id and self._matches_dataset_prefilter(dataset_by_id[dataset_id])
            ]
        else:
            prefiltered_datasets = [
                ds for ds in datasets
                if isinstance(ds, dict) and self._matches_dataset_prefilter(ds, grant_to_subgroup_map)
            ]
        self._source_dataset_count = len(prefiltered_datasets)
        total = len(prefiltered_datasets) if prefiltered_datasets else 1
        for idx, ds in enumerate(prefiltered_datasets, start=1):
            if not isinstance(ds, dict):
                self._set_rebuild_progress(idx, total, f"対象タイル一覧を作成中... {idx}/{total}")
                continue
            dsid = str(ds.get("id") or "")
            if not dsid:
                self._set_rebuild_progress(idx, total, f"対象タイル一覧を作成中... {idx}/{total}")
                continue
            entries = self._read_entry_items(dsid)
            if not entries:
                self._set_rebuild_progress(idx, total, f"対象タイル一覧を作成中... {idx}/{total}")
                continue
            records.extend(
                _build_tile_records(
                    ds,
                    entries,
                    grant_to_subgroup_map,
                    sample_info_map,
                    instrument_info_map,
                )
            )
            self._set_rebuild_progress(idx, total, f"対象タイル一覧を作成中... {idx}/{total}")

        return records

    def _apply_filters_to_cached_records(self, auto_trigger: bool = False):
        if not self._all_records:
            self._records = []
            self._populate_table(self._records)
            self._records_dirty = False
            self.status.setText("検索結果: 0 タイル")
            return

        candidates = self._candidate_records_from_exact_indexes()
        filtered_records = [rec for rec in candidates if self._matches_record(rec)]
        self._records = filtered_records
        self._populate_table(self._records)
        self._records_dirty = False

        matched_dataset_count = len({str(rec.get("dataset_id") or "") for rec in self._records if str(rec.get("dataset_id") or "").strip()})
        prefix = "自動更新" if auto_trigger else "検索結果"
        self.status.setText(
            f"{prefix}: {len(self._records)} タイル / 対象データセット {matched_dataset_count} / 全データセット {self._source_dataset_count}"
        )
        self.rebuild_progress.setVisible(False)

    def rebuild_tiles(self, auto_trigger: bool = False, force_source_refresh: bool = False):
        if not self._has_effective_filter():
            self._records = []
            self._populate_table(self._records)
            self._records_dirty = False
            self.rebuild_progress.setVisible(False)
            self.status.setText("有効な絞込みフィルタを設定してください。")
            return

        signature = self._dataset_prefilter_signature()
        need_source_refresh = force_source_refresh or not self._all_records or (self._last_source_signature != signature)

        if need_source_refresh:
            records = self._build_all_records_from_sources()
            self._suppress_filter_dirty = True
            try:
                self._update_filter_options(records)
            finally:
                self._suppress_filter_dirty = False
            self._all_records = records
            self._build_record_exact_indexes(self._all_records)
            self._last_source_signature = signature
        else:
            self.rebuild_progress.setVisible(False)

        self._apply_filters_to_cached_records(auto_trigger=auto_trigger)

    def _create_filter_combo(self, placeholder: str, object_name: str) -> QComboBox:
        combo = QComboBox(self)
        combo.setObjectName(object_name)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        combo.addItem("")
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)
        return combo

    def _collect_equipment_candidates(self) -> tuple[set[str], dict[str, str]]:
        names: set[str] = set()
        local_to_name: dict[str, str] = {}

        try:
            index_payload = ensure_rde_search_index(force_rebuild=False)
            reverse = index_payload.get("reverse") if isinstance(index_payload.get("reverse"), dict) else {}
            name_map = reverse.get("equipment_name") if isinstance(reverse, dict) else {}
            local_map = reverse.get("equipment_local_id") if isinstance(reverse, dict) else {}
            if isinstance(name_map, dict):
                names.update([str(k).strip() for k in name_map.keys() if str(k).strip()])
            if isinstance(local_map, dict):
                for local_id in local_map.keys():
                    key = str(local_id).strip()
                    if key:
                        local_to_name.setdefault(key, "")
        except Exception:
            pass

        try:
            name_map = load_equipment_name_map_from_merged_data2()
            for item in name_map.values() if isinstance(name_map, dict) else []:
                if not isinstance(item, dict):
                    continue
                for key in ("ja", "raw", "en"):
                    value = str(item.get(key) or "").strip()
                    if value:
                        names.add(value)
        except Exception:
            pass

        try:
            local_map = load_instrument_local_id_map_from_instruments_json()
            for value in local_map.values() if isinstance(local_map, dict) else []:
                local_id = str(value or "").strip()
                if local_id:
                    local_to_name.setdefault(local_id, "")
        except Exception:
            pass

        path = get_dynamic_file_path("output/rde/data/instruments.json")
        for item in _load_json_list_or_data(path):
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            name = str(attrs.get("nameJa") or attrs.get("nameEn") or "").strip()
            if name:
                names.add(name)
            raw_programs = attrs.get("programs")
            programs: list[Any] = raw_programs if isinstance(raw_programs, list) else []
            for program in programs:
                if not isinstance(program, dict):
                    continue
                local_id = str(program.get("localId") or "").strip()
                if not local_id:
                    continue
                if local_id not in local_to_name or not local_to_name[local_id]:
                    local_to_name[local_id] = name

        return names, local_to_name

    def _collect_subgroup_candidates(self, dataset_items: list[dict]) -> set[str]:
        subgroup_ids: set[str] = set()

        for item in dataset_items:
            if not isinstance(item, dict):
                continue
            rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            group_data = (rels.get("group") or {}).get("data") if isinstance(rels, dict) else None
            if isinstance(group_data, dict):
                gid = str(group_data.get("id") or "").strip()
                if gid:
                    subgroup_ids.add(gid)
            for key in ("groupId", "subgroupId", "subGroupId", "sub_group_id"):
                value = str(attrs.get(key) or "").strip() if isinstance(attrs, dict) else ""
                if value:
                    subgroup_ids.add(value)

        subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
        subgroup_items: list[dict] = []
        if subgroup_path and os.path.exists(subgroup_path):
            try:
                with open(subgroup_path, "r", encoding="utf-8") as f:
                    subgroup_payload = json.load(f)
                if isinstance(subgroup_payload, dict):
                    included = subgroup_payload.get("included")
                    if isinstance(included, list):
                        subgroup_items = [x for x in included if isinstance(x, dict)]
                    else:
                        data_items = subgroup_payload.get("data")
                        if isinstance(data_items, list):
                            subgroup_items = [x for x in data_items if isinstance(x, dict)]
                elif isinstance(subgroup_payload, list):
                    subgroup_items = [x for x in subgroup_payload if isinstance(x, dict)]
            except Exception:
                subgroup_items = []

        for item in subgroup_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "group":
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            if attrs.get("groupType") != "TEAM":
                continue
            gid = str(item.get("id") or "").strip()
            if gid:
                subgroup_ids.add(gid)

        return subgroup_ids

    def _load_subgroup_info_map(self) -> dict[str, dict[str, str]]:
        if self._subgroup_info_cache is not None:
            return self._subgroup_info_cache

        result: dict[str, dict[str, str]] = {}
        subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
        subgroup_items: list[dict] = []
        if subgroup_path and os.path.exists(subgroup_path):
            try:
                with open(subgroup_path, "r", encoding="utf-8") as f:
                    subgroup_payload = json.load(f)
                if isinstance(subgroup_payload, dict):
                    included = subgroup_payload.get("included")
                    if isinstance(included, list):
                        subgroup_items = [x for x in included if isinstance(x, dict)]
                    else:
                        data_items = subgroup_payload.get("data")
                        if isinstance(data_items, list):
                            subgroup_items = [x for x in data_items if isinstance(x, dict)]
                elif isinstance(subgroup_payload, list):
                    subgroup_items = [x for x in subgroup_payload if isinstance(x, dict)]
            except Exception:
                subgroup_items = []

        for item in subgroup_items:
            if item.get("type") != "group":
                continue
            gid = str(item.get("id") or "").strip()
            if not gid:
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            if attrs.get("groupType") != "TEAM":
                continue
            result[gid] = {
                "name": str(attrs.get("name") or "").strip(),
                "description": str(attrs.get("description") or "").strip(),
            }
        self._subgroup_info_cache = result
        return result

    def _load_instrument_name_map(self) -> dict[str, str]:
        path = get_dynamic_file_path("output/rde/data/instruments.json")
        result: dict[str, str] = {}
        for item in _load_json_list_or_data(path):
            iid = str(item.get("id") or "").strip()
            if not iid:
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            name = str(attrs.get("nameJa") or attrs.get("nameEn") or "").strip()
            local_id = ""
            programs: list[Any] = []
            raw_programs = attrs.get("programs")
            if isinstance(raw_programs, list):
                programs = raw_programs
            for program in programs:
                if not isinstance(program, dict):
                    continue
                local_id = str(program.get("localId") or "").strip()
                if local_id:
                    break
            if name and local_id:
                result[iid] = f"{name} [{local_id}]"
            elif name:
                result[iid] = name
            elif local_id:
                result[iid] = local_id
        return result

    def _collect_template_display_candidates(self, dataset_items: list[dict]) -> list[tuple[str, str]]:
        template_path = get_dynamic_file_path("output/rde/data/template.json")
        template_items = _load_json_list_or_data(template_path)
        template_map = {str(item.get("id") or "").strip(): item for item in template_items if isinstance(item, dict)}
        instrument_name_map = self._load_instrument_name_map()

        template_ids: set[str] = set()
        for item in dataset_items:
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
            template_rel = (rels.get("template") or {}).get("data") if isinstance(rels, dict) else None
            if isinstance(template_rel, dict):
                tid = str(template_rel.get("id") or "").strip()
                if tid:
                    template_ids.add(tid)
            attr_tid = str(attrs.get("templateId") or "").strip()
            if attr_tid:
                template_ids.add(attr_tid)
        template_ids.update([tid for tid in template_map.keys() if tid])

        out: list[tuple[str, str]] = []
        for tid in sorted(template_ids):
            template_obj = template_map.get(tid, {}) if isinstance(template_map, dict) else {}
            name = _safe_attr(template_obj, "nameJa", tid) if isinstance(template_obj, dict) else tid
            rels = template_obj.get("relationships") if isinstance(template_obj, dict) and isinstance(template_obj.get("relationships"), dict) else {}
            instruments_rel = (rels.get("instruments") or {}).get("data") if isinstance(rels, dict) else []
            if isinstance(instruments_rel, dict):
                instruments_rel = [instruments_rel]
            instrument_labels: list[str] = []
            for inst in instruments_rel if isinstance(instruments_rel, list) else []:
                if not isinstance(inst, dict):
                    continue
                inst_id = str(inst.get("id") or "").strip()
                if not inst_id:
                    continue
                label = instrument_name_map.get(inst_id)
                if label:
                    instrument_labels.append(label)
            display = name
            if instrument_labels:
                display = f"{name} | {', '.join(instrument_labels)}"
            out.append((display, tid))
        return out

    def _collect_related_dataset_display_candidates(self, dataset_items: list[dict]) -> list[tuple[str, str]]:
        subgroup_map = self._load_subgroup_info_map()
        instrument_name_map = self._load_instrument_name_map()
        template_candidates = self._collect_template_display_candidates(dataset_items)
        template_display_by_id = {match: label for label, match in template_candidates}

        out: list[tuple[str, str]] = []
        for item in dataset_items:
            dataset_id = str(item.get("id") or "").strip()
            if not dataset_id:
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}

            group_data = (rels.get("group") or {}).get("data") if isinstance(rels, dict) else None
            subgroup_id = str(group_data.get("id") or attrs.get("groupId") or "").strip() if isinstance(group_data, dict) else str(attrs.get("groupId") or "").strip()
            subgroup_info = subgroup_map.get(subgroup_id, {})
            subgroup_name = str(subgroup_info.get("name") or "").strip()

            grant = str(attrs.get("grantNumber") or "").strip()
            dataset_name = str(attrs.get("name") or "").strip()

            inst_labels: list[str] = []
            instruments_data = (rels.get("instruments") or {}).get("data") if isinstance(rels, dict) else []
            if isinstance(instruments_data, dict):
                instruments_data = [instruments_data]
            for inst in instruments_data if isinstance(instruments_data, list) else []:
                if not isinstance(inst, dict):
                    continue
                inst_id = str(inst.get("id") or "").strip()
                if not inst_id:
                    continue
                name = instrument_name_map.get(inst_id)
                if name:
                    inst_labels.append(name)

            if not inst_labels:
                template_data = (rels.get("template") or {}).get("data") if isinstance(rels, dict) else None
                template_id = str(template_data.get("id") or attrs.get("templateId") or "").strip() if isinstance(template_data, dict) else str(attrs.get("templateId") or "").strip()
                if template_id:
                    template_display = template_display_by_id.get(template_id, "")
                    if "|" in template_display:
                        inst_labels = [template_display.split("|", 1)[1].strip()]

            display = _join_non_empty([
                subgroup_name,
                grant,
                dataset_name,
                ", ".join(inst_labels),
            ])
            if not display:
                display = dataset_id
            out.append((display, dataset_id))
        return out

    def _collect_dataset_filter_candidates(self, dataset_items: list[dict]) -> tuple[set[str], set[str], set[str], set[str]]:
        grants: set[str] = set()
        templates: set[str] = set()
        related_ids: set[str] = set()
        dataset_ids: set[str] = set()

        for item in dataset_items:
            if not isinstance(item, dict):
                continue
            dataset_id = str(item.get("id") or "").strip()
            if dataset_id:
                dataset_ids.add(dataset_id)

            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            grant = str(attrs.get("grantNumber") or "").strip()
            if grant:
                grants.add(grant)

            rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
            template_data = (rels.get("template") or {}).get("data") if isinstance(rels, dict) else None
            if isinstance(template_data, dict):
                template_id = str(template_data.get("id") or "").strip()
                if template_id:
                    templates.add(template_id)

            attr_template = str(attrs.get("templateId") or "").strip()
            if attr_template:
                templates.add(attr_template)

            related_data = (rels.get("relatedDatasets") or {}).get("data") if isinstance(rels, dict) else []
            if isinstance(related_data, dict):
                related_data = [related_data]
            for rel_item in related_data if isinstance(related_data, list) else []:
                if not isinstance(rel_item, dict):
                    continue
                rid = str(rel_item.get("id") or "").strip()
                if rid:
                    related_ids.add(rid)

        template_path = get_dynamic_file_path("output/rde/data/template.json")
        for item in _load_json_list_or_data(template_path):
            template_id = str(item.get("id") or "").strip()
            if template_id:
                templates.add(template_id)

        related_ids.update(dataset_ids)
        return grants, templates, related_ids, dataset_ids

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]], selected_text: str):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        seen: set[str] = set()
        for label, match_value in items:
            text = str(label or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            combo.addItem(text)
            combo.setItemData(combo.count() - 1, str(match_value or "").strip(), Qt.UserRole)
        if selected_text:
            index = combo.findText(selected_text)
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                combo.setEditText(selected_text)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _update_filter_options(self, records: list[dict]):
        datasets = self._dataset_items_cache if self._dataset_items_cache else self._load_dataset_items()

        current_subgroup = self.f_subgroup.currentText().strip()
        current_grant = self.f_grant.currentText().strip()
        current_template = self.f_template.currentText().strip()
        current_related = self.f_related.currentText().strip()
        current_equip_name = self.f_equip_name.currentText().strip()
        current_equip_local = self.f_equip_local.currentText().strip()

        subgroup_set = self._collect_subgroup_candidates(datasets)
        grant_set, template_set, related_set, _dataset_ids = self._collect_dataset_filter_candidates(datasets)
        subgroup_info_map = self._load_subgroup_info_map()
        template_display_items = self._collect_template_display_candidates(datasets)
        related_display_items = self._collect_related_dataset_display_candidates(datasets)
        equip_name_set: set[str] = set()
        equip_local_name_map: dict[str, str] = {}

        for rec in records:
            subgroup = str(rec.get("subgroup") or "").strip()
            if subgroup:
                subgroup_set.add(subgroup)
            grant = str(rec.get("grant_number") or "").strip()
            if grant:
                grant_set.add(grant)
            template = str(rec.get("template") or "").strip()
            if template:
                template_set.add(template)
            equip_name = str(rec.get("equipment_name") or "").strip()
            if equip_name:
                equip_name_set.add(equip_name)
            equip_local = str(rec.get("equipment_local_id") or "").strip()
            if equip_local:
                current = equip_local_name_map.get(equip_local, "")
                equip_local_name_map[equip_local] = current or equip_name

            related_values = str(rec.get("related_datasets") or "").strip()
            if related_values:
                for value in [v.strip() for v in related_values.split(",")]:
                    if value:
                        related_set.add(value)

        extra_names, extra_local_name_map = self._collect_equipment_candidates()
        equip_name_set.update(extra_names)
        for local_id, equip_name in extra_local_name_map.items():
            current = equip_local_name_map.get(local_id, "")
            equip_local_name_map[local_id] = current or str(equip_name or "").strip()

        for mapped_name in [v for v in equip_local_name_map.values() if str(v).strip()]:
            equip_name_set.add(str(mapped_name).strip())

        subgroup_items: list[tuple[str, str]] = []
        for gid in sorted(subgroup_set):
            info = subgroup_info_map.get(gid, {})
            name = str(info.get("name") or "").strip()
            desc = str(info.get("description") or "").strip()
            label = _join_non_empty([name, desc]) or gid
            subgroup_items.append((label, gid))

        grant_items = [(grant, grant) for grant in sorted(grant_set)]

        template_item_map: dict[str, tuple[str, str]] = {label: (label, match) for label, match in template_display_items}
        known_template_ids = {match for _, match in template_display_items}
        for tid in sorted(template_set):
            if tid not in known_template_ids:
                template_item_map[tid] = (tid, tid)

        related_item_map: dict[str, tuple[str, str]] = {label: (label, match) for label, match in related_display_items}
        known_related_ids = {match for _, match in related_display_items}
        for rid in sorted(related_set):
            if rid not in known_related_ids:
                related_item_map[rid] = (rid, rid)

        equip_name_items = [(name, name) for name in sorted(equip_name_set)]
        equip_local_items: list[tuple[str, str]] = []
        for local_id in sorted(equip_local_name_map.keys()):
            equip_name = str(equip_local_name_map.get(local_id) or "").strip()
            label = _join_non_empty([local_id, equip_name]) or local_id
            equip_local_items.append((label, local_id))

        self._set_combo_items(self.f_subgroup, subgroup_items, current_subgroup)
        self._set_combo_items(self.f_grant, grant_items, current_grant)
        self._set_combo_items(self.f_template, sorted(template_item_map.values(), key=lambda x: x[0]), current_template)
        self._set_combo_items(self.f_related, sorted(related_item_map.values(), key=lambda x: x[0]), current_related)
        self._set_combo_items(self.f_equip_name, equip_name_items, current_equip_name)
        self._set_combo_items(self.f_equip_local, equip_local_items, current_equip_local)

    def _populate_table(self, records: list[dict]):
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for rec in records:
            r = self.table.rowCount()
            self.table.insertRow(r)

            checked_item = QTableWidgetItem()
            checked_item.setFlags(checked_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checked_item.setCheckState(Qt.Checked)
            checked_item.setText("✓")
            checked_item.setTextAlignment(Qt.AlignCenter)
            checked_item.setData(Qt.UserRole, rec)
            self.table.setItem(r, 0, checked_item)

            values = [
                self._resolve_subgroup_display(rec.get("subgroup", "")),
                rec.get("grant_number", ""),
                rec.get("dataset_name", ""),
                rec.get("tile_number", ""),
                rec.get("tile_name", ""),
                rec.get("tile_id", ""),
                rec.get("sample_name", ""),
                rec.get("sample_uuid", ""),
                rec.get("equipment_name", ""),
                rec.get("equipment_local_id", ""),
                rec.get("tags", ""),
            ]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(_to_text(value))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(r, col, item)

            self._apply_row_visual_state(r)

        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)

    def _resolve_subgroup_display(self, subgroup_id: str) -> str:
        subgroup_id = str(subgroup_id or "").strip()
        if not subgroup_id:
            return ""
        info = self._load_subgroup_info_map().get(subgroup_id, {})
        return _join_non_empty([str(info.get("name") or ""), str(info.get("description") or "")]) or subgroup_id

    def _on_item_changed(self, item: QTableWidgetItem):
        if item is None:
            return
        if item.column() != 0:
            return
        self._apply_row_visual_state(item.row())

    def _apply_row_visual_state(self, row: int):
        check_item = self.table.item(row, 0)
        if check_item is None:
            return
        checked = check_item.checkState() == Qt.Checked
        check_item.setText("✓" if checked else "")
        bg = get_qcolor(ThemeKey.BUTTON_SUCCESS_BACKGROUND if checked else ThemeKey.TABLE_ROW_BACKGROUND)
        fg = get_qcolor(ThemeKey.BUTTON_SUCCESS_TEXT if checked else ThemeKey.TABLE_ROW_TEXT)
        for col in range(self.table.columnCount()):
            cell = self.table.item(row, col)
            if cell is None:
                continue
            cell.setData(Qt.BackgroundRole, bg)
            cell.setData(Qt.ForegroundRole, fg)

    def _set_checked_all(self, checked: bool, ensure_current: bool = False):
        if ensure_current:
            self._ensure_records_ready()
        state = Qt.Checked if checked else Qt.Unchecked
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None:
                it.setCheckState(state)

    def _invert_checks(self, ensure_current: bool = False):
        if ensure_current:
            self._ensure_records_ready()
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is None:
                continue
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)

    def _exclude_checked(self, ensure_current: bool = False):
        if ensure_current:
            self._ensure_records_ready()
        kept: list[dict] = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            rec = it.data(Qt.UserRole) if it else None
            if rec is None:
                continue
            if it.checkState() != Qt.Checked:
                kept.append(rec)
        self._records = kept
        self._populate_table(self._records)
        self._records_dirty = False
        self.status.setText(f"選択除外後: {len(self._records)} タイル")

    def _export(self, fmt: str):
        if fmt not in {"csv"}:
            return

        self._ensure_records_ready()
        if not self._records:
            QMessageBox.information(self, "情報", "出力対象がありません。")
            return

        path, _ = QFileDialog.getSaveFileName(self, "保存", "rde_bulk_tiles.csv", "CSV (*.csv)")
        if not path:
            return

        headers = [
            "subgroup",
            "subgroup_display",
            "grant_number",
            "dataset_name",
            "tile_number",
            "tile_name",
            "tile_id",
            "sample_name",
            "sample_uuid",
            "equipment_name",
            "equipment_local_id",
            "tags",
            "template",
            "related_datasets",
        ]

        export_rows: list[dict] = []
        for rec in self._records:
            row = dict(rec)
            row["subgroup_display"] = self._resolve_subgroup_display(row.get("subgroup", ""))
            export_rows.append(row)

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for rec in export_rows:
                writer.writerow({k: _to_text(rec.get(k, "")) for k in headers})
        QMessageBox.information(self, "出力", f"出力しました: {path}")

    def _toggle_row_height_mode(self):
        self._compact_rows_mode = not self._compact_rows_mode
        if self._compact_rows_mode:
            self.compact_rows_btn.setText("複数行表示")
            self._apply_single_line_row_heights()
        else:
            self.compact_rows_btn.setText("1行表示")
            self._reset_auto_row_heights()

    def _apply_single_line_row_heights(self):
        row_h = int(self.table.fontMetrics().height() * 1.6)
        if row_h <= 0:
            return
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, row_h)

    def _reset_auto_row_heights(self):
        row_h = int(self.table.fontMetrics().height() * 1.8)
        if row_h <= 0:
            row_h = 26
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, row_h)

    def _selected_records(self) -> list[dict]:
        selected: list[dict] = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is None or it.checkState() != Qt.Checked:
                continue
            rec = it.data(Qt.UserRole)
            if isinstance(rec, dict):
                selected.append(rec)
        return selected

    def _ask_filter_usage(self) -> dict | None:
        ans = QMessageBox.question(
            self,
            "ファイルフィルタ適用",
            "今回の一括取得でファイルフィルタを適用しますか？",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if ans == QMessageBox.Cancel:
            return None
        if ans == QMessageBox.Yes:
            return dict(self.current_filter_config or get_default_filter())
        return get_default_filter()

    def _build_hierarchy_relpath(self, rec: dict, file_name: str) -> str:
        subgroup_label = str(rec.get("subgroup_display") or "").strip()
        if not subgroup_label:
            subgroup_label = self._resolve_subgroup_display(rec.get("subgroup", ""))
        grant = str(rec.get("grant_number") or "").strip()
        dataset_name = str(rec.get("dataset_name") or "").strip()
        tile_number = str(rec.get("tile_number") or "").strip()
        tile_name = str(rec.get("tile_name") or "").strip()
        tile_label = f"{tile_number}_{tile_name}" if tile_number else tile_name
        if not tile_label:
            tile_label = str(rec.get("tile_id") or "").strip()

        parts = [
            _safe_path_component(subgroup_label),
            _safe_path_component(grant),
            _safe_path_component(dataset_name),
            _safe_path_component(tile_label),
            _safe_path_component(file_name),
        ]
        return os.path.join(*parts)

    def _copy_outputs(self, saved_items: list[tuple[str, dict]], options: dict):
        flat_enabled = bool(options.get("flat_enabled"))
        zip_enabled = bool(options.get("zip_enabled"))
        flat_dir = str(options.get("flat_dir") or "").strip()
        zip_path = str(options.get("zip_path") or "").strip()

        if flat_enabled and flat_dir:
            os.makedirs(flat_dir, exist_ok=True)
            for src, rec in saved_items:
                if not os.path.isfile(src):
                    continue
                base = os.path.basename(src)
                relpath = self._build_hierarchy_relpath(rec, base)
                dst = os.path.join(flat_dir, relpath)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        if zip_enabled and zip_path:
            os.makedirs(os.path.dirname(zip_path) or ".", exist_ok=True)
            with zipfile.ZipFile(zip_path, mode="a", compression=zipfile.ZIP_DEFLATED) as zf:
                for src, rec in saved_items:
                    if not os.path.isfile(src):
                        continue
                    relpath = self._build_hierarchy_relpath(rec, os.path.basename(src))
                    zf.write(src, arcname=relpath.replace("\\", "/"))

    def execute_bulk_download(self):
        self._ensure_records_ready()
        selected = self._selected_records()
        if not selected:
            QMessageBox.information(self, "情報", "取得対象タイルを選択してください。")
            return

        filter_config = self._ask_filter_usage()
        if filter_config is None:
            return

        opt_dialog = BulkSaveOptionDialog(self)
        if opt_dialog.exec() != QDialog.Accepted:
            return
        options = opt_dialog.get_values()

        if options.get("flat_enabled") and not options.get("flat_dir"):
            QMessageBox.warning(self, "入力不足", "保存先フォルダを指定してください。")
            return
        if options.get("zip_enabled") and not options.get("zip_path"):
            QMessageBox.warning(self, "入力不足", "ZIP保存先を指定してください。")
            return

        from core.bearer_token_manager import BearerTokenManager
        from classes.data_fetch2.core.logic.fetch2_filelist_logic import _process_data_entry_for_parallel

        token = BearerTokenManager.get_token_with_relogin_prompt(self)
        if not token:
            QMessageBox.warning(self, "認証エラー", "Bearer Tokenを取得できませんでした。")
            return

        saved_items: list[tuple[str, dict]] = []
        ok = 0
        ng = 0
        for idx, rec in enumerate(selected, start=1):
            self.status.setText(f"取得中... {idx}/{len(selected)} : {rec.get('dataset_name', '')} / {rec.get('tile_name', '')}")
            dataset_obj = rec.get("dataset_obj") or {}
            dataset_attrs = dataset_obj.get("attributes", {}) if isinstance(dataset_obj, dict) else {}
            grant = str(dataset_attrs.get("grantNumber") or "")
            dataset_name = str(dataset_attrs.get("name") or "")
            entry_obj = rec.get("entry_obj")
            if not isinstance(entry_obj, dict):
                ng += 1
                continue

            result = _process_data_entry_for_parallel(
                token,
                entry_obj,
                get_dynamic_file_path("output/rde/data/dataFiles"),
                grant,
                dataset_name,
                filter_config,
                self,
                None,
            )
            if isinstance(result, dict) and result.get("status") == "success":
                ok += 1
            else:
                ng += 1

            tile_number = str(rec.get("tile_number") or "")
            tile_name = str(rec.get("tile_name") or "")
            safe_tile = f"{tile_number}_{tile_name}" if tile_number else tile_name
            safe_tile = safe_tile.replace("/", "_").replace("\\", "_")
            tile_dir = get_dynamic_file_path(
                f"output/rde/data/dataFiles/{grant}/{dataset_name}/{safe_tile}"
            )
            if os.path.isdir(tile_dir):
                for name in os.listdir(tile_dir):
                    src = os.path.join(tile_dir, name)
                    if os.path.isfile(src):
                        saved_items.append((src, rec))

        self._copy_outputs(saved_items, options)
        self.status.setText(f"完了: 成功 {ok} / 失敗 {ng} / 追加保存対象ファイル {len(saved_items)}")
        QMessageBox.information(
            self,
            "一括取得完了",
            f"通常保存（データ取得タブと同一フォルダ）に加えて追加保存処理を実施しました。\n成功: {ok}\n失敗: {ng}",
        )


def create_bulk_rde_tab(parent: QWidget | None = None) -> DataFetch2BulkRdeTab:
    return DataFetch2BulkRdeTab(parent)
