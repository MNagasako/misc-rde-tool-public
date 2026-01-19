"""
基本情報タブ自動検証機能

基本情報タブが表示された際に、self.jsonの存在と有効性を自動的に確認し、
問題がある場合はユーザーに通知して再ログインを促す機能を提供します。
"""

import os
import logging
from typing import Optional
from qt_compat.widgets import QMessageBox
from qt_compat.core import QTimer

logger = logging.getLogger(__name__)


class BasicInfoTabValidator:
    """基本情報タブの自動検証クラス"""
    
    def __init__(self, parent, controller):
        """
        Args:
            parent: 親ウィジェット
            controller: UIコントローラー
        """
        self.parent = parent
        self.controller = controller
        self.last_validation_time = 0
        self.validation_interval = 60000  # 60秒（ミリ秒）
        
    def validate_on_tab_shown(self):
        """
        タブが表示されたときの検証処理
        
        実行内容:
        1. self.jsonの存在確認
        2. トークンの有効性確認
        3. 問題がある場合はユーザーに通知
        4. 再ログイン促進
        """
        try:
            import time
            current_time = time.time() * 1000  # ミリ秒に変換
            
            # 頻繁な検証を避けるため、最後の検証から一定時間経過している場合のみ実行
            if current_time - self.last_validation_time < self.validation_interval:
                logger.debug("前回の検証から間もないため、スキップします")
                return
            
            self.last_validation_time = current_time
            
            # 非同期で検証を実行（UIをブロックしない）
            QTimer.singleShot(500, self._perform_validation)
            
        except Exception as e:
            logger.error(f"タブ表示時の検証でエラー: {e}")
    
    def _perform_validation(self):
        """実際の検証処理を実行"""
        try:
            from core.bearer_token_manager import BearerTokenManager
            from classes.basic.core.basic_info_logic import fetch_self_info_from_api
            import tempfile
            
            logger.info("[基本情報タブ] 自動検証を開始します")
            
            # 1. トークンの取得と検証
            bearer_token = BearerTokenManager.get_valid_token()
            
            if not bearer_token:
                logger.warning("[基本情報タブ] トークンが取得できません")
                self._show_login_required_message()
                return
            
            # 2. self.jsonの取得を試行（一時ディレクトリに保存）
            temp_dir = tempfile.mkdtemp()
            try:
                result = fetch_self_info_from_api(
                    bearer_token=bearer_token,
                    output_dir=temp_dir,
                    parent_widget=self.parent
                )
                
                if result:
                    logger.info("[基本情報タブ] 認証検証成功")
                    # 成功した場合、output/rde/dataにも保存
                    from config.common import OUTPUT_DIR
                    output_dir = os.path.join(OUTPUT_DIR, "rde", "data")
                    fetch_self_info_from_api(
                        bearer_token=bearer_token,
                        output_dir=output_dir,
                        parent_widget=self.parent
                    )
                    from classes.theme import ThemeKey
                    self._update_status_display("認証OK", ThemeKey.TEXT_SUCCESS)
                else:
                    logger.warning("[基本情報タブ] 認証検証失敗")
                    self._show_authentication_error()
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[基本情報タブ] self.json取得エラー: {error_msg}")
                
                # エラーの種類に応じて適切なメッセージを表示
                if "401" in error_msg or "認証エラー" in error_msg:
                    self._show_authentication_error()
                elif "403" in error_msg or "アクセス拒否" in error_msg:
                    self._show_permission_error()
                elif "ネットワークエラー" in error_msg or "None" in error_msg:
                    self._show_network_error()
                else:
                    self._show_general_error(error_msg)
            finally:
                # 一時ディレクトリを削除
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"[基本情報タブ] 検証処理でエラー: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_login_required_message(self):
        """ログインが必要なメッセージを表示"""
        def show_dialog():
            reply = QMessageBox.question(
                self.parent,
                "ログインが必要",
                "RDEシステムにログインしていません。\n\n"
                "基本情報を取得するには、ログインが必要です。\n"
                "ログインタブに移動しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self._switch_to_login_tab()
        
        QTimer.singleShot(0, show_dialog)
        from classes.theme import ThemeKey
        self._update_status_display("未ログイン", ThemeKey.TEXT_ERROR)
    
    def _show_authentication_error(self):
        """認証エラーメッセージを表示"""
        def show_dialog():
            from core.bearer_token_manager import BearerTokenManager
            
            if BearerTokenManager.request_relogin_if_invalid(self.parent):
                self._switch_to_login_tab()
        
        QTimer.singleShot(0, show_dialog)
        from classes.theme import ThemeKey
        self._update_status_display("認証エラー", ThemeKey.TEXT_ERROR)
    
    def _show_permission_error(self):
        """権限エラーメッセージを表示"""
        def show_dialog():
            QMessageBox.warning(
                self.parent,
                "権限エラー",
                "このユーザーには基本情報取得の権限がありません。\n\n"
                "管理者に連絡して権限を確認してください。"
            )
        
        QTimer.singleShot(0, show_dialog)
        from classes.theme import ThemeKey
        self._update_status_display("権限なし", ThemeKey.TEXT_WARNING)
    
    def _show_network_error(self):
        """ネットワークエラーメッセージを表示"""
        def show_dialog():
            reply = QMessageBox.warning(
                self.parent,
                "ネットワークエラー",
                "RDEサーバーに接続できません。\n\n"
                "ネットワーク接続を確認してください。\n"
                "再試行しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # 少し待ってから再検証
                QTimer.singleShot(2000, self._perform_validation)
        
        QTimer.singleShot(0, show_dialog)
        from classes.theme import ThemeKey
        self._update_status_display("ネットワークエラー", ThemeKey.TEXT_ERROR)
    
    def _show_general_error(self, error_msg):
        """一般的なエラーメッセージを表示"""
        def show_dialog():
            QMessageBox.critical(
                self.parent,
                "エラー",
                f"基本情報の取得でエラーが発生しました:\n\n{error_msg}"
            )
        
        QTimer.singleShot(0, show_dialog)
        from classes.theme import ThemeKey
        self._update_status_display("エラー", ThemeKey.TEXT_ERROR)
    
    def _switch_to_login_tab(self):
        """ログインタブに切り替え"""
        try:
            if hasattr(self.parent, 'tabs'):
                for i in range(self.parent.tabs.count()):
                    if self.parent.tabs.tabText(i) == "ログイン":
                        self.parent.tabs.setCurrentIndex(i)
                        logger.info("ログインタブに切り替えました")
                        return
            
            # タブが見つからない場合
            logger.warning("ログインタブが見つかりません")
            
        except Exception as e:
            logger.error(f"ログインタブへの切り替えエラー: {e}")
    
    def _update_status_display(self, status_text, border_color_key=None):
        """ステータス表示を更新"""
        try:
            # 統合ステータス表示（優先）
            if hasattr(self.controller, 'basic_unified_status_widget'):
                try:
                    self.controller.basic_unified_status_widget.set_auth_status(status_text, border_color_key)
                except Exception as e:
                    logger.error(f"統合ステータスの認証表示更新エラー: {e}")
                return

            # フォールバック: 旧 JSON状況ウィジェットへの追記（互換）
            if hasattr(self.controller, 'json_status_widget'):
                try:
                    status_prefix = f"[認証状況: {status_text}]\n\n"
                    current_text = self.controller.json_status_widget.status_text.toPlainText()

                    if not current_text.startswith("[認証状況:"):
                        new_text = status_prefix + current_text
                    else:
                        lines = current_text.split("\n")
                        new_text = status_prefix + "\n".join(lines[2:])

                    self.controller.json_status_widget.status_text.setPlainText(new_text)
                except Exception as e:
                    logger.error(f"旧ステータス表示更新エラー: {e}")
                
        except Exception as e:
            logger.error(f"ステータス表示更新エラー: {e}")
            import traceback
            traceback.print_exc()

def create_basic_info_tab_validator(parent, controller):
    """
    基本情報タブ検証機能を作成
    
    Args:
        parent: 親ウィジェット
        controller: UIコントローラー
        
    Returns:
        BasicInfoTabValidator: 検証機能のインスタンス
    """
    return BasicInfoTabValidator(parent, controller)
