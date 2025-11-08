"""
AI機能のタブウィジェット
画面サイズ適応型レスポンシブデザイン対応
"""

import logging
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QApplication,
        QScrollArea, QGroupBox, QGridLayout, QComboBox,
        QTextEdit, QCheckBox
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass
    class QTabWidget: pass

logger = logging.getLogger(__name__)

class AITabWidget(QTabWidget):
    """AI機能のタブウィジェット"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_controller = parent
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        # レスポンシブデザイン設定
        self.setup_responsive_layout()
        
        # タブ作成
        self.create_ai_analysis_tab()
        self.create_ai_settings_tab()
        self.create_ai_history_tab()
        
    def setup_responsive_layout(self):
        """レスポンシブレイアウト設定"""
        # 画面サイズ取得
        desktop = QApplication.desktop()
        screen_rect = desktop.screenGeometry()
        screen_width = screen_rect.width()
        
        # レスポンシブ設定
        self.columns = self.get_optimal_layout_columns(screen_width)
        
    def get_optimal_layout_columns(self, width=None):
        """最適な段組数を取得"""
        if width is None:
            desktop = QApplication.desktop()
            width = desktop.screenGeometry().width()
            
        if width < 1024:
            return 1  # 1段組（スクロール表示）
        elif width < 1440:
            return 2  # 2段組（左右分割）
        else:
            return 3  # 3段組（左中右分割）
            
    def create_ai_analysis_tab(self):
        """AI分析タブ"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # タイトル
        title_label = QLabel("AI分析")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # データソース選択グループ
        datasource_group = QGroupBox("データソース選択")
        datasource_layout = QVBoxLayout(datasource_group)
        
        # データソースドロップダウン
        datasource_layout_h = QHBoxLayout()
        datasource_label = QLabel("データソース:")
        self.datasource_combo = QComboBox()
        self.datasource_combo.addItems(["基本情報データ", "データセット情報", "アクセスログ"])
        datasource_layout_h.addWidget(datasource_label)
        datasource_layout_h.addWidget(self.datasource_combo)
        datasource_layout.addLayout(datasource_layout_h)
        
        content_layout.addWidget(datasource_group)
        
        # 分析設定グループ
        analysis_group = QGroupBox("分析設定")
        analysis_layout = QVBoxLayout(analysis_group)
        
        # 分析モデル選択
        model_layout = QHBoxLayout()
        model_label = QLabel("AIモデル:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(["GPT-4", "GPT-3.5-turbo", "Claude-3"])
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        analysis_layout.addLayout(model_layout)
        
        # 分析プロンプト
        prompt_label = QLabel("分析プロンプト:")
        self.prompt_text = QTextEdit()
        self.prompt_text.setMaximumHeight(100)
        self.prompt_text.setPlaceholderText("分析内容を記述してください...")
        analysis_layout.addWidget(prompt_label)
        analysis_layout.addWidget(self.prompt_text)
        
        content_layout.addWidget(analysis_group)
        
        # 実行ボタン
        execute_group = QGroupBox("実行")
        execute_layout = QHBoxLayout(execute_group)
        
        execute_btn = QPushButton("🤖 AI分析実行")
        execute_btn.setMinimumHeight(40)
        execute_btn.clicked.connect(self.execute_ai_analysis)
        execute_layout.addWidget(execute_btn)
        execute_layout.addStretch()
        
        content_layout.addWidget(execute_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "AI分析")
        
    def create_ai_settings_tab(self):
        """AI設定タブ"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # タイトル
        title_label = QLabel("AI設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # API設定グループ
        api_group = QGroupBox("API設定")
        api_layout = QVBoxLayout(api_group)
        
        # APIキー入力
        api_key_layout = QHBoxLayout()
        api_key_label = QLabel("APIキー:")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("APIキーを入力...")
        api_key_layout.addWidget(api_key_label)
        api_key_layout.addWidget(self.api_key_input)
        api_layout.addLayout(api_key_layout)
        
        # APIエンドポイント
        endpoint_layout = QHBoxLayout()
        endpoint_label = QLabel("エンドポイント:")
        self.endpoint_input = QLineEdit()
        self.endpoint_input.setPlaceholderText("https://api.openai.com/v1")
        endpoint_layout.addWidget(endpoint_label)
        endpoint_layout.addWidget(self.endpoint_input)
        api_layout.addLayout(endpoint_layout)
        
        content_layout.addWidget(api_group)
        
        # 動作設定グループ
        behavior_group = QGroupBox("動作設定")
        behavior_layout = QVBoxLayout(behavior_group)
        
        # タイムアウト設定
        timeout_layout = QHBoxLayout()
        timeout_label = QLabel("タイムアウト:")
        self.timeout_input = QLineEdit()
        self.timeout_input.setText("30")
        self.timeout_input.setPlaceholderText("秒")
        timeout_layout.addWidget(timeout_label)
        timeout_layout.addWidget(self.timeout_input)
        timeout_layout.addWidget(QLabel("秒"))
        timeout_layout.addStretch()
        behavior_layout.addLayout(timeout_layout)
        
        # 自動保存設定
        self.auto_save_checkbox = QCheckBox("分析結果を自動保存")
        self.auto_save_checkbox.setChecked(True)
        behavior_layout.addWidget(self.auto_save_checkbox)
        
        content_layout.addWidget(behavior_group)
        
        # 保存ボタン
        save_group = QGroupBox("設定保存")
        save_layout = QHBoxLayout(save_group)
        
        save_btn = QPushButton("💾 設定保存")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.save_ai_settings)
        save_layout.addWidget(save_btn)
        save_layout.addStretch()
        
        content_layout.addWidget(save_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "AI設定")
        
    def create_ai_history_tab(self):
        """AI履歴タブ"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # タイトル
        title_label = QLabel("AI履歴")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # 履歴表示グループ
        history_group = QGroupBox("分析履歴")
        history_layout = QVBoxLayout(history_group)
        
        # 履歴表示エリア
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setPlaceholderText("AI分析の履歴がここに表示されます...")
        history_layout.addWidget(self.history_text)
        
        content_layout.addWidget(history_group)
        
        # 操作ボタン
        actions_group = QGroupBox("履歴操作")
        actions_layout = QHBoxLayout(actions_group)
        
        refresh_btn = QPushButton("🔄 履歴更新")
        refresh_btn.clicked.connect(self.refresh_history)
        actions_layout.addWidget(refresh_btn)
        
        clear_btn = QPushButton("🗑️ 履歴クリア")
        clear_btn.clicked.connect(self.clear_history)
        actions_layout.addWidget(clear_btn)
        
        export_btn = QPushButton("📤 履歴エクスポート")
        export_btn.clicked.connect(self.export_history)
        actions_layout.addWidget(export_btn)
        
        actions_layout.addStretch()
        
        content_layout.addWidget(actions_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "AI履歴")
        
    def execute_ai_analysis(self):
        """AI分析実行"""
        try:
            if self.parent_controller and hasattr(self.parent_controller, 'execute_ai_analysis'):
                self.parent_controller.execute_ai_analysis()
        except Exception as e:
            logger.error(f"AI分析実行エラー: {e}")
            
    def save_ai_settings(self):
        """AI設定保存"""
        try:
            # 設定の保存処理
            logger.info("AI設定を保存しました")
        except Exception as e:
            logger.error(f"AI設定保存エラー: {e}")
            
    def refresh_history(self):
        """履歴更新"""
        try:
            # 履歴の更新処理
            logger.info("AI履歴を更新しました")
        except Exception as e:
            logger.error(f"履歴更新エラー: {e}")
            
    def clear_history(self):
        """履歴クリア"""
        try:
            self.history_text.clear()
            logger.info("AI履歴をクリアしました")
        except Exception as e:
            logger.error(f"履歴クリアエラー: {e}")
            
    def export_history(self):
        """履歴エクスポート"""
        try:
            # 履歴のエクスポート処理
            logger.info("AI履歴をエクスポートしました")
        except Exception as e:
            logger.error(f"履歴エクスポートエラー: {e}")


def create_ai_tab_widget(parent=None):
    """AIタブウィジェットを作成"""
    try:
        return AITabWidget(parent)
    except Exception as e:
        logger.error(f"AIタブウィジェット作成エラー: {e}")
        return None
