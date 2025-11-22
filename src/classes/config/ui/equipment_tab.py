"""
設備タブ - ARIM RDE Tool
設備サイトからのデータ取得機能

Phase3-2: 設定メニュー設備タブ追加
Phase5: EquipmentWidget統合（設備データ取得機能実装）
"""

import logging

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QLabel
    )
    from qt_compat.gui import QFont
    from classes.theme import get_color, ThemeKey
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

# ログ設定
logger = logging.getLogger(__name__)

class EquipmentTab(QWidget):
    """設備タブ - 設備データ取得機能"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # EquipmentWidgetを組み込む
        try:
            from classes.equipment.ui.equipment_widget import EquipmentWidget
            self.equipment_widget = EquipmentWidget(self)
            layout.addWidget(self.equipment_widget)
            logger.info("設備データ取得ウィジェットを設定タブに統合しました")
        except ImportError as e:
            logger.error("EquipmentWidget読み込みエラー（ImportError）: %s", e)
            import traceback
            traceback.print_exc()
            
            # Qt環境がない場合のフォールバック
            error_label = QLabel(
                f"⚠️ 設備データ取得ウィジェットの読み込みに失敗しました\n\n"
                f"エラー: Qt互換モジュールが必要です\n\n"
                f"詳細: {str(e)}\n\n"
                f"この機能を使用するには、アプリケーションを再起動してください。"
            )
            error_label.setStyleSheet(
                f"font-weight: bold; color: {get_color(ThemeKey.PANEL_ERROR_TEXT)}; "
                f"background-color: {get_color(ThemeKey.PANEL_ERROR_BACKGROUND)}; padding: 20px; "
                f"border-radius: 4px; border: 2px solid {get_color(ThemeKey.PANEL_ERROR_BORDER)};"
            )
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
        except Exception as e:
            logger.error("EquipmentWidget読み込みエラー（その他）: %s", e)
            import traceback
            traceback.print_exc()
            
            # その他のエラーの場合
            error_label = QLabel(
                f"⚠️ 設備データ取得ウィジェットの初期化に失敗しました\n\n"
                f"エラータイプ: {type(e).__name__}\n"
                f"エラー: {str(e)}\n\n"
                f"詳細はログファイルを確認してください。"
            )
            error_label.setStyleSheet(
                f"font-weight: bold; color: {get_color(ThemeKey.PANEL_ERROR_TEXT)}; "
                f"background-color: {get_color(ThemeKey.PANEL_ERROR_BACKGROUND)}; padding: 20px; "
                f"border-radius: 4px; border: 2px solid {get_color(ThemeKey.PANEL_ERROR_BORDER)};"
            )
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
