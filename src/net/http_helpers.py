"""
HTTP ヘルパー関数
セッション管理ベースのHTTP操作を提供

このモジュールは net.http の代替として、循環参照を回避しつつ
プロキシ対応HTTPリクエストを提供します。
"""

from .session_manager import get_proxy_session, _session_manager
from typing import Dict, Optional, Any, Union
import requests  # 型ヒント用のみ
import time
from . import api_logger

def _log_and_execute(method: str, url: str, session: requests.Session, **kwargs) -> requests.Response:
    """
    APIリクエストをログ記録して実行
    
    Args:
        method: HTTPメソッド
        url: リクエストURL
        session: Requestsセッション
        **kwargs: requests.request()のパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    # リクエスト情報をログ記録
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
    
    # リクエスト実行（時間計測）
    start_time = time.time()
    success = False
    error_msg = None
    response = None
    
    try:
        response = session.request(method, url, **kwargs)
        success = True
        
        # レスポンスログ記録
        elapsed_ms = (time.time() - start_time) * 1000
        api_logger.log_response(
            method=method.upper(),
            url=url,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            success=True
        )
        
        return response
        
    except requests.exceptions.SSLError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_msg = f"SSL Error: {str(e)[:100]}"
        api_logger.log_response(
            method=method.upper(),
            url=url,
            status_code=0,
            elapsed_ms=elapsed_ms,
            success=False,
            error=error_msg
        )
        api_logger.log_ssl_verification_failure(url, str(e)[:200])
        raise
        
    except requests.exceptions.ProxyError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_msg = f"Proxy Error: {str(e)[:100]}"
        api_logger.log_response(
            method=method.upper(),
            url=url,
            status_code=0,
            elapsed_ms=elapsed_ms,
            success=False,
            error=error_msg
        )
        proxy_url = proxies.get('https') or proxies.get('http')
        if proxy_url:
            api_logger.log_proxy_connection(proxy_url, False)
        raise
        
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        error_msg = f"{type(e).__name__}: {str(e)[:100]}"
        api_logger.log_response(
            method=method.upper(),
            url=url,
            status_code=0,
            elapsed_ms=elapsed_ms,
            success=False,
            error=error_msg
        )
        raise

def proxy_get(url: str, **kwargs) -> requests.Response:
    """
    プロキシ対応 GET リクエスト（Bearer Token自動付与）
    
    Args:
        url: リクエストURL
        **kwargs: requests.get() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    
    # Bearer Token自動付与（ヘッダーに含まれていない場合）
    if 'headers' not in kwargs or kwargs['headers'] is None:
        kwargs['headers'] = {}
    
    if 'Authorization' not in kwargs['headers']:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                kwargs['headers']['Authorization'] = f'Bearer {bearer_token}'
        except Exception:
            pass  # トークン取得失敗時は何もしない（Cookie認証にフォールバック）
    
    return _log_and_execute('GET', url, session, **kwargs)

