from qt_compat.widgets import QLabel, QTextEdit, QPushButton, QHBoxLayout, QVBoxLayout
from qt_compat.gui import QFont

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
    style_map = {
        "default": "background-color: #f5f5f5; color: #333; border: 1px solid #bbb; border-radius: 4px; padding: 4px 12px;",
        "action": "background-color: #ff9800; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold;",
        "group": "background-color: #4caf50; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold;",
        "dataset": "background-color: #8e24aa; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold;",
        "auth": "background-color: #1976d2; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold;",
        "web": "background-color: #0097a7; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold;",
        "api": "background-color: #c62828; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold;",
    }
    button.setStyleSheet(style_map.get(color_style, style_map["default"]))
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
