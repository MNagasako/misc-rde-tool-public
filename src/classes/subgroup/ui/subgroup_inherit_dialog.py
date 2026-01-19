import logging
from typing import Any, Dict, List

from qt_compat.widgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


logger = logging.getLogger(__name__)


GRANT_NUMBER_NOT_INHERITED_MESSAGE = "課題番号は引き継がないため設定してください"


def build_subjects_with_grant_number_placeholder(
    subjects: Any,
    placeholder: str = GRANT_NUMBER_NOT_INHERITED_MESSAGE,
) -> List[Dict[str, Any]]:
    if not isinstance(subjects, list):
        return []

    result: List[Dict[str, Any]] = []
    for s in subjects:
        if not isinstance(s, dict):
            continue
        copied = dict(s)
        copied["grantNumber"] = placeholder
        result.append(copied)
    return result


class SubgroupInheritDialog(QDialog):
    """既存サブグループから新規作成フォームへ値を引き継ぐ項目を選択するダイアログ。"""

    def __init__(self, parent, group_data: Dict[str, Any]):
        super().__init__(parent)
        self._group = group_data or {}

        self.setWindowTitle("既存サブグループ読込")

        layout = QVBoxLayout()

        header = QLabel("既存サブグループの内容をフォームに引き継ぎます。\n引き継ぐ項目を選択してください。")
        header.setWordWrap(True)
        layout.addWidget(header)

        self.cb_members = QCheckBox("メンバーリスト")
        self.cb_group_name = QCheckBox("グループ名")
        self.cb_description = QCheckBox("説明")
        self.cb_subjects = QCheckBox("課題")
        self.cb_funds = QCheckBox("研究資金")

        # デフォルト: 課題・研究資金以外をON
        self.cb_members.setChecked(True)
        self.cb_group_name.setChecked(True)
        self.cb_description.setChecked(True)
        self.cb_subjects.setChecked(False)
        self.cb_funds.setChecked(False)

        layout.addWidget(self.cb_members)
        layout.addWidget(self.cb_group_name)
        layout.addWidget(self.cb_description)
        layout.addWidget(self.cb_subjects)
        layout.addWidget(self.cb_funds)

        note = QLabel(f"※課題番号は引き継ぎません。'{GRANT_NUMBER_NOT_INHERITED_MESSAGE}' を設定します。")
        note.setWordWrap(True)
        layout.addWidget(note)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMinimumHeight(220)
        preview.setText(self._build_preview_text())
        layout.addWidget(preview)

        button_row = QHBoxLayout()
        button_row.addStretch()

        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("キャンセル")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)

        layout.addLayout(button_row)
        self.setLayout(layout)

    def selected_options(self) -> Dict[str, bool]:
        return {
            "members": bool(self.cb_members.isChecked()),
            "group_name": bool(self.cb_group_name.isChecked()),
            "description": bool(self.cb_description.isChecked()),
            "subjects": bool(self.cb_subjects.isChecked()),
            "funds": bool(self.cb_funds.isChecked()),
        }

    def _build_preview_text(self) -> str:
        try:
            name = (self._group or {}).get("name", "")
            desc = (self._group or {}).get("description", "")
            gid = (self._group or {}).get("id", "")

            parts: List[str] = []
            parts.append(f"ID: {gid}")
            parts.append(f"グループ名: {name}")
            parts.append(f"説明: {desc}")

            members = (self._group or {}).get("members", [])
            parts.append("")
            parts.append("メンバー:")
            if isinstance(members, list) and members:
                for m in members:
                    if not isinstance(m, dict):
                        continue
                    parts.append(
                        f"- {m.get('name','')} <{m.get('email','')}> ({m.get('role','')})"
                    )
            else:
                parts.append("- (なし)")

            subjects = (self._group or {}).get("subjects", [])
            parts.append("")
            parts.append("課題:")
            if isinstance(subjects, list) and subjects:
                for s in subjects:
                    if not isinstance(s, dict):
                        continue
                    parts.append(f"- {s.get('grantNumber','')} / {s.get('title','')}")
            else:
                parts.append("- (なし)")

            funds = (self._group or {}).get("funds", [])
            parts.append("")
            parts.append("研究資金:")
            if isinstance(funds, list) and funds:
                for f in funds:
                    if isinstance(f, dict):
                        parts.append(f"- {f.get('fundNumber','')}")
                    else:
                        parts.append(f"- {str(f)}")
            else:
                parts.append("- (なし)")

            return "\n".join(parts)
        except Exception as exc:
            logger.debug("preview build failed", exc_info=True)
            return f"(プレビュー生成に失敗しました: {exc})"
