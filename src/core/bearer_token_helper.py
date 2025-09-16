"""
共通のBearerトークン取得ヘルパー
"""
from typing import Optional

def get_current_bearer_token(widget=None) -> Optional[str]:
    """
    ウィジェット階層・コントローラ・AppConfigManager・ファイルからBearerトークンを取得（通常登録タブ方式）
    Args:
        widget: 起点となるウィジェット（selfなど）
    Returns:
        str or None: Bearerトークン
    """
    # 1. ウィジェット階層を遡ってbearer_tokenを探す
    current = widget
    while current:
        if hasattr(current, 'bearer_token') and getattr(current, 'bearer_token'):
            return getattr(current, 'bearer_token')
        if hasattr(current, 'controller') and hasattr(current.controller, 'bearer_token') and getattr(current.controller, 'bearer_token'):
            return getattr(current.controller, 'bearer_token')
        current = current.parent() if hasattr(current, 'parent') and callable(current.parent) else None
    # 2. AppConfigManager
    try:
        from classes.managers.app_config_manager import get_config_manager
        token = get_config_manager().get('bearer_token')
        if token:
            return token
    except Exception:
        pass
    # 3. ファイル
    try:
        from config.common import BEARER_TOKEN_FILE
        import os
        if os.path.exists(BEARER_TOKEN_FILE):
            with open(BEARER_TOKEN_FILE, 'r', encoding='utf-8') as f:
                token = f.read().strip()
                if token.startswith('BearerToken='):
                    token = token[len('BearerToken='):]
                return token if token else None
    except Exception:
        pass
    return None
