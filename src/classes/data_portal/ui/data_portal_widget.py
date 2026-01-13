"""
データポータルメインウィジェット

ログイン設定タブとデータセットアップロードタブを統合したタブウィジェット
"""

from typing import Optional, TYPE_CHECKING

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel
)
from qt_compat.core import Signal

from classes.managers.log_manager import get_logger
from .login_settings_tab import LoginSettingsTab
if TYPE_CHECKING:
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

        # 遅延生成用
        self.master_data_tab: Optional["MasterDataTab"] = None
        self._master_placeholder = None
        self._pending_portal_client = None

        self.dataset_upload_tab: Optional["DatasetUploadTab"] = None
        self._upload_placeholder = None

        self._init_ui()
        self._connect_signals()
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        
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

        # マスタデータタブ（初回表示時まで生成を遅延）
        self._master_placeholder = QWidget(self)
        placeholder_layout = QVBoxLayout(self._master_placeholder)
        placeholder_layout.setContentsMargins(12, 12, 12, 12)
        placeholder_layout.addWidget(QLabel("読み込み中..."))
        placeholder_layout.addStretch()
        self.tab_widget.addTab(self._master_placeholder, "📋 マスタ")

        # データセットJSONアップロードタブ（初回表示時まで生成を遅延）
        self._upload_placeholder = QWidget(self)
        upload_placeholder_layout = QVBoxLayout(self._upload_placeholder)
        upload_placeholder_layout.setContentsMargins(12, 12, 12, 12)
        upload_placeholder_layout.addWidget(QLabel("読み込み中..."))
        upload_placeholder_layout.addStretch()
        self.tab_widget.addTab(self._upload_placeholder, "📤 データカタログ")
        
        layout.addWidget(self.tab_widget)

        # タブ切替で遅延生成
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
    
    def _connect_signals(self):
        """シグナル接続"""
        # ログインテスト完了シグナルを転送
        self.login_settings_tab.login_test_completed.connect(
            self._on_login_test_completed
        )
        
        # アップロードタブは遅延生成のため、生成時に接続する
        
        # マスタタブは遅延生成のため、生成時に接続する
        
        # 認証情報保存後にアップロードタブを有効化
        self.login_settings_tab.credentials_saved.connect(
            self._on_credentials_saved
        )
    
    def _on_login_test_completed(self, success: bool, message: str):
        """ログインテスト完了時の処理"""
        # シグナルを転送
        self.login_test_completed.emit(success, message)
        
        # 成功時にPortalClientをマスタタブに設定（マスタタブが未生成なら保留）
        if success and hasattr(self.login_settings_tab, 'portal_client'):
            portal_client = self.login_settings_tab.portal_client
            if portal_client:
                self._pending_portal_client = portal_client
                if self.master_data_tab is not None:
                    self.master_data_tab.set_portal_client(portal_client)
                    logger.info("マスタタブにPortalClientを設定しました")

    def _on_tab_changed(self, index: int) -> None:
        """タブ切替時の遅延初期化"""
        try:
            # 0: login, 1: master, 2: upload
            if index == 0:
                try:
                    if hasattr(self, "login_settings_tab") and hasattr(self.login_settings_tab, "auto_test_connections"):
                        self.login_settings_tab.auto_test_connections()
                except Exception:
                    pass
            elif index == 1:
                self._ensure_master_tab()
            elif index == 2:
                self._ensure_upload_tab()
        except Exception as e:
            logger.error("DataPortalWidget: tab change handling failed: %s", e)

    def _ensure_master_tab(self) -> None:
        if self.master_data_tab is not None:
            return
        idx = self.tab_widget.indexOf(self._master_placeholder)
        if idx < 0:
            # 何らかの理由で placeholder が無い場合は末尾に追加
            idx = 1

        from .master_data_tab import MasterDataTab

        self.master_data_tab = MasterDataTab(self)
        # シグナルを転送
        self.master_data_tab.master_fetched.connect(self.master_fetched.emit)
        # 保留していた PortalClient を設定
        if self._pending_portal_client is not None:
            try:
                self.master_data_tab.set_portal_client(self._pending_portal_client)
                logger.info("マスタタブにPortalClientを設定しました")
            except Exception as e:
                logger.error("マスタタブへのPortalClient設定に失敗: %s", e)

        # 置換
        self.tab_widget.removeTab(idx)
        self.tab_widget.insertTab(idx, self.master_data_tab, "📋 マスタ")
        # current tab を維持
        self.tab_widget.setCurrentIndex(idx)

    def _ensure_upload_tab(self) -> None:
        if self.dataset_upload_tab is not None:
            return
        idx = self.tab_widget.indexOf(self._upload_placeholder)
        if idx < 0:
            idx = 2

        from .dataset_upload_tab import DatasetUploadTab

        self.dataset_upload_tab = DatasetUploadTab(self)
        # シグナルを転送
        self.dataset_upload_tab.upload_completed.connect(self.upload_completed.emit)

        # 置換
        self.tab_widget.removeTab(idx)
        self.tab_widget.insertTab(idx, self.dataset_upload_tab, "📤 データカタログ")
        self.tab_widget.setCurrentIndex(idx)
    
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
            if self.dataset_upload_tab is not None and hasattr(self.dataset_upload_tab, 'refresh_theme'):
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

    def open_upload_and_select_dataset(self, dataset_id: str) -> bool:
        """データカタログ(アップロード)タブを開き、dataset_idを選択する。

        DataPortalWidget は upload タブを遅延生成するため、本メソッドで
        生成→タブ移動→選択までを一括で行う。
        """

        self.switch_to_upload_tab()
        try:
            self._ensure_upload_tab()
        except Exception as e:
            logger.error("DataPortalWidget: failed to ensure upload tab: %s", e)
            return False

        try:
            if self.dataset_upload_tab is None:
                return False
            select_fn = getattr(self.dataset_upload_tab, "select_dataset_id", None)
            if callable(select_fn):
                return bool(select_fn(dataset_id))
        except Exception as e:
            logger.error("DataPortalWidget: dataset selection failed: %s", e)
        return False
