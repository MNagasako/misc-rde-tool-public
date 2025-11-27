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
        
        # フォントサイズ指定を追加 (base_button_style の内部に font-size が無い場合のみ上書き)
        if f"font-size:" not in base_button_style:
            base_button_style = base_button_style.replace(
                "QPushButton { ", f"QPushButton {{ font-size: {font_size}pt; "
            )
        
        button.setStyleSheet(base_button_style)
        return button
