"""
HTTP リクエスト共通化ヘルパーモジュール v2
セッション管理ベースでプロキシ対応HTTPリクエストを提供
循環参照を回避した安全な設計
"""
# === セッション管理ベースのプロキシ対応 ===
from net.session_manager import get_proxy_session, _session_manager
import requests as _requests_types  # 型ヒント専用
import logging
from typing import Dict, Optional, Any, Union
from datetime import datetime
import json
import time

# APIログ機能
try:
    from net import api_logger
    API_LOGGER_AVAILABLE = True
except ImportError:
    API_LOGGER_AVAILABLE = False

# デバッグログ用
try:
    from classes.utils.debug_log import DebugLog
    logger = DebugLog()
except ImportError:
    # フォールバック用の標準ロガー
    logger = logging.getLogger(__name__)


def _base_request(method: str, url: str, headers: Optional[Dict[str, str]] = None,
                 data: Optional[Union[Dict, str, bytes]] = None,
                 json_data: Optional[Dict] = None,
                 params: Optional[Dict[str, str]] = None,
                 timeout: int = 30,
                 stream: bool = False,
                 cookies: Optional[Dict] = None) -> Optional[_requests_types.Response]:
    """
    内部共通リクエスト処理関数（セッション管理ベース + APIログ統合）
    
    Args:
        method: HTTPメソッド (GET, POST, PUT, DELETE等)
        url: リクエストURL
        headers: リクエストヘッダー
        data: フォームデータまたはバイナリデータ
        json_data: JSONデータ
        params: URLパラメータ
        timeout: タイムアウト秒数
        stream: ストリーミングモード
        cookies: Cookie辞書
        
    Returns:
        _requests_types.Response または None (エラー時)
    """
    try:
        start_time = datetime.now()
        start_time_perf = time.time()  # APIログ用の高精度タイマー
        
        # デフォルトヘッダー設定
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        if headers:
            default_headers.update(headers)
        
        # セッション管理ベースのリクエスト実行
        session = get_proxy_session()
        
        # APIログ記録（リクエスト開始）
        if API_LOGGER_AVAILABLE:
            proxies = session.proxies or {}
            verify = session.verify
            truststore_enabled = hasattr(_session_manager, '_truststore_ssl_context') and _session_manager._truststore_ssl_context is not None
            
            api_logger.log_request(
                method=method.upper(),
                url=url,
                proxies=proxies,
                verify=verify,
                ssl_context_used=truststore_enabled,
                truststore_enabled=truststore_enabled
            )
        
        response = session.request(
            method=method,
            url=url,
            headers=default_headers,
            data=data,
            json=json_data,
            params=params,
            timeout=timeout,
            stream=stream,
            cookies=cookies
        )
        
        # パフォーマンス計測
        elapsed_time = (datetime.now() - start_time).total_seconds()
        elapsed_ms = (time.time() - start_time_perf) * 1000
        
        # APIログ記録（レスポンス）
        if API_LOGGER_AVAILABLE:
            api_logger.log_response(
                method=method.upper(),
                url=url,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                success=True
            )
        
        # デバッグログ出力
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(logging.INFO, f"HTTP {method.upper()} {url} -> {response.status_code} ({elapsed_time:.2f}s)")
        else:
            logger.info(f"HTTP {method.upper()} {url} -> {response.status_code} ({elapsed_time:.2f}s)")
        
        return response
        
    except _requests_types.exceptions.Timeout:
        elapsed_ms = (time.time() - start_time_perf) * 1000 if 'start_time_perf' in locals() else 0
        error_msg = f"HTTP Timeout: {method.upper()} {url} (timeout={timeout}s)"
        
        # APIログ記録（タイムアウト）
        if API_LOGGER_AVAILABLE:
            api_logger.log_response(
                method=method.upper(),
                url=url,
                status_code=0,
                elapsed_ms=elapsed_ms,
                success=False,
                error=f"Timeout ({timeout}s)"
            )
        
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None
        
    except _requests_types.exceptions.ConnectionError as e:
        elapsed_ms = (time.time() - start_time_perf) * 1000 if 'start_time_perf' in locals() else 0
        error_msg = f"HTTP Connection Error: {method.upper()} {url}"
        
        # APIログ記録（接続エラー）
        if API_LOGGER_AVAILABLE:
            api_logger.log_response(
                method=method.upper(),
                url=url,
                status_code=0,
                elapsed_ms=elapsed_ms,
                success=False,
                error=f"Connection Error: {str(e)[:100]}"
            )
        
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None
        
    except _requests_types.exceptions.SSLError as e:
        elapsed_ms = (time.time() - start_time_perf) * 1000 if 'start_time_perf' in locals() else 0
        error_msg = f"HTTP SSL Error: {method.upper()} {url}"
        
        # APIログ記録（SSLエラー）
        if API_LOGGER_AVAILABLE:
            api_logger.log_response(
                method=method.upper(),
                url=url,
                status_code=0,
                elapsed_ms=elapsed_ms,
                success=False,
                error=f"SSL Error: {str(e)[:100]}"
            )
            api_logger.log_ssl_verification_failure(url, str(e)[:200])
        
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None
        
    except _requests_types.exceptions.ProxyError as e:
        elapsed_ms = (time.time() - start_time_perf) * 1000 if 'start_time_perf' in locals() else 0
        error_msg = f"HTTP Proxy Error: {method.upper()} {url}"
        
        # APIログ記録（プロキシエラー）
        if API_LOGGER_AVAILABLE:
            session = get_proxy_session()
            proxies = session.proxies or {}
            
            api_logger.log_response(
                method=method.upper(),
                url=url,
                status_code=0,
                elapsed_ms=elapsed_ms,
                success=False,
                error=f"Proxy Error: {str(e)[:100]}"
            )
            
            proxy_url = proxies.get('https') or proxies.get('http')
            if proxy_url:
                api_logger.log_proxy_connection(proxy_url, False)
        
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None
    
    except Exception as e:
        elapsed_ms = (time.time() - start_time_perf) * 1000 if 'start_time_perf' in locals() else 0
        error_msg = f"HTTP Request Error: {method.upper()} {url}, error={str(e)}"
        
        # APIログ記録（汎用エラー）
        if API_LOGGER_AVAILABLE:
            api_logger.log_response(
                method=method.upper(),
                url=url,
                status_code=0,
                elapsed_ms=elapsed_ms,
                success=False,
                error=f"{type(e).__name__}: {str(e)[:100]}"
            )
        
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None


