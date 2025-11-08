"""
データ取得2タブウィジェット - QTabWidgetベース
一括取得タブ（現状のUIをそのまま移植）
"""
from qt_compat.widgets import QWidget, QTabWidget, QVBoxLayout
from classes.data_fetch2.core.ui.data_fetch2_widget import create_data_fetch2_widget

class DataFetch2TabWidget(QTabWidget):
    def __init__(self, parent=None, bearer_token=None):
        super().__init__(parent)
        self.bearer_token = bearer_token
        # 一括取得タブ
        self.bulk_tab = QWidget()
        bulk_layout = QVBoxLayout(self.bulk_tab)
        # bearer_tokenを渡してウィジェット生成
        self.bulk_widget = create_data_fetch2_widget(self.bulk_tab, bearer_token=self.bearer_token)
        bulk_layout.addWidget(self.bulk_widget)
        self.bulk_tab.setLayout(bulk_layout)
        self.addTab(self.bulk_tab, "一括取得")

# ファクトリ関数

def create_data_fetch2_tab_widget(parent=None, bearer_token=None):
    return DataFetch2TabWidget(parent, bearer_token)
