"""
AI設定ウィジェット - ARIM RDE Tool
AIテスト機能用のLLM設定を管理するウィジェット

機能:
- プロバイダー（OpenAI、Gemini、ローカルLLM）の設定
- モデル選択
- API Key設定
- ローカルLLM URL設定
- 設定の保存・読み込み
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox,
        QGroupBox, QGridLayout, QScrollArea, QTextEdit,
        QSpinBox, QDoubleSpinBox, QMessageBox, QFormLayout,
        QProgressBar, QSplitter
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QThread
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス定義
    class QWidget: pass
    class pyqtSignal: pass

# ログ設定
logger = logging.getLogger(__name__)

# パス管理
try:
    from config.common import get_dynamic_file_path
except ImportError:
    def get_dynamic_file_path(relative_path):
        return relative_path

class AISettingsWidget(QWidget):
    """AI設定ウィジェット"""
    
    # シグナル定義
    settings_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.config_file_path = get_dynamic_file_path("input/ai_config.json")
        self.current_config = {}
        
        # UI要素の参照
        self.provider_widgets = {}
        self.default_provider_combo = None
        self.timeout_spinbox = None
        self.max_tokens_spinbox = None
        self.temperature_spinbox = None
        
        self.setup_ui()
        self.load_current_settings()
    
    def setup_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("AI設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(15)
        
        # グローバル設定
        self.setup_global_settings(content_layout)
        
        # プロバイダー設定
        self.setup_provider_settings(content_layout)
        
        # テスト機能
        self.setup_test_section(content_layout)
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        # ボタンエリア
        self.setup_buttons(layout)
    
    def setup_global_settings(self, layout):
        """グローバル設定セクション"""
        group = QGroupBox("グローバル設定")
        group_layout = QFormLayout(group)
        
        # デフォルトプロバイダー
        self.default_provider_combo = QComboBox()
        self.default_provider_combo.addItems(["openai", "gemini", "local_llm"])
        group_layout.addRow("デフォルトプロバイダー:", self.default_provider_combo)
        
        # タイムアウト
        self.timeout_spinbox = QSpinBox()
        self.timeout_spinbox.setRange(1, 300)
        self.timeout_spinbox.setValue(30)
        self.timeout_spinbox.setSuffix(" 秒")
        group_layout.addRow("タイムアウト:", self.timeout_spinbox)
        
        # 最大トークン数
        self.max_tokens_spinbox = QSpinBox()
        self.max_tokens_spinbox.setRange(1, 10000)
        self.max_tokens_spinbox.setValue(1000)
        group_layout.addRow("最大トークン数:", self.max_tokens_spinbox)
        
        # 温度パラメータ
        self.temperature_spinbox = QDoubleSpinBox()
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setValue(0.7)
        group_layout.addRow("温度パラメータ:", self.temperature_spinbox)
        
        layout.addWidget(group)
    
    def setup_provider_settings(self, layout):
        """プロバイダー設定セクション"""
        # OpenAI設定
        self.setup_openai_settings(layout)
        
        # Gemini設定
        self.setup_gemini_settings(layout)
        
        # ローカルLLM設定
        self.setup_local_llm_settings(layout)
    
    def setup_openai_settings(self, layout):
        """OpenAI設定"""
        group = QGroupBox("OpenAI設定")
        group_layout = QVBoxLayout(group)
        
        # 有効化チェックボックス
        enabled_checkbox = QCheckBox("OpenAIを有効にする")
        group_layout.addWidget(enabled_checkbox)
        
        # 設定フォーム
        form_layout = QFormLayout()
        
        # API Key
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.Password)
        api_key_edit.setPlaceholderText("OpenAI API Keyを入力...")
        form_layout.addRow("API Key:", api_key_edit)
        
        # Base URL
        base_url_edit = QLineEdit()
        base_url_edit.setText("https://api.openai.com/v1")
        form_layout.addRow("Base URL:", base_url_edit)
        
        # デフォルトモデル
        default_model_combo = QComboBox()
        default_model_combo.setEditable(True)
        default_model_combo.addItems([
            "gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"
        ])
        form_layout.addRow("デフォルトモデル:", default_model_combo)
        
        # 利用可能モデル
        models_label = QLabel("利用可能モデル:")
        models_edit = QTextEdit()
        models_edit.setMaximumHeight(100)
        models_edit.setPlainText("gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo")
        form_layout.addRow(models_label, models_edit)
        
        group_layout.addLayout(form_layout)
        
        # ウィジェット参照を保存
        self.provider_widgets['openai'] = {
            'enabled': enabled_checkbox,
            'api_key': api_key_edit,
            'base_url': base_url_edit,
            'default_model': default_model_combo,
            'models': models_edit
        }
        
        layout.addWidget(group)
    
    def setup_gemini_settings(self, layout):
        """Gemini設定"""
        group = QGroupBox("Gemini設定")
        group_layout = QVBoxLayout(group)
        
        # 有効化チェックボックス
        enabled_checkbox = QCheckBox("Geminiを有効にする")
        group_layout.addWidget(enabled_checkbox)
        
        # 設定フォーム
        form_layout = QFormLayout()
        
        # API Key
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.Password)
        api_key_edit.setPlaceholderText("Gemini API Keyを入力...")
        form_layout.addRow("API Key:", api_key_edit)
        
        # Base URL
        base_url_edit = QLineEdit()
        base_url_edit.setText("https://generativelanguage.googleapis.com/v1beta")
        form_layout.addRow("Base URL:", base_url_edit)
        
        # デフォルトモデル
        default_model_combo = QComboBox()
        default_model_combo.setEditable(True)
        default_model_combo.addItems([
            "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"
        ])
        form_layout.addRow("デフォルトモデル:", default_model_combo)
        
        # 利用可能モデル
        models_label = QLabel("利用可能モデル:")
        models_edit = QTextEdit()
        models_edit.setMaximumHeight(100)
        models_edit.setPlainText("gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash, gemini-1.0-pro")
        form_layout.addRow(models_label, models_edit)
        
        group_layout.addLayout(form_layout)
        
        # ウィジェット参照を保存
        self.provider_widgets['gemini'] = {
            'enabled': enabled_checkbox,
            'api_key': api_key_edit,
            'base_url': base_url_edit,
            'default_model': default_model_combo,
            'models': models_edit
        }
        
        layout.addWidget(group)
    
    def setup_local_llm_settings(self, layout):
        """ローカルLLM設定"""
        group = QGroupBox("ローカルLLM設定")
        group_layout = QVBoxLayout(group)
        
        # 有効化チェックボックス
        enabled_checkbox = QCheckBox("ローカルLLMを有効にする")
        group_layout.addWidget(enabled_checkbox)
        
        # 設定フォーム
        form_layout = QFormLayout()
        
        # Base URL（ローカルLLMの場合はAPI Keyの代わり）
        base_url_edit = QLineEdit()
        base_url_edit.setText("http://localhost:11434/api/generate")
        base_url_edit.setPlaceholderText("ローカルLLMサーバーのURLを入力...")
        form_layout.addRow("サーバーURL:", base_url_edit)
        
        # デフォルトモデル
        default_model_combo = QComboBox()
        default_model_combo.setEditable(True)
        default_model_combo.addItems([
            "llama3.1:8b", "gemma3:1b", "gemma3:4b", "deepseek-r1:7b"
        ])
        form_layout.addRow("デフォルトモデル:", default_model_combo)
        
        # 利用可能モデル
        models_label = QLabel("利用可能モデル:")
        models_edit = QTextEdit()
        models_edit.setMaximumHeight(120)
        models_edit.setPlainText("llama3.1:8b, gemma3:1b, gemma3:4b, deepseek-r1:7b")
        form_layout.addRow(models_label, models_edit)
        
        # 注意事項
        note_label = QLabel("注意: Ollama等のローカルLLMサーバーが必要です。")
        note_label.setStyleSheet("color: #666; font-style: italic;")
        form_layout.addRow("", note_label)
        
        group_layout.addLayout(form_layout)
        
        # ウィジェット参照を保存（ローカルLLMはAPI Keyがない）
        self.provider_widgets['local_llm'] = {
            'enabled': enabled_checkbox,
            'base_url': base_url_edit,
            'default_model': default_model_combo,
            'models': models_edit
        }
        
        layout.addWidget(group)
    
    def setup_test_section(self, layout):
        """AIテストセクション"""
        group = QGroupBox("AIテスト機能")
        group_layout = QVBoxLayout(group)
        
        # 説明
        info_label = QLabel(
            "現在の設定でAIプロバイダーとの接続および動作をテストできます。\n"
            "テストは保存された設定またはフォーム内容を使用します。"
        )
        info_label.setWordWrap(True)
        group_layout.addWidget(info_label)
        
        # テストプロバイダー選択
        test_form_layout = QFormLayout()
        
        self.test_provider_combo = QComboBox()
        self.test_provider_combo.addItems(["デフォルト", "openai", "gemini", "local_llm"])
        test_form_layout.addRow("テストプロバイダー:", self.test_provider_combo)
        
        self.test_model_combo = QComboBox()
        self.test_model_combo.setEditable(True)
        test_form_layout.addRow("テストモデル:", self.test_model_combo)
        
        # プロバイダー変更時にモデルリストを更新
        self.test_provider_combo.currentTextChanged.connect(self.update_test_models)
        
        group_layout.addLayout(test_form_layout)
        
        # カスタムプロンプト入力
        prompt_label = QLabel("カスタムプロンプト（オプション）:")
        group_layout.addWidget(prompt_label)
        
        self.custom_prompt_edit = QTextEdit()
        self.custom_prompt_edit.setMaximumHeight(80)
        self.custom_prompt_edit.setPlaceholderText("カスタムプロンプトを入力（空の場合は接続テスト用プロンプトを使用）")
        group_layout.addWidget(self.custom_prompt_edit)
        
        # テストボタン
        test_button_layout = QHBoxLayout()
        
        self.connection_test_button = QPushButton("接続テスト")
        self.connection_test_button.clicked.connect(self.run_connection_test)
        test_button_layout.addWidget(self.connection_test_button)
        
        self.prompt_test_button = QPushButton("プロンプトテスト")
        self.prompt_test_button.clicked.connect(self.run_prompt_test)
        test_button_layout.addWidget(self.prompt_test_button)
        
        test_button_layout.addStretch()
        group_layout.addLayout(test_button_layout)
        
        # プログレスバー
        self.test_progress_bar = QProgressBar()
        self.test_progress_bar.setVisible(False)
        group_layout.addWidget(self.test_progress_bar)
        
        # 結果表示エリア
        result_label = QLabel("テスト結果:")
        group_layout.addWidget(result_label)
        
        self.test_result_area = QTextEdit()
        self.test_result_area.setMaximumHeight(200)
        self.test_result_area.setReadOnly(True)
        self.test_result_area.setPlaceholderText("テスト結果がここに表示されます...")
        group_layout.addWidget(self.test_result_area)
        
        layout.addWidget(group)
    
    def setup_buttons(self, layout):
        """ボタンエリア"""
        button_layout = QHBoxLayout()
        
        # 設定テストボタン
        test_button = QPushButton("設定テスト")
        test_button.clicked.connect(self.test_ai_settings)
        button_layout.addWidget(test_button)
        
        # リセットボタン
        reset_button = QPushButton("リセット")
        reset_button.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_button)
        
        button_layout.addStretch()
        
        # 保存ボタン
        save_button = QPushButton("保存")
        save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(save_button)
        
        # 再読み込みボタン
        reload_button = QPushButton("再読み込み")
        reload_button.clicked.connect(self.load_current_settings)
        button_layout.addWidget(reload_button)
        
        layout.addLayout(button_layout)
    
    def load_current_settings(self):
        """現在の設定を読み込み"""
        try:
            config_path = os.path.abspath(self.config_file_path)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.current_config = json.load(f)
            else:
                # デフォルト設定を読み込み
                self.load_default_settings()
                return
            
            # UI要素に設定を反映
            self.apply_config_to_ui()
            
        except Exception as e:
            logger.error(f"AI設定読み込みエラー: {e}")
            QMessageBox.warning(self, "エラー", f"AI設定の読み込みに失敗しました: {e}")
            self.load_default_settings()
    
    def load_default_settings(self):
        """デフォルト設定を読み込み"""
        try:
            sample_path = os.path.abspath(get_dynamic_file_path("input/ai_config_sample.json"))
            
            if os.path.exists(sample_path):
                with open(sample_path, 'r', encoding='utf-8') as f:
                    self.current_config = json.load(f)
            else:
                # ハードコードされたデフォルト
                self.current_config = self.get_hardcoded_defaults()
            
            self.apply_config_to_ui()
            
        except Exception as e:
            logger.error(f"デフォルト設定読み込みエラー: {e}")
            self.current_config = self.get_hardcoded_defaults()
            self.apply_config_to_ui()
    
    def get_hardcoded_defaults(self):
        """ハードコードされたデフォルト設定"""
        return {
            "ai_providers": {
                "openai": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
                    "default_model": "gpt-4o-mini"
                },
                "gemini": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta",
                    "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
                    "default_model": "gemini-2.0-flash"
                },
                "local_llm": {
                    "enabled": False,
                    "base_url": "http://localhost:11434/api/generate",
                    "models": ["llama3.1:8b", "gemma3:1b", "gemma3:4b"],
                    "default_model": "llama3.1:8b"
                }
            },
            "default_provider": "gemini",
            "timeout": 30,
            "max_tokens": 1000,
            "temperature": 0.7
        }
    
    def apply_config_to_ui(self):
        """設定をUIに反映"""
        try:
            # グローバル設定
            if self.default_provider_combo:
                default_provider = self.current_config.get('default_provider', 'gemini')
                index = self.default_provider_combo.findText(default_provider)
                if index >= 0:
                    self.default_provider_combo.setCurrentIndex(index)
            
            if self.timeout_spinbox:
                self.timeout_spinbox.setValue(self.current_config.get('timeout', 30))
            
            if self.max_tokens_spinbox:
                self.max_tokens_spinbox.setValue(self.current_config.get('max_tokens', 1000))
            
            if self.temperature_spinbox:
                self.temperature_spinbox.setValue(self.current_config.get('temperature', 0.7))
            
            # プロバイダー設定
            providers = self.current_config.get('ai_providers', {})
            
            for provider_name, widgets in self.provider_widgets.items():
                provider_config = providers.get(provider_name, {})
                
                # 有効化状態
                if 'enabled' in widgets:
                    widgets['enabled'].setChecked(provider_config.get('enabled', False))
                
                # API Key
                if 'api_key' in widgets:
                    widgets['api_key'].setText(provider_config.get('api_key', ''))
                
                # Base URL
                if 'base_url' in widgets:
                    widgets['base_url'].setText(provider_config.get('base_url', ''))
                
                # デフォルトモデル
                if 'default_model' in widgets:
                    default_model = provider_config.get('default_model', '')
                    widgets['default_model'].setCurrentText(default_model)
                
                # モデルリスト
                if 'models' in widgets:
                    models = provider_config.get('models', [])
                    models_text = ', '.join(models)
                    widgets['models'].setPlainText(models_text)
            
            # テスト用モデルリストを初期化
            if hasattr(self, 'test_provider_combo'):
                self.update_test_models()
            
        except Exception as e:
            logger.error(f"設定UI反映エラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定のUI反映に失敗しました: {e}")
    
    def collect_ui_settings(self):
        """UIから設定を収集"""
        try:
            config = {
                "ai_providers": {},
                "default_provider": self.default_provider_combo.currentText(),
                "timeout": self.timeout_spinbox.value(),
                "max_tokens": self.max_tokens_spinbox.value(),
                "temperature": self.temperature_spinbox.value()
            }
            
            # プロバイダー設定を収集
            for provider_name, widgets in self.provider_widgets.items():
                provider_config = {
                    "enabled": widgets['enabled'].isChecked(),
                    "default_model": widgets['default_model'].currentText()
                }
                
                # API Key（ローカルLLMにはない）
                if 'api_key' in widgets:
                    provider_config['api_key'] = widgets['api_key'].text()
                
                # Base URL
                if 'base_url' in widgets:
                    provider_config['base_url'] = widgets['base_url'].text()
                
                # モデルリスト
                if 'models' in widgets:
                    models_text = widgets['models'].toPlainText()
                    models = [model.strip() for model in models_text.split(',') if model.strip()]
                    provider_config['models'] = models
                
                # ローカルLLMの注記
                if provider_name == 'local_llm':
                    provider_config['note'] = "Ollama等のローカルLLMサーバーが必要です。"
                
                config['ai_providers'][provider_name] = provider_config
            
            return config
            
        except Exception as e:
            logger.error(f"UI設定収集エラー: {e}")
            return None
    
    def save_settings(self):
        """設定を保存"""
        try:
            config = self.collect_ui_settings()
            if config is None:
                return
            
            config_path = os.path.abspath(self.config_file_path)
            
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            # JSON形式で保存
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.current_config = config
            self.settings_changed.emit()
            
            QMessageBox.information(self, "保存完了", "AI設定が正常に保存されました。")
            
        except Exception as e:
            logger.error(f"AI設定保存エラー: {e}")
            QMessageBox.critical(self, "エラー", f"AI設定の保存に失敗しました: {e}")
    
    def reset_to_defaults(self):
        """デフォルト設定にリセット"""
        reply = QMessageBox.question(
            self, "設定リセット", 
            "AI設定をデフォルトにリセットしますか？\n未保存の変更は失われます。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.load_default_settings()
    
    def test_ai_settings(self):
        """AI設定をテスト"""
        # 簡単な設定検証
        config = self.collect_ui_settings()
        if config is None:
            QMessageBox.warning(self, "エラー", "設定の収集に失敗しました。")
            return
        
        # 有効なプロバイダーをチェック
        enabled_providers = []
        for name, provider in config['ai_providers'].items():
            if provider.get('enabled', False):
                enabled_providers.append(name)
        
        if not enabled_providers:
            QMessageBox.warning(self, "設定エラー", "有効なプロバイダーが設定されていません。")
            return
        
        # 基本的な設定検証
        issues = []
        
        for name in enabled_providers:
            provider = config['ai_providers'][name]
            
            # API Keyチェック（ローカルLLM以外）
            if name != 'local_llm' and not provider.get('api_key', '').strip():
                issues.append(f"{name}: API Keyが設定されていません")
            
            # Base URLチェック
            if not provider.get('base_url', '').strip():
                issues.append(f"{name}: Base URLが設定されていません")
            
            # モデルチェック
            if not provider.get('models') or len(provider.get('models', [])) == 0:
                issues.append(f"{name}: 利用可能モデルが設定されていません")
        
        # 結果表示
        if issues:
            message = "設定に以下の問題があります:\n\n" + "\n".join(f"• {issue}" for issue in issues)
            QMessageBox.warning(self, "設定検証", message)
        else:
            message = f"設定検証が完了しました。\n\n有効なプロバイダー: {', '.join(enabled_providers)}"
            QMessageBox.information(self, "設定検証", message)
    
    def update_test_models(self):
        """テスト用モデルリストを更新"""
        try:
            provider = self.test_provider_combo.currentText()
            self.test_model_combo.clear()
            
            if provider == "デフォルト":
                # デフォルトプロバイダーのデフォルトモデルを設定
                default_provider = self.default_provider_combo.currentText()
                if default_provider in self.provider_widgets:
                    default_model = self.provider_widgets[default_provider]['default_model'].currentText()
                    self.test_model_combo.addItem(f"{default_model} (デフォルト)")
                    self.test_model_combo.setCurrentText(f"{default_model} (デフォルト)")
            elif provider in self.provider_widgets:
                # プロバイダー固有のモデルリストを設定
                widgets = self.provider_widgets[provider]
                if 'models' in widgets:
                    models_text = widgets['models'].toPlainText()
                    models = [model.strip() for model in models_text.split(',') if model.strip()]
                    self.test_model_combo.addItems(models)
                    
                    # デフォルトモデルを選択
                    if 'default_model' in widgets:
                        default_model = widgets['default_model'].currentText()
                        index = self.test_model_combo.findText(default_model)
                        if index >= 0:
                            self.test_model_combo.setCurrentIndex(index)
            
        except Exception as e:
            logger.error(f"テストモデルリスト更新エラー: {e}")
    
    def get_test_config(self):
        """テスト用設定を取得"""
        try:
            # 現在のフォーム内容から設定を収集
            current_config = self.collect_ui_settings()
            if current_config is None:
                # フォールバック：ファイルから読み込み
                self.load_current_settings()
                current_config = self.current_config
            
            return current_config
            
        except Exception as e:
            logger.error(f"テスト設定取得エラー: {e}")
            return None
    
    def get_test_provider_and_model(self):
        """テスト用プロバイダーとモデルを取得"""
        provider = self.test_provider_combo.currentText()
        model = self.test_model_combo.currentText()
        
        if provider == "デフォルト":
            config = self.get_test_config()
            if config:
                provider = config.get('default_provider', 'gemini')
                providers = config.get('ai_providers', {})
                if provider in providers:
                    model = providers[provider].get('default_model', '')
        
        # "モデル名 (デフォルト)" の形式から実際のモデル名を抽出
        if " (デフォルト)" in model:
            model = model.replace(" (デフォルト)", "")
        
        return provider, model
    
    def run_connection_test(self):
        """接続テストを実行"""
        try:
            provider, model = self.get_test_provider_and_model()
            
            if not provider or not model:
                QMessageBox.warning(self, "テストエラー", "プロバイダーまたはモデルが選択されていません。")
                return
            
            # プログレス表示開始
            self.show_test_progress("接続テスト実行中...")
            
            # 接続テスト用の簡単なプロンプト
            test_prompt = "Hello, this is a connection test. Please respond with a simple greeting."
            
            # AIテストを実行
            self.execute_ai_test(provider, model, test_prompt, "接続テスト")
            
        except Exception as e:
            self.hide_test_progress()
            logger.error(f"接続テストエラー: {e}")
            QMessageBox.critical(self, "エラー", f"接続テストでエラーが発生しました: {e}")
    
    def run_prompt_test(self):
        """プロンプトテストを実行"""
        try:
            provider, model = self.get_test_provider_and_model()
            
            if not provider or not model:
                QMessageBox.warning(self, "テストエラー", "プロバイダーまたはモデルが選択されていません。")
                return
            
            # カスタムプロンプトまたはデフォルトプロンプトを使用
            custom_prompt = self.custom_prompt_edit.toPlainText().strip()
            
            if custom_prompt:
                test_prompt = custom_prompt
                test_type = "カスタムプロンプトテスト"
            else:
                # デフォルトテストプロンプト
                test_prompt = (
                    "以下の質問に200文字程度で回答してください。\n\n"
                    "質問: 人工知能の発展が材料科学分野に与える影響について、"
                    "特にデータ解析と新材料発見の観点から簡潔に説明してください。"
                )
                test_type = "デフォルトプロンプトテスト"
            
            # プログレス表示開始
            self.show_test_progress("プロンプトテスト実行中...")
            
            # AIテストを実行
            self.execute_ai_test(provider, model, test_prompt, test_type)
            
        except Exception as e:
            self.hide_test_progress()
            logger.error(f"プロンプトテストエラー: {e}")
            QMessageBox.critical(self, "エラー", f"プロンプトテストでエラーが発生しました: {e}")
    
    def execute_ai_test(self, provider, model, prompt, test_type):
        """AIテストを実行（バックグラウンド処理）"""
        import time
        from datetime import datetime
        
        try:
            # AIマネージャーを取得または作成
            ai_manager = self.get_ai_manager()
            if ai_manager is None:
                self.hide_test_progress()
                self.show_test_result(f"❌ {test_type}失敗", "AIマネージャーの初期化に失敗しました。")
                return
            
            start_time = time.time()
            
            # プロンプト送信
            result = ai_manager.send_prompt(prompt, provider, model)
            
            end_time = time.time()
            response_time = end_time - start_time
            
            # 結果の表示
            if result.get('success', False):
                response_content = result.get('response') or result.get('content', '応答内容なし')
                usage_info = result.get('usage', {})
                tokens_used = usage_info.get('total_tokens', '不明')
                api_response_time = result.get('response_time', response_time)
                
                # 応答時間のフォーマット
                if isinstance(api_response_time, (int, float)):
                    response_time_text = f"{api_response_time:.2f}"
                else:
                    response_time_text = str(api_response_time)
                
                result_text = f"""✅ {test_type}成功

