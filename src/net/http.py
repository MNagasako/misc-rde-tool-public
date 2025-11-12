"""
HTTP Network Wrapper - ARIM RDE Tool プロキシ対応モジュール

requestsライブラリの薄いラッパーとして動作し、プロキシ・SSL設定を透過的に適用。
既存コードからは `from net import http as requests` でインポートして使用。
"""

import requests as _original_requests  # 元のrequestsライブラリを別名でインポート
import logging
import os
import json
import time
from typing import Dict, Optional, Any, Union
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# APIログ機能
try:
    from . import api_logger
    API_LOGGER_AVAILABLE = True
except ImportError:
    API_LOGGER_AVAILABLE = False

# YAML サポートの確認
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# OS証明書ストア対応
try:
    import truststore
    TRUSTSTORE_AVAILABLE = True
except ImportError:
    TRUSTSTORE_AVAILABLE = False
    
# PAC対応
try:
    import pypac
    PAC_AVAILABLE = True
except ImportError:
    PAC_AVAILABLE = False

# 内部ロガー
logger = logging.getLogger("net.http")

# グローバルセッション（単一インスタンス）
_global_session: Optional[_original_requests.Session] = None
_config: Optional[Dict[str, Any]] = None


def _load_network_config() -> Dict[str, Any]:
    """ネットワーク設定ファイルを読み込み（存在しない場合はDIRECT設定を返す）"""
    try:
        # パス管理は既存のconfig.commonを使用
        from config.common import get_dynamic_file_path
        
        # YAML を優先してチェック
        if YAML_AVAILABLE:
            config_path = get_dynamic_file_path("config/network.yaml")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    logger.info(f"ネットワーク設定(YAML)を読み込みました: {config_path}")
                    return config
        
        # JSON形式をチェック
        config_path = get_dynamic_file_path("config/network.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"ネットワーク設定(JSON)を読み込みました: {config_path}")
                return config
        
        logger.info(f"ネットワーク設定ファイルが見つかりません。DIRECT動作で開始")
        return _get_default_config()
            
    except Exception as e:
        logger.warning(f"ネットワーク設定の読み込みに失敗。DIRECT動作で継続: {e}")
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    """デフォルト設定（DIRECT: プロキシなし）"""
    return {
        "network": {
            "mode": "DIRECT",
            "proxies": {"http": "", "https": "", "no_proxy": ""},
            "pac_url": "",
            "cert": {"use_os_store": True, "verify": True, "ca_bundle": ""},
            "timeouts": {"connect": 10, "read": 30},
            "retries": {"total": 3, "backoff_factor": 0.5, "status_forcelist": [429, 500, 502, 503, 504]}
        },
        "webview": {"auto_proxy_from_network": True, "additional_args": []}
    }


def _create_session(config: Dict[str, Any]) -> _original_requests.Session:
    """設定に基づいてrequests.Sessionを構築"""
    session = _original_requests.Session()
    network_config = config.get("network", {})
    mode = network_config.get("mode", "DIRECT")
    
    # 1. SSL/truststore設定
    cert_config = network_config.get("cert", {})
    if cert_config.get("use_os_store", True) and TRUSTSTORE_AVAILABLE:
        truststore.inject_into_ssl()
        logger.info("OS証明書ストアを有効化しました")
    
    # SSL検証設定
    session.verify = cert_config.get("verify", True)
    ca_bundle = cert_config.get("ca_bundle", "")
    if ca_bundle and os.path.exists(ca_bundle):
        session.verify = ca_bundle
        logger.info(f"カスタムCA Bundle を使用: {ca_bundle}")
    
    # 2. プロキシ設定
    if mode == "DIRECT":
        # プロキシを明示的に無効化
        session.proxies = {}
        session.trust_env = False  # 環境変数のプロキシも無視
        logger.info("DIRECT モード: プロキシなしで動作")
        
    elif mode == "STATIC":
        # 固定プロキシ設定
        proxy_config = network_config.get("proxies", {})
        proxies = {}
        if proxy_config.get("http"):
            proxies["http"] = proxy_config["http"]
        if proxy_config.get("https"):
            proxies["https"] = proxy_config["https"]
        
        session.proxies = proxies
        session.trust_env = False  # 環境変数より設定ファイル優先
        
        # no_proxy設定
        if proxy_config.get("no_proxy"):
            os.environ["NO_PROXY"] = proxy_config["no_proxy"]
            
        logger.info(f"STATIC プロキシ: {proxies}")
        
    elif mode == "PAC" and PAC_AVAILABLE:
        # PAC自動設定（循環参照回避のため直接HTTP使用）
        pac_url = network_config.get("pac_url", "")
        if pac_url:
            try:
                # PAC取得専用の基本セッション（プロキシなし）
                pac_fetch_session = _original_requests.Session()
                pac_fetch_session.proxies = {}  # 明示的にプロキシなし
                pac_fetch_session.trust_env = False
                
                # PACファイルを直接取得
                pac_response = pac_fetch_session.get(pac_url, timeout=10)
                pac_content = pac_response.text
                
                # PACから基本的なプロキシ設定を抽出（簡易実装）
                if "DIRECT" in pac_content:
                    # DIRECTが含まれている場合は基本的に直接接続
                    session.proxies = {}
                    session.trust_env = False
                    logger.info(f"PAC設定(DIRECT優先)を適用: {pac_url}")
                else:
                    # 何らかのプロキシ設定がある場合（より高度な解析が必要）
                    logger.warning(f"PAC設定の詳細解析は未実装。DIRECTで継続: {pac_url}")
                    session.proxies = {}
                    session.trust_env = False
                
                pac_fetch_session.close()  # 取得用セッションは破棄
                
            except Exception as e:
                logger.error(f"PAC設定の取得に失敗: {e}. DIRECTで継続")
                session.proxies = {}
                session.trust_env = False
        else:
            logger.warning("PAC URLが設定されていません。DIRECTで継続")
            session.proxies = {}
            session.trust_env = False
            
    else:
        logger.warning(f"未対応モードまたは依存ライブラリ不足: {mode}. DIRECTで継続")
        session.proxies = {}
        session.trust_env = False
    
    # 3. リトライ設定
    retry_config = network_config.get("retries", {})
    retry_strategy = Retry(
        total=retry_config.get("total", 3),
        backoff_factor=retry_config.get("backoff_factor", 0.5),
        status_forcelist=retry_config.get("status_forcelist", [429, 500, 502, 503, 504])
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # 4. デフォルトヘッダー設定
    session.headers.update({
        'User-Agent': 'ARIM-RDE-Tool/1.13.5 (Windows NT 10.0; Win64; x64) requests-wrapper'
    })
    
    logger.info("HTTPセッションを構築しました")
    return session


def configure(config: Optional[Dict[str, Any]] = None) -> None:
    """ネットワーク設定を適用（アプリ起動時に一度呼び出し）"""
    global _global_session, _config
    
    if config is None:
        config = _load_network_config()
    
    _config = config
    _global_session = _create_session(config)
    logger.info("ネットワーク設定が完了しました")


def get_session() -> _original_requests.Session:
    """設定済みのSessionオブジェクトを取得"""
    global _global_session
    
    if _global_session is None:
        configure()  # 未初期化の場合は自動初期化
    
    return _global_session


def get_config() -> Dict[str, Any]:
    """現在のネットワーク設定を取得"""
    global _config
    
    if _config is None:
        configure()
    
    return _config


# ===== requests互換API =====
# 既存コードから透過的に使用できるようにrequests.getなどと同じインターフェースを提供

def _log_and_execute_request(method: str, url: str, session: _original_requests.Session, **kwargs) -> _original_requests.Response:
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
    if not API_LOGGER_AVAILABLE:
        # ログ機能が無効な場合は直接実行
        return session.request(method, url, **kwargs)
    
    # リクエスト情報をログ記録
    proxies = session.proxies or {}
    verify = session.verify
    truststore_enabled = TRUSTSTORE_AVAILABLE
    
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
        
    except _original_requests.exceptions.SSLError as e:
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
        
    except _original_requests.exceptions.ProxyError as e:
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


def get(url: str, **kwargs) -> _original_requests.Response:
    """requests.get互換のGETリクエスト"""
    session = get_session()
    return _log_and_execute_request('GET', url, session, **kwargs)


def post(url: str, **kwargs) -> _original_requests.Response:
    """requests.post互換のPOSTリクエスト"""
    session = get_session()
    return _log_and_execute_request('POST', url, session, **kwargs)


def put(url: str, **kwargs) -> _original_requests.Response:
    """requests.put互換のPUTリクエスト"""
    session = get_session()
    return _log_and_execute_request('PUT', url, session, **kwargs)


def patch(url: str, **kwargs) -> _original_requests.Response:
    """requests.patch互換のPATCHリクエスト"""
    session = get_session()
    return _log_and_execute_request('PATCH', url, session, **kwargs)


def delete(url: str, **kwargs) -> _original_requests.Response:
    """requests.delete互換のDELETEリクエスト"""
    session = get_session()
    return _log_and_execute_request('DELETE', url, session, **kwargs)


def head(url: str, **kwargs) -> _original_requests.Response:
    """requests.head互換のHEADリクエスト"""
    session = get_session()
    return _log_and_execute_request('HEAD', url, session, **kwargs)


def request(method: str, url: str, **kwargs) -> _original_requests.Response:
    """requests.request互換の汎用リクエスト"""
    session = get_session()
    return _log_and_execute_request(method, url, session, **kwargs)


# ===== requests互換のクラス・関数エクスポート =====

# Session クラス（互換性のため）
def Session():
    """新しいSessionオブジェクトを作成（設定は共通設定を継承）"""
    session = _original_requests.Session()
    
    # 共通設定をコピー
    global_session = get_session()
    session.proxies = global_session.proxies.copy()
    session.verify = global_session.verify
    session.headers.update(global_session.headers)
    
    return session


# 例外クラス（元のrequestsから継承）
exceptions = _original_requests.exceptions
Response = _original_requests.Response
cookies = _original_requests.cookies

# その他の互換性関数
def add_bearer_token(token: str) -> None:
    """共通SessionにBearerトークンを設定"""
    session = get_session()
    session.headers['Authorization'] = f'Bearer {token}'


# ===== WebView統合機能 =====

def get_webview_proxy_args() -> list:
    """
    現在のプロキシ設定をWebView (QWebEngineView) の起動引数に変換
    """
    config = get_config()
    webview_config = config.get("webview", {})
    
    # auto_proxy_from_networkがFalseの場合は何も追加しない
    if not webview_config.get("auto_proxy_from_network", True):
        return webview_config.get("additional_args", [])
    
    network_config = config.get("network", {})
    mode = network_config.get("mode", "DIRECT")
    
    proxy_args = []
    
    if mode == "DIRECT":
        # プロキシを明示的に無効化
        proxy_args.extend([
            "--no-proxy-server",
            "--proxy-server=direct://"
        ])
        logger.info("WebView: DIRECT設定を適用")
        
    elif mode == "SYSTEM":
        # システムプロキシ設定を使用（デフォルトの動作）
        # WebViewはデフォルトでシステムプロキシを使用するため特別な引数は不要
        logger.info("WebView: SYSTEMプロキシ設定を適用（自動検出）")
        
    elif mode == "STATIC":
        # 固定プロキシ設定
        proxy_config = network_config.get("proxies", {})
        http_proxy = proxy_config.get("http", "")
        https_proxy = proxy_config.get("https", "")
        
        if http_proxy:
            # プロキシサーバー設定
            proxy_args.append(f"--proxy-server={http_proxy}")
            
            # no_proxy設定
            no_proxy = proxy_config.get("no_proxy", "")
            if no_proxy:
                proxy_args.append(f"--proxy-bypass-list={no_proxy}")
                
            logger.info(f"WebView: STATIC プロキシ設定を適用: {http_proxy}")
        else:
            logger.warning("WebView: STATIC設定でプロキシURLが空、DIRECTで起動")
            proxy_args.extend([
                "--no-proxy-server",
                "--proxy-server=direct://"
            ])
            
    elif mode == "PAC":
        # PAC自動設定
        pac_url = network_config.get("pac_url", "")
        if pac_url:
            proxy_args.append(f"--proxy-pac-url={pac_url}")
            logger.info(f"WebView: PAC設定を適用: {pac_url}")
        else:
            logger.warning("WebView: PAC URLが設定されていません、DIRECTで起動")
            proxy_args.extend([
                "--no-proxy-server",
                "--proxy-server=direct://"
            ])
    
    # 追加引数を結合
    additional_args = webview_config.get("additional_args", [])
    proxy_args.extend(additional_args)
    
    logger.info(f"WebView起動引数: {proxy_args}")
    return proxy_args


def apply_webview_proxy_settings(app_or_profile):
    """
    QWebEngineProfile または QApplication にプロキシ設定を適用
    
    Args:
        app_or_profile: QWebEngineProfile または QApplication インスタンス
    """
    try:
        from qt_compat.webengine import QWebEngineProfile
        from qt_compat.core import QCoreApplication
        
        proxy_args = get_webview_proxy_args()
        
        if hasattr(app_or_profile, 'setHttpCacheType'):
            # QWebEngineProfile の場合
            profile = app_or_profile
            logger.info("WebView: Profileレベルでのプロキシ設定適用")
            # プロファイル固有の設定は限定的
            
        else:
            # QApplication の場合 - 起動引数で設定済みを想定
            logger.info("WebView: Application起動引数でプロキシ設定済み")
            
    except ImportError:
        logger.warning("WebView: PyQt5 WebEngineが利用できません")
    except Exception as e:
        logger.error(f"WebView: プロキシ設定適用中にエラー: {e}")


def get_webview_startup_args():
    """
    QApplication起動時に使用するWebView関連引数を取得
    main関数などでQApplication作成前に呼び出す
    """
    return get_webview_proxy_args()
    logger.info("Bearer トークンを設定しました")


def add_cookies(cookie_dict: Dict[str, str]) -> None:
    """共通SessionにCookieを設定"""
    session = get_session()
    session.cookies.update(cookie_dict)
    logger.info(f"Cookieを設定しました: {len(cookie_dict)}個")


def clear_auth() -> None:
    """認証情報をクリア"""
    session = get_session()
    if 'Authorization' in session.headers:
        del session.headers['Authorization']
    session.cookies.clear()
    logger.info("認証情報をクリアしました")


# 設定取得関数
def get_proxy_config() -> Dict[str, str]:
    """現在のプロキシ設定を取得"""
    session = get_session()
    return session.proxies


def get_webview_proxy_args() -> list:
    """WebView用のプロキシコマンドライン引数を生成"""
    config = get_config()
    webview_config = config.get("webview", {})
    
    if not webview_config.get("auto_proxy_from_network", True):
        return webview_config.get("additional_args", [])
    
    network_config = config.get("network", {})
    mode = network_config.get("mode", "DIRECT")
    args = []
    
    if mode == "STATIC":
        proxy_config = network_config.get("proxies", {})
        if proxy_config.get("http") or proxy_config.get("https"):
            proxy_server = proxy_config.get("https") or proxy_config.get("http")
            args.append(f"--proxy-server={proxy_server}")
            
    elif mode == "PAC":
        pac_url = network_config.get("pac_url", "")
        if pac_url:
            args.append(f"--proxy-pac-url={pac_url}")
    
    # 追加引数をマージ
    args.extend(webview_config.get("additional_args", []))
    
    return args
