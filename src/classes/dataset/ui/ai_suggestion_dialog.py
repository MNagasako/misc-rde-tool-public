"""
AI提案ダイアログ
データセットの説明文をAIで生成・提案するダイアログウィンドウ
"""

import os
import json
import logging
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QTextEdit, QProgressBar,
    QMessageBox, QSplitter, QWidget, QTabWidget, QGroupBox,
    QComboBox
)
from qt_compat.core import Qt, QThread, Signal, QTimer
from classes.ai.core.ai_manager import AIManager

# ロガー設定
logger = logging.getLogger(__name__)
from classes.ai.extensions import AIExtensionRegistry, DatasetDescriptionExtension
from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
from classes.dataset.ui.prompt_template_edit_dialog import PromptTemplateEditDialog
from classes.dataset.util.dataset_context_collector import get_dataset_context_collector


class AIRequestThread(QThread):
    """AI リクエスト処理用スレッド"""
    result_ready = Signal(object)  # PySide6: dict→object
    error_occurred = Signal(str)
    
    def __init__(self, prompt, context_data=None):
        super().__init__()
        self.prompt = prompt
        self.context_data = context_data or {}
        self._stop_requested = False
        
    def stop(self):
        """スレッドの停止をリクエスト"""
        self._stop_requested = True
        
    def run(self):
        """AIリクエストを実行"""
        try:
            if self._stop_requested:
                return
                
            ai_manager = AIManager()
            
            # AI設定を取得
            from classes.config.ui.ai_settings_widget import get_ai_config
            ai_config = get_ai_config()
            
            if self._stop_requested:
                return
            
            if not ai_config:
                self.error_occurred.emit("AI設定が見つかりません")
                return
                
            # デフォルトプロバイダーとモデルを取得
            provider = ai_config.get('default_provider', 'gemini')
            model = ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash')
            
            # デバッグ用ログ出力
            logger.debug("AI設定取得: provider=%s, model=%s", provider, model)
            logger.debug("AI設定内容: %s", ai_config)
            
            if self._stop_requested:
                return
            
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
        self.extension_ai_threads = []  # AI拡張用のスレッドリスト
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
        
        # AI拡張タブ
        try:
            extension_tab = QWidget()
            self.tab_widget.addTab(extension_tab, "AI拡張")
            self.setup_extension_tab(extension_tab)
        except Exception as e:
            logger.warning("AI拡張タブの初期化に失敗しました: %s", e)
            # AI拡張タブが失敗しても他の機能は使用可能
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        # SpinnerButtonをインポートして使用
        from classes.dataset.ui.spinner_button import SpinnerButton
        
        self.generate_button = SpinnerButton("🚀 AI提案生成")
        self.generate_button.setMinimumHeight(35)
        self.generate_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #81C784;
                color: #E8F5E9;
            }
        """)
        
        self.apply_button = QPushButton("適用")
        self.cancel_button = QPushButton("キャンセル")
        
        self.apply_button.setEnabled(False)
        
        button_layout.addWidget(self.generate_button)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # データセット選択ドロップダウンを初期化
        QTimer.singleShot(100, self.initialize_dataset_dropdown)
        
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
            logger.debug("既にAIスレッドが実行中です")
            return
        
        try:
            # スピナー開始
            self.generate_button.start_loading("生成中")
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # 不定プログレス
            
            # プロンプトを構築
            prompt = self.build_prompt()
            
            # 詳細情報タブに表示
            self.update_detail_display(prompt)
            
            # 既存のスレッドがあれば停止
            if self.ai_thread:
                if self.ai_thread.isRunning():
                    self.ai_thread.stop()
                    self.ai_thread.wait(1000)
            
            # AIリクエストスレッドを開始
            self.ai_thread = AIRequestThread(prompt, self.context_data)
            self.ai_thread.result_ready.connect(self.on_ai_result)
            self.ai_thread.error_occurred.connect(self.on_ai_error)
            self.ai_thread.start()
            
        except Exception as e:
            logger.error("AI提案生成エラー: %s", e)
            self.generate_button.stop_loading()
            self.progress_bar.setVisible(False)
        
    def update_detail_display(self, prompt):
        """詳細情報タブの表示を更新"""
        logger.debug("プロンプト表示更新: 全%s文字", len(prompt))
        
        # プロンプト内にファイル情報が含まれているか確認
        if 'ファイル構成' in prompt or 'ファイル統計' in prompt or 'タイル#' in prompt:
            logger.debug("[OK] プロンプトにファイル情報が含まれています")
        else:
            logger.warning("プロンプトにファイル情報が見つかりません")
        
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
            
            if dialog.exec() == QDialog.Accepted:
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
            logger.debug("プロンプト構築開始 - 入力コンテキスト: %s", self.context_data)
            
            # AI設定を取得してプロバイダー・モデル情報を追加
            from classes.config.ui.ai_settings_widget import get_ai_config
            ai_config = get_ai_config()
            provider = ai_config.get('default_provider', 'gemini') if ai_config else 'gemini'
            model = ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash') if ai_config else 'gemini-2.0-flash'
            
            logger.debug("使用予定AI: provider=%s, model=%s", provider, model)
            
            # データセットコンテキストコレクターを使用して完全なコンテキストを収集
            context_collector = get_dataset_context_collector()
            
            # データセットIDを取得（context_dataから）
            dataset_id = self.context_data.get('dataset_id')
            logger.debug("データセットID: %s", dataset_id)
            
            # context_dataからdataset_idを一時的に除外してから渡す
            context_data_without_id = {k: v for k, v in self.context_data.items() if k != 'dataset_id'}
            
            # collect_full_contextにdataset_idを明示的に渡す
            full_context = context_collector.collect_full_context(
                dataset_id=dataset_id,
                **context_data_without_id
            )
            
            logger.debug("コンテキストコレクター処理後: %s", list(full_context.keys()))
            
            # AI拡張機能からコンテキストデータを収集（既に統合されたfull_contextを使用）
            context = self.ai_extension.collect_context_data(**full_context)
            
            logger.debug("AI拡張機能処理後: %s", list(context.keys()))
            
            # プロバイダーとモデル情報をコンテキストに追加
            context['llm_provider'] = provider
            context['llm_model'] = model
            context['llm_model_name'] = f"{provider}:{model}"  # プロンプトテンプレート用
            
            # 毎回外部テンプレートファイルを最新の状態で読み込み
            logger.debug("外部テンプレートファイルを再読み込み中...")
            reload_success = self.ai_extension.reload_external_templates()
            if reload_success:
                logger.debug("外部テンプレート再読み込み成功")
            else:
                logger.warning("外部テンプレート再読み込み失敗、既存テンプレートを使用")
            
            # デフォルトテンプレートを取得
            template = self.ai_extension.get_template("basic")
            if not template:
                logger.warning("テンプレートが取得できませんでした")
                # フォールバック用の簡単なプロンプト
                return f"データセット '{context.get('name', '未設定')}' の説明文を提案してください。"
            
            # プロンプトをレンダリング（contextを使用）
            prompt = template.render(context)
            
            logger.debug("生成されたプロンプト長: %s 文字", len(prompt))
            logger.debug("ARIM関連情報含有: %s", 'ARIM課題関連情報' in prompt)
            
            return prompt
            
        except Exception as e:
            logger.error("プロンプト構築エラー: %s", e)
            import traceback
            traceback.print_exc()
            
            # エラー時のフォールバック（より詳細な情報を含める）
            name = self.context_data.get('name', '未設定')
            grant_number = self.context_data.get('grant_number', '未設定')
            description = self.context_data.get('description', '')
            dataset_type = self.context_data.get('type', 'mixed')
            
            fallback_prompt = f"""
