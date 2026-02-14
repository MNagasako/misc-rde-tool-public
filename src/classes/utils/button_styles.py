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

# コンパクト（横並びで詰めたいボタン向け）
_BASE_COMPACT = "font-weight: bold; border-radius: 6px; margin: 1px; padding: 3px 6px;"

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

    # Basic Info tab grouped actions
    'basicinfo_group1': (
        ThemeKey.BUTTON_BASICINFO_GROUP1_BACKGROUND,
        ThemeKey.BUTTON_BASICINFO_GROUP1_TEXT,
        ThemeKey.BUTTON_BASICINFO_GROUP1_BACKGROUND_HOVER,
        ThemeKey.BUTTON_BASICINFO_GROUP1_BACKGROUND_PRESSED,
        ThemeKey.BUTTON_BASICINFO_GROUP1_BORDER,
    ),
    'basicinfo_group2': (
        ThemeKey.BUTTON_BASICINFO_GROUP2_BACKGROUND,
        ThemeKey.BUTTON_BASICINFO_GROUP2_TEXT,
        ThemeKey.BUTTON_BASICINFO_GROUP2_BACKGROUND_HOVER,
        ThemeKey.BUTTON_BASICINFO_GROUP2_BACKGROUND_PRESSED,
        ThemeKey.BUTTON_BASICINFO_GROUP2_BORDER,
    ),
    'basicinfo_group3': (
        ThemeKey.BUTTON_BASICINFO_GROUP3_BACKGROUND,
        ThemeKey.BUTTON_BASICINFO_GROUP3_TEXT,
        ThemeKey.BUTTON_BASICINFO_GROUP3_BACKGROUND_HOVER,
        ThemeKey.BUTTON_BASICINFO_GROUP3_BACKGROUND_PRESSED,
        ThemeKey.BUTTON_BASICINFO_GROUP3_BORDER,
    ),
    'basicinfo_refetch': (
        ThemeKey.BUTTON_BASICINFO_REFETCH_BACKGROUND,
        ThemeKey.BUTTON_BASICINFO_REFETCH_TEXT,
        ThemeKey.BUTTON_BASICINFO_REFETCH_BACKGROUND_HOVER,
        ThemeKey.BUTTON_BASICINFO_REFETCH_BACKGROUND_PRESSED,
        ThemeKey.BUTTON_BASICINFO_REFETCH_BORDER,
    ),
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
    pressed_key = mapping[3] if len(mapping) > 3 else hover_key
    border_key = mapping[4] if len(mapping) > 4 else None

    base = _BASE_COMPACT if kind_lower.startswith("basicinfo_") else _BASE
    border_css = f"border: 1px solid {get_color(border_key)}; " if border_key else ""

    style = (
        "QPushButton { "
        f"background-color: {get_color(bg_key)}; "
        f"color: {get_color(fg_key)}; "
        f"{border_css}{base} }}"
    )

    if hover_key:
        hover_bg = get_color(hover_key)
        style += f" QPushButton:hover {{ background-color: {hover_bg}; }}"

    if pressed_key:
        pressed_bg = get_color(pressed_key)
        style += f" QPushButton:pressed {{ background-color: {pressed_bg}; }}"

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
        f"QPushButton:pressed {{ background-color: {hover_bg}; color: {hover_fg}; }}"
    )


def get_menu_button_style(is_active: bool) -> str:
    """メニューボタン用のスタイルを返す (hover対応)

    注意: テーマ切替時に色が変わるため、キャッシュキーにテーマモードを含める。
    """
    return _get_menu_button_style_cached(is_active, _theme_cache_key())


# === Main menu grouped styles ===

_MENU_GROUP_BY_MODE: dict[str, int] = {
    # Group 1
    "login": 1,
    # Group 2 (RDE)
    "subgroup_create": 2,
    "dataset_open": 2,
    "data_register": 2,
    "sample_dedup": 2,
    "data_fetch": 2,  # optional/hidden by default
    # Group 7 (Data Fetch2 dedicated)
    "data_fetch2": 7,
    # Group 3 (RDE prep)
    "basic_info": 3,
    # Group 4 (Data portal)
    "data_portal": 4,
    # Group 5 (AI)
    "ai_test2": 5,
    "ai_test": 5,  # optional/hidden by default
    # Group 6 (Settings)
    "settings": 6,
}


