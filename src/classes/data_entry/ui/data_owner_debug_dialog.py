from __future__ import annotations

import json
import os
from typing import Any

from classes.managers.log_manager import get_logger
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import get_dynamic_file_path
from qt_compat.core import Qt
from qt_compat.widgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = get_logger(__name__)


def _safe_json_dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(payload)


class JsonViewerDialog(QDialog):
    def __init__(self, parent=None, *, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(920, 680)

        layout = QVBoxLayout(self)

        self._info = QLabel("", self)
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        try:
            self._text.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self._text.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass

        layout.addWidget(self._text)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("閉じる", self)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def set_source(self, *, source_label: str, path: str | None = None, payload: Any | None = None) -> None:
        self._info.setText(source_label)
        if path:
            p = str(path)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        self._text.setPlainText(f.read())
                    return
                except Exception as exc:
                    self._text.setPlainText(f"[ERROR] failed to read: {p}\n{exc}")
                    return
            self._text.setPlainText(f"[NOT FOUND] {p}")
            return

        self._text.setPlainText(_safe_json_dumps(payload))


class DataOwnerDebugDialog(QDialog):
    def __init__(self, parent=None, *, context: dict):
        super().__init__(parent)
        self.setWindowTitle("データ所有者（所属）: エラー詳細")
        self.setModal(True)
        self.resize(980, 720)

        self._context = context if isinstance(context, dict) else {}

        root = QVBoxLayout(self)

        summary = QLabel(self)
        summary.setWordWrap(True)
        notes = self._context.get("notes")
        note_lines = [str(x) for x in notes] if isinstance(notes, list) else []
        if note_lines:
            summary.setText("原因候補:\n- " + "\n- ".join(note_lines))
        else:
            summary.setText("原因候補: (なし)")
        root.addWidget(summary)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(scroll)
        scroll.setWidget(body)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)
        root.addWidget(scroll)

        body_layout.addWidget(self._build_targets_group(body))
        body_layout.addWidget(self._build_structure_group(body))
        body_layout.addStretch(1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("閉じる", self)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _build_targets_group(self, parent: QWidget) -> QGroupBox:
        box = QGroupBox("参照対象", parent)
        layout = QVBoxLayout(box)

        dataset_id = str(self._context.get("dataset_id") or "")
        dataset_path = str(self._context.get("dataset_json_path") or "")
        dataset_exists = bool(self._context.get("dataset_json_exists"))

        group_id = str(self._context.get("group_id") or "")
        subgroup_candidates = self._context.get("subgroup_candidate_paths")
        subgroup_candidates = subgroup_candidates if isinstance(subgroup_candidates, list) else []
        subgroup_existing = self._context.get("subgroup_existing_paths")
        subgroup_existing = subgroup_existing if isinstance(subgroup_existing, list) else []

        # dataset
        ds_row = QHBoxLayout()
        ds_row.addWidget(QLabel(f"Dataset ID: {dataset_id}", box))
        ds_btn = QPushButton("JSONを開く", box)
        ds_btn.setEnabled(bool(dataset_path))
        ds_btn.clicked.connect(lambda: self._open_json(title=f"dataset.json ({dataset_id})", path=dataset_path))
        ds_row.addStretch(1)
        ds_row.addWidget(ds_btn)
        layout.addLayout(ds_row)

        ds_status = QLabel(
            f"dataset.json: {'OK' if dataset_exists else 'NOT FOUND'}\npath: {dataset_path}",
            box,
        )
        ds_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(ds_status)

        # subgroup/group
        sg_row = QHBoxLayout()
        sg_row.addWidget(QLabel(f"SubGroup(Group) ID: {group_id}", box))
        sg_btn = QPushButton("JSONを開く", box)
        sg_btn.setEnabled(bool(subgroup_existing))
        sg_btn.clicked.connect(lambda: self._open_first_existing_subgroup(group_id=group_id))
        sg_row.addStretch(1)
        sg_row.addWidget(sg_btn)
        layout.addLayout(sg_row)

        sg_status_lines = [
            f"subGroup json candidates ({len(subgroup_candidates)}):",
            *[f"- {p}" for p in subgroup_candidates],
            f"existing ({len(subgroup_existing)}):",
            *[f"- {p}" for p in subgroup_existing],
        ]
        sg_status = QLabel("\n".join(sg_status_lines), box)
        sg_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(sg_status)

        hint = QLabel(
            "※ subGroup JSONが無い/構造不足の場合でも、API応答次第でIDのみ候補になることがあります。",
            box,
        )
        hint.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return box

    def _build_structure_group(self, parent: QWidget) -> QGroupBox:
        box = QGroupBox("JSON構造サマリ", parent)
        layout = QVBoxLayout(box)

        rel_keys = self._context.get("dataset_relationship_keys")
        rel_keys = rel_keys if isinstance(rel_keys, list) else []

        included_counts = self._context.get("dataset_included_type_counts")
        included_counts = included_counts if isinstance(included_counts, dict) else {}

        members_count = int(self._context.get("members_count") or 0)
        member_ids = self._context.get("member_ids")
        member_ids = member_ids if isinstance(member_ids, list) else []

        members_preview = self._context.get("members_preview")
        members_preview = members_preview if isinstance(members_preview, list) else []

        lines: list[str] = []
        lines.append(f"dataset.relationships keys: {', '.join(rel_keys) if rel_keys else '(none)'}")
        if included_counts:
            counts_str = ", ".join([f"{k}:{v}" for k, v in sorted(included_counts.items())])
            lines.append(f"dataset.included type counts: {counts_str}")
        else:
            lines.append("dataset.included type counts: (none)")

        lines.append(f"members_count (after load_group_members): {members_count}")
        if member_ids:
            lines.append(f"member_ids: {', '.join(member_ids)}")

        if members_preview:
            lines.append("members_preview (first 20):")
            for m in members_preview:
                if not isinstance(m, dict):
                    continue
                uid = str(m.get("id") or "")
                uname = str(m.get("userName") or "")
                org = str(m.get("organizationName") or "")
                lines.append(f"- {uid} | {uname} | {org}")

        text = QPlainTextEdit(box)
        text.setReadOnly(True)
        text.setPlainText("\n".join(lines))
        try:
            text.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            text.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass

        layout.addWidget(text)
        return box

    def _open_json(self, *, title: str, path: str) -> None:
        dlg = JsonViewerDialog(self, title=title)
        dlg.set_source(source_label=f"path: {path}", path=path)
        dlg.exec()

    def _open_first_existing_subgroup(self, *, group_id: str) -> None:
        subgroup_existing = self._context.get("subgroup_existing_paths")
        subgroup_existing = subgroup_existing if isinstance(subgroup_existing, list) else []
        if subgroup_existing:
            self._open_json(title=f"subGroup.json ({group_id})", path=str(subgroup_existing[0]))
            return

        # 念のため、動的パスで再計算
        gid = str(group_id or "").strip()
        if gid:
            candidates = [
                get_dynamic_file_path(f"output/rde/data/subGroups/{gid}.json"),
                get_dynamic_file_path(f"output/rde/data/subGroupsAncestors/{gid}.json"),
                get_dynamic_file_path(f"output/rde/data/subgroups/{gid}.json"),
            ]
            for p in candidates:
                if p and os.path.exists(p):
                    self._open_json(title=f"subGroup.json ({gid})", path=str(p))
                    return

        dlg = JsonViewerDialog(self, title="subGroup.json")
        dlg.set_source(source_label="subGroup JSON が見つかりません", payload={"group_id": gid})
        dlg.exec()


def show_data_owner_debug_dialog(parent, *, context: dict | None) -> None:
    try:
        ctx = context if isinstance(context, dict) else {}
        dlg = DataOwnerDebugDialog(parent, context=ctx)
        dlg.exec()
    except Exception as exc:
        logger.error("failed to show data owner debug dialog: %s", exc, exc_info=True)
