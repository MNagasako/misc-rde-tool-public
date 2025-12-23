"""データポータル（公開・ログイン不要）タブ - Settings用ラッパー。

ReportTab / EquipmentTab と同じ構造で、設定ダイアログ内に統合する。
既存の authenticated DataPortalWidget の機能は毀損しない。
"""

from __future__ import annotations

import logging

from qt_compat.widgets import QLabel, QVBoxLayout, QWidget

from classes.theme import ThemeKey, get_color

logger = logging.getLogger(__name__)


class DataPortalPublicTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            from classes.data_portal.ui.public_data_portal_widget import PublicDataPortalWidget

            self.public_portal_widget = PublicDataPortalWidget(self)
            layout.addWidget(self.public_portal_widget)
            logger.info("公開データポータルウィジェットを設定タブに統合しました")

        except ImportError as exc:
            logger.error("PublicDataPortalWidget読み込みエラー（ImportError）: %s", exc, exc_info=True)
            error_label = QLabel(
                "⚠️ 公開データポータルウィジェットの読み込みに失敗しました\n\n"
                "Qt互換モジュールが必要です\n\n"
                f"詳細: {exc}"
            )
            error_label.setStyleSheet(
                f"font-weight: bold; color: {get_color(ThemeKey.PANEL_ERROR_TEXT)}; "
                f"background-color: {get_color(ThemeKey.PANEL_ERROR_BACKGROUND)}; padding: 20px; "
                f"border-radius: 4px; border: 1px solid {get_color(ThemeKey.PANEL_ERROR_BORDER)};"
            )
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

        except Exception as exc:
            logger.error("PublicDataPortalWidget読み込みエラー: %s", exc, exc_info=True)
            error_label = QLabel(
                "⚠️ 公開データポータルウィジェットの初期化に失敗しました\n\n"
                f"エラータイプ: {type(exc).__name__}\n"
                f"エラー: {exc}"
            )
            error_label.setStyleSheet(
                f"font-weight: bold; color: {get_color(ThemeKey.PANEL_ERROR_TEXT)}; "
                f"background-color: {get_color(ThemeKey.PANEL_ERROR_BACKGROUND)}; padding: 20px; "
                f"border-radius: 4px; border: 1px solid {get_color(ThemeKey.PANEL_ERROR_BORDER)};"
            )
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