🔧 設定情報:
• プロバイダー: {provider}
• モデル: {model}
• 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• 応答時間: {response_time:.2f}秒

📝 送信プロンプト:
{prompt[:200]}{"..." if len(prompt) > 200 else ""}

🤖 AI応答:
{response_content}

📊 詳細情報:
• トークン使用量: {tokens_used}
• APIレスポンス時間: {response_time_text}秒"""
            
                self.show_test_result(f"✅ {test_type}成功", result_text)
            else:
                error_message = result.get('error', '不明なエラー')
                
                result_text = f"""❌ {test_type}失敗

🔧 設定情報:
• プロバイダー: {provider}
• モデル: {model}
• 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• 試行時間: {response_time:.2f}秒

📝 送信プロンプト:
{prompt[:200]}{"..." if len(prompt) > 200 else ""}

❌ エラー内容:
{error_message}

💡 解決策:
• API Keyが正しく設定されているか確認
• ネットワーク接続を確認
• プロバイダーのサービス状態を確認
• ローカルLLMの場合はサーバーが起動しているか確認"""
            
                self.show_test_result(f"❌ {test_type}失敗", result_text)
            
        except Exception as e:
            self.hide_test_progress()
            error_text = f"""❌ {test_type}でエラーが発生しました

🔧 設定情報:
• プロバイダー: {provider}
• モデル: {model}
• 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

