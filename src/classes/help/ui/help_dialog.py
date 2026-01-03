"""
ヘルプダイアログ - ARIM RDE Tool v2.4.3
About（ライセンス）と使用方法を表示
"""

import logging
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QDialog, QVBoxLayout, QTabWidget, QPushButton,
        QHBoxLayout
    )
    from qt_compat.core import Qt
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QDialog: pass


class HelpDialog(QDialog):
    """ヘルプダイアログ - About + 使用方法"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """UI構築"""
        self.setWindowTitle("ARIM RDE Tool - ヘルプ")
        self.setModal(False)  # モードレスダイアログ
        
        # 画面サイズの80%に設定
        if PYQT5_AVAILABLE:
            from qt_compat import get_screen_geometry
            screen_rect = get_screen_geometry(self)
            width = int(screen_rect.width() * 0.8)
            height = int(screen_rect.height() * 0.8)
            self.resize(width, height)
            
            # 画面中央に配置
            self.move(
                (screen_rect.width() - width) // 2,
                (screen_rect.height() - height) // 2
            )
        else:
            self.resize(800, 600)
        
        # メインレイアウト
        layout = QVBoxLayout(self)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Aboutタブ
        self.setup_about_tab()
        
        # 使用方法タブ
        self.setup_usage_tab()
        
        # 閉じるボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
    
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


def show_help_dialog(parent=None):
    """ヘルプダイアログを表示"""
    try:
        dialog = HelpDialog(parent)
        dialog.show()
        return dialog
    except Exception as e:
        logger.error(f"ヘルプダイアログ表示エラー: {e}")
        return None
