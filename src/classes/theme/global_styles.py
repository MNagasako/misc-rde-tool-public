"""グローバル基本スタイル生成 (最適化対応)"""
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

__all__ = ["get_global_base_style"]

try:
    from classes.utils.theme_perf_util import _LARGE_COMBO_CACHE  # type: ignore
    _HAS_LARGE_COMBOS = bool(_LARGE_COMBO_CACHE)
except Exception:
    _HAS_LARGE_COMBOS = False

def get_global_base_style() -> str:
    combo_full = f"""
QComboBox {{ background-color: {get_color(ThemeKey.COMBO_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; border: 1px solid {get_color(ThemeKey.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}
QComboBox:hover {{ border: 1px solid {get_color(ThemeKey.COMBO_BORDER_FOCUS)}; }}
QComboBox:focus {{ background-color: {get_color(ThemeKey.COMBO_BACKGROUND_FOCUS)}; border: 1px solid {get_color(ThemeKey.COMBO_BORDER_FOCUS)}; }}
QComboBox QAbstractItemView {{ background-color: {get_color(ThemeKey.COMBO_DROPDOWN_BACKGROUND)}; border: 1px solid {get_color(ThemeKey.COMBO_DROPDOWN_BORDER)}; selection-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)}; selection-color: {get_color(ThemeKey.TABLE_ROW_TEXT_SELECTED)}; }}
QComboBox::drop-down {{ width: 18px; background-color: {get_color(ThemeKey.COMBO_ARROW_BACKGROUND)}; border-left: 1px solid {get_color(ThemeKey.COMBO_BORDER)}; }}
QComboBox::drop-down:pressed {{ background-color: {get_color(ThemeKey.COMBO_ARROW_BACKGROUND_PRESSED)}; }}
QComboBox:disabled {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.INPUT_TEXT_DISABLED)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER_DISABLED)}; }}
"""
    combo_simple = f"""
QComboBox {{ background-color: {get_color(ThemeKey.COMBO_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; border: 1px solid {get_color(ThemeKey.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}
QComboBox:hover {{ border: 1px solid {get_color(ThemeKey.COMBO_BORDER_FOCUS)}; }}
QComboBox:focus {{ background-color: {get_color(ThemeKey.COMBO_BACKGROUND_FOCUS)}; border: 1px solid {get_color(ThemeKey.COMBO_BORDER_FOCUS)}; }}
QComboBox::drop-down {{ width: 18px; background-color: {get_color(ThemeKey.COMBO_ARROW_BACKGROUND)}; border-left: 1px solid {get_color(ThemeKey.COMBO_BORDER)}; }}
QComboBox::drop-down:pressed {{ background-color: {get_color(ThemeKey.COMBO_ARROW_BACKGROUND_PRESSED)}; }}
QComboBox:disabled {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.INPUT_TEXT_DISABLED)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER_DISABLED)}; }}
"""
    combo_section = combo_simple if _HAS_LARGE_COMBOS else combo_full
    return f"""QWidget {{ background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}
QGroupBox {{ background-color: {get_color(ThemeKey.GROUPBOX_BACKGROUND)}; border: 1px solid {get_color(ThemeKey.GROUPBOX_BORDER)}; border-radius: 5px; margin-top: 6px; padding-top: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 8px; padding: 0 4px; background-color: {get_color(ThemeKey.GROUPBOX_BACKGROUND)}; color: {get_color(ThemeKey.GROUPBOX_TITLE_TEXT)}; font-weight: bold; }}
QScrollArea {{ background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; }}
QScrollArea > QWidget > QWidget {{ background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; }}
QScrollBar:vertical {{ background-color: {get_color(ThemeKey.SCROLLBAR_BACKGROUND)}; width: 10px; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background-color: {get_color(ThemeKey.SCROLLBAR_HANDLE)}; border-radius: 5px; min-height: 16px; }}
QScrollBar::handle:vertical:hover {{ background-color: {get_color(ThemeKey.SCROLLBAR_HANDLE_HOVER)}; }}
{combo_section}
QLineEdit, QTextEdit {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER)}; border-radius: 4px; padding: 4px; }}
QLineEdit:focus, QTextEdit:focus {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND_FOCUS)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER_FOCUS)}; }}
QLineEdit:disabled, QTextEdit:disabled {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.INPUT_TEXT_DISABLED)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER_DISABLED)}; }}
QLineEdit::placeholder {{ color: {get_color(ThemeKey.TEXT_PLACEHOLDER)}; }}
QComboBox QLineEdit::placeholder {{ color: {get_color(ThemeKey.TEXT_PLACEHOLDER)}; }}
QCheckBox, QRadioButton {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; spacing: 4px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {get_color(ThemeKey.INPUT_BORDER)}; background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border: 1px solid {get_color(ThemeKey.INPUT_BORDER_FOCUS)}; }}
QCheckBox::indicator:checked {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)}; }}
QRadioButton::indicator:checked {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)}; }}
QTabWidget::pane {{ border: 1px solid {get_color(ThemeKey.TAB_BORDER)}; background: {get_color(ThemeKey.TAB_BACKGROUND)}; border-radius: 4px; }}
QTabBar::tab {{ background: {get_color(ThemeKey.TAB_INACTIVE_BACKGROUND)}; color: {get_color(ThemeKey.TAB_INACTIVE_TEXT)}; padding: 6px 12px; border: 1px solid {get_color(ThemeKey.TAB_BORDER)}; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)}; color: {get_color(ThemeKey.TAB_ACTIVE_TEXT)}; border: 1px solid {get_color(ThemeKey.TAB_ACTIVE_BORDER)}; }}
QTabBar::tab:hover {{ background: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)}; }}
QLabel {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}
QLabel[muted="true"] {{ color: {get_color(ThemeKey.TEXT_MUTED)}; }}
QDialog {{ background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}
QDialog QLabel {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}
QListView::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)}; color: {get_color(ThemeKey.TABLE_ROW_TEXT_SELECTED)}; }}
QListView::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {{ background: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)}; }}
QMenu {{ background-color: {get_color(ThemeKey.MENU_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; }}
QMenu::item:selected {{ background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)}; color: {get_color(ThemeKey.TABLE_ROW_TEXT_SELECTED)}; }}
QMenu::item:hover {{ background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)}; }}
QToolTip {{ background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; padding: 4px; border-radius: 4px; }}
QHeaderView::section {{ background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)}; color: {get_color(ThemeKey.TABLE_HEADER_TEXT)}; border: 1px solid {get_color(ThemeKey.TABLE_HEADER_BORDER)}; padding: 4px 6px; }}
QHeaderView::section:horizontal:hover {{ background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)}; }}
QProgressBar {{ background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; color: {get_color(ThemeKey.TEXT_PRIMARY)}; border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; border-radius: 4px; text-align: center; }}
QProgressBar::chunk {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border-radius: 4px; }}
"""
