"""
AIサジェストボタン用のスピナーアニメーション実装

ローディング中を視覚的に示すスピナー付きボタン
"""

from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont


class SpinnerButton(QPushButton):
    """スピナーアニメーション機能付きボタン"""
    
    # スピナー用の回転文字列パターン
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, text: str, parent=None):
        """
        Args:
            text: ボタンのテキスト
            parent: 親ウィジェット
        """
        super().__init__(text, parent)
        
        self._original_text = text
        self._loading_text = ""
        self._is_loading = False
        self._spinner_index = 0
        
        # スピナーアニメーション用タイマー
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._update_spinner)
        self._spinner_timer.setInterval(80)  # 80ms間隔でアニメーション
    
    def start_loading(self, loading_text: str = "処理中"):
        """
        ローディングアニメーションを開始
        
        Args:
            loading_text: ローディング中に表示するテキスト
        """
        if self._is_loading:
            return
        
        self._is_loading = True
        self._loading_text = loading_text
        self._spinner_index = 0
        
        # ボタンを無効化
        self.setEnabled(False)
        
        # スピナーアニメーション開始
        self._spinner_timer.start()
        self._update_spinner()
    
    def stop_loading(self):
        """ローディングアニメーションを停止"""
        if not self._is_loading:
            return
        
        self._is_loading = False
        self._spinner_timer.stop()
        
        # ボタンを元の状態に戻す
        self.setText(self._original_text)
        self.setEnabled(True)
    
    def _update_spinner(self):
        """スピナーフレームを更新"""
        if not self._is_loading:
            return
        
        # 現在のスピナーフレームを取得
        spinner_char = self.SPINNER_FRAMES[self._spinner_index]
        
        # ボタンテキストを更新
        self.setText(f"{spinner_char} {self._loading_text}")
        
        # 次のフレームへ
        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
    
    def set_original_text(self, text: str):
        """
        元のテキストを更新
        
        Args:
            text: 新しいテキスト
        """
        self._original_text = text
        if not self._is_loading:
            self.setText(text)
    
    def is_loading(self) -> bool:
        """
        ローディング中かどうか
        
        Returns:
            ローディング中の場合True
        """
        return self._is_loading
