"""
AI拡張プロンプト編集ダイアログ
プロンプトファイルの編集とテンプレート変数の管理を行う
"""

import os
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QMessageBox, QTabWidget, QWidget, QGroupBox,
    QLineEdit, QFormLayout, QScrollArea, QListWidget, QListWidgetItem,
    QComboBox, QSizePolicy
)
from qt_compat.core import Qt, Signal
from classes.dataset.util.ai_extension_helper import load_prompt_file, save_prompt_file
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import get_dynamic_file_path

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
        # ユーザーが高さを変更できるようサイズグリップを有効化
        self.setSizeGripEnabled(True)
        
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
            desc_label.setStyleSheet(
                f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px 10px;"
            )
            header_layout.addWidget(desc_label)
        
        file_label = QLabel(f"ファイル: {self.prompt_file_path}")
        file_label.setStyleSheet(
            f"font-family: 'Consolas'; color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px 10px;"
        )
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
        self.save_button.setProperty("variant", "success")
        
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setProperty("variant", "secondary")
        
        self.preview_button = QPushButton("プレビュー更新")
        self.preview_button.setProperty("variant", "info")
        
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
        self.prompt_edit.setPlaceholderText(
            "プロンプトテンプレートを入力してください...\n\nテンプレート変数の例:\n{name} - データセット名\n{type} - データセットタイプ\n{description} - 説明"
        )
        # 最小高さを抑えて、ダイアログの縮小を妨げないようにする
        self.prompt_edit.setMinimumHeight(240)
        self.prompt_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.prompt_edit)

        # 出力フォーマット選択（text/json）
        fmt_group = QGroupBox("出力フォーマット")
        fmt_layout = QHBoxLayout(fmt_group)
        fmt_label = QLabel("LLM応答の期待フォーマット:")
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["text", "json"])
        # 初期値（button_configにあればそれを使用）
        init_fmt = self.button_config.get('output_format', 'text')
        if init_fmt not in ["text", "json"]:
            init_fmt = "text"
        self.output_format_combo.setCurrentText(init_fmt)
        fmt_layout.addWidget(fmt_label)
        fmt_layout.addWidget(self.output_format_combo)
        layout.addWidget(fmt_group)

        # ヘルプ情報
        help_group = QGroupBox("ヘルプ")
        help_layout = QVBoxLayout(help_group)
        help_text = QLabel(
            """
<b>基本テンプレート変数:</b><br>
• <code>{name}</code> - データセット名<br>
• <code>{type}</code> - データセットタイプ<br>
• <code>{grant_number}</code> - 課題番号<br>
• <code>{description}</code> - 既存の説明文<br>
• <code>{experiment_data}</code> - 実験データ（JSON形式）<br>
• <code>{material_index_data}</code> - マテリアルインデックスデータ<br>
• <code>{equipment_data}</code> - 装置情報データ<br><br>
<b>ARIM利用報告書データ:</b><br>
• <code>{arim_report_title}</code> - 利用課題名 など<br><br>
<b>データポータルマスタデータ:</b><br>
• <code>{dataportal_material_index}</code> - マテリアルインデックスマスタ<br>
• <code>{dataportal_tag}</code> - タグマスタ<br>
• <code>{dataportal_equipment}</code> - 装置分類マスタ<br><br>
<b>静的データ:</b><br>
• <code>{static_material_index}</code> - MI.json（input/ai/MI.json）
            """
        )
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        # ヘルプセクションはスクロール可能にして、ダイアログの最小サイズを抑制
        help_scroll = QScrollArea()
        help_scroll.setWidget(help_group)
        help_scroll.setWidgetResizable(True)
        help_scroll.setMaximumHeight(240)
        layout.addWidget(help_scroll)

        # 変数リスト（挿入支援）は変数タブで構築
        
    def setup_preview_tab(self, tab_widget):
        """プレビュータブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # プレビューエリア
        preview_label = QLabel("プロンプトプレビュー（サンプルデータ使用）:")
        preview_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(preview_label)
        
        self.preview_display = QTextEdit()
        self.preview_display.setReadOnly(True)
        # 最小高さを抑える
        self.preview_display.setMinimumHeight(240)
        self.preview_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.preview_display)
        
        # サンプルデータ情報
        sample_info = QLabel("※プレビューではサンプルデータを使用しています。実際のAI問い合わせ時には現在のデータセット情報が使用されます。")
        sample_info.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-style: italic; margin: 5px;"
        )
        sample_info.setWordWrap(True)
        layout.addWidget(sample_info)

    def setup_variables_tab(self, tab_widget):
        """テンプレート変数タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)

        # 利用可能な変数リスト
        self.variables_list = QListWidget()
        variables = [
            ("name", "データセット名", "サンプルデータセット"),
            ("type", "データセットタイプ", "experimental"),
            ("grant_number", "課題番号", "JPMXP1234567890"),
            ("description", "説明", "説明文..."),
            ("experiment_data", "実験データ", "{\"測定項目\": \"材料特性\"}"),
            ("material_index_data", "マテリアルインデックスデータ", "{\"材料分類\": \"金属\"}"),
            ("equipment_data", "装置情報データ", "{\"装置名\": \"分析装置A\"}"),
            ("arim_report_title", "ARIM 利用課題名", "..."),
            ("arim_extension_data", "ARIM 拡張データ", "..."),
            ("file_tree", "ファイル構成", "..."),
            ("dataportal_material_index", "データポータル マテリアルインデックスマスタ", "{...JSON...}"),
            ("dataportal_tag", "データポータル タグマスタ", "{...JSON...}"),
            ("dataportal_equipment", "データポータル 装置分類マスタ", "{...JSON...}"),
            ("static_material_index", "静的マテリアルインデックス (MI.json)", "{...JSON...}"),
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
        layout.addLayout(insert_layout)

        # 変数リスト選択時の挿入
        self.variables_list.itemDoubleClicked.connect(self.insert_variable_from_list)
        
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
                'file_tree': 'ファイル構成情報（サンプル）',
                'dataportal_material_index': '{"environment": "sample", "data": {"1": "デバイス・センサー関連材料"}}',
                'dataportal_tag': '{"environment": "sample", "data": {"tag1": "タグ例"}}',
                'dataportal_equipment': '{"environment": "sample", "data": {"eq1": "装置例"}}',
                'static_material_index': '{"categories": ["金属", "セラミックス"]}'
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
            # 出力フォーマットの取得
            selected_fmt = self.output_format_combo.currentText()
            # 設定ファイルの更新（ai_ext_conf.json の対象ボタンの output_format）
            try:
                from classes.dataset.util.ai_extension_helper import load_ai_extension_config
                import json

                config = load_ai_extension_config()
                btn_id = self.button_config.get('id')

                if btn_id and 'buttons' in config:
                    for btn in config['buttons']:
                        if btn.get('id') == btn_id:
                            btn['output_format'] = selected_fmt
                            break

                    conf_path = get_dynamic_file_path('input/ai/ai_ext_conf.json')
                    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
                    with open(conf_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                # 該当が無い場合は後続処理のみ行う（情報ログ扱い）
            except Exception as e:
                # フォーマット保存失敗は致命的ではないため警告のみ
                QMessageBox.warning(self, "警告", f"出力フォーマットの保存に失敗しました: {e}")
            
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