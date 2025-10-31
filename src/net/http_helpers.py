"""
HTTP ヘルパー関数
セッション管理ベースのHTTP操作を提供

このモジュールは net.http の代替として、循環参照を回避しつつ
プロキシ対応HTTPリクエストを提供します。
"""

from .session_manager import get_proxy_session
from typing import Dict, Optional, Any, Union
import requests  # 型ヒント用のみ

def proxy_get(url: str, **kwargs) -> requests.Response:
    """
    プロキシ対応 GET リクエスト
    
    Args:
        url: リクエストURL
        **kwargs: requests.get() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.get(url, **kwargs)

def proxy_post(url: str, data: Optional[Union[Dict, str, bytes]] = None,
               json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 POST リクエスト
    
    Args:
        url: リクエストURL
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.post() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.post(url, data=data, json=json, **kwargs)

def proxy_put(url: str, data: Optional[Union[Dict, str, bytes]] = None,
              json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 PUT リクエスト
    
    Args:
        url: リクエストURL
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.put() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.put(url, data=data, json=json, **kwargs)

def proxy_patch(url: str, data: Optional[Union[Dict, str, bytes]] = None,
                json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 PATCH リクエスト
    
    Args:
        url: リクエストURL  
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.patch() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.patch(url, data=data, json=json, **kwargs)

def proxy_delete(url: str, data: Optional[Union[Dict, str, bytes]] = None,
                 json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 DELETE リクエスト
    
    Args:
        url: リクエストURL
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.delete() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.delete(url, data=data, json=json, **kwargs)

def proxy_head(url: str, **kwargs) -> requests.Response:
    """
    プロキシ対応 HEAD リクエスト
    
    Args:
        url: リクエストURL
        **kwargs: requests.head() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.head(url, **kwargs)

def proxy_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    プロキシ対応汎用HTTPリクエスト
    
    Args:
        method: HTTPメソッド (GET, POST, PUT, etc.)
        url: リクエストURL
        **kwargs: requests.request() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    return session.request(method, url, **kwargs)

# ============================================================================
# 便利な設定関数
# ============================================================================

def add_auth_header(headers: Optional[Dict[str, str]] = None, 
                   bearer_token: Optional[str] = None,
                   api_key: Optional[str] = None,
                   url: Optional[str] = None) -> Dict[str, str]:
    """
    認証ヘッダーを追加（複数ホスト対応 v1.18.3+）
    
    Args:
        headers: 既存のヘッダー辞書
        bearer_token: Bearerトークン（指定しない場合はURLから自動選択）
        api_key: APIキー
        url: リクエスト先URL（トークン自動選択時に使用）
        
    Returns:
        Dict[str, str]: 認証ヘッダー付きの辞書
    """
    if headers is None:
        headers = {}
    
    headers = headers.copy()
    
    # bearer_tokenが指定されていない場合、URLから自動選択
    if not bearer_token and url:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
        except Exception:
            pass  # 自動選択失敗時は何もしない
    
    if bearer_token:
        headers['Authorization'] = f'Bearer {bearer_token}'
    elif api_key:
        headers['X-API-Key'] = api_key
    
    return headers

def create_json_headers(additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    JSON用のヘッダーを作成
    
    Args:
        additional_headers: 追加ヘッダー
        
    Returns:
        Dict[str, str]: JSON用ヘッダー
    """
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    if additional_headers:
        headers.update(additional_headers)
    
    return headers
