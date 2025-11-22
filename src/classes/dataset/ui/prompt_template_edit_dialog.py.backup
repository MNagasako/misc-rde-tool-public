"""
プロンプトテンプレート編集ダイアログ
AI拡張機能のプロンプトテンプレートを編集・管理する
"""

import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QTabWidget, QWidget, QComboBox, QLineEdit,
    QMessageBox, QSplitter, QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt
from config.common import get_dynamic_file_path


class PromptTemplateEditDialog(QDialog):
    """プロンプトテンプレート編集ダイアログ"""
    
    def __init__(self, parent=None, extension_name="dataset_description", template_name="basic"):
        super().__init__(parent)
        self.extension_name = extension_name
        self.template_name = template_name
        self.templates_config = {}
        
        self.setup_ui()
        self.load_templates()
        
    def setup_ui(self):
        """UI要素のセットアップ"""
        self.setWindowTitle("プロンプトテンプレート編集")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # タイトル
        title_label = QLabel("プロンプトテンプレート編集")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)
        
        # テンプレート選択
        template_group = QGroupBox("テンプレート設定")
        template_layout = QFormLayout(template_group)
        
        self.extension_combo = QComboBox()
        self.extension_combo.addItems(["dataset_description"])
        self.extension_combo.setCurrentText(self.extension_name)
        template_layout.addRow("拡張機能:", self.extension_combo)
        
        self.template_combo = QComboBox()
        self.template_combo.addItems(["basic", "detailed"])
        self.template_combo.setCurrentText(self.template_name)
        template_layout.addRow("テンプレート:", self.template_combo)
        
        self.template_name_edit = QLineEdit()
        template_layout.addRow("テンプレート名:", self.template_name_edit)
        
        layout.addWidget(template_group)
        
        # メインエリア（スプリッター）
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # 左側：プロンプトテンプレート編集
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        prompt_label = QLabel("プロンプトテンプレート:")
        left_layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("""
プロンプトテンプレートを入力してください。
変数は {変数名} の形式で指定できます。

例:
データセット名: {name}
課題番号: {grant_number}
説明: {existing_description}
""")
        left_layout.addWidget(self.prompt_edit)
        
        splitter.addWidget(left_widget)
        
        # 右側：コンテキスト変数と説明
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        context_label = QLabel("利用可能な変数:")
        right_layout.addWidget(context_label)
        
        self.context_info = QTextEdit()
        self.context_info.setReadOnly(True)
        self.context_info.setMaximumWidth(300)
        self.context_info.setText("""
基本変数:
• {name} - データセット名
• {type} - データセットタイプ
• {grant_number} - 課題番号
• {existing_description} - 既存の説明

詳細変数:
• {file_info} - ファイル情報
• {metadata} - メタデータ
• {related_datasets} - 関連データセット

注意: 空の変数には [変数名未設定] が自動的に挿入されます。
""")
        right_layout.addWidget(self.context_info)
        
        splitter.addWidget(right_widget)
        
        # プレビューエリア
        preview_group = QGroupBox("プレビュー")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        preview_layout.addWidget(self.preview_text)
        
        preview_button = QPushButton("プレビュー生成")
        preview_button.clicked.connect(self.generate_preview)
        preview_layout.addWidget(preview_button)
        
        layout.addWidget(preview_group)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        self.load_button = QPushButton("読み込み")
        self.save_button = QPushButton("保存")
        self.reset_button = QPushButton("リセット")
        self.apply_button = QPushButton("適用")
        self.cancel_button = QPushButton("キャンセル")
        
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # シグナル接続
        self.extension_combo.currentTextChanged.connect(self.on_template_changed)
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
        self.load_button.clicked.connect(self.load_template)
        self.save_button.clicked.connect(self.save_template)
        self.reset_button.clicked.connect(self.reset_template)
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
    def load_templates(self):
        """テンプレート設定ファイルを読み込み"""
        try:
            config_path = get_dynamic_file_path("input/prompt_templates.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.templates_config = json.load(f)
            else:
                self.templates_config = self.get_default_templates()
                
            self.load_template()
            
        except Exception as e:
            QMessageBox.warning(self, "警告", f"テンプレート読み込みエラー: {e}")
            self.templates_config = self.get_default_templates()
            
    def get_default_templates(self):
        """デフォルトのテンプレート設定を取得"""
        return {
            "dataset_description": {
                "basic": {
                    "name": "基本テンプレート",
                    "prompt": """データセットの説明文を3つの異なるスタイルで提案してください。

データセット情報:
- 名前: {name}
- タイプ: {type}
- 課題番号: {grant_number}
- 既存説明: {existing_description}

要求:
1. 簡潔で分かりやすい説明文（100文字程度）
2. 学術的で詳細な説明文（200文字程度）
3. 一般向けに親しみやすい説明文（150文字程度）

出力形式:
[簡潔版] ここに簡潔な説明
[学術版] ここに学術的な説明
[一般版] ここに一般向けの説明

注意: 各説明文は改行なしで1行で出力してください。"""
                },
                "detailed": {
                    "name": "詳細テンプレート",
                    "prompt": """データセットの詳細説明文を生成してください。

基本情報:
- データセット名: {name}
- データセットタイプ: {type}
- 研究課題番号: {grant_number}
- 既存の説明: {existing_description}

関連情報:
- ファイル情報: {file_info}
- メタデータ: {metadata}
- 関連データセット: {related_datasets}

要求:
専門的で包括的な説明文を作成してください。研究の背景、データの特徴、利用方法を含めてください。

出力: 詳細な説明文（500文字以内）"""
                }
            }
        }
        
    def on_template_changed(self):
        """テンプレート選択変更時の処理"""
        self.load_template()
        
    def load_template(self):
        """選択されたテンプレートを読み込み"""
        try:
            extension = self.extension_combo.currentText()
            template = self.template_combo.currentText()
            
            if extension in self.templates_config and template in self.templates_config[extension]:
                template_data = self.templates_config[extension][template]
                self.template_name_edit.setText(template_data.get("name", template))
                self.prompt_edit.setText(template_data.get("prompt", ""))
            else:
                self.template_name_edit.setText("")
                self.prompt_edit.setText("")
                
        except Exception as e:
            QMessageBox.warning(self, "警告", f"テンプレート読み込みエラー: {e}")
            
    def save_template(self):
        """現在のテンプレートを保存"""
        try:
            extension = self.extension_combo.currentText()
            template = self.template_combo.currentText()
            
            if extension not in self.templates_config:
                self.templates_config[extension] = {}
                
            self.templates_config[extension][template] = {
                "name": self.template_name_edit.text(),
                "prompt": self.prompt_edit.toPlainText()
            }
            
            # ファイルに保存
            config_path = get_dynamic_file_path("input/prompt_templates.json")
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.templates_config, f, ensure_ascii=False, indent=2)
                
            QMessageBox.information(self, "保存完了", "テンプレートが保存されました")
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"テンプレート保存エラー: {e}")
            
    def reset_template(self):
        """テンプレートをデフォルトにリセット"""
        defaults = self.get_default_templates()
        extension = self.extension_combo.currentText()
        template = self.template_combo.currentText()
        
        if extension in defaults and template in defaults[extension]:
            template_data = defaults[extension][template]
            self.template_name_edit.setText(template_data.get("name", template))
            self.prompt_edit.setText(template_data.get("prompt", ""))
            
    def generate_preview(self):
        """プレビューを生成"""
        try:
            # サンプルデータでプレビュー生成
            sample_data = {
                "name": "サンプルデータセット",
                "type": "実験データ",
                "grant_number": "JPMXP1234567890",
                "existing_description": "既存の説明文",
                "file_info": "CSV, JSON ファイル含む",
                "metadata": "2024年作成、材料科学分野",
                "related_datasets": "関連データセット3件"
            }
            
            prompt_template = self.prompt_edit.toPlainText()
            preview = prompt_template.format(**sample_data)
            self.preview_text.setText(preview)
            
        except Exception as e:
            self.preview_text.setText(f"プレビュー生成エラー: {e}")
            
    def get_current_template(self):
        """現在編集中のテンプレートデータを取得"""
        return {
            "extension": self.extension_combo.currentText(),
            "template": self.template_combo.currentText(),
            "name": self.template_name_edit.text(),
            "prompt": self.prompt_edit.toPlainText()
        }