def api_request(method: str, url: str, bearer_token: Optional[str] = None,
               headers: Optional[Dict[str, str]] = None,
               json_data: Optional[Dict] = None,
               params: Optional[Dict[str, str]] = None,
               timeout: int = 30) -> Optional[_requests_types.Response]:
    """
    JSON API リクエスト用共通関数（セッション管理ベース・複数ホスト対応 v1.18.3+）
    
    Args:
        method: HTTPメソッド
        url: リクエストURL
        bearer_token: Bearerトークン（未指定時はURLから自動選択）
        headers: 追加ヘッダー
        json_data: JSONデータ
        params: URLパラメータ
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    # ヘッダー設定
    request_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    # bearer_tokenが指定されていない場合、URLから自動選択
    if not bearer_token:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
                    logger.log(logging.DEBUG, f"Bearer Token自動選択: {url[:50]}...")
                else:
                    logger.debug(f"Bearer Token自動選択: {url[:50]}...")
        except Exception as e:
            if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
                logger.log(logging.WARNING, f"Bearer Token自動選択失敗: {e}")
            else:
                logger.warning(f"Bearer Token自動選択失敗: {e}")
    
    if bearer_token:
        request_headers['Authorization'] = f'Bearer {bearer_token}'
    
    if headers:
        request_headers.update(headers)
    
    return _base_request(
        method=method,
        url=url,
        headers=request_headers,
        json_data=json_data,
        params=params,
        timeout=timeout
    )


def stream_request(method: str, url: str, bearer_token: Optional[str] = None,
                timeout: int = 30, headers: Optional[Dict[str, str]] = None, 
                stream: bool = True) -> Optional[_requests_types.Response]:
    """
    ストリーミングリクエスト用関数（セッション管理ベース・複数ホスト対応 v1.18.3+）
    
    Args:
        method: HTTPメソッド
        url: リクエストURL
        bearer_token: Bearerトークン（未指定時はURLから自動選択）
        timeout: タイムアウト秒数
        headers: カスタムヘッダー
        stream: ストリーミングモード
        
    Returns:
        _requests_types.Response または None
    """
    request_headers = {}
    
    # bearer_tokenが指定されていない場合、URLから自動選択
    if not bearer_token:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
        except Exception:
            pass
    
    if bearer_token:
        request_headers['Authorization'] = f'Bearer {bearer_token}'
    
    if headers:
        request_headers.update(headers)
    
    return _base_request(
        method=method,
        url=url,
        headers=request_headers,
        timeout=timeout,
        stream=stream
    )


def download_request(url: str, bearer_token: Optional[str] = None,
              timeout: int = 30, headers: Optional[Dict[str, str]] = None,
              stream: bool = True) -> Optional[_requests_types.Response]:
    """
    ダウンロード用リクエスト関数（セッション管理ベース・複数ホスト対応 v1.18.3+）
    
    Args:
        url: ダウンロードURL
        bearer_token: Bearerトークン（未指定時はURLから自動選択）
        timeout: タイムアウト秒数
        headers: カスタムヘッダー
        stream: ストリーミングモード
        
    Returns:
        _requests_types.Response または None
    """
    return stream_request('GET', url, bearer_token, timeout, headers, stream=stream)


def post_json_request(url: str, json_data: Dict[str, Any], bearer_token: Optional[str] = None,
             timeout: int = 30) -> Optional[_requests_types.Response]:
    """
    JSON POST リクエスト用関数（セッション管理ベース）
    
    Args:
        url: リクエストURL
        json_data: POSTするJSONデータ
        bearer_token: Bearerトークン
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    return api_request('POST', url, bearer_token, json_data=json_data, timeout=timeout)


