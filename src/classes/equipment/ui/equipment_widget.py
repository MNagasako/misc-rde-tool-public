"""
設備タブWidget

ARIM設備データの並列取得・処理・出力機能を提供するUIです。
"""

import logging

from classes.equipment.util.output_paths import ensure_equipment_output_dirs

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import QWidget, QVBoxLayout, QTabWidget
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    # Qt非対応時はエラー
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class EquipmentWidget(QWidget):
    """設備タブWidget
    
    データ取得、一覧表示、カタログ変換、データマージの4タブを提供するコンテナ
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setup_ui()
    
    def setup_ui(self):
        """UI構築"""
        ensure_equipment_output_dirs(logger)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # タブウィジェット作成
        self.tab_widget = QTabWidget()
        
        # 各タブ追加
        from classes.equipment.ui.fetch_tab import FetchTab
        from classes.equipment.ui.listing_tab import EquipmentListingTab
        from classes.equipment.ui.convert_tab import ConvertTab
        from classes.equipment.ui.merge_tab import MergeTab
        
        self.fetch_tab = FetchTab(self)
        self.listing_tab = EquipmentListingTab(self)
        self.convert_tab = ConvertTab(self)
        self.merge_tab = MergeTab(self)
        
        self.tab_widget.addTab(self.fetch_tab, "📊 データ取得")
        self.tab_widget.addTab(self.listing_tab, "📋 一覧表示")
        self.tab_widget.addTab(self.convert_tab, "🔄 カタログ変換")
        self.tab_widget.addTab(self.merge_tab, "🔗 データマージ")
        
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.refresh_all_tabs()
        
        main_layout.addWidget(self.tab_widget)

    def on_tab_changed(self, index: int):
        """タブ切り替え時に最新状態へ更新"""
        tab = self.tab_widget.widget(index)
        self._refresh_tab(tab)

    def refresh_all_tabs(self):
        for tab in (self.fetch_tab, self.listing_tab, self.convert_tab, self.merge_tab):
            self._refresh_tab(tab)

    @staticmethod
    def _refresh_tab(tab):
        refresh = getattr(tab, "refresh_from_disk", None)
        if callable(refresh):
            refresh()
