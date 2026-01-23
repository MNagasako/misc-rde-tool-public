from __future__ import annotations

import json
import os
from typing import Any

from classes.managers.log_manager import get_logger
from classes.theme import ThemeKey, get_color, get_qcolor
from config.common import get_dynamic_file_path
from qt_compat.core import Qt
from qt_compat.gui import QBrush
from qt_compat.widgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
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
        ctx = context if isinstance(context, dict) else {}
        is_error = bool(ctx.get("is_error"))
        self.setWindowTitle("データ所有者（所属）: 詳細（エラー）" if is_error else "データ所有者（所属）: 詳細")
        self.setModal(True)
        self.resize(980, 720)

        self._context = ctx
        self._targets_text: str = ""
        self._trace_tree: QTreeWidget | None = None
        self._structure_text: QPlainTextEdit | None = None

        root = QVBoxLayout(self)

        summary = QLabel(self)
        summary.setWordWrap(True)
        notes = self._context.get("notes")
        note_lines = [str(x) for x in notes] if isinstance(notes, list) else []
        if note_lines:
            summary.setText("メモ/状態:\n- " + "\n- ".join(note_lines))
        else:
            summary.setText("メモ/状態: (なし)")
        root.addWidget(summary)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setObjectName("data_owner_debug_splitter")
        root.addWidget(splitter, 1)

        targets = self._build_targets_group(splitter)
        trace = self._build_trace_tree_group(splitter)
        structure = self._build_structure_group(splitter)
        splitter.addWidget(targets)
        splitter.addWidget(trace)
        splitter.addWidget(structure)

        try:
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 2)
            splitter.setStretchFactor(2, 1)
            splitter.setSizes([200, 360, 220])
        except Exception:
            pass

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("閉じる", self)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self._setup_dialog_size()

    def _setup_dialog_size(self) -> None:
        """ダイアログ初期サイズを設定（ディスプレイ高さの90%）。"""

        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            screen_rect = screen.availableGeometry()

            target_height = int(screen_rect.height() * 0.9)
            # 幅は既定値(980)を基本としつつ、画面からはみ出さないようにする
            target_width = min(int(self.width() or 980), int(screen_rect.width() * 0.95))
            self.resize(target_width, target_height)
        except Exception as e:
            logger.warning("DataOwnerDebugDialog size setup failed: %s", e)

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            QApplication.clipboard().setText(str(text or ""))
        except Exception:
            pass

    def _tree_to_text(self, tree: QTreeWidget) -> str:
        lines: list[str] = []

        try:
            header0 = tree.headerItem().text(0)
            header1 = tree.headerItem().text(1)
            if header0 or header1:
                lines.append(f"{header0}\t{header1}".rstrip())
        except Exception:
            pass

        def _walk(item: QTreeWidgetItem, depth: int) -> None:
            indent = "  " * max(depth, 0)
            try:
                c0 = item.text(0)
                c1 = item.text(1)
                lines.append(f"{indent}{c0}\t{c1}".rstrip())
            except Exception:
                lines.append(f"{indent}(unreadable)")

            try:
                for i in range(item.childCount()):
                    _walk(item.child(i), depth + 1)
            except Exception:
                return

        try:
            for i in range(tree.topLevelItemCount()):
                _walk(tree.topLevelItem(i), 0)
        except Exception:
            pass

        return "\n".join(lines)

    def _build_targets_group(self, parent: QWidget) -> QGroupBox:
        box = QGroupBox("参照対象", parent)
        layout = QVBoxLayout(box)

        header_row = QHBoxLayout()
        header_row.addStretch(1)
        copy_btn = QPushButton("コピー", box)
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(self._targets_text))
        header_row.addWidget(copy_btn)
        layout.addLayout(header_row)

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
        sg_text = QPlainTextEdit(box)
        sg_text.setReadOnly(True)
        sg_text.setPlainText("\n".join(sg_status_lines))
        layout.addWidget(sg_text)

        hint = QLabel(
            "※ subGroup JSONが無い/構造不足の場合でも、API応答次第でIDのみ候補になることがあります。",
            box,
        )
        hint.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # コピー用
        self._targets_text = "\n".join(
            [
                f"Dataset ID: {dataset_id}",
                f"dataset.json: {'OK' if dataset_exists else 'NOT FOUND'}",
                f"path: {dataset_path}",
                "",
                f"SubGroup(Group) ID: {group_id}",
                *sg_status_lines,
            ]
        )

        return box

    def _build_structure_group(self, parent: QWidget) -> QGroupBox:
        box = QGroupBox("JSON構造サマリ", parent)
        layout = QVBoxLayout(box)

        header_row = QHBoxLayout()
        header_row.addStretch(1)
        copy_btn = QPushButton("コピー", box)
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(self._structure_text.toPlainText() if self._structure_text else ""))
        header_row.addWidget(copy_btn)
        layout.addLayout(header_row)

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
        self._structure_text = text
        return box

    def _build_trace_tree_group(self, parent: QWidget) -> QGroupBox:
        box = QGroupBox("参照ツリー（参照JSON → 参照キー）", parent)
        layout = QVBoxLayout(box)

        header_row = QHBoxLayout()
        header_row.addStretch(1)
        copy_btn = QPushButton("コピー", box)
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(self._tree_to_text(self._trace_tree) if self._trace_tree else ""))
        header_row.addWidget(copy_btn)
        layout.addLayout(header_row)

        tree = QTreeWidget(box)
        tree.setColumnCount(2)
        tree.setHeaderLabels(["項目", "内容"])
        tree.setAlternatingRowColors(True)
        tree.setExpandsOnDoubleClick(True)

        try:
            tree.setStyleSheet(
                f"""
                QTreeWidget {{
                    background-color: {get_color(ThemeKey.FILE_TREE_BACKGROUND)};
                    color: {get_color(ThemeKey.FILE_TREE_TEXT)};
                    border: 1px solid {get_color(ThemeKey.FILE_TREE_BORDER)};
                    border-radius: 4px;
                }}
                QHeaderView::section {{
                    background-color: {get_color(ThemeKey.FILE_TREE_HEADER_BACKGROUND)};
                    color: {get_color(ThemeKey.FILE_TREE_HEADER_TEXT)};
                    border: 1px solid {get_color(ThemeKey.FILE_TREE_BORDER)};
                    padding: 4px;
                }}
                """
            )
        except Exception:
            pass

        def _set_item_state(item: QTreeWidgetItem, *, kind: str) -> None:
            try:
                if kind == "selected":
                    item.setForeground(0, QBrush(get_qcolor(ThemeKey.TEXT_SUCCESS)))
                    item.setForeground(1, QBrush(get_qcolor(ThemeKey.TEXT_SUCCESS)))
                    item.setBackground(0, QBrush(get_qcolor(ThemeKey.TABLE_ROW_OWNER_BACKGROUND)))
                    item.setBackground(1, QBrush(get_qcolor(ThemeKey.TABLE_ROW_OWNER_BACKGROUND)))
                elif kind == "error":
                    item.setForeground(0, QBrush(get_qcolor(ThemeKey.TEXT_ERROR)))
                    item.setForeground(1, QBrush(get_qcolor(ThemeKey.TEXT_ERROR)))
                elif kind == "warning":
                    item.setForeground(0, QBrush(get_qcolor(ThemeKey.TEXT_WARNING)))
                    item.setForeground(1, QBrush(get_qcolor(ThemeKey.TEXT_WARNING)))
                else:
                    item.setForeground(0, QBrush(get_qcolor(ThemeKey.TEXT_PRIMARY)))
                    item.setForeground(1, QBrush(get_qcolor(ThemeKey.TEXT_PRIMARY)))
            except Exception:
                pass

        dataset_id = str(self._context.get("dataset_id") or "")
        dataset_path = str(self._context.get("dataset_json_path") or "")
        dataset_exists = bool(self._context.get("dataset_json_exists"))
        group_id = str(self._context.get("group_id") or "")

        combo_entries = self._context.get("combo_entries")
        combo_entries = combo_entries if isinstance(combo_entries, list) else []
        selected_user_ids = {str(e.get("user_id") or "") for e in combo_entries if isinstance(e, dict)}

        root_ds = QTreeWidgetItem(["datasets/<id>.json", dataset_path])
        _set_item_state(root_ds, kind="error" if not dataset_exists and dataset_path else "normal")
        tree.addTopLevelItem(root_ds)
        QTreeWidgetItem(root_ds, ["存在", "OK" if dataset_exists else "NOT FOUND"])
        QTreeWidgetItem(root_ds, ["参照キー", "data.relationships.group.data.id"])
        QTreeWidgetItem(root_ds, ["抽出 group_id", group_id])
        QTreeWidgetItem(root_ds, ["備考", "Dataset ID: " + dataset_id])
        root_ds.setExpanded(True)

        # group member resolution
        members_debug = self._context.get("members_debug")
        members_debug = members_debug if isinstance(members_debug, dict) else {}

        root_members = QTreeWidgetItem(["サブグループメンバー解決", "load_group_members_*" ])
        tree.addTopLevelItem(root_members)
        QTreeWidgetItem(root_members, ["対象 group_id", str(members_debug.get("group_id") or group_id)])

        steps = members_debug.get("steps")
        steps = steps if isinstance(steps, list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_name = str(step.get("step") or "")
            step_item = QTreeWidgetItem([step_name, ""])
            root_members.addChild(step_item)

            if "error" in step:
                QTreeWidgetItem(step_item, ["error", str(step.get("error") or "")])
                _set_item_state(step_item, kind="error")

            reads = step.get("reads")
            if isinstance(reads, list) and reads:
                reads_item = QTreeWidgetItem(["reads", ""])
                step_item.addChild(reads_item)
                for r in reads:
                    QTreeWidgetItem(reads_item, ["-", str(r)])

            candidates = step.get("candidates")
            if isinstance(candidates, list) and candidates:
                c_item = QTreeWidgetItem(["candidates", ""])
                step_item.addChild(c_item)
                for p in candidates:
                    QTreeWidgetItem(c_item, ["-", str(p)])

            used_path = step.get("used_path")
            if used_path:
                up = QTreeWidgetItem(["used_path", str(used_path)])
                step_item.addChild(up)
                _set_item_state(up, kind="selected")

            # API attempts
            attempts = step.get("attempts")
            if isinstance(attempts, list) and attempts:
                a_root = QTreeWidgetItem(["attempts", str(len(attempts))])
                step_item.addChild(a_root)
                for a in attempts:
                    if not isinstance(a, dict):
                        continue
                    url = str(a.get("url") or "")
                    status = a.get("status")
                    err = a.get("error")
                    cnt = a.get("user_count")
                    a_item = QTreeWidgetItem(["url", url])
                    a_root.addChild(a_item)
                    QTreeWidgetItem(a_item, ["status", "" if status is None else str(status)])
                    QTreeWidgetItem(a_item, ["user_count", "" if cnt is None else str(cnt)])
                    if err:
                        QTreeWidgetItem(a_item, ["error", str(err)])
                        _set_item_state(a_item, kind="warning")

        # combo entries
        root_combo = QTreeWidgetItem(["コンボ反映（データ所有者候補）", str(len(combo_entries))])
        tree.addTopLevelItem(root_combo)
        for e in combo_entries:
            if not isinstance(e, dict):
                continue
            uid = str(e.get("user_id") or "")
            text = str(e.get("text") or "")
            item = QTreeWidgetItem([uid or "(no id)", text])
            root_combo.addChild(item)
            _set_item_state(item, kind="selected" if uid and uid in selected_user_ids else "normal")

        # preview (members)
        members_preview = self._context.get("members_preview")
        members_preview = members_preview if isinstance(members_preview, list) else []
        root_preview = QTreeWidgetItem(["members_preview", str(len(members_preview))])
        tree.addTopLevelItem(root_preview)
        for m in members_preview:
            if not isinstance(m, dict):
                continue
            uid = str(m.get("id") or "")
            uname = str(m.get("userName") or "")
            org = str(m.get("organizationName") or "")
            line = f"{uname} ({org})" if org else uname
            item = QTreeWidgetItem([uid, line])
            root_preview.addChild(item)
            _set_item_state(item, kind="selected" if uid and uid in selected_user_ids else "normal")

        root_members.setExpanded(True)
        root_combo.setExpanded(True)

        layout.addWidget(tree)
        self._trace_tree = tree
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
