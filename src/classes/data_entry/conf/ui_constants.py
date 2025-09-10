# 各行のラベル・入力欄共通スタイル（QSS）
ROW_STYLE_QSS = """
QLabel {
    font-weight: 600;
    min-width: 120px;
    color: #495057;
    padding: 2px 0;
}
QLineEdit, QTextEdit, QComboBox {
    border: 2px solid #e9ecef;
    border-radius: 3px;
    padding: 2px 3px;
    font-size: 10pt;
    background-color: white;
}
QLineEdit:focus, QTextEdit:focus {
    border-color: #2196f3;
    outline: none;
}
QLineEdit::placeholder, QTextEdit::placeholder {
    color: #28a745;
    font-style: italic;
}
"""
# タブ・フォーム共通スタイル（QSS）
DATA_REGISTER_TAB_STYLE = """
QTabWidget::pane {
    border: 1px solid #ddd;
    border-radius: 6px;
    background-color: white;
    min-height: 400px;
}
QTabWidget::tab-bar {
    alignment: left;
}
QTabBar::tab {
    background-color: #f8f9fa;
    border: 1px solid #ddd;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 0.3em 1.2em;
    margin-right: 2px;
    min-width: 100px;
    font-weight: 500;
    color: #495057;
    font-size: 10.5pt;
    font-family: 'Meiryo', 'Yu Gothic', 'Segoe UI', sans-serif;
}
QTabBar::tab:selected {
    background-color: white;
    border-color: #2196f3;
    border-bottom: 1px solid white;
    color: #2196f3;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background-color: #e9ecef;
    color: #212529;
}
"""

DATA_REGISTER_FORM_STYLE = """
QWidget {
    font-family: 'Meiryo', 'Yu Gothic', 'Segoe UI', sans-serif;
    font-size: 10.5pt;
}
QLabel {
    font-size: 10.5pt;
    color: #212529;
    font-weight: 500;
    margin-top: 0.08em;
    margin-bottom: 0.08em;
    padding-top: 0.02em;
    padding-bottom: 0.02em;
}
QLineEdit, QTextEdit, QComboBox {
    font-size: 10.5pt;
    padding-top: 0.02em;
    padding-bottom: 0.02em;
    padding-left: 0.2em;
    padding-right: 0.2em;
    border: 1px solid #ced4da;
    border-radius: 3px;
    background: #fff;
    margin-top: 0.05em;
    margin-bottom: 0.05em;
    min-height: 1.3em;
    min-width: 120px;
}
QPushButton {
    font-size: 10.5pt;
    padding-top: 0.04em;
    padding-bottom: 0.04em;
    padding-left: 0.4em;
    padding-right: 0.4em;
    border-radius: 4px;
    background: #2196f3;
    color: #fff;
    font-weight: bold;
    margin-top: 0.05em;
    margin-bottom: 0.05em;
    min-height: 1.3em;
    transition: background 0.2s;
}
QPushButton:enabled {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #42a5f5, stop:1 #1976d2);
    color: #fff;
    border: 1.5px solid #1976d2;
}
QPushButton:hover:enabled {
    background: #1565c0;
    color: #fff;
}
QPushButton:disabled {
    background: #eceff1;
    color: #b0bec5;
    border: 1.5px dashed #b0bec5;
    opacity: 1.0;
}
QPushButton:hover:enabled {
    background: #1976d2;
    color: #fff;
}
QPushButton:disabled {
    background: #cfd8dc;
    color: #b0bec5;
    border: 1.5px dashed #90a4ae;
    opacity: 1.0;
}
QGroupBox {
    border: 1.2px solid #2196f3;
    border-radius: 5px;
    margin-top: 0.12em;
    margin-bottom: 0.12em;
    padding-top: 0.08em;
    padding-bottom: 0.08em;
    padding-left: 0.15em;
    padding-right: 0.15em;
    background: #fafdff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 4px;
    top: -4px;
    padding: 0 0.2em;
    color: #2196f3;
    font-size: 10.5pt;
    font-weight: bold;
    background: #fafdff;
    border-radius: 2px;
    margin-top: 0.04em;
    margin-bottom: 0.04em;
}
"""

SCROLL_AREA_STYLE = """
QScrollArea {
    border: none;
    background-color: #f8f9fa;
    padding: 0.2em;
    margin: 0px;
}
QScrollBar:vertical {
    background-color: #f8f9fa;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #6c757d;
    border-radius: 5px;
    min-height: 16px;
}
QScrollBar::handle:vertical:hover {
    background-color: #495057;
}
"""

# 一括登録UI用スタイル
BATCH_REGISTER_STYLE = """
QWidget {
    font-family: 'Meiryo', 'Yu Gothic', 'Segoe UI', sans-serif;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #dee2e6;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 12px;
    font-weight: bold;
    color: #495057;
    background-color: #f8f9fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: #2196f3;
    background-color: #f8f9fa;
}
QPushButton {
    padding: 6px 12px;
    border-radius: 4px;
    border: 1px solid #ced4da;
    background-color: #fff;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #e9ecef;
    border-color: #adb5bd;
}
"""

FILE_TREE_STYLE = """
QTreeWidget {
    border: 1px solid #dee2e6;
    border-radius: 4px;
    background-color: white;
    alternate-background-color: #f8f9fa;
    selection-background-color: #e3f2fd;
    font-size: 9pt;
}
QTreeWidget::item {
    padding: 4px;
    border-bottom: 1px solid #f1f3f4;
}
QTreeWidget::item:selected {
    background-color: #2196f3;
    color: white;
}
QTreeWidget::item:hover {
    background-color: #e9ecef;
}
QHeaderView::section {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    padding: 6px;
    font-weight: bold;
    color: #495057;
}
"""

FILESET_TABLE_STYLE = """
QTableWidget {
    border: 1px solid #dee2e6;
    border-radius: 4px;
    background-color: white;
    alternate-background-color: #f8f9fa;
    selection-background-color: #e3f2fd;
    font-size: 9pt;
    gridline-color: #e9ecef;
}
QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #f1f3f4;
}
QTableWidget::item:selected {
    background-color: #2196f3;
    color: white;
}
QTableWidget::item:hover {
    background-color: #e9ecef;
}
QHeaderView::section {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    padding: 8px;
    font-weight: bold;
    color: #495057;
}
"""

# レイアウト・フォント・比率などの変数
TAB_HEIGHT_RATIO = 0.8  # ディスプレイ高さの80%
TAB_MIN_WIDTH = 100
TAB_PADDING = (6, 12)  # (上下, 左右)
FORM_FONT_SIZE = 10.5  # pt単位に変更
GROUPBOX_BORDER_COLOR = "#2196f3"