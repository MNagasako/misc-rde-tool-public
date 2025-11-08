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

    def set_message(self, msg):
        """
        WebView下部のメッセージ表示領域の内容を更新し、ログファイルにも追記。
        """
        self.log_message(msg)
        self.update_label(msg)

    def set_autologin_message(self, msg):
        """
        自動ログイン用メッセージラベルの内容を更新。
        """
        if self.autologin_msg_label:
            self.autologin_msg_label.setText(msg)

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
