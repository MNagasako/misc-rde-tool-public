"""
HTTP リクエスト共通化ヘルパーモジュール v2
セッション管理ベースでプロキシ対応HTTPリクエストを提供
循環参照を回避した安全な設計
"""
# === セッション管理ベースのプロキシ対応 ===
from net.session_manager import get_proxy_session
import requests as _requests_types  # 型ヒント専用
import logging
from typing import Dict, Optional, Any, Union
from datetime import datetime
import json

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
    内部共通リクエスト処理関数（セッション管理ベース）
    
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
        
        # デフォルトヘッダー設定
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        if headers:
            default_headers.update(headers)
        
        # セッション管理ベースのリクエスト実行
        session = get_proxy_session()
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
        
        # ログ出力
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(logging.INFO, f"HTTP {method.upper()} {url} -> {response.status_code} ({elapsed_time:.2f}s)")
        else:
            logger.info(f"HTTP {method.upper()} {url} -> {response.status_code} ({elapsed_time:.2f}s)")
        
        return response
        
    except _requests_types.exceptions.Timeout:
        error_msg = f"HTTP Timeout: {method.upper()} {url} (timeout={timeout}s)"
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None
        
    except _requests_types.exceptions.ConnectionError:
        error_msg = f"HTTP Connection Error: {method.upper()} {url}"
        if hasattr(logger, 'log') and logger.__class__.__name__ == 'DebugLog':
            logger.log(f"[ERROR] {error_msg}", "ERROR")
        elif hasattr(logger, 'log'):
            logger.log(logging.ERROR, f"[ERROR] {error_msg}")
        else:
            logger.error(f"[ERROR] {error_msg}")
        return None
        
    except Exception as e:
        error_msg = f"HTTP Request Error: {method.upper()} {url}, error={str(e)}"
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
    JSON API リクエスト用共通関数（セッション管理ベース）
    
    Args:
        method: HTTPメソッド
        url: リクエストURL
        bearer_token: Bearerトークン
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
    ストリーミングリクエスト用関数（セッション管理ベース）
    
    Args:
        method: HTTPメソッド
        url: リクエストURL
        bearer_token: Bearerトークン
        timeout: タイムアウト秒数
        headers: カスタムヘッダー
        stream: ストリーミングモード
        
    Returns:
        _requests_types.Response または None
    """
    request_headers = {}
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
    ダウンロード用リクエスト関数（セッション管理ベース）
    
    Args:
        url: ダウンロードURL
        bearer_token: Bearerトークン
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
    フォームデータ POST リクエスト用関数（セッション管理ベース）
    
    Args:
        url: リクエストURL
        data: フォームデータ
        bearer_token: Bearerトークン
        headers: カスタムヘッダー
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    request_headers = {}
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
    バイナリデータ POST リクエスト用関数（セッション管理ベース）
    
    Args:
        url: リクエストURL
        data: バイナリデータ
        bearer_token: Bearerトークン
        content_type: Content-Type ヘッダー
        headers: カスタムヘッダー
        timeout: タイムアウト秒数
        
    Returns:
        _requests_types.Response または None
    """
    request_headers = {
        'Content-Type': content_type
    }
    
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
