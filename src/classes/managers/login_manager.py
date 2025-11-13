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
from qt_compat.core import QTimer, QUrl
from qt_compat.widgets import QApplication, QMessageBox
from config.common import get_cookie_file_path
# v2.0.3: BEARER_TOKEN_FILE削除、bearer_tokens.jsonのみ使用
from classes.core.browser_controller import mask_sensitive_url

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
        
        # 既存の認証情報(後方互換) - v1.20.3: 属性がない場合に対応
        self.login_username = getattr(browser, 'login_username', None)
        self.login_password = getattr(browser, 'login_password', None)
        self.login_mode = getattr(browser, 'login_mode', None)
        
        # v1.18.3: マルチホストトークン取得フラグ
        self._material_token_fetched = False
        
        # v2.0.2: トークン取得完了状態管理
        self._rde_token_acquired = False
        self._material_token_acquired = False
        self._login_in_progress = False
        self._autologin_cancelled = False  # 自動ログインキャンセルフラグ
        
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
                from qt_compat.widgets import QMessageBox, QCheckBox
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
                
                msg_box.exec()
                
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
    
    def cancel_autologin(self):
        """自動ログイン処理をキャンセル"""
        try:
            self._autologin_cancelled = True
            self._login_in_progress = False
            
            if hasattr(self.browser, 'autologin_msg_label') and self.browser.autologin_msg_label:
                self.browser.autologin_msg_label.setText("⚠️ 自動ログインをキャンセルしました")
                self.browser.autologin_msg_label.setVisible(True)
            
            logger.info("自動ログイン処理をキャンセルしました")
            
        except Exception as e:
            logger.error(f"自動ログインキャンセルエラー: {e}")
    
    def reset_autologin_cancel_flag(self):
        """自動ログインキャンセルフラグをリセット"""
        self._autologin_cancelled = False
        logger.debug("自動ログインキャンセルフラグをリセットしました")

    def poll_dice_btn_status(self):
        # test_modeでは処理をスキップ
        if hasattr(self.browser, 'test_mode') and self.browser.test_mode:
            return
        
        # 自動ログインがキャンセルされた場合はスキップ
        if self._autologin_cancelled:
            logger.info("自動ログインがキャンセルされました")
            return
            
        from qt_compat.core import QTimer
        js_code = load_js_template('poll_dice_btn_status.js')
        def after_check(is_ready):
            try:
                # 安全性チェック: browserが削除されていないか確認
                if not hasattr(self, 'browser') or self.browser is None:
                    return
                
                # 自動ログインがキャンセルされた場合はスキップ
                if self._autologin_cancelled:
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
                logger.info(f'[LOGIN] 現在のURL: {mask_sensitive_url(self.webview.url().toString())}')
                self.poll_identifier_input()
            else:
                logger.warning('[WARN] DICEアカウントボタンの自動クリックに失敗')
                logger.warning(f'[LOGIN] エラー時のURL: {mask_sensitive_url(self.webview.url().toString())}')
        self.webview.page().runJavaScript(js_code, after_click)

    def poll_identifier_input(self):
        from qt_compat.core import QTimer
        js_code = load_js_template('poll_identifier_input.js')
        def after_check(is_ready):
            if is_ready:
                self.browser.update_autologin_msg('identifier欄が出現しました（自動入力）')
                username = self.login_username or ''
                logger.info(f'[LOGIN-DEBUG] username取得: "{username}" (length={len(username)})')
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
                logger.info(f'[LOGIN] identifier送信後のURL: {mask_sensitive_url(self.webview.url().toString())}')
                self.browser.update_autologin_msg('identifier入力・submit自動実行')
                self.poll_password_input()
            elif result == 'set_only':
                logger.info(f"[INFO] identifier欄に値をセットしました（submitボタンは見つからず）: {value}")
                logger.info(f'[LOGIN] identifier入力後のURL: {mask_sensitive_url(self.webview.url().toString())}')
                self.browser.update_autologin_msg('identifier入力のみ自動実行')
            else:
                logger.warning("[WARN] identifier欄が見つかりませんでした")
                logger.warning(f'[LOGIN] エラー時のURL: {mask_sensitive_url(self.webview.url().toString())}')
        self.webview.page().runJavaScript(js_code, after_set)

    def poll_password_input(self):
        from qt_compat.core import QTimer
        js_code = load_js_template('poll_password_input.js')
        def after_check(is_ready):
            if is_ready:
                self.browser.update_autologin_msg('パスワード欄が出現しました（自動入力）')
                password = self.login_password or ''
                logger.info(f'[LOGIN-DEBUG] password取得: {"*" * len(password)} (length={len(password)})')
                if password:
                    self.set_password_input_and_submit(password)
                else:
                    logger.info('[INFO] login.txtにパスワードが無いためパスワード欄は空欄のまま。')
                    self.browser.update_autologin_msg('パスワード欄が出現（パスワード未設定）')
            else:
                QTimer.singleShot(300, self.poll_password_input)
        self.webview.page().runJavaScript(js_code, after_check)

    def set_password_input_and_submit(self, value):
        # v1.20.3: PySide6対応 - フォーム送信は正常に動作するため、デバッグコード削除
        safe_value = value.replace("'", "\\'")
        js_code = load_js_template('set_password_input_and_submit.js').replace('{value}', safe_value)
        
        def after_set(result):
            if result == 'set_and_submitted':
                self.browser.update_autologin_msg('パスワード入力・フォーム自動submit')
                logger.info(f'[LOGIN] パスワード送信完了、URL: {mask_sensitive_url(self.webview.url().toString())}')
            elif result == 'set_and_clicked':
                self.browser.update_autologin_msg('パスワード入力・Nextボタン自動クリック')
                logger.info(f'[LOGIN] パスワード送信完了（Nextボタン）、URL: {mask_sensitive_url(self.webview.url().toString())}')
            elif result == 'set_only':
                self.browser.update_autologin_msg('パスワード入力のみ自動実行')
                logger.info(f'[LOGIN] パスワード入力のみ、URL: {mask_sensitive_url(self.webview.url().toString())}')
            else:
                self.browser.update_autologin_msg('パスワード欄が見つかりませんでした')
                logger.warning(f'[LOGIN] パスワード欄エラー、URL: {mask_sensitive_url(self.webview.url().toString())}')
        
        self.webview.page().runJavaScript(js_code, after_set)
    
    def check_login_redirect(self, retries=5):
        """
        ログイン後のリダイレクトを確認
        v1.20.3: PySide6ではフォーム送信後のリダイレクトが遅延する可能性がある
        """
        current_url = self.webview.url().toString()
        logger.info(f'[LOGIN] リダイレクト確認 (残り{retries}回): {mask_sensitive_url(current_url)}')
        
        # /rde/datasets に到達したか確認
        if '/rde/datasets' in current_url:
            logger.info('[LOGIN] ✅ ログイン成功 - /rde/datasetsに到達')
            return
        
        # rde.nims.go.jpのトップページに到達（リダイレクト中）
        if 'rde.nims.go.jp' in current_url and 'datasets' not in current_url:
            logger.info('[LOGIN] rde.nims.go.jpに到達 - さらに遷移を待機')
            if retries > 0:
                QTimer.singleShot(2000, lambda: self.check_login_redirect(retries - 1))
            return
        
        # まだdiceidm.nims.go.jp（認証処理中）
        if 'diceidm.nims.go.jp' in current_url:
            logger.info('[LOGIN] まだ認証ページ - リダイレクト待機中')
            if retries > 0:
                QTimer.singleShot(2000, lambda: self.check_login_redirect(retries - 1))
            else:
                logger.warning('[LOGIN] ⚠️ リダイレクトタイムアウト - ログイン失敗の可能性')
            return
        
        # その他のURL
        logger.info(f'[LOGIN] 予期しないURL: {mask_sensitive_url(current_url)}')
        if retries > 0:
            QTimer.singleShot(2000, lambda: self.check_login_redirect(retries - 1))

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

    def save_bearer_token_to_file(self, token, host='rde.nims.go.jp'):
        """
        Bearer Tokenをファイルに保存（複数ホスト対応）
        
        Args:
            token: 保存するBearerトークン
            host: ホスト名（デフォルト: 'rde.nims.go.jp'）
        """
        try:
            from config.common import save_bearer_token
            logger.info(f"[TOKEN] Bearerトークンをファイルに保存開始 ({host}): {token[:20]}...")
            if save_bearer_token(token, host):
                logger.info(f"[TOKEN] BearerToken保存成功 ({host})")
            else:
                logger.error(f"[TOKEN] BearerToken保存失敗 ({host})")
        except Exception as e:
            logger.error(f"[TOKEN] BearerToken保存エラー ({host}): {e}")

    def try_get_bearer_token(self, retries=3, host='rde.nims.go.jp', initial_delay=0):
        """
        WebViewからBearerトークンを取得する（複数ホスト対応）
        
        Args:
            retries: リトライ回数
            host: 対象ホスト名（デフォルト: 'rde.nims.go.jp'）
            initial_delay: 初回取得前の遅延時間（ミリ秒、デフォルト: 0）
        """
        # PySide6対応：初回取得時はsessionStorageが設定されるまで待機
        if initial_delay > 0:
            logger.info(f"[TOKEN] {initial_delay}ms待機してからBearerトークン取得開始")
            QTimer.singleShot(initial_delay, lambda: self.try_get_bearer_token(retries, host, 0))
            return
        
        logger.info(f"[TOKEN] Bearerトークン取得開始: host={host}, retries={retries}")
        logger.debug("トークン取得開始: host=%s", host)
        
        # v1.20.3: PySide6対応 - sessionStorageとlocalStorageの両方から取得
        js_code = load_js_template('extract_bearer_token_localStorage.js')
        
        def handle_token_list(token_list):
            logger.debug("JavaScript実行完了: result=%s", type(token_list))
            
            # PySide6: runJavaScriptの結果が文字列の場合、JSONパースが必要
            if isinstance(token_list, str):
                logger.debug("文字列結果を検出、長さ=%s", len(token_list))
                if not token_list or token_list == '':
                    logger.debug("空の文字列 - sessionStorageが空")
                    token_list = None
                else:
                    try:
                        logger.debug("JSON文字列をパース試行: %s...", token_list[:200])
                        token_list = json.loads(token_list)
                        logger.debug("JSONパース成功: %s, 要素数=%s", type(token_list), len(token_list) if token_list else 0)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.debug("JSONパース失敗: %s", e)
                        token_list = None
            
            logger.debug(f"[TOKEN] sessionStorage取得結果: {len(token_list) if token_list else 0}件")
            
            if not token_list:
                logger.warning(f"[TOKEN] sessionStorageが空です ({host})")
                logger.debug("sessionStorageが空 - リトライ=%s", retries)
                if retries > 0:
                    logger.warning(f"[TOKEN] トークン取得失敗 ({host})。リトライします... (残り{retries-1}回)")
                    QTimer.singleShot(2000, lambda: self.try_get_bearer_token(retries=retries - 1, host=host))
                return
            
            logger.debug("sessionStorage内容:")
            for i, item in enumerate(token_list):
                if isinstance(item, dict):
                    logger.debug("  [%s] key=%s, value_len=%s", i, item.get('key', 'N/A'), len(item.get('value', '')))
            
            # AccessToken抽出
            access_token = None
            refresh_token = None
            
            for item in token_list:
                if (
                    isinstance(item, dict)
                    and 'accesstoken' in item['key'].lower()
                    and item['value']
                ):
                    try:
                        data = json.loads(item['value'])
                        if data.get('credentialType') == 'AccessToken' and 'secret' in data:
                            access_token = data['secret']
                            
                            # トークンの内容をデコードして検証（デバッグ用）
                            logger.debug("AccessToken取得: %s...", access_token[:50])
                            try:
                                import base64
                                # JWT形式: header.payload.signature
                                parts = access_token.split('.')
                                if len(parts) == 3:
                                    # ペイロード部分をデコード（Base64URL → 通常のBase64）
                                    payload_b64 = parts[1]
                                    # パディング調整
                                    payload_b64 += '=' * (4 - len(payload_b64) % 4)
                                    payload_json = base64.b64decode(payload_b64).decode('utf-8')
                                    payload_data = json.loads(payload_json)
                                    logger.debug("AccessTokenペイロード: aud=%s, scp=%s", payload_data.get('aud'), payload_data.get('scp'))
                                    
                                    # スコープを確認してトークンの種類を判定
                                    scopes = payload_data.get('scp', '')
                                    if 'materials' in scopes:
                                        logger.debug("[OK] Material API用トークンを検出")
                                    else:
                                        logger.debug("[OK] RDE API用トークンを検出")
                            except Exception as decode_err:
                                logger.debug("トークンデコードエラー: %s", decode_err)
                            
                            break  # AccessToken取得成功
                    except Exception as e:
                        logger.warning(f"[TOKEN] AccessToken JSONパース失敗: {e}")
                        logger.debug("AccessToken JSONパースエラー: %s", e)
            
            # RefreshToken抽出（v2.1.0: TokenManager対応）
            for item in token_list:
                if (
                    isinstance(item, dict)
                    and 'refreshtoken' in item['key'].lower()
                    and item['value']
                ):
                    try:
                        data = json.loads(item['value'])
                        if data.get('credentialType') == 'RefreshToken' and 'secret' in data:
                            refresh_token = data['secret']
                            logger.debug("RefreshToken取得: %s...", refresh_token[:50])
                            break  # RefreshToken取得成功
                    except Exception as e:
                        logger.warning(f"[TOKEN] RefreshToken JSONパース失敗: {e}")
                        logger.debug("RefreshToken JSONパースエラー: %s", e)
            
            # トークン保存処理
            if access_token:
                # 既存のAccessToken保存処理
                self.browser.bearer_token = access_token
                logger.info(f"[TOKEN] Bearerトークン自動取得成功 ({host}): {access_token[:40]}... (省略)")
                logger.debug("トークンを %s として保存", host)
                
                # ファイルにも保存（ホスト別）
                self.save_bearer_token_to_file(access_token, host)
                
                # v2.1.0: TokenManager統合 - RefreshToken保存
                if refresh_token:
                    try:
                        from classes.managers.token_manager import TokenManager
                        
                        # JWT expiryから有効期限を取得（デフォルト3600秒）
                        expires_in = 3600
                        try:
                            import base64
                            parts = access_token.split('.')
                            if len(parts) == 3:
                                payload_b64 = parts[1]
                                payload_b64 += '=' * (4 - len(payload_b64) % 4)
                                payload_json = base64.b64decode(payload_b64).decode('utf-8')
                                payload_data = json.loads(payload_json)
                                
                                # exp (expiration time) からexpires_inを計算
                                if 'exp' in payload_data:
                                    import time
                                    current_time = int(time.time())
                                    expires_in = payload_data['exp'] - current_time
                                    logger.debug("JWT expiry: %s秒", expires_in)
                        except Exception as exp_err:
                            logger.debug("JWT expiry解析エラー: %s", exp_err)
                        
                        # TokenManagerに保存
                        token_manager = TokenManager.get_instance()
                        success = token_manager.save_tokens(
                            host=host,
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expires_in=expires_in
                        )
                        
                        if success:
                            logger.info(f"[TOKEN] RefreshToken保存成功 ({host})")
                            logger.debug("TokenManagerにRefreshToken保存完了")
                        else:
                            logger.warning(f"[TOKEN] RefreshToken保存失敗 ({host})")
                    except Exception as tm_err:
                        logger.error(f"[TOKEN] TokenManager保存エラー: {tm_err}", exc_info=True)
                
                # v1.18.3: UIコンポーネントにトークン更新を通知
                self._notify_token_updated(access_token, host)
                
                # v2.0.2: トークン取得完了フラグを更新
                if host == 'rde.nims.go.jp':
                    self._rde_token_acquired = True
                    logger.info("[TOKEN] RDEトークン取得完了フラグを設定")
                elif host == 'rde-material.nims.go.jp':
                    self._material_token_acquired = True
                    logger.info("[TOKEN] マテリアルトークン取得完了フラグを設定")
                
                # v2.0.2: 両トークン取得完了チェック
                if self._rde_token_acquired and self._material_token_acquired:
                    logger.info("[TOKEN] ✅ 両トークン取得完了")
                    self._login_in_progress = False
                    # メッセージ更新: 全トークン取得完了
                    self.browser.update_autologin_msg("✅ ログイン完了")
                    self._notify_login_complete()
                
                # v1.16: 認証完了後のクリーンアップ
                self._secure_cleanup_credentials()
                
                # rde.nims.go.jpの場合は、続けてrde-material.nims.go.jpのトークンも取得
                # v1.18.3: 無限ループ防止 - まだ取得していない場合のみ実行
                if host == 'rde.nims.go.jp' and not self._material_token_fetched:
                    logger.info("[TOKEN] rde-material.nims.go.jpのトークン取得を開始します")
                    logger.debug("Material トークン取得プロセスを2秒後に開始")
                    # メッセージ更新: Materialトークン取得開始
                    self.browser.update_autologin_msg("🔄 Materialトークン取得中...")
                    QTimer.singleShot(2000, lambda: self.fetch_material_token())

                
                return
            else:
                logger.warning(f"[TOKEN] BearerトークンがsessionStorageから取得できませんでした ({host})")
                logger.debug("AccessToken形式のデータが見つかりませんでした")
        
        logger.debug("JavaScript実行開始")
        self.webview.page().runJavaScript(js_code, handle_token_list)
    
    def on_cookie_added(self, cookie):
        """
        Cookieが追加された時のイベントハンドラ
        Args:
            cookie: 追加されたCookieオブジェクト
        """
        try:
            # Cookieをブラウザのリストに追加
            domain = cookie.domain()
            name = cookie.name().data().decode()
            value = cookie.value().data().decode()
            
            # 既存のCookieリストに追加
            self.browser.cookies.append((domain, name, value))
            
            logger.debug("[COOKIE-DEBUG] Cookie追加: domain=%s, name=%s, value_len=%s", domain, name, len(value))
            logger.debug(f"Cookie追加: domain={domain}, name={name}, value={value[:20]}...")
        except Exception as e:
            logger.error("[COOKIE-DEBUG] Cookie追加エラー: %s", e)
            logger.error(f"Cookie追加エラー: {e}")
    
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
    
    def fetch_material_token(self, retry_count=0, max_retries=3):
        """
        rde-material.nims.go.jpからBearerトークンを取得
        認証情報は共通のため、既にログイン済みの状態でアクセスして
        Cookieからトークンを抽出する
        
        トークン取得後、rde.nims.go.jp/rde/datasetsに戻る(データ取得機能用)
        
        Args:
            retry_count: 現在のリトライ回数（内部使用）
            max_retries: 最大リトライ回数（デフォルト: 3）
        """
        # v2.0.7: リトライロジック追加 - 最大試行回数チェック
        if retry_count >= max_retries:
            logger.error(f"[TOKEN] マテリアルトークン取得が{max_retries}回失敗しました")
            self.browser.update_autologin_msg(f"❌ マテリアルトークン取得失敗（{max_retries}回試行）")
            # フラグをリセットして次回再試行可能にする
            self._material_token_fetched = False
            return
        
        # v1.18.3: 二重実行防止 - 既に取得プロセス実行中の場合はスキップ（初回のみ）
        if retry_count == 0 and self._material_token_fetched:
            logger.info("[TOKEN] rde-material.nims.go.jpトークン取得は既に実行済みです（スキップ）")
            return
        
        # フラグを先に設定して二重実行を防止（初回のみ）
        if retry_count == 0:
            logger.info("[TOKEN] rde-material.nims.go.jpトークン取得フラグを設定")
            self._material_token_fetched = True
        
        # メッセージ更新: Material取得開始
        retry_msg = f" (試行 {retry_count + 1}/{max_retries})" if retry_count > 0 else ""
        self.browser.update_autologin_msg(f"🔄 Material認証中...{retry_msg}")
            
        try:
            # 重要: rde-material.nims.go.jpのログインページに遷移してトークンを取得
            # 正しいURL: /samples/samples（/rde/samplesは存在しない）
            material_url = "https://rde-material.nims.go.jp/samples/samples"
            logger.info(f"[TOKEN] rde-material.nims.go.jpへ遷移開始: {mask_sensitive_url(material_url)} (retry={retry_count})")
            logger.debug("Material URL遷移: %s", mask_sensitive_url(material_url))
            
            # 認証完了を待つための状態管理
            self._material_auth_redirect_count = 0
            self._material_token_fetch_timer = None
            self._material_auth_completed = False
            
            # v2.0.7: タイムアウト監視タイマー（10秒）- ハング防止機能
            def on_timeout():
                if not self._material_auth_completed:
                    logger.warning(f"[TOKEN] マテリアルトークン取得がタイムアウト（10秒経過） - リトライします (retry={retry_count})")
                    self.browser.update_autologin_msg("⚠️ タイムアウト - 再試行中...")
                    
                    # シグナルを切断
                    try:
                        self.webview.loadFinished.disconnect(on_load_finished)
                    except:
                        pass
                    try:
                        self.webview.urlChanged.disconnect(on_url_changed)
                    except:
                        pass
                    
                    # リトライ
                    if retry_count < max_retries - 1:
                        logger.info(f"[TOKEN] タイムアウトによるリトライ - {2000}ms後に再試行")
                        QTimer.singleShot(2000, lambda: self.fetch_material_token(retry_count + 1, max_retries))
                    else:
                        logger.error("[TOKEN] Material認証が最大リトライ回数に達しました（タイムアウト）")
                        self._material_token_fetched = False
                        self.browser.update_autologin_msg("❌ マテリアルトークン取得失敗（タイムアウト）")
            
            # 10秒後にタイムアウトチェック
            self._material_timeout_timer = QTimer.singleShot(10000, on_timeout)
            
            # リトライコンテキストを保存（エラー時に使用）
            self._material_retry_context = {
                'retry_count': retry_count,
                'max_retries': max_retries
            }
            
            # URL変化を監視（認証リダイレクト検出用）
            def on_url_changed(url):
                if self._material_auth_completed:
                    logger.debug("[TOKEN] 認証完了済み、urlChangedをスキップ")
                    return
                    
                url_str = url.toString()
                logger.info(f"[TOKEN] URL変化検出: {mask_sensitive_url(url_str)}")
                logger.debug("URL変化: %s", mask_sensitive_url(url_str))
                
                # /samples/samples に到達し、エラーページでない場合は認証成功
                if 'rde-material.nims.go.jp' in url_str and '/samples/samples' in url_str and '/error' not in url_str:
                    logger.info("[TOKEN] ✅ URL変化で認証成功検出")
                    logger.debug("URL変化で認証成功")
                    self._material_auth_completed = True
                    # メッセージ更新: Materialトークン取得開始
                    self.browser.update_autologin_msg("🔑 Materialトークン取得中...")
                    
                    # タイムアウトタイマーをキャンセル
                    if hasattr(self, '_material_timeout_timer'):
                        # QTimer.singleShotは直接stopできないが、フラグで制御される
                        logger.debug("[TOKEN] タイムアウト監視を停止（認証成功）")
                    
                    # シグナルを切断
                    try:
                        self.webview.urlChanged.disconnect(on_url_changed)
                        logger.debug("[TOKEN] urlChangedシグナルを切断")
                    except Exception as e:
                        logger.debug("[TOKEN] urlChanged切断済みまたはエラー: %s", e)
                    
                    try:
                        self.webview.loadFinished.disconnect(on_load_finished)
                        logger.debug("[TOKEN] loadFinishedシグナルを切断")
                    except Exception as e:
                        logger.debug("[TOKEN] loadFinished切断済みまたはエラー: %s", e)
                    
                    # トークン取得を試行（URL変化で検出した場合もここで実行）
                    def after_token_fetch():
                        logger.info("[TOKEN] rde-material.nims.go.jpのトークン取得を試行")
                        logger.debug("Material トークン取得開始")
                        self.try_get_bearer_token(retries=3, host='rde-material.nims.go.jp')
                        # トークン取得完了後、元のrde.nims.go.jp/rde/datasetsに戻る
                        QTimer.singleShot(2000, self.return_to_rde_datasets)
                    
                    # 待機時間を6秒に延長（sessionStorage更新待ち）
                    self._material_token_fetch_timer = QTimer.singleShot(6000, after_token_fetch)
            
            # ページロード完了を待ってトークン取得
            def on_load_finished(ok):
                # 既に認証完了している場合は何もしない（重複処理防止）
                if self._material_auth_completed:
                    logger.debug("[TOKEN] 認証完了済み、loadFinishedをスキップ")
                    return
                
                if not ok:
                    logger.warning("[TOKEN] rde-material.nims.go.jp ページロード失敗")
                    logger.debug("Material ページロード失敗")
                    # シグナルを切断
                    try:
                        self.webview.loadFinished.disconnect(on_load_finished)
                    except:
                        pass
                    try:
                        self.webview.urlChanged.disconnect(on_url_changed)
                    except:
                        pass
                    
                    # v2.0.7: ページロード失敗時のリトライ
                    if retry_count < max_retries - 1:
                        logger.info(f"[TOKEN] Material認証失敗 - {2000}ms後にリトライします")
                        QTimer.singleShot(2000, lambda: self.fetch_material_token(retry_count + 1, max_retries))
                    else:
                        logger.error("[TOKEN] Material認証が最大リトライ回数に達しました")
                        self._material_token_fetched = False  # フラグリセット
                    return
                
                current_url = self.webview.url().toString()
                logger.info(f"[TOKEN] ページロード完了: {mask_sensitive_url(current_url)}")
                logger.debug("Material loadFinished: %s", mask_sensitive_url(current_url))
                
                # エラーページへのリダイレクトを検出
                if '/error' in current_url or '401' in current_url:
                    self._material_auth_redirect_count += 1
                    logger.info(f"[TOKEN] 401エラーページ検出 (リダイレクト回数: {self._material_auth_redirect_count}) - 認証リダイレクト待機中")
                    logger.debug("401エラー検出、OAuth2リダイレクト待機中... (試行%s/3)", self._material_auth_redirect_count)
                    
                    # 最大3回までリダイレクトを待つ
                    if self._material_auth_redirect_count >= 3:
                        logger.warning("[TOKEN] 認証リダイレクトがタイムアウト")
                        logger.debug("認証タイムアウト")
                        try:
                            self.webview.loadFinished.disconnect(on_load_finished)
                        except:
                            pass
                        try:
                            self.webview.urlChanged.disconnect(on_url_changed)
                        except:
                            pass
                        
                        # v2.0.7: 認証タイムアウト時のリトライ
                        if retry_count < max_retries - 1:
                            logger.info(f"[TOKEN] リダイレクトタイムアウト - {3000}ms後にリトライします")
                            QTimer.singleShot(3000, lambda: self.fetch_material_token(retry_count + 1, max_retries))
                        else:
                            logger.error("[TOKEN] Material認証が最大リトライ回数に達しました")
                            self._material_token_fetched = False  # フラグリセット
                    return
                
                # /samples/samples への到達を確認（認証成功）
                if 'rde-material.nims.go.jp' in current_url and '/samples/samples' in current_url and '/error' not in current_url:
                    logger.info("[TOKEN] ✅ rde-material.nims.go.jp 認証成功 - /samples/samplesに到達")
                    logger.debug("Material 認証成功、トークン取得準備")
                    self._material_auth_completed = True
                    # メッセージ更新: Materialトークン取得開始
                    self.browser.update_autologin_msg("🔑 Materialトークン取得中...")
                    
                    # タイムアウトタイマーをキャンセル
                    if hasattr(self, '_material_timeout_timer'):
                        logger.debug("[TOKEN] タイムアウト監視を停止（認証成功）")
                    
                    # シグナルを切断（無限ループ防止）- 順序に注意
                    try:
                        self.webview.loadFinished.disconnect(on_load_finished)
                        logger.debug("[TOKEN] loadFinishedシグナルを切断")
                    except Exception as e:
                        logger.debug("[TOKEN] loadFinished切断済みまたはエラー: %s", e)
                    
                    try:
                        self.webview.urlChanged.disconnect(on_url_changed)
                        logger.debug("[TOKEN] urlChangedシグナルを切断")
                    except Exception as e:
                        logger.debug("[TOKEN] urlChanged切断済みまたはエラー: %s", e)
                    
                    # トークン取得を試行（十分な待機時間を確保）
                    def after_token_fetch():
                        logger.info("[TOKEN] rde-material.nims.go.jpのトークン取得を試行")
                        logger.debug("Material トークン取得開始")
                        
                        # タイムアウト監視を完全停止
                        if hasattr(self, '_material_timeout_timer'):
                            logger.debug("[TOKEN] タイムアウト監視を停止（トークン取得開始）")
                        
                        self.try_get_bearer_token(retries=3, host='rde-material.nims.go.jp')
                        # トークン取得完了後、元のrde.nims.go.jp/rde/datasetsに戻る
                        # 注意: try_get_bearer_token内で_notify_login_completeが呼ばれる
                        QTimer.singleShot(2000, self.return_to_rde_datasets)
                    
                    # 待機時間を6秒に延長（認証処理とsessionStorage更新を待つ）
                    self._material_token_fetch_timer = QTimer.singleShot(6000, after_token_fetch)
                else:
                    # まだ認証リダイレクト中
                    logger.info(f"[TOKEN] 認証リダイレクト中: {current_url}")
                    logger.debug("リダイレクト待機: %s", current_url)
            
            # 一時的にシグナルに接続
            self.webview.loadFinished.connect(on_load_finished)
            self.webview.urlChanged.connect(on_url_changed)
            logger.debug("[TOKEN] loadFinished/urlChangedシグナルを接続")
            
            # WebViewでrde-material.nims.go.jpに遷移
            logger.info(f"[TOKEN] WebViewでURL遷移実行: {material_url}")
            self.webview.setUrl(QUrl(material_url))
            
        except Exception as e:
            logger.error(f"[TOKEN] rde-material.nims.go.jpトークン取得エラー: {e}")
            logger.debug("Material トークン取得エラー: %s", e)
            
            # v2.0.7: 例外発生時のリトライ
            if retry_count < max_retries - 1:
                logger.info(f"[TOKEN] 例外発生 - {3000}ms後にリトライします: {e}")
                QTimer.singleShot(3000, lambda: self.fetch_material_token(retry_count + 1, max_retries))
            else:
                logger.error("[TOKEN] Material認証が最大リトライ回数に達しました（例外）")
                self._material_token_fetched = False  # フラグリセット
    
    def return_to_rde_datasets(self):
        """
        rde.nims.go.jp/rde/datasetsに戻る（データ取得機能用）
        """
        try:
            rde_datasets_url = "https://rde.nims.go.jp/rde/datasets"
            logger.info(f"rde.nims.go.jp/rde/datasetsに戻ります: {rde_datasets_url}")
            self.webview.setUrl(QUrl(rde_datasets_url))
        except Exception as e:
            logger.error(f"rde.nims.go.jp/rde/datasets遷移エラー: {e}")
    
    def reset_material_token_flag(self):
        """
        マテリアルトークン取得フラグをリセット
        再ログイン時に呼び出すことで、再度トークン取得を可能にする
        """
        logger.info("[TOKEN] マテリアルトークン取得フラグをリセット")
        self._material_token_fetched = False
    
    def invalidate_all_tokens(self):
        """
        全トークンを無効化（ログインボタン押下時に使用）
        
        v2.0.6: ファイル削除 + フラグリセット + メモリクリア
        """
        try:
            from config.common import delete_bearer_token
            
            logger.info("[TOKEN] 全トークン無効化を開始")
            
            # 1. トークンファイルを削除
            rde_deleted = delete_bearer_token('rde.nims.go.jp')
            material_deleted = delete_bearer_token('rde-material.nims.go.jp')
            
            if rde_deleted:
                logger.info("[TOKEN] RDEトークンファイルを削除")
            if material_deleted:
                logger.info("[TOKEN] マテリアルトークンファイルを削除")
            
            # 2. 取得完了フラグをリセット
            self._rde_token_acquired = False
            self._material_token_acquired = False
            self._material_token_fetched = False
            logger.info("[TOKEN] トークン取得フラグをリセット")
            
            # 3. メモリ上のトークンをクリア
            if hasattr(self.browser, 'bearer_token'):
                self.browser.bearer_token = None
            
            logger.info("[TOKEN] ✅ 全トークン無効化完了")
            return True
            
        except Exception as e:
            logger.error(f"[TOKEN] トークン無効化エラー: {e}", exc_info=True)
            return False
    
    def check_tokens_acquired(self) -> tuple[bool, bool]:
        """
        両方のトークン（RDE・マテリアル）が取得済みかチェック
        
        Returns:
            tuple: (rde_token_exists, material_token_exists)
        
        Note:
            v2.0.6: 存在チェックのみ（高速）。有効性検証はvalidate_tokens_with_api()を使用。
        """
        from config.common import load_bearer_token
        
        rde_token = load_bearer_token('rde.nims.go.jp')
        material_token = load_bearer_token('rde-material.nims.go.jp')
        
        rde_exists = rde_token is not None and len(rde_token) > 0
        material_exists = material_token is not None and len(material_token) > 0
        
        logger.info(f"[TOKEN-CHECK] RDE: {rde_exists}, Material: {material_exists}")
        return rde_exists, material_exists
    
    def validate_tokens_with_api(self) -> tuple[bool, bool]:
        """
        両方のトークンの有効性をAPI呼び出しで検証
        
        Returns:
            tuple: (rde_token_valid, material_token_valid)
        
        Note:
            v2.0.6: 実際のAPI呼び出しで401エラーをチェック（低速）
        """
        try:
            from config.common import load_bearer_token
            from net.http_helpers import proxy_request
            
            logger.info("[TOKEN-VALIDATE] トークン有効性検証開始")
            
            # RDEトークン検証
            rde_valid = False
            rde_token = load_bearer_token('rde.nims.go.jp')
            if rde_token:
                try:
                    # RDE APIエンドポイント: /rde/subGroups（軽量）
                    test_url = "https://rde.nims.go.jp/rde/api/v1/subGroups"
                    headers = {"Authorization": f"Bearer {rde_token}"}
                    
                    response = proxy_request(
                        method='GET',
                        url=test_url,
                        headers=headers,
                        timeout=5
                    )
                    
                    if response and response.status_code == 200:
                        rde_valid = True
                        logger.info("[TOKEN-VALIDATE] RDEトークン有効")
                    elif response and response.status_code == 401:
                        logger.warning("[TOKEN-VALIDATE] RDEトークン無効（401）")
                    else:
                        logger.warning(f"[TOKEN-VALIDATE] RDE検証エラー: {response.status_code if response else 'No response'}")
                        
                except Exception as e:
                    logger.error(f"[TOKEN-VALIDATE] RDE検証例外: {e}")
            else:
                logger.info("[TOKEN-VALIDATE] RDEトークンが存在しません")
            
            # マテリアルトークン検証
            material_valid = False
            material_token = load_bearer_token('rde-material.nims.go.jp')
            if material_token:
                try:
                    # Material APIエンドポイント: /samples/samples（軽量）
                    test_url = "https://rde-material.nims.go.jp/samples/api/v1/samples"
                    headers = {"Authorization": f"Bearer {material_token}"}
                    
                    response = proxy_request(
                        method='GET',
                        url=test_url,
                        headers=headers,
                        timeout=5
                    )
                    
                    if response and response.status_code == 200:
                        material_valid = True
                        logger.info("[TOKEN-VALIDATE] マテリアルトークン有効")
                    elif response and response.status_code == 401:
                        logger.warning("[TOKEN-VALIDATE] マテリアルトークン無効（401）")
                    else:
                        logger.warning(f"[TOKEN-VALIDATE] Material検証エラー: {response.status_code if response else 'No response'}")
                        
                except Exception as e:
                    logger.error(f"[TOKEN-VALIDATE] Material検証例外: {e}")
            else:
                logger.info("[TOKEN-VALIDATE] マテリアルトークンが存在しません")
            
            logger.info(f"[TOKEN-VALIDATE] 検証完了 - RDE: {rde_valid}, Material: {material_valid}")
            return rde_valid, material_valid
            
        except Exception as e:
            logger.error(f"[TOKEN-VALIDATE] トークン検証エラー: {e}", exc_info=True)
            return False, False
    
    def ensure_both_tokens(self, force_refresh=False):
        """
        両方のトークンが取得済みか確認し、不足分を取得
        
        Args:
            force_refresh: Trueの場合、既存トークンを強制リフレッシュ
        """
        logger.info("[TOKEN-ENSURE] トークン確認開始")
        
        rde_exists, material_exists = self.check_tokens_acquired()
        
        if force_refresh:
            logger.info("[TOKEN-ENSURE] 強制リフレッシュモード")
            self._rde_token_acquired = False
            self._material_token_acquired = False
            self._material_token_fetched = False
        
        # RDEトークンが不足している場合
        if not rde_exists or force_refresh:
            logger.info("[TOKEN-ENSURE] RDEトークンを取得します")
            self.browser.update_autologin_msg("🔄 RDEトークン取得中...")
            # 3秒待機してからトークン取得（PySide6対応）
            self.try_get_bearer_token(retries=3, host='rde.nims.go.jp', initial_delay=3000)
        else:
            logger.info("[TOKEN-ENSURE] RDEトークンは既に存在")
            self._rde_token_acquired = True
        
        # マテリアルトークンが不足している場合
        if not material_exists or force_refresh:
            logger.info("[TOKEN-ENSURE] マテリアルトークンを取得します")
            self.browser.update_autologin_msg("🔄 マテリアルトークン取得中...")
            # RDEトークン取得後に実行
            QTimer.singleShot(5000, self.fetch_material_token)
        else:
            logger.info("[TOKEN-ENSURE] マテリアルトークンは既に存在")
            self._material_token_acquired = True
        
        # 両トークンが既に存在する場合、ログイン完了通知を送信
        if self._rde_token_acquired and self._material_token_acquired:
            logger.info("[TOKEN-ENSURE] ✅ 両トークン既存 - ログイン完了通知を送信")
            self._login_in_progress = False
            self.browser.update_autologin_msg("✅ ログイン完了")
            QTimer.singleShot(500, self._notify_login_complete)
    
    def is_login_complete(self) -> bool:
        """
        ログインが完全に完了しているかチェック（両トークン取得済み）
        
        Returns:
            bool: 両トークン取得済みの場合True
        """
        rde_exists, material_exists = self.check_tokens_acquired()
        return rde_exists and material_exists
    
    def _notify_login_complete(self):
        """ログイン完了を通知"""
        try:
            logger.info("[TOKEN] ログイン完了通知を送信")
            
            # メッセージ更新
            if hasattr(self.browser, 'update_autologin_msg'):
                self.browser.update_autologin_msg("✅ ログイン完了（両トークン取得済み）")
            
            # UIコントローラーに通知
            if hasattr(self.browser, 'ui_controller'):
                if hasattr(self.browser.ui_controller, 'on_login_complete'):
                    self.browser.ui_controller.on_login_complete()
            
            # ディスプレイマネージャーに通知
            if hasattr(self.browser, 'display_manager'):
                self.browser.display_manager.set_message("ログイン完了 - 全機能が利用可能です")
                
        except Exception as e:
            logger.error(f"[TOKEN] ログイン完了通知エラー: {e}", exc_info=True)

    
    def _notify_token_updated(self, token: str, host: str):
        """
        トークン更新をUIコンポーネントに通知
        
        Args:
            token: 更新されたトークン
            host: ホスト名
        """
        try:
            logger.info(f"[TOKEN] トークン更新をUIコンポーネントに通知: host={host}")
            
            # デバッグ情報
            logger.debug(f"[TOKEN] browser属性チェック: hasattr(ui_controller)={hasattr(self.browser, 'ui_controller')}")
            if hasattr(self.browser, 'ui_controller'):
                logger.debug(f"[TOKEN] ui_controller存在チェック: {self.browser.ui_controller is not None}")
            
            # UI controllerが存在する場合、タブwidgetを更新
            if hasattr(self.browser, 'ui_controller') and self.browser.ui_controller:
                logger.info("[TOKEN] UIコントローラー経由でタブwidgetを更新開始")
                self.browser.ui_controller._update_tabs_bearer_token(token)
                logger.info("[TOKEN] UIコントローラー経由でタブwidgetを更新完了")
            else:
                logger.warning("[TOKEN] UIコントローラーが存在しないため、タブwidget更新をスキップ")
            
            # 直接タブwidgetが存在する場合も更新
            if hasattr(self.browser, 'tabs') and self.browser.tabs:
                logger.debug(f"[TOKEN] tabs属性が存在: count={self.browser.tabs.count()}")
                for i in range(self.browser.tabs.count()):
                    widget = self.browser.tabs.widget(i)
                    if hasattr(widget, 'bearer_token'):
                        widget.bearer_token = token
                        logger.debug(f"[TOKEN] タブ{i}のbearer_tokenを更新")
            else:
                logger.debug("[TOKEN] tabs属性が存在しないか、Noneです")
                        
        except Exception as e:
            logger.error(f"[TOKEN] トークン更新通知エラー: {e}", exc_info=True)
    
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

