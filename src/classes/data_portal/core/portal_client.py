"""
データポータルクライアント

ARIMデータポータルサイトへのHTTP通信・セッション管理・ログイン機能を提供
net.http_helpersを使用してプロキシ・SSL設定に対応
"""

import logging
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse

from net.http_helpers import proxy_get, proxy_post
from classes.managers.log_manager import get_logger
from .auth_manager import PortalCredentials
from ..conf.config import get_data_portal_config

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
        if self.credentials:
            return (self.credentials.basic_username, self.credentials.basic_password)
        return None
    
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
             files: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        """
        POSTリクエストを送信
        
        Args:
            path: リクエストパス
            data: POSTデータ
            files: アップロードファイル
        
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
            
            response = proxy_post(
                url,
                data=data,
                files=files,
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
            
            # Step 2: ログインフォーム送信
            login_data = {
                'id': self.credentials.login_username,  # 'user_id'ではなく'id'
                'password': self.credentials.login_password,
                'pass_check': '1'  # ログインチェックフラグ
            }
            
            logger.info(f"ログインフォーム送信: id={self.credentials.login_username}, pass_check=1")
            success, response = self.post("index.php", data=login_data)
            
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
            logger.info(f"'ユーザーID' in response: {'ユーザーID' in response_text}")
            
            # ログイン失敗判定：ログインページにリダイレクトされた場合
            if 'ログイン' in response_text or 'Login' in response_text:
                logger.error("❌ ログイン失敗（ログインページ再表示）")
                # レスポンスの先頭200文字をログ出力
                logger.error(f"レスポンス先頭: {response_text[:200]}")
                return False, "ログイン失敗: 認証情報が正しくありません"
            else:
                # ログインページが表示されていない = ログイン成功
                self.authenticated = True
                logger.info("✅ ログイン成功（ログインページ非表示確認）")
                return True, "ログイン成功"
            
        except Exception as e:
            logger.error(f"ログインエラー: {e}")
            self.authenticated = False
            return False, f"ログインエラー: {e}"
    
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
