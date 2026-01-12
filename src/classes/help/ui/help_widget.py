"""
ヘルプウィジェット - ARIM RDE Tool v2.4.16
メインウィンドウ内にヘルプコンテンツを表示するウィジェット版
"""

import logging
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QTabWidget
    )
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass


class HelpWidget(QWidget):
    """ヘルプウィジェット - メインウィンドウ統合版"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """UI構築"""
        # メインレイアウト
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Aboutタブ
        self.setup_about_tab()
        
        # 使用方法タブ
        self.setup_usage_tab()
    
    def setup_about_tab(self):
        """Aboutタブ設定"""
        try:
            from classes.help.ui.about_tab import create_about_tab
            about_tab = create_about_tab(self)
            if about_tab:
                self.tab_widget.addTab(about_tab, "About")
            else:
                self._create_fallback_tab("About", "Aboutタブの読み込みに失敗しました。")
        except Exception as e:
            logger.error(f"Aboutタブ作成エラー: {e}")
            self._create_fallback_tab("About", f"エラー: {e}")
    
    def setup_usage_tab(self):
        """使用方法タブ設定"""
        try:
            from classes.help.ui.usage_tab import create_usage_tab
            usage_tab = create_usage_tab(self)
            if usage_tab:
                self.tab_widget.addTab(usage_tab, "使用方法")
            else:
                self._create_fallback_tab("使用方法", "使用方法タブの読み込みに失敗しました。")
        except Exception as e:
            logger.error(f"使用方法タブ作成エラー: {e}")
            self._create_fallback_tab("使用方法", f"エラー: {e}")
    
    def _create_fallback_tab(self, title: str, message: str):
        """フォールバック用タブ作成"""
        from qt_compat.widgets import QWidget, QVBoxLayout, QLabel
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        label = QLabel(message)
        label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
        layout.addWidget(label)
        layout.addStretch()
        
        self.tab_widget.addTab(widget, title)


def create_help_widget(parent=None):
    """ヘルプウィジェットを作成
    
    Args:
        parent: 親ウィジェット
        
    Returns:
        HelpWidget: ヘルプウィジェット
    """
    try:
        if not PYQT5_AVAILABLE:
            logger.error("PyQt5が利用できないため、ヘルプウィジェットを作成できません。")
            return None
            
        widget = HelpWidget(parent)
        return widget
        
    except Exception as e:
        logger.error(f"ヘルプウィジェット作成エラー: {e}")
        return None
