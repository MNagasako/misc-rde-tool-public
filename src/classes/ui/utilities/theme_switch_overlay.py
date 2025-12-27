from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from classes.theme import ThemeKey, get_color


class ThemeSwitchOverlayDialog(QDialog):
    """テーマ切替中に操作をブロックするオーバーレイ（ApplicationModal）。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self._label = QLabel("テーマ切替中…")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._apply_theme()

    def _apply_theme(self) -> None:
        # 透明背景の上に半透明パネルを描画
        bg = get_color(ThemeKey.OVERLAY_BACKGROUND)
        fg = get_color(ThemeKey.OVERLAY_TEXT)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {bg};
                border-radius: 8px;
            }}
            QLabel {{
                color: {fg};
                font-size: 12pt;
                font-weight: bold;
                padding: 12px;
            }}
            """
        )

    def show_centered(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            try:
                geo = parent.frameGeometry()
                self.setFixedSize(260, 90)
                self.move(geo.center() - self.rect().center())
            except Exception:
                pass
        self._apply_theme()
        self.show()
