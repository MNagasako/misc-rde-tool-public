"""
データセットタブウィジェット - QTabWidgetベース
データセット開設、修正、データエントリー機能の統合UI
"""
from qt_compat.widgets import QWidget, QTabWidget, QVBoxLayout, QLabel, QScrollArea
from classes.dataset.ui.dataset_open_widget import create_dataset_open_widget
from classes.dataset.ui.dataset_edit_widget import create_dataset_edit_widget
from classes.dataset.ui.dataset_dataentry_widget_minimal import create_dataset_dataentry_widget
from classes.dataset.ui.dataset_listing_widget import create_dataset_listing_widget
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

class DatasetTabWidget(QTabWidget):
    def __init__(self, parent=None, bearer_token=None, ui_controller=None):
        super().__init__(parent)
        self.bearer_token = bearer_token
        self.ui_controller = ui_controller
        
        # 開設タブ
        self.open_tab = QWidget()
        open_layout = QVBoxLayout(self.open_tab)
        try:
            # データセット開設ウィジェット生成
            self.open_widget = create_dataset_open_widget(
                parent=self.open_tab,
                title="データセット開設",
                create_auto_resize_button=ui_controller.create_auto_resize_button if ui_controller else None
            )
            open_layout.addWidget(self.open_widget)
        except Exception as e:
            error_label = QLabel(f"データセット開設機能読み込みエラー: {e}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            open_layout.addWidget(error_label)
        
        self.open_tab.setLayout(open_layout)
        self.addTab(self.open_tab, "開設")
        
        # 修正タブ
        self.edit_tab = QWidget()
        edit_layout = QVBoxLayout(self.edit_tab)
        try:
            # データセット修正ウィジェット生成
            self.edit_widget = create_dataset_edit_widget(
                parent=self.edit_tab,
                title="データセット修正",
                create_auto_resize_button=ui_controller.create_auto_resize_button if ui_controller else None
            )
            # 修正タブ全体をスクロール可能にする
            edit_scroll = QScrollArea()
            edit_scroll.setWidgetResizable(True)
            edit_scroll.setWidget(self.edit_widget)
            edit_layout.addWidget(edit_scroll)
        except Exception as e:
            error_label = QLabel(f"データセット修正機能読み込みエラー: {e}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            edit_layout.addWidget(error_label)
        
        self.edit_tab.setLayout(edit_layout)
        self.addTab(self.edit_tab, "閲覧・修正")
        
        # データエントリータブ
        self.dataentry_tab = QWidget()
        dataentry_layout = QVBoxLayout(self.dataentry_tab)
        try:
            # データエントリーウィジェット生成（拡張版）
            self.dataentry_widget = create_dataset_dataentry_widget(
                parent=self.dataentry_tab,
                title="データエントリー",
                create_auto_resize_button=ui_controller.create_auto_resize_button if ui_controller else None
            )
            dataentry_layout.addWidget(self.dataentry_widget)
        except Exception as e:
            error_label = QLabel(f"データエントリー機能読み込みエラー: {e}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            dataentry_layout.addWidget(error_label)
        
        self.dataentry_tab.setLayout(dataentry_layout)
        self.addTab(self.dataentry_tab, "データエントリー")

        # 一覧タブ
        self.listing_tab = QWidget()
        listing_layout = QVBoxLayout(self.listing_tab)
        try:
            self.listing_widget = create_dataset_listing_widget(
                parent=self.listing_tab,
                title="一覧",
            )
            listing_layout.addWidget(self.listing_widget)
        except Exception as e:
            error_label = QLabel(f"データセット一覧機能読み込みエラー: {e}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            listing_layout.addWidget(error_label)
        self.listing_tab.setLayout(listing_layout)
        self.addTab(self.listing_tab, "一覧")

# ファクトリ関数
def create_dataset_tab_widget(parent=None, bearer_token=None, ui_controller=None):
    return DatasetTabWidget(parent, bearer_token, ui_controller)