データセットの説明文を3つの異なるスタイルで提案してください。

【データセット基本情報】
- データセット名: {name}
- 課題番号: {grant_number}
- データセットタイプ: {dataset_type}
"""
            
            if description:
                fallback_prompt += f"- 既存の説明: {description}\n"
            
            fallback_prompt += """
【要求事項】
1. 学術的で専門的な内容を含めること
2. データの特徴や価値を明確にすること
3. 利用者にとって有用な情報を提供すること

【出力形式】
以下の3つのスタイルで説明文を提案してください:

[簡潔版] ここに簡潔な説明（200文字程度）

[学術版] ここに学術的な説明（500文字程度）

[一般版] ここに一般向けの説明（300文字程度）

注意: 各説明文は改行なしで1行で出力してください。
"""
            
            logger.warning("フォールバックプロンプトを使用: %s文字", len(fallback_prompt))
            return fallback_prompt
        
    def on_ai_result(self, result):
        """AIリクエスト結果を処理"""
        try:
            self.progress_bar.setVisible(False)
            
            # スピナー停止
            self.generate_button.stop_loading()
            
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
            logger.error("AI結果処理エラー: %s", e)
            QMessageBox.critical(self, "エラー", f"AI結果処理エラー: {str(e)}")
            
    def on_ai_error(self, error_message):
        """AIリクエストエラーを処理"""
        try:
            self.progress_bar.setVisible(False)
            
            # スピナー停止
            self.generate_button.stop_loading()
            
            logger.error("AIエラー: %s", error_message)
            QMessageBox.critical(self, "AIエラー", error_message)
            
        except Exception as e:
            logger.error("AIエラー処理エラー: %s", e)
        
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
                logger.info("AI提案を自動生成開始: 課題番号 %s", grant_number)
                self.generate_suggestions()
            else:
                logger.info("課題番号が設定されていないため、手動でAI提案生成を行ってください")
                
        except Exception as e:
            logger.warning("自動AI提案生成エラー: %s", e)
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
            
            # HTMLエスケープして改行を<br>に変換（XSS対策）
            import html
            escaped_text = html.escape(suggestion['text'])
            text_with_breaks = escaped_text.replace('\n', '<br>')
            preview_html += f'<div style="white-space: pre-wrap; line-height: 1.4;">{text_with_breaks}</div>'
            preview_html += '</div><br>'
        
        self.preview_text.setHtml(preview_html)
            
    def get_selected_suggestion(self):
        """選択された提案を取得"""
        return self.selected_suggestion
    
    def setup_extension_tab(self, tab_widget):
        """AI拡張タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # ヘッダー
        header_layout = QHBoxLayout()
        
        title_label = QLabel("AI拡張サジェスト機能")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 設定ボタン
        config_button = QPushButton("設定編集")
        config_button.setToolTip("AI拡張設定ファイルを編集")
        config_button.clicked.connect(self.edit_extension_config)
        config_button.setMaximumWidth(80)
        header_layout.addWidget(config_button)
        
        layout.addLayout(header_layout)
        
        # データセット選択エリア
        dataset_select_widget = QWidget()
        dataset_select_layout = QVBoxLayout(dataset_select_widget)
        dataset_select_layout.setContentsMargins(10, 5, 10, 5)
        
        # データセット選択ラベル
        dataset_select_label = QLabel("分析対象データセットを選択:")
        dataset_select_label.setStyleSheet("font-weight: bold; margin: 5px;")
        dataset_select_layout.addWidget(dataset_select_label)
        
        # データセット選択コンボボックス
        dataset_combo_container = QWidget()
        dataset_combo_layout = QHBoxLayout(dataset_combo_container)
        dataset_combo_layout.setContentsMargins(0, 0, 0, 0)
        
        self.extension_dataset_combo = QComboBox()
        self.extension_dataset_combo.setMinimumWidth(500)
        self.extension_dataset_combo.setEditable(True)
        self.extension_dataset_combo.setInsertPolicy(QComboBox.NoInsert)
        self.extension_dataset_combo.setMaxVisibleItems(12)
        self.extension_dataset_combo.lineEdit().setPlaceholderText("データセットを検索・選択してください")
        dataset_combo_layout.addWidget(self.extension_dataset_combo)
        
        # ▼ボタン追加
        show_all_btn = QPushButton("▼")
        show_all_btn.setToolTip("全件リスト表示")
        show_all_btn.setFixedWidth(28)
        show_all_btn.clicked.connect(self.show_all_datasets)
        dataset_combo_layout.addWidget(show_all_btn)
        
        dataset_select_layout.addWidget(dataset_combo_container)
        layout.addWidget(dataset_select_widget)
        
        # データセット情報エリア（既存）
        dataset_info_widget = QWidget()
        dataset_info_layout = QVBoxLayout(dataset_info_widget)
        dataset_info_layout.setContentsMargins(10, 5, 10, 5)
        
        # データセット情報を取得・表示
        dataset_name = self.context_data.get('name', '').strip()
        grant_number = self.context_data.get('grant_number', '').strip()
        dataset_type = self.context_data.get('type', '').strip()
        
        if not dataset_name:
            dataset_name = "データセット名未設定"
        if not grant_number:
            grant_number = "課題番号未設定"
        if not dataset_type:
            dataset_type = "タイプ未設定"
        
        dataset_info_html = f"""
        <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 10px; margin: 5px 0;">
            <h4 style="margin: 0 0 8px 0; color: #495057;">📊 対象データセット情報</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="font-weight: bold; color: #6c757d; padding: 2px 10px 2px 0; width: 100px;">データセット名:</td>
                    <td style="color: #212529; padding: 2px 0;">{dataset_name}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #6c757d; padding: 2px 10px 2px 0;">課題番号:</td>
                    <td style="color: #212529; padding: 2px 0;">{grant_number}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #6c757d; padding: 2px 10px 2px 0;">タイプ:</td>
                    <td style="color: #212529; padding: 2px 0;">{dataset_type}</td>
                </tr>
            </table>
        </div>
        """
        
        self.dataset_info_label = QLabel(dataset_info_html)
        self.dataset_info_label.setWordWrap(True)
        dataset_info_layout.addWidget(self.dataset_info_label)
        
        layout.addWidget(dataset_info_widget)
        
        # メインコンテンツエリア（左右分割）
        from qt_compat.widgets import QSplitter
        content_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(content_splitter)
        
        # 左側: ボタンエリア
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        buttons_label = QLabel("🤖 AIサジェスト機能")
        buttons_label.setStyleSheet("font-weight: bold; margin: 5px 0; font-size: 13px; color: #495057;")
        left_layout.addWidget(buttons_label)
        
        # ボタンエリア（スクロールなしで直接配置）
        self.buttons_widget = QWidget()
        self.buttons_layout = QVBoxLayout(self.buttons_widget)
        self.buttons_layout.setContentsMargins(5, 5, 5, 5)
        self.buttons_layout.setSpacing(6)  # ボタン間の間隔を狭く
        
        left_layout.addWidget(self.buttons_widget)
        left_layout.addStretch()  # 下部にストレッチを追加
        
        left_widget.setMaximumWidth(280)  # 幅を調整
        left_widget.setMinimumWidth(250)
        content_splitter.addWidget(left_widget)
        
        # 右側: 応答表示エリア
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        response_label = QLabel("📝 AI応答結果")
        response_label.setStyleSheet("font-weight: bold; margin: 5px 0; font-size: 13px; color: #495057;")
        right_layout.addWidget(response_label)
        
        from qt_compat.widgets import QTextBrowser
        
        self.extension_response_display = QTextBrowser()
        self.extension_response_display.setReadOnly(True)
        self.extension_response_display.setOpenExternalLinks(False)  # セキュリティのため外部リンクは無効
        self.extension_response_display.setPlaceholderText(
            "🤖 AI拡張サジェスト機能へようこそ！\n\n"
            "左側のボタンをクリックすると、選択した機能に応じたAI分析結果がここに表示されます。\n\n"
            "利用可能な機能:\n"
            "• 重要技術領域の分析\n"
            "• キーワード提案\n"
            "• 応用分野の提案\n"
            "• 制限事項の分析\n"
            "• 関連データセットの提案\n"
            "• 改善提案\n\n"
            "各ボタンを右クリックするとプロンプトの編集・プレビューが可能です。"
        )
        self.extension_response_display.setStyleSheet("""
            QTextBrowser {
                border: 1px solid #dee2e6;
                border-radius: 5px;
                background-color: #ffffff;
                font-family: 'Yu Gothic', 'Meiryo', sans-serif;
                font-size: 12px;
                line-height: 1.3;
                padding: 6px;
            }
            QTextBrowser h1 {
                color: #2c3e50;
                font-size: 16px;
                font-weight: bold;
                margin: 8px 0 4px 0;
                border-bottom: 2px solid #3498db;
                padding-bottom: 2px;
            }
            QTextBrowser h2 {
                color: #34495e;
                font-size: 15px;
                font-weight: bold;
                margin: 6px 0 3px 0;
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 1px;
            }
            QTextBrowser h3 {
                color: #34495e;
                font-size: 14px;
                font-weight: bold;
                margin: 5px 0 2px 0;
            }
            QTextBrowser p {
                margin: 3px 0;
                line-height: 1.3;
            }
            QTextBrowser ul {
                margin: 3px 0 3px 12px;
            }
            QTextBrowser li {
                margin: 1px 0;
                line-height: 1.3;
            }
            QTextBrowser code {
                background-color: #f8f9fa;
                color: #e83e8c;
                padding: 1px 3px;
                border-radius: 2px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }
            QTextBrowser pre {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 3px;
                padding: 6px;
                margin: 4px 0;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                overflow-x: auto;
            }
            QTextBrowser blockquote {
                border-left: 3px solid #3498db;
                margin: 4px 0;
                padding: 4px 8px;
                background-color: #f8f9fa;
                font-style: italic;
            }
            QTextBrowser strong {
                font-weight: bold;
                color: #2c3e50;
            }
            QTextBrowser em {
                font-style: italic;
                color: #7f8c8d;
            }
            QTextBrowser table {
                border-collapse: collapse;
                width: 100%;
                margin: 6px 0;
                font-size: 11px;
                border: 1px solid #dee2e6;
                background-color: #ffffff;
            }
            QTextBrowser th {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 6px 8px;
                text-align: left;
                font-weight: bold;
                color: #495057;
            }
            QTextBrowser td {
                border: 1px solid #dee2e6;
                padding: 6px 8px;
                text-align: left;
                vertical-align: top;
                line-height: 1.3;
            }
        """)
        right_layout.addWidget(self.extension_response_display)
        
        # 応答制御ボタン
        response_button_layout = QHBoxLayout()
        
        self.clear_response_button = QPushButton("🗑️ クリア")
        self.clear_response_button.clicked.connect(self.clear_extension_response)
        self.clear_response_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        
        self.copy_response_button = QPushButton("📋 コピー")
        self.copy_response_button.clicked.connect(self.copy_extension_response)
        self.copy_response_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        
        response_button_layout.addWidget(self.clear_response_button)
        response_button_layout.addWidget(self.copy_response_button)
        response_button_layout.addStretch()
        
        right_layout.addLayout(response_button_layout)
        
        content_splitter.addWidget(right_widget)
        
        # 初期状態でボタンを読み込み
        try:
            self.load_extension_buttons()
        except Exception as e:
            logger.warning("AI拡張ボタンの読み込みに失敗しました: %s", e)
            # エラーメッセージを表示
            error_label = QLabel(f"AI拡張機能の初期化に失敗しました。\n\n設定ファイルを確認してください:\ninput/ai/ai_ext_conf.json\n\nエラー: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px; background-color: #fff8f8; border: 1px solid #ffcdd2; border-radius: 5px;")
            error_label.setWordWrap(True)
            error_label.setAlignment(Qt.AlignCenter)
            self.buttons_layout.addWidget(error_label)
        
        # データセット選択の初期化
        self.initialize_dataset_dropdown()
        
        # データセット選択のシグナル接続
        if hasattr(self, 'extension_dataset_combo'):
            self.extension_dataset_combo.currentTextChanged.connect(self.on_dataset_selection_changed)
        
    def load_extension_buttons(self):
        """AI拡張設定からボタンを読み込んで表示"""
        try:
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config
            config = load_ai_extension_config()
            
            # 既存のボタンをクリア
            for i in reversed(range(self.buttons_layout.count())):
                self.buttons_layout.itemAt(i).widget().setParent(None)
            
            ui_settings = config.get('ui_settings', {})
            buttons_per_row = ui_settings.get('buttons_per_row', 3)
            button_height = ui_settings.get('button_height', 60)
            button_width = ui_settings.get('button_width', 140)
            show_icons = ui_settings.get('show_icons', True)
            enable_categories = ui_settings.get('enable_categories', True)
            
            # ボタン設定を取得
            buttons_config = config.get('buttons', [])
            default_buttons = config.get('default_buttons', [])
            
            # 全ボタンをまとめる
            all_buttons = buttons_config + default_buttons
            
            if not all_buttons:
                no_buttons_label = QLabel("AI拡張ボタンが設定されていません。\n設定編集ボタンから設定ファイルを確認してください。")
                no_buttons_label.setStyleSheet("color: #666; text-align: center; padding: 20px;")
                no_buttons_label.setAlignment(Qt.AlignCenter)
                self.buttons_layout.addWidget(no_buttons_label)
                return
            
            # カテゴリ別にボタンを整理
            if enable_categories:
                categories = {}
                for button_config in all_buttons:
                    category = button_config.get('category', 'その他')
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(button_config)
                
                # カテゴリごとにボタンを作成
                for category_name, category_buttons in categories.items():
                    self.create_category_section(category_name, category_buttons, buttons_per_row, button_height, button_width, show_icons)
            else:
                # カテゴリなしでボタンを作成
                self.create_buttons_grid(all_buttons, buttons_per_row, button_height, button_width, show_icons)
            
            # 最後にストレッチを追加
            self.buttons_layout.addStretch()
            
        except Exception as e:
            error_label = QLabel(f"AI拡張設定の読み込みエラー: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 10px;")
            self.buttons_layout.addWidget(error_label)
    
    def create_category_section(self, category_name, buttons, buttons_per_row, button_height, button_width, show_icons):
        """カテゴリセクションを作成（シンプル版）"""
        # ボタンを1列に配置（カテゴリヘッダーは不要）
        for button_config in buttons:
            button = self.create_extension_button(button_config, button_height, button_width, show_icons)
            self.buttons_layout.addWidget(button)
    
    def create_buttons_grid(self, buttons, buttons_per_row, button_height, button_width, show_icons):
        """ボタングリッドを作成（カテゴリなし・シンプル版）"""
        # ボタンを1列に配置
        for button_config in buttons:
            button = self.create_extension_button(button_config, button_height, button_width, show_icons)
            self.buttons_layout.addWidget(button)
    
    def create_extension_button(self, button_config, button_height, button_width, show_icons):
        """AI拡張ボタンを作成（改良版）"""
        from classes.dataset.ui.spinner_button import SpinnerButton
        
        button_id = button_config.get('id', 'unknown')
        label = button_config.get('label', 'Unknown')
        description = button_config.get('description', '')
        icon = button_config.get('icon', '🤖') if show_icons else ''
        
        # ボタンテキスト（アイコン＋タイトル＋説明を統合）
        button_text = f"{icon} {label}"
        if description:
            # 説明が長い場合は短縮
            short_desc = description[:40] + "..." if len(description) > 40 else description
            button_text += f"\n{short_desc}"
        
        button = SpinnerButton(button_text)
        
        # ボタンサイズを調整（複数行テキスト対応）
        button.setMinimumHeight(max(50, button_height - 15))  # 説明文のため高さを確保
        button.setMaximumHeight(max(60, button_height - 5))
        button.setMinimumWidth(max(200, button_width - 40))
        button.setMaximumWidth(max(240, button_width - 20))
        
        # ツールチップ（詳細情報）
        tooltip_text = f"🔹 {label}"
        if description:
            tooltip_text += f"\n💡 {description}"
        tooltip_text += "\n\n右クリック: プロンプト編集"
        button.setToolTip(tooltip_text)
        
        # 改良されたボタンスタイル（複数行対応）
        button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #4CAF50, stop: 1 #45a049);
                color: white;
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                text-align: left;
                margin: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #66BB6A, stop: 1 #4CAF50);
                transform: scale(1.02);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #388E3C, stop: 1 #2E7D32);
            }
            QPushButton:disabled {
                background-color: #E0E0E0;
                color: #9E9E9E;
            }
        """)
        
        # ボタンにconfigを保存
        button.button_config = button_config
        
        # ボタンクリック時の処理
        button.clicked.connect(lambda checked, config=button_config: self.on_extension_button_clicked(config))
        
        # 右クリックメニューでプロンプト編集を追加
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, config=button_config, btn=button: self.show_button_context_menu(pos, config, btn))
        
        return button
    
    def on_extension_button_clicked(self, button_config):
        """AI拡張ボタンクリック時の処理"""
        try:
            button_id = button_config.get('id', 'unknown')
            label = button_config.get('label', 'Unknown')
            
            logger.debug("AI拡張ボタンクリック: %s (%s)", button_id, label)
            
            # senderからクリックされたボタンを取得
            clicked_button = self.sender()
            
            if clicked_button and hasattr(clicked_button, 'start_loading'):
                clicked_button.start_loading("AI処理中")
            
            # プロンプトを構築
            prompt = self.build_extension_prompt(button_config)
            
            if not prompt:
                if clicked_button:
                    clicked_button.stop_loading()
                QMessageBox.warning(self, "警告", "プロンプトの構築に失敗しました。")
                return
            
            # AI問い合わせを実行
            self.execute_extension_ai_request(prompt, button_config, clicked_button)
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"AI拡張ボタン処理エラー: {str(e)}")
    
    def build_extension_prompt(self, button_config):
        """AI拡張プロンプトを構築"""
        try:
            prompt_file = button_config.get('prompt_file')
            prompt_template = button_config.get('prompt_template')
            
            logger.debug("プロンプト構築開始 - prompt_file: %s, prompt_template: %s", prompt_file, bool(prompt_template))
            
            if prompt_file:
                # ファイルからプロンプトを読み込み
                from classes.dataset.util.ai_extension_helper import load_prompt_file
                template_content = load_prompt_file(prompt_file)
                if not template_content:
                    logger.warning("プロンプトファイルが読み込めません: %s", prompt_file)
                    # フォールバック用のシンプルプロンプト
                    template_content = f"""データセットについて分析してください。

