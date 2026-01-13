"""
AI応答待機中のスピナーオーバーレイウィジェット

QTextEdit等のウィジェット上に半透明のスピナーを表示
"""

import os
import weakref
from typing import Optional

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
    
    def __init__(
        self,
        parent=None,
        message: str = "AI応答を待機中...",
        show_cancel: bool = False,
        cancel_text: str = "キャンセル",
        *,
        spinner_point_size: int = 24,
        message_point_size: int = 12,
    ):
        """
        Args:
            parent: 親ウィジェット
            message: 表示するメッセージ
            show_cancel: キャンセルボタンを表示するか
            cancel_text: キャンセルボタンの表示テキスト
        """
        super().__init__(parent)

        # pytest 実行中はネイティブクラッシュ要因になりやすいタイマー/raise_ を避け、
        # 画面表示（可視/不可視）だけに限定する。
        self._test_mode = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        
        self._message = message
        self._progress_current: Optional[int] = None
        self._progress_total: Optional[int] = None
        self._progress_prefix: str = ""
        self._spinner_index = 0
        self._show_cancel = show_cancel
        self._cancel_text = cancel_text
        
        self._theme_manager = None
        try:
            self._theme_manager = ThemeManager.instance()
            # NOTE: 長時間のpytest-qtスイートでは、Qt側の破棄タイミングとPython側の参照関係により
            # bound method を直接connectするとネイティブクラッシュが発生し得るため、weakref経由で安全に中継する。
            self_ref = weakref.ref(self)

            def _safe_refresh_theme(*_):
                obj = self_ref()
                if obj is None:
                    return
                try:
                    obj.refresh_theme()
                except RuntimeError:
                    # Internal C++ object already deleted
                    return

            self._theme_changed_handler = _safe_refresh_theme
            self._theme_manager.theme_changed.connect(self._theme_changed_handler)
        except Exception:
            self._theme_manager = None
        
        # レイアウト
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # スピナーラベル
        self.spinner_label = QLabel(self)
        self._spinner_point_size = int(spinner_point_size or 24)
        self._message_point_size = int(message_point_size or 12)

        font = QFont()
        font.setPointSize(self._spinner_point_size)
        self.spinner_label.setFont(font)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spinner_label)
        
        # メッセージラベル
        self.message_label = QLabel(message, self)
        message_font = QFont()
        message_font.setPointSize(self._message_point_size)
        self.message_label.setFont(message_font)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)

        # 進捗ラベル（任意）
        self.progress_label = QLabel("", self)
        try:
            self.progress_label.setAlignment(Qt.AlignCenter)
        except Exception:
            pass
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

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

        # pytest中はタイマーを回さず、最小限のUI更新だけ行う
        if self._test_mode:
            self._spinner_timer.stop()
            self._update_spinner()
            self.show()
            return

        self._spinner_timer.start()
        self._update_spinner()
        self.show()
        self.raise_()  # 最前面に表示
    
    def stop(self):
        """スピナーアニメーションを停止"""
        self._spinner_timer.stop()
        try:
            self.clear_progress()
        except Exception:
            pass
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

    def set_progress(self, current: int | None, total: int | None, *, prefix: str = "処理済み") -> None:
        """予定総数/処理済み数の進捗表示を更新する。

        Args:
            current: 処理済み数（Noneで非表示）
            total: 予定総数（Noneで非表示）
            prefix: 表示プレフィックス
        """
        try:
            if current is None or total is None:
                self.clear_progress()
                return
            cur = int(current)
            tot = int(total)
            if tot <= 0:
                self.clear_progress()
                return
            if cur < 0:
                cur = 0
            if cur > tot:
                cur = tot

            self._progress_current = cur
            self._progress_total = tot
            self._progress_prefix = str(prefix or "").strip()

            shown_prefix = (self._progress_prefix + ": ") if self._progress_prefix else ""
            self.progress_label.setText(f"{shown_prefix}{cur} / {tot}")
            self.progress_label.show()
        except Exception:
            # 表示更新に失敗してもアプリは継続
            try:
                self.clear_progress()
            except Exception:
                pass

    def clear_progress(self) -> None:
        """進捗表示をクリアして非表示にする。"""
        try:
            self._progress_current = None
            self._progress_total = None
            self._progress_prefix = ""
            self.progress_label.setText("")
            self.progress_label.hide()
        except Exception:
            return

    def show_message(self, message: str):
        """後方互換: show_message(message) を set_message に委譲する。"""
        self.set_message(message)

    def set_sizes(self, *, spinner_point_size: int | None = None, message_point_size: int | None = None) -> None:
        """スピナー/メッセージのフォントサイズを変更する（任意）。"""
        try:
            if spinner_point_size is not None:
                self._spinner_point_size = int(spinner_point_size)
                f = self.spinner_label.font()
                f.setPointSize(self._spinner_point_size)
                self.spinner_label.setFont(f)
        except Exception:
            pass
        try:
            if message_point_size is not None:
                self._message_point_size = int(message_point_size)
                f = self.message_label.font()
                f.setPointSize(self._message_point_size)
                self.message_label.setFont(f)
        except Exception:
            pass
    
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
            try:
                self.progress_label.setStyleSheet(f"color: {overlay_text}; padding: 0px 12px 8px 12px;")
            except Exception:
                pass
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
            # テーマ取得失敗時でもアプリは継続（色のハードコードはしない）
            return
