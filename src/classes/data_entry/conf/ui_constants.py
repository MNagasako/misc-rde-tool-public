# 各行のラベル・入力欄共通スタイル（QSS）
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color, ThemeManager

# 【v2.1.7最適化】スタイルキャッシュ（テーマモード単位）
_style_cache = {}
_theme_hook_installed = False

def _get_theme_cache_key(prefix):
    """テーマモードをキーとしてキャッシュキーを生成"""
    try:
        mode = ThemeManager.instance().get_mode().value
        return f"{prefix}_{mode}"
    except Exception:
        return f"{prefix}_default"


def clear_style_cache() -> None:
    """スタイル生成キャッシュをクリアする。

    テーマ切替時に古い配色が残らないように、QSS生成キャッシュとQt側の描画キャッシュも可能な範囲でクリアする。
    """

    _style_cache.clear()
    try:
        from PySide6.QtGui import QPixmapCache

        QPixmapCache.clear()
    except Exception:
        pass

    # テーマ切替後に定数も更新しておく
    try:
        refresh_all_styles()
    except Exception:
        pass


def _install_theme_cache_hook() -> None:
    global _theme_hook_installed
    if _theme_hook_installed:
        return

    try:
        ThemeManager.instance().theme_changed.connect(lambda *_: clear_style_cache())
        _theme_hook_installed = True
    except Exception:
        # ThemeManager未初期化/Qt未ロード等でもアプリは動かす
        _theme_hook_installed = False


_install_theme_cache_hook()

# すべての関数と定数をエクスポート
__all__ = [
    'get_row_style_qss',
    'get_data_register_tab_style',
    'get_data_register_form_style',
    'get_scroll_area_style',
    'get_batch_register_style',
    'get_file_tree_style',
    'get_fileset_table_style',
    'get_groupbox_border_color',
    'get_launch_button_style',
    'ROW_STYLE_QSS',
    'DATA_REGISTER_TAB_STYLE',
    'DATA_REGISTER_FORM_STYLE',
    'SCROLL_AREA_STYLE',
    'BATCH_REGISTER_STYLE',
    'GROUPBOX_BORDER_COLOR',
    'FILE_TREE_STYLE',
    'FILESET_TABLE_STYLE',
    'TAB_HEIGHT_RATIO',
    'TAB_MIN_WIDTH',
    'TAB_PADDING',
    'FORM_FONT_SIZE',
]

def get_row_style_qss():
    """行スタイルを動的に生成"""
    return f"""
QLabel {{
    font-weight: 600;
    min-width: 120px;
    color: {get_color(ThemeKey.TEXT_SECONDARY)};
    padding: 2px 0;
}}
QLineEdit, QTextEdit, QComboBox {{
    border: 2px solid {get_color(ThemeKey.INPUT_BORDER)};
    border-radius: 3px;
    padding: 2px 3px;
    font-size: 10pt;
    background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {get_color(ThemeKey.INPUT_BORDER_FOCUS)};
    outline: none;
}}
QLineEdit::placeholder, QTextEdit::placeholder {{
    color: {get_color(ThemeKey.INPUT_PLACEHOLDER)};
    font-style: italic;
}}
QComboBox QAbstractItemView {{
    background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
    selection-background-color: {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)};
    selection-color: {get_color(ThemeKey.TEXT_PRIMARY)};
}}
"""

def get_launch_button_style():
    """他機能連携（Launch）ボタンのスタイル"""
    # 後方互換のため、このモジュールでも公開する
    from classes.utils.launch_ui_styles import get_launch_button_style as _get

    return _get()

# タブ・フォーム共通スタイル（QSS）
def get_data_register_tab_style():
    """タブスタイルを動的に生成"""
    return f"""
QTabWidget {{
    /* コンテナ全体の背景（ライトモードで暗色が残る問題の修正） */
    background-color: {get_color(ThemeKey.DATA_ENTRY_TAB_CONTAINER_BACKGROUND)};
}}
QTabWidget::pane {{
    border: 1px solid {get_color(ThemeKey.TAB_BORDER)};
    border-radius: 6px;
    background-color: {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)};
    min-height: 400px;
}}
QTabWidget::tab-bar {{
    alignment: left;
}}
QTabBar::tab {{
    background-color: {get_color(ThemeKey.TAB_BACKGROUND)};
    border: 1px solid {get_color(ThemeKey.TAB_BORDER)};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 0.3em 1.2em;
    margin-right: 2px;
    min-width: 100px;
    font-weight: 500;
    color: {get_color(ThemeKey.TAB_INACTIVE_TEXT)};
    font-size: 10.5pt;
    font-family: 'Meiryo', 'Yu Gothic', 'Segoe UI', sans-serif;
}}
QTabBar::tab:selected {{
    background-color: {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)};
    border-color: {get_color(ThemeKey.TAB_ACTIVE_BORDER)};
    border-bottom: 1px solid {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)};
    color: {get_color(ThemeKey.TAB_ACTIVE_TEXT)};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
}}
"""

