"""
報告書タブ - ARIM RDE Tool
報告書サイトからのデータ取得機能

EquipmentTabパターンに準拠した実装:
- ReportWidgetのシンプルなラッパー
- 設定ダイアログ内での表示に最適化
"""

import logging

try:
    from qt_compat.widgets import QWidget, QVBoxLayout
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

# ログ設定
logger = logging.getLogger(__name__)

class ReportTab(QWidget):
    """報告書タブ - ReportWidgetのラッパー"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("ReportTab: 初期化開始")
        self.setup_ui()
        logger.info("ReportTab: 初期化完了")
        
    def setup_ui(self):
        """UI初期化 - ReportWidgetを配置"""
        logger.info("ReportTab.setup_ui: 開始")
        
        # レイアウト設定（EquipmentTabパターン）
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        try:
            # ReportWidget読み込み
            logger.info("ReportTab.setup_ui: ReportWidgetインポート試行")
            from classes.reports.ui.report_widget import ReportWidget
            logger.info("ReportTab.setup_ui: ReportWidgetインポート成功")
            
            # ウィジェット作成
            logger.info("ReportTab.setup_ui: ReportWidget作成試行")
            self.report_widget = ReportWidget(self)
            logger.info("ReportTab.setup_ui: ReportWidget作成成功")
            
            # レイアウトに追加
            layout.addWidget(self.report_widget)
            logger.info("ReportTab.setup_ui: ReportWidget配置完了")
            
        except ImportError as e:
            logger.error(f"ReportTab.setup_ui: ReportWidgetインポート失敗: {e}")
            # フォールバック表示
            from qt_compat.widgets import QLabel
            error_label = QLabel(f"報告書機能の読み込みに失敗しました\n{str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            layout.addWidget(error_label)
            
        except Exception as e:
            logger.error(f"ReportTab.setup_ui: 予期しないエラー: {e}", exc_info=True)
            from qt_compat.widgets import QLabel
            error_label = QLabel(f"報告書タブの初期化中にエラーが発生しました\n{str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            layout.addWidget(error_label)
        
        logger.info("ReportTab.setup_ui: 完了")