def put_json_request(url: str, json_data: Dict[str, Any], bearer_token: Optional[str] = None,
               timeout: int = 30) -> Optional[_requests_types.Response]:
    """
    JSON PUT リクエスト用関数（セッション管理ベース）
    
    Args:
        url: リクエストURL
        json_data: PUTするJSONデータ
        bearer_token: Bearerトークン
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    return api_request('PUT', url, bearer_token, json_data=json_data, timeout=timeout)


def fetch_binary(url: str, bearer_token: Optional[str] = None,
                headers: Optional[Dict[str, str]] = None,
                timeout: int = 30, stream: bool = False) -> Optional[bytes]:
    """
    バイナリデータ取得用関数（セッション管理ベース）
    
    Args:
        url: リクエストURL
        bearer_token: Bearerトークン  
        headers: カスタムヘッダー
        timeout: タイムアウト秒数
        stream: ストリーミングモード
        
    Returns:
        bytes: バイナリデータ または None
    """
    try:
        response = download_request(url, bearer_token, timeout, headers, stream)
        if response and response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] バイナリデータ取得失敗: {url}, error={str(e)}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] バイナリデータ取得失敗: {url}, error={str(e)}")
        else:
            logger.error(f"[ERROR] バイナリデータ取得失敗: {url}, error={str(e)}")
        return None


def post_form(url: str, data: Dict[str, Any], bearer_token: Optional[str] = None,
             headers: Optional[Dict[str, str]] = None,
             timeout: int = 30) -> Optional[_requests_types.Response]:
    """
    フォームデータ POST リクエスト用関数（セッション管理ベース・複数ホスト対応 v1.18.4+）
    
    Args:
        url: リクエストURL
        data: フォームデータ
        bearer_token: Bearerトークン（未指定時はURLから自動選択）
        headers: カスタムヘッダー
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    request_headers = {}
    
    # bearer_tokenが指定されていない場合、URLから自動選択
    if not bearer_token:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
                    logger.log(logging.DEBUG, f"Bearer Token自動選択 (POST Form): {url[:50]}...")
                else:
                    logger.debug(f"Bearer Token自動選択 (POST Form): {url[:50]}...")
        except Exception as e:
            if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
                logger.log(f"[WARNING] Bearer Token自動選択エラー: {e}", "WARNING")
            elif hasattr(logger, 'log'):
                logger.log(logging.WARNING, f"[WARNING] Bearer Token自動選択エラー: {e}")
            else:
                logger.warning(f"[WARNING] Bearer Token自動選択エラー: {e}")
    
    if bearer_token:
        request_headers['Authorization'] = f'Bearer {bearer_token}'
    
    if headers:
        request_headers.update(headers)
    
    return _base_request(
        method='POST',
        url=url,
        headers=request_headers,
        data=data,
        timeout=timeout
    )


def post_binary(url: str, data: bytes, bearer_token: Optional[str] = None,
               content_type: str = 'application/octet-stream',
               headers: Optional[Dict[str, str]] = None,
               timeout: int = 30) -> Optional[_requests_types.Response]:
    """
    バイナリデータ POST リクエスト用関数（セッション管理ベース・複数ホスト対応 v1.18.4+）
    
    Args:
        url: リクエストURL
        data: バイナリデータ
        bearer_token: Bearerトークン（未指定時はURLから自動選択）
        content_type: Content-Type ヘッダー
        headers: カスタムヘッダー
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    request_headers = {
        'Content-Type': content_type
    }
    
    # bearer_tokenが指定されていない場合、URLから自動選択
    if not bearer_token:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
                    logger.log(logging.DEBUG, f"Bearer Token自動選択 (POST Binary): {url[:50]}...")
                else:
                    logger.debug(f"Bearer Token自動選択 (POST Binary): {url[:50]}...")
        except Exception as e:
            if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
                logger.log(f"[WARNING] Bearer Token自動選択エラー: {e}", "WARNING")
            elif hasattr(logger, 'log'):
                logger.log(logging.WARNING, f"[WARNING] Bearer Token自動選択エラー: {e}")
            else:
                logger.warning(f"[WARNING] Bearer Token自動選択エラー: {e}")
    
    if bearer_token:
        request_headers['Authorization'] = f'Bearer {bearer_token}'
    
    if headers:
        request_headers.update(headers)
    
    return _base_request(
        method='POST',
        url=url,
        headers=request_headers,
        data=data,
        timeout=timeout
    )
