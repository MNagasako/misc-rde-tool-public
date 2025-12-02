"""
AI応答待機中のスピナーオーバーレイウィジェット

QTextEdit等のウィジェット上に半透明のスピナーを表示
"""

from qt_compat.widgets import QWidget, QLabel, QVBoxLayout, QPushButton
from qt_compat.core import Qt, QTimer, Signal
from qt_compat.gui import QFont


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
        
        # 半透明の白背景
        self.setStyleSheet("background-color: rgba(255, 255, 255, 200);")
        
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
            self.cancel_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 12px;
                    min-width: 100px;
                }
                QPushButton:hover { background-color: #d32f2f; }
                QPushButton:disabled { background-color: #BDBDBD; color: #E0E0E0; }
                """
            )
            self.cancel_button.clicked.connect(self.cancel_requested.emit)
            layout.addWidget(self.cancel_button)
        
        # スピナーアニメーション用タイマー
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._update_spinner)
        self._spinner_timer.setInterval(80)  # 80ms間隔
        
        # 初期状態は非表示
        self.hide()
        
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
