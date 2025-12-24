#!/usr/bin/env python3

"""
ARIM RDE Tool v2.3.6 - PySide6によるRDE→ARIMデータポータル移行ツール

主要機能:
- RDEシステムへの自動ログイン・データセット一括取得・画像保存
- PySide6 WebView統合ブラウザによる認証・操作自動化
- ARIM匿名化・HTMLログ出力・統合API処理・AI分析機能
- OAuth2 RefreshToken対応トークン管理システム（TokenManager）

v2.1.7新機能:
- テーマ切替最適化完了（不要な再処理を完全除去）
- refresh_theme()で配色のみ更新・ファイルIO/API呼出し/再構築を回避
- QMenu/QToolTip/QHeaderView/QProgressBar のグローバルスタイル追加
- パレット強制適用強化（OS/アプリテーマ不一致対応完全解決）
- テーマウィジェット監査完了・検証スクリプト実装

v2.1.3機能:
- データ取得2機能のファイル単位プログレス表示改善
- 並列ダウンロード対応とスレッドセーフなカウンター実装
- 2段階プログレス表示（ファイルリスト取得→ダウンロード）

v2.0.5機能:
- truststore統合によるSSL検証強化（Windows証明書ストア対応）
- APIアクセスログ機能実装（daily rotation・自動クリーンアップ）
- プロキシ設定変更時の自動再起動プロンプト実装
- SSL/プロキシ/処理時間の包括的ログ記録

v2.0.3機能:
- ログインUI完全簡素化（ボタンのみ表示）
- 自動ログイン手動実行機能
- test-host.example.comトークンエラー完全除外
- 包括的デバッグログ実装（LOGIN-EXECUTE/TOKEN-ACQ）
- トークン状態タブで2ホスト固定表示

v2.0.1機能:
- トークン自動リフレッシュ（QTimer 60秒間隔、5分前マージン）
- トークン状態表示タブ（有効期限・残り時間表示）
- マルチホストトークン管理（RDE/Material API対応）
- 手動リフレッシュAPI実装

アーキテクチャ:
- 責務分離された専門クラス群による高保守性
- EventHandlerManager統合イベント処理システム
- 動的パス管理・環境切替対応・統一ログシステム
- プロキシ設定UI改善・PAC/企業CA設定の横並び表示対応

注意: バージョン更新時はconfig/common.pyのREVISIONも要確認
"""

# 標準ライブラリ
import sys
import argparse
import os

import logging

# ロガー設定
logger = logging.getLogger(__name__)
# PyQt5 - WebEngine初期化問題の回避
from qt_compat import initialize_webengine
from qt_compat.core import Qt

# WebEngine初期化
initialize_webengine()
from qt_compat.widgets import QApplication, QWidget, QLabel
from qt_compat.webengine import QWebEngineView, QWebEngineProfile
from qt_compat.webengine_page import WebEnginePageWithConsole
from qt_compat.core import QTimer
from qt_compat.gui import QIcon
# 設定・関数モジュール
from config.common import REVISION, OUTPUT_DIR, DYNAMIC_IMAGE_DIR, get_static_resource_path,get_base_dir
from functions.common_funcs import read_login_info
# テーマ管理
from classes.theme import get_color, ThemeKey, ThemeManager, ThemeMode, apply_window_frame_theme
from classes.utils.button_styles import get_button_style
# クラス群
from classes.core import AppInitializer
from classes.core import ImageInterceptor
from classes.managers.overlay_manager import OverlayManager
from classes.managers.login_manager import LoginManager
from classes.core import BrowserController
from classes.managers.event_handler_manager import EventHandlerManager
from classes.utils.debug_log import debug_log
from classes.managers.app_config_manager import get_config_manager
from classes.managers.log_manager import get_log_manager, get_logger
# ログ管理の初期化
log_manager = get_log_manager()
logger = get_logger("RDE_WebView")
# スプラッシュスクリーン
try:
    from classes.utils.splash_screen import show_splash_screen
    SPLASH_AVAILABLE = True
except Exception as e:
    SPLASH_AVAILABLE = False
    logger.warning(f"スプラッシュスクリーン機能が利用できません: {e}")
    def show_splash_screen():
        """スプラッシュスクリーン無効時のダミー関数"""
        return

