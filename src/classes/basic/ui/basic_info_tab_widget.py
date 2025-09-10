"""
基本情報機能のタブウィジェット
画面サイズ適応型レスポンシブデザイン対応
"""

import logging
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QApplication,
        QScrollArea, QGroupBox, QGridLayout
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass
    class QTabWidget: pass

logger = logging.getLogger(__name__)

class BasicInfoTabWidget(QTabWidget):
    """基本情報機能のタブウィジェット"""
    
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
        self.create_basic_fetch_tab()
        self.create_xlsx_export_tab()
        self.create_advanced_tab()
        
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
            
    def create_basic_fetch_tab(self):
        """基本情報取得タブ"""
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
        title_label = QLabel("基本情報取得")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # 検索条件グループ
        search_group = QGroupBox("検索条件")
        search_layout = QVBoxLayout(search_group)
        
        # 検索入力
        search_input_layout = QHBoxLayout()
        search_label = QLabel("対象ユーザー:")
        self.basic_info_input = QLineEdit()
        self.basic_info_input.setPlaceholderText("空欄の場合は自身が管理するデータセットが対象")
        search_input_layout.addWidget(search_label)
        search_input_layout.addWidget(self.basic_info_input)
        search_layout.addLayout(search_input_layout)
        
        content_layout.addWidget(search_group)
        
        # ボタングループ（レスポンシブ対応）
        buttons_group = QGroupBox("実行")
        if self.columns == 1:
            buttons_layout = QVBoxLayout(buttons_group)
        elif self.columns == 2:
            buttons_layout = QGridLayout(buttons_group)
        else:
            buttons_layout = QHBoxLayout(buttons_group)
            
        # 基本情報取得ボタン
        fetch_btn = QPushButton("🔍 基本情報取得")
        fetch_btn.setMinimumHeight(40)
        fetch_btn.clicked.connect(self.fetch_basic_info)
        
        # 自身の基本情報取得ボタン
        fetch_self_btn = QPushButton("👤 自身の基本情報取得")
        fetch_self_btn.setMinimumHeight(40)
        fetch_self_btn.clicked.connect(self.fetch_basic_info_self)
        
        # レスポンシブボタン配置
        if self.columns == 1:
            buttons_layout.addWidget(fetch_btn)
            buttons_layout.addWidget(fetch_self_btn)
        elif self.columns == 2:
            buttons_layout.addWidget(fetch_btn, 0, 0)
            buttons_layout.addWidget(fetch_self_btn, 0, 1)
        else:
            buttons_layout.addWidget(fetch_btn)
            buttons_layout.addWidget(fetch_self_btn)
            buttons_layout.addStretch()
            
        content_layout.addWidget(buttons_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "基本情報取得")
        
    def create_xlsx_export_tab(self):
        """XLSX出力タブ"""
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
        title_label = QLabel("XLSX出力")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # 出力オプショングループ
        export_group = QGroupBox("出力オプション")
        export_layout = QVBoxLayout(export_group)
        
        info_label = QLabel(
            "取得した基本情報をXLSX形式で出力します。\n"
            "事前に基本情報の取得を実行してください。"
        )
        export_layout.addWidget(info_label)
        
        content_layout.addWidget(export_group)
        
        # ボタングループ（レスポンシブ対応）
        buttons_group = QGroupBox("出力実行")
        if self.columns == 1:
            buttons_layout = QVBoxLayout(buttons_group)
        elif self.columns == 2:
            buttons_layout = QGridLayout(buttons_group)
        else:
            buttons_layout = QHBoxLayout(buttons_group)
            
        # XLSX反映ボタン
        apply_xlsx_btn = QPushButton("📄 XLSX反映")
        apply_xlsx_btn.setMinimumHeight(40)
        apply_xlsx_btn.clicked.connect(self.apply_basic_info_to_xlsx)
        
        # まとめXLSXボタン
        summary_xlsx_btn = QPushButton("📋 まとめXLSX")
        summary_xlsx_btn.setMinimumHeight(40)
        summary_xlsx_btn.clicked.connect(self.summary_basic_info_to_xlsx)
        
        # レスポンシブボタン配置
        if self.columns == 1:
            buttons_layout.addWidget(apply_xlsx_btn)
            buttons_layout.addWidget(summary_xlsx_btn)
        elif self.columns == 2:
            buttons_layout.addWidget(apply_xlsx_btn, 0, 0)
            buttons_layout.addWidget(summary_xlsx_btn, 0, 1)
        else:
            buttons_layout.addWidget(apply_xlsx_btn)
            buttons_layout.addWidget(summary_xlsx_btn)
            buttons_layout.addStretch()
            
        content_layout.addWidget(buttons_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "XLSX出力")
        
    def create_advanced_tab(self):
        """高度な設定タブ"""
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
        title_label = QLabel("高度な設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # 設定グループ
        settings_group = QGroupBox("設定オプション")
        settings_layout = QVBoxLayout(settings_group)
        
        settings_info = QLabel(
            "・出力形式: XLSX (Excel)\n"
            "・文字エンコーディング: UTF-8\n"
            "・日付形式: YYYY-MM-DD\n"
            "・出力先: output/ ディレクトリ"
        )
        settings_layout.addWidget(settings_info)
        
        content_layout.addWidget(settings_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "高度な設定")
        
    def fetch_basic_info(self):
        """基本情報取得"""
        try:
            if self.parent_controller and hasattr(self.parent_controller, 'fetch_basic_info'):
                self.parent_controller.fetch_basic_info()
        except Exception as e:
            logger.error(f"基本情報取得エラー: {e}")
            
    def fetch_basic_info_self(self):
        """自身の基本情報取得"""
        try:
            if self.parent_controller and hasattr(self.parent_controller, 'fetch_basic_info_self'):
                self.parent_controller.fetch_basic_info_self()
        except Exception as e:
            logger.error(f"自身の基本情報取得エラー: {e}")
            
    def apply_basic_info_to_xlsx(self):
        """XLSX反映"""
        try:
            if self.parent_controller and hasattr(self.parent_controller, 'apply_basic_info_to_Xlsx'):
                self.parent_controller.apply_basic_info_to_Xlsx()
        except Exception as e:
            logger.error(f"XLSX反映エラー: {e}")
            
    def summary_basic_info_to_xlsx(self):
        """まとめXLSX"""
        try:
            if self.parent_controller and hasattr(self.parent_controller, 'summary_basic_info_to_Xlsx'):
                self.parent_controller.summary_basic_info_to_Xlsx()
        except Exception as e:
            logger.error(f"まとめXLSX エラー: {e}")


def create_basic_info_tab_widget(parent=None):
    """基本情報タブウィジェットを作成"""
    try:
        return BasicInfoTabWidget(parent)
    except Exception as e:
        logger.error(f"基本情報タブウィジェット作成エラー: {e}")
        return None
