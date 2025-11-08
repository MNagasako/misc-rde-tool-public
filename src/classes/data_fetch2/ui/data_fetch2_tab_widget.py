"""
データ取得2機能のタブウィジェット
画面サイズ適応型レスポンシブデザイン対応
"""

import logging
from typing import Optional

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QApplication,
        QScrollArea, QGroupBox, QGridLayout, QComboBox,
        QTextEdit, QListWidget, QTreeWidget, QTreeWidgetItem,
        QCheckBox, QSpinBox
    )
    from qt_compat.core import Qt
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass
    class QTabWidget: pass

logger = logging.getLogger(__name__)

class DataFetch2TabWidget(QTabWidget):
    """データ取得2機能のタブウィジェット"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_controller = parent
        self.bearer_token = None
        
        # フィルタ設定の初期化
        try:
            from classes.data_fetch2.conf.file_filter_config import get_default_filter
            self.current_filter_config = get_default_filter()
        except ImportError:
            # フォールバック
            self.current_filter_config = {
                "file_types": ["MAIN_IMAGE"],
                "media_types": [],
                "extensions": [],
                "size_min": 0,
                "size_max": 0,
                "filename_pattern": "",
                "max_download_count": 0
            }
        
        self.setup_ui()
        
    def set_bearer_token(self, token):
        """Bearer tokenを設定"""
        self.bearer_token = token
        
    def setup_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        # レスポンシブデザイン設定
        self.setup_responsive_layout()
         # データセット取得タブを追加
        self.create_dataset_tab()       
        # タブ作成
        self.create_filter_tab()
        

        
    def setup_responsive_layout(self):
        """レスポンシブレイアウト設定"""
        # 画面サイズ取得 - PySide6対応
        from qt_compat import get_screen_size
        screen_width, _ = get_screen_size(self)
        
        # レスポンシブ設定
        self.columns = self.get_optimal_layout_columns(screen_width)
        
    def get_optimal_layout_columns(self, width=None):
        """最適な段組数を取得"""
        if width is None:
            from qt_compat import get_screen_size
            width, _ = get_screen_size(self)
            
        if width < 1024:
            return 1  # 1段組（スクロール表示）
        elif width < 1440:
            return 2  # 2段組（左右分割）
        else:
            return 3  # 3段組（左中右分割）
            
    # 不要なメソッドを削除: create_search_tab, create_download_tab
    # フィルタ設定とデータ取得のみに機能を集約
    
    def create_filter_tab(self):
        """ファイルフィルタタブ - 高度なフィルタ機能"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # タイトル
        title_label = QLabel("ファイルフィルタ設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        desc_label = QLabel("データ取得タブで一括取得するファイルの種類や条件を指定します")
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)
        
        # ファイルフィルタウィジェット
        try:
            from classes.data_fetch2.ui.file_filter_widget import create_file_filter_widget
            self.file_filter_widget = create_file_filter_widget(tab_widget)
            self.file_filter_widget.filterChanged.connect(self.on_file_filter_changed)
            layout.addWidget(self.file_filter_widget)
        except ImportError as e:
            logger.error(f"フィルタウィジェットのインポートに失敗: {e}")
            # フォールバック: 簡易フィルタUI
            fallback_label = QLabel("高度なフィルタ機能は利用できません")
            fallback_label.setStyleSheet("color: red; font-weight: bold;")
            layout.addWidget(fallback_label)
            self.file_filter_widget = None
        
        self.addTab(tab_widget, "🔍 ファイルフィルタ")
        
    def create_dataset_tab(self):
        """データセット選択・取得タブ"""
        try:
            from classes.data_fetch2.core.ui.data_fetch2_widget import create_data_fetch2_widget
            # 既存の機能ウィジェットを統合
            tab_widget = create_data_fetch2_widget(self, self.bearer_token)
            if tab_widget:
                self.addTab(tab_widget, "📊 データ取得")
            else:
                # フォールバック
                fallback_widget = QWidget()
                fallback_layout = QVBoxLayout(fallback_widget)
                fallback_label = QLabel("データ取得機能は利用できません")
                fallback_label.setStyleSheet("color: red; font-weight: bold;")
                fallback_layout.addWidget(fallback_label)
                self.addTab(fallback_widget, "📊 データ取得")
        except ImportError as e:
            logger.error(f"データ取得ウィジェットのインポートエラー: {e}")
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout(fallback_widget)
            fallback_label = QLabel("データ取得機能は利用できません")
            fallback_label.setStyleSheet("color: red; font-weight: bold;")
            fallback_layout.addWidget(fallback_label)
            self.addTab(fallback_widget, "📊 データ取得")
            
    def on_file_filter_changed(self, filter_config):
        """ファイルフィルタ変更時のハンドラー"""
        logger.info(f"フィルタ設定変更: {filter_config}")
        # フィルタ設定を保存
        self.current_filter_config = filter_config
        
        # フィルタ概要を表示（オプション）
        try:
            from classes.data_fetch2.util.file_filter_util import get_filter_summary
            summary = get_filter_summary(filter_config)
            logger.debug(f"フィルタ概要: {summary}")
        except ImportError:
            pass


def create_data_fetch2_tab_widget(parent=None):
    """データ取得2タブウィジェットを作成"""
    try:
        return DataFetch2TabWidget(parent)
    except Exception as e:
        logger.error(f"データ取得2タブウィジェット作成エラー: {e}")
        return None