def get_data_register_form_style():
    """フォームスタイルを動的に生成"""
    return f"""
QWidget {{
    font-family: 'Meiryo', 'Yu Gothic', 'Segoe UI', sans-serif;
    font-size: 10.5pt;
    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
}}
QLabel {{
    font-size: 10.5pt;
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
    font-weight: 500;
    margin-top: 0.08em;
    margin-bottom: 0.08em;
    padding-top: 0.02em;
    padding-bottom: 0.02em;
}}
QLineEdit, QTextEdit, QComboBox {{
    font-size: 10.5pt;
    padding-top: 0.02em;
    padding-bottom: 0.02em;
    padding-left: 0.2em;
    padding-right: 0.2em;
    border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
    border-radius: 3px;
    background: {get_color(ThemeKey.INPUT_BACKGROUND)};
    color: {get_color(ThemeKey.INPUT_TEXT)};
    margin-top: 0.05em;
    margin-bottom: 0.05em;
    min-height: 1.3em;
    min-width: 120px;
}}
QPushButton {{
    font-size: 10.5pt;
    padding-top: 0.04em;
    padding-bottom: 0.04em;
    padding-left: 0.4em;
    padding-right: 0.4em;
    border-radius: 4px;
    background: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
    font-weight: bold;
    margin-top: 0.05em;
    margin-bottom: 0.05em;
    min-height: 1.3em;
}}
QPushButton:enabled {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}, stop:1 {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)});
    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
    border: 1.5px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
}}
QPushButton:hover:enabled {{
    background: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
}}
QPushButton:disabled {{
    background: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
    color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
    border: 1.5px dashed {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
    opacity: 1.0;
}}
QGroupBox {{
    border: 1.2px solid {get_color(ThemeKey.GROUPBOX_BORDER)};
    border-radius: 5px;
    margin-top: 0.12em;
    margin-bottom: 0.12em;
    padding-top: 0.08em;
    padding-bottom: 0.08em;
    padding-left: 0.15em;
    padding-right: 0.15em;
    background: {get_color(ThemeKey.GROUPBOX_BACKGROUND)};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 4px;
    top: -4px;
    padding: 0 0.2em;
    color: {get_color(ThemeKey.GROUPBOX_TITLE_TEXT)};
    font-size: 10.5pt;
    font-weight: bold;
    background: {get_color(ThemeKey.GROUPBOX_BACKGROUND)};
    border-radius: 2px;
    margin-top: 0.04em;
    margin-bottom: 0.04em;
}}
"""

def get_scroll_area_style():
    """スクロールエリアスタイルを動的に生成"""
    return f"""
QScrollArea {{
    border: none;
    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
    padding: 0.2em;
    margin: 0px;
}}
QScrollArea > QWidget > QWidget {{
    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
}}
QScrollBar:vertical {{
    background-color: {get_color(ThemeKey.SCROLLBAR_BACKGROUND)};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background-color: {get_color(ThemeKey.SCROLLBAR_HANDLE)};
    border-radius: 5px;
    min-height: 16px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {get_color(ThemeKey.SCROLLBAR_HANDLE_HOVER)};
}}
"""

# 一括登録UI用スタイル
def get_batch_register_style():
    """一括登録スタイルを動的に生成（キャッシュ付き）"""
    cache_key = _get_theme_cache_key("batch_register")
    if cache_key in _style_cache:
        return _style_cache[cache_key]
    
    style = f"""
QWidget {{
    font-family: 'Meiryo', 'Yu Gothic', 'Segoe UI', sans-serif;
    font-size: 10pt;
    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
}}
QGroupBox {{
    border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 12px;
    font-weight: bold;
    color: {get_color(ThemeKey.TEXT_SECONDARY)};
    background-color: {get_color(ThemeKey.GROUPBOX_BACKGROUND)};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: {get_color(ThemeKey.GROUPBOX_TITLE_TEXT)};
    background-color: {get_color(ThemeKey.GROUPBOX_BACKGROUND)};
}}
QPushButton {{
    padding: 6px 12px;
    border-radius: 4px;
    border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
    background-color: {get_color(ThemeKey.BUTTON_DEFAULT_BACKGROUND)};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)};
    border-color: {get_color(ThemeKey.BORDER_DARK)};
}}
"""
    _style_cache[cache_key] = style
    return style

