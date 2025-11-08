"""
AI拡張プロンプト編集ダイアログ
プロンプトファイルの編集とテンプレート変数の管理を行う
"""

import os
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QMessageBox, QTabWidget, QWidget, QGroupBox,
    QLineEdit, QFormLayout, QScrollArea, QListWidget, QListWidgetItem
)
from qt_compat.core import Qt, Signal
from classes.dataset.util.ai_extension_helper import load_prompt_file, save_prompt_file


class AIExtensionPromptEditDialog(QDialog):
    """AI拡張プロンプト編集ダイアログ"""
    
    prompt_updated = Signal(str)  # プロンプト更新シグナル
    
    def __init__(self, parent=None, prompt_file_path="", button_config=None):
        super().__init__(parent)
        self.prompt_file_path = prompt_file_path
        self.button_config = button_config or {}
        self.original_content = ""
        
        self.setup_ui()
        self.load_prompt_content()
        
    def setup_ui(self):
        """UI要素のセットアップ"""
        self.setWindowTitle("AI拡張プロンプト編集")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # ヘッダー情報
        header_layout = QVBoxLayout()
        
        button_label = self.button_config.get('label', 'Unknown')
        description = self.button_config.get('description', '')
        
        title_label = QLabel(f"プロンプト編集: {button_label}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        header_layout.addWidget(title_label)
        
        if description:
            desc_label = QLabel(f"説明: {description}")
            desc_label.setStyleSheet("color: #666; margin: 5px 10px;")
            header_layout.addWidget(desc_label)
        
        file_label = QLabel(f"ファイル: {self.prompt_file_path}")
        file_label.setStyleSheet("font-family: 'Consolas'; color: #888; margin: 5px 10px;")
        header_layout.addWidget(file_label)
        
        layout.addLayout(header_layout)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # プロンプト編集タブ
        edit_tab = QWidget()
        self.tab_widget.addTab(edit_tab, "プロンプト編集")
        self.setup_edit_tab(edit_tab)
        
        # テンプレート変数タブ
        variables_tab = QWidget()
        self.tab_widget.addTab(variables_tab, "テンプレート変数")
        self.setup_variables_tab(variables_tab)
        
        # プレビュータブ
        preview_tab = QWidget()
        self.tab_widget.addTab(preview_tab, "プレビュー")
        self.setup_preview_tab(preview_tab)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        self.save_button = QPushButton("保存")
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        
        self.preview_button = QPushButton("プレビュー更新")
        self.preview_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        
        button_layout.addWidget(self.preview_button)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # シグナル接続
        self.save_button.clicked.connect(self.save_prompt)
        self.cancel_button.clicked.connect(self.reject)
        self.preview_button.clicked.connect(self.update_preview)
        
    def setup_edit_tab(self, tab_widget):
        """プロンプト編集タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # 編集エリア
        edit_label = QLabel("プロンプトテンプレート:")
        edit_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(edit_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("プロンプトテンプレートを入力してください...\n\nテンプレート変数の例:\n{name} - データセット名\n{type} - データセットタイプ\n{description} - 説明")
        self.prompt_edit.setMinimumHeight(400)
        layout.addWidget(self.prompt_edit)
        
        # ヘルプ情報
        help_group = QGroupBox("ヘルプ")
        help_layout = QVBoxLayout(help_group)
        
        help_text = QLabel("""
<b>基本テンプレート変数:</b><br>
• <code>{name}</code> - データセット名<br>
• <code>{type}</code> - データセットタイプ<br>
• <code>{grant_number}</code> - 課題番号<br>
• <code>{description}</code> - 既存の説明文<br>
• <code>{experiment_data}</code> - 実験データ（JSON形式）<br>
• <code>{material_index_data}</code> - マテリアルインデックスデータ<br>
• <code>{equipment_data}</code> - 装置情報データ<br><br>
<b>ARIM利用報告書データ（課題番号から自動取得）:</b><br>
• <code>{arim_report_title}</code> - 利用課題名<br>
• <code>{arim_report_institute}</code> - 実施機関<br>
• <code>{arim_report_tech_area}</code> - 技術領域<br>
• <code>{arim_report_keywords}</code> - キーワード<br>
• <code>{arim_report_abstract}</code> - 概要・目的・実施内容<br>
• <code>{arim_report_experimental}</code> - 実験内容<br>
• <code>{arim_report_results}</code> - 結果と考察<br>
• <code>{arim_report_user_name}</code> - 利用者名<br>
• <code>{arim_report_affiliation}</code> - 所属機関<br>
• <code>{arim_report_remarks}</code> - その他・特記事項<br><br>
<b>注意事項:</b><br>
• テンプレート変数は波括弧 { } で囲んでください<br>
• 存在しない変数は "未設定" に置換されます<br>
• ARIM報告書データは課題番号があるときのみ取得されます<br>
• AIが理解しやすい構造化された形式で記述してください
        """)
        help_text.setWordWrap(True)
        help_text.setStyleSheet("background-color: #f9f9f9; padding: 10px; border-radius: 5px;")
        help_layout.addWidget(help_text)
        
        layout.addWidget(help_group)
        
    def setup_variables_tab(self, tab_widget):
        """テンプレート変数タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # 変数一覧
        variables_label = QLabel("利用可能なテンプレート変数:")
        variables_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(variables_label)
        
        self.variables_list = QListWidget()
        self.variables_list.setMaximumHeight(200)
        
        # 利用可能な変数リスト
        variables = [
            ("name", "データセット名", "例: マテリアル特性データセット"),
            ("type", "データセットタイプ", "例: mixed, experimental, computational"),
            ("grant_number", "課題番号", "例: JPMXP1234567890"),
            ("description", "既存の説明文", "例: 既存のデータセット説明"),
            ("experiment_data", "実験データ（JSON形式）", "実験データの詳細情報"),
            ("material_index_data", "マテリアルインデックス", "材料分類データ"),
            ("equipment_data", "装置情報", "使用された実験装置の情報"),
            ("dataset_existing_info", "データセット既存情報", "RDEから取得した既存情報"),
            # ARIM利用報告書データ
            ("arim_report_title", "ARIM利用課題名", "課題番号から取得される利用課題名"),
            ("arim_report_institute", "ARIM実施機関", "例: 東北大学 / Tohoku Univ."),
            ("arim_report_tech_area", "ARIM技術領域", "横断技術領域・重要技術領域"),
            ("arim_report_keywords", "ARIMキーワード", "例: シリコンキャパシタ,水素アニール"),
            ("arim_report_abstract", "ARIM概要", "目的・用途・実施内容"),
            ("arim_report_experimental", "ARIM実験内容", "実験手法・実施内容"),
            ("arim_report_results", "ARIM結果と考察", "実験結果・考察・成果"),
            ("arim_report_user_name", "ARIM利用者名", "課題申請者名"),
            ("arim_report_affiliation", "ARIM所属機関", "利用者の所属機関"),
            ("arim_report_remarks", "ARIM特記事項", "謝辞・参考文献等"),
            ("arim_extension_data", "ARIM拡張データ", "ARIM課題関連情報"),
            ("file_tree", "ファイル構成", "データセット内のファイル構造")
        ]
        
        for var_name, var_desc, var_example in variables:
            item_text = f"{{{var_name}}} - {var_desc}\n    {var_example}"
            item = QListWidgetItem(item_text)
            self.variables_list.addItem(item)
        
        layout.addWidget(self.variables_list)
        
        # 変数挿入ボタン
        insert_layout = QHBoxLayout()
        
        self.insert_var_edit = QLineEdit()
        self.insert_var_edit.setPlaceholderText("変数名を入力（例: name）")
        
        insert_button = QPushButton("変数挿入")
        insert_button.clicked.connect(self.insert_variable)
        
        insert_layout.addWidget(QLabel("変数挿入:"))
        insert_layout.addWidget(self.insert_var_edit)
        insert_layout.addWidget(insert_button)
        insert_layout.addStretch()
        
        layout.addLayout(insert_layout)
        
        # 変数リスト選択時の挿入
        self.variables_list.itemDoubleClicked.connect(self.insert_variable_from_list)
        
    def setup_preview_tab(self, tab_widget):
        """プレビュータブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # プレビューエリア
        preview_label = QLabel("プロンプトプレビュー（サンプルデータ使用）:")
        preview_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(preview_label)
        
        self.preview_display = QTextEdit()
        self.preview_display.setReadOnly(True)
        self.preview_display.setMinimumHeight(400)
        layout.addWidget(self.preview_display)
        
        # サンプルデータ情報
        sample_info = QLabel("※プレビューではサンプルデータを使用しています。実際のAI問い合わせ時には現在のデータセット情報が使用されます。")
        sample_info.setStyleSheet("color: #666; font-style: italic; margin: 5px;")
        sample_info.setWordWrap(True)
        layout.addWidget(sample_info)
        
    def load_prompt_content(self):
        """プロンプトファイルの内容を読み込む"""
        if self.prompt_file_path:
            content = load_prompt_file(self.prompt_file_path)
            if content:
                self.original_content = content
                self.prompt_edit.setText(content)
            else:
                # ファイルが存在しない場合のデフォルトテンプレート
                default_template = self.get_default_template()
                self.prompt_edit.setText(default_template)
        else:
            # ファイルパスが指定されていない場合（デフォルトボタン）
            default_template = self.button_config.get('prompt_template', '')
            self.prompt_edit.setText(default_template)
    
    def get_default_template(self):
        """デフォルトのプロンプトテンプレートを取得"""
        return """データセットについて分析してください。

【データセット情報】
- 名前: {name}
- タイプ: {type}
- 課題番号: {grant_number}
- 説明: {description}

【実験データ】
{experiment_data}

【分析指示】
上記データセット情報を基に、以下の観点から分析してください：

1. データセットの特徴
2. 技術的価値
3. 応用可能性
4. 改善提案

【出力形式】
各項目について詳しく分析し、200文字程度で要約してください。

日本語で詳細に分析してください。"""
    
    def insert_variable(self):
        """変数を挿入"""
        var_name = self.insert_var_edit.text().strip()
        if var_name:
            cursor = self.prompt_edit.textCursor()
            cursor.insertText(f"{{{var_name}}}")
            self.insert_var_edit.clear()
    
    def insert_variable_from_list(self, item):
        """リストから変数を挿入"""
        text = item.text()
        # {変数名} の部分を抽出
        if '{' in text and '}' in text:
            start = text.find('{')
            end = text.find('}') + 1
            var_placeholder = text[start:end]
            
            cursor = self.prompt_edit.textCursor()
            cursor.insertText(var_placeholder)
    
    def update_preview(self):
        """プレビューを更新"""
        try:
            current_content = self.prompt_edit.toPlainText()
            
            # サンプルデータを作成
            sample_data = {
                'name': 'サンプルデータセット',
                'type': 'experimental',
                'grant_number': 'JPMXP1234567890',
                'description': 'これはサンプルの説明文です。実際のデータセットでは現在の説明文が使用されます。',
                'experiment_data': '{"実験日": "2024-01-01", "測定項目": "材料特性", "サンプル数": 100}',
                'material_index_data': '{"材料分類": "金属", "組成": "Fe-Ni合金"}',
                'equipment_data': '{"装置名": "分析装置A", "精度": "±0.1%"}',
                'dataset_existing_info': 'RDEから取得した既存情報（サンプル）',
                'arim_extension_data': 'ARIM課題関連情報（サンプル）',
                'file_tree': 'ファイル構成情報（サンプル）'
            }
            
            # テンプレート変数を置換
            from classes.dataset.util.ai_extension_helper import format_prompt_with_context
            preview_content = format_prompt_with_context(current_content, sample_data)
            
            self.preview_display.setText(preview_content)
            
        except Exception as e:
            self.preview_display.setText(f"プレビュー生成エラー: {str(e)}")
    
    def save_prompt(self):
        """プロンプトを保存"""
        try:
            current_content = self.prompt_edit.toPlainText()
            
            if self.prompt_file_path:
                # ファイルに保存
                if save_prompt_file(self.prompt_file_path, current_content):
                    self.prompt_updated.emit(self.prompt_file_path)
                    QMessageBox.information(self, "保存完了", f"プロンプトファイルを保存しました。\n\n{self.prompt_file_path}")
                    self.accept()
                else:
                    QMessageBox.critical(self, "エラー", "プロンプトファイルの保存に失敗しました。")
            else:
                # デフォルトボタンの場合は設定を更新（実装は後で追加）
                QMessageBox.information(self, "情報", "デフォルトテンプレートの更新機能は今後実装予定です。")
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存エラー: {str(e)}")
    
    def closeEvent(self, event):
        """ダイアログクローズ時の処理"""
        current_content = self.prompt_edit.toPlainText()
        
        if current_content != self.original_content:
            reply = QMessageBox.question(
                self, 
                "未保存の変更", 
                "プロンプトに未保存の変更があります。保存しますか？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Yes:
                self.save_prompt()
                return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        
        event.accept()