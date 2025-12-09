"""
Aboutタブ - ARIM RDE Tool v2.1.3
ライセンス情報表示
"""

import logging

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QLabel, QTextBrowser,
        QScrollArea, QGroupBox
    )
    from qt_compat.core import Qt
    from qt_compat.gui import QFont
    from classes.theme import ThemeKey
    from classes.theme.theme_manager import get_color
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

from classes.help.util.markdown_renderer import load_help_markdown, set_markdown_document


class AboutTab(QWidget):
    """Aboutタブ - アプリケーション情報とライセンス表示"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # アプリケーション情報
        self.create_app_info_section(layout)
        
        # ライセンス情報
        self.create_license_section(layout)
        
    def create_app_info_section(self, parent_layout):
        """アプリケーション情報セクション"""
        group = QGroupBox("アプリケーション情報")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)
        
        # アプリ名
        try:
            from classes.help.conf.license_info import (
                APP_NAME, APP_VERSION, APP_DESCRIPTION, 
                APP_AUTHOR, APP_COPYRIGHT
            )
        except ImportError:
            APP_NAME = "ARIM RDE Tool"
            APP_VERSION = "v2.1.5"
            APP_DESCRIPTION = "データ移行ツール"
            APP_AUTHOR = "ARIM事業"
            APP_COPYRIGHT = "Copyright © 2024-2025 ARIM"
        
        title_label = QLabel(f"{APP_NAME} {APP_VERSION}")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        desc_label = QLabel(APP_DESCRIPTION)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 著作権
        copyright_label = QLabel(APP_COPYRIGHT)
        copyright_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin-top: 6px;")
        layout.addWidget(copyright_label)
        
        # 作者
        author_label = QLabel(f"開発: {APP_AUTHOR}")
        author_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        layout.addWidget(author_label)
        
        parent_layout.addWidget(group)
    
    def create_license_section(self, parent_layout):
        """ライセンス情報セクション"""
        group = QGroupBox("About")
        layout = QVBoxLayout(group)
        
        # Aboutテキスト表示
        about_browser = QTextBrowser()
        about_browser.setOpenExternalLinks(True)
        # ドキュメントマージンを小さく設定
        about_browser.document().setDocumentMargin(8)
        
        try:
            about_text, base_dir = load_help_markdown('about.md')
            set_markdown_document(about_browser, about_text, base_dir)
        except FileNotFoundError as e:
            logger.warning("About情報ファイルが見つかりません: %s", e)
            about_browser.setPlainText("About情報ファイルが見つかりませんでした。docs/help/about.md を確認してください。")
        except Exception as e:
            logger.error(f"About情報読み込みエラー: {e}")
            about_browser.setPlainText(f"About情報の読み込みに失敗しました。\n\nエラー: {e}")
        
        layout.addWidget(about_browser)
        
        parent_layout.addWidget(group)


def create_about_tab(parent=None):
    """Aboutタブを作成"""
    try:
        return AboutTab(parent)
    except Exception as e:
        logger.error(f"Aboutタブ作成エラー: {e}")
        return None
