from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel
from classes.theme import ThemeKey, get_color


def apply_label_style(label: QLabel, color_key: ThemeKey, bold: bool = False, point_size: int = 10) -> None:
    """QLabelにフォント/パレットベースのスタイルを適用しQSSを削減する。

    Args:
        label: 対象 QLabel
        color_key: テキストカラー用 ThemeKey
        bold: 太字指定
        point_size: フォントサイズ(pt)
    """
    try:
        font = label.font() if isinstance(label.font(), QFont) else QFont()
        font.setPointSize(point_size)
        font.setBold(bold)
        label.setFont(font)
        label.setStyleSheet(f"color: {get_color(color_key)};")
    except Exception:
        # フォールバック（最低限カラーのみ）
        try:
            label.setStyleSheet(f"color: {get_color(color_key)};")
        except Exception:
            pass
