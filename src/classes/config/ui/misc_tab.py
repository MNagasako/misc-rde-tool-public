"""
MISC（その他）タブ - ARIM RDE Tool
その他の便利機能を集約

Phase2-2: 設定メニューMISCタブ追加
"""

import sys
import os
import logging
from pathlib import Path

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QMessageBox
    )
    from qt_compat.core import Qt
    from classes.theme import get_color, ThemeKey
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

# ログ設定
logger = logging.getLogger(__name__)

class MiscTab(QWidget):
    """MISC（その他）タブ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # タイトル
        title_label = QLabel("その他の便利機能")
        title_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        layout.addWidget(title_label)
        
        # ディレクトリ操作グループ
        dir_group = self.create_directory_group()
        layout.addWidget(dir_group)
        
        # スペーサー（将来の拡張用）
        layout.addStretch(1)
        
    def create_directory_group(self):
        """ディレクトリ操作グループ"""
        group = QGroupBox("ディレクトリ操作")
        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """)
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # インストールディレクトリを開くボタン
        install_dir_layout = QHBoxLayout()
        
        install_dir_label = QLabel("アプリケーションのインストール先:")
        install_dir_label.setStyleSheet("font-weight: normal;")
        install_dir_layout.addWidget(install_dir_label)
        
        open_install_dir_btn = QPushButton("📁 インストールディレクトリを開く")
        open_install_dir_btn.setToolTip("アプリケーションがインストールされているディレクトリをエクスプローラーで開きます")
        open_install_dir_btn.clicked.connect(self.open_install_directory)
        open_install_dir_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 8px 15px;
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
            }}
        """)
        install_dir_layout.addWidget(open_install_dir_btn)
        install_dir_layout.addStretch()
        
        layout.addLayout(install_dir_layout)
        
        # 説明ラベル
        info_label = QLabel(
            "インストールディレクトリには、アプリケーションの実行ファイル、\n"
            "設定ファイル、ログファイルなどが保存されています。"
        )
        info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; font-weight: normal;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        return group
        
    def open_install_directory(self):
        """インストールディレクトリを開く"""
        try:
            from config.common import get_base_dir
            # アプリケーションのルートディレクトリを取得
            if getattr(sys, 'frozen', False):
                # PyInstallerでバイナリ化されている場合
                app_dir = Path(sys.executable).parent
            else:
                # 開発環境（ソースから実行）の場合
                app_dir = Path(get_base_dir())
                
            logger.info(f"インストールディレクトリを開く: {app_dir}")
            
            # OSに応じてディレクトリを開く
            if sys.platform == 'win32':
                os.startfile(str(app_dir))
            elif sys.platform == 'darwin':
                os.system(f'open "{app_dir}"')
            else:
                os.system(f'xdg-open "{app_dir}"')
                
            logger.info("インストールディレクトリを開きました")
            
        except Exception as e:
            logger.error(f"インストールディレクトリを開く際にエラーが発生: {e}")
            import traceback
            traceback.print_exc()
            
            QMessageBox.critical(
                self,
                "エラー",
                f"ディレクトリを開けませんでした:\n{str(e)}"
            )