データセット名: {{name}}
課題番号: {{grant_number}}
タイプ: {{dataset_type}}
既存説明: {{description}}

上記の情報を基に、「{button_config.get('label', 'AI分析')}」の観点から詳細な分析を行ってください。"""
            elif prompt_template:
                # 直接指定されたテンプレートを使用
                template_content = prompt_template
                logger.debug("直接指定されたテンプレートを使用")
            else:
                logger.warning("プロンプトファイルもテンプレートも指定されていません")
                # デフォルトプロンプト
                template_content = f"""データセットについて分析してください。

データセット名: {{name}}
課題番号: {{grant_number}}
タイプ: {{dataset_type}}
既存説明: {{description}}

上記の情報を基に、「{button_config.get('label', 'AI分析')}」の観点から詳細な分析を行ってください。"""
            
            # コンテキストデータを準備
            context_data = self.prepare_extension_context()
            logger.debug("コンテキストデータ準備完了: %s", list(context_data.keys()))
            
            # プロンプトを置換
            from classes.dataset.util.ai_extension_helper import format_prompt_with_context
            formatted_prompt = format_prompt_with_context(template_content, context_data)
            
            logger.debug("プロンプト構築完了 - 長さ: %s文字", len(formatted_prompt))
            return formatted_prompt
            
        except Exception as e:
            logger.error("AI拡張プロンプト構築エラー: %s", e)
            import traceback
            traceback.print_exc()
            return None
    
    def prepare_extension_context(self):
        """AI拡張用のコンテキストデータを準備"""
        try:
            # 基本コンテキストデータを確保
            if hasattr(self, 'context_data') and self.context_data:
                context_data = self.context_data.copy()
            else:
                # フォールバック用の基本データ
                context_data = {
                    'name': getattr(self, 'name_input', None).text() if hasattr(self, 'name_input') and self.name_input else "未設定",
                    'grant_number': getattr(self, 'grant_number_input', None).text() if hasattr(self, 'grant_number_input') and self.grant_number_input else "未設定",
                    'dataset_type': getattr(self, 'type_combo', None).currentText() if hasattr(self, 'type_combo') and self.type_combo else "未設定",
                    'description': getattr(self, 'description_input', None).toPlainText() if hasattr(self, 'description_input') and self.description_input else "未設定"
                }
                logger.warning("context_dataが初期化されていません。フォールバックデータを使用します。")
            
            # データセット選択による更新があった場合は最新情報を使用
            if hasattr(self, 'extension_dataset_combo') and self.extension_dataset_combo.currentIndex() > 0:
                selected_dataset = self.extension_dataset_combo.itemData(self.extension_dataset_combo.currentIndex())
                if selected_dataset:
                    attrs = selected_dataset.get('attributes', {})
                    context_data.update({
                        'name': attrs.get('name', context_data.get('name', '')),
                        'grant_number': attrs.get('grantNumber', context_data.get('grant_number', '')),
                        'dataset_type': attrs.get('datasetType', context_data.get('dataset_type', 'mixed')),
                        'description': attrs.get('description', context_data.get('description', '')),
                        'dataset_id': selected_dataset.get('id', '')
                    })
                    logger.debug("データセット選択による情報更新: %s", context_data['name'])
            
            # 追加のコンテキストデータを収集（可能な場合）
            try:
                from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
                context_collector = get_dataset_context_collector()
                
                dataset_id = context_data.get('dataset_id')
                if dataset_id:
                    # データセットIDを一時的に除外
                    context_data_without_id = {k: v for k, v in context_data.items() if k != 'dataset_id'}
                    
                    # 完全なコンテキストを収集
                    full_context = context_collector.collect_full_context(
                        dataset_id=dataset_id,
                        **context_data_without_id
                    )
                    
                    context_data.update(full_context)
            except Exception as context_error:
                logger.warning("拡張コンテキスト収集でエラー: %s", context_error)
                # エラーが発生してもbase contextで続行
            
            return context_data
            
        except Exception as e:
            logger.error("AI拡張コンテキスト準備エラー: %s", e)
            # 最小限のフォールバックデータ
            return {
                'name': "データセット名未設定",
                'grant_number': "課題番号未設定", 
                'dataset_type': "タイプ未設定",
                'description': "説明未設定"
            }
    
    def execute_extension_ai_request(self, prompt, button_config, button_widget):
        """AI拡張リクエストを実行"""
        try:
            # AIリクエストスレッドを作成・実行
            ai_thread = AIRequestThread(prompt, self.context_data)
            
            # スレッドリストに追加（管理用）
            self.extension_ai_threads.append(ai_thread)
            
            # スレッド完了時のコールバック
            def on_success(result):
                try:
                    response_text = result.get('response') or result.get('content', '')
                    if response_text:
                        # 応答をフォーマットして表示
                        formatted_response = self.format_extension_response(response_text, button_config)
                        self.extension_response_display.setHtml(formatted_response)
                    else:
                        self.extension_response_display.setText("AI応答が空でした。")
                finally:
                    if button_widget:
                        button_widget.stop_loading()
                    # 完了したスレッドをリストから削除
                    if ai_thread in self.extension_ai_threads:
                        self.extension_ai_threads.remove(ai_thread)
            
            def on_error(error_message):
                try:
                    self.extension_response_display.setText(f"エラー: {error_message}")
                finally:
                    if button_widget:
                        button_widget.stop_loading()
                    # エラー時もスレッドをリストから削除
                    if ai_thread in self.extension_ai_threads:
                        self.extension_ai_threads.remove(ai_thread)
            
            ai_thread.result_ready.connect(on_success)
            ai_thread.error_occurred.connect(on_error)
            ai_thread.start()
            
        except Exception as e:
            if button_widget:
                button_widget.stop_loading()
            QMessageBox.critical(self, "エラー", f"AI拡張リクエスト実行エラー: {str(e)}")
    
    def format_extension_response(self, response_text, button_config):
        """AI拡張応答をフォーマット（マークダウン対応）"""
        try:
            label = button_config.get('label', 'AI拡張')
            icon = button_config.get('icon', '🤖')
            timestamp = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # マークダウンをHTMLに変換
            html_content = self.convert_markdown_to_html(response_text)
            
            # HTMLフォーマット（コンパクトヘッダー付き）
            formatted_html = f"""
            <div style="border: 1px solid #e1e5e9; border-radius: 6px; padding: 0; margin: 3px 0; background-color: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 8px 12px; border-radius: 6px 6px 0 0; margin-bottom: 0;">
                    <h3 style="margin: 0; font-size: 14px; font-weight: bold;">{icon} {label}</h3>
                    <small style="opacity: 0.9; font-size: 10px;">実行時刻: {timestamp}</small>
                </div>
                <div style="padding: 10px; line-height: 1.3; font-family: 'Yu Gothic', 'Meiryo', sans-serif;">
                    {html_content}
                </div>
            </div>
            """
            
            return formatted_html
            
        except Exception as e:
            logger.error("AI拡張応答フォーマットエラー: %s", e)
            # フォールバック
            import html
            escaped_text = html.escape(response_text)
            return f"<div style='padding: 10px; border: 1px solid #ccc;'><pre>{escaped_text}</pre></div>"
    
    def convert_markdown_to_html(self, markdown_text):
        """シンプルなマークダウン→HTML変換"""
        try:
            import re
            html_text = markdown_text
            
            # HTMLエスケープ
            import html
            html_text = html.escape(html_text)
            
            # マークダウン要素をHTMLに変換
            
            # ヘッダー（### → h3, ## → h2, # → h1）
            html_text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_text, flags=re.MULTILINE)
            html_text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_text, flags=re.MULTILINE)
            html_text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_text, flags=re.MULTILINE)
            
            # 太字（**text** → <strong>text</strong>）
            html_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_text)
            
            # 斜体（*text* → <em>text</em>）
            html_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_text)
            
            # インラインコード（`code` → <code>code</code>）
            html_text = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_text)
            
            # マークダウンテーブル変換を先に処理
            html_text = self.convert_markdown_tables(html_text)
            
            # リスト項目（- item → <li>item</li>）
            lines = html_text.split('\n')
            in_list = False
            in_table = False
            result_lines = []
            
            for line in lines:
                stripped = line.strip()
                
                # テーブル行の判定（既に変換済みのHTMLテーブルはスキップ）
                if '<table' in line or '</table>' in line or '<tr>' in line or '</tr>' in line:
                    in_table = True
                    result_lines.append(line)
                    if '</table>' in line:
                        in_table = False
                    continue
                
                if in_table:
                    result_lines.append(line)
                    continue
                
                if re.match(r'^[-*+]\s+', stripped):
                    if not in_list:
                        result_lines.append('<ul>')
                        in_list = True
                    item_text = re.sub(r'^[-*+]\s+', '', stripped)
                    result_lines.append(f'<li>{item_text}</li>')
                else:
                    if in_list:
                        result_lines.append('</ul>')
                        in_list = False
                    if stripped:  # 空行でない場合
                        result_lines.append(f'<p>{line}</p>')
                    else:
                        # 空行は少ない間隔にする
                        result_lines.append('<div style="margin: 2px 0;"></div>')
            
            if in_list:
                result_lines.append('</ul>')
            
            html_text = '\n'.join(result_lines)
            
            # コードブロック（```code``` → <pre><code>code</code></pre>）- コンパクトスタイル
            html_text = re.sub(
                r'```([^`]*?)```', 
                r'<pre style="background-color: #f8f9fa; padding: 6px; border-radius: 3px; border: 1px solid #e9ecef; overflow-x: auto; margin: 4px 0;"><code>\1</code></pre>', 
                html_text, 
                flags=re.DOTALL
            )
            
            # 引用（> text → <blockquote>text</blockquote>）
            html_text = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', html_text, flags=re.MULTILINE)
            
            return html_text
            
        except Exception as e:
            logger.warning("マークダウン変換エラー: %s", e)
            # エラー時はプレーンテキストをHTMLエスケープして返す
            import html
            return f"<pre>{html.escape(markdown_text)}</pre>"
    
    def convert_markdown_tables(self, text):
        """マークダウンテーブルをHTMLテーブルに変換"""
        try:
            import re
            lines = text.split('\n')
            result_lines = []
            in_table = False
            table_lines = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # テーブル行の判定（|で始まって|で終わる、または|を含む）
                if '|' in stripped and len(stripped.split('|')) >= 3:
                    # セパレータ行の判定（|:---|---|:---|のような行）
                    is_separator = re.match(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$', stripped)
                    
                    if not in_table:
                        in_table = True
                        table_lines = []
                    
                    if is_separator:
                        # セパレータ行は無視してテーブルヘッダーを確定
                        continue
                    else:
                        table_lines.append(stripped)
                else:
                    # テーブル以外の行
                    if in_table:
                        # テーブル終了 - HTMLテーブルを生成
                        html_table = self.build_html_table(table_lines)
                        result_lines.append(html_table)
                        in_table = False
                        table_lines = []
                    
                    result_lines.append(line)
            
            # 最後にテーブルがある場合
            if in_table and table_lines:
                html_table = self.build_html_table(table_lines)
                result_lines.append(html_table)
            
            return '\n'.join(result_lines)
            
        except Exception as e:
            logger.warning("テーブル変換エラー: %s", e)
            return text
    
    def build_html_table(self, table_lines):
        """テーブル行のリストからHTMLテーブルを構築"""
        try:
            if not table_lines:
                return ""
            
            html_parts = ['<table>']
            
            for i, line in enumerate(table_lines):
                # 行をセルに分割
                cells = [cell.strip() for cell in line.split('|')]
                # 最初と最後の空セルを除去
                if cells and not cells[0]:
                    cells = cells[1:]
                if cells and not cells[-1]:
                    cells = cells[:-1]
                
                if not cells:
                    continue
                
                html_parts.append('<tr>')
                
                # 最初の行はヘッダーとして扱う
                if i == 0:
                    for cell in cells:
                        html_parts.append(f'<th>{cell}</th>')
                else:
                    for cell in cells:
                        html_parts.append(f'<td>{cell}</td>')
                
                html_parts.append('</tr>')
            
            html_parts.append('</table>')
            
            return '\n'.join(html_parts)
            
        except Exception as e:
            logger.warning("HTMLテーブル構築エラー: %s", e)
            return '\n'.join(table_lines)
    
    def edit_extension_config(self):
        """AI拡張設定ファイルを編集"""
        try:
            from classes.dataset.ui.ai_extension_prompt_edit_dialog import AIExtensionPromptEditDialog
            
            # 設定ファイルのパスを取得
            config_path = "input/ai/ai_ext_conf.json"
            
            # プロンプト編集ダイアログを表示（設定ファイル編集モード）
            dialog = AIExtensionPromptEditDialog(
                parent=self,
                prompt_file_path=config_path,
                button_config={
                    'label': 'AI拡張設定',
                    'description': 'AI拡張機能の設定ファイル'
                }
            )
            
            # 更新時にボタンを再読み込み
            dialog.prompt_updated.connect(lambda: self.load_extension_buttons())
            
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定編集エラー: {str(e)}")
    
    def clear_extension_response(self):
        """AI拡張応答をクリア"""
        self.extension_response_display.clear()
    
    def copy_extension_response(self):
        """AI拡張応答をクリップボードにコピー"""
        try:
            from qt_compat.widgets import QApplication
            # QTextBrowserからプレーンテキストを取得
            text = self.extension_response_display.toPlainText()
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                QMessageBox.information(self, "コピー完了", "応答内容をクリップボードにコピーしました。")
            else:
                QMessageBox.warning(self, "警告", "コピーする内容がありません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コピーエラー: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コピーエラー: {str(e)}")
    
    def show_button_context_menu(self, position, button_config, button_widget):
        """ボタンの右クリックメニューを表示"""
        try:
            from qt_compat.widgets import QMenu, QAction
            
            menu = QMenu(button_widget)
            
            # プロンプト編集アクション
            edit_action = QAction("📝 プロンプト編集", menu)
            edit_action.triggered.connect(lambda: self.edit_button_prompt(button_config))
            menu.addAction(edit_action)
            
            # プロンプトプレビューアクション
            preview_action = QAction("👁️ プロンプトプレビュー", menu)
            preview_action.triggered.connect(lambda: self.preview_button_prompt(button_config))
            menu.addAction(preview_action)
            
            # メニューを表示
            global_pos = button_widget.mapToGlobal(position)
            menu.exec_(global_pos)
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コンテキストメニューエラー: {str(e)}")
    
    def edit_button_prompt(self, button_config):
        """ボタンのプロンプトを編集"""
        try:
            prompt_file = button_config.get('prompt_file')
            
            if prompt_file:
                # ファイルベースのプロンプトを編集
                from classes.dataset.ui.ai_extension_prompt_edit_dialog import AIExtensionPromptEditDialog
                
                dialog = AIExtensionPromptEditDialog(
                    parent=self,
                    prompt_file_path=prompt_file,
                    button_config=button_config
                )
                
                dialog.exec()
            else:
                # デフォルトテンプレートの場合は新しいファイルを作成するか尋ねる
                reply = QMessageBox.question(
                    self,
                    "プロンプトファイル作成",
                    f"ボタン '{button_config.get('label', 'Unknown')}' はデフォルトテンプレートを使用しています。\n"
                    "プロンプトファイルを作成して編集しますか？",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    # 新しいプロンプトファイルパスを生成
                    button_id = button_config.get('id', 'unknown')
                    new_prompt_file = f"input/ai/prompts/ext/{button_id}.txt"
                    
                    # デフォルトテンプレートを初期内容として使用
                    initial_content = button_config.get('prompt_template', self.get_default_template_for_button(button_config))
                    
                    # ファイルを作成
                    from classes.dataset.util.ai_extension_helper import save_prompt_file
                    if save_prompt_file(new_prompt_file, initial_content):
                        # 設定ファイルを更新（今後の拡張で実装）
                        QMessageBox.information(
                            self,
                            "ファイル作成完了",
                            f"プロンプトファイルを作成しました:\n{new_prompt_file}\n\n"
                            "設定ファイルの更新は手動で行ってください。"
                        )
                        
                        # 編集ダイアログを開く
                        dialog = AIExtensionPromptEditDialog(
                            parent=self,
                            prompt_file_path=new_prompt_file,
                            button_config=button_config
                        )
                        dialog.exec()
                    else:
                        QMessageBox.critical(self, "エラー", "プロンプトファイルの作成に失敗しました。")
                        
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロンプト編集エラー: {str(e)}")
    
    def preview_button_prompt(self, button_config):
        """ボタンのプロンプトをプレビュー"""
        try:
            prompt = self.build_extension_prompt(button_config)
            
            if prompt:
                # プレビューダイアログを表示
                from qt_compat.widgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
                
                preview_dialog = QDialog(self)
                preview_dialog.setWindowTitle(f"プロンプトプレビュー: {button_config.get('label', 'Unknown')}")
                preview_dialog.resize(700, 500)
                
                layout = QVBoxLayout(preview_dialog)
                
                preview_text = QTextEdit()
                preview_text.setReadOnly(True)
                preview_text.setText(prompt)
                layout.addWidget(preview_text)
                
                close_button = QPushButton("閉じる")
                close_button.clicked.connect(preview_dialog.close)
                layout.addWidget(close_button)
                
                preview_dialog.exec()
            else:
                QMessageBox.warning(self, "警告", "プロンプトの構築に失敗しました。")
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロンプトプレビューエラー: {str(e)}")
    
    def get_default_template_for_button(self, button_config):
        """ボタン用のデフォルトテンプレートを取得"""
        button_id = button_config.get('id', 'unknown')
        label = button_config.get('label', 'Unknown')
        
        return f"""データセットについて{label}を分析してください。

