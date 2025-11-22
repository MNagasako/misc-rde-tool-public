"""共通ボタンスタイルヘルパー

各所で重複している QPushButton の styleSheet 文字列を一元生成し
キャッシュすることでテーマ切替時のスタイル再構築コストと
パースエラーを低減する。

使用例:
    from classes.utils.button_styles import get_button_style
    button.setStyleSheet(get_button_style('primary'))

kind 値:
    primary / secondary / danger / warning / inactive / active / success / neutral / close /
    web / auth / api / default
"""
from __future__ import annotations
from functools import lru_cache
from classes.theme import get_color, ThemeKey

# ベース共通部品
_BASE = "font-weight: bold; border-radius: 6px; margin: 2px; padding: 4px 8px;"

_MAPPING = {
    'primary': (ThemeKey.BUTTON_PRIMARY_BACKGROUND, ThemeKey.BUTTON_PRIMARY_TEXT),
    'secondary': (ThemeKey.BUTTON_SECONDARY_BACKGROUND, ThemeKey.BUTTON_SECONDARY_TEXT),
    'danger': (ThemeKey.BUTTON_DANGER_BACKGROUND, ThemeKey.BUTTON_DANGER_TEXT),
    'warning': (ThemeKey.BUTTON_WARNING_BACKGROUND, ThemeKey.BUTTON_WARNING_TEXT),
    'inactive': (ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND, ThemeKey.MENU_BUTTON_INACTIVE_TEXT),
    'active': (ThemeKey.BUTTON_PRIMARY_BACKGROUND, ThemeKey.BUTTON_PRIMARY_TEXT),
    'success': (ThemeKey.BUTTON_SUCCESS_BACKGROUND, ThemeKey.BUTTON_SUCCESS_TEXT),
    'neutral': (ThemeKey.BUTTON_NEUTRAL_BACKGROUND, ThemeKey.BUTTON_NEUTRAL_TEXT),
    'web': (ThemeKey.BUTTON_WEB_BACKGROUND, ThemeKey.BUTTON_WEB_TEXT),
    'auth': (ThemeKey.BUTTON_AUTH_BACKGROUND, ThemeKey.BUTTON_AUTH_TEXT),
    'api': (ThemeKey.BUTTON_API_BACKGROUND, ThemeKey.BUTTON_API_TEXT),
    'default': (ThemeKey.BUTTON_DEFAULT_BACKGROUND, ThemeKey.BUTTON_DEFAULT_TEXT),
}

@lru_cache(maxsize=64)
def get_button_style(kind: str) -> str:
    """スタイル種別に応じたQSS文字列を返す (QPushButtonセレクタ付き)"""
    kind_lower = kind.lower()
    if kind_lower == 'close':
        # 閉じるボタン専用 (背景なし、色のみ強調)
        return (
            "QPushButton { "
            f"color: {get_color(ThemeKey.NOTIFICATION_WARNING_TEXT)}; "
            "border: none; font-weight: bold; font-size: 16px; padding: 0 6px; }"
        )
    bg_key, fg_key = _MAPPING.get(kind_lower, _MAPPING['secondary'])
    return (
        "QPushButton { "
        f"background-color: {get_color(bg_key)}; "
        f"color: {get_color(fg_key)}; "
        + _BASE + " }"
    )

__all__ = ["get_button_style"]
