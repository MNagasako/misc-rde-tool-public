#!/usr/bin/env python3
"""
LoginManager - ログイン・認証管理クラス

概要:
RDEシステムへのログイン処理と認証情報管理を専門に行うクラスです。
自動ログイン、Cookie管理、トークン処理を統合的に処理します。

主要機能:
- 自動ログイン処理の実行
- Cookie情報の保存・読み込み
- Bearer Token の管理
- 認証状態の監視・更新
- ログインフォームの自動入力
- セッション維持の管理

責務:
認証関連の処理を一元化し、セキュリティ要件を満たしつつ
メインクラスから認証ロジックを分離します。
"""

import logging
import json
from config.common import LOGIN_FILE
from functions.common_funcs import load_js_template
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox
from config.common import get_cookie_file_path, BEARER_TOKEN_FILE

logger = logging.getLogger("RDE_WebView")

# v1.16: 新しい認証情報ストア統合
try:
    from classes.core.credential_store import (
        perform_health_check, decide_autologin_source, get_credential_store,
        CredentialInfo
    )
    from classes.managers.app_config_manager import get_config_manager
    CREDENTIAL_STORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"認証情報ストアが利用できません: {e}")
    CREDENTIAL_STORE_AVAILABLE = False

logger = logging.getLogger("RDE_WebView")

