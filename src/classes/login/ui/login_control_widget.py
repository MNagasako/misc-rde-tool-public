#!/usr/bin/env python3
"""
ログイン機能コントロールウィジェット（v2.0.3: 簡素化版）
"""

import logging
from typing import Optional

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QPushButton, 
        QMessageBox, QGroupBox
    )
    from qt_compat.core import QUrl
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

from classes.managers.app_config_manager import get_config_manager
from classes.core.credential_store import get_credential_store, decide_autologin_source, perform_health_check

logger = logging.getLogger(__name__)


class LoginControlWidget(QWidget):
    """ログイン機能コントロールウィジェット"""
    
    def __init__(self, parent=None, webview=None):
        QWidget.__init__(self, parent)
        
        if not PYQT5_AVAILABLE:
            logger.warning("PyQt5が利用できないため、ログインコントロールウィジェットを初期化できません")
            return
        
        self.parent_widget = parent
        self.webview = webview
        self.config_manager = get_config_manager()
        
        self.init_ui()
    
    def init_ui(self):
        """UI初期化（v2.0.3: 簡素化・ログアウトボタン削除）"""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # グループボックス
        group = QGroupBox()
        group.setStyleSheet("""
            QGroupBox {
                background-color: #f0f8ff;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(5)
        
        # 自動ログイントグルボタン
        self.toggle_autologin_button = QPushButton("自動ログイン")
        self.toggle_autologin_button.clicked.connect(self.toggle_autologin)
        self.toggle_autologin_button.setMinimumHeight(30)
        self.toggle_autologin_button.setCheckable(True)
        group_layout.addWidget(self.toggle_autologin_button)
        
        # ログイン実行ボタン（v2.0.3: 手動ログイン開始用）
        self.execute_login_button = QPushButton("ログイン実行")
        self.execute_login_button.clicked.connect(self.execute_login)
        self.execute_login_button.setMinimumHeight(30)
        self.execute_login_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        group_layout.addWidget(self.execute_login_button)
        
        layout.addWidget(group)
        layout.addStretch()
        
        # 初期化時にUIを更新
        self._update_ui_state()
    
    def update_autologin_button_state(self):
        """自動ログインボタン状態更新（後方互換性のため）"""
        self._update_ui_state()
    
    def _update_ui_state(self):
        """UI状態を更新"""
        try:
            # 自動ログインボタン更新
            autologin_enabled = self.config_manager.get("autologin.autologin_enabled", False)
            self.toggle_autologin_button.setChecked(autologin_enabled)
            
            if autologin_enabled:
                self.toggle_autologin_button.setText("自動ログイン✓")
                self.toggle_autologin_button.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        font-weight: bold;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                    QPushButton:checked {
                        background-color: #2E7D32;
                    }
                """)
            else:
                self.toggle_autologin_button.setText("自動ログイン")
                self.toggle_autologin_button.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        font-weight: bold;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #1976D2;
                    }
                """)
                
        except Exception as e:
            logger.error(f"UI状態更新エラー: {e}")
    
    def toggle_autologin(self):
        """自動ログインの有効/無効を切り替え"""
        try:
            new_state = self.toggle_autologin_button.isChecked()
            
            if new_state:
                health_check = perform_health_check()
                storage_pref = self.config_manager.get("autologin.credential_storage", "auto")
                actual_source = decide_autologin_source(storage_pref, health_check)
                
                if actual_source == "none":
                    QMessageBox.warning(
                        self,
                        "認証情報なし",
                        "「設定」タブで認証情報を保存してください。"
                    )
                    self.toggle_autologin_button.setChecked(False)
                    return
                
                store = get_credential_store(actual_source)
                if store:
                    creds = store.load_credentials()  # get_credentials → load_credentials
                    if not creds:
                        QMessageBox.warning(
                            self,
                            "認証情報なし",
                            "「設定」タブで認証情報を保存してください。"
                        )
                        self.toggle_autologin_button.setChecked(False)
                        return
            
            self.config_manager.set("autologin.autologin_enabled", new_state)
            self.config_manager.save_to_file()
            
            self._update_ui_state()
            
            msg = "自動ログインを有効にしました。" if new_state else "自動ログインを無効にしました。"
            QMessageBox.information(self, "設定変更", msg)
            
            logger.info(f"自動ログイン設定変更: {'有効' if new_state else '無効'}")
            
        except Exception as e:
            logger.error(f"自動ログイン切り替えエラー: {e}")
            QMessageBox.critical(self, "エラー", f"設定の変更に失敗しました: {e}")
    
    def execute_login(self):
        """
        ログイン実行（v2.0.3: 手動トリガー）
        自動ログインが有効な場合は自動ログインプロセスを実行
        
        v2.0.6: ログインボタン押下時に既存トークンを無効化
        """
        try:
            logger.info("[LOGIN-EXECUTE] ログイン実行ボタンがクリックされました")
            
            # 自動ログインが有効か確認
            autologin_enabled = self.config_manager.get("autologin.autologin_enabled", False)
            logger.info(f"[LOGIN-EXECUTE] 自動ログイン設定: {autologin_enabled}")
            
            if not autologin_enabled:
                logger.warning("[LOGIN-EXECUTE] 自動ログインが無効です")
                QMessageBox.warning(
                    self,
                    "自動ログイン無効",
                    "自動ログインが無効です。\n\n"
                    "先に「自動ログイン」ボタンをONにして、認証情報を設定してください。"
                )
                return
            
            # 親ウィジェットとLoginManagerを確認
            if not hasattr(self.parent_widget, 'login_manager'):
                logger.error("[LOGIN-EXECUTE] LoginManagerが見つかりません")
                QMessageBox.critical(
                    self,
                    "エラー",
                    "ログイン管理機能が利用できません。"
                )
                return
            
            login_manager = self.parent_widget.login_manager
            
            # v2.0.6: 既存トークンを無効化（再ログイン時のトークン取得を確実に）
            logger.info("[LOGIN-EXECUTE] 既存トークンを無効化します")
            invalidate_success = login_manager.invalidate_all_tokens()
            if invalidate_success:
                logger.info("[LOGIN-EXECUTE] ✅ トークン無効化完了")
            else:
                logger.warning("[LOGIN-EXECUTE] ⚠️ トークン無効化に一部失敗しました（継続）")
            
            # トークン取得状態を確認
            logger.info("[LOGIN-EXECUTE] 現在のトークン状態を確認中...")
            rde_exists, material_exists = login_manager.check_tokens_acquired()
            logger.info(f"[LOGIN-EXECUTE] RDEトークン: {rde_exists}, マテリアルトークン: {material_exists}")
            
            if rde_exists and material_exists:
                logger.info("[LOGIN-EXECUTE] 両方のトークンが既に存在します")
                QMessageBox.information(
                    self,
                    "ログイン済み",
                    "既にログイン済みです。\n\n"
                    "両方のトークンが取得されています。"
                )
                return
            
            # 自動ログインプロセスを開始
            logger.info("[LOGIN-EXECUTE] 自動ログインプロセスを開始します")
            logger.debug(f"[LOGIN-EXECUTE] LoginManager: {login_manager}")
            logger.debug(f"[LOGIN-EXECUTE] credential_source: {getattr(login_manager, 'credential_source', 'N/A')}")
            logger.debug(f"[LOGIN-EXECUTE] credential_store: {getattr(login_manager, 'credential_store', 'N/A')}")
            
            # ログイン中フラグをセット
            login_manager._login_in_progress = True
            logger.info("[LOGIN-EXECUTE] _login_in_progress = True")
            
            # メッセージラベルを更新
            if hasattr(self.parent_widget, 'autologin_msg_label'):
                self.parent_widget.autologin_msg_label.setText("🔄 自動ログイン中...")
                self.parent_widget.autologin_msg_label.setVisible(True)
                logger.info("[LOGIN-EXECUTE] メッセージラベル更新完了")
            
            # トークン取得を開始
            logger.info("[LOGIN-EXECUTE] ensure_both_tokens() を呼び出します")
            from qt_compat.core import QTimer
            QTimer.singleShot(500, lambda: self._start_token_acquisition(login_manager))
            
            QMessageBox.information(
                self,
                "ログイン開始",
                "自動ログインを開始しました。\n\n"
                "処理完了までお待ちください。"
            )
            
        except Exception as e:
            logger.error(f"[LOGIN-EXECUTE] ログイン実行エラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"ログイン処理の開始に失敗しました:\n{e}")
    
    def _start_token_acquisition(self, login_manager):
        """トークン取得を開始（デバッグログ付き）"""
        try:
            logger.info("[TOKEN-ACQ] トークン取得プロセス開始")
            logger.debug(f"[TOKEN-ACQ] LoginManager instance: {id(login_manager)}")
            
            # ensure_both_tokensメソッドの存在確認
            if not hasattr(login_manager, 'ensure_both_tokens'):
                logger.error("[TOKEN-ACQ] ensure_both_tokensメソッドが存在しません")
                if hasattr(self.parent_widget, 'autologin_msg_label'):
                    self.parent_widget.autologin_msg_label.setText("❌ ログイン失敗")
                return
            
            logger.info("[TOKEN-ACQ] ensure_both_tokens() を実行")
            login_manager.ensure_both_tokens()
            logger.info("[TOKEN-ACQ] ensure_both_tokens() 実行完了")
            
        except Exception as e:
            logger.error(f"[TOKEN-ACQ] トークン取得エラー: {e}", exc_info=True)
            if hasattr(self.parent_widget, 'autologin_msg_label'):
                self.parent_widget.autologin_msg_label.setText(f"❌ ログイン失敗: {e}")


def create_login_control_widget(parent=None, webview=None):
    """ログインコントロールウィジェットを作成"""
    return LoginControlWidget(parent, webview)
