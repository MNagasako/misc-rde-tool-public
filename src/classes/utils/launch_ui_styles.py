from __future__ import annotations

import weakref
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
    except Exception:
        return

    try:
        label_ref = weakref.ref(launch_label) if launch_label is not None else lambda: None
    except Exception:
        label_ref = lambda: None

    try:
        button_list = list(launch_buttons or [])
    except Exception:
        button_list = []

    button_refs = []
    for b in button_list:
        try:
            button_refs.append(weakref.ref(b))
        except Exception:
            pass

    def _on_theme_changed(*_args):
        label_obj = None
        try:
            label_obj = label_ref()
        except Exception:
            label_obj = None

        alive_buttons = []
        for ref in list(button_refs):
            try:
                btn = ref()
            except Exception:
                btn = None
            if btn is not None:
                alive_buttons.append(btn)

        apply_launch_controls_theme(label_obj, alive_buttons)

    try:
        tm.theme_changed.connect(_on_theme_changed)
    except Exception:
        return

    # Disconnect when the primary widget is destroyed (prevents connection leaks)
    def _disconnect(*_args):
        try:
            tm.theme_changed.disconnect(_on_theme_changed)
        except Exception:
            pass

    try:
        if launch_label is not None and hasattr(launch_label, "destroyed"):
            launch_label.destroyed.connect(_disconnect)
        else:
            first = button_list[0] if button_list else None
            if first is not None and hasattr(first, "destroyed"):
                first.destroyed.connect(_disconnect)
    except Exception:
        pass
