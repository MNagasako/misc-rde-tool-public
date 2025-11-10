"""
CookieManager - WebViewのCookieをHTTPリクエストに統合

Material APIなどのリクエスト時に、WebViewで取得したセッションCookieを
requestsライブラリのリクエストに含めるためのユーティリティ

v2.1.0: Material API 403エラー対策のため新規作成
"""

import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class CookieManager:
    """WebViewのCookieをHTTPリクエストに統合するクラス"""
    
    @staticmethod
    def get_cookies_for_domain(browser_cookies: List[Tuple[str, str, str]], 
                                target_domain: str) -> Dict[str, str]:
        """
        指定ドメインのCookieを取得してdict形式で返す
        
        Args:
            browser_cookies: Browserクラスのcookiesリスト [(domain, name, value), ...]
            target_domain: 取得対象ドメイン（例: "rde-material.nims.go.jp"）
            
        Returns:
            dict: Cookie名と値のマッピング {"name": "value", ...}
        """
        cookies = {}
        
        if not browser_cookies:
            logger.warning(f"[CookieManager] Cookieリストが空です")
            return cookies
        
        for domain, name, value in browser_cookies:
            # ドメイン完全一致または親ドメイン一致
            if domain == target_domain or target_domain.endswith(domain.lstrip('.')):
                cookies[name] = value
                logger.debug(f"[CookieManager] Cookie取得: {name}={value[:20]}... (domain={domain})")
        
        logger.info(f"[CookieManager] {target_domain}用Cookie取得完了: {len(cookies)}個")
        return cookies
    
    @staticmethod
    def add_cookies_to_headers(headers: Dict[str, str], 
                                 cookies: Dict[str, str]) -> Dict[str, str]:
        """
        HTTPヘッダーにCookieを追加
        
        Args:
            headers: 既存のHTTPヘッダー
            cookies: 追加するCookie {"name": "value", ...}
            
        Returns:
            dict: Cookie付きヘッダー
        """
        if not cookies:
            return headers
        
        # Cookie文字列を生成
        cookie_str = "; ".join([f"{name}={value}" for name, value in cookies.items()])
        
        # 既存のCookieヘッダーがある場合はマージ
        if "Cookie" in headers:
            headers["Cookie"] = f"{headers['Cookie']}; {cookie_str}"
        else:
            headers["Cookie"] = cookie_str
        
        logger.info(f"[CookieManager] HTTPヘッダーにCookie追加完了: {len(cookies)}個")
        return headers
