"""
データポータルメインウィジェット

ログイン設定タブとデータセットアップロードタブを統合したタブウィジェット
"""

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QTabWidget
)
from qt_compat.core import Signal

from classes.managers.log_manager import get_logger
from .login_settings_tab import LoginSettingsTab
from .master_data_tab import MasterDataTab
from .dataset_upload_tab import DatasetUploadTab

logger = get_logger("DataPortal.Widget")


class DataPortalWidget(QWidget):
    """
    データポータルメインウィジェット
    
    タブ構成:
    1. ログイン設定タブ - 認証情報管理
    2. マスタタブ - マスタデータ管理
    3. データセットタブ - JSONアップロード
    """
    
    # シグナル定義
    login_test_completed = Signal(bool, str)  # ログインテスト完了
    upload_completed = Signal(bool, str)  # アップロード完了
    master_fetched = Signal(str, bool)  # マスタ取得完了
    
    def __init__(self, parent=None):
        """初期化"""
        super().__init__(parent)
        
        self._init_ui()
        self._connect_signals()
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        theme_manager = ThemeManager()
        theme_manager.theme_changed.connect(self.refresh_theme)
        
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
        
        # マスタデータタブ
        self.master_data_tab = MasterDataTab(self)
        self.tab_widget.addTab(self.master_data_tab, "📋 マスタ")
        
        # データセットJSONアップロードタブ
        self.dataset_upload_tab = DatasetUploadTab(self)
        self.tab_widget.addTab(self.dataset_upload_tab, "📤 データカタログ")
        
        layout.addWidget(self.tab_widget)
    
    def _connect_signals(self):
        """シグナル接続"""
        # ログインテスト完了シグナルを転送
        self.login_settings_tab.login_test_completed.connect(
            self._on_login_test_completed
        )
        
        # アップロード完了シグナルを転送
        self.dataset_upload_tab.upload_completed.connect(
            self.upload_completed.emit
        )
        
        # マスタ取得完了シグナルを転送
        self.master_data_tab.master_fetched.connect(
            self.master_fetched.emit
        )
        
        # 認証情報保存後にアップロードタブを有効化
        self.login_settings_tab.credentials_saved.connect(
            self._on_credentials_saved
        )
    
    def _on_login_test_completed(self, success: bool, message: str):
        """ログインテスト完了時の処理"""
        # シグナルを転送
        self.login_test_completed.emit(success, message)
        
        # 成功時にPortalClientをマスタタブに設定
        if success and hasattr(self.login_settings_tab, 'portal_client'):
            portal_client = self.login_settings_tab.portal_client
            if portal_client:
                self.master_data_tab.set_portal_client(portal_client)
                logger.info("マスタタブにPortalClientを設定しました")
    
    def _on_credentials_saved(self, environment: str):
        """認証情報保存後の処理"""
        logger.info(f"認証情報保存完了: {environment}")
        # 必要に応じてアップロードタブに通知
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        try:
            # 各タブのrefresh_theme()を呼び出し
            if hasattr(self, 'login_settings_tab') and hasattr(self.login_settings_tab, 'refresh_theme'):
                self.login_settings_tab.refresh_theme()
            if hasattr(self, 'master_data_tab') and hasattr(self.master_data_tab, 'refresh_theme'):
                self.master_data_tab.refresh_theme()
            if hasattr(self, 'dataset_upload_tab') and hasattr(self.dataset_upload_tab, 'refresh_theme'):
                self.dataset_upload_tab.refresh_theme()
            
            # ウィジェット全体を再描画
            self.update()
            logger.debug("DataPortalWidget: テーマ更新完了")
        except Exception as e:
            logger.error(f"DataPortalWidget: テーマ更新エラー: {e}")
    
    def switch_to_login_tab(self):
        """ログイン設定タブに切り替え"""
        self.tab_widget.setCurrentIndex(0)
    
    def switch_to_master_tab(self):
        """マスタタブに切り替え"""
        self.tab_widget.setCurrentIndex(1)
    
    def switch_to_upload_tab(self):
        """データセットタブに切り替え"""
        self.tab_widget.setCurrentIndex(2)
