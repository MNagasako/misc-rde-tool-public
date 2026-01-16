"""Dialog to relink a data entry (tile) to another existing sample within allowed scope."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Set, Tuple
from qt_compat.widgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from config.common import get_dynamic_file_path
from core.bearer_token_manager import BearerTokenManager

from classes.dataset.ui.invoice_edit_dialog import fetch_invoice_for_edit, patch_invoice_for_edit
from classes.subgroup.core.subgroup_api_client import SubgroupApiClient
from classes.subgroup.util.sample_dedup_table_records import fetch_samples_for_subgroups


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


class SampleEntrySampleRelinkDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        subgroup_id: str,
        current_sample_id: str,
        entry_id: str,
        tile_name: str = "",
        dataset_name: str = "",
    ):
        super().__init__(parent)
        self._subgroup_id = str(subgroup_id or "").strip()
        self._current_sample_id = str(current_sample_id or "").strip()
        self._entry_id = str(entry_id or "").strip()
        self._tile_name = str(tile_name or "").strip()
        self._dataset_name = str(dataset_name or "").strip()

        self.setWindowTitle("紐づけ試料変更")
        self.setMinimumWidth(620)

        self._combo = QComboBox(self)
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.NoInsert)
        self._combo.setMaxVisibleItems(15)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)

        self._reload_btn = QPushButton("候補を再読み込み", self)
        self._reload_btn.clicked.connect(lambda: self._load_candidates(force_fetch=True))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)

        title = "タイルの紐づけ試料を変更します。"
        if self._tile_name:
            title += f"\nタイル: {self._tile_name}"
        if self._dataset_name:
            title += f"\nデータセット: {self._dataset_name}"
        layout.addWidget(QLabel(title, self))

        layout.addWidget(QLabel(f"データエントリーID: {self._entry_id}", self))
        layout.addWidget(QLabel(f"現在の試料ID: {self._current_sample_id or '(不明)'}", self))

        row = QHBoxLayout()
        row.addWidget(QLabel("新しい試料:", self))
        row.addWidget(self._combo, 1)
        row.addWidget(self._reload_btn)
        layout.addLayout(row)

        layout.addWidget(self._status)
        layout.addWidget(buttons)

        self._load_candidates(force_fetch=False)

    def _samples_file_path(self, subgroup_id: str) -> str:
        sid = str(subgroup_id or "").strip()
        return get_dynamic_file_path(f"output/rde/data/samples/{sid}.json")

    def _read_samples_file(self, subgroup_id: str) -> List[Dict[str, Any]]:
        try:
            path = self._samples_file_path(subgroup_id)
            if not path or not os.path.exists(path):
                return []
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            data = payload.get("data") if isinstance(payload, dict) else None
            return [x for x in (data or []) if isinstance(x, dict)]
        except Exception:
            return []

    def _sharing_group_subgroup_ids(self) -> List[str]:
        # sharingGroups are represented as subgroup-like entities (id/name).
        ids: List[str] = []
        if not self._current_sample_id:
            return ids
        try:
            api = SubgroupApiClient(self)
            detail = api.get_sample_detail(self._current_sample_id)
            included = detail.get("included") if isinstance(detail, dict) else None
            if not isinstance(included, list):
                return ids
            for item in included:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "sharingGroup":
                    continue
                gid = _safe_str(item.get("id")).strip()
                if gid:
                    ids.append(gid)
        except Exception:
            return ids
        # unique while keeping order
        seen: Set[str] = set()
        out: List[str] = []
        for x in ids:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def _load_candidates(self, *, force_fetch: bool) -> None:
        if not self._subgroup_id:
            self._status.setText("サブグループIDが取得できないため候補を作れません。")
            self._combo.clear()
            return

        subgroup_ids = [self._subgroup_id] + self._sharing_group_subgroup_ids()
        subgroup_ids = [x for x in subgroup_ids if x]

        missing: List[str] = []
        for sgid in subgroup_ids:
            path = self._samples_file_path(sgid)
            if not path or not os.path.exists(path):
                missing.append(sgid)

        if force_fetch and missing:
            try:
                msg = fetch_samples_for_subgroups(missing)
                self._status.setText(str(msg))
            except Exception:
                pass

        candidates: List[Tuple[str, str]] = []
        seen_ids: Set[str] = set()
        for sgid in subgroup_ids:
            for s in self._read_samples_file(sgid):
                sid = _safe_str(s.get("id")).strip()
                if not sid or sid in seen_ids:
                    continue
                attrs = s.get("attributes") if isinstance(s.get("attributes"), dict) else {}
                names = attrs.get("names") if isinstance(attrs.get("names"), list) else []
                name = _safe_str(names[0]).strip() if names else ""
                label = f"{name} (ID: {sid})" if name else f"ID: {sid}"
                if sgid != self._subgroup_id:
                    label += f"  [共有:{sgid}]"
                candidates.append((label, sid))
                seen_ids.add(sid)

        self._combo.blockSignals(True)
        self._combo.clear()
        for label, sid in candidates:
            self._combo.addItem(label, sid)
        self._combo.blockSignals(False)

        # preselect: keep current if present, else first.
        if self._current_sample_id:
            idx = self._combo.findData(self._current_sample_id)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)

        self._status.setText(
            f"候補: {len(candidates)} 件（サブグループ={self._subgroup_id} / 共有グループ={len(subgroup_ids)-1}）"
        )

    def _on_accept(self) -> None:
        new_sample_id = _safe_str(self._combo.currentData()).strip()
        if not new_sample_id:
            QMessageBox.warning(self, "入力エラー", "新しい試料が選択されていません")
            return
        if not self._entry_id:
            QMessageBox.warning(self, "入力エラー", "データエントリーIDが取得できません")
            return

        if new_sample_id == self._current_sample_id:
            # No change.
            self.accept()
            return

        token = BearerTokenManager.get_token_with_relogin_prompt(self)
        if not token:
            QMessageBox.warning(self, "認証エラー", "Bearerトークンが取得できません")
            return

        try:
            payload = fetch_invoice_for_edit(self._entry_id, token)
            data = payload.get("data") if isinstance(payload, dict) else None
            attributes = data.get("attributes") if isinstance(data, dict) else {}
            if not isinstance(attributes, dict):
                attributes = {}

            sample = attributes.get("sample") if isinstance(attributes.get("sample"), dict) else {}
            sample["sampleId"] = new_sample_id
            attributes["sample"] = sample

            patch_invoice_for_edit(self._entry_id, attributes, token)
        except Exception as exc:
            QMessageBox.critical(self, "更新失敗", f"試料の紐づけ更新に失敗しました:\n{exc}")
            return

        QMessageBox.information(self, "更新完了", "試料の紐づけを更新しました。")
        self.accept()
