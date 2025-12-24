from __future__ import annotations

from typing import List

try:
    try:
        from qt_compat.widgets import (
            QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
            QHeaderView, QLineEdit, QHBoxLayout
        )
        from qt_compat.core import Qt
    except Exception:
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
            QHeaderView, QLineEdit, QHBoxLayout
        )
        from PySide6.QtCore import Qt
except ImportError:
    from src.qt_compat.widgets import (
        QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
        QHeaderView, QLineEdit, QHBoxLayout
    )
    from src.qt_compat.core import Qt
import re
import logging
import json
import os
from datetime import datetime

from classes.config.core.models import SupportedFileFormatEntry
from classes.config.core import supported_formats_service as formats_service
from classes.theme import get_color, ThemeKey


class SupportedFormatsTab(QWidget):
    """設定ウィジェット用: 対応ファイル形式一覧タブ。

    外部から`set_entries(List[SupportedFileFormatEntry])`でデータを受け取り表示する。
    列ごとのフィルタ・ソート対応。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("対応ファイル形式一覧")
        layout.addWidget(title)
        
        # フィルタ入力欄（各列用）
        filter_row = QHBoxLayout()
        self.filter_inputs = []
        for col_name in ["装置ID", "拡張子(正規化)", "拡張子(説明込み)", "テンプレート名", "版"]:
            filter_edit = QLineEdit()
            filter_edit.setPlaceholderText(f"{col_name}でフィルタ")
            filter_edit.textChanged.connect(self._apply_filters)
            self.filter_inputs.append(filter_edit)
            filter_row.addWidget(filter_edit)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "装置ID", "拡張子(正規化)", "拡張子(説明込み)", "テンプレート名", "版"
        ])
        # ソート有効化
        self.table.setSortingEnabled(True)
        # 編集設定（ダブルクリック/選択クリック）
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        # 列幅を可変に設定（ユーザーがリサイズ可能）
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # 初期列幅を内容に合わせて調整
        self.table.resizeColumnsToContents()
        self.table.itemChanged.connect(self._handle_item_changed)
        layout.addWidget(self.table)
        
        # ファイルリンク表示用ラベル
        self.file_link_label = QLabel("")
        self.file_link_label.setWordWrap(True)
        layout.addWidget(self.file_link_label)
        
        # 保存結果表示用ラベル
        self.save_status_label = QLabel("")
        self.save_status_label.setWordWrap(True)
        self.save_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SUCCESS)};")
        layout.addWidget(self.save_status_label)

        self.all_entries = []  # フィルタ用の全データ保持
        self._filtered_entries: List[SupportedFileFormatEntry] = []
        self._source_file: str = ""
        self._updating_table = False
        self._logger = logging.getLogger(__name__)

    def set_entries(self, entries: List[SupportedFileFormatEntry], source_file: str = ""):
        self.all_entries = entries
        if source_file:
            self._source_file = source_file
        self._apply_filters()

        # ファイルリンク表示
        target_source = source_file or self._source_file
        if target_source:
            import pathlib
            try:
                out_json = pathlib.Path("output/supported_formats.json").resolve()
                self.file_link_label.setText(
                    f"元ファイル: {target_source}\n"
                    f"抽出済みファイル: {out_json}"
                )
            except Exception:
                self.file_link_label.setText(f"元ファイル: {target_source}")
        else:
            self.file_link_label.setText("")
        self.save_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SUCCESS)};")
        self.save_status_label.setText("")
    
    def _apply_filters(self):
        """フィルタを適用してテーブルを更新"""
        # フィルタ条件を取得
        filters = [f.text().strip().lower() for f in self.filter_inputs]
        
        # フィルタリング
        filtered = []
        for e in self.all_entries:
            # 版をテンプレート名から推測
            inferred_version = self._infer_version(e.template_name) if e.template_version is None else str(e.template_version)
            
            # 各列の値
            exts_str = ", ".join([f".{ext}" for ext in e.file_exts])
            desc_parts = [f".{ext}:{e.file_descs.get(ext, '')}" for ext in e.file_exts]
            desc_str = ", ".join(desc_parts)
            
            row_values = [
                e.equipment_id,
                exts_str,
                desc_str,
                e.template_name,
                inferred_version
            ]
            
            # フィルタチェック
            match = True
            for i, filter_text in enumerate(filters):
                if filter_text and filter_text not in row_values[i].lower():
                    match = False
                    break
            
            if match:
                filtered.append((e, row_values, inferred_version))
        
        # テーブル更新
        self._updating_table = True
        self.table.setSortingEnabled(False)  # 更新中はソート無効化
        self.table.setRowCount(len(filtered))
        self._filtered_entries = []
        for i, (e, row_values, inferred_version) in enumerate(filtered):
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                if col == 1:
                    # 拡張子列のみ編集可
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, col, item)
            self._filtered_entries.append(e)
        self.table.setSortingEnabled(True)  # ソート再有効化
        self._updating_table = False
    
    def _infer_version(self, template_name: str) -> str:
        """テンプレート名から版を推測（例: R6, V3等）"""
        # R6, R7 等のパターン
        m = re.search(r"[_-]?R(\d+)[_-]?", template_name, re.IGNORECASE)
        if m:
            return f"R{m.group(1)}"
        # V3, V4 等のパターン
        m = re.search(r"[_-]?V(\d+)[_-]?", template_name, re.IGNORECASE)
        if m:
            return f"V{m.group(1)}"
        return ""

    def _handle_item_changed(self, item: QTableWidgetItem):
        """拡張子列の編集を検知して保存"""
        if self._updating_table or item.column() != 1:
            return

        row = item.row()
        if row < 0 or row >= len(self._filtered_entries):
            return

        entry = self._filtered_entries[row]
        new_exts = self._parse_extensions(item.text())

        # 正規化結果でUIを再構築
        self._update_entry_extensions(entry, new_exts)
        self._persist_entries()
        self._apply_filters()

    def _parse_extensions(self, raw_text: str) -> List[str]:
        """ユーザーが入力した拡張子文字列を正規化

        対応:
        - 区切り: 半角/全角カンマ・セミコロン・空白・「または」/or
        - スラッシュ表記の展開: .dm3/4 -> dm3, dm4 / tif/tiff -> tif, tiff
        - 先頭ドット・ワイルドカード除去、重複排除、lower化
        """
        if not raw_text:
            return []

        text = raw_text.strip()
        # 全角記号 → 半角に寄せる簡易正規化
        replacements = {
            '、': ',', '，': ',', '；': ';', '・': ',', '／': '/', '　': ' ',
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        # または / or を区切りに
        text = re.sub(r"\s*(または|or)\s*", ",", text, flags=re.IGNORECASE)

        tokens = re.split(r"[\s,;]+", text)

        def expand_slash(tok: str) -> List[str]:
            # 例: dm3/4, dm3/dm4, tif/tiff の展開
            if '/' not in tok:
                return [tok]
            parts = [p for p in tok.split('/') if p]
            if not parts:
                return []
            head = parts[0]
            # 先頭が英字+数字のとき、後続が数字のみなら置換展開
            m = re.match(r"^([a-z]+)(\d+)$", head, re.IGNORECASE)
            if m:
                base, _num = m.group(1), m.group(2)
                out = [head]
                for p in parts[1:]:
                    if re.fullmatch(r"\d+", p):
                        out.append(f"{base}{p}")
                    else:
                        out.append(p)
                return out
            # それ以外は単純分割
            return parts

        normalized: List[str] = []
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            token = token.replace('*', '')
            if token.startswith('.'):
                token = token[1:]
            token = token.lower()
            # スラッシュ展開
            expanded = []
            for t in expand_slash(token):
                t = t.strip()
                if not t:
                    continue
                if t.startswith('.'):
                    t = t[1:]
                t = t.lower()
                if t and t not in expanded:
                    expanded.append(t)
            for t in expanded:
                if t and t not in normalized:
                    normalized.append(t)
        return normalized

    def _update_entry_extensions(self, entry: SupportedFileFormatEntry, new_exts: List[str]):
        """エントリの拡張子・説明マップを更新"""
        existing_descs = entry.file_descs or {}
        entry.file_exts = new_exts
        entry.file_descs = {ext: existing_descs.get(ext, "") for ext in new_exts}

    def _persist_entries(self):
        """現在のエントリ一覧をJSONへ保存"""
        try:
            out_path = formats_service.get_default_output_path()
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            meta = {}
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8") as f:
                    try:
                        meta = json.load(f)
                    except json.JSONDecodeError:
                        meta = {}

            source_file = self._source_file or meta.get("source_file", "")
            parsed_at = meta.get("parsed_at")

            payload = [
                {
                    "equipment_id": e.equipment_id,
                    "file_exts": e.file_exts,
                    "file_descs": e.file_descs,
                    "template_name": e.template_name,
                    "template_version": e.template_version,
                    "source_sheet": e.source_sheet,
                    "original_format": e.original_format,
                }
                for e in self.all_entries
            ]

            meta_out = {
                "source_file": source_file,
                "parsed_at": parsed_at or datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "entries": payload,
            }

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(meta_out, f, ensure_ascii=False, indent=2)

            human_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SUCCESS)};")
            self.save_status_label.setText(f"✅ 拡張子の変更を保存しました ({human_time})")
        except Exception as exc:
            self._logger.error("対応ファイル拡張子の保存に失敗: %s", exc, exc_info=True)
            self.save_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)};")
            self.save_status_label.setText(f"❌ 保存に失敗しました: {exc}")
