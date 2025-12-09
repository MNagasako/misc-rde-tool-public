"""
報告書タブWidget

ARIM報告書データの並列取得・処理・出力機能を提供するUIです。
タブ化構造：データ取得、Excel変換、研究データ生成

Version: 2.1.0
"""

import logging

from classes.equipment.util.output_paths import ensure_equipment_output_dirs
from classes.reports.util.output_paths import get_reports_root_dir

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import QWidget, QVBoxLayout, QTabWidget
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class ReportWidget(QWidget):
    """
    報告書タブWidget（タブコンテナ）
    
    各機能を個別タブとして提供：
    - データ取得タブ
    - 一覧表示タブ
    - Excel変換タブ
    - 研究データ生成タブ
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        theme_manager = ThemeManager()
        theme_manager.theme_changed.connect(self.refresh_theme)
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # タブWidget作成
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 各タブを動的インポート・追加
        self.setup_tabs()
    
    def setup_tabs(self):
        """タブ設定"""
        try:
            logger.info("報告書タブの初期化を開始...")
            get_reports_root_dir()
            ensure_equipment_output_dirs(logger)
            
            # データ取得タブ
            logger.info("データ取得タブをインポート中...")
            from classes.reports.ui.fetch_tab import ReportFetchTab
            logger.info("ReportFetchTabを作成中...")
            self.fetch_tab = ReportFetchTab()
            self.tab_widget.addTab(self.fetch_tab, "📊 データ取得")
            logger.info("✅ データ取得タブ追加完了")

            # 一覧タブ
            logger.info("一覧タブをインポート中...")
            from classes.reports.ui.listing_tab import ReportListingTab
            logger.info("ReportListingTabを作成中...")
            self.listing_tab = ReportListingTab()
            self.tab_widget.addTab(self.listing_tab, "📋 一覧表示")
            logger.info("✅ 一覧タブ追加完了")
            
            # Excel変換タブ
            logger.info("Excel変換タブをインポート中...")
            from classes.reports.ui.convert_tab import ReportConvertTab
            logger.info("ReportConvertTabを作成中...")
            self.convert_tab = ReportConvertTab()
            self.tab_widget.addTab(self.convert_tab, "🔄 Excel変換")
            logger.info("✅ Excel変換タブ追加完了")
            
            # 研究データ生成タブ
            logger.info("研究データ生成タブをインポート中...")
            from classes.reports.ui.research_data_tab import ResearchDataTab
            logger.info("ResearchDataTabを作成中...")
            self.research_data_tab = ResearchDataTab()
            self.tab_widget.addTab(self.research_data_tab, "📄 研究データ生成")
            logger.info("✅ 研究データ生成タブ追加完了")
            
            logger.info(f"✅ 全タブ追加完了: {self.tab_widget.count()}個のタブ")
            self.tab_widget.currentChanged.connect(self.on_tab_changed)
            self.refresh_all_tabs()
            
        except ImportError as e:
            logger.error(f"タブのインポートエラー: {e}", exc_info=True)
            # フォールバックとしてエラーメッセージ表示
            from qt_compat.widgets import QLabel
            error_label = QLabel(f"タブの読み込みに失敗しました:\n{str(e)}")
            error_label.setWordWrap(True)
            self.tab_widget.addTab(error_label, "⚠ エラー")
        except Exception as e:
            logger.error(f"タブ設定エラー: {e}", exc_info=True)
            from qt_compat.widgets import QLabel
            error_label = QLabel(f"エラーが発生しました:\n{str(e)}")
            error_label.setWordWrap(True)
            self.tab_widget.addTab(error_label, "⚠ エラー")
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        try:
            # 各タブのrefresh_theme()を呼び出し
            if hasattr(self, 'fetch_tab') and hasattr(self.fetch_tab, 'refresh_theme'):
                self.fetch_tab.refresh_theme()
            if hasattr(self, 'listing_tab') and hasattr(self.listing_tab, 'refresh_theme'):
                self.listing_tab.refresh_theme()
            if hasattr(self, 'convert_tab') and hasattr(self.convert_tab, 'refresh_theme'):
                self.convert_tab.refresh_theme()
            if hasattr(self, 'research_data_tab') and hasattr(self.research_data_tab, 'refresh_theme'):
                self.research_data_tab.refresh_theme()
            
            # ウィジェット全体を再描画
            self.update()
            logger.debug("ReportWidget: テーマ更新完了")
        except Exception as e:
            logger.error(f"ReportWidget: テーマ更新エラー: {e}")

    def on_tab_changed(self, index: int):
        """タブ切り替え時に最新状態へ更新"""
        tab = self.tab_widget.widget(index)
        self._refresh_tab(tab)

    def refresh_all_tabs(self):
        """全タブをディスク上の最新状態へ更新"""
        for tab in (
            getattr(self, 'fetch_tab', None),
            getattr(self, 'listing_tab', None),
            getattr(self, 'convert_tab', None),
            getattr(self, 'research_data_tab', None),
        ):
            self._refresh_tab(tab)

    @staticmethod
    def _refresh_tab(tab):
        refresh = getattr(tab, "refresh_from_disk", None)
        if callable(refresh):
            refresh()
