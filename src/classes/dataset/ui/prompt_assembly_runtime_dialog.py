"""Runtime selector for prompt assembly mode."""

from __future__ import annotations

import os

from typing import Optional

from qt_compat.widgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from classes.ai.util.prompt_assembly import detect_prompt_assembly_sources, get_prompt_assembly_source_catalog


PROMPT_ASSEMBLY_RUNTIME_DEFAULT = "default"
PROMPT_ASSEMBLY_RUNTIME_FULL = "full_embed"
PROMPT_ASSEMBLY_RUNTIME_FILTERED = "filtered_embed"


class PromptAssemblyRuntimeDialog(QDialog):
    """Ask the user how embedded prompt sources should be assembled at runtime."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        button_label: str = "AI機能",
        template_text: str = "",
        button_config: Optional[dict] = None,
        target_label: str = "データセット",
    ):
        super().__init__(parent)
        self._button_config = dict(button_config or {})
        self._button_label = str(button_label or "AI機能")
        self._template_text = str(template_text or "")
        self._target_label = str(target_label or "データセット")
        self._detected_sources = detect_prompt_assembly_sources(self._template_text)
        self._source_catalog = get_prompt_assembly_source_catalog()

        self.setModal(True)
        self.setWindowTitle(f"{self._button_label}: 埋め込み方式の選択")
        self.resize(620, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            f"{self._target_label}向けの「{self._button_label}」を実行します。\n"
            "プロンプト内の大型埋め込みデータを、どの方式で組み立てるか選択してください。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("組み立て方式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("デフォルト（テンプレート設定を使用）", PROMPT_ASSEMBLY_RUNTIME_DEFAULT)
        self.mode_combo.addItem("全文埋め込み", PROMPT_ASSEMBLY_RUNTIME_FULL)
        self.mode_combo.addItem("候補限定埋め込み", PROMPT_ASSEMBLY_RUNTIME_FILTERED)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        layout.addWidget(QLabel("埋め込み対象"))

        self.targets_view = QPlainTextEdit()
        self.targets_view.setReadOnly(True)
        self.targets_view.setPlainText(self._build_targets_text())
        layout.addWidget(self.targets_view, 1)

        note = QLabel("デフォルトを選ぶと、テンプレート定義の既定方式と対象別設定をそのまま使います。")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_button = QPushButton("実行")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    def _build_targets_text(self) -> str:
        if not self._detected_sources:
            return "このテンプレートでは、切り替え対象となる大型埋め込みプレースホルダは検出されませんでした。"

        default_mode = (self._button_config.get("prompt_assembly_mode") or PROMPT_ASSEMBLY_RUNTIME_FULL).strip() or PROMPT_ASSEMBLY_RUNTIME_FULL
        source_overrides = self._button_config.get("prompt_assembly_sources") or {}
        lines = []
        for placeholder in self._detected_sources:
            metadata = self._source_catalog.get(placeholder, {})
            label = metadata.get("label", placeholder)
            source_mode = (source_overrides.get(placeholder) or {}).get("mode") or default_mode
            mode_label = "候補限定埋め込み" if source_mode == PROMPT_ASSEMBLY_RUNTIME_FILTERED else "全文埋め込み"
            lines.append(f"- {label} ({placeholder})")
            lines.append(f"  既定: {mode_label}")
            method = str(metadata.get("method") or "").strip()
            if method:
                lines.append(f"  内容: {method}")
        return "\n".join(lines)

    def get_prompt_assembly_override(self) -> Optional[dict]:
        selected_mode = self.mode_combo.currentData()
        if selected_mode not in {PROMPT_ASSEMBLY_RUNTIME_FULL, PROMPT_ASSEMBLY_RUNTIME_FILTERED}:
            return None

        return {
            "mode": selected_mode,
            "sources": {
                placeholder: {"mode": selected_mode}
                for placeholder in self._detected_sources
            },
        }


def request_prompt_assembly_override(
    parent: Optional[QWidget] = None,
    *,
    button_label: str = "AI機能",
    template_text: str = "",
    button_config: Optional[dict] = None,
    target_label: str = "データセット",
) -> tuple[bool, Optional[dict]]:
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("RDE_TEST_SHOW_PROMPT_ASSEMBLY_DIALOG", "") != "1":
        return True, None

    dialog = PromptAssemblyRuntimeDialog(
        parent,
        button_label=button_label,
        template_text=template_text,
        button_config=button_config,
        target_label=target_label,
    )
    if dialog.exec() != QDialog.Accepted:
        return False, None
    return True, dialog.get_prompt_assembly_override()