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
    'primary': (ThemeKey.BUTTON_PRIMARY_BACKGROUND, ThemeKey.BUTTON_PRIMARY_TEXT, ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER),
    'secondary': (ThemeKey.BUTTON_SECONDARY_BACKGROUND, ThemeKey.BUTTON_SECONDARY_TEXT, ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER),
    'danger': (ThemeKey.BUTTON_DANGER_BACKGROUND, ThemeKey.BUTTON_DANGER_TEXT, ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER),
    'warning': (ThemeKey.BUTTON_WARNING_BACKGROUND, ThemeKey.BUTTON_WARNING_TEXT, ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER),
    'inactive': (ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND, ThemeKey.MENU_BUTTON_INACTIVE_TEXT, None),
    'active': (ThemeKey.BUTTON_PRIMARY_BACKGROUND, ThemeKey.BUTTON_PRIMARY_TEXT, ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER),
    'success': (ThemeKey.BUTTON_SUCCESS_BACKGROUND, ThemeKey.BUTTON_SUCCESS_TEXT, ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER),
    'neutral': (ThemeKey.BUTTON_NEUTRAL_BACKGROUND, ThemeKey.BUTTON_NEUTRAL_TEXT, ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER),
    'web': (ThemeKey.BUTTON_WEB_BACKGROUND, ThemeKey.BUTTON_WEB_TEXT, ThemeKey.BUTTON_WEB_BACKGROUND_HOVER),
    'auth': (ThemeKey.BUTTON_AUTH_BACKGROUND, ThemeKey.BUTTON_AUTH_TEXT, ThemeKey.BUTTON_AUTH_BACKGROUND_HOVER),
    'api': (ThemeKey.BUTTON_API_BACKGROUND, ThemeKey.BUTTON_API_TEXT, ThemeKey.BUTTON_API_BACKGROUND_HOVER),
    'default': (ThemeKey.BUTTON_DEFAULT_BACKGROUND, ThemeKey.BUTTON_DEFAULT_TEXT, ThemeKey.BUTTON_DEFAULT_BACKGROUND_HOVER),
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
    
    # マッピングから取得 (デフォルトはsecondary)
    mapping = _MAPPING.get(kind_lower, _MAPPING['secondary'])
    bg_key, fg_key = mapping[0], mapping[1]
    hover_key = mapping[2] if len(mapping) > 2 else None

    # ベーススタイル
    style = (
        "QPushButton { "
        f"background-color: {get_color(bg_key)}; "
        f"color: {get_color(fg_key)}; "
        f"{_BASE} }}"
    )
    
    # ホバースタイル
    if hover_key:
        style += f" QPushButton:hover {{ background-color: {get_color(hover_key)}; }}"
        
    # 無効状態スタイル (共通)
    style += (
        " QPushButton:disabled { "
        f"background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)}; "
        f"color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; "
        f"border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)}; "
        "}"
    )
    
    return style

@lru_cache(maxsize=32)
def get_menu_button_style(is_active: bool) -> str:
    """メニューボタン用のスタイルを返す (hover対応)"""
    if is_active:
        bg_key = ThemeKey.MENU_BUTTON_ACTIVE_BACKGROUND
        fg_key = ThemeKey.MENU_BUTTON_ACTIVE_TEXT
    else:
        bg_key = ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND
        fg_key = ThemeKey.MENU_BUTTON_INACTIVE_TEXT
    
    hover_bg = get_color(ThemeKey.MENU_BUTTON_HOVER_BACKGROUND)
    hover_fg = get_color(ThemeKey.MENU_BUTTON_HOVER_TEXT)
    
    return (
        "QPushButton { "
        f"background-color: {get_color(bg_key)}; "
        f"color: {get_color(fg_key)}; "
        "font-weight: bold; border-radius: 6px; margin: 2px; padding: 4px 8px; }"
        f"QPushButton:hover {{ background-color: {hover_bg}; color: {hover_fg}; }}"
    )

__all__ = ["get_button_style", "get_menu_button_style"]
