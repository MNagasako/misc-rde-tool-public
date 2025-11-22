#!/usr/bin/env python3
"""
DisplayManager - 表示・メッセージ管理クラス - ARIM RDE Tool v1.13.1

概要:
アプリケーションの表示要素とメッセージ管理を専門に行うクラスです。
UI要素の更新、ログメッセージの表示、ステータス管理を統合的に処理します。

主要機能:
- ステータスメッセージの表示・更新
- ログメッセージの自動表示
- 点滅メッセージによるユーザー通知
- 表示メッセージの長さ調整・最適化
- 複数のラベル要素への統合表示

責務:
UI表示の一元管理により、メインクラスから表示ロジックを分離し、
保守性と可読性を向上させます。
"""

from datetime import datetime
import logging

from classes.theme import get_color, ThemeKey

logger = logging.getLogger("RDE_WebView")

class DisplayManager:
    """
    表示・メッセージ管理専用クラス
    """
    def __init__(self, webview_msg_label=None, log_path=None, max_len=110, autologin_msg_label=None):
        self.webview_msg_label = webview_msg_label
        self.autologin_msg_label = autologin_msg_label
        self.log_path = log_path
        self.max_len = max_len
        # --- 追加: 自動ログインメッセージ点滅用 ---
        self.blinking_state = False
        self.blinking_timer = None
        self._blinking_msg_text = None
        
        # ログイン処理監視用
        self._last_login_message = None
        self._login_message_start_time = None
        self._login_stall_timer = None
        self._login_stall_warning_shown = False

    def set_message(self, msg):
        """
        WebView下部のメッセージ表示領域の内容を更新し、ログファイルにも追記。
        """
        self.log_message(msg)
        self.update_label(msg)

    def set_autologin_message(self, msg):
        """
        自動ログイン用メッセージラベルの内容を更新。
        ログイン処理の停止を監視します。
        """
        if self.autologin_msg_label:
            self.autologin_msg_label.setText(msg)
            
            # ログイン処理監視の開始・更新
            self._monitor_login_message(msg)
    
    def _monitor_login_message(self, msg):
        """
        ログインメッセージを監視し、10秒間同じメッセージの場合は警告を表示
        """
        import time
        from qt_compat.core import QTimer
        
        current_time = time.time()
        
        # メッセージが変わった場合
        if msg != self._last_login_message:
            self._last_login_message = msg
            self._login_message_start_time = current_time
            self._login_stall_warning_shown = False
            
            # 既存のタイマーをクリア
            if self._login_stall_timer:
                self._login_stall_timer.stop()
                self._login_stall_timer = None
            
            # ログイン関連のメッセージの場合のみ監視開始とヘルプラベル表示
            if msg and ("ログイン" in msg or "トークン" in msg or "認証" in msg or "取得中" in msg):
                # login_help_labelを表示
                self._show_login_help_label()
                
                # 10秒後に警告表示をチェック
                if hasattr(self.autologin_msg_label, 'parent'):
                    parent = self.autologin_msg_label.parent()
                    if parent:
                        self._login_stall_timer = QTimer(parent)
                        self._login_stall_timer.setSingleShot(True)
                        self._login_stall_timer.timeout.connect(self._check_login_stall)
                        self._login_stall_timer.start(10000)  # 10秒
        
        # ログイン完了メッセージの場合は監視停止とヘルプラベル非表示
        if ("完了" in msg or "成功" in msg or "ログイン済み" in msg or 
            "両トークン取得済み" in msg or "全機能が利用可能" in msg):
            if self._login_stall_timer:
                self._login_stall_timer.stop()
                self._login_stall_timer = None
            self._login_stall_warning_shown = False
            # login_help_labelを非表示
            self._hide_login_help_label()
    
    def _check_login_stall(self):
        """
        ログイン処理が停止している可能性がある場合に警告を表示
        """
        import time
        
        if self._login_stall_warning_shown:
            return
        
        current_time = time.time()
        
        # 10秒以上同じメッセージが表示されている場合
        if self._login_message_start_time and (current_time - self._login_message_start_time) >= 10:
            self._login_stall_warning_shown = True
            
            # 警告メッセージを追加（autologin_msg_labelに）
            if self.autologin_msg_label:
                current_text = self.autologin_msg_label.text()
                warning_text = f"{current_text}\n\n⚠️ ログイン処理が停止している可能性があります。"
                self.autologin_msg_label.setText(warning_text)
                self.autologin_msg_label.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.NOTIFICATION_WARNING_BACKGROUND)}; "
                    f"color: {get_color(ThemeKey.NOTIFICATION_WARNING_TEXT)}; "
                    f"border: 2px solid {get_color(ThemeKey.NOTIFICATION_WARNING_BORDER)}; "
                    f"padding: 10px; border-radius: 5px; font-weight: bold;"
                )
                
                logger.warning("ログイン処理が10秒間停止しています: %s", self._last_login_message)
            
            # login_help_labelを表示（存在する場合）
            self._show_login_help_label()
    
    def _show_login_help_label(self):
        """ログイン情報ラベルを表示"""
        if hasattr(self.autologin_msg_label, 'parent'):
            parent = self.autologin_msg_label.parent()
            while parent:
                if hasattr(parent, 'login_help_label'):
                    parent.login_help_label.setVisible(True)
                    break
                parent = parent.parent() if hasattr(parent, 'parent') else None
    
    def _hide_login_help_label(self):
        """ログイン情報ラベルを非表示"""
        if hasattr(self.autologin_msg_label, 'parent'):
            parent = self.autologin_msg_label.parent()
            while parent:
                if hasattr(parent, 'login_help_label'):
                    parent.login_help_label.setVisible(False)
                    break
                parent = parent.parent() if hasattr(parent, 'parent') else None

    # --- 追加: 自動ログインメッセージ点滅制御 ---
    def start_blinking_msg(self, parent):
        if self.blinking_timer is not None:
            return  # すでに点滅中
        
        # 安全性チェック: parentが削除されていないか確認
        try:
            if hasattr(parent, 'isHidden') and parent.isHidden():
                return
        except RuntimeError:
            # オブジェクトが削除されている場合は処理をスキップ
            return
            
        from qt_compat.core import QTimer
        self.blinking_state = True
        try:
            self.blinking_timer = QTimer(parent)
            self.blinking_timer.setInterval(400)
            self.blinking_timer.timeout.connect(self.toggle_blinking_msg)
            self.blinking_timer.start()
        except RuntimeError:
            # タイマー作成に失敗した場合は処理をスキップ
            self.blinking_timer = None
            return
            
        if self.autologin_msg_label:
            self.autologin_msg_label.setVisible(True)

    def stop_blinking_msg(self):
        if self.blinking_timer is not None:
            self.blinking_timer.stop()
            self.blinking_timer = None
            if self.autologin_msg_label:
                self.autologin_msg_label.setVisible(True)
        self.blinking_state = False
        self._blinking_msg_text = None

    def toggle_blinking_msg(self):
        if self.blinking_state:
            if self.autologin_msg_label:
                # 表示時は元のテキスト
                self.autologin_msg_label.setText(self._blinking_msg_text if self._blinking_msg_text else self.autologin_msg_label.text())
                self.autologin_msg_label.setVisible(True)
            self.blinking_state = False
        else:
            if self.autologin_msg_label:
                # 非表示時は空白に
                if not self._blinking_msg_text:
                    self._blinking_msg_text = self.autologin_msg_label.text()
                self.autologin_msg_label.setText(' ')
                self.autologin_msg_label.setVisible(True)
            self.blinking_state = True

    def log_message(self, msg):
        """
        ログファイルにメッセージを追記
        """
        if not self.log_path:
            return
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(f"{now}\t{msg}\n")
        except Exception as e:
            logger.warning(f"webview_message.log書き込み失敗: {e}")

    def update_label(self, msg):
        """
        メッセージをUIラベルに表示（長すぎる場合は省略）
        """
        display_msg = msg
        if msg and len(msg) > self.max_len:
            display_msg = msg[:self.max_len] + '...'
        if self.webview_msg_label:
            self.webview_msg_label.setText(display_msg)