def get_file_tree_style():
    """ファイルツリースタイルを動的に生成（キャッシュ付き）"""
    cache_key = _get_theme_cache_key("file_tree")
    if cache_key in _style_cache:
        return _style_cache[cache_key]
    
    style = f"""
QTreeWidget {{
    border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
    border-radius: 4px;
    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
    alternate-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE)};
    selection-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
    font-size: 9pt;
}}
QTreeWidget::item {{
    padding: 4px;
    border-bottom: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
}}
QTreeWidget::item:selected {{
    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
}}
QTreeWidget::item:hover {{
    background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)};
}}
QHeaderView::section {{
    background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
    border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
    padding: 6px;
    font-weight: bold;
    color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};
}}
"""
    _style_cache[cache_key] = style
    return style

def get_fileset_table_style():
    """ファイルセットテーブルスタイルを動的に生成（キャッシュ付き）"""
    cache_key = _get_theme_cache_key("fileset_table")
    if cache_key in _style_cache:
        return _style_cache[cache_key]
    
    style = f"""
QTableWidget {{
    border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
    border-radius: 4px;
    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
    alternate-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE)};
    selection-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)};
    color: {get_color(ThemeKey.TEXT_PRIMARY)};
    font-size: 9pt;
    gridline-color: {get_color(ThemeKey.TABLE_BORDER)};
}}
QTableWidget::item {{
    padding: 6px;
    border-bottom: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
}}
QTableWidget::item:selected {{
    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
}}
QTableWidget::item:hover {{
    background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)};
}}
QHeaderView::section {{
    background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
    border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
    padding: 6px;
    font-weight: bold;
    color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};
}}
"""
    _style_cache[cache_key] = style
    return style

def get_groupbox_border_color():
    """GroupBoxボーダー色を動的に取得"""
    return get_color(ThemeKey.GROUPBOX_BORDER)

# 後方互換性のため、モジュールロード時に定数を初期化
# 動的にスタイルを取得する場合は関数を直接呼び出すことを推奨
ROW_STYLE_QSS = get_row_style_qss()
DATA_REGISTER_TAB_STYLE = get_data_register_tab_style()
DATA_REGISTER_FORM_STYLE = get_data_register_form_style()
SCROLL_AREA_STYLE = get_scroll_area_style()
BATCH_REGISTER_STYLE = get_batch_register_style()
FILE_TREE_STYLE = get_file_tree_style()
FILESET_TABLE_STYLE = get_fileset_table_style()
GROUPBOX_BORDER_COLOR = get_groupbox_border_color()

def refresh_all_styles():
    """全てのスタイル定数を更新（テーマ変更時に呼び出す）"""
    global ROW_STYLE_QSS, DATA_REGISTER_TAB_STYLE, DATA_REGISTER_FORM_STYLE
    global SCROLL_AREA_STYLE, BATCH_REGISTER_STYLE, FILE_TREE_STYLE
    global FILESET_TABLE_STYLE, GROUPBOX_BORDER_COLOR
    
    ROW_STYLE_QSS = get_row_style_qss()
    DATA_REGISTER_TAB_STYLE = get_data_register_tab_style()
    DATA_REGISTER_FORM_STYLE = get_data_register_form_style()
    SCROLL_AREA_STYLE = get_scroll_area_style()
    BATCH_REGISTER_STYLE = get_batch_register_style()
    FILE_TREE_STYLE = get_file_tree_style()
    FILESET_TABLE_STYLE = get_fileset_table_style()
    GROUPBOX_BORDER_COLOR = get_groupbox_border_color()

# レイアウト・フォント・比率などの変数
TAB_HEIGHT_RATIO = 0.8  # ディスプレイ高さの80%
TAB_MIN_WIDTH = 100
TAB_PADDING = (6, 12)  # (上下, 左右)
FORM_FONT_SIZE = 10.5  # pt単位に変更
