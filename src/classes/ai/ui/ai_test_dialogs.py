"""
AI テスト機能のダイアログクラス - ARIM RDE Tool
ui_ai_test.py から分離したダイアログ専用モジュール
"""
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QDialogButtonBox, QMessageBox
)
from qt_compat.core import Qt
import os
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color


class PromptTemplateEditorDialog(QDialog):
    """プロンプトテンプレート編集ダイアログ"""
    
    def __init__(self, parent, method_name, prompt_file, current_template, default_template):
        super().__init__(parent)
        self.method_name = method_name
        self.prompt_file = prompt_file
        self.current_template = current_template
        self.default_template = default_template
        self.setup_ui()
        
    def setup_ui(self):
        """UIセットアップ"""
        self.setWindowTitle(f"プロンプトテンプレート編集 - {self.method_name}")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        
        # 説明ラベル
        info_label = QLabel(f"分析方法「{self.method_name}」のプロンプトテンプレートを編集します。")
        info_label.setStyleSheet(f"font-weight: bold; margin-bottom: 10px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        layout.addWidget(info_label)
        
        # ファイル名表示
        file_label = QLabel(f"ファイル: {self.prompt_file}")
        file_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin-bottom: 15px;")
        layout.addWidget(file_label)
        
        # テンプレート編集エリア
        template_label = QLabel("プロンプトテンプレート:")
        template_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(template_label)
        
        self.template_edit = QTextEdit()
        self.template_edit.setPlainText(self.current_template)
        self.template_edit.setStyleSheet(
            f"""
            QTextEdit {{
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
                line-height: 1.4;
            }}
            QTextEdit:focus {{
                border-color: {get_color(ThemeKey.INPUT_BORDER_FOCUS)};
            }}
            """
        )
        layout.addWidget(self.template_edit)
        
        # 変数説明
        variables_label = QLabel("利用可能な変数:")
        variables_label.setStyleSheet("font-weight: bold; margin-top: 15px; margin-bottom: 5px;")
        layout.addWidget(variables_label)
        
        variables_info = QLabel(
            "• {experiment_data} - 実験データ\n"
            "• {material_index} - マテリアルインデックス情報\n"
            "• {static_data} - 静的データファイルの内容\n"
            "• {prepared_data} - ARIM拡張データ"
        )
        variables_info.setStyleSheet(
            f"color: {get_color(ThemeKey.PANEL_NEUTRAL_TEXT)}; "
            f"background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)}; "
            f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; "
            "border-radius: 4px; padding: 8px; margin-bottom: 15px;"
        )
        layout.addWidget(variables_info)
        
        # ボタン群
        button_layout = QHBoxLayout()
        
        # デフォルト復元ボタン
        restore_button = QPushButton("デフォルトに復元")
        restore_button.setProperty("variant", "warning")
        restore_button.setStyleSheet("padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        restore_button.clicked.connect(self.restore_default)
        button_layout.addWidget(restore_button)
        
        button_layout.addStretch()
        
        # キャンセル/保存ボタン
        button_box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        button_box.button(QDialogButtonBox.Cancel).setText("キャンセル")
        button_box.button(QDialogButtonBox.Save).setText("保存")
        button_box.accepted.connect(self.save_template)
        button_box.rejected.connect(self.reject)
        
        # ボタンスタイル
        for button in [button_box.button(QDialogButtonBox.Cancel), button_box.button(QDialogButtonBox.Save)]:
            button.setStyleSheet("padding: 8px 16px; border-radius: 4px; font-weight: bold; min-width: 80px;")
        
        # バリアントで色制御
        cancel_btn = button_box.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setProperty("variant", "secondary")
        
        save_btn = button_box.button(QDialogButtonBox.Save)
        if save_btn:
            save_btn.setProperty("variant", "success")
        
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def restore_default(self):
        """デフォルトテンプレートに復元"""
        reply = QMessageBox.question(
            self, "デフォルト復元確認",
            "現在の内容を破棄してデフォルトテンプレートに復元しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.template_edit.setPlainText(self.default_template)
    
    def save_template(self):
        """テンプレートを保存"""
        try:
            from config.common import get_dynamic_file_path
            import os
            
            template_content = self.template_edit.toPlainText()
            
            # プロンプトテンプレートファイルのパス
            template_path = get_dynamic_file_path(f'input/ai/prompts/{self.prompt_file}')
            
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(template_path), exist_ok=True)
            
            # ファイルに保存
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(template_content)
            
            # 親ウィジェット（AITestWidget）にキャッシュクリアを通知
            if hasattr(self.parent(), 'clear_template_cache'):
                self.parent().clear_template_cache(self.prompt_file)
            
            QMessageBox.information(
                self, "保存完了",
                f"プロンプトテンプレートを保存しました。\n\nファイル: {template_path}\n\n変更は次回の分析実行時から反映されます。"
            )
            
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self, "保存エラー",
                f"プロンプトテンプレートの保存に失敗しました。\n\nエラー: {e}"
            )
    
    def get_template_content(self):
        """編集されたテンプレート内容を取得"""
        return self.template_edit.toPlainText()
