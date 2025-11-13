"""
共通UIコントローラークラス - ARIM RDE Tool v1.17.2
機能別UIコントローラーを統合する基本クラス
"""

from qt_compat.widgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from qt_compat.core import QTimer, Signal, QObject
from qt_compat.gui import QFont
import logging

from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog, PopupDialog

logger = logging.getLogger(__name__)


class UIController(QObject):
    """統合UIコントローラー - 各機能UIの基本クラス"""
    
    # シグナル定義
    webview_login_success = Signal()
    dataset_selected = Signal(str)
    
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.logger = logging.getLogger(__name__)
        self._bearer_token = None
        self._webview = None
        
        # UI状態管理
        self.mode_widgets = {}
        self.current_mode = None
        
        # プログレス表示用
        self.progress_dialog = None
        self.progress_timer = None
        
    @property 
    def bearer_token(self):
        """Bearer token getter"""
        return self._bearer_token
        
    @bearer_token.setter
    def bearer_token(self, value):
        """Bearer token setter"""
        self._bearer_token = value
        
    @property
    def webview(self):
        """WebView getter"""
        return self._webview
        
    def setup_main_layout(self):
        """メインレイアウトを設定する"""
        if self.main_window is None:
            self.logger.warning("Main window is not set")
            return
            
        # 基本的なレイアウト設定
        try:
            if hasattr(self.main_window, 'centralWidget'):
                central_widget = self.main_window.centralWidget()
                if central_widget is None:
                    central_widget = QWidget()
                    self.main_window.setCentralWidget(central_widget)
                    
                # レイアウトが存在しない場合は作成
                if central_widget.layout() is None:
                    layout = QVBoxLayout()
                    central_widget.setLayout(layout)
                    
            self.logger.info("Main layout setup completed")
            
        except Exception as e:
            self.logger.error(f"Failed to setup main layout: {e}")
            
    def show_progress_dialog(self, title="処理中", message="お待ちください..."):
        """プログレスダイアログを表示"""
        try:
            if self.progress_dialog is None:
                self.progress_dialog = PopupDialog(self.main_window)
            
            self.progress_dialog.set_title(title)
            self.progress_dialog.set_message(message)
            self.progress_dialog.show()
            
        except Exception as e:
            self.logger.error(f"Failed to show progress dialog: {e}")
    
    def hide_progress_dialog(self):
        """プログレスダイアログを非表示"""
        try:
            if self.progress_dialog:
                self.progress_dialog.hide()
        except Exception as e:
            self.logger.error(f"Failed to hide progress dialog: {e}")
            
    def create_text_area_dialog(self, title, content, parent=None):
        """テキストエリアダイアログを作成"""
        try:
            dialog = TextAreaExpandDialog(parent or self.main_window)
            dialog.set_title(title)
            dialog.set_content(content)
            return dialog
        except Exception as e:
            self.logger.error(f"Failed to create text area dialog: {e}")
            return None
            
    def finalize_window_setup(self):
        """ウィンドウ設定を最終化する"""
        try:
            if self.main_window is None:
                self.logger.warning("Main window is not set for finalization")
                return
                
            # ウィンドウのサイズと位置を調整
            if hasattr(self.main_window, 'resize'):
                # デフォルトサイズを設定
                self.main_window.resize(1200, 800)
                logger.debug("ウィンドウ初期化: 1200x800")
                
            # ウィンドウを中央に配置
            if hasattr(self.main_window, 'center'):
                self.main_window.center()
            elif hasattr(self.main_window, 'move'):
                # フォールバック：画面中央に配置
                screen = self.main_window.screen().geometry()
                size = self.main_window.geometry()
                self.main_window.move(
                    (screen.width() - size.width()) // 2,
                    (screen.height() - size.height()) // 2
                )
                
            # ウィンドウを表示
            if hasattr(self.main_window, 'show'):
                self.main_window.show()
                
            self.logger.info("Window setup finalized")
            
        except Exception as e:
            self.logger.error(f"Failed to finalize window setup: {e}")
        
    def show_error(self, message: str):
        """エラーメッセージ表示"""
        self.logger.error(f"UI Error: {message}")
        # TODO: エラーダイアログ表示
        
    def show_text_area_expanded(self, title: str, content: str):
        """テキストエリア拡大表示"""
        try:
            dialog = TextAreaExpandDialog(title, content, self.main_window)
            dialog.exec()
        except Exception as e:
            self.logger.error(f"テキストエリア表示エラー: {e}")
            
    def update_sample_form(self, sample_id: str, sample_name: str, sample_description: str):
        """サンプルフォーム更新"""
        # 各機能モジュールでオーバーライド
        pass
        
    def init_mode_widgets(self):
        """モードウィジェット初期化"""
        # 各機能モジュールでオーバーライド  
        pass
        
    def switch_mode(self, mode: str):
        """モード切り替え"""
        logger.debug("モード切り替え: %s", mode)
        
        # ウインドウサイズをデバッグ出力
        if self.main_window:
            window_size = self.main_window.size()
            logger.debug("現在のウインドウサイズ: %sx%s", window_size.width(), window_size.height())
            
            # スクリーンサイズとの比較
            from qt_compat.widgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                screen_size = screen.size()
                width_ratio = (window_size.width() / screen_size.width()) * 100
                height_ratio = (window_size.height() / screen_size.height()) * 100
                logger.debug("スクリーン比率: 幅%.1f%% 高さ%.1f%%", width_ratio, height_ratio)
        
        self.current_mode = mode
        # 具体的な実装は各機能モジュールで
        pass
        
    def get_current_mode(self):
        """現在のモード取得"""
        return self.current_mode
        
    def show_progress(self, title: str, message: str, max_value: int = 0):
        """プログレス表示開始"""
        # TODO: プログレスダイアログ実装
        pass
        
    def update_progress(self, value: int, message: str = None):
        """プログレス更新"""
        # TODO: プログレス更新実装
        pass
        
    def hide_progress(self):
        """プログレス非表示"""
        # TODO: プログレス非表示実装
        pass