class Browser(QWidget):
    @debug_log
    def is_rde_logged_in_url(self, url):
        """RDEログイン完了後の画面かどうかを判定（BrowserControllerに委譲）"""
        return self.browser_controller.is_rde_logged_in_url(url)

    @debug_log
    def set_webview_message(self, msg):
        """WebView下部メッセージ表示（DisplayManagerに委譲）"""
        self.display_manager.set_message(msg)

    @debug_log
    def __init__(self, auto_close=False, test_mode=False):
        """Browserクラス初期化（WebView設定・ログイン情報読み込み）"""
        super().__init__()
        
        # テーマ管理の初期化（最優先）
        theme_manager = ThemeManager.instance()
        detected = theme_manager.detect_system_theme()
        theme_manager.set_mode(detected)
        theme_manager.theme_changed.connect(self._on_theme_mode_changed)
        logger.info(f"[Theme] 初期テーマモード (OS検出): {detected.value}")
        
        # 基本属性の初期化
        self._init_basic_attributes(auto_close, test_mode)
        # UI要素の初期化
        self._init_ui_elements()

        # 各種マネージャーの初期化
        self.app_initializer = AppInitializer(self)
        self.app_initializer.initialize_all()

        # ログイン情報の初期化
        # v1.20.3: レガシーファイルと新認証システムの統合
        legacy_username, legacy_password, legacy_mode = read_login_info()
        
        # LoginManager初期化（新認証システム）
        self.login_manager = LoginManager(self, self.webview, self.autologin_msg_label)
        
        # v2.1.0: TokenManager初期化・自動リフレッシュ開始
        try:
            from classes.managers.token_manager import TokenManager
            self.token_manager = TokenManager.get_instance()
            self.token_manager.start_auto_refresh()
            
            # Signal接続: トークン更新成功/失敗通知
            self.token_manager.token_refreshed.connect(self._on_token_refreshed)
            self.token_manager.token_refresh_failed.connect(self._on_token_refresh_failed)
            self.token_manager.token_expired.connect(self._on_token_expired)
            
            logger.info("[TokenManager] 自動リフレッシュタイマー開始")
            logger.info("TokenManager初期化完了 - 自動リフレッシュ有効")
        except Exception as tm_err:
            logger.error(f"[TokenManager] 初期化エラー: {tm_err}", exc_info=True)
            logger.error("TokenManager初期化失敗: %s", tm_err)
        
        # レガシーファイルが優先（互換性維持）、なければ新認証システムの値を使用
        if legacy_username or legacy_password:
            self.login_username = legacy_username
            self.login_password = legacy_password
            self.login_mode = legacy_mode
            logger.info("レガシーログイン情報使用: %s", self.login_username)
        else:
            # 新認証システムから読み込まれた値を使用
            self.login_username = getattr(self.login_manager, 'login_username', None)
            self.login_password = getattr(self.login_manager, 'login_password', None)
            self.login_mode = getattr(self.login_manager, 'login_mode', None)
            if self.login_username:
                logger.info("新認証システムログイン情報使用: %s", self.login_username)
            else:
                logger.info("ログイン情報なし - 手動ログインが必要です")

        # BrowserControllerの初期化
        self.browser_controller = BrowserController(self)

        # EventHandlerManagerの初期化
        self.event_handler_manager = EventHandlerManager(self)

        # WebViewとレイアウトの設定
        self._setup_webview_and_layout()

        # 初期モードをloginに設定
        self.current_mode = "login"
        if hasattr(self, 'overlay_manager') and self.overlay_manager:
            self.overlay_manager.hide_overlay()
        self.switch_mode(self.current_mode)

        # v2.0.4: デバッグモード起動時のクリーンアップ
        from classes.utils.token_cleanup import cleanup_on_startup
        cleanup_on_startup()

        # ウィンドウの表示と最終設定
        self._finalize_window_setup()

        # プロキシ起動時通知（UIが完全に表示された後）
        QTimer.singleShot(500, self._show_proxy_startup_notification)
        
        # v2.0.2: 起動時トークン確認とUI無効化
        QTimer.singleShot(1000, self._check_initial_tokens)

        if self.test_mode:
            QTimer.singleShot(100, self.quick_test_exit)

    def _init_basic_attributes(self, auto_close, test_mode):
        """基本属性の初期化"""
        # 設定管理の初期化
        self.config_manager = get_config_manager()
        
        self.overlay = None
        self.overlay_manager = None
        self.setWindowTitle(f"ARIM-RDE-TOOL {REVISION}")
        icon_path = get_static_resource_path("image/icon/icon1.ico")
        self.setWindowIcon(QIcon(icon_path))
        self.image_dir = DYNAMIC_IMAGE_DIR
        self.cookies = []
        self.closed = False
        self.auto_close = auto_close
        self.bearer_token = None
        self.webview = QWebEngineView()
        
        # PySide6対応: JavaScriptコンソールメッセージを有効化するカスタムPageを設定
        # デフォルトProfileを引き継ぐために、既存のProfileを渡す
        from qt_compat.webengine import QWebEngineProfile
        default_profile = QWebEngineProfile.defaultProfile()
        custom_page = WebEnginePageWithConsole(default_profile, self.webview)
        self.webview.setPage(custom_page)
        logger.info("[WEBENGINE] カスタムPageを設定してJavaScriptコンソールを有効化")
        
        self._recent_blob_hashes = set()
        self._data_id_image_counts = {}
        self._active_image_processes = set()
        self._current_image_grant_number = None
        self.test_mode = test_mode
        self._test_timer = None
        # 設定管理からデフォルトのgrant_numberを取得
        self.grant_number = self.config_manager.get("app.default_grant_number", "JPMXP1222TU0195")
        self.grant_input = None
        self.grant_btn = None
        # 設定管理から自動ログイン設定を取得
        self.auto_login_enabled = self.config_manager.get("app.auto_login_enabled", False)

    def _init_ui_elements(self):
        """UI要素の初期化"""
        # オーバーレイマネージャーの初期化（webview生成直後に必ず実行）
        self.overlay_manager = OverlayManager(self, self.webview)

        # EventHandlerの初期化
        from classes.core import EventHandler
        self.event_handler = EventHandler(self)
        self.event_handler.set_auto_close(self.auto_close)

        self.webview.setFixedHeight(500)
        #self.webview.setFixedWidth(900)
        #self._webview_fixed_width = 900
        # v2.0.2: 待機メッセージ専用ラベル（目立つスタイル）
        from qt_compat.core import Qt
        self.autologin_msg_label = QLabel('準備中...')
        self.autologin_msg_label.setStyleSheet(f'''
            QLabel {{
                background-color: {get_color(ThemeKey.PANEL_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.PANEL_INFO_TEXT)};
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                border: 1px solid {get_color(ThemeKey.PANEL_INFO_BORDER)};
                border-radius: 6px;
                margin: 5px;
            }}
        ''')
        self.autologin_msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.autologin_msg_label.setMinimumHeight(50)
        self.autologin_msg_label.setText('自動ログインは現在無効です')
        
        self.webview_msg_label = QLabel('')
        self.webview_msg_label.setStyleSheet(f'color: {get_color(ThemeKey.TEXT_WARNING)}; font-size: 13px; padding: 2px;')
        
        # v2.1.3: ログイン処理説明ラベル（停止時の対処説明）
        self.login_help_label = QLabel(
            "💡 ログイン処理が途中で止まった場合は、「ログイン実行」ボタンでやり直してください。"
        )
        self.login_help_label.setStyleSheet(f"""
            QLabel {{
                background-color: {get_color(ThemeKey.PANEL_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.PANEL_INFO_TEXT)};
                padding: 8px;
                border-radius: 4px;
                border: 1px solid {get_color(ThemeKey.PANEL_INFO_BORDER)};
                font-size: 9pt;
            }}
        """)
        self.login_help_label.setWordWrap(True)
        self.login_help_label.setVisible(False)  # 初期は非表示
        
        # v1.16: レガシー警告バナー用ウィジェット
        self.legacy_warning_banner = None

    def _setup_webview_and_layout(self):
        """WebViewとレイアウトの設定"""
        # v1.20.3: PySide6対応 - WebEngineの設定を明示的に有効化
        from qt_compat.webengine import QWebEngineSettings
        settings = self.webview.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        logger.info("[WEBENGINE] JavaScript と LocalStorage を有効化")
        
        interceptor = ImageInterceptor()
        self.webview.page().profile().setUrlRequestInterceptor(interceptor)
        self.browser_controller.setup_webview(self.webview)
        self.webview.page().profile().cookieStore().cookieAdded.connect(self.login_manager.on_cookie_added)
        self.ui_controller.setup_main_layout()

    def _finalize_window_setup(self):
        """ウィンドウの表示と最終設定"""
        self.ui_controller.finalize_window_setup()
        # 標準ウィンドウ枠のカラーも現在のテーマに追従させる
        QTimer.singleShot(0, self._apply_native_titlebar_theme)

    def _show_proxy_startup_notification(self):
        """プロキシ起動時通知を表示"""
        try:
            logger.info("プロキシ起動時通知を表示開始")
            
            from classes.config.ui.proxy_startup_notification import show_proxy_startup_notification
            
            # AppInitializerで初期化されたプロキシ設定から情報を取得
            proxy_config = {}
            
            # グローバルセッションマネージャーから設定を取得
            try:
                from net.session_manager import get_current_proxy_config
                proxy_config = get_current_proxy_config()
                logger.info(f"グローバルプロキシ設定取得: {proxy_config}")
            except Exception as e:
                logger.warning(f"グローバルプロキシ設定取得失敗: {e}")
                
                # フォールバック: 設定ファイルから直接読み込み
                try:
                    import yaml
                    from config.common import get_dynamic_file_path
                    
                    yaml_path = get_dynamic_file_path("config/network.yaml")
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                    proxy_config = data.get('network', {})
                    logger.info(f"ファイルからプロキシ設定取得: {proxy_config}")
                    
                except Exception as e2:
                    logger.warning(f"設定ファイル読み込み失敗: {e2}")
                    proxy_config = {"mode": "UNKNOWN"}
            
            # 通知を表示
            show_proxy_startup_notification(proxy_config, self)
            
            logger.info("プロキシ起動時通知表示完了")
            
        except Exception as e:
            logger.warning(f"プロキシ起動時通知エラー: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def _on_theme_mode_changed(self, _mode):
        """テーマ変更時にタイトルバー配色を更新"""
        QTimer.singleShot(0, self._apply_native_titlebar_theme)

    def _apply_native_titlebar_theme(self):
        """OS標準ウィンドウ枠にテーマを適用"""
        try:
            apply_window_frame_theme(self)
        except Exception as err:
            logger.debug("タイトルバーのテーマ適用に失敗しました: %s", err)
    
    # v2.1.0: TokenManager Signal Handlers
    def _on_token_refreshed(self, host):
        """トークン更新成功通知ハンドラ"""
        logger.info(f"[TokenManager] トークン自動更新成功: {host}")
        logger.info("トークン更新成功: %s", host)
        # UI通知は不要（自動更新のため）
    
    def _on_token_refresh_failed(self, host, error):
        """トークン更新失敗通知ハンドラ"""
        logger.warning(f"[TokenManager] トークン自動更新失敗: {host} - {error}")
        logger.warning("トークン更新失敗: %s - %s", host, error)
        # 必要に応じてUI通知を追加可能
    
    def _on_token_expired(self, host):
        """RefreshToken期限切れ通知ハンドラ（再ログイン必要）"""
        # v2.0.3: TokenManagerのクラス定数を使用（2ホスト固定）
        from classes.managers.token_manager import TokenManager
        
        if host not in TokenManager.ACTIVE_HOSTS:
            logger.debug(f"[TokenManager] 非アクティブホストの期限切れ通知を無視: {host}")
            return
        
        logger.error(f"[TokenManager] RefreshToken期限切れ: {host} - 再ログインが必要です")
        logger.error("RefreshToken期限切れ: %s - 再ログインしてください", host)
        
        # UI通知（ユーザーに再ログインを促す）
        from qt_compat.widgets import QMessageBox
        QMessageBox.warning(
            self,
            "トークン期限切れ",
            f"ホスト '{host}' のRefreshTokenが期限切れです。\n\n"
            "再ログインしてください。",
            QMessageBox.StandardButton.Ok
        )
    
    def _check_initial_tokens(self):
        """
        起動時にトークンの状態を確認し、UIを制御
        v2.0.2: トークン確認機能
        v2.0.4: DEBUG_SKIP_LOGIN_CHECK環境変数対応・トークン自動クリア
        """
        try:
            logger.info("[TOKEN-CHECK] 起動時トークン確認開始")
            
            # デバッグモード確認
            debug_skip = os.environ.get('DEBUG_SKIP_LOGIN_CHECK', '').lower() in ('1', 'true', 'yes')
            if debug_skip:
                from classes.utils.token_cleanup import get_debug_status_message
                logger.warning("[DEBUG] DEBUG_SKIP_LOGIN_CHECK有効 - ログインチェックをスキップして全機能を有効化")
                self.autologin_msg_label.setText(get_debug_status_message())
                self.autologin_msg_label.setVisible(True)
                if hasattr(self, 'ui_controller'):
                    self.ui_controller.set_buttons_enabled_except_login_settings(True)
                return
            
            # トークンの存在確認
            rde_exists, material_exists = self.login_manager.check_tokens_acquired()
            
            if rde_exists and material_exists:
                # 両方のトークンが存在する場合
                logger.info("[TOKEN-CHECK] 両トークン存在 - 全機能を有効化")
                self.autologin_msg_label.setText("✅ ログイン済み（トークン確認完了）")
                self.autologin_msg_label.setVisible(True)
                QTimer.singleShot(3000, lambda: self.autologin_msg_label.setVisible(False))
                
                # UI有効化
                if hasattr(self, 'ui_controller'):
                    self.ui_controller.set_buttons_enabled_except_login_settings(True)
                
                # ログイン完了通知を送信
                if hasattr(self.login_manager, '_notify_login_complete'):
                    self.login_manager._rde_token_acquired = True
                    self.login_manager._material_token_acquired = True
                    self.login_manager._login_in_progress = False
                    QTimer.singleShot(500, self.login_manager._notify_login_complete)
            else:
                # トークンが不足している場合
                if not rde_exists and not material_exists:
                    logger.info("[TOKEN-CHECK] トークンなし - ログインが必要")
                    msg = "ログインしてください"
                elif not rde_exists:
                    logger.info("[TOKEN-CHECK] RDEトークンなし")
                    msg = "RDEトークンが必要です"
                else:
                    logger.info("[TOKEN-CHECK] マテリアルトークンなし")
                    msg = "マテリアルトークンが必要です"
                
                self.autologin_msg_label.setText(f"⚠️ {msg}")
                self.autologin_msg_label.setVisible(True)
                
                # UI無効化（ログインと設定以外）
                if hasattr(self, 'ui_controller'):
                    self.ui_controller.set_buttons_enabled_except_login_settings(False)
                
                # 自動ログイン有効時は自動的にトークン取得を開始
                if self.auto_login_enabled:
                    logger.info("[TOKEN-CHECK] 自動ログイン有効 - トークン取得開始")
                    self.autologin_msg_label.setText("🔄 自動ログイン中...")
                    self.login_manager._login_in_progress = True
                    
                    # トークン取得を開始（不足分のみ）
                    QTimer.singleShot(2000, lambda: self.login_manager.ensure_both_tokens(is_autologin=True))
                    
        except Exception as e:
            logger.error(f"[TOKEN-CHECK] 起動時トークン確認エラー: {e}", exc_info=True)


    def switch_mode(self, mode):
        """モードを切り替える"""
        self.ui_controller.switch_mode(mode)
        self.current_mode = mode  # 互換性のため保持

    # 動的委譲メソッド（単純委譲メソッドの統合）
    def __getattr__(self, name):
        """単純委譲メソッドの動的ルーティング"""
        # UIController委譲メソッド
        ui_methods = ['update_menu_button_styles', 'setup_data_fetch_mode', 'show_dummy_message', 
                     'show_grant_number_form', 'update_image_limit']
        # EventHandlerManager委譲メソッド
        eh_methods = ['execute_batch_grant_numbers', 'save_cookies_and_show_grant_form', 
                     'on_load_finished', '_hash_blob', 'center_window']
        
        if name in ui_methods and hasattr(self, 'ui_controller'):
            return getattr(self.ui_controller, name)
        elif name in eh_methods and hasattr(self, 'event_handler_manager'):
            return getattr(self.event_handler_manager, name)
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def quick_test_exit(self):
        """テスト用の早期終了メソッド"""
        self.stop_blinking_msg()
        if hasattr(self, 'display_manager') and self.display_manager:
            self.display_manager.stop_blinking_msg()
        logger.debug("初期化テスト完了 - 早期終了")
        QApplication.quit()
    
    def show_legacy_warning_banner(self):
        """レガシーファイル使用時の警告バナーを表示（v1.16追加）"""
        try:
            if self.legacy_warning_banner:
                # 既に表示済みの場合はスキップ
                return
            
            from qt_compat.widgets import QFrame, QHBoxLayout, QPushButton, QLabel
            from qt_compat.core import Qt
            
            # 警告バナーウィジェット作成
            self.legacy_warning_banner = QFrame()
            self.legacy_warning_banner.setStyleSheet(
                f"background-color: {get_color(ThemeKey.NOTIFICATION_WARNING_BACKGROUND)}; "
                f"border: 1px solid {get_color(ThemeKey.NOTIFICATION_WARNING_BORDER)}; "
                "border-radius: 4px; margin: 5px; padding: 10px;"
            )
            
            banner_layout = QHBoxLayout(self.legacy_warning_banner)
            
            # 警告アイコンとメッセージ
            warning_icon = QLabel("⚠️")
            warning_icon.setFixedWidth(30)
            banner_layout.addWidget(warning_icon)
            
            warning_message = QLabel(
                "旧 input/login.txt を使用しています（平文保存のため非推奨）。"
                "設定 > 自動ログイン から安全な保存先へ移行してください。"
            )
            warning_message.setStyleSheet(f"color: {get_color(ThemeKey.NOTIFICATION_WARNING_TEXT)}; font-weight: bold;")
            warning_message.setWordWrap(True)
            banner_layout.addWidget(warning_message, 1)
            
            # 設定ボタン
            settings_button = QPushButton("設定を開く")
            settings_button.setStyleSheet(get_button_style('warning'))
            settings_button.clicked.connect(self._open_autologin_settings)
            banner_layout.addWidget(settings_button)
            
            # 閉じるボタン
            close_button = QPushButton("×")
            close_button.setFixedSize(25, 25)
            close_button.setStyleSheet(get_button_style('close'))
            close_button.clicked.connect(self._hide_legacy_warning_banner)
            banner_layout.addWidget(close_button)
            
            # メインレイアウトの先頭に挿入
            if hasattr(self, 'ui_controller') and hasattr(self.ui_controller, 'main_layout'):
                self.ui_controller.main_layout.insertWidget(0, self.legacy_warning_banner)
            else:
                # フォールバック: Browserウィジェットのレイアウトに追加
                if self.layout():
                    self.layout().insertWidget(0, self.legacy_warning_banner)
            
            logger.info("レガシー警告バナー表示")
            
        except Exception as e:
            logger.error(f"レガシー警告バナー表示エラー: {e}")
    
    def _hide_legacy_warning_banner(self):
        """レガシー警告バナーを非表示"""
        try:
            if self.legacy_warning_banner:
                self.legacy_warning_banner.setVisible(False)
                logger.info("レガシー警告バナーを非表示")
        except Exception as e:
            logger.error(f"レガシー警告バナー非表示エラー: {e}")
    
    def _open_autologin_settings(self):
        """自動ログイン設定画面を開く"""
        try:
            from classes.config.ui.settings_dialog import run_settings_logic
            run_settings_logic(self, getattr(self, 'bearer_token', None))
        except Exception as e:
            logger.error(f"設定ダイアログ起動エラー: {e}")
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(self, "エラー", f"設定画面の起動に失敗しました: {e}")

    def run_test_flow(self):
        # 自動ログイン・自動grantNumber検索・自動終了
        self.set_webview_message('[TEST] 自動テストフロー開始')
        # 1. 自動ログイン（login_managerに自動入力・自動submit機能があれば呼び出し）
        if hasattr(self.login_manager, 'auto_login'):
            self.login_manager.auto_login()
        # 2. grantNumber自動入力・検索（UI部品があれば直接セット）
        if hasattr(self, 'grant_input') and self.grant_input:
            self.grant_input.setText(self.grant_number)
        # grantNumber検索ボタンがあれば自動クリック
        if hasattr(self, 'grant_btn') and self.grant_btn:
            self.grant_btn.click()
        # 3. 一定時間後に自動終了（出力検証も実施）
        QTimer.singleShot(10000, self.check_output_and_quit)

    def check_output_and_quit(self):
        # 出力ディレクトリのファイル・階層を検証
        import os
        base_dir = os.path.join(OUTPUT_DIR, 'datasets', self.grant_number)
        found = os.path.exists(base_dir) and len(os.listdir(base_dir)) > 0
        msg = '[TEST] 出力ディレクトリ検証: ' + ('OK' if found else 'NG')
        self.set_webview_message(msg)
        print(msg)
        
        # test_modeでは全てのタイマーを停止
        if self.test_mode:
            self.stop_blinking_msg()
            if hasattr(self, 'display_manager') and self.display_manager:
                self.display_manager.stop_blinking_msg()
            if hasattr(self, 'login_manager') and self.login_manager:
                logger.info("LoginManager処理を停止")
        QApplication.quit()

    def show_overlay(self, watermark_text=None):
        # ダミー関数（オーバーレイを表示しない）
        return

    def hide_overlay(self):
        self.overlay_manager.hide_overlay()

    def resizeEvent(self, event):
        self.event_handler.handle_resize_event(event)
        super().resizeEvent(event)

    def eventFilter(self, obj, event):
        if self.event_handler.handle_event_filter(obj, event):
            return True
        if self.overlay_manager.event_filter(obj, event):
            return True
        return super().eventFilter(obj, event)


    @debug_log
    def update_autologin_msg(self, msg):
        """
        待機メッセージを更新（v2.0.2: スタイル動的変更対応）
        """
        self.display_manager.set_autologin_message(msg)
        
        # メッセージ内容に応じてスタイルを変更
        if hasattr(self, 'autologin_msg_label'):
            if "✅" in msg or "完了" in msg or "ログイン済み" in msg:
                # 成功スタイル（緑）
                self.autologin_msg_label.setStyleSheet(f'''
                    QLabel {{
                        background-color: {get_color(ThemeKey.NOTIFICATION_SUCCESS_BACKGROUND)};
                        color: {get_color(ThemeKey.NOTIFICATION_SUCCESS_TEXT)};
                        font-size: 14px;
                        font-weight: bold;
                        padding: 12px;
                        border: 1px solid {get_color(ThemeKey.NOTIFICATION_SUCCESS_BORDER)};
                        border-radius: 6px;
                        margin: 5px;
                    }}
                ''')
            elif "⚠️" in msg or "エラー" in msg or "失敗" in msg:
                # 警告スタイル（オレンジ/赤）
                self.autologin_msg_label.setStyleSheet(f'''
                    QLabel {{
                        background-color: {get_color(ThemeKey.NOTIFICATION_ERROR_BACKGROUND)};
                        color: {get_color(ThemeKey.NOTIFICATION_ERROR_TEXT)};
                        font-size: 14px;
                        font-weight: bold;
                        padding: 12px;
                        border: 1px solid {get_color(ThemeKey.NOTIFICATION_ERROR_BORDER)};
                        border-radius: 6px;
                        margin: 5px;
                    }}
                ''')
            elif "🔄" in msg or "処理中" in msg or "ログイン中" in msg:
                # 処理中スタイル（青）
                self.autologin_msg_label.setStyleSheet(f'''
                    QLabel {{
                        background-color: {get_color(ThemeKey.PANEL_INFO_BACKGROUND)};
                        color: {get_color(ThemeKey.PANEL_INFO_TEXT)};
                        font-size: 14px;
                        font-weight: bold;
                        padding: 12px;
                        border: 1px solid {get_color(ThemeKey.PANEL_INFO_BORDER)};
                        border-radius: 6px;
                        margin: 5px;
                    }}
                ''')
            else:
                # デフォルトスタイル（グレー）
                self.autologin_msg_label.setStyleSheet(f'''
                    QLabel {{
                        background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
                        color: {get_color(ThemeKey.PANEL_NEUTRAL_TEXT)};
                        font-size: 14px;
                        font-weight: bold;
                        padding: 12px;
                        border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                        border-radius: 6px;
                        margin: 5px;
                    }}
                ''')
        
        # 点滅中はラベルを必ず表示
        if hasattr(self.display_manager, 'blinking_state') and self.display_manager.blinking_state:
            if self.display_manager.autologin_msg_label:
                self.display_manager.autologin_msg_label.setVisible(True)

    @debug_log
    def start_blinking_msg(self):
        self.display_manager.start_blinking_msg(self)

    @debug_log
    def stop_blinking_msg(self):
        self.display_manager.stop_blinking_msg()

    @debug_log
    def toggle_blinking_msg(self):
        self.display_manager.toggle_blinking_msg()

    @debug_log
    def try_get_bearer_token(self, retries=3):
        """LoginManagerに処理を委譲"""
        self.login_manager.try_get_bearer_token(retries)

    @debug_log
    def log_webview_html(self, url=None):
        """HtmlLoggerに処理を委譲"""
        self.html_logger.log_webview_html(self.webview, url)

    @debug_log
    def on_url_changed(self, url):
        """URL変更時の処理（BrowserControllerに委譲）"""
        self.browser_controller.on_url_changed(url)

    @debug_log
    def closeEvent(self, event):
        # v2.0.4: デバッグモード終了時のクリーンアップ
        from classes.utils.token_cleanup import cleanup_on_exit
        cleanup_on_exit()
        
        event.accept()

    @debug_log
    def on_grant_number_decided(self, *args, **kwargs):
        self.grant_input.setDisabled(True)
        self.grant_btn.setDisabled(True)
        new_grant_number = self.grant_input.text().strip()
        success = self.project_manager.process_grant_number(new_grant_number)
        
        # 結果に応じてメッセージを表示
        if success:
            self.result_label.setText("データ取得・保存が完了しました")
            self.set_webview_message('課題情報取得完了')
        else:
            self.result_label.setText("データ取得中にエラーが発生しました")
            self.set_webview_message('課題情報取得エラー')
        
        # grantNumber入力欄と決定ボタンを再度有効化
        self.grant_input.setDisabled(False)
        self.grant_btn.setDisabled(False)
        
        # 検索完了後、WebView下部のメッセージをクリア
        self.set_webview_message('')

    @debug_log
    def search_and_save_result(self, grant_number=None):
        """API検索・保存処理（EventHandlerManagerに委譲）"""
        self.event_handler_manager.search_and_save_result(grant_number)

    @debug_log
    def fetch_and_save_multiple_datasets(self, grant_number=None):
        """複数データセット取得・保存処理（EventHandlerManagerに委譲）"""
        self.event_handler_manager.fetch_and_save_multiple_datasets(grant_number)

    @debug_log
    def process_dataset_id(self, id, name, details_dir, headers, fetch_and_save_data_list=None):
        """データセット処理（EventHandlerManagerに委譲）"""
        self.event_handler_manager.process_dataset_id(id, name, details_dir, headers, fetch_and_save_data_list)

    @debug_log
    def save_webview_blob_images(self, data_id, subdir, headers):
        """WebView blob画像保存（EventHandlerManagerに委譲）"""
        self.event_handler_manager.save_webview_blob_images(data_id, subdir, headers)

    def _start_blob_image_polling(self, data_id, subdir, headers):
        """blob画像ポーリング開始（EventHandlerManagerに委譲）"""
        self.event_handler_manager._start_blob_image_polling(data_id, subdir, headers)

    def _extract_and_save_blob_images(self, blob_srcs, loop, max_images=None, data_id=None):
        """blob画像抽出・保存（EventHandlerManagerに委譲）"""
        self.event_handler_manager._extract_and_save_blob_images(blob_srcs, loop, max_images, data_id)

    @debug_log
    def apply_arim_anonymization(self, dataset_dir, grant_number):
        """ARIM匿名化処理（EventHandlerManagerに委譲）"""
        self.event_handler_manager.apply_arim_anonymization(dataset_dir, grant_number)

    @debug_log
    def fetch_and_save_dataset_detail(self, id, subdir, headers, datatree_json_path):
        """データセット詳細取得・保存（EventHandlerManagerに委譲）"""
        self.event_handler_manager.fetch_and_save_dataset_detail(id, subdir, headers, datatree_json_path)

    @debug_log
    def handle_blob_images(self, dir_path, result, data_id=None):
        """blob画像データ保存（EventHandlerManagerに委譲）"""
        self.event_handler_manager.handle_blob_images(dir_path, result, data_id)

    @debug_log
    def _on_batch_progress_updated(self, current, total):
        """バッチ処理進行状況の更新"""
        self.event_handler_manager._on_batch_progress_updated(current, total)
    
    @debug_log
    def _on_batch_completed(self, results):
        """バッチ処理完了時の処理"""
        self.event_handler_manager._on_batch_completed(results)
    
    @debug_log
    def _on_batch_error(self, error_message):
        """バッチ処理エラー時の処理"""
        self.event_handler_manager._on_batch_error(error_message)

def main():
    # ディレクトリの初期化（遅延初期化）
    from config.common import initialize_directories
    initialize_directories()
    
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--logout', action='store_true', help='古いCookieを削除しRDEから完全ログアウトしてから開始')
        parser.add_argument('--auto-close', action='store_true', help='自動終了を有効にする（デフォルト: 手動終了）')
        parser.add_argument('--test', action='store_true', help='テストモードで自動ログイン・自動検索・自動終了')
        parser.add_argument('--keep-tokens', action='store_true', help='開発モード: トークン・認証情報を起動/終了時に削除しない')
        parser.add_argument('--force-dialog', action='store_true', help='v2.1.17: 単一プロジェクトグループの場合でもダイアログを表示')
        parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO', help='ログレベルを指定 (デフォルト: INFO)')
        parser.add_argument('--version', '-v', action='store_true', help='バージョン情報を表示して終了')
        parser.add_argument('--version-all', action='store_true', help='全バージョン記載箇所をまとめて表示して終了')
        args = parser.parse_args()
        
        # ログレベル設定
        if args.log_level:
            config_manager = get_config_manager()
            config_manager.set("logging.level", args.log_level)
            logger.info("ログレベルを %s に設定しました", args.log_level)
    
        # v2.1.17: 単一プロジェクトグループでもダイアログを表示するフラグ
        if args.force_dialog:
            os.environ['FORCE_PROJECT_GROUP_DIALOG'] = '1'
            logger.info("[v2.1.17] --force-dialog オプション有効 - 単一プロジェクトグループでもダイアログを表示")
            print("="*80)
            print("📋 --force-dialog オプション有効")
            print("   単一プロジェクトグループの場合でもダイアログを表示します")
            print("="*80)
    
        # 開発モード: トークン保持フラグを環境変数に設定
        if args.keep_tokens:
            os.environ['SKIP_TOKEN_CLEANUP'] = '1'
            logger.info("[DEVELOPMENT MODE] トークン保持モード有効 - 起動/終了時にトークンを削除しません")
            print("="*80)
            print("⚠️  開発モード: トークン・認証情報を保持します")
            print("   起動時・終了時の自動削除がスキップされます")
            print("   セキュリティリスクがあるため、開発用途のみに使用してください")
            print("="*80)

        if args.version:
            try:
                version_path = get_static_resource_path('../VERSION.txt')
                with open(version_path, encoding='utf-8') as f:
                    version = f.readline().strip()
                print(version)
            except Exception:
                logger.debug("バージョン情報の取得に失敗しました")
            sys.exit(0)

        if args.version_all:
            logger.debug("--- バージョン情報一覧 ---")
            # VERSION.txt
            try:
                version_path = get_static_resource_path('../VERSION.txt')
                with open(version_path, encoding='utf-8') as f:
                    logger.debug("VERSION.txt: %s", f.readline().strip())
            except Exception:
                logger.debug("VERSION.txt: 取得失敗")
            # config/common.py REVISION
            try:
                from config.common import REVISION
                logger.debug("config/common.py REVISION: %s", REVISION)
            except Exception:
                logger.debug("config/common.py REVISION: 取得失敗")
            # arim_rde_tool.py ヘッダー
            try:
                tool_path = get_static_resource_path('arim_rde_tool.py')
                with open(tool_path, encoding='utf-8') as f:
                    for i in range(10):
                        line = f.readline()
                        if 'ARIM RDE Tool v' in line:
                            logger.debug("arim_rde_tool.py header: %s", line.strip())
                            break
            except Exception:
                logger.debug("arim_rde_tool.py header: 取得失敗")
            # README.md
            try:
                readme_path = get_static_resource_path('../README.md')
                with open(readme_path, encoding='utf-8') as f:
                    for i in range(10):
                        line = f.readline()
                        if 'ARIM RDE Tool v' in line:
                            logger.debug("README.md: %s", line.strip())
                            break
            except Exception:
                logger.debug("README.md: 取得失敗")
            # doc_archives/ARCHITECTURE_FEATURE_MAP_v1.17.2.md
            try:
                arch_path = get_static_resource_path('../doc_archives/ARCHITECTURE_FEATURE_MAP_v1.17.2.md')
                with open(arch_path, encoding='utf-8') as f:
                    line = f.readline()
                    logger.debug("ARCHITECTURE_FEATURE_MAP_v1.17.2.md: %s", line.strip())
            except Exception:
                logger.debug("ARCHITECTURE_FEATURE_MAP_v1.17.2.md: 取得失敗")

            # src配下の__version__定義
            import re
            import glob
            version_matches = []
            src_dir = os.path.join(get_base_dir(), 'src')
            for pyfile in glob.glob(os.path.join(src_dir, '**', '*.py'), recursive=True):
                try:
                    with open(pyfile, encoding='utf-8') as f:
                        for line in f:
                            m = re.match(r'__version__\s*=\s*["\"](.*?)["\"]', line)
                            if m:
                                version_matches.append(f"{pyfile}: __version__ = {m.group(1)}")
                except Exception:
                    continue
            if version_matches:
                logger.debug("src配下の__version__定義:")
                for v in version_matches:
                    print('  ' + v)
            else:
                logger.debug("src配下の__version__定義: なし")
            sys.exit(0)
        
        show_splash_screen()
        app = QApplication(sys.argv)
        browser = Browser(auto_close=args.auto_close, test_mode=args.test)
        app.exec()
    except Exception as e:
        logger.error(f"メイン関数でエラーが発生しました: {e}")
        raise

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"アプリケーション起動時にエラーが発生しました: {e}")
        logger.error("起動エラー: %s", e)
        sys.exit(1)