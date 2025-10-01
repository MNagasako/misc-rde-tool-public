#!/usr/bin/env python3

"""
ARIM RDE Tool v1.17.11 - PyQt5によるRDE→ARIMデータポータル移行ツール

主要機能:
- RDEシステムへの自動ログイン・データセット一括取得・画像保存
- PyQt5 WebView統合ブラウザによる認証・操作自動化
- ARIM匿名化・HTMLログ出力・統合API処理・AI分析機能

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
# PyQt5 - WebEngine初期化問題の回避
from PyQt5.QtCore import QCoreApplication, Qt
# WebEngine使用前に属性を設定
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
# 設定・関数モジュール
from config.common import REVISION, OUTPUT_DIR, DYNAMIC_IMAGE_DIR, get_static_resource_path
from functions.common_funcs import read_login_info
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
        # 基本属性の初期化
        self._init_basic_attributes(auto_close, test_mode)
        # UI要素の初期化
        self._init_ui_elements()

        # 各種マネージャーの初期化
        self.app_initializer = AppInitializer(self)
        self.app_initializer.initialize_all()

        # ログイン情報とLoginManagerの初期化
        self.login_username, self.login_password ,self.login_mode= read_login_info()
        print(f"[INFO] ログイン情報: {self.login_username}, {self.login_password}, {self.login_mode}")

        self.login_manager = LoginManager(self, self.webview, self.autologin_msg_label)

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

        # ウィンドウの表示と最終設定
        self._finalize_window_setup()

        # プロキシ起動時通知（UIが完全に表示された後）
        QTimer.singleShot(500, self._show_proxy_startup_notification)

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
        self.autologin_msg_label = QLabel('（自動ログインメッセージ欄）')
        self.autologin_msg_label.setStyleSheet('color: #007acc; font-size: 12px; padding: 2px;')
        self.autologin_msg_label.setText('自動ログインは現在無効です')
        self.webview_msg_label = QLabel('')
        self.webview_msg_label.setStyleSheet('color: #d2691e; font-size: 13px; padding: 2px;')
        
        # v1.16: レガシー警告バナー用ウィジェット
        self.legacy_warning_banner = None

    def _setup_webview_and_layout(self):
        """WebViewとレイアウトの設定"""
        interceptor = ImageInterceptor()
        self.webview.page().profile().setUrlRequestInterceptor(interceptor)
        self.browser_controller.setup_webview(self.webview)
        self.webview.page().profile().cookieStore().cookieAdded.connect(self.login_manager.on_cookie_added)
        self.ui_controller.setup_main_layout()

    def _finalize_window_setup(self):
        """ウィンドウの表示と最終設定"""
        self.ui_controller.finalize_window_setup()

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
        print('[TEST] 初期化テスト完了 - 早期終了')
        QApplication.quit()
    
    def show_legacy_warning_banner(self):
        """レガシーファイル使用時の警告バナーを表示（v1.16追加）"""
        try:
            if self.legacy_warning_banner:
                # 既に表示済みの場合はスキップ
                return
            
            from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel
            from PyQt5.QtCore import Qt
            
            # 警告バナーウィジェット作成
            self.legacy_warning_banner = QFrame()
            self.legacy_warning_banner.setStyleSheet(
                "background-color: #fff3cd; border: 1px solid #ffeaa7; "
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
            warning_message.setStyleSheet("color: #856404; font-weight: bold;")
            warning_message.setWordWrap(True)
            banner_layout.addWidget(warning_message, 1)
            
            # 設定ボタン
            settings_button = QPushButton("設定を開く")
            settings_button.setStyleSheet(
                "background-color: #ffc107; color: #212529; border: none; "
                "padding: 5px 10px; border-radius: 3px;"
            )
            settings_button.clicked.connect(self._open_autologin_settings)
            banner_layout.addWidget(settings_button)
            
            # 閉じるボタン
            close_button = QPushButton("×")
            close_button.setFixedSize(25, 25)
            close_button.setStyleSheet(
                "background-color: transparent; border: none; "
                "color: #856404; font-weight: bold; font-size: 16px;"
            )
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
            from PyQt5.QtWidgets import QMessageBox
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
        self.display_manager.set_autologin_message(msg)
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
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--logout', action='store_true', help='古いCookieを削除しRDEから完全ログアウトしてから開始')
        parser.add_argument('--auto-close', action='store_true', help='自動終了を有効にする（デフォルト: 手動終了）')
        parser.add_argument('--test', action='store_true', help='テストモードで自動ログイン・自動検索・自動終了')
        parser.add_argument('--version', '-v', action='store_true', help='バージョン情報を表示して終了')
        parser.add_argument('--version-all', action='store_true', help='全バージョン記載箇所をまとめて表示して終了')
        args = parser.parse_args()

        if args.version:
            try:
                with open(os.path.join(os.path.dirname(__file__), '../VERSION.txt'), encoding='utf-8') as f:
                    version = f.readline().strip()
                print(version)
            except Exception:
                print('バージョン情報の取得に失敗しました')
            sys.exit(0)

        if args.version_all:
            print('--- バージョン情報一覧 ---')
            # VERSION.txt
            try:
                with open(os.path.join(os.path.dirname(__file__), '../VERSION.txt'), encoding='utf-8') as f:
                    print(f"VERSION.txt: {f.readline().strip()}")
            except Exception:
                print('VERSION.txt: 取得失敗')
            # config/common.py REVISION
            try:
                from config.common import REVISION
                print(f"config/common.py REVISION: {REVISION}")
            except Exception:
                print('config/common.py REVISION: 取得失敗')
            # arim_rde_tool.py ヘッダー
            try:
                with open(__file__, encoding='utf-8') as f:
                    for i in range(10):
                        line = f.readline()
                        if 'ARIM RDE Tool v' in line:
                            print(f"arim_rde_tool.py header: {line.strip()}")
                            break
            except Exception:
                print('arim_rde_tool.py header: 取得失敗')
            # README.md
            try:
                readme_path = os.path.join(os.path.dirname(__file__), '../README.md')
                with open(readme_path, encoding='utf-8') as f:
                    for i in range(10):
                        line = f.readline()
                        if 'ARIM RDE Tool v' in line:
                            print(f"README.md: {line.strip()}")
                            break
            except Exception:
                print('README.md: 取得失敗')
            # docs/ARCHITECTURE_FEATURE_MAP_v1.17.2.md
            try:
                arch_path = os.path.join(os.path.dirname(__file__), '../docs/ARCHITECTURE_FEATURE_MAP_v1.17.2.md')
                with open(arch_path, encoding='utf-8') as f:
                    line = f.readline()
                    print(f"ARCHITECTURE_FEATURE_MAP_v1.17.2.md: {line.strip()}")
            except Exception:
                print('ARCHITECTURE_FEATURE_MAP_v1.17.2.md: 取得失敗')

            # src配下の__version__定義
            import re
            import glob
            version_matches = []
            src_dir = os.path.join(os.path.dirname(__file__), '.')
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
                print('src配下の__version__定義:')
                for v in version_matches:
                    print('  ' + v)
            else:
                print('src配下の__version__定義: なし')
            sys.exit(0)
        
        show_splash_screen()
        app = QApplication(sys.argv)
        browser = Browser(auto_close=args.auto_close, test_mode=args.test)
        app.exec_()
    except Exception as e:
        logger.error(f"メイン関数でエラーが発生しました: {e}")
        raise

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"アプリケーション起動時にエラーが発生しました: {e}")
        print(f"起動エラー: {e}")
        sys.exit(1)