❌ エラー内容:
{str(e)}

💡 トラブルシューティング:
• 設定を確認してください
• ネットワーク接続を確認してください
• エラーログを確認してください"""
            
            self.show_test_result(f"❌ {test_type}エラー", error_text)
        
        finally:
            self.hide_test_progress()
    
    def get_ai_manager(self):
        """AIマネージャーを取得"""
        try:
            # テスト用の設定でAIマネージャーを作成
            config = self.get_test_config()
            if config is None:
                return None
            
            from classes.ai.core.ai_manager import AIManager
            ai_manager = AIManager()
            ai_manager.config = config  # テスト設定を適用
            
            return ai_manager
            
        except Exception as e:
            logger.error(f"AIマネージャー取得エラー: {e}")
            return None
    
    def show_test_progress(self, message):
        """テストプログレス表示"""
        self.test_progress_bar.setVisible(True)
        self.test_progress_bar.setRange(0, 0)  # 無限プログレス
        self.connection_test_button.setEnabled(False)
        self.prompt_test_button.setEnabled(False)
        
        # 結果エリアにプログレス表示
        self.test_result_area.setText(f"🔄 {message}")
    
    def hide_test_progress(self):
        """テストプログレス非表示"""
        self.test_progress_bar.setVisible(False)
        self.connection_test_button.setEnabled(True)
        self.prompt_test_button.setEnabled(True)
    
    def show_test_result(self, title, content):
        """テスト結果表示"""
        self.test_result_area.setText(content)
        
        # 結果に応じてスクロール位置を調整
        if "✅" in title:
            # 成功の場合は応答部分まで自動スクロール
            cursor = self.test_result_area.textCursor()
            cursor.movePosition(cursor.Start)
            if "🤖 AI応答:" in content:
                # AI応答部分を探してスクロール
                ai_response_pos = content.find("🤖 AI応答:")
                if ai_response_pos >= 0:
                    cursor.setPosition(ai_response_pos)
                    self.test_result_area.setTextCursor(cursor)
        else:
            # エラーの場合は先頭に戻る
            cursor = self.test_result_area.textCursor()
            cursor.movePosition(cursor.Start)
            self.test_result_area.setTextCursor(cursor)


def create_ai_settings_widget(parent=None):
    """AI設定ウィジェットを作成"""
    try:
        return AISettingsWidget(parent)
    except Exception as e:
        logger.error(f"AI設定ウィジェット作成エラー: {e}")
        return None


def get_ai_config():
    """AI設定を取得"""
    try:
        config_path = get_dynamic_file_path("input/ai_config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 設定ファイルの構造に合わせて正規化
                if 'ai_providers' in config:
                    # 新しい構造: ai_providers -> providers
                    normalized_config = {
                        'default_provider': config.get('default_provider', 'gemini'),
                        'providers': config.get('ai_providers', {}),
                        'timeout': config.get('timeout', 30),
                        'max_tokens': config.get('max_tokens', 1001),
                        'temperature': config.get('temperature', 0.8)
                    }
                    return normalized_config
                else:
                    # 旧い構造はそのまま返す
                    return config
        else:
            # デフォルト設定を返す
            return {
                'default_provider': 'gemini',
                'providers': {
                    'gemini': {
                        'default_model': 'gemini-2.0-flash'
                    }
                }
            }
    except Exception as e:
        logger.error(f"AI設定取得エラー: {e}")
        return None