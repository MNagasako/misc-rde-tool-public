"""
報告書タブWidget

ARIM報告書データの並列取得・処理・出力機能を提供するUIです。
タブ化構造：データ取得、Excel変換、研究データ生成

Version: 2.1.0
"""

import logging

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
        self._lazy_tabs = {}
        self._lazy_building = set()
        self._lazy_initialized_once = False
        self._output_dirs_ready = False
        self.setup_ui()
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_theme)
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # タブWidget作成
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # タブは遅延ロード（初期表示を軽くする）
        self.setup_tabs()
    
    def setup_tabs(self):
        """タブ設定"""
        from qt_compat.widgets import QLabel

        logger.info("報告書タブの遅延ロードを設定...")

        def placeholder(text: str) -> QLabel:
            label = QLabel(text)
            label.setWordWrap(True)
            return label

        # まずはプレースホルダを追加（ここでは重い import/初期化をしない）
        self._add_lazy_tab(
            label="📊 データ取得",
            placeholder_widget=placeholder("データ取得タブを読み込み中..."),
            builder=self._build_fetch_tab,
            attr_name="fetch_tab",
        )
        self._add_lazy_tab(
            label="📋 一覧表示",
            placeholder_widget=placeholder("一覧表示タブを読み込み中..."),
            builder=self._build_listing_tab,
            attr_name="listing_tab",
        )
        self._add_lazy_tab(
            label="🔄 Excel変換",
            placeholder_widget=placeholder("Excel変換タブを読み込み中..."),
            builder=self._build_convert_tab,
            attr_name="convert_tab",
        )
        self._add_lazy_tab(
            label="📄 研究データ生成",
            placeholder_widget=placeholder("研究データ生成タブを読み込み中..."),
            builder=self._build_research_data_tab,
            attr_name="research_data_tab",
        )

        logger.info(f"✅ タブプレースホルダ追加完了: {self.tab_widget.count()}個のタブ")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def showEvent(self, event):
        super().showEvent(event)
        if self._lazy_initialized_once:
            return
        self._lazy_initialized_once = True

        # 初期表示の露出を妨げないよう、少し遅らせて現タブをロード
        try:
            from qt_compat.core import QTimer

            QTimer.singleShot(50, lambda: self._maybe_build_tab(self.tab_widget.currentIndex()))
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        self._maybe_build_tab(index)
        tab = self.tab_widget.widget(index)
        self._refresh_tab(tab)

    def _add_lazy_tab(self, label: str, placeholder_widget: QWidget, builder, attr_name: str):
        index = self.tab_widget.addTab(placeholder_widget, label)
        self._lazy_tabs[index] = (label, builder, attr_name)

    def _maybe_build_tab(self, index: int):
        spec = self._lazy_tabs.get(index)
        if not spec:
            return
        if index in self._lazy_building:
            return
        label, builder, attr_name = spec
        self._lazy_building.add(index)
        try:
            widget = builder()
        except Exception as e:
            logger.error(f"ReportWidget: タブ構築エラー ({label}): {e}", exc_info=True)
            from qt_compat.widgets import QLabel

            widget = QLabel(f"タブの読み込みに失敗しました:\n{str(e)}")
            widget.setWordWrap(True)
        finally:
            # NOTE: 差し替え完了まで building 状態を維持する。
            # 差し替え中に currentChanged が再入すると無限再帰になり得るため。
            pass

        try:
            # タブの remove/insert/setCurrentIndex は currentChanged を誘発し、
            # _on_tab_changed → _maybe_build_tab が再入する可能性がある。
            # Qt のシグナルをブロックしつつ差し替える。
            from qt_compat.core import QtCore

            blocker = QtCore.QSignalBlocker(self.tab_widget)
            try:
                old = self.tab_widget.widget(index)
                self.tab_widget.removeTab(index)
                if old is not None:
                    old.deleteLater()
                self.tab_widget.insertTab(index, widget, label)

                # 再入防止のため、lazy管理から先に外しておく
                self._lazy_tabs.pop(index, None)
                setattr(self, attr_name, widget)

                try:
                    self.tab_widget.setCurrentIndex(index)
                except Exception:
                    pass
            finally:
                # blocker の破棄でシグナルブロック解除
                del blocker
        except Exception as e:
            logger.error(f"ReportWidget: タブ差し替え失敗 ({label}): {e}", exc_info=True)
        finally:
            self._lazy_building.discard(index)

    def _ensure_output_dirs(self):
        if self._output_dirs_ready:
            return
        from classes.equipment.util.output_paths import ensure_equipment_output_dirs
        from classes.reports.util.output_paths import get_reports_root_dir

        get_reports_root_dir()
        ensure_equipment_output_dirs(logger)
        self._output_dirs_ready = True

    def _build_fetch_tab(self) -> QWidget:
        self._ensure_output_dirs()
        from classes.reports.ui.fetch_tab import ReportFetchTab

        return ReportFetchTab()

    def _build_listing_tab(self) -> QWidget:
        self._ensure_output_dirs()
        from classes.reports.ui.listing_tab import ReportListingTab

        return ReportListingTab(defer_initial_refresh=True)

    def _build_convert_tab(self) -> QWidget:
        self._ensure_output_dirs()
        from classes.reports.ui.convert_tab import ReportConvertTab

        return ReportConvertTab()

    def _build_research_data_tab(self) -> QWidget:
        self._ensure_output_dirs()
        from classes.reports.ui.research_data_tab import ResearchDataTab

        return ResearchDataTab()
    
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
