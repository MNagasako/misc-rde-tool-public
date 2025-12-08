"""
AI応答待機中のスピナーオーバーレイウィジェット

QTextEdit等のウィジェット上に半透明のスピナーを表示
"""

from qt_compat.widgets import QWidget, QLabel, QVBoxLayout, QPushButton
from qt_compat.core import Qt, QTimer, Signal
from qt_compat.gui import QFont

from classes.theme import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color


class SpinnerOverlay(QWidget):
    """スピナーアニメーション付きオーバーレイウィジェット"""
    cancel_requested = Signal()
    
    # スピナー用の回転文字列パターン
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, parent=None, message: str = "AI応答を待機中...", show_cancel: bool = False, cancel_text: str = "キャンセル"):
        """
        Args:
            parent: 親ウィジェット
            message: 表示するメッセージ
            show_cancel: キャンセルボタンを表示するか
            cancel_text: キャンセルボタンの表示テキスト
        """
        super().__init__(parent)
        
        self._message = message
        self._spinner_index = 0
        self._show_cancel = show_cancel
        self._cancel_text = cancel_text
        
        self._theme_manager = None
        try:
            self._theme_manager = ThemeManager.instance()
            self._theme_manager.theme_changed.connect(self.refresh_theme)
        except Exception:
            self._theme_manager = None
        
        # レイアウト
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # スピナーラベル
        self.spinner_label = QLabel(self)
        font = QFont()
        font.setPointSize(24)
        self.spinner_label.setFont(font)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spinner_label)
        
        # メッセージラベル
        self.message_label = QLabel(message, self)
        message_font = QFont()
        message_font.setPointSize(12)
        self.message_label.setFont(message_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)

        # キャンセルボタン（任意）
        self.cancel_button = None
        if self._show_cancel:
            self.cancel_button = QPushButton(self._cancel_text, self)
            self.cancel_button.setCursor(Qt.PointingHandCursor)
            self.cancel_button.clicked.connect(self.cancel_requested.emit)
            layout.addWidget(self.cancel_button)
        
        # スピナーアニメーション用タイマー
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._update_spinner)
        self._spinner_timer.setInterval(80)  # 80ms間隔
        
        # 初期状態は非表示
        self.hide()

        # 初期テーマ適用
        self._apply_theme()
        
        # 親のサイズに合わせて初期化
        if parent:
            self.setGeometry(parent.rect())
    
    def start(self):
        """スピナーアニメーションを開始"""
        self._spinner_index = 0
        # 親のサイズに再度合わせる
        if self.parent():
            self.setGeometry(self.parent().rect())
        self._spinner_timer.start()
        self._update_spinner()
        self.show()
        self.raise_()  # 最前面に表示
    
    def stop(self):
        """スピナーアニメーションを停止"""
        self._spinner_timer.stop()
        self.hide()
    
    def _update_spinner(self):
        """スピナーフレームを更新"""
        spinner_char = self.SPINNER_FRAMES[self._spinner_index]
        self.spinner_label.setText(spinner_char)
        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
    
    def set_message(self, message: str):
        """
        表示メッセージを更新
        
        Args:
            message: 新しいメッセージ
        """
        self._message = message
        self.message_label.setText(message)
    
    def showEvent(self, event):
        """表示時に親のサイズに合わせる"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().showEvent(event)
    
    def resizeEvent(self, event):
        """親ウィジェットのリサイズに追従"""
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)

    def refresh_theme(self, *_):
        """外部からテーマ更新要求を受けた際の再描画"""
        self._apply_theme()

    def _apply_theme(self):
        """現在のテーマに沿って色を適用"""
        try:
            overlay_bg = get_color(ThemeKey.OVERLAY_BACKGROUND)
            overlay_text = get_color(ThemeKey.OVERLAY_TEXT)
            self.setStyleSheet(f"background-color: {overlay_bg};")
            self.spinner_label.setStyleSheet(f"color: {overlay_text};")
            self.message_label.setStyleSheet(f"color: {overlay_text}; font-weight: bold; padding: 4px 12px;")
            if self.cancel_button:
                self.cancel_button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DANGER_BORDER)};
                        border-radius: 5px;
                        padding: 6px 12px;
                        min-width: 100px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{ background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)}; }}
                    QPushButton:pressed {{ background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)}; }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )
        except Exception:
            # テーマ取得失敗時はデフォルトスタイルにフォールバック
            self.setStyleSheet("background-color: rgba(255, 255, 255, 200);")
            self.spinner_label.setStyleSheet("color: #333333;")
            self.message_label.setStyleSheet("color: #333333;")
            if self.cancel_button:
                self.cancel_button.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 6px 12px;
                        min-width: 100px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #d32f2f; }
                    QPushButton:disabled { background-color: #BDBDBD; color: #E0E0E0; }
                    """
                )
