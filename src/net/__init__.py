"""
Network module for ARIM RDE Tool
HTTP requests with proxy support

緊急修正: 循環参照回避のため、一時的にインポートを無効化
"""

# 型定義のインポート（循環参照なし）
try:
    import requests as _requests_types
except ImportError:
    # フォールバック用の型定義
    class _MockResponse:
        status_code = 200
        content = b''
        text = ''
        def json(self): return {}
    
    class _MockSession:
        def request(self, *args, **kwargs): return _MockResponse()
    
    class _requests_types:
        Response = _MockResponse
        Session = _MockSession
        class exceptions:
            RequestException = Exception
            Timeout = Exception
            ConnectionError = Exception

# 循環参照回避のため、一時的にコメントアウト
# from .http import (
#     get, post, put, patch, delete, head, request,
#     Session, Response, exceptions, cookies,
#     configure, get_session, get_config,
#     add_bearer_token, add_cookies, clear_auth,
#     get_proxy_config, get_webview_proxy_args
# )

# from .config import (
#     load_network_config, get_default_config, 
#     save_network_config, validate_config
# )

# __all__ = [
#     # HTTP functions
#     'get', 'post', 'put', 'patch', 'delete', 'head', 'request',
#     
#     # Classes and objects
#     'Session', 'Response', 'exceptions', 'cookies',
#     
#     # Configuration functions
#     'configure', 'get_session', 'get_config',
#     
#     # Authentication helpers
#     'add_bearer_token', 'add_cookies', 'clear_auth',
#     
#     # Proxy helpers
#     'get_proxy_config', 'get_webview_proxy_args',
#     
#     # Config management
#     'load_network_config', 'get_default_config',
#     'save_network_config', 'validate_config'
# ]