【データセット情報】
- 名前: {{name}}
- タイプ: {{type}}
- 課題番号: {{grant_number}}
- 説明: {{description}}

【実験データ】
{{experiment_data}}

【分析指示】
上記データセット情報を基に、{label}の観点から分析してください。

【出力形式】
分析結果を詳しく説明し、200文字程度で要約してください。

日本語で詳細に分析してください。"""
    
    def cleanup_threads(self):
        """すべてのスレッドをクリーンアップ"""
        try:
            # メインAIスレッドの停止
            if self.ai_thread and self.ai_thread.isRunning():
                logger.debug("メインAIスレッドを停止中...")
                self.ai_thread.stop()
                self.ai_thread.wait(3000)  # 3秒まで待機
                if self.ai_thread.isRunning():
                    logger.warning("メインAIスレッドの強制終了")
                    self.ai_thread.terminate()
            
            # AI拡張スレッドの停止
            for thread in self.extension_ai_threads:
                if thread and thread.isRunning():
                    logger.debug("AI拡張スレッドを停止中...")
                    thread.stop()
                    thread.wait(3000)  # 3秒まで待機
                    if thread.isRunning():
                        logger.warning("AI拡張スレッドの強制終了")
                        thread.terminate()
            
            # スレッドリストをクリア
            self.extension_ai_threads.clear()
            logger.debug("すべてのスレッドのクリーンアップ完了")
            
        except Exception as e:
            logger.error("スレッドクリーンアップエラー: %s", e)
    
    def closeEvent(self, event):
        """ダイアログクローズ時の処理"""
        try:
            logger.debug("AISuggestionDialog終了処理開始")
            self.cleanup_threads()
            event.accept()
        except Exception as e:
            logger.error("ダイアログクローズエラー: %s", e)
            event.accept()
    
    def reject(self):
        """キャンセル時の処理"""
        try:
            logger.debug("AISuggestionDialogキャンセル処理開始")
            self.cleanup_threads()
            super().reject()
        except Exception as e:
            logger.error("ダイアログキャンセルエラー: %s", e)
            super().reject()
    
    def accept(self):
        """OK時の処理"""
        try:
            logger.debug("AISuggestionDialog完了処理開始")
            self.cleanup_threads()
            super().accept()
        except Exception as e:
            logger.error("ダイアログ完了エラー: %s", e)
            super().accept()
    
    def initialize_dataset_dropdown(self):
        """データセット選択ドロップダウンを初期化"""
        if not hasattr(self, 'extension_dataset_combo'):
            logger.debug("extension_dataset_combo が存在しません")
            return
            
        try:
            from config.common import get_dynamic_file_path
            from classes.dataset.util.dataset_dropdown_util import load_dataset_list
            import os
            
            logger.debug("データセット選択初期化を開始")
            
            # dataset.jsonのパス
            dataset_json_path = get_dynamic_file_path('output/rde/data/dataset.json')
            info_json_path = get_dynamic_file_path('output/rde/data/info.json')
            
            logger.debug("dataset.jsonパス: %s", dataset_json_path)
            logger.debug("ファイル存在確認: %s", os.path.exists(dataset_json_path))
            
            # データセット一覧を読み込み
            self.load_datasets_to_combo(dataset_json_path, info_json_path)
            
            # 現在のコンテキストに基づいて選択
            self.select_current_dataset()
            
            logger.debug("データセット選択初期化完了")
            
        except Exception as e:
            logger.error("データセット選択初期化エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def load_datasets_to_combo(self, dataset_json_path, info_json_path):
        """データセット一覧をコンボボックスに読み込み（検索補完機能付き）"""
        try:
            from classes.dataset.util.dataset_dropdown_util import load_dataset_list
            
            # データセット一覧を取得
            datasets = load_dataset_list(dataset_json_path)
            
            # コンボボックスをクリア
            self.extension_dataset_combo.clear()
            
            # 既存のCompleterがあればクリア
            if self.extension_dataset_combo.completer():
                self.extension_dataset_combo.completer().deleteLater()
            
            # 表示名のリストを作成（検索補完用）
            display_names = []
            
            # データセット一覧を追加
            for dataset_info in datasets:
                dataset_id = dataset_info.get('id', '')
                display_name = dataset_info.get('display', '名前なし')
                
                # アイテムを追加
                self.extension_dataset_combo.addItem(display_name, dataset_info)
                display_names.append(display_name)
            
            # QCompleterを設定（修正タブと同じ実装）
            from qt_compat.widgets import QCompleter
            from qt_compat.core import Qt
            
            completer = QCompleter(display_names, self.extension_dataset_combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            
            # 検索時の補完リスト（popup）の高さを12行分に制限
            popup_view = completer.popup()
            popup_view.setMinimumHeight(240)
            popup_view.setMaximumHeight(240)
            
            self.extension_dataset_combo.setCompleter(completer)
            
            # データセットキャッシュを保存（修正タブと同様）
            self.extension_dataset_combo._datasets_cache = datasets
            self.extension_dataset_combo._display_names_cache = display_names
            
            # プレースホルダーテキストを更新
            if self.extension_dataset_combo.lineEdit():
                self.extension_dataset_combo.lineEdit().setPlaceholderText(f"データセット ({len(datasets)}件) から検索・選択してください")
            
            # マウスクリック時の全件表示機能を追加（修正タブと同様）
            self.setup_mouse_click_handler()
            
            logger.debug("データセット %s件を読み込みました", len(datasets))
            
            # データセット選択変更のイベントハンドラを接続
            self.extension_dataset_combo.currentIndexChanged.connect(self.on_dataset_selection_changed)
            
        except Exception as e:
            logger.error("データセット読み込みエラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def select_current_dataset(self):
        """現在のコンテキストに基づいてデータセットを選択"""
        if not hasattr(self, 'extension_dataset_combo'):
            return
            
        try:
            # コンテキストからデータセット名または課題番号を取得
            current_name = self.context_data.get('name', '').strip()
            current_grant_number = self.context_data.get('grant_number', '').strip()
            
            if current_name or current_grant_number:
                # コンボボックスから一致するアイテムを検索
                for i in range(self.extension_dataset_combo.count()):
                    text = self.extension_dataset_combo.itemText(i)
                    dataset = self.extension_dataset_combo.itemData(i)
                    
                    if dataset:
                        attrs = dataset.get('attributes', {})
                        name = attrs.get('name', '')
                        grant_number = attrs.get('grantNumber', '')
                        
                        # 名前または課題番号で一致判定
                        if (current_name and current_name == name) or \
                           (current_grant_number and current_grant_number == grant_number):
                            self.extension_dataset_combo.setCurrentIndex(i)
                            logger.debug("データセット自動選択: %s", text)
                            return
            
        except Exception as e:
            logger.error("データセット自動選択エラー: %s", e)
    
    def on_dataset_selection_changed(self, text):
        """データセット選択変更時の処理"""
        try:
            if not hasattr(self, 'extension_dataset_combo'):
                return
                
            current_index = self.extension_dataset_combo.currentIndex()
            if current_index <= 0:  # "選択してください"が選択された場合
                return
            
            # 選択されたデータセットを取得
            dataset_info = self.extension_dataset_combo.itemData(current_index)
            if not dataset_info:
                return
            
            # コンテキストデータを更新
            self.update_context_from_dataset(dataset_info)
            
            # データセット情報表示を更新
            self.update_dataset_info_display()
            
            logger.debug("データセット選択変更: %s", text)
            
        except Exception as e:
            logger.error("データセット選択変更エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_context_from_dataset(self, dataset_info):
        """選択されたデータセット情報からコンテキストデータを更新"""
        try:
            # dataset_infoの形式を確認
            if 'attributes' in dataset_info:
                # dataset.json形式の場合
                attrs = dataset_info.get('attributes', {})
                self.context_data['dataset_id'] = dataset_info.get('id', '')
                self.context_data['name'] = attrs.get('name', '')
                self.context_data['grant_number'] = attrs.get('grantNumber', '')
                self.context_data['type'] = attrs.get('datasetType', 'mixed')
                self.context_data['description'] = attrs.get('description', '')
            else:
                # load_dataset_list形式の場合
                self.context_data['dataset_id'] = dataset_info.get('id', '')
                self.context_data['name'] = dataset_info.get('name', '')
                self.context_data['grant_number'] = dataset_info.get('grantNumber', '')
                self.context_data['type'] = dataset_info.get('datasetType', 'mixed')
                self.context_data['description'] = dataset_info.get('description', '')
            
            # アクセスポリシーとコンタクト情報をデフォルト値で設定
            if 'access_policy' not in self.context_data:
                self.context_data['access_policy'] = 'restricted'
            if 'contact' not in self.context_data:
                self.context_data['contact'] = ''
            
            logger.debug("コンテキストデータ更新: dataset_id=%s, name=%s", self.context_data.get('dataset_id', ''), self.context_data.get('name', ''))
            
        except Exception as e:
            logger.error("コンテキストデータ更新エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_dataset_info_display(self):
        """データセット情報表示を更新"""
        try:
            # データセット情報を取得
            dataset_name = self.context_data.get('name', '').strip()
            grant_number = self.context_data.get('grant_number', '').strip()
            dataset_type = self.context_data.get('type', '').strip()
            
            if not dataset_name:
                dataset_name = "データセット名未設定"
            if not grant_number:
                grant_number = "課題番号未設定"
            if not dataset_type:
                dataset_type = "タイプ未設定"
            
            # HTMLを更新
            dataset_info_html = f"""
        <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 10px; margin: 5px 0;">
            <h4 style="margin: 0 0 8px 0; color: #495057;">📊 対象データセット情報</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="font-weight: bold; color: #6c757d; padding: 2px 10px 2px 0; width: 100px;">データセット名:</td>
                    <td style="color: #212529; padding: 2px 0;">{dataset_name}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #6c757d; padding: 2px 10px 2px 0;">課題番号:</td>
                    <td style="color: #212529; padding: 2px 0;">{grant_number}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #6c757d; padding: 2px 10px 2px 0;">タイプ:</td>
                    <td style="color: #212529; padding: 2px 0;">{dataset_type}</td>
                </tr>
            </table>
        </div>
        """
            
            # dataset_info_labelがある場合のみ更新
            if hasattr(self, 'dataset_info_label') and self.dataset_info_label:
                self.dataset_info_label.setText(dataset_info_html)
            
        except Exception as e:
            logger.error("データセット情報表示更新エラー: %s", e)
    
    def show_all_datasets(self):
        """全データセット表示（▼ボタン用）"""
        try:
            if hasattr(self, 'extension_dataset_combo'):
                self.extension_dataset_combo.showPopup()
        except Exception as e:
            logger.error("全データセット表示エラー: %s", e)
    
    def setup_mouse_click_handler(self):
        """マウスクリック時の全件表示機能を設定（修正タブと同様）"""
        try:
            if not hasattr(self.extension_dataset_combo, '_mouse_press_event_set'):
                orig_mouse_press = self.extension_dataset_combo.mousePressEvent
                
                def combo_mouse_press_event(event):
                    if not self.extension_dataset_combo.lineEdit().text():
                        # コンボボックスをクリア
                        self.extension_dataset_combo.clear()
                        
                        # キャッシュされたデータセット一覧と表示名を使用
                        cached_datasets = getattr(self.extension_dataset_combo, '_datasets_cache', [])
                        cached_display_names = getattr(self.extension_dataset_combo, '_display_names_cache', [])
                        
                        logger.debug("AI拡張 - コンボボックス展開: %s件のデータセット", len(cached_datasets))
                        
                        # データセット一覧を再設定
                        if cached_datasets and cached_display_names:
                            for i, dataset_info in enumerate(cached_datasets):
                                display_name = cached_display_names[i] if i < len(cached_display_names) else '名前なし'
                                self.extension_dataset_combo.addItem(display_name, dataset_info)
                        else:
                            # フォールバック：キャッシュがない場合
                            self.extension_dataset_combo.addItem("-- データセットを選択してください --", None)
                    
                    self.extension_dataset_combo.showPopup()
                    orig_mouse_press(event)
                
                self.extension_dataset_combo.mousePressEvent = combo_mouse_press_event
                self.extension_dataset_combo._mouse_press_event_set = True
                
        except Exception as e:
            logger.error("マウスクリックハンドラ設定エラー: %s", e)
