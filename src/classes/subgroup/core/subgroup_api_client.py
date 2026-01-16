"""
サブグループAPI クライアント（リファクタリング版）
HTTP通信、認証、ペイロード構築を統一管理
"""
import json
import logging
import base64
from qt_compat.widgets import QMessageBox
from qt_compat.core import QTimer
from core.bearer_token_manager import BearerTokenManager

logger = logging.getLogger(__name__)


class SubgroupApiClient:
    """サブグループAPI通信クライアント"""
    
    def __init__(self, widget, browser=None):
        """
        Args:
            widget: 親ウィジェット（bearer_token取得用）
            browser: Browserインスタンス（Cookie取得用、オプショナル）
        """
        self.widget = widget
        self.browser = browser  # v2.1.0: Cookie取得用
        
        # v2.1.0: browserが明示的に渡されていない場合、widgetの親を辿ってBrowserインスタンスを探す
        if not self.browser:
            self.browser = self._find_browser_instance(widget)
        
        self.api_base_url = "https://rde-api.nims.go.jp"
        self.bearer_token = None
    
    def _find_browser_instance(self, widget):
        """widgetの親階層からBrowserインスタンスを探す"""
        current = widget
        max_depth = 10  # 無限ループ防止
        depth = 0
        
        while current and depth < max_depth:
            # cookiesアトリビュートを持つインスタンスがBrowser
            if hasattr(current, 'cookies') and isinstance(getattr(current, 'cookies', None), list):
                logger.debug("Browserインスタンス発見: %s", type(current).__name__)
                return current
            
            # 親を辿る
            if hasattr(current, 'parent') and callable(current.parent):
                current = current.parent()
            elif hasattr(current, 'parentWidget') and callable(current.parentWidget):
                current = current.parentWidget()
            else:
                break
            
            depth += 1
        
        logger.warning("Browserインスタンスが見つかりませんでした")
        return None
    
    def authenticate(self):
        """
        Bearer トークンの取得・設定（統一管理システム使用）
        常に最新のトークンをファイルから読み込む
        
        Returns:
            bool: 認証成功かどうか
        """
        logger.debug("SubgroupApiClient.authenticate() 開始")
        logger.debug("RDE API用トークン取得中...")
        
        # v1.18.3: キャッシュせず、毎回最新のトークンを取得
        logger.debug("BearerTokenManager.get_token_with_relogin_prompt() 呼び出し前")
        self.bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self.widget)
        logger.debug("get_token_with_relogin_prompt() 結果: %s...", self.bearer_token[:20] if self.bearer_token else 'None')
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[TOKEN] サブグループAPI認証: token={'取得成功' if self.bearer_token else '取得失敗'}")
        
        if not self.bearer_token:
            logger.debug("トークンが取得できませんでした")
            QMessageBox.warning(
                self.widget, 
                "認証エラー", 
                "Bearerトークンが取得できません。ログイン状態を確認してください。"
            )
            return False
        
        logger.debug("認証成功: %s...", self.bearer_token[:20])
        
        # トークン検証
        logger.debug("トークン検証を実行...")
        is_valid = BearerTokenManager.validate_token(self.bearer_token)
        logger.debug("トークン検証結果: %s", '有効' if is_valid else '無効')
        
        if not is_valid:
            logger.debug("トークンが無効です")
            QMessageBox.warning(
                self.widget,
                "認証エラー",
                "Bearerトークンが無効です。再ログインしてください。"
            )
            return False
        
        return True

    def _load_material_token(self):
        """Load bearer token for material/material-api hosts.

        起動時クリーンアップ等でトークンファイルが空でも、WebViewの実行中セッションが
        Material用トークンを保持している場合があるため、最後にブラウザのbearer_tokenも確認する。
        """
        from config.common import load_bearer_token, save_bearer_token

        # Prefer API host key; fall back to UI host key for backward compatibility.
        token = load_bearer_token("rde-material-api.nims.go.jp")
        if token:
            return token
        token = load_bearer_token("rde-material.nims.go.jp")
        if token:
            return token

        # Fallback: use the currently held browser token if it looks like a Material token.
        browser_token = getattr(self.browser, "bearer_token", None)
        if isinstance(browser_token, str) and browser_token and self._looks_like_material_token(browser_token):
            try:
                # Persist for subsequent API calls; common.py will alias-save across UI/API hosts.
                save_bearer_token("rde-material.nims.go.jp", browser_token)
            except Exception:
                pass
            return browser_token

        return None

    def _decode_jwt_payload_no_verify(self, token: str) -> dict:
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return {}
            payload_b64 = parts[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
            payload = json.loads(payload_bytes.decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _looks_like_material_token(self, token: str) -> bool:
        payload = self._decode_jwt_payload_no_verify(token)
        scp = payload.get("scp")
        if isinstance(scp, str) and "materials" in scp:
            return True
        # Web成功ログで azp が material client を指していたため補助判定として使用
        azp = payload.get("azp")
        if isinstance(azp, str) and azp == "329b70945b2f4265945dad45d1bb8771":
            return True
        return False

    def _material_token_claims_summary(self, token: str) -> str:
        payload = self._decode_jwt_payload_no_verify(token)
        if not payload:
            return "(token claims: unknown)"
        scp = payload.get("scp")
        aud = payload.get("aud")
        azp = payload.get("azp")
        return f"(token claims: scp={scp!s}, aud={aud!s}, azp={azp!s})"

    def _add_material_cookies(self, headers: dict, browser_cookies: list) -> dict:
        try:
            from classes.subgroup.util.cookie_manager import CookieManager

            # Prefer API domain cookies; fall back to non-API domain cookies.
            cookies = CookieManager.get_cookies_for_domain(browser_cookies, "rde-material-api.nims.go.jp")
            if not cookies:
                cookies = CookieManager.get_cookies_for_domain(browser_cookies, "rde-material.nims.go.jp")
            if cookies:
                return CookieManager.add_cookies_to_headers(headers, cookies)
        except Exception:
            return headers
        return headers

    def _build_material_headers(self, *, material_token: str, browser_cookies: list | None = None, with_content_type: bool = False) -> dict:
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {material_token}",
            "Connection": "keep-alive",
            "Host": "rde-material-api.nims.go.jp",
            "Origin": "https://rde-material.nims.go.jp",
            "Referer": "https://rde-material.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        if with_content_type:
            headers["Content-Type"] = "application/vnd.api+json"
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)
        return headers
    
    def create_subgroup(self, payload, group_name, auto_refresh=True):
        """
        サブグループ作成API呼び出し
        
        Args:
            payload (dict): APIペイロード
            group_name (str): グループ名（メッセージ用）
            auto_refresh (bool): 成功時の自動リフレッシュ有効/無効
            
        Returns:
            bool: 作成成功かどうか
        """
        if not self.authenticate():
            return False
        
        api_url = f"{self.api_base_url}/groups"
        headers = self._build_headers()
        
        try:
            from net.http_helpers import proxy_post
            resp = proxy_post(api_url, headers=headers, json=payload, timeout=15)
            return self._handle_response(resp, group_name, "作成", auto_refresh)
        except Exception as e:
            QMessageBox.warning(self.widget, "APIエラー", f"API送信中にエラーが発生しました: {e}")
            return False
    
    def update_subgroup(self, group_id, payload, group_name, auto_refresh=True):
        """
        サブグループ更新API呼び出し
        
        Args:
            group_id (str): グループID
            payload (dict): APIペイロード
            group_name (str): グループ名（メッセージ用）
            auto_refresh (bool): 成功時の自動リフレッシュ有効/無効
            
        Returns:
            bool: 更新成功かどうか
        """
        logger.debug("update_subgroup() 開始 - group_id=%s", group_id)
        if not self.authenticate():
            logger.debug("認証失敗")
            return False
        
        logger.debug("認証成功、RDEトークン使用: %s...", self.bearer_token[:20] if self.bearer_token else 'None')
        api_url = f"{self.api_base_url}/groups/{group_id}"
        logger.debug("API呼び出し: %s", api_url)
        headers = self._build_headers()
        
        try:
            from net.http_helpers import proxy_patch
            logger.debug("proxy_patch() 呼び出し中...")
            resp = proxy_patch(api_url, headers=headers, json=payload, timeout=15)
            logger.debug("API レスポンス: status_code=%s", resp.status_code)
            return self._handle_response(resp, group_name, "更新", auto_refresh)
        except Exception as e:
            logger.error("API送信エラー: %s", e)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self.widget, "APIエラー", f"API送信中にエラーが発生しました: {e}")
            return False
    
    def _build_headers(self):
        """標準HTTPヘッダーの構築"""
        return {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {self.bearer_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    
    def _handle_response(self, response, group_name, operation, auto_refresh):
        """APIレスポンスのハンドリング"""
        if response.status_code in (200, 201):
            # 成功時にsubGroup.jsonを即座に自動再取得（スキップなし）
            refresh_success = False
            if auto_refresh:
                try:
                    from classes.basic.core.basic_info_logic import auto_refresh_subgroup_json
                    from classes.utils.progress_worker import SimpleProgressWorker
                    from classes.basic.ui.ui_basic_info import show_progress_dialog
                    
                    logger.info("サブグループ%s成功 - subGroup.json即座に再取得開始", operation)
                    
                    # プログレス表示付きで自動更新（即座に実行）
                    worker = SimpleProgressWorker(
                        task_func=auto_refresh_subgroup_json,
                        task_kwargs={'bearer_token': self.bearer_token, 'force_refresh_subgroup': True},
                        task_name="サブグループ情報更新"
                    )
                    
                    # プログレス表示（ブロッキング実行）
                    progress_dialog = show_progress_dialog(self.widget, "サブグループ情報更新中", worker)
                    
                    refresh_success = True
                    logger.info("サブグループ情報自動更新完了")
                    
                    # サブグループ更新通知を送信
                    try:
                        from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
                        subgroup_notifier = get_subgroup_refresh_notifier()
                        from qt_compat.core import QTimer
                        def send_notification():
                            try:
                                subgroup_notifier.notify_refresh()
                                logger.info("サブグループ更新通知を送信しました")
                            except Exception as e:
                                logger.warning("サブグループ更新通知送信に失敗: %s", e)
                        QTimer.singleShot(500, send_notification)  # 0.5秒後に通知
                    except Exception as e:
                        logger.warning("サブグループ更新通知の設定に失敗: %s", e)
                    
                except Exception as e:
                    logger.error("サブグループ情報自動更新でエラー: %s", e)
                    QMessageBox.warning(
                        self.widget, 
                        f"{operation}警告", 
                        f"サブグループ[{group_name}]の{operation}には成功しましたが、\nsubGroup.jsonの自動更新に失敗しました。\n\n"
                        f"基本情報タブで手動更新を実行してください。\n\nエラー: {e}"
                    )
                    # エラー時のみメッセージ表示（通常は自動更新のプログレスダイアログで完結）
            
            return True
        else:
            QMessageBox.warning(
                self.widget, 
                f"{operation}失敗", 
                f"サブグループ[{group_name}]の{operation}に失敗しました。\n\n"
                f"Status: {response.status_code}\n{response.text}"
            )
            return False
    

    
    def get_sample_detail(self, sample_id):
        """
        試料詳細情報を取得（共有グループ情報を含む）
        
        Args:
            sample_id (str): 試料ID
            
        Returns:
            dict: 試料詳細情報、エラー時はNone
        """
        logger.debug("get_sample_detail() 開始 - sample_id=%s", sample_id)
        
        api_url = (
            f"https://rde-material-api.nims.go.jp/samples/{sample_id}"
            "?include=owner%2CsharingGroups%2CowningGroup"
            "&fields%5Buser%5D=userName%2CorganizationName%2CisDeleted"
        )
        logger.debug("API呼び出し: %s", api_url)
        
        # v2.1.0: WebViewのCookieを取得
        browser_cookies = []
        try:
            if self.browser and hasattr(self.browser, 'cookies'):
                browser_cookies = self.browser.cookies
                logger.debug("WebView Cookie取得: %s個", len(browser_cookies))
        except Exception as e:
            logger.warning("WebView Cookie取得失敗: %s", e)
        
        material_token = self._load_material_token()
        if not material_token:
            logger.warning("Materialトークンが見つかりません（get_sample_detail）")
        headers = {"Accept": "application/vnd.api+json"}
        if material_token:
            headers = self._build_material_headers(material_token=material_token, browser_cookies=None, with_content_type=False)
        
        # v2.1.0: WebViewのCookieをヘッダーに追加
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)
        
        try:
            from net.http_helpers import proxy_get
            logger.debug("proxy_get() 呼び出し中...")
            response = proxy_get(api_url, headers=headers)
            logger.debug("API レスポンス: status_code=%s", response.status_code)
            
            if response.status_code == 200:
                logger.debug("試料詳細取得成功")
                return response.json()
            else:
                logger.error("試料詳細取得エラー (Status: %s)", response.status_code)
                logger.debug("レスポンス内容: %s", response.text[:200])
                return None
                
        except Exception as e:
            logger.error("API呼び出しエラー: %s", str(e))
            import traceback
            traceback.print_exc()
            return None

    def update_sample_payload(self, sample_id: str, payload: dict) -> tuple[bool, str]:
        """試料情報を更新（Material API）。

        - Web UIではなくAPIで更新する。
        - payload はユーザーがHTML/通信ログを参考に作成したJSONをそのまま送信する。
        - まず PATCH を試し、405 等の場合のみ POST をフォールバックする。
        """
        sid = str(sample_id or "").strip()
        if not sid:
            return False, "sample_id が空です"
        if not isinstance(payload, dict):
            return False, "payload が dict ではありません"

        logger.debug("update_sample_payload() 開始 - sample_id=%s", sid)

        browser_cookies = []
        try:
            if self.browser and hasattr(self.browser, 'cookies'):
                browser_cookies = self.browser.cookies
        except Exception:
            browser_cookies = []

        api_url = f"https://rde-material-api.nims.go.jp/samples/{sid}"
        material_token = self._load_material_token()
        if not material_token:
            logger.warning("Materialトークンが見つかりません（update_sample_payload）")
        else:
            try:
                logger.info("[TOKEN] Material token selected for update_sample_payload %s", self._material_token_claims_summary(material_token))
            except Exception:
                pass
        headers = {
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }
        if material_token:
            headers = self._build_material_headers(
                material_token=material_token,
                browser_cookies=None,
                with_content_type=True,
            )
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)

        try:
            from net.http_helpers import proxy_patch, proxy_post

            logger.debug("PATCH Sample API URL: %s", api_url)
            logger.debug("ペイロード: %s", json.dumps(payload, ensure_ascii=False, indent=2)[:2000])
            resp = proxy_patch(api_url, headers=headers, json=payload)

            # 成功系: 200(本文あり) / 204(本文なし)
            if resp.status_code in (200, 204):
                return True, "OK"

            # ユーザー要望: POSTの場合があるためフォールバック
            if resp.status_code in (405, 404):
                logger.debug("PATCH not accepted (status=%s). Trying POST fallback...", resp.status_code)
                resp2 = proxy_post(api_url, headers=headers, json=payload)
                if resp2.status_code in (200, 201, 204):
                    return True, "OK"
                return False, f"POST失敗 (Status: {resp2.status_code})\n{resp2.text}"

            # それ以外
            msg = f"更新失敗 (Status: {resp.status_code})"
            try:
                www_auth = resp.headers.get("www-authenticate")
                if www_auth:
                    msg += f"\nwww-authenticate: {www_auth}"
            except Exception:
                pass
            if material_token:
                try:
                    msg += f"\n{self._material_token_claims_summary(material_token)}"
                except Exception:
                    pass
            try:
                msg += f"\n{resp.text}"
            except Exception:
                pass
            return False, msg

        except Exception as e:
            logger.error("Material API update error: %s", str(e))
            return False, f"API呼び出しエラー: {e}"

    def get_sample_terms(self, *, for_general_use: bool = True) -> list[dict] | None:
        """試料項目定義(sampleTerms)を取得。"""
        flag = "true" if for_general_use else "false"
        api_url = f"https://rde-material-api.nims.go.jp/sampleTerms?forGeneralUse={flag}"

        browser_cookies = []
        try:
            if self.browser and hasattr(self.browser, 'cookies'):
                browser_cookies = self.browser.cookies
        except Exception:
            browser_cookies = []

        material_token = self._load_material_token()
        headers = {"Accept": "application/vnd.api+json"}
        if material_token:
            headers = self._build_material_headers(material_token=material_token, browser_cookies=None, with_content_type=False)
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)

        try:
            from net.http_helpers import proxy_get

            resp = proxy_get(api_url, headers=headers)
            if resp.status_code != 200:
                logger.error("sampleTerms取得失敗 (Status: %s)", resp.status_code)
                return None
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            return data if isinstance(data, list) else None
        except Exception as e:
            logger.error("sampleTerms取得例外: %s", e)
            return None

    def get_sample_classes(self) -> list[dict] | None:
        """試料分類(sampleClasses)を取得（terms含む）。"""
        api_url = "https://rde-material-api.nims.go.jp/sampleClasses?include=terms"

        browser_cookies = []
        try:
            if self.browser and hasattr(self.browser, 'cookies'):
                browser_cookies = self.browser.cookies
        except Exception:
            browser_cookies = []

        material_token = self._load_material_token()
        headers = {"Accept": "application/vnd.api+json"}
        if material_token:
            headers = self._build_material_headers(material_token=material_token, browser_cookies=None, with_content_type=False)
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)

        try:
            from net.http_helpers import proxy_get

            resp = proxy_get(api_url, headers=headers)
            if resp.status_code != 200:
                logger.error("sampleClasses取得失敗 (Status: %s)", resp.status_code)
                return None
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            return data if isinstance(data, list) else None
        except Exception as e:
            logger.error("sampleClasses取得例外: %s", e)
            return None
    
    def set_sample_sharing_group(self, sample_id, sharing_group_id, sharing_group_name):
        """
        試料に共有グループを設定
        
        Args:
            sample_id (str): 試料ID
            sharing_group_id (str): 共有グループID
            sharing_group_name (str): 共有グループ名
            
        Returns:
            tuple: (success: bool, message: str)
        """
        # Material API用のトークンを取得
        logger.debug("set_sample_sharing_group() 開始 - sample_id=%s", sample_id)
        logger.debug("Material API用トークン取得中...")
        # Material APIトークンを取得
        material_token = self._load_material_token()
        
        if not material_token:
            logger.error("Material APIトークンが取得できません")
            return False, "Material APIトークンが取得できません"
        
        logger.debug("Material トークン取得成功: %s...", material_token[:20])
        
        # トークン検証
        logger.debug("Material トークン検証中...")
        is_valid = BearerTokenManager.validate_token(material_token)
        logger.debug("Material トークン検証結果: %s", '有効' if is_valid else '無効')
        
        if not is_valid:
            logger.error("Material APIトークンが無効です")
            return False, "Material APIトークンが無効です"
        
        # v2.1.0: WebViewのCookieを取得してリクエストに含める
        logger.debug("WebViewのCookieを取得中...")
        browser_cookies = []
        try:
            # Browserインスタンスからcookiesを取得
            if self.browser and hasattr(self.browser, 'cookies'):
                browser_cookies = self.browser.cookies
                logger.debug("WebView Cookie取得: %s個", len(browser_cookies))
            else:
                logger.warning("Browserインスタンスが設定されていません")
        except Exception as e:
            logger.warning("WebView Cookie取得失敗: %s", e)
        
        api_url = f"https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups"
        logger.debug("API呼び出し: %s", api_url)
        
        payload = {
            "data": [{
                "type": "sharingGroup",
                "id": sharing_group_id,
                "meta": {
                    "name": sharing_group_name
                }
            }]
        }
        
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {material_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-material-api.nims.go.jp",
            "Origin": "https://rde-entry-arim.nims.go.jp",
            "Referer": "https://rde-entry-arim.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        
        # v2.1.0: WebViewのCookieをヘッダーに追加
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)
        else:
            logger.warning("WebView Cookieが利用できません - Cookieなしでリクエスト")
        
        logger.debug("POST Sample Sharing Group API URL: %s", api_url)
        logger.debug("ペイロード: %s", json.dumps(payload, ensure_ascii=False, indent=2))
        
        try:
            from net.http_helpers import proxy_post
            logger.debug("proxy_post() 呼び出し中...")
            response = proxy_post(api_url, headers=headers, json=payload)
            logger.debug("API レスポンス: status_code=%s", response.status_code)
            
            if response.status_code == 204:
                logger.info("試料共有グループ設定成功: sample_id=%s, group=%s", sample_id, sharing_group_name)
                return True, f"試料に共有グループ「{sharing_group_name}」を設定しました"
            else:
                error_msg = f"API エラー (Status: {response.status_code})"
                try:
                    error_detail = response.json()
                    error_msg += f"\n詳細: {json.dumps(error_detail, ensure_ascii=False, indent=2)}"
                except:
                    error_msg += f"\n応答: {response.text}"
                try:
                    www_auth = response.headers.get("www-authenticate")
                    if www_auth:
                        error_msg += f"\nwww-authenticate: {www_auth}"
                except Exception:
                    pass
                logger.error("%s", error_msg)
                logger.debug("レスポンス内容: %s", response.text[:200])
                return False, error_msg
                
        except Exception as e:
            error_msg = f"API呼び出しエラー: {str(e)}"
            logger.error("%s", error_msg)
            return False, error_msg
    
    def delete_sample_sharing_group(self, sample_id, sharing_group_id):
        """
        試料から共有グループを削除
        
        Args:
            sample_id (str): 試料ID
            sharing_group_id (str): 共有グループID
            
        Returns:
            tuple: (success: bool, message: str)
        """
        # Material API用のトークンを取得
        material_token = self._load_material_token()
        
        if not material_token:
            return False, "Material APIトークンが取得できません"
        
        api_url = f"https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups"
        
        payload = {
            "data": [{
                "type": "sharingGroup",
                "id": sharing_group_id
            }]
        }
        
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {material_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-material-api.nims.go.jp",
            "Origin": "https://rde-entry-arim.nims.go.jp",
            "Referer": "https://rde-entry-arim.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }

        # v2.1.0: WebViewのCookieをヘッダーに追加
        browser_cookies = []
        try:
            if self.browser and hasattr(self.browser, 'cookies'):
                browser_cookies = self.browser.cookies
        except Exception:
            browser_cookies = []
        if browser_cookies:
            headers = self._add_material_cookies(headers, browser_cookies)
        
        logger.debug("DELETE Sample Sharing Group API URL: %s", api_url)
        logger.debug("ペイロード: %s", json.dumps(payload, ensure_ascii=False, indent=2))
        
        try:
            from net.http_helpers import proxy_delete
            response = proxy_delete(api_url, headers=headers, json=payload)
            
            if response.status_code == 204:
                logger.info("試料共有グループ削除成功: sample_id=%s", sample_id)
                return True, "試料から共有グループを削除しました"
            else:
                error_msg = f"API エラー (Status: {response.status_code})"
                try:
                    error_detail = response.json()
                    error_msg += f"\n詳細: {json.dumps(error_detail, ensure_ascii=False, indent=2)}"
                except:
                    error_msg += f"\n応答: {response.text}"
                try:
                    www_auth = response.headers.get("www-authenticate")
                    if www_auth:
                        error_msg += f"\nwww-authenticate: {www_auth}"
                except Exception:
                    pass
                logger.error("%s", error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"API呼び出しエラー: {str(e)}"
            logger.error("%s", error_msg)
            return False, error_msg


class SubgroupPayloadBuilder:
    """サブグループAPIペイロード構築クラス"""
    
    @staticmethod
    def create_payload(group_name, description, subjects, funds, roles, parent_id):
        """
        新規作成用ペイロードの構築
        
        Args:
            group_name (str): グループ名
            description (str): 説明
            subjects (list): 課題リスト [{"grantNumber": "", "title": ""}, ...]
            funds (list): 研究資金リスト [str, ...]
            roles (list): ロールリスト [{"userId": "", "role": "", ...}, ...]
            parent_id (str): 親グループID
            
        Returns:
            dict: APIペイロード
        """
        # 研究資金をAPIフォーマットに変換
        formatted_funds = [{"fundNumber": f} for f in funds if f.strip()]
        
        return {
            "data": {
                "type": "group",
                "attributes": {
                    "name": group_name,
                    "description": description,
                    "subjects": subjects,
                    "funds": formatted_funds,
                    "roles": roles
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": parent_id
                        }
                    }
                }
            }
        }
    
    @staticmethod
    def update_payload(group_id, group_name, description, subjects, funds, roles, parent_id):
        """
        更新用ペイロードの構築（PATCH用）
        
        Args:
            group_id (str): グループID
            group_name (str): グループ名
            description (str): 説明
            subjects (list): 課題リスト
            funds (list): 研究資金リスト
            roles (list): ロールリスト
            parent_id (str): 親グループID
            
        Returns:
            dict: APIペイロード
        """
        # 研究資金をAPIフォーマットに変換
        formatted_funds = [{"fundNumber": f} for f in funds if f.strip()]
        
        return {
            "data": {
                "type": "group",
                "id": group_id,
                "attributes": {
                    "name": group_name,
                    "description": description,
                    "subjects": subjects,
                    "funds": formatted_funds,
                    "roles": roles
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": parent_id
                        }
                    }
                }
            }
        }
    
    @staticmethod
    def build_request_info(payload, group_name, operation_type="作成"):
        """
        リクエスト情報文字列の構築（確認ダイアログ用）
        
        Args:
            payload (dict): APIペイロード
            group_name (str): グループ名
            operation_type (str): 操作タイプ（"作成" または "更新"）
            
        Returns:
            str: リクエスト情報文字列
        """
        attr = payload['data']['attributes']
        
        # ロール日本語訳マッピング
        role_translation = {
            'OWNER': '管理者',
            'ASSISTANT': '代理',
            'MEMBER': 'メンバ',
            'AGENT': '登録代行',
            'VIEWER': '閲覧'
        }
        
        # ユーザー名キャッシュから取得
        from classes.subgroup.core.user_cache_manager import UserCacheManager
        cache_manager = UserCacheManager.instance()
        
        # ロール情報の簡易表示（氏名 + 日本語ロール）
        role_summary = []
        for role in attr.get('roles', []):
            user_id = role.get('userId', '')
            role_name = role.get('role', '')
            
            # ユーザー名をキャッシュから取得
            user_info = cache_manager.get_user(user_id)
            if user_info and user_info.get('userName'):
                display_name = user_info['userName']
            else:
                # キャッシュにない場合はIDを表示
                display_name = user_id[:10] + "..." if len(user_id) > 10 else user_id
            
            # ロールを日本語化
            role_jp = role_translation.get(role_name, role_name)
            
            role_summary.append(f"  {display_name}({role_jp})")
        
        # メンバー表示（全員を改行で表示）
        members_text = "\n".join(role_summary) if role_summary else "  なし"
        
        return (
            f"本当にサブグループを{operation_type}しますか？\n\n"
            f"グループ名: {attr.get('name')}\n"
            f"説明: {attr.get('description')}\n"
            f"課題数: {len(attr.get('subjects', []))}\n"
            f"研究資金数: {len(attr.get('funds', []))}\n"
            f"メンバー数: {len(attr.get('roles', []))}\n"
            f"メンバー:\n{members_text}\n"
            f"\nこの操作はRDEでサブグループを{operation_type}します。"
        )
    
    
    @staticmethod
    def build_detailed_request_info(payload, api_url):
        """
        詳細リクエスト情報の構築（デバッグ・詳細表示用）
        
        Args:
            payload (dict): APIペイロード
            api_url (str): API URL
            
        Returns:
            str: 詳細リクエスト情報
        """
        headers_dict = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer <YOUR_BEARER_TOKEN>",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        
        header_order = [
            "Accept", "Accept-Encoding", "Accept-Language", "Authorization", "Connection",
            "Content-Type", "Host", "Origin", "Referer", "Sec-Fetch-Dest", "Sec-Fetch-Mode",
            "Sec-Fetch-Site", "User-Agent", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"
        ]
        headers_str = '\n'.join([f'{k}: {headers_dict[k]}' for k in header_order if k in headers_dict])
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        
        return (
            f"Request URL\n{api_url}\nRequest Method\nPOST\n\n"
            f"POST /groups HTTP/1.1\n{headers_str}\n\n{payload_str}"
        )


