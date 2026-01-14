"""
データポータルクライアント

ARIMデータポータルサイトへのHTTP通信・セッション管理・ログイン機能を提供
net.http_helpersを使用してプロキシ・SSL設定に対応
"""

import logging
import re
import os
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse

from net.http_helpers import proxy_get, proxy_post
from classes.managers.log_manager import get_logger
from .auth_manager import PortalCredentials
from ..conf.config import get_data_portal_config
from bs4 import BeautifulSoup

logger = get_logger("DataPortal.PortalClient")


class PortalClient:
    """
    データポータルクライアントクラス
    
    機能:
    - セッション管理
    - Basic認証対応
    - ログイン/ログアウト
    - データポータルサイトへのHTTP通信
    
    環境設定:
    - input/data_portal_config.json から環境別URLを読み込み
    - テスト環境URLはハードコーディングしない（Git管理外設定ファイルで管理）
    """
    
    def __init__(self, environment: str = "production"):
        """
        初期化
        
        Args:
            environment: 'test' または 'production'
        """
        self.environment = environment
        
        # 設定ファイルからURLを取得
        config = get_data_portal_config()
        env_config = config.get_environment_config(environment)
        
        if env_config is None:
            logger.error(f"環境 '{environment}' の設定が見つかりません")
            raise ValueError(f"環境 '{environment}' の設定が見つかりません")
        
        self.base_url = env_config.url
        self.credentials: Optional[PortalCredentials] = None
        self.authenticated = False
        self.session_cookies = {}
        
        logger.info(f"PortalClient 初期化: {environment} 環境 ({self.base_url})")
    
    def set_credentials(self, credentials: PortalCredentials):
        """
        認証情報を設定
        
        Args:
            credentials: 認証情報
        """
        self.credentials = credentials
        logger.info("認証情報を設定しました")
    
    def _get_auth_tuple(self) -> Optional[Tuple[str, str]]:
        """
        Basic認証用のタプルを取得
        
        Returns:
            Tuple[str, str]: (username, password) または None
        """
        # NOTE:
        # - 本番環境(production)では現在 Basic認証は不要
        # - テスト環境(test)では Basic認証が必要
        # 仕様変更で完全に不要/必要が反転した場合は、この分岐を見直す。
        if not self.credentials:
            return None

        if str(self.environment) != "test":
            return None

        user = (self.credentials.basic_username or "").strip()
        pwd = (self.credentials.basic_password or "").strip()
        if not user or not pwd:
            return None
        return (user, pwd)
    
    def _build_url(self, path: str = "") -> str:
        """
        完全なURLを構築
        
        Args:
            path: パス（main.php等）
        
        Returns:
            str: 完全なURL
        """
        if path:
            return urljoin(self.base_url, path)
        return self.base_url
    
    def get(self, path: str = "", params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        """
        GETリクエストを送信
        
        Args:
            path: リクエストパス
            params: クエリパラメータ
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            url = self._build_url(path)
            auth = self._get_auth_tuple()
            
            logger.info(f"[REQUEST] GET {url}")
            if params:
                logger.info(f"[REQUEST] Query Params: {params}")
            if auth:
                logger.info(f"[REQUEST] Basic Auth: {auth[0]}:***")
            if self.session_cookies:
                logger.info(f"[REQUEST] Cookies: {list(self.session_cookies.keys())}")
            
            response = proxy_get(
                url,
                params=params,
                auth=auth,
                cookies=self.session_cookies
            )
            
            # 実際に送信されたリクエストヘッダーをログ出力
            if hasattr(response, 'request') and hasattr(response.request, 'headers'):
                logger.info(f"[REQUEST] Sent Headers: {dict(response.request.headers)}")
            
            # レスポンス詳細をログ出力
            logger.info(f"[RESPONSE] Status: {response.status_code}")
            logger.info(f"[RESPONSE] Headers: {dict(response.headers)}")
            if response.cookies:
                logger.info(f"[RESPONSE] Cookies: {response.cookies.get_dict()}")
            
            # レスポンスボディの先頭を出力（デバッグ用）
            try:
                body_preview = response.text[:500] if hasattr(response, 'text') else str(response.content[:500])
                logger.debug(f"[RESPONSE] Body Preview: {body_preview}")
            except:
                pass
            
            if response.status_code == 200:
                # セッションCookieを更新
                self.session_cookies.update(response.cookies.get_dict())
                logger.info("[SUCCESS] GET request completed successfully")
                return True, response
            else:
                logger.warning(f"[FAILURE] GET リクエスト失敗: {response.status_code}")
                logger.warning(f"[FAILURE] Response Text: {response.text[:200] if hasattr(response, 'text') else 'N/A'}")
                return False, f"ステータスコード: {response.status_code}"
                
        except Exception as e:
            logger.error(f"[ERROR] GET リクエストエラー: {e}")
            import traceback
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            return False, str(e)
    
    def post(self, path: str = "", data: Optional[Dict[str, Any]] = None, 
             files: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, Any]:
        """
        POSTリクエストを送信
        
        Args:
            path: リクエストパス
            data: POSTデータ
            files: アップロードファイル
            headers: HTTPヘッダー
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            url = self._build_url(path)
            auth = self._get_auth_tuple()
            
            logger.info(f"[REQUEST] POST {url}")
            if data:
                logger.info(f"[REQUEST] Form Data: {data}")
            if files:
                logger.info(f"[REQUEST] Files: {list(files.keys())}")
            if auth:
                logger.info(f"[REQUEST] Basic Auth: {auth[0]}:***")
            if self.session_cookies:
                logger.info(f"[REQUEST] Cookies: {list(self.session_cookies.keys())}")
            if headers:
                logger.info(f"[REQUEST] Custom Headers: {headers}")
            
            response = proxy_post(
                url,
                data=data,
                files=files,
                auth=auth,
                cookies=self.session_cookies,
                headers=headers
            )
            
            # 実際に送信されたリクエストヘッダーをログ出力
            if hasattr(response, 'request') and hasattr(response.request, 'headers'):
                logger.info(f"[REQUEST] Sent Headers: {dict(response.request.headers)}")
            
            # レスポンス詳細をログ出力
            logger.info(f"[RESPONSE] Status: {response.status_code}")
            logger.info(f"[RESPONSE] Headers: {dict(response.headers)}")
            if response.cookies:
                logger.info(f"[RESPONSE] Cookies: {response.cookies.get_dict()}")
            
            # レスポンスボディの先頭を出力（デバッグ用）
            try:
                body_preview = response.text[:500] if hasattr(response, 'text') else str(response.content[:500])
                logger.debug(f"[RESPONSE] Body Preview: {body_preview}")
            except:
                pass
            
            if response.status_code == 200:
                # セッションCookieを更新
                self.session_cookies.update(response.cookies.get_dict())
                logger.info("[SUCCESS] POST request completed successfully")
                return True, response
            else:
                logger.warning(f"[FAILURE] POST リクエスト失敗: {response.status_code}")
                logger.warning(f"[FAILURE] Response Text: {response.text[:200] if hasattr(response, 'text') else 'N/A'}")
                return False, f"ステータスコード: {response.status_code}"
                
        except Exception as e:
            logger.error(f"[ERROR] POST リクエストエラー: {e}")
            import traceback
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            return False, str(e)
    
    def _save_login_debug_response(self, step_name: str, response_text: str):
        """
        ログインレスポンスをデバッグ用に保存
        
        Args:
            step_name: ステップ名（ファイル名に使用）
            response_text: レスポンスHTML
        """
        try:
            from datetime import datetime
            import os
            from config.common import get_dynamic_file_path
            
            debug_dir = get_dynamic_file_path("output/data_portal_debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(debug_dir, f"{step_name}_{timestamp}.html")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(response_text)
            
            logger.info(f"デバッグレスポンス保存: {filepath}")
        except Exception as e:
            logger.error(f"デバッグレスポンス保存エラー: {e}")
    
    def login(self, credentials: Optional[PortalCredentials] = None) -> Tuple[bool, str]:
        """
        データポータルサイトにログイン
        
        Args:
            credentials: 認証情報（Noneの場合は既に設定済みのものを使用）
        
        Returns:
            Tuple[bool, str]: (成功フラグ, メッセージ)
        """
        if credentials:
            self.set_credentials(credentials)
        
        if not self.credentials:
            return False, "認証情報が設定されていません"
        
        try:
            logger.info("ログイン開始...")
            
            # Step 1: ログインページにアクセス（セッション確立）
            success, response = self.get("index.php")
            if not success:
                return False, f"ログインページ取得失敗: {response}"
            
            # デバッグ用: ログインページを保存
            self._save_login_debug_response("login_page", response.text)
            logger.info("ログインページ取得成功")
            
            # Step 2: ログインフォーム送信（HTMLから動的抽出）
            # ログインページのフォームから全input/buttonを抽出し、必要項目を上書き
            parsed_fields: Dict[str, Any] = {}
            post_target: str = "index.php"
            try:
                soup = BeautifulSoup(response.text, 'lxml')

                # 候補フォームを収集
                candidate_forms = soup.find_all('form')
                target_form = None

                # ユーザー名/パスワードのいずれかを含むフォームを優先選択
                username_keys = ['id', 'user_id', 'username', 'login_id']
                password_keys = ['password', 'pass', 'pwd', 'login_password']

                for f in candidate_forms:
                    names = set(inp.get('name') for inp in f.find_all('input') if inp.get('name'))
                    if any(k in names for k in username_keys) and any(k in names for k in password_keys):
                        target_form = f
                        break

                # 見つからなければ最初のフォームを使用
                if target_form is None and candidate_forms:
                    target_form = candidate_forms[0]

                if target_form:
                    # form actionを取得
                    action_attr = target_form.get('action')
                    if action_attr:
                        post_target = action_attr

                    # input要素を収集
                    inputs = target_form.find_all('input')
                    for inp in inputs:
                        name = inp.get('name')
                        if not name:
                            continue
                        value = inp.get('value', '')
                        parsed_fields[name] = value

                    # button要素(type=submit)も収集（name/valueが要求されるサイト対策）
                    for btn in target_form.find_all('button'):
                        btn_type = (btn.get('type') or '').lower()
                        name = btn.get('name')
                        if btn_type == 'submit' and name:
                            value = btn.get('value') or btn.text.strip() or 'submit'
                            parsed_fields[name] = value
                else:
                    logger.warning("ログインフォームが見つかりません。既定フィールドで送信します。")
            except Exception as e:
                logger.warning(f"ログインフォーム解析失敗: {e}。既定フィールドで送信します。")

            # ユーザー名フィールドの推定と適用
            username_keys = ['id', 'user_id', 'username', 'login_id']
            applied_username = False
            for key in username_keys:
                if key in parsed_fields:
                    parsed_fields[key] = self.credentials.login_username
                    applied_username = True
                    break
            if not applied_username:
                # デフォルトキー
                parsed_fields['id'] = self.credentials.login_username

            # パスワードフィールドの推定と適用
            password_keys = ['password', 'pass', 'pwd', 'login_password']
            applied_password = False
            for key in password_keys:
                if key in parsed_fields:
                    parsed_fields[key] = self.credentials.login_password
                    applied_password = True
                    break
            if not applied_password:
                parsed_fields['password'] = self.credentials.login_password

            # ログインチェック/CSRF類似フィールドの適用（存在すれば上書き、なければ追加）
            if 'pass_check' in parsed_fields:
                parsed_fields['pass_check'] = '1'
            else:
                parsed_fields['pass_check'] = '1'

            # 追加でsubmit相当の候補を補完（必要に応じて）
            submit_candidates = ['login', 'submit', 'submit_login']
            if not any(k in parsed_fields for k in submit_candidates):
                # フォームにボタンnameがない場合、一般的なキーを補う
                parsed_fields['submit'] = 'login'

            login_data = parsed_fields
            
            # PySide6対応: Referer/Originヘッダーを明示的に設定
            headers = {
                'Referer': self._build_url("index.php"),
                'Origin': self.base_url.rstrip('/'),
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            logger.info(f"ログインフォーム送信: id={self.credentials.login_username}, pass_check=1, action={post_target}")
            success, response = self.post(post_target, data=login_data, headers=headers)
            
            if not success:
                return False, f"ログイン送信失敗: {response}"
            
            # デバッグ用: レスポンスを保存
            self._save_login_debug_response("login_response", response.text)
            
            # ログイン成功確認
            response_text = response.text
            
            # レスポンスの詳細ログ
            logger.info(f"レスポンス長: {len(response_text)} bytes")
            logger.info(f"'ログイン' in response: {'ログイン' in response_text}")
            logger.info(f"'Login' in response: {'Login' in response_text}")
            logger.info(f"'ログアウト' in response: {'ログアウト' in response_text}")
            logger.info(f"'page_header' in response: {'page_header' in response_text}")
            
            # PySide6対応: ログイン成功判定を「ログアウトリンクの存在」で行う
            # ログインページには「ログイン (Login)」ボタンがあり
            # ログイン後のメインページには「ログアウト (Logout)」リンクが表示される
            if 'ログアウト' in response_text or 'Logout' in response_text:
                # ログアウトリンクがある = ログイン成功
                self.authenticated = True
                logger.info("[OK] ログイン成功（ログアウトリンク確認）")
                return True, "ログイン成功"
            elif 'ログイン' in response_text or 'Login' in response_text:
                # ログインフォームが表示されている = ログイン失敗
                logger.error("[X] ログイン失敗（ログインページ再表示）")
                # レスポンスの先頭200文字をログ出力
                logger.error(f"レスポンス先頭: {response_text[:200]}")
                return False, "ログイン失敗: 認証情報が正しくありません"
            else:
                # どちらでもない場合（予期しない状態）
                logger.error("[X] ログイン判定不能（予期しないレスポンス）")
                logger.error(f"レスポンス先頭: {response_text[:200]}")
                return False, "ログイン失敗: 予期しないレスポンス"
            
        except Exception as e:
            logger.error(f"ログインエラー: {e}")
            self.authenticated = False
            return False, f"ログインエラー: {e}"

    def _origin_for_headers(self) -> str:
        try:
            parsed = urlparse(self.base_url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
        return "https://nanonet.go.jp"

    @staticmethod
    def _extract_csv_tokens_from_html(html: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract (code, key) for csv_download from portal HTML (best-effort)."""

        text = html or ""
        code = None
        key = None

        # Look for query fragments like code=165&key=... or hidden inputs.
        try:
            m = re.search(r"\bcode=(\d+)\b", text)
            if m:
                code = m.group(1)
        except Exception:
            code = None
        try:
            m = re.search(r"\bkey=([A-Za-z0-9_-]{8,})\b", text)
            if m:
                key = m.group(1)
        except Exception:
            key = None

        return code, key

    def download_theme_csv(
        self,
        *,
        keyword: str = "",
        search_inst: str = "",
        search_license_level: str = "",
        search_status: str = "",
        page: int = 1,
    ) -> Tuple[bool, Any]:
        """Download logged-in theme list as CSV.

        The portal provides a CSV export via main.php:
        - mode=theme
        - mode2=csv_download
        - auth=1
        - code/key tokens (extracted from HTML)
        """

        if not self.credentials:
            return False, "認証情報が設定されていません"

        if not self.is_authenticated():
            ok, msg = self.login()
            if not ok:
                return False, msg

        # Fetch main page to obtain code/key tokens.
        ok, resp = self.get("main.php", params={"mode": "theme"})
        if not ok or not hasattr(resp, "text"):
            return False, "CSV用トークン取得失敗"

        html = resp.text or ""
        code, key = self._extract_csv_tokens_from_html(html)
        if not code or not key:
            # Persist for inspection
            try:
                self._save_login_debug_response("theme_main_for_csv", html)
            except Exception:
                pass
            return False, "CSV用トークン(code/key)を抽出できません"

        headers = {
            "Origin": self._origin_for_headers(),
            "Referer": "https://nanonet.go.jp/",
        }

        data = {
            "mode": "theme",
            "mode2": "csv_download",
            "keyword": keyword or "",
            "search_inst": search_inst or "",
            "search_license_level": search_license_level or "",
            "search_status": search_status or "",
            "page": str(int(page) if int(page) > 0 else 1),
            "auth": "1",
            "code": str(code),
            "key": str(key),
        }

        ok, resp = self.post("main.php", data=data, headers=headers)
        if not ok:
            return False, resp

        # Save CSV for real-world inspection (opt-in via env).
        if os.environ.get("ARIM_PORTAL_SAVE_CSV", "").strip():
            try:
                from datetime import datetime
                from config.common import get_dynamic_file_path

                out_dir = get_dynamic_file_path("output/data_portal_debug")
                os.makedirs(out_dir, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(out_dir, f"theme_list_{self.environment}_{ts}.csv")
                payload = getattr(resp, "content", b"")
                with open(path, "wb") as fh:
                    fh.write(payload)
                logger.info(f"CSV保存: {path}")
            except Exception:
                pass

        return True, resp
    
    def logout(self) -> Tuple[bool, str]:
        """
        ログアウト
        
        Returns:
            Tuple[bool, str]: (成功フラグ, メッセージ)
        """
        try:
            logger.info("ログアウト...")
            
            # セッションをクリア
            self.session_cookies.clear()
            self.authenticated = False
            
            logger.info("ログアウト完了")
            return True, "ログアウト完了"
            
        except Exception as e:
            logger.error(f"ログアウトエラー: {e}")
            return False, f"ログアウトエラー: {e}"
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        接続テスト（Basic認証 + セッションログイン確認）
        
        Returns:
            Tuple[bool, str]: (成功フラグ, メッセージ)
        """
        try:
            logger.info("接続テスト開始...")
            
            # Step 1: Basic認証確認
            logger.info("Step 1: Basic認証確認...")
            success, response = self.get("main.php", params={"mode": "theme"})
            
            if not success:
                logger.warning(f"Basic認証失敗: {response}")
                return False, f"Basic認証失敗: {response}"
            
            logger.info("✅ Basic認証成功")
            
            # Step 2: セッションログイン確認
            logger.info("Step 2: セッションログイン確認...")
            login_success, login_message = self.login()
            
            if not login_success:
                logger.warning(f"セッションログイン失敗: {login_message}")
                return False, f"Basic認証成功、セッションログイン失敗: {login_message}"
            
            logger.info("✅ セッションログイン成功")
            return True, "接続成功（Basic認証 + セッションログイン）"
                
        except Exception as e:
            logger.error(f"接続テストエラー: {e}")
            return False, f"接続テストエラー: {e}"
    
    def is_authenticated(self) -> bool:
        """
        認証済みかチェック
        
        Returns:
            bool: 認証済みの場合True
        """
        return self.authenticated
