from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QFileDialog,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from classes.equipment.util import equipment_manager_store as store
from classes.utils.facility_link_helper import (
    load_equipment_name_map_from_merged_data2,
)


@dataclass(frozen=True)
class EquipmentEntry:
    equipment_id: str
    device_name_ja: str


def _pick_first_nonempty(*values: Any) -> str:
    for v in values:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _load_instruments_localid_name_entries() -> List[EquipmentEntry]:
    """output/rde/data/instruments.json から localId + nameJa を抽出して一覧化する。"""

    try:
        from config.common import INSTRUMENTS_JSON_PATH

        path = Path(INSTRUMENTS_JSON_PATH)
    except Exception:
        return []

    if not path.exists() or not path.is_file():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []

    result: List[EquipmentEntry] = []
    for inst in data:
        if not isinstance(inst, dict):
            continue
        attr = inst.get("attributes") or {}
        name_ja = str(attr.get("nameJa") or "").strip()
        programs = attr.get("programs") or []
        local_id = ""
        if isinstance(programs, list):
            for prog in programs:
                if not isinstance(prog, dict):
                    continue
                lid = str(prog.get("localId") or "").strip()
                if lid:
                    local_id = lid
                    break
        if local_id:
            result.append(EquipmentEntry(equipment_id=local_id, device_name_ja=name_ja))

    return result


def build_equipment_catalog() -> List[EquipmentEntry]:
    """merged_data2 + instruments.json から設備エントリ一覧を作る（重複はequipment_idで統合）。"""

    catalog: Dict[str, EquipmentEntry] = {}

    # merged_data2: equipment_id -> ja/raw
    try:
        name_map = load_equipment_name_map_from_merged_data2()
    except Exception:
        name_map = {}

    for eid, item in (name_map or {}).items():
        if not isinstance(item, dict):
            continue
        equipment_id = str(eid or "").strip()
        if not equipment_id:
            continue
        device_name_ja = str(item.get("ja") or item.get("raw") or item.get("en") or "").strip()
        catalog[equipment_id] = EquipmentEntry(equipment_id=equipment_id, device_name_ja=device_name_ja)

    # instruments.json: localId -> nameJa
    for e in _load_instruments_localid_name_entries():
        if not e.equipment_id:
            continue
        existing = catalog.get(e.equipment_id)
        if existing is None:
            catalog[e.equipment_id] = e
        else:
            # nameが空なら補完
            if not existing.device_name_ja and e.device_name_ja:
                catalog[e.equipment_id] = EquipmentEntry(equipment_id=e.equipment_id, device_name_ja=e.device_name_ja)

    # sort by equipment_id
    items = list(catalog.values())
    items.sort(key=lambda x: x.equipment_id)
    return items


