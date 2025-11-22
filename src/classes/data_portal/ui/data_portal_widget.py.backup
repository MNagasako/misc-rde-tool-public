"""
データポータルメインウィジェット

ログイン設定タブとデータセットアップロードタブを統合したタブウィジェット
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget
)
from PyQt5.QtCore import pyqtSignal

from classes.managers.log_manager import get_logger
from .login_settings_tab import LoginSettingsTab
from .dataset_upload_tab import DatasetUploadTab

logger = get_logger("DataPortal.Widget")


class DataPortalWidget(QWidget):
    """
    データポータルメインウィジェット
    
    タブ構成:
    1. ログイン設定タブ - 認証情報管理
    2. データセットJSONタブ - JSONアップロード
    """
    
    # シグナル定義
    login_test_completed = pyqtSignal(bool, str)  # ログインテスト完了
    upload_completed = pyqtSignal(bool, str)  # アップロード完了
    
    def __init__(self, parent=None):
        """初期化"""
        super().__init__(parent)
        
        self._init_ui()
        self._connect_signals()
        logger.info("データポータルウィジェット初期化完了")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # タブウィジェット作成
        self.tab_widget = QTabWidget()
        
        # ログイン設定タブ
        self.login_settings_tab = LoginSettingsTab(self)
        self.tab_widget.addTab(self.login_settings_tab, "🔐 ログイン設定")
        
        # データセットJSONアップロードタブ
        self.dataset_upload_tab = DatasetUploadTab(self)
        self.tab_widget.addTab(self.dataset_upload_tab, "📤 データセットJSON")
        
        layout.addWidget(self.tab_widget)
    
    def _connect_signals(self):
        """シグナル接続"""
        # ログインテスト完了シグナルを転送
        self.login_settings_tab.login_test_completed.connect(
            self.login_test_completed.emit
        )
        
        # アップロード完了シグナルを転送
        self.dataset_upload_tab.upload_completed.connect(
            self.upload_completed.emit
        )
        
        # 認証情報保存後にアップロードタブを有効化
        self.login_settings_tab.credentials_saved.connect(
            self._on_credentials_saved
        )
    
    def _on_credentials_saved(self, environment: str):
        """認証情報保存後の処理"""
        logger.info(f"認証情報保存完了: {environment}")
        # 必要に応じてアップロードタブに通知
    
    def switch_to_login_tab(self):
        """ログイン設定タブに切り替え"""
        self.tab_widget.setCurrentIndex(0)
    
    def switch_to_upload_tab(self):
        """データセットJSONタブに切り替え"""
        self.tab_widget.setCurrentIndex(1)
