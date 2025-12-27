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

from classes.theme import ThemeKey, get_color

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
    'info': (ThemeKey.BUTTON_INFO_BACKGROUND, ThemeKey.BUTTON_INFO_TEXT, ThemeKey.BUTTON_INFO_BACKGROUND_HOVER),
    'web': (ThemeKey.BUTTON_WEB_BACKGROUND, ThemeKey.BUTTON_WEB_TEXT, ThemeKey.BUTTON_WEB_BACKGROUND_HOVER),
    'auth': (ThemeKey.BUTTON_AUTH_BACKGROUND, ThemeKey.BUTTON_AUTH_TEXT, ThemeKey.BUTTON_AUTH_BACKGROUND_HOVER),
    'api': (ThemeKey.BUTTON_API_BACKGROUND, ThemeKey.BUTTON_API_TEXT, ThemeKey.BUTTON_API_BACKGROUND_HOVER),
    'default': (ThemeKey.BUTTON_DEFAULT_BACKGROUND, ThemeKey.BUTTON_DEFAULT_TEXT, ThemeKey.BUTTON_DEFAULT_BACKGROUND_HOVER),
}


def _theme_cache_key() -> str:
    """Return a stable cache key for the current theme mode.

    Note: style strings are theme-dependent. Caching only by `kind` causes
    stale colors after theme toggle.
    """
    try:
        from classes.theme.theme_manager import ThemeManager

        return ThemeManager.instance().get_mode().value
    except Exception:
        return "unknown"

@lru_cache(maxsize=256)
def _get_button_style_cached(kind_lower: str, theme_key: str) -> str:
    """Cacheable implementation. `theme_key` must change when theme changes."""
    if kind_lower == 'close':
        return (
            "QPushButton { "
            f"color: {get_color(ThemeKey.NOTIFICATION_WARNING_TEXT)}; "
            "border: none; font-weight: bold; font-size: 16px; padding: 0 6px; }"
        )

    mapping = _MAPPING.get(kind_lower, _MAPPING['secondary'])
    bg_key, fg_key = mapping[0], mapping[1]
    hover_key = mapping[2] if len(mapping) > 2 else None

    style = (
        "QPushButton { "
        f"background-color: {get_color(bg_key)}; "
        f"color: {get_color(fg_key)}; "
        f"{_BASE} }}"
    )

    if hover_key:
        style += f" QPushButton:hover {{ background-color: {get_color(hover_key)}; }}"

    style += (
        " QPushButton:disabled { "
        f"background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)}; "
        f"color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; "
        f"border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)}; "
        "}"
    )

    return style


def get_button_style(kind: str) -> str:
    """スタイル種別に応じたQSS文字列を返す (QPushButtonセレクタ付き)

    注意: テーマ切替時に色が変わるため、キャッシュキーにテーマモードを含める。
    """
    kind_lower = kind.lower()
    return _get_button_style_cached(kind_lower, _theme_cache_key())

@lru_cache(maxsize=64)
def _get_menu_button_style_cached(is_active: bool, theme_key: str) -> str:
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


def get_menu_button_style(is_active: bool) -> str:
    """メニューボタン用のスタイルを返す (hover対応)

    注意: テーマ切替時に色が変わるため、キャッシュキーにテーマモードを含める。
    """
    return _get_menu_button_style_cached(is_active, _theme_cache_key())

__all__ = ["get_button_style", "get_menu_button_style"]
