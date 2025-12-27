from __future__ import annotations

from typing import Iterable

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color


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


def apply_launch_controls_theme(launch_label, launch_buttons: Iterable[object]) -> None:
    """「他機能連携」ラベル/ボタンのテーマ準拠スタイルを適用する。

    注意: 既に setStyleSheet 済みのボタンはテーマ切替で自動更新されないため、
    theme_changed で再適用する前提のヘルパー。
    """
    try:
        if launch_label is not None and hasattr(launch_label, "setStyleSheet"):
            launch_label.setStyleSheet(
                f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;"
            )
    except Exception:
        pass

    try:
        style = get_launch_button_style()
        for b in list(launch_buttons or []):
            if b is None or not hasattr(b, "setStyleSheet"):
                continue
            b.setStyleSheet(style)
    except Exception:
        pass


def bind_launch_controls_to_theme(launch_label, launch_buttons: Iterable[object]) -> None:
    """テーマ変更時に「他機能連携」スタイルを再適用するバインドを行う。"""
    try:
        tm = ThemeManager.instance()
        tm.theme_changed.connect(lambda *_: apply_launch_controls_theme(launch_label, launch_buttons))
    except Exception:
        return