class EquipmentManagerListDialog(QDialog):
    """設備管理者リスト編集ダイアログ。

    - 表示: 設備ID / 装置名 / 管理者名 / 管理者メール / 備考
    - 1セルに複数値を入れる場合は ';' または改行で区切る
    - 保存先: input/equipment_managers.json
    """

    def __init__(self, parent: QWidget, *, equipment_entries: Optional[Iterable[Tuple[str, str]]] = None):
        super().__init__(parent)
        self.setWindowTitle("設備管理者リスト")

        layout = QVBoxLayout(self)

        try:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
        except Exception:
            pass

        layout.addWidget(QLabel("設備IDごとに装置管理者情報（名前/メール/備考）を登録します。複数ある場合は ';' または改行で区切って入力してください。"))

        self._headers = ["設備ID", "装置名", "管理者名", "管理者メール", "備考"]

        # filters
        filter_area = QScrollArea(self)
        filter_area.setWidgetResizable(True)
        filter_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        filter_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        filter_widget = QWidget(filter_area)
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filters: List[QLineEdit] = []
        for h in self._headers:
            f = QLineEdit()
            f.setPlaceholderText(h)
            f.setClearButtonEnabled(True)
            f.textChanged.connect(self._apply_filters)
            f.setMinimumWidth(140)
            self._filters.append(f)
            filter_layout.addWidget(f)
        filter_layout.addStretch()
        filter_area.setWidget(filter_widget)
        try:
            filter_area.setMaximumHeight(max(44, filter_widget.sizeHint().height() + 6))
        except Exception:
            filter_area.setMaximumHeight(52)
        layout.addWidget(filter_area)

        self.table = QTableWidget(0, len(self._headers), self)
        self.table.setHorizontalHeaderLabels(self._headers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setTextElideMode(Qt.ElideRight)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setSectionResizeMode(3, QHeaderView.Stretch)
            header.setSectionResizeMode(4, QHeaderView.Stretch)
        except Exception:
            header.setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.open_file_btn = QPushButton("管理者リストJSONを開く")
        self.open_folder_btn = QPushButton("格納フォルダを開く")
        self.export_xlsx_btn = QPushButton("XLSXエクスポート")
        self.import_xlsx_btn = QPushButton("XLSXインポート")
        self.save_btn = QPushButton("保存")
        self.cancel_btn = QPushButton("キャンセル")
        btn_row.addWidget(self.open_file_btn)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addWidget(self.export_xlsx_btn)
        btn_row.addWidget(self.import_xlsx_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn.clicked.connect(self.reject)
        self.open_file_btn.clicked.connect(self._open_store_file)
        self.open_folder_btn.clicked.connect(self._open_store_folder)
        self.export_xlsx_btn.clicked.connect(self._export_xlsx)
        self.import_xlsx_btn.clicked.connect(self._import_xlsx)

        self._load_rows(equipment_entries)

        try:
            if parent is not None:
                self.resize(int(parent.width() * 0.9), max(520, int(parent.height() * 0.85)))
        except Exception:
            pass

    def _load_rows(self, equipment_entries: Optional[Iterable[Tuple[str, str]]]):
        # Optional: allow callers to pass only IDs (name empty). In that case,
        # fill names from merged_data2 / instruments.json.
        try:
            merged_name_map = load_equipment_name_map_from_merged_data2()
        except Exception:
            merged_name_map = {}

        instruments_name_map: Dict[str, str] = {}
        try:
            for e in _load_instruments_localid_name_entries():
                if e.equipment_id:
                    instruments_name_map[e.equipment_id] = (e.device_name_ja or "").strip()
        except Exception:
            instruments_name_map = {}

        if equipment_entries is None:
            entries = build_equipment_catalog()
        else:
            entries = [EquipmentEntry(equipment_id=str(eid or "").strip(), device_name_ja=str(name or "").strip()) for eid, name in equipment_entries]
            entries = [e for e in entries if e.equipment_id]
            entries.sort(key=lambda x: x.equipment_id)

        mapping = store.load_equipment_managers()

        sorting_enabled = False
        try:
            sorting_enabled = bool(self.table.isSortingEnabled())
        except Exception:
            sorting_enabled = False

        try:
            # ソート有効のまま setItem すると行が移動してセル設定がズレるため一時停止する
            self.table.setSortingEnabled(False)
            self.table.setUpdatesEnabled(False)
        except Exception:
            pass

        self.table.setRowCount(0)
        for e in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)

            eid_item = QTableWidgetItem(e.equipment_id)
            eid_item.setFlags(eid_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, eid_item)

            device_name_ja = (e.device_name_ja or "").strip()
            if not device_name_ja:
                mm = merged_name_map.get(e.equipment_id) if isinstance(merged_name_map, dict) else None
                if isinstance(mm, dict):
                    device_name_ja = _pick_first_nonempty(mm.get("ja"), mm.get("raw"), mm.get("en"))
            if not device_name_ja:
                device_name_ja = (instruments_name_map.get(e.equipment_id) or "").strip()

            name_item = QTableWidgetItem(device_name_ja)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            managers = mapping.get(e.equipment_id, [])
            names, emails, notes = store.managers_to_placeholder_fields(managers)

            self.table.setItem(row, 2, QTableWidgetItem(names))
            self.table.setItem(row, 3, QTableWidgetItem(emails))
            self.table.setItem(row, 4, QTableWidgetItem(notes))

        try:
            self.table.setUpdatesEnabled(True)
            self.table.setSortingEnabled(sorting_enabled)
        except Exception:
            pass

        self._apply_filters()

    def _open_store_file(self):
        try:
            path = Path(store.get_equipment_manager_store_path())
        except Exception:
            QMessageBox.information(self, "開く", "管理者リストのパスを取得できませんでした。")
            return

        if not path.exists():
            QMessageBox.information(self, "開く", "管理者リストJSONはまだ作成されていません。保存すると作成されます。")
            return

        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception:
            QMessageBox.information(self, "開く", "ファイルを開けませんでした。")

    def _open_store_folder(self):
        try:
            path = Path(store.get_equipment_manager_store_path())
            folder = path.parent
            folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            QMessageBox.information(self, "開く", "格納フォルダのパスを取得できませんでした。")
            return

        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception:
            QMessageBox.information(self, "開く", "フォルダを開けませんでした。")

    def _apply_filters(self):
        texts = [(f.text() or "").strip().lower() for f in self._filters]
        for r in range(self.table.rowCount()):
            hide = False
            for c, t in enumerate(texts):
                if not t:
                    continue
                item = self.table.item(r, c)
                cell = (item.text() if item else "").lower()
                if t not in cell:
                    hide = True
                    break
            self.table.setRowHidden(r, hide)

    def _on_save(self):
        mapping, _name_map = self._build_mapping_from_table()

        try:
            store.save_equipment_managers(mapping)
        except Exception as exc:
            QMessageBox.warning(self, "保存失敗", f"保存に失敗しました: {exc}")
            return

        QMessageBox.information(self, "保存", "設備管理者リストを保存しました。")
        self.accept()

    def _build_mapping_from_table(self) -> tuple[Dict[str, List[store.EquipmentManager]], Dict[str, str]]:
        mapping: Dict[str, List[store.EquipmentManager]] = {}
        name_map: Dict[str, str] = {}
        for r in range(self.table.rowCount()):
            eid = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if not eid:
                continue
            device_name = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if device_name:
                name_map[eid] = device_name
            names = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            emails = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            notes = self.table.item(r, 4).text() if self.table.item(r, 4) else ""
            managers = store.parse_managers_from_fields(names, emails, notes)
            if managers:
                mapping[eid] = managers
        return (mapping, name_map)

    def _export_xlsx(self):
        mapping, name_map = self._build_mapping_from_table()
        try:
            default_dir = str(Path(store.get_equipment_manager_store_path()).parent)
        except Exception:
            default_dir = ""
        default_path = str(Path(default_dir) / "equipment_managers.xlsx") if default_dir else "equipment_managers.xlsx"

        path, _filter = QFileDialog.getSaveFileName(
            self,
            "XLSXエクスポート",
            default_path,
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        if not str(path).lower().endswith(".xlsx"):
            path = f"{path}.xlsx"

        try:
            store.export_equipment_managers_to_xlsx(path=path, mapping=mapping, equipment_name_by_id=name_map)
        except Exception as exc:
            QMessageBox.warning(self, "エクスポート失敗", f"XLSXのエクスポートに失敗しました: {exc}")
            return

        QMessageBox.information(self, "エクスポート", "XLSXをエクスポートしました。")

    def _import_xlsx(self):
        try:
            default_dir = str(Path(store.get_equipment_manager_store_path()).parent)
        except Exception:
            default_dir = ""
        default_path = str(Path(default_dir) / "equipment_managers.xlsx") if default_dir else ""

        path, _filter = QFileDialog.getOpenFileName(
            self,
            "XLSXインポート",
            default_path,
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        try:
            imported_mapping, imported_name_map = store.import_equipment_managers_from_xlsx(path=path)
        except Exception as exc:
            QMessageBox.warning(self, "インポート失敗", f"XLSXの読み込みに失敗しました: {exc}")
            return

        # 置換 or マージ
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("XLSXインポート")
        box.setText("インポート方法を選択してください。")
        replace_btn = box.addButton("置き換え", QMessageBox.AcceptRole)
        merge_btn = box.addButton("マージ", QMessageBox.ActionRole)
        cancel_btn = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(merge_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is None or clicked == cancel_btn:
            return

        current_mapping, _current_names = self._build_mapping_from_table()
        if clicked == replace_btn:
            new_mapping = imported_mapping
        else:
            new_mapping = store.merge_equipment_manager_mappings(current_mapping, imported_mapping)

        self._apply_mapping_to_table(new_mapping, imported_name_map)
        QMessageBox.information(self, "インポート", "XLSXをインポートしました。内容を確認して『保存』してください。")

    def _apply_mapping_to_table(self, mapping: Dict[str, List[store.EquipmentManager]], name_map: Dict[str, str]):
        # existing rows index
        row_by_eid: Dict[str, int] = {}
        for r in range(self.table.rowCount()):
            eid = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if eid:
                row_by_eid[eid] = r

        # add missing rows (from imported)
        for eid, managers in (mapping or {}).items():
            ee = str(eid or "").strip()
            if not ee:
                continue
            if ee in row_by_eid:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)

            eid_item = QTableWidgetItem(ee)
            eid_item.setFlags(eid_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, eid_item)

            dev = str((name_map or {}).get(ee, "") or "").strip()
            name_item = QTableWidgetItem(dev)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            self.table.setItem(row, 2, QTableWidgetItem(""))
            self.table.setItem(row, 3, QTableWidgetItem(""))
            self.table.setItem(row, 4, QTableWidgetItem(""))
            row_by_eid[ee] = row

        # apply values
        for eid, r in row_by_eid.items():
            managers = (mapping or {}).get(eid, [])
            names, emails, notes = store.managers_to_placeholder_fields(list(managers or []))
            self.table.setItem(r, 2, QTableWidgetItem(names))
            self.table.setItem(r, 3, QTableWidgetItem(emails))
            self.table.setItem(r, 4, QTableWidgetItem(notes))
            # 装置名が空で、XLSX側にあれば補完
            if (not (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()) and (name_map or {}).get(eid):
                name_item = QTableWidgetItem(str((name_map or {}).get(eid, "") or ""))
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 1, name_item)

        self._apply_filters()