def _group_keys(group: int, is_active: bool) -> tuple[ThemeKey, ThemeKey, ThemeKey]:
    """Return (bg_key, fg_key, hover_bg_key) for the group + state."""

    if group == 1:
        if is_active:
            return (
                ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
                ThemeKey.MENU_GROUP1_ACTIVE_TEXT,
                ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
            )
        return (
            ThemeKey.MENU_GROUP1_INACTIVE_BACKGROUND,
            ThemeKey.MENU_GROUP1_INACTIVE_TEXT,
            ThemeKey.MENU_GROUP1_HOVER_BACKGROUND,
        )
    if group == 2:
        if is_active:
            return (
                ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
                ThemeKey.MENU_GROUP2_ACTIVE_TEXT,
                ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
            )
        return (
            ThemeKey.MENU_GROUP2_INACTIVE_BACKGROUND,
            ThemeKey.MENU_GROUP2_INACTIVE_TEXT,
            ThemeKey.MENU_GROUP2_HOVER_BACKGROUND,
        )
    if group == 3:
        if is_active:
            return (
                ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
                ThemeKey.MENU_GROUP3_ACTIVE_TEXT,
                ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
            )
        return (
            ThemeKey.MENU_GROUP3_INACTIVE_BACKGROUND,
            ThemeKey.MENU_GROUP3_INACTIVE_TEXT,
            ThemeKey.MENU_GROUP3_HOVER_BACKGROUND,
        )
    if group == 4:
        if is_active:
            return (
                ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
                ThemeKey.MENU_GROUP4_ACTIVE_TEXT,
                ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
            )
        return (
            ThemeKey.MENU_GROUP4_INACTIVE_BACKGROUND,
            ThemeKey.MENU_GROUP4_INACTIVE_TEXT,
            ThemeKey.MENU_GROUP4_HOVER_BACKGROUND,
        )
    if group == 5:
        if is_active:
            return (
                ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
                ThemeKey.MENU_GROUP5_ACTIVE_TEXT,
                ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
            )
        return (
            ThemeKey.MENU_GROUP5_INACTIVE_BACKGROUND,
            ThemeKey.MENU_GROUP5_INACTIVE_TEXT,
            ThemeKey.MENU_GROUP5_HOVER_BACKGROUND,
        )
    if group == 7:
        if is_active:
            return (
                ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
                ThemeKey.MENU_GROUP7_ACTIVE_TEXT,
                ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
            )
        return (
            ThemeKey.MENU_GROUP2_INACTIVE_BACKGROUND,
            ThemeKey.MENU_GROUP7_INACTIVE_TEXT,
            ThemeKey.MENU_GROUP7_HOVER_BACKGROUND,
        )
    # group 6 (default)
    if is_active:
        return (
            ThemeKey.MENU_ACTIVE_WARM_BACKGROUND,
            ThemeKey.MENU_GROUP6_ACTIVE_TEXT,
            ThemeKey.MENU_ACTIVE_WARM_HOVER_BACKGROUND,
        )
    return (
        ThemeKey.MENU_GROUP6_INACTIVE_BACKGROUND,
        ThemeKey.MENU_GROUP6_INACTIVE_TEXT,
        ThemeKey.MENU_GROUP6_HOVER_BACKGROUND,
    )


@lru_cache(maxsize=256)
def _get_grouped_menu_button_style_cached(mode: str, is_active: bool, theme_key: str) -> str:
    # Keep some buttons unchanged (as requested).
    if mode in {"help"}:
        return get_menu_button_style(is_active)

    group = _MENU_GROUP_BY_MODE.get(mode)
    if group is None:
        return get_menu_button_style(is_active)

    bg_key, fg_key, hover_bg_key = _group_keys(group, is_active)
    hover_bg = get_color(hover_bg_key)
    return (
        "QPushButton { "
        f"background-color: {get_color(bg_key)}; "
        f"color: {get_color(fg_key)}; "
        "font-weight: bold; border-radius: 6px; margin: 2px; padding: 4px 8px; }"
        f"QPushButton:hover {{ background-color: {hover_bg}; color: {get_color(fg_key)}; }}"
        f"QPushButton:pressed {{ background-color: {hover_bg}; color: {get_color(fg_key)}; }}"
    )


def get_grouped_menu_button_style(mode: str, is_active: bool) -> str:
    """メインメニュー（左ペイン）用: グループ別のスタイルを返す。

    - テーマ切替に完全追従（キャッシュキーにテーマモードを含める）
    - hover/選択中(=active) を個別配色
    - help / theme / close などは既存のまま（呼び出し側で使い分ける想定）
    """

    return _get_grouped_menu_button_style_cached(mode, is_active, _theme_cache_key())

__all__ = ["get_button_style", "get_menu_button_style", "get_grouped_menu_button_style"]
