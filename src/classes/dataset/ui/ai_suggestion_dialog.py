"""
AI提案ダイアログ
データセットの説明文をAIで生成・提案するダイアログウィンドウ
"""

import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QTextEdit, QProgressBar,
    QMessageBox, QSplitter, QWidget, QTabWidget, QGroupBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from classes.ai.core.ai_manager import AIManager
from classes.ai.extensions import AIExtensionRegistry, DatasetDescriptionExtension
from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
from classes.dataset.ui.prompt_template_edit_dialog import PromptTemplateEditDialog
from classes.dataset.util.dataset_context_collector import get_dataset_context_collector


class AIRequestThread(QThread):
    """AI リクエスト処理用スレッド"""
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, prompt, context_data=None):
        super().__init__()
        self.prompt = prompt
        self.context_data = context_data or {}
        
    def run(self):
        """AIリクエストを実行"""
        try:
            ai_manager = AIManager()
            
            # AI設定を取得
            from classes.config.ui.ai_settings_widget import get_ai_config
            ai_config = get_ai_config()
            
            if not ai_config:
                self.error_occurred.emit("AI設定が見つかりません")
                return
                
            # デフォルトプロバイダーとモデルを取得
            provider = ai_config.get('default_provider', 'gemini')
            model = ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash')
            
            # デバッグ用ログ出力
            print(f"[DEBUG] AI設定取得: provider={provider}, model={model}")
            print(f"[DEBUG] AI設定内容: {ai_config}")
            
            # AIリクエスト実行
            result = ai_manager.send_prompt(self.prompt, provider, model)
            
            if result.get('success', False):
                self.result_ready.emit(result)
            else:
                error_msg = result.get('error', '不明なエラー')
                self.error_occurred.emit(f"AIリクエストエラー: {error_msg}")
                
        except Exception as e:
            self.error_occurred.emit(f"AIリクエスト処理エラー: {str(e)}")


