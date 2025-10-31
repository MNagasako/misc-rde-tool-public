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
from PyQt5.QtCore import QTimer, QUrl
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
        
        # 既存の認証情報(後方互換)
        self.login_username = browser.login_username
        self.login_password = browser.login_password
        self.login_mode = browser.login_mode
        
        # v1.18.3: マルチホストトークン取得フラグ
        self._material_token_fetched = False
        
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
        
        # v1.18.3: 自動ログイン開始時にマテリアルトークンフラグをリセット
        logger.info("[LOGIN] 自動ログイン開始 - マテリアルトークンフラグをリセット")
        self.reset_material_token_flag()
            
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

    def try_get_bearer_token(self, retries=3, host='rde.nims.go.jp'):
        """
        WebViewからBearerトークンを取得する（複数ホスト対応）
        
        Args:
            retries: リトライ回数
            host: 対象ホスト名（デフォルト: 'rde.nims.go.jp'）
        """
        logger.info(f"[TOKEN] Bearerトークン取得開始: host={host}, retries={retries}")
        js_code = load_js_template('extract_bearer_token.js')
        
        def handle_token_list(token_list):
            logger.debug(f"[TOKEN] sessionStorage取得結果: {len(token_list) if token_list else 0}件")
            if not token_list and retries > 0:
                logger.warning(f"[TOKEN] トークン取得失敗 ({host})。リトライします... (残り{retries-1}回)")
                self.try_get_bearer_token(retries=retries - 1, host=host)
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
                            token = data['secret']
                            
                            # トークンの内容をデコードして検証（デバッグ用）
                            print(f"[TOKEN-DEBUG] 取得したトークン: {token[:50]}...")
                            try:
                                import base64
                                # JWT形式: header.payload.signature
                                parts = token.split('.')
                                if len(parts) == 3:
                                    # ペイロード部分をデコード（Base64URL → 通常のBase64）
                                    payload_b64 = parts[1]
                                    # パディング調整
                                    payload_b64 += '=' * (4 - len(payload_b64) % 4)
                                    payload_json = base64.b64decode(payload_b64).decode('utf-8')
                                    payload_data = json.loads(payload_json)
                                    print(f"[TOKEN-DEBUG] トークンペイロード: aud={payload_data.get('aud')}, scp={payload_data.get('scp')}")
                                    
                                    # スコープを確認してトークンの種類を判定
                                    scopes = payload_data.get('scp', '')
                                    if 'materials' in scopes:
                                        print(f"[TOKEN-DEBUG] ✓ Material API用トークンを検出")
                                    else:
                                        print(f"[TOKEN-DEBUG] ✓ RDE API用トークンを検出")
                            except Exception as decode_err:
                                print(f"[TOKEN-DEBUG] トークンデコードエラー: {decode_err}")
                            
                            self.browser.bearer_token = token
                            logger.info(f"[TOKEN] Bearerトークン自動取得成功 ({host}): {token[:40]}... (省略)")
                            print(f"[TOKEN-DEBUG] トークンを {host} として保存")
                            
                            # ファイルにも保存（ホスト別）
                            self.save_bearer_token_to_file(token, host)
                            
                            # v1.18.3: UIコンポーネントにトークン更新を通知
                            self._notify_token_updated(token, host)
                            
                            # v1.16: 認証完了後のクリーンアップ
                            self._secure_cleanup_credentials()
                            
                            # rde.nims.go.jpの場合は、続けてrde-material.nims.go.jpのトークンも取得
                            # v1.18.3: 無限ループ防止 - まだ取得していない場合のみ実行
                            if host == 'rde.nims.go.jp' and not self._material_token_fetched:
                                logger.info("[TOKEN] rde-material.nims.go.jpのトークン取得を開始します")
                                print(f"[TOKEN-DEBUG] Material トークン取得プロセスを2秒後に開始")
                                QTimer.singleShot(2000, lambda: self.fetch_material_token())
                            
                            return
                    except Exception as e:
                        logger.warning(f"[TOKEN] JSONパース失敗: {e}")
                        print(f"[TOKEN-DEBUG] JSONパースエラー: {e}")
            
            logger.warning(f"[TOKEN] BearerトークンがsessionStorageから取得できませんでした ({host})")
        
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
    
    def fetch_material_token(self):
        """
        rde-material.nims.go.jpからBearerトークンを取得
        認証情報は共通のため、既にログイン済みの状態でアクセスして
        Cookieからトークンを抽出する
        
        トークン取得後、rde.nims.go.jp/rde/datasetsに戻る(データ取得機能用)
        """
        # v1.18.3: 二重実行防止 - 既に取得プロセス実行中の場合はスキップ
        if self._material_token_fetched:
            logger.info("[TOKEN] rde-material.nims.go.jpトークン取得は既に実行済みです（スキップ）")
            return
        
        # フラグを先に設定して二重実行を防止
        logger.info("[TOKEN] rde-material.nims.go.jpトークン取得フラグを設定")
        self._material_token_fetched = True
            
        try:
            # 重要: rde-material.nims.go.jpのログインページに遷移してトークンを取得
            # ルートパスではなく、/rde/samplesなど実際のアプリケーションパスに遷移
            material_url = "https://rde-material.nims.go.jp/rde/samples"
            logger.info(f"[TOKEN] rde-material.nims.go.jpへ遷移開始: {material_url}")
            print(f"[TOKEN-DEBUG] Material URL遷移: {material_url}")
            
            # ページロード完了を待ってトークン取得
            def on_load_finished(ok):
                # シグナルを即座に切断（無限ループ防止）
                try:
                    self.webview.loadFinished.disconnect(on_load_finished)
                    logger.debug("[TOKEN] loadFinishedシグナルを切断")
                except:
                    pass  # 既に切断されている場合は無視
                
                if ok:
                    logger.info("[TOKEN] rde-material.nims.go.jp ページロード完了")
                    print(f"[TOKEN-DEBUG] Material ページロード完了、待機中...")
                    # トークン取得を試行（十分な待機時間を確保）
                    def after_token_fetch():
                        logger.info("[TOKEN] rde-material.nims.go.jpのトークン取得を試行")
                        print(f"[TOKEN-DEBUG] Material トークン取得開始")
                        self.try_get_bearer_token(retries=3, host='rde-material.nims.go.jp')
                        # トークン取得後、元のrde.nims.go.jp/rde/datasetsに戻る
                        QTimer.singleShot(1000, self.return_to_rde_datasets)
                    
                    # 待機時間を5秒に延長（認証処理とsessionStorage更新を待つ）
                    QTimer.singleShot(5000, after_token_fetch)
                else:
                    logger.warning("[TOKEN] rde-material.nims.go.jp ページロード失敗")
                    print(f"[TOKEN-DEBUG] Material ページロード失敗")
            
            # 一時的にloadFinishedシグナルに接続
            self.webview.loadFinished.connect(on_load_finished)
            logger.debug("[TOKEN] loadFinishedシグナルを接続")
            
            # WebViewでrde-material.nims.go.jpに遷移
            logger.info(f"[TOKEN] WebViewでURL遷移実行: {material_url}")
            self.webview.setUrl(QUrl(material_url))
            
        except Exception as e:
            logger.error(f"[TOKEN] rde-material.nims.go.jpトークン取得エラー: {e}")
            print(f"[TOKEN-DEBUG] Material トークン取得エラー: {e}")
            # エラー時はフラグをリセット
            self._material_token_fetched = False
    
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