class LoginManager:
    """
    ログイン・認証・クッキー取得管理クラス
    v1.16: 新しい認証情報ストア統合
    """
    def __init__(self, browser, webview, autologin_msg_label):
        self.browser = browser
        self.webview = webview
        self.autologin_msg_label = autologin_msg_label
        
        # v1.16: 新しい認証情報管理
        self.config_manager = get_config_manager() if CREDENTIAL_STORE_AVAILABLE else None
        self.credential_source = None
        self.credential_store = None
        
        # 既存の認証情報（後方互換）
        self.login_username = browser.login_username
        self.login_password = browser.login_password
        self.login_mode = browser.login_mode
        
        # v1.16: 起動時に認証情報を決定
        self._initialize_credential_source()
    
    def _initialize_credential_source(self):
        """認証情報ソースの初期化"""
        if not CREDENTIAL_STORE_AVAILABLE or not self.config_manager:
            logger.info("認証情報ストア無効: レガシーモードで動作")
            return
        
        try:
            # 自動ログインが有効かチェック
            autologin_enabled = self.config_manager.get("autologin.autologin_enabled", False)
            if not autologin_enabled:
                logger.info("自動ログインが無効: 手動ログインまたはレガシーファイル使用")
                return
            
            # ヘルスチェック実行
            health_check = perform_health_check()
            
            # 認証情報ソースを決定
            storage_pref = self.config_manager.get("autologin.credential_storage", "auto")
            self.credential_source = decide_autologin_source(storage_pref, health_check)
            
            logger.info(f"認証情報ソース決定: {self.credential_source}")
            
            # レガシーファイル使用時の警告
            if self.credential_source == "legacy_file":
                warn_on_legacy = self.config_manager.get("autologin.warn_on_legacy_file", True)
                if warn_on_legacy:
                    self._show_legacy_warning()
            
            # 認証情報ストアを取得
            if self.credential_source != "none":
                self.credential_store = get_credential_store(self.credential_source)
                if self.credential_store:
                    self._load_credentials_from_store()
                
        except Exception as e:
            logger.error(f"認証情報ソース初期化エラー: {e}")
    
    def _show_legacy_warning(self):
        """レガシーファイル使用時の警告を表示"""
        try:
            if hasattr(self.browser, 'show_legacy_warning_banner'):
                self.browser.show_legacy_warning_banner()
            else:
                # フォールバック: ダイアログ表示
                from PyQt5.QtWidgets import QMessageBox, QCheckBox
                msg_box = QMessageBox(self.browser)
                msg_box.setWindowTitle("認証情報の警告")
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setText(
                    "旧 input/login.txt を使用しています（平文保存のため非推奨）。\n"
                    "設定 > 自動ログイン から安全な保存先へ移行してください。"
                )
                
                # "今後は表示しない"チェックボックス
                checkbox = QCheckBox("今後は表示しない")
                msg_box.setCheckBox(checkbox)
                
                msg_box.exec_()
                
                # チェックボックスがONなら警告を無効化
                if checkbox.isChecked():
                    self.config_manager.set("autologin.warn_on_legacy_file", False)
                    self.config_manager.save_to_file()
                    
        except Exception as e:
            logger.error(f"レガシー警告表示エラー: {e}")
    
    def _load_credentials_from_store(self):
        """認証情報ストアから認証情報を読み込み"""
        try:
            if not self.credential_store:
                return
            
            credentials = self.credential_store.load_credentials()
            if credentials:
                # 認証情報を設定（メモリ上のみ）
                self.login_username = credentials.username
                self.login_password = credentials.password
                self.login_mode = credentials.login_mode
                
                logger.info(f"認証情報を{self.credential_source}から読み込み: {credentials.username}")
                
                # ブラウザ側の認証情報も更新（後方互換）
                self.browser.login_username = credentials.username
                self.browser.login_password = credentials.password
                self.browser.login_mode = credentials.login_mode
            else:
                logger.warning(f"認証情報が見つからない: {self.credential_source}")
                
        except Exception as e:
            logger.error(f"認証情報読み込みエラー: {e}")
    
    def _secure_cleanup_credentials(self):
        """メモリ上の認証情報の安全なクリーンアップ"""
        try:
            if hasattr(self, 'login_password') and self.login_password:
                # パスワードをゼロで上書き（Python文字列の制限内で）
                password_len = len(self.login_password)
                self.login_password = '\x00' * password_len
                self.login_password = None
                
            # ブラウザ側も同様にクリーンアップ
            if hasattr(self.browser, 'login_password') and self.browser.login_password:
                password_len = len(self.browser.login_password)
                self.browser.login_password = '\x00' * password_len
                self.browser.login_password = None
                
        except Exception as e:
            logger.error(f"認証情報クリーンアップエラー: {e}")

    def poll_dice_btn_status(self):
        # test_modeでは処理をスキップ
        if hasattr(self.browser, 'test_mode') and self.browser.test_mode:
            return
            
        from PyQt5.QtCore import QTimer
        js_code = load_js_template('poll_dice_btn_status.js')
        def after_check(is_ready):
            try:
                # 安全性チェック: browserが削除されていないか確認
                if not hasattr(self, 'browser') or self.browser is None:
                    return
                    
                # test_modeでは処理をスキップ
                if hasattr(self.browser, 'test_mode') and self.browser.test_mode:
                    return
                    
                if is_ready:
                    self.browser.autologin_status = 'dice_btn_ready'
                    self.browser.update_autologin_msg('DICEログインボタンが有効です（自動クリック）')
                    self.browser.stop_blinking_msg()
                    if self.login_mode =="dice":
                        self.click_dice_btn()
                else:
                    self.browser.update_autologin_msg('DICEログインボタンを待機中...')
                    self.browser.start_blinking_msg()
                    QTimer.singleShot(500, self.poll_dice_btn_status)
            except RuntimeError:
                # オブジェクトが削除されている場合は処理をスキップ
                pass
        self.webview.page().runJavaScript(js_code, after_check)

    def click_dice_btn(self):
        js_code = load_js_template('click_dice_btn.js')
        def after_click(result):
            if result:
                logger.info('[INFO] DICEアカウントボタンを自動クリックしました')
                self.poll_identifier_input()
            else:
                logger.warning('[WARN] DICEアカウントボタンの自動クリックに失敗')
        self.webview.page().runJavaScript(js_code, after_click)

    def poll_identifier_input(self):
        from PyQt5.QtCore import QTimer
        js_code = load_js_template('poll_identifier_input.js')
        def after_check(is_ready):
            if is_ready:
                self.browser.update_autologin_msg('identifier欄が出現しました（自動入力）')
                username = self.login_username or ''
                if username:
                    self.set_identifier_input_and_submit(username)
                else:
                    logger.info(f'[INFO] {LOGIN_FILE}にユーザー名が無いためidentifier欄は空欄のまま。')
                    self.browser.update_autologin_msg('identifier欄が出現（ユーザー名未設定）')
            else:
                QTimer.singleShot(300, self.poll_identifier_input)
        self.webview.page().runJavaScript(js_code, after_check)

    def set_identifier_input_and_submit(self, value):
        js_code = load_js_template('set_identifier_input_and_submit.js').replace('{value}', value)
        def after_set(result):
            if result == 'set_and_submitted':
                logger.info(f"[INFO] identifier欄に値をセットしsubmitボタンを自動クリックしました: {value}")
                self.browser.update_autologin_msg('identifier入力・submit自動実行')
                self.poll_password_input()
            elif result == 'set_only':
                logger.info(f"[INFO] identifier欄に値をセットしました（submitボタンは見つからず）: {value}")
                self.browser.update_autologin_msg('identifier入力のみ自動実行')
            else:
                logger.warning("[WARN] identifier欄が見つかりませんでした")
        self.webview.page().runJavaScript(js_code, after_set)

    def poll_password_input(self):
        from PyQt5.QtCore import QTimer
        js_code = load_js_template('poll_password_input.js')
        def after_check(is_ready):
            if is_ready:
                self.browser.update_autologin_msg('パスワード欄が出現しました（自動入力）')
                password = self.login_password or ''
                if password:
                    self.set_password_input_and_submit(password)
                else:
                    logger.info('[INFO] login.txtにパスワードが無いためパスワード欄は空欄のまま。')
                    self.browser.update_autologin_msg('パスワード欄が出現（パスワード未設定）')
            else:
                QTimer.singleShot(300, self.poll_password_input)
        self.webview.page().runJavaScript(js_code, after_check)

    def set_password_input_and_submit(self, value):
        safe_value = value.replace("'", "\\'")
        js_code = load_js_template('set_password_input_and_submit.js').replace('{value}', safe_value)
        def after_set(result):
            if result == 'set_and_submitted':
                self.browser.update_autologin_msg('パスワード入力・フォーム自動submit')
            elif result == 'set_and_clicked':
                self.browser.update_autologin_msg('パスワード入力・Nextボタン自動クリック')
            elif result == 'set_only':
                self.browser.update_autologin_msg('パスワード入力のみ自動実行')
            else:
                self.browser.update_autologin_msg('パスワード欄が見つかりませんでした')
        self.webview.page().runJavaScript(js_code, after_set)

    def save_cookies_button(self):
        self.webview.page().profile().cookieStore().loadAllCookies()
        def save_cookies_and_close():
            if self.browser.cookies:
                with open(get_cookie_file_path(), 'w', encoding='utf-8') as f:
                    for domain, name, value in self.browser.cookies:
                        f.write(f"{name}={value}; ")
                logger.info('Cookieを保存しました。ウィンドウを自動で閉じます。')
            else:
                logger.info('Cookieが取得できませんでした。')
            self.browser.close()
        QTimer.singleShot(3000, save_cookies_and_close)

    def save_cookies_and_show_grant_form(self):
        """
        クッキーを保存し、その後grantNumberフォームを表示する。
        """
        self.webview.page().profile().cookieStore().loadAllCookies()
        def save_cookies():
            if self.browser.cookies:
                with open(get_cookie_file_path(), 'w', encoding='utf-8') as f:
                    for domain, name, value in self.browser.cookies:
                        f.write(f"{name}={value}; ")
                logger.info('Cookieを保存しました。grantNumberフォームを表示します。')
                # WebViewを不可視化（内容・状態は維持）
                self.webview.setEnabled(False)
                self.webview.setStyleSheet("background: transparent;")
                self.browser.show_grant_number_form()
            else:
                logger.info('Cookieが取得できませんでした。')
        QTimer.singleShot(1000, save_cookies)

    def save_bearer_token_to_file(self, token):
        try:
            with open(BEARER_TOKEN_FILE, 'w', encoding='utf-8') as f:
                f.write(f"BearerToken={token}\n")
            logger.info("BearerTokenを専用ファイルに保存しました。")
        except Exception as e:
            logger.error(f"BearerTokenの保存に失敗しました: {e}")

    def try_get_bearer_token(self, retries=3):
        """
        WebViewからBearerトークンを取得する
        Args:
            retries: リトライ回数
        """
        js_code = load_js_template('extract_bearer_token.js')
        
        def handle_token_list(token_list):
            if not token_list and retries > 0:
                logger.warning("トークン取得失敗。リトライします...")
                self.try_get_bearer_token(retries=retries - 1)
                return
            
            for item in token_list:
                if (
                    isinstance(item, dict)
                    and 'accesstoken' in item['key'].lower()
                    and item['value']
                ):
                    try:
                        data = json.loads(item['value'])
                        if data.get('credentialType') == 'AccessToken' and 'secret' in data:
                            self.browser.bearer_token = data['secret']
                            logger.info("Bearerトークン自動取得: " + data['secret'][:40] + "... (省略)")
                            # ファイルにも保存
                            self.save_bearer_token_to_file(data['secret'])
                            
                            # v1.16: 認証完了後のクリーンアップ
                            self._secure_cleanup_credentials()
                            return
                    except Exception as e:
                        logger.warning(f"JSONパース失敗: {e}")
            
            logger.warning("BearerトークンがsessionStorageから取得できませんでした")
        
        self.webview.page().runJavaScript(js_code, handle_token_list)
    
    def on_cookie_added(self, cookie):
        """
        Cookieが追加された時のイベントハンドラ
        Args:
            cookie: 追加されたCookieオブジェクト
        """
        # Cookieをブラウザのリストに追加
        domain = cookie.domain()
        name = cookie.name().data().decode()
        value = cookie.value().data().decode()
        
        # 既存のCookieリストに追加
        self.browser.cookies.append((domain, name, value))
        
        logger.debug(f"Cookie追加: domain={domain}, name={name}, value={value[:20]}...")
    
    def check_login_status(self, url_str):
        """
        URL変更時にログイン状態をチェック
        Args:
            url_str: 変更後のURL文字列
        """
        # ログイン状態に応じた処理をここに実装
        if '/rde/datasets' in url_str:
            logger.info("RDEデータセットページに到達しました")
            self.browser.update_autologin_msg("RDEログイン完了")
            
    def check_page_load_status(self):
        """
        ページロード完了時にログイン状態をチェック
        """
        # ページロード完了後の処理をここに実装
        logger.debug("ページロード完了 - ログイン状態チェック")
    
    def test_credentials(self, credentials: 'CredentialInfo') -> bool:
        """
        認証情報のテストログイン（v1.16追加）
        
        Args:
            credentials: テスト対象の認証情報
            
        Returns:
            bool: テスト成功時True
        """
        try:
            # TODO: 実際のテストログイン実装
            # 現在は基本検証のみ
            if not credentials.username or not credentials.password:
                return False
            
            # 将来的にはここで実際のRDEログインテストを実行
            logger.info(f"認証情報テスト: {credentials.username} (パスワード長: {len(credentials.password)})")
            
            return True
            
        except Exception as e:
            logger.error(f"認証情報テストエラー: {e}")
            return False