class AISuggestionDialog(QDialog):
    """AI提案ダイアログクラス"""
    
    def __init__(self, parent=None, context_data=None, extension_name="dataset_description", auto_generate=True):
        super().__init__(parent)
        self.context_data = context_data or {}
        self.extension_name = extension_name
        self.suggestions = []
        self.selected_suggestion = None
        self.ai_thread = None
        self.auto_generate = auto_generate  # 自動生成フラグ
        
        # AI拡張機能を取得
        self.ai_extension = AIExtensionRegistry.get(extension_name)
        if not self.ai_extension:
            self.ai_extension = DatasetDescriptionExtension()
        
        self.setup_ui()
        self.setup_connections()
        
        # 自動生成が有効な場合、ダイアログ表示後に自動でAI提案を生成
        if self.auto_generate:
            QTimer.singleShot(100, self.auto_generate_suggestions)
        
    def setup_ui(self):
        """UI要素のセットアップ"""
        self.setWindowTitle("AI説明文提案")
        self.setModal(True)
        self.resize(900, 700)
        
        layout = QVBoxLayout(self)
        
        # タイトルとツールバー
        header_layout = QHBoxLayout()
        title_label = QLabel("AIによる説明文の提案")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # プロンプトテンプレート編集ボタン
        self.edit_template_button = QPushButton("プロンプト編集")
        self.edit_template_button.setToolTip("プロンプトテンプレートを編集")
        self.edit_template_button.clicked.connect(self.edit_prompt_template)
        header_layout.addWidget(self.edit_template_button)
        
        layout.addLayout(header_layout)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # メインタブ
        main_tab = QWidget()
        self.tab_widget.addTab(main_tab, "AI提案")
        self.setup_main_tab(main_tab)
        
        # プロンプト表示タブ
        prompt_tab = QWidget()
        self.tab_widget.addTab(prompt_tab, "プロンプト全文")
        self.setup_prompt_tab(prompt_tab)
        
        # 詳細情報タブ
        detail_tab = QWidget()
        self.tab_widget.addTab(detail_tab, "詳細情報")
        self.setup_detail_tab(detail_tab)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        self.generate_button = QPushButton("AI提案生成")
        self.apply_button = QPushButton("適用")
        self.cancel_button = QPushButton("キャンセル")
        
        self.apply_button.setEnabled(False)
        
        button_layout.addWidget(self.generate_button)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
    def setup_main_tab(self, tab_widget):
        """メインタブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # コンテンツエリア
        content_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(content_splitter)
        
        # 候補リスト
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        
        list_label = QLabel("提案候補:")
        list_layout.addWidget(list_label)
        
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumWidth(250)
        list_layout.addWidget(self.suggestion_list)
        
        content_splitter.addWidget(list_widget)
        
        # プレビューエリア（全候補同時表示）
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        preview_label = QLabel("全候補プレビュー:")
        preview_layout.addWidget(preview_label)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setHtml(
            '<div style="padding: 20px; color: #666; text-align: center;">'
            '<h3>AI提案生成後に全候補が表示されます</h3>'
            '<p>候補リストで選択した候補が強調表示されます。<br>'
            '実際に適用する説明文を選択してください。</p>'
            '</div>'
        )
        preview_layout.addWidget(self.preview_text)
        
        content_splitter.addWidget(preview_widget)
        
    def setup_prompt_tab(self, tab_widget):
        """プロンプト表示タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # プロンプト全文表示
        prompt_label = QLabel("AIに送信されるプロンプト全文（ARIM課題データ統合済み）:")
        prompt_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(prompt_label)
        
        self.full_prompt_display = QTextEdit()
        self.full_prompt_display.setReadOnly(True)
        self.full_prompt_display.setPlainText("プロンプトはAI提案生成時に表示されます。")
        layout.addWidget(self.full_prompt_display)
        
        # 統計情報
        stats_label = QLabel("統計情報:")
        stats_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(stats_label)
        
        self.prompt_stats = QLabel("文字数: -, 行数: -, ARIM統合: -")
        self.prompt_stats.setStyleSheet("color: #666; margin: 5px;")
        layout.addWidget(self.prompt_stats)
        
    def setup_detail_tab(self, tab_widget):
        """詳細情報タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # プロンプト情報
        prompt_group = QGroupBox("使用プロンプト")
        prompt_layout = QVBoxLayout(prompt_group)
        
        self.prompt_display = QTextEdit()
        self.prompt_display.setReadOnly(True)
        self.prompt_display.setMaximumHeight(200)
        prompt_layout.addWidget(self.prompt_display)
        
        layout.addWidget(prompt_group)
        
        # コンテキストデータ
        context_group = QGroupBox("コンテキストデータ")
        context_layout = QVBoxLayout(context_group)
        
        self.context_display = QTextEdit()
        self.context_display.setReadOnly(True)
        self.context_display.setMaximumHeight(200)
        context_layout.addWidget(self.context_display)
        
        layout.addWidget(context_group)
        
        # AI応答の詳細
        response_group = QGroupBox("AI応答詳細")
        response_layout = QVBoxLayout(response_group)
        
        self.response_detail = QTextEdit()
        self.response_detail.setReadOnly(True)
        response_layout.addWidget(self.response_detail)
        
        layout.addWidget(response_group)
        
    def setup_connections(self):
        """シグナル・スロット接続"""
        self.generate_button.clicked.connect(self.generate_suggestions)
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.suggestion_list.currentItemChanged.connect(self.on_suggestion_selected)
        
    def generate_suggestions(self):
        """AI提案を生成"""
        if self.ai_thread and self.ai_thread.isRunning():
            return
            
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定プログレス
        self.generate_button.setEnabled(False)
        
        # プロンプトを構築
        prompt = self.build_prompt()
        
        # 詳細情報タブに表示
        self.update_detail_display(prompt)
        
        # AIリクエストスレッドを開始
        self.ai_thread = AIRequestThread(prompt, self.context_data)
        self.ai_thread.result_ready.connect(self.on_ai_result)
        self.ai_thread.error_occurred.connect(self.on_ai_error)
        self.ai_thread.start()
        
    def update_detail_display(self, prompt):
        """詳細情報タブの表示を更新"""
        # プロンプト表示（詳細情報タブ）
        self.prompt_display.setText(prompt)
        
        # プロンプト全文表示（プロンプトタブ）
        self.full_prompt_display.setPlainText(prompt)
        
        # プロンプト統計情報を更新
        char_count = len(prompt)
        line_count = prompt.count('\n') + 1
        has_arim_data = "ARIM課題関連情報" in prompt
        
        self.prompt_stats.setText(f"文字数: {char_count}, 行数: {line_count}, ARIM統合: {'○' if has_arim_data else '×'}")
        
        # コンテキストデータ表示
        context_text = "収集されたコンテキストデータ:\n\n"
        for key, value in self.context_data.items():
            # ARIM関連データは見やすく表示
            if key in ['dataset_existing_info', 'arim_extension_data', 'arim_experiment_data']:
                context_text += f"■ {key}:\n{value}\n\n"
            else:
                context_text += f"• {key}: {value}\n"
        self.context_display.setText(context_text)
        
    def edit_prompt_template(self):
        """プロンプトテンプレート編集ダイアログを表示"""
        try:
            dialog = PromptTemplateEditDialog(
                parent=self,
                extension_name=self.extension_name,
                template_name="basic"
            )
            
            if dialog.exec_() == QDialog.Accepted:
                # テンプレートが更新された場合、AI拡張機能を再読み込み
                self.ai_extension = AIExtensionRegistry.get(self.extension_name)
                if not self.ai_extension:
                    self.ai_extension = DatasetDescriptionExtension()
                    
                QMessageBox.information(self, "更新完了", "プロンプトテンプレートが更新されました")
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロンプトテンプレート編集エラー: {str(e)}")
        
    def build_prompt(self):
        """AIリクエスト用プロンプトを構築"""
        try:
            print(f"[DEBUG] プロンプト構築開始 - 入力コンテキスト: {self.context_data}")
            
            # AI設定を取得してプロバイダー・モデル情報を追加
            from classes.config.ui.ai_settings_widget import get_ai_config
            ai_config = get_ai_config()
            provider = ai_config.get('default_provider', 'gemini') if ai_config else 'gemini'
            model = ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash') if ai_config else 'gemini-2.0-flash'
            
            print(f"[DEBUG] 使用予定AI: provider={provider}, model={model}")
            
            # データセットコンテキストコレクターを使用して完全なコンテキストを収集
            context_collector = get_dataset_context_collector()
            
            # データセットIDがある場合は詳細情報を取得
            dataset_id = self.context_data.get('dataset_id')
            full_context = context_collector.collect_full_context(
                dataset_id=dataset_id,
                **self.context_data
            )
            
            print(f"[DEBUG] コンテキストコレクター処理後: {list(full_context.keys())}")
            
            # AI拡張機能からコンテキストデータを収集（既に統合されたfull_contextを使用）
            context = self.ai_extension.collect_context_data(**full_context)
            
            print(f"[DEBUG] AI拡張機能処理後: {list(context.keys())}")
            
            # プロバイダーとモデル情報をコンテキストに追加
            context['llm_provider'] = provider
            context['llm_model'] = model
            context['llm_model_name'] = f"{provider}:{model}"  # プロンプトテンプレート用
            
            # 毎回外部テンプレートファイルを最新の状態で読み込み
            print("[DEBUG] 外部テンプレートファイルを再読み込み中...")
            reload_success = self.ai_extension.reload_external_templates()
            if reload_success:
                print("[DEBUG] 外部テンプレート再読み込み成功")
            else:
                print("[WARNING] 外部テンプレート再読み込み失敗、既存テンプレートを使用")
            
            # デフォルトテンプレートを取得
            template = self.ai_extension.get_template("basic")
            if not template:
                print("[WARNING] テンプレートが取得できませんでした")
                # フォールバック用の簡単なプロンプト
                return f"データセット '{context.get('name', '未設定')}' の説明文を提案してください。"
            
            # プロンプトをレンダリング（contextを使用）
            prompt = template.render(context)
            
            print(f"[DEBUG] 生成されたプロンプト長: {len(prompt)} 文字")
            print(f"[DEBUG] ARIM関連情報含有: {'ARIM課題関連情報' in prompt}")
            
            return prompt
            
        except Exception as e:
            print(f"[WARNING] プロンプト構築エラー: {e}")
            import traceback
            traceback.print_exc()
            # エラー時のフォールバック
            return f"""
データセットの説明文を3つの異なるスタイルで提案してください。

データセット情報:
名前: {self.context_data.get('name', '未設定')}
課題番号: {self.context_data.get('grant_number', '未設定')}

出力形式:
[簡潔版] ここに簡潔な説明
[学術版] ここに学術的な説明  
[一般版] ここに一般向けの説明
"""
        
    def on_ai_result(self, result):
        """AIリクエスト結果を処理"""
        self.progress_bar.setVisible(False)
        self.generate_button.setEnabled(True)
        
        try:
            # レスポンステキストを取得
            response_text = result.get('response') or result.get('content', '')
            
            # 詳細情報タブにAI応答を表示
            response_detail = f"AI応答の詳細:\n\n"
            response_detail += f"成功: {result.get('success', False)}\n"
            response_detail += f"トークン使用量: {result.get('usage', {}).get('total_tokens', '不明')}\n"
            response_detail += f"応答時間: {result.get('response_time', 0):.2f}秒\n\n"
            response_detail += f"生の応答:\n{response_text}"
            self.response_detail.setText(response_detail)
            
            if response_text:
                self.parse_suggestions(response_text)
            else:
                QMessageBox.warning(self, "警告", "AIからの応答が空です")
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"AI結果処理エラー: {str(e)}")
            
    def on_ai_error(self, error_message):
        """AIリクエストエラーを処理"""
        self.progress_bar.setVisible(False)
        self.generate_button.setEnabled(True)
        QMessageBox.critical(self, "AIエラー", error_message)
        
    def parse_suggestions(self, response_text):
        """AI応答から提案候補を抽出"""
        self.suggestions.clear()
        self.suggestion_list.clear()
        
        try:
            # AI拡張機能を使用してレスポンスを解析
            parsed_suggestions = self.ai_extension.process_ai_response(response_text)
            
            for suggestion in parsed_suggestions:
                self.suggestions.append(suggestion)
                item = QListWidgetItem(suggestion['title'])
                self.suggestion_list.addItem(item)
                
            if self.suggestions:
                self.suggestion_list.setCurrentRow(0)
                self.apply_button.setEnabled(True)
                
                # 全候補をプレビューエリアに表示
                self.display_all_suggestions()
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"提案解析エラー: {str(e)}")
            
            # フォールバック: 全体を1つの提案として扱う
            self.suggestions.append({
                'title': 'AI提案',
                'text': response_text.strip()
            })
            
            item = QListWidgetItem('AI提案')
            self.suggestion_list.addItem(item)
            self.suggestion_list.setCurrentRow(0)
            self.apply_button.setEnabled(True)
            
            # フォールバック時も全候補表示
            self.display_all_suggestions()
    
    def display_all_suggestions(self):
        """全ての提案候補をプレビューエリアに表示"""
        if not self.suggestions:
            self.preview_text.setPlainText("提案候補がありません。")
            return
            
        # 最初の候補を選択状態として表示
        self.update_preview_highlight(0)
    
    def auto_generate_suggestions(self):
        """自動AI提案生成（ダイアログ表示時に自動実行）"""
        try:
            # 課題番号が存在する場合のみ自動生成
            grant_number = self.context_data.get('grant_number', '').strip()
            if grant_number and grant_number != '未設定':
                print(f"[INFO] AI提案を自動生成開始: 課題番号 {grant_number}")
                self.generate_suggestions()
            else:
                print("[INFO] 課題番号が設定されていないため、手動でAI提案生成を行ってください")
                
        except Exception as e:
            print(f"[WARNING] 自動AI提案生成エラー: {e}")
            # エラーが発生しても処理を続行（手動実行は可能）
            
    def on_suggestion_selected(self, current, previous):
        """提案選択時の処理（候補選択マーク用）"""
        if current:
            row = self.suggestion_list.row(current)
            if 0 <= row < len(self.suggestions):
                suggestion = self.suggestions[row]
                self.selected_suggestion = suggestion['text']
                
                # プレビューエリアで該当候補をハイライト表示
                self.update_preview_highlight(row)
            
    def update_preview_highlight(self, selected_index):
        """プレビューエリアで選択された候補をハイライト"""
        if not self.suggestions:
            return
            
        # 全候補を表示し、選択された候補を強調
        preview_html = ""
        
        for i, suggestion in enumerate(self.suggestions):
            if i == selected_index:
                # 選択された候補は背景色を変更
                preview_html += f'<div style="background-color: #e6f3ff; border: 2px solid #0066cc; padding: 10px; margin: 5px 0; border-radius: 5px;">'
                preview_html += f'<h3 style="color: #0066cc; margin: 0 0 10px 0;">【選択中】{suggestion["title"]}</h3>'
            else:
                # その他の候補は通常表示
                preview_html += f'<div style="border: 1px solid #ccc; padding: 10px; margin: 5px 0; border-radius: 5px;">'
                preview_html += f'<h3 style="color: #333; margin: 0 0 10px 0;">{suggestion["title"]}</h3>'
            
            # 改行を<br>に変換してHTML表示
            text_with_breaks = suggestion['text'].replace('\n', '<br>')
            preview_html += f'<div style="white-space: pre-wrap; line-height: 1.4;">{text_with_breaks}</div>'
            preview_html += '</div><br>'
        
        self.preview_text.setHtml(preview_html)
            
    def get_selected_suggestion(self):
        """選択された提案を取得"""
        return self.selected_suggestion