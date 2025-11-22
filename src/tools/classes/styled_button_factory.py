from qt_compat.widgets import QPushButton
from qt_compat.gui import QFont
from classes.theme import get_color, ThemeKey
from classes.utils.button_styles import get_button_style

class StyledButtonFactory:
    """
    ボタンのデザイン・スタイルを一元管理するファクトリークラス。
    RDEDatasetCreationGUI から分離。
    """
    @staticmethod
    def create_styled_button(text, color_style="default", font_size=9):
        button = QPushButton(text)
        font = QFont("メイリオ", font_size)
        button.setFont(font)
        # kind対応マッピング (button_styles の kind と color_style の橋渡し)
        kind_map = {
            "user": "success",
            "dataset": "secondary",
            "group": "warning",
            "action": "danger",
            "web": "web",
            "auth": "auth",
            "api": "api",
            "default": "default",
        }
        kind = kind_map.get(color_style, "primary")
        base_button_style = get_button_style(kind)
        # 追加ホバー背景 (存在すれば)
        hover_suffix = ""
        hover_key_map = {
            "primary": ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER,
            "secondary": ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER,
            "success": ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER,
            "warning": ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER,
            "danger": ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER,
            "web": ThemeKey.BUTTON_WEB_BACKGROUND_HOVER,
            "auth": ThemeKey.BUTTON_AUTH_BACKGROUND_HOVER,
            "api": ThemeKey.BUTTON_API_BACKGROUND_HOVER,
            "default": ThemeKey.BUTTON_DEFAULT_BACKGROUND,  # fallback no hover variant
        }
        if kind in hover_key_map:
            hover_color = get_color(hover_key_map[kind])
            hover_suffix = f"\nQPushButton:hover {{ background-color: {hover_color}; }}"
        # disabled 状態は共通で追加
        disabled_block = (
            "\nQPushButton:disabled { "
            f"background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; "
            f"border-color: {get_color(ThemeKey.BUTTON_DISABLED_BORDER)}; "
            "}"
        )
        # フォントサイズ指定を追加 (base_button_style の内部に font-size が無い場合のみ上書き)
        if f"font-size:" not in base_button_style:
            base_button_style = base_button_style.replace(
                "QPushButton { ", f"QPushButton {{ font-size: {font_size}pt; "
            )
        full_style = base_button_style + hover_suffix + disabled_block
        button.setStyleSheet(full_style)
        return button
