"""
APIアクセスログ管理モジュール

HTTPリクエスト/レスポンスの詳細ログを記録し、
起動日が変わったら古いログを自動削除します。
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

# プロジェクトルート取得
try:
    from config.common import get_project_root
    PROJECT_ROOT = get_project_root()
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent

# ログディレクトリ
API_LOG_DIR = PROJECT_ROOT / "output" / "log" / "api"
API_LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日次ログファイル名フォーマット
LOG_FILE_FORMAT = "api_access_%Y%m%d.log"

# ロガー設定
_api_logger: Optional[logging.Logger] = None
_current_log_date: Optional[str] = None


def _get_today_log_file() -> Path:
    """今日のログファイルパスを取得"""
    today = datetime.now().strftime("%Y%m%d")
    return API_LOG_DIR / f"api_access_{today}.log"


def _cleanup_old_logs():
    """起動日以外の古いログファイルを削除"""
    today = datetime.now().strftime("%Y%m%d")
    
    try:
        for log_file in API_LOG_DIR.glob("api_access_*.log"):
            # ファイル名から日付を抽出
            filename = log_file.stem  # api_access_20251112
            date_str = filename.split("_")[-1]  # 20251112
            
            if date_str != today:
                log_file.unlink()
                logger.debug("古いAPIログ削除: %s", log_file.name)
    except Exception as e:
        logger.error("APIログクリーンアップエラー: %s", e)


def _init_logger():
    """APIロガーを初期化"""
    global _api_logger, _current_log_date
    
    today = datetime.now().strftime("%Y%m%d")
    
    # 日付が変わった、または初回初期化
    if _current_log_date != today or _api_logger is None:
        # 古いログを削除
        _cleanup_old_logs()
        
        # 新しいロガーを作成
        _api_logger = logging.getLogger(f"api_access_{today}")
        _api_logger.setLevel(logging.INFO)
        _api_logger.handlers.clear()  # 既存ハンドラをクリア
        
        # ファイルハンドラ
        log_file = _get_today_log_file()
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # フォーマット
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        _api_logger.addHandler(file_handler)
        _current_log_date = today
        
        _api_logger.info("=" * 100)
        _api_logger.info(f"API Access Log Started - {datetime.now().strftime('%Y-%m-%d')}")
        _api_logger.info("=" * 100)


def get_logger() -> logging.Logger:
    """APIロガーを取得（自動初期化）"""
    if _api_logger is None or _current_log_date != datetime.now().strftime("%Y%m%d"):
        _init_logger()
    return _api_logger


def log_request(
    method: str,
    url: str,
    proxies: Dict[str, str],
    verify: Any,
    ssl_context_used: bool = False,
    truststore_enabled: bool = False
):
    """
    HTTPリクエスト開始ログ
    
    Args:
        method: HTTPメソッド (GET, POST, etc.)
        url: リクエストURL
        proxies: プロキシ設定
        verify: SSL検証設定 (True/False/証明書パス)
        ssl_context_used: カスタムSSLコンテキスト使用有無
        truststore_enabled: truststore有効化状態
    """
    logger = get_logger()
    
    # プロキシ使用判定
    proxy_used = bool(proxies.get('http') or proxies.get('https'))
    proxy_info = f"Proxy: {proxies.get('https') or proxies.get('http')}" if proxy_used else "Proxy: None (Direct)"
    
    # SSL検証情報
    if verify is False:
        ssl_info = "SSL: Disabled ⚠️"
    elif verify is True:
        if truststore_enabled:
            ssl_info = "SSL: Enabled (truststore + Windows Cert Store) ✅"
        else:
            ssl_info = "SSL: Enabled (default) ✅"
    else:
        ssl_info = f"SSL: Enabled (Custom CA: {verify}) ✅"
    
    # CA情報
    ca_info = "truststore" if truststore_enabled else ("custom" if isinstance(verify, str) else "system")
    
    logger.info(f"→ REQUEST  | {method:6s} | {url}")
    logger.info(f"            | {proxy_info} | {ssl_info} | CA: {ca_info}")


def log_response(
    method: str,
    url: str,
    status_code: int,
    elapsed_ms: float,
    success: bool = True,
    error: Optional[str] = None
):
    """
    HTTPレスポンスログ
    
    Args:
        method: HTTPメソッド
        url: リクエストURL
        status_code: HTTPステータスコード
        elapsed_ms: 処理時間（ミリ秒）
        success: 成功/失敗フラグ
        error: エラーメッセージ（失敗時）
    """
    logger = get_logger()
    
    if success:
        status_icon = "✅" if 200 <= status_code < 300 else ("⚠️" if 400 <= status_code < 500 else "❌")
        logger.info(f"← RESPONSE | {method:6s} | HTTP {status_code} {status_icon} | {elapsed_ms:.0f}ms | {url}")
    else:
        logger.error(f"← ERROR    | {method:6s} | {error} | {elapsed_ms:.0f}ms | {url}")


def log_ssl_verification_success(url: str, cert_info: Optional[str] = None):
    """SSL検証成功ログ"""
    logger = get_logger()
    cert_detail = f" | Cert: {cert_info}" if cert_info else ""
    logger.info(f"   SSL Verification SUCCESS ✅{cert_detail} | {url}")


def log_ssl_verification_failure(url: str, error: str):
    """SSL検証失敗ログ"""
    logger = get_logger()
    logger.error(f"   SSL Verification FAILED ❌ | {error} | {url}")


def log_proxy_connection(proxy_url: str, success: bool):
    """プロキシ接続ログ"""
    logger = get_logger()
    if success:
        logger.info(f"   Proxy Connection SUCCESS ✅ | {proxy_url}")
    else:
        logger.error(f"   Proxy Connection FAILED ❌ | {proxy_url}")


# 初期化（モジュールインポート時に古いログ削除）
_cleanup_old_logs()