def proxy_post(url: str, data: Optional[Union[Dict, str, bytes]] = None,
               json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 POST リクエスト（Bearer Token自動付与）
    
    Args:
        url: リクエストURL
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.post() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    
    # Bearer Token自動付与
    if 'headers' not in kwargs or kwargs['headers'] is None:
        kwargs['headers'] = {}
    
    if 'Authorization' not in kwargs['headers']:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                kwargs['headers']['Authorization'] = f'Bearer {bearer_token}'
        except Exception:
            pass
    
    return _log_and_execute('POST', url, session, data=data, json=json, **kwargs)

def proxy_put(url: str, data: Optional[Union[Dict, str, bytes]] = None,
              json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 PUT リクエスト（Bearer Token自動付与）
    
    Args:
        url: リクエストURL
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.put() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    
    # Bearer Token自動付与
    if 'headers' not in kwargs or kwargs['headers'] is None:
        kwargs['headers'] = {}
    
    if 'Authorization' not in kwargs['headers']:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                kwargs['headers']['Authorization'] = f'Bearer {bearer_token}'
        except Exception:
            pass
    
    return _log_and_execute('PUT', url, session, data=data, json=json, **kwargs)

def proxy_patch(url: str, data: Optional[Union[Dict, str, bytes]] = None,
                json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 PATCH リクエスト（Bearer Token自動付与）
    
    Args:
        url: リクエストURL  
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.patch() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    
    # Bearer Token自動付与
    if 'headers' not in kwargs or kwargs['headers'] is None:
        kwargs['headers'] = {}
    
    if 'Authorization' not in kwargs['headers']:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                kwargs['headers']['Authorization'] = f'Bearer {bearer_token}'
        except Exception:
            pass
    
    return _log_and_execute('PATCH', url, session, data=data, json=json, **kwargs)

def proxy_delete(url: str, data: Optional[Union[Dict, str, bytes]] = None,
                 json: Optional[Dict] = None, **kwargs) -> requests.Response:
    """
    プロキシ対応 DELETE リクエスト（Bearer Token自動付与）
    
    Args:
        url: リクエストURL
        data: フォームデータまたはバイナリデータ
        json: JSONデータ
        **kwargs: requests.delete() と同じパラメータ
        
    Returns:
        requests.Response: レスポンスオブジェクト
    """
    session = get_proxy_session()
    
    # Bearer Token自動付与
    if 'headers' not in kwargs or kwargs['headers'] is None:
        kwargs['headers'] = {}
    
    if 'Authorization' not in kwargs['headers']:
        try:
            from config.common import get_bearer_token_for_url
            bearer_token = get_bearer_token_for_url(url)
            if bearer_token:
                kwargs['headers']['Authorization'] = f'Bearer {bearer_token}'
        except Exception:
            pass
    
    return _log_and_execute('DELETE', url, session, data=data, json=json, **kwargs)

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
    return _log_and_execute('HEAD', url, session, **kwargs)

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
    return _log_and_execute(method, url, session, **kwargs)

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

# ============================================================================
# 並列ダウンロード機能
# ============================================================================

def parallel_download(
    tasks: list,
    worker_function: callable,
    max_workers: int = 10,
    progress_callback: Optional[callable] = None,
    threshold: int = 50
) -> Dict[str, Any]:
    """
    並列ダウンロードを実行
    
    Args:
        tasks: タスクリスト（各タスクはworker_functionに渡される引数のタプル）
        worker_function: 各タスクを処理する関数
        max_workers: 最大並列数（デフォルト: 10）
        progress_callback: プログレスコールバック (current, total, message) -> bool
        threshold: 並列化を行う最小タスク数（デフォルト: 50）
        
    Returns:
        Dict[str, Any]: 実行結果
            - success_count: 成功数
            - failed_count: 失敗数
            - skipped_count: スキップ数
            - total: 総タスク数
            - cancelled: キャンセルされたかどうか
            - errors: エラーリスト
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    total_tasks = len(tasks)
    
    # タスク数が閾値未満の場合は同期実行
    if total_tasks < threshold:
        return _sequential_download(tasks, worker_function, progress_callback)
    
    # 並列ダウンロード実行
    success_count = 0
    failed_count = 0
    skipped_count = 0
    completed_count = 0
    cancelled = False
    errors = []
    
    # スレッドセーフなカウンタ
    lock = threading.Lock()
    
    def update_progress():
        """プログレス更新"""
        nonlocal completed_count
        with lock:
            completed_count += 1
            if progress_callback:
                # 0-100%に正規化
                progress_percent = int((completed_count / total_tasks) * 100)
                message = f"並列ダウンロード中... ({completed_count}/{total_tasks})"
                if not progress_callback(progress_percent, 100, message):
                    return False
        return True
    
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 全タスクを投入
            future_to_task = {
                executor.submit(worker_function, *task): task 
                for task in tasks
            }
            
            # 完了したタスクから処理
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                
                try:
                    result = future.result()
                    
                    # 結果の解釈
                    if isinstance(result, str):
                        if "skipped" in result.lower():
                            with lock:
                                skipped_count += 1
                        elif "success" in result.lower():
                            with lock:
                                success_count += 1
                        elif "failed" in result.lower() or "error" in result.lower():
                            with lock:
                                failed_count += 1
                            errors.append({"task": task, "error": result})
                        else:
                            with lock:
                                success_count += 1
                    elif isinstance(result, dict):
                        # 辞書形式の結果を解釈
                        status = result.get("status", "unknown")
                        if status == "success":
                            with lock:
                                success_count += 1
                        elif status == "skipped":
                            with lock:
                                skipped_count += 1
                        elif status == "failed":
                            with lock:
                                failed_count += 1
                            errors.append({"task": task, "error": result.get("error")})
                    else:
                        # その他の結果は成功とみなす
                        with lock:
                            success_count += 1
                    
                except Exception as e:
                    with lock:
                        failed_count += 1
                    errors.append({"task": task, "error": str(e)})
                
                # プログレス更新
                if not update_progress():
                    cancelled = True
                    # 残りのタスクをキャンセル
                    for f in future_to_task:
                        f.cancel()
                    break
        
    except Exception as e:
        errors.append({"error": f"並列実行エラー: {e}"})
    
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "total": total_tasks,
        "cancelled": cancelled,
        "errors": errors
    }

def _sequential_download(
    tasks: list,
    worker_function: callable,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    同期ダウンロードを実行（並列化の閾値未満の場合）
    
    Args:
        tasks: タスクリスト
        worker_function: 各タスクを処理する関数
        progress_callback: プログレスコールバック
        
    Returns:
        Dict[str, Any]: 実行結果
    """
    success_count = 0
    failed_count = 0
    skipped_count = 0
    completed_count = 0
    cancelled = False
    errors = []
    total_tasks = len(tasks)
    
    for idx, task in enumerate(tasks):
        try:
            result = worker_function(*task)
            
            # 結果の解釈
            if isinstance(result, str):
                if "skipped" in result.lower():
                    skipped_count += 1
                elif "success" in result.lower():
                    success_count += 1
                elif "failed" in result.lower() or "error" in result.lower():
                    failed_count += 1
                    errors.append({"task": task, "error": result})
                else:
                    success_count += 1
            elif isinstance(result, dict):
                status = result.get("status", "unknown")
                if status == "success":
                    success_count += 1
                elif status == "skipped":
                    skipped_count += 1
                elif status == "failed":
                    failed_count += 1
                    errors.append({"task": task, "error": result.get("error")})
            else:
                success_count += 1
            
        except Exception as e:
            failed_count += 1
            errors.append({"task": task, "error": str(e)})
        
        # プログレス更新
        completed_count = idx + 1
        if progress_callback:
            progress_percent = int((completed_count / total_tasks) * 100)
            message = f"同期ダウンロード中... ({completed_count}/{total_tasks})"
            if not progress_callback(progress_percent, 100, message):
                cancelled = True
                break
    
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "total": total_tasks,
        "cancelled": cancelled,
        "errors": errors
    }