# 後方互換性のための関数群（既存コードとの互換性維持）

def send_subgroup_request(widget, api_url, headers, payload, group_name, auto_refresh=True):
    """
    後方互換性のためのサブグループリクエスト送信関数
    """
    client = SubgroupApiClient(widget)
    if "groups" in api_url and headers.get("Authorization"):
        # 新規作成の場合
        return client.create_subgroup(payload, group_name, auto_refresh)
    else:
        # その他の場合（要実装）
        logger.warning("未対応のAPIリクエスト: %s", api_url)
        return False


def create_subgroup_payload(group_name, description, subjects, funds, roles, parent_id):
    """
    後方互換性のためのペイロード作成関数
    """
    return SubgroupPayloadBuilder.create_payload(
        group_name, description, subjects, funds, roles, parent_id
    )


def build_subgroup_request(info, group_config, member_lines, idx, group, selected_user_ids=None, roles=None):
    """
    後方互換性のためのリクエスト構築関数（一括作成用）
    """
    # 既存の実装を維持（将来的にはSubgroupPayloadBuilderに統合予定）
    raw_subjects = group.get("subjects", [])
    subjects = []
    for s in raw_subjects:
        if isinstance(s, dict):
            grant_number = s.get("grantNumber")
            title = s.get("title")
            if not grant_number and not title:
                continue
            if not grant_number:
                grant_number = title
            if not title:
                title = grant_number
            subjects.append({"grantNumber": grant_number, "title": title})
        else:
            grant_number = str(s)
            subjects.append({"grantNumber": grant_number, "title": grant_number})
    
    raw_funds = group.get("funds", [])
    funds = []
    for f in raw_funds:
        if isinstance(f, dict):
            fund_number = f.get("fundNumber")
            if fund_number:
                funds.append({"fundNumber": fund_number})
        else:
            fund_number = str(f)
            if fund_number:
                funds.append({"fundNumber": fund_number})
    
    # rolesが提供されていればそれを使用、なければ旧方式
    if roles:
        payload_roles = roles
    elif selected_user_ids:
        payload_roles = []
        for user_id in selected_user_ids:
            payload_roles.append({
                "userId": user_id,
                "role": "OWNER",
                "canCreateDatasets": True,
                "canEditMembers": True
            })
    else:
        payload_roles = []
    
    parent_id = info.get("project_group_id", "")
    payload = {
        "data": {
            "type": "group",
            "attributes": {
                "name": group.get("group_name", ""),
                "description": group.get("description", ""),
                "subjects": subjects,
                "funds": funds,
                "roles": payload_roles
            },
            "relationships": {
                "parent": {
                    "data": {
                        "type": "group",
                        "id": parent_id
                    }
                }
            }
        }
    }
    
    api_url = "https://rde-api.nims.go.jp/groups"
    return SubgroupPayloadBuilder.build_detailed_request_info(payload, api_url), payload, api_url, {}
