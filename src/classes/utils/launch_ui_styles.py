from __future__ import annotations

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color


def get_launch_button_style() -> str:
    """他機能連携（Launch）ボタンの共通スタイル。

    目立ちすぎない・高さ控えめ・テーマ準拠（ライト/ダーク両対応）。
    """

    return f"""
    QPushButton {{
        background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
        border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
        border-radius: 4px;
        padding: 2px 8px;
        font-weight: 600;
        font-size: 9.5pt;
        min-height: 24px;
        min-width: 96px;
    }}
    QPushButton:hover {{
        background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
    }}
    QPushButton:disabled {{
        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
    }}
    """
