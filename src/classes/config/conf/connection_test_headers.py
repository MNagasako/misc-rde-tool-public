"""
接続テスト用ヘッダ定義

接続テストで使用可能なHTTPヘッダのプリセット定義
"""

from typing import Dict

# Pythonデフォルト（requests標準ヘッダ）
PYTHON_DEFAULT_HEADERS = {}

# ブラウザ模倣（APIアクセス） - アプリケーション内のAPI呼び出しと同じヘッダ
BROWSER_MIMIC_API_HEADERS = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
    'Origin': 'https://rde-user.nims.go.jp',
    'Referer': 'https://rde-user.nims.go.jp/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

# ブラウザ模倣（WebView） - PySide6 WebEngineと同等のヘッダ
BROWSER_MIMIC_WEBVIEW_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.8.1 Chrome/118.0.5993.220 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="118", "Google Chrome";v="118", "Not=A?Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

# ヘッダパターン選択肢の定義
HEADER_PATTERNS = {
    'python_default': {
        'name': 'Pythonデフォルト',
        'description': 'requestsライブラリの標準ヘッダ（最小限）',
        'headers': PYTHON_DEFAULT_HEADERS
    },
    'browser_api': {
        'name': 'ブラウザ模倣（API）',
        'description': 'アプリのAPI呼び出しと同じヘッダ',
        'headers': BROWSER_MIMIC_API_HEADERS
    },
    'browser_webview': {
        'name': 'ブラウザ模倣（WebView）',
        'description': 'ログイン認証WebViewと同じヘッダ',
        'headers': BROWSER_MIMIC_WEBVIEW_HEADERS
    },
    'custom': {
        'name': 'カスタム',
        'description': '手動で指定したヘッダ',
        'headers': {}  # UI側で設定
    }
}


def get_header_pattern(pattern_key: str) -> Dict[str, str]:
    """ヘッダパターンを取得
    
    Args:
        pattern_key: パターンキー（'python_default', 'browser_api', 'browser_webview', 'custom'）
    
    Returns:
        ヘッダ辞書
    """
    pattern = HEADER_PATTERNS.get(pattern_key)
    if not pattern:
        return {}
    return pattern['headers'].copy()


def get_pattern_list():
    """利用可能なヘッダパターン一覧を取得
    
    Returns:
        (パターンキー, 表示名, 説明) のリスト
    """
    return [
        (key, info['name'], info['description'])
        for key, info in HEADER_PATTERNS.items()
    ]
