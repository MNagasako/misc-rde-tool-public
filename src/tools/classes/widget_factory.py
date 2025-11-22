from qt_compat.widgets import QLabel, QTextEdit, QPushButton, QHBoxLayout, QVBoxLayout
from qt_compat.gui import QFont
from classes.theme import get_color, ThemeKey
from classes.utils.button_styles import get_button_style

def create_labeled_textedit(label_text, placeholder, max_height=100, font_size=None):
    label = QLabel(label_text)
    textedit = QTextEdit()
    textedit.setPlaceholderText(placeholder)
    textedit.setMaximumHeight(max_height)
    if font_size:
        font = textedit.font()
        font.setPointSize(font_size)
        textedit.setFont(font)
    return label, textedit

def create_action_button(text, callback=None, color_style="default", font_size=None):
    button = QPushButton(text)
    # スタイルは color_style で分岐
    kind_map = {
        "default": "default",
        "action": "warning",
        "group": "success",
        "dataset": "secondary",
        "auth": "primary",
        "web": "web",
        "api": "danger",
    }
    style = get_button_style(kind_map.get(color_style, "default"))
    # 最小幅など追加装飾が必要ならここで拡張可能
    button.setStyleSheet(style)
    if callback:
        button.clicked.connect(callback)
    if font_size:
        font = button.font()
        font.setPointSize(font_size)
        button.setFont(font)
    return button

def create_labeled_lineedit(label_text, default_text="", font_size=None):
    label = QLabel(label_text)
    from qt_compat.widgets import QLineEdit
    lineedit = QLineEdit()
    lineedit.setText(default_text)
    if font_size:
        font = lineedit.font()
        font.setPointSize(font_size)
        lineedit.setFont(font)
    return label, lineedit

# 追加で必要なWidgetファクトリ関数があればここに追記してください
