"""Dialog for managing AI extension button definitions."""

from __future__ import annotations

from typing import Optional

from qt_compat.widgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QCheckBox,
)
from qt_compat.core import Qt, Signal

from classes.dataset.util.ai_extension_config_manager import AIExtensionConfigManager
from classes.dataset.util.ai_extension_helper import infer_ai_suggest_target_kind
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color


class AIExtensionConfigDialog(QDialog):
    """UI to add/remove/reorder AI extension definition buttons."""

    config_saved = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("AIサジェスト機能定義の管理")
        # できるだけスクロールバーが不要になるよう、少し大きめに確保
        self.resize(1100, 720)
        self.setModal(True)

        self._manager = AIExtensionConfigManager()
        self._locked_ids = {btn.get('id') for btn in self._manager.buttons if not btn.get('allow_delete', False)}
        self._current_index: int = -1
        self._is_loading_form = False
        # 設定キーが未存在でも従来のデフォルトを維持
        self._dataset_desc_prompt_button_id = (
            self._manager.get_dataset_description_ai_proposal_prompt_button_id() or "json_explain_dataset_basic"
        )
        self._quick_ai_prompt_button_id = self._manager.get_dataset_quick_ai_prompt_button_id() or ""
        if not self._quick_ai_prompt_button_id:
            if self._manager.find_by_id("dataset_explanation_quick") is not None:
                self._quick_ai_prompt_button_id = "dataset_explanation_quick"

        self._ai_check_prompt_button_id = self._manager.get_dataset_ai_check_prompt_button_id() or ""
        if not self._ai_check_prompt_button_id:
            if self._manager.find_by_id("json_check_dataset_summary_simple_quality") is not None:
                self._ai_check_prompt_button_id = "json_check_dataset_summary_simple_quality"

        self._build_ui()
        self._refresh_button_list(select_index=0)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            "AIサジェストボタンの定義を追加・削除・並び替えできます。\n"
            "🔒 マークの付いたボタンはアプリの他機能で使用中のため削除できません。"
        )
        header.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
        )
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Left: button list + controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)

        self.button_list = QListWidget()
        self.button_list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.button_list, 1)

        controls_layout = QHBoxLayout()
        self.add_button = QPushButton("追加")
        self.add_button.clicked.connect(self._on_add_button)
        self.delete_button = QPushButton("削除")
        self.delete_button.clicked.connect(self._on_delete_button)
        self.move_up_button = QPushButton("↑ 上へ")
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button = QPushButton("↓ 下へ")
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))

        controls_layout.addWidget(self.add_button)
        controls_layout.addWidget(self.delete_button)
        controls_layout.addWidget(self.move_up_button)
        controls_layout.addWidget(self.move_down_button)
        left_layout.addLayout(controls_layout)

        splitter.addWidget(left_panel)

        # Right: detail editor
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.id_edit = QLineEdit()
        form.addRow("ID", self.id_edit)

        self.label_edit = QLineEdit()
        form.addRow("表示ラベル", self.label_edit)

        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("例: 🤖")
        form.addRow("アイコン", self.icon_edit)

        self.category_edit = QLineEdit()
        form.addRow("カテゴリ", self.category_edit)

        self.prompt_file_edit = QLineEdit()
        form.addRow("プロンプトファイル", self.prompt_file_edit)

        self.target_kind_combo = QComboBox()
        self.target_kind_combo.addItem("データセット", "dataset")
        self.target_kind_combo.addItem("報告書", "report")
        form.addRow("対象", self.target_kind_combo)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["text", "json"])
        form.addRow("出力形式", self.output_format_combo)

        self.dataset_desc_prompt_checkbox = QCheckBox("「データセット説明 AI提案」のプロンプトテンプレートとして使用")
        self.dataset_desc_prompt_checkbox.setToolTip(
            "AI説明文提案（AI提案タブ）で使用するプロンプトを、このボタンのプロンプトに切り替えます。\n"
            "選択できるのは1つだけで、最後にチェックしたものが優先されます。\n"
            "※ 出力形式が json のボタンのみ推奨です。"
        )
        self.dataset_desc_prompt_checkbox.toggled.connect(self._on_dataset_desc_prompt_toggled)
        form.addRow("データセット説明AI提案", self.dataset_desc_prompt_checkbox)

        self.quick_ai_prompt_checkbox = QCheckBox("「⚡ Quick AI」のプロンプトテンプレートとして使用")
        self.quick_ai_prompt_checkbox.setToolTip(
            "⚡ Quick AI で使用するプロンプトを、このボタンのプロンプトに切り替えます。\n"
            "選択できるのは1つだけで、最後にチェックしたものが優先されます。"
        )
        self.quick_ai_prompt_checkbox.toggled.connect(self._on_quick_ai_prompt_toggled)
        form.addRow("⚡ Quick AI", self.quick_ai_prompt_checkbox)

        self.ai_check_prompt_checkbox = QCheckBox("「📋 AI CHECK」のプロンプトテンプレートとして使用")
        self.ai_check_prompt_checkbox.setToolTip(
            "📋 AI CHECK で使用するプロンプトを、このボタンのプロンプトに切り替えます。\n"
            "選択できるのは1つだけで、最後にチェックしたものが優先されます。\n"
            "※ JSON出力のプロンプトが推奨です（スコア等の表示が安定します）。"
        )
        self.ai_check_prompt_checkbox.toggled.connect(self._on_ai_check_prompt_toggled)
        form.addRow("📋 AI CHECK", self.ai_check_prompt_checkbox)

        self.allow_delete_checkbox = QCheckBox("このボタンの削除を許可する")
        form.addRow("削除許可", self.allow_delete_checkbox)

        right_layout.addLayout(form)

        desc_label = QLabel("説明")
        desc_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        right_layout.addWidget(desc_label)
        self.description_edit = QTextEdit()
        self.description_edit.setFixedHeight(80)
        right_layout.addWidget(self.description_edit)

        template_label = QLabel("インラインテンプレート (任意)")
        template_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        right_layout.addWidget(template_label)
        self.prompt_template_edit = QTextEdit()
        self.prompt_template_edit.setPlaceholderText("ファイルではなくインラインでプロンプトを定義する場合に使用")
        right_layout.addWidget(self.prompt_template_edit, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # Footer buttons
        footer = QHBoxLayout()
        footer.addStretch()
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self._on_save)
        self.cancel_button = QPushButton("閉じる")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)
        layout.addLayout(footer)

        self._apply_button_theme(self.add_button, ThemeKey.BUTTON_PRIMARY_BACKGROUND)
        self._apply_button_theme(self.delete_button, ThemeKey.BUTTON_DANGER_BACKGROUND)
        self._apply_button_theme(self.move_up_button, ThemeKey.BUTTON_NEUTRAL_BACKGROUND)
        self._apply_button_theme(self.move_down_button, ThemeKey.BUTTON_NEUTRAL_BACKGROUND)
        self._apply_button_theme(self.save_button, ThemeKey.BUTTON_SUCCESS_BACKGROUND)
        self._apply_button_theme(self.cancel_button, ThemeKey.BUTTON_NEUTRAL_BACKGROUND)

    # ------------------------------------------------------------------
    # Data binding helpers
    # ------------------------------------------------------------------
    def _refresh_button_list(self, select_index: Optional[int] = None) -> None:
        self.button_list.clear()
        for button in self._manager.buttons:
            locked_prefix = '🔒 ' if not button.get('allow_delete', False) else ''
            selected_prefix = '★ ' if button.get('id') == self._dataset_desc_prompt_button_id else ''
            quick_prefix = '⚡ ' if button.get('id') == self._quick_ai_prompt_button_id else ''
            check_prefix = '📋 ' if button.get('id') == self._ai_check_prompt_button_id else ''
            icon = button.get('icon', '') or ''
            label = button.get('label', '(ラベル未設定)')

            target_kind = infer_ai_suggest_target_kind(button)
            target_tag = '［報告書］' if target_kind == 'report' else '［AI拡張］'
            item = QListWidgetItem(
                f"{selected_prefix}{quick_prefix}{check_prefix}{locked_prefix}{target_tag} {icon} {label} ({button.get('id', '???')})"
            )
            self.button_list.addItem(item)
        if self._manager.buttons:
            index = select_index if select_index is not None else min(self._current_index, len(self._manager.buttons) - 1)
            index = max(0, index)
            self.button_list.setCurrentRow(index)
        else:
            self._current_index = -1
            self._clear_form()
        self._update_button_controls()

    def _on_selection_changed(self, index: int) -> None:
        if self._is_loading_form:
            return
        self._save_current_button()
        self._current_index = index
        self._load_form(index)
        self._update_button_controls()

    def _load_form(self, index: int) -> None:
        self._is_loading_form = True
        try:
            if index < 0 or index >= len(self._manager.buttons):
                self._clear_form()
                return
            button = self._manager.buttons[index]
            self.id_edit.setText(button.get('id', ''))
            self.label_edit.setText(button.get('label', ''))
            self.icon_edit.setText(button.get('icon', ''))
            self.category_edit.setText(button.get('category', ''))
            self.prompt_file_edit.setText(button.get('prompt_file', ''))

            target_kind = infer_ai_suggest_target_kind(button)
            idx = self.target_kind_combo.findData(target_kind)
            if idx >= 0:
                self.target_kind_combo.setCurrentIndex(idx)
            else:
                self.target_kind_combo.setCurrentIndex(0)
            current_format = button.get('output_format', 'text')
            if self.output_format_combo.findText(current_format) == -1:
                self.output_format_combo.addItem(current_format)
            self.output_format_combo.setCurrentText(current_format)
            self.description_edit.setText(button.get('description', ''))
            self.prompt_template_edit.setText(button.get('prompt_template', ''))
            deletable = button.get('allow_delete', False)
            locked = button.get('id') in self._locked_ids
            self.allow_delete_checkbox.setChecked(deletable)
            self.allow_delete_checkbox.setEnabled(not locked)
            self.id_edit.setEnabled(not locked)

            # データセット説明AI提案のプロンプト指定
            button_id = button.get('id', '')
            is_selected = bool(button_id) and button_id == self._dataset_desc_prompt_button_id
            self.dataset_desc_prompt_checkbox.blockSignals(True)
            self.dataset_desc_prompt_checkbox.setChecked(is_selected)
            self.dataset_desc_prompt_checkbox.blockSignals(False)
            # json推奨: 明示的にjson以外は警告し、チェック操作時に弾く
            self.dataset_desc_prompt_checkbox.setEnabled(True)

            # QUICK AI のプロンプト指定
            is_quick_selected = bool(button_id) and button_id == self._quick_ai_prompt_button_id
            self.quick_ai_prompt_checkbox.blockSignals(True)
            self.quick_ai_prompt_checkbox.setChecked(is_quick_selected)
            self.quick_ai_prompt_checkbox.blockSignals(False)
            self.quick_ai_prompt_checkbox.setEnabled(True)

            # AI CHECK のプロンプト指定
            is_check_selected = bool(button_id) and button_id == self._ai_check_prompt_button_id
            self.ai_check_prompt_checkbox.blockSignals(True)
            self.ai_check_prompt_checkbox.setChecked(is_check_selected)
            self.ai_check_prompt_checkbox.blockSignals(False)
            self.ai_check_prompt_checkbox.setEnabled(True)
        finally:
            self._is_loading_form = False

    def _clear_form(self) -> None:
        self.id_edit.clear()
        self.label_edit.clear()
        self.icon_edit.clear()
        self.category_edit.clear()
        self.prompt_file_edit.clear()
        self.description_edit.clear()
        self.prompt_template_edit.clear()
        self.output_format_combo.setCurrentText("text")
        self.target_kind_combo.setCurrentIndex(0)
        self.allow_delete_checkbox.setChecked(False)
        self.allow_delete_checkbox.setEnabled(False)
        self.id_edit.setEnabled(False)
        if hasattr(self, 'dataset_desc_prompt_checkbox'):
            self.dataset_desc_prompt_checkbox.blockSignals(True)
            self.dataset_desc_prompt_checkbox.setChecked(False)
            self.dataset_desc_prompt_checkbox.blockSignals(False)
            self.dataset_desc_prompt_checkbox.setEnabled(False)
        if hasattr(self, 'quick_ai_prompt_checkbox'):
            self.quick_ai_prompt_checkbox.blockSignals(True)
            self.quick_ai_prompt_checkbox.setChecked(False)
            self.quick_ai_prompt_checkbox.blockSignals(False)
            self.quick_ai_prompt_checkbox.setEnabled(False)
        if hasattr(self, 'ai_check_prompt_checkbox'):
            self.ai_check_prompt_checkbox.blockSignals(True)
            self.ai_check_prompt_checkbox.setChecked(False)
            self.ai_check_prompt_checkbox.blockSignals(False)
            self.ai_check_prompt_checkbox.setEnabled(False)

    def _save_current_button(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._manager.buttons):
            return
        button = self._manager.buttons[self._current_index]
        locked = button.get('id') in self._locked_ids
        if not locked:
            new_id = self.id_edit.text().strip()
            if new_id and new_id != button.get('id'):
                if self._manager.find_by_id(new_id) is not None:
                    QMessageBox.warning(self, "警告", "同じIDが既に存在します。IDは変更されません。")
                else:
                    button['id'] = new_id
        button['label'] = self.label_edit.text().strip()
        button['icon'] = self.icon_edit.text().strip() or '🤖'
        button['category'] = self.category_edit.text().strip()
        button['prompt_file'] = self.prompt_file_edit.text().strip()
        button['target_kind'] = self.target_kind_combo.currentData() or infer_ai_suggest_target_kind(button)
        button['output_format'] = self.output_format_combo.currentText()
        button['description'] = self.description_edit.toPlainText().strip()
        button['prompt_template'] = self.prompt_template_edit.toPlainText().strip()
        if not locked:
            button['allow_delete'] = self.allow_delete_checkbox.isChecked()
        else:
            button['allow_delete'] = False

        # データセット説明AI提案のプロンプト指定は、選択されたボタンIDとして別キーで管理する
        # （ボタン定義自体にフラグを埋め込まない: 1つのみ・最後指定優先を確実にするため）
        try:
            button_id = button.get('id', '')
            if button_id and self.dataset_desc_prompt_checkbox.isChecked():
                self._dataset_desc_prompt_button_id = button_id
        except Exception:
            pass

        # QUICK AI のプロンプト指定
        try:
            button_id = button.get('id', '')
            if button_id and self.quick_ai_prompt_checkbox.isChecked():
                self._quick_ai_prompt_button_id = button_id
        except Exception:
            pass

        # AI CHECK のプロンプト指定
        try:
            button_id = button.get('id', '')
            if button_id and self.ai_check_prompt_checkbox.isChecked():
                self._ai_check_prompt_button_id = button_id
        except Exception:
            pass

    def _on_dataset_desc_prompt_toggled(self, checked: bool) -> None:
        if self._is_loading_form:
            return
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        button_id = (button.get('id') or '').strip()
        if not button_id:
            return
        # dataset説明AI提案はJSON前提のため、json以外は弾く（誤設定防止）
        fmt = (self.output_format_combo.currentText() or '').strip().lower()
        if checked and fmt != 'json':
            QMessageBox.warning(self, "警告", "データセット説明AI提案はJSON応答を前提とします。出力形式を 'json' にしてください。")
            self.dataset_desc_prompt_checkbox.blockSignals(True)
            self.dataset_desc_prompt_checkbox.setChecked(False)
            self.dataset_desc_prompt_checkbox.blockSignals(False)
            return

        if checked:
            # 最後に指定したものが優先（= これを選択）
            self._dataset_desc_prompt_button_id = button_id
        else:
            if self._dataset_desc_prompt_button_id == button_id:
                self._dataset_desc_prompt_button_id = ""

        # リストの★表示を更新
        self._refresh_button_list(select_index=self._current_index)

    def _on_quick_ai_prompt_toggled(self, checked: bool) -> None:
        if self._is_loading_form:
            return
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        button_id = (button.get('id') or '').strip()
        if not button_id:
            return

        if checked:
            self._quick_ai_prompt_button_id = button_id
        else:
            if self._quick_ai_prompt_button_id == button_id:
                self._quick_ai_prompt_button_id = ""

        self._refresh_button_list(select_index=self._current_index)

    def _on_ai_check_prompt_toggled(self, checked: bool) -> None:
        if self._is_loading_form:
            return
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        button_id = (button.get('id') or '').strip()
        if not button_id:
            return

        if checked:
            self._ai_check_prompt_button_id = button_id
        else:
            if self._ai_check_prompt_button_id == button_id:
                self._ai_check_prompt_button_id = ""

        self._refresh_button_list(select_index=self._current_index)

    def _update_button_controls(self) -> None:
        has_selection = 0 <= self._current_index < len(self._manager.buttons)
        self.delete_button.setEnabled(has_selection and self._manager.can_delete(self._current_index))
        self.move_up_button.setEnabled(has_selection and self._current_index > 0)
        self.move_down_button.setEnabled(has_selection and has_selection and self._current_index < len(self._manager.buttons) - 1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_add_button(self) -> None:
        from qt_compat.widgets import QInputDialog

        self._save_current_button()
        button_id, ok = QInputDialog.getText(self, "AIサジェストボタンの追加", "新しいボタンのIDを入力してください")
        if not ok or not button_id.strip():
            return
        try:
            index = self._manager.add_button(button_id.strip())
            self._refresh_button_list(select_index=index)
        except ValueError as exc:
            QMessageBox.warning(self, "警告", str(exc))

    def _on_delete_button(self) -> None:
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        if not button.get('allow_delete', False):
            QMessageBox.information(self, "情報", "このボタンは削除できません。")
            return
        reply = QMessageBox.question(
            self,
            "確認",
            f"'{button.get('label', button.get('id'))}' を削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._manager.remove_button(self._current_index)
            self._current_index = min(self._current_index, len(self._manager.buttons) - 1)
            self._refresh_button_list(select_index=self._current_index)
        except ValueError as exc:
            QMessageBox.warning(self, "警告", str(exc))

    def _move_selected(self, offset: int) -> None:
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        new_index = self._current_index + offset
        if self._manager.move_button(self._current_index, new_index):
            self._current_index = new_index
            self._refresh_button_list(select_index=new_index)

    def _on_save(self) -> None:
        self._save_current_button()
        self._manager.set_dataset_description_ai_proposal_prompt_button_id(
            self._dataset_desc_prompt_button_id or None
        )
        self._manager.set_dataset_quick_ai_prompt_button_id(
            self._quick_ai_prompt_button_id or None
        )
        self._manager.set_dataset_ai_check_prompt_button_id(
            self._ai_check_prompt_button_id or None
        )
        success = self._manager.save()
        if success:
            QMessageBox.information(self, "保存完了", "AIサジェスト定義を保存しました。")
            self.config_saved.emit()
            self.accept()
        else:
            QMessageBox.critical(self, "エラー", "設定の保存に失敗しました。ログを確認してください。")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _apply_button_theme(self, button: QPushButton, bg_key: ThemeKey) -> None:
        button.setStyleSheet(
            f"QPushButton {{ background-color: {get_color(bg_key)}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};"
            f" border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 4px; padding: 6px 10px; }}"
            f"QPushButton:disabled {{ background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};"
            f" color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; }}"
        )
