from qt_compat.widgets import QPushButton
from qt_compat.gui import QFont

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
        base_style = f"""
            QPushButton {{
                font-size: {font_size}pt;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: 2px solid;
                min-height: 18px;
                text-align: center;
            }}
            QPushButton:hover {{

            }}
            QPushButton:pressed {{

            }}
            QPushButton:disabled {{
                background-color: #85929E;
                border-color: #5D6D7E;
                color: #D5DBDB;
            }}
        """
        if color_style == "user":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border-color: #45a049;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
        elif color_style == "dataset":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #9C27B0;
                    color: white;
                    border-color: #7B1FA2;
                }
                QPushButton:hover {
                    background-color: #7B1FA2;
                }
            """)
        elif color_style == "group":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #FF9800;
                    color: white;
                    border-color: #F57C00;
                }
                QPushButton:hover {
                    background-color: #F57C00;
                }
            """)
        elif color_style == "action":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #F44336;
                    color: white;
                    border-color: #D32F2F;
                }
                QPushButton:hover {
                    background-color: #D32F2F;
                }
            """)
        elif color_style == "web":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #009688;
                    color: white;
                    border-color: #00796B;
                }
                QPushButton:hover {
                    background-color: #00796B;
                }
            """)
        elif color_style == "auth":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #795548;
                    color: white;
                    border-color: #5D4037;
                }
                QPushButton:hover {
                    background-color: #5D4037;
                }
            """)
        elif color_style == "api":
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border-color: #1976D2;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
        else:
            button.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #0D47A1;
                    color: white;
                    border-color: #1565C0;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
        return button
