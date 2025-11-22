"""
Bearer Token統一管理クラス v1.0

概要:
Bearer Tokenの取得・検証・再ログイン促進を統一的に管理し、
アプリ全体でのAPI認証を簡素化・堅牢化するクラスです。

主要機能:
- ファイルベース（output/.private/bearer_token.txt）からの統一トークン取得
- self.json API呼び出しによるトークン有効性検証
- 無効時の再ログイン促進（ユーザーへの明確な通知）
- エラーハンドリングの統一

設計思想:
複数箇所に散在するトークン取得・検証ロジックを一元化し、
保守性・可読性・信頼性を向上させます。
"""

import os
import logging
from typing import Optional
from config.common import BEARER_TOKEN_FILE, get_dynamic_file_path

logger = logging.getLogger("BearerTokenManager")


class BearerTokenManager:
    """Bearer Token統一管理クラス"""
    
    @staticmethod
    def get_current_token() -> Optional[str]:
        """
        現在有効なBearer Tokenを取得（レガシー互換）
        
        Returns:
            str: 有効なBearer Token、無効または存在しない場合はNone
        """
        return BearerTokenManager.get_valid_token()
    
    @staticmethod
    def get_valid_token() -> Optional[str]:
        """
        有効なBearer Tokenを取得
        
        ファイルからトークンを読み込み、有効性を検証してから返す
        
        Returns:
            str: 有効なBearer Token、無効または存在しない場合はNone
        """
        print("[TOKEN-DEBUG] get_valid_token() 開始")
        try:
            print("[TOKEN-DEBUG] logger.info呼び出し前")
            logger.info("[TOKEN] 有効なBearerトークン取得を開始")
            print("[TOKEN-DEBUG] logger.info呼び出し後")
            
            # 1. ファイルからトークンを読み込み
            print("[TOKEN-DEBUG] _load_token_from_file()呼び出し前")
            token = BearerTokenManager._load_token_from_file()
            print(f"[TOKEN-DEBUG] _load_token_from_file()結果: {token[:20] if token else 'None'}...")
            if not token:
                logger.warning("[TOKEN] Bearerトークンファイルが存在しないか空です")
                print("[TOKEN-DEBUG] トークンファイルが存在しないか空、Noneを返却")
                return None
            
            logger.info(f"[TOKEN] ファイルから読み込んだトークン: {token[:20]}...")
            
            # 2. トークンの有効性を検証
            logger.debug("[TOKEN] トークンの有効性を検証中...")
            print("[TOKEN-DEBUG] validate_token()呼び出し前")
            is_valid = BearerTokenManager.validate_token(token)
            print(f"[TOKEN-DEBUG] validate_token()結果: {is_valid}")
            if is_valid:
                logger.info("[TOKEN] Bearerトークン検証成功")
                print(f"[TOKEN-DEBUG] 検証成功、トークン返却: {token[:20]}...")
                return token
            else:
                logger.warning("[TOKEN] Bearerトークンが無効です")
                print("[TOKEN-DEBUG] 検証失敗、Noneを返却")
                return None
                
        except Exception as e:
            logger.error(f"[TOKEN] Bearerトークン取得エラー: {e}", exc_info=True)
            print(f"[TOKEN-DEBUG] 例外発生: {e}")
            return None
    
    @staticmethod
    def _load_token_from_file() -> Optional[str]:
        """
        ファイルからBearer Tokenを読み込み（内部用）
        複数ホスト対応のJSONファイルを優先し、レガシーファイルをフォールバックとする
        
        Returns:
            str: ファイルから読み込んだトークン、失敗時はNone
        """
        try:
            # v1.18.3: load_bearer_token関数を使用（複数ホスト対応）
            from config.common import load_bearer_token
            token = load_bearer_token('rde.nims.go.jp')
            if token:
                logger.debug("[TOKEN] 複数ホスト対応ファイルからトークン読み込み成功")
                return token
            
            logger.warning("[TOKEN] Bearerトークンファイルが見つからないか空です")
            return None
            
        except Exception as e:
            logger.error(f"[TOKEN] Bearerトークンファイル読み込みエラー: {e}")
            return None
    
    @staticmethod
    def validate_token(token: str) -> bool:
        """
        Bearer Tokenの有効性をself.json API呼び出しで検証
        
        Args:
            token: 検証するBearer Token
            
        Returns:
            bool: 有効時True、無効時False
        """
        if not token:
            return False
        
        try:
            from classes.utils.api_request_helper import api_request
            
            # self.json API呼び出しでトークン検証
            url = "https://rde-user-api.nims.go.jp/users/self"
            headers = {
                'Accept': 'application/vnd.api+json',
                'Host': 'rde-user-api.nims.go.jp',
                'Origin': 'https://rde.nims.go.jp',
                'Referer': 'https://rde.nims.go.jp/'
            }
            
            response = api_request("GET", url, bearer_token=token, headers=headers, timeout=10)
            
            if response is None:
                logger.warning("Bearer Token検証: APIリクエスト失敗")
                return False
            
            if response.status_code == 200:
                logger.debug("Bearer Token検証成功")
                return True
            elif response.status_code == 401:
                logger.warning("Bearer Token検証失敗: 認証エラー (401)")
                return False
            else:
                logger.warning(f"Bearer Token検証失敗: HTTPステータス {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Bearer Token検証エラー: {e}")
            return False
    
    @staticmethod
    def request_relogin_if_invalid(parent_widget=None) -> bool:
        """
        無効トークン時の再ログイン促進
        
        Args:
            parent_widget: メッセージボックスの親ウィジェット
            
        Returns:
            bool: ユーザーが再ログインを選択した場合True
        """
        try:
            from PyQt5.QtWidgets import QMessageBox
            
            if parent_widget is None:
                # フォールバック: コンソールメッセージのみ
                logger.error("Bearer Tokenが無効です。アプリを再起動してログインしてください。")
                return False
            
            # ユーザーへの再ログイン促進ダイアログ
            msg_box = QMessageBox(parent_widget)
            msg_box.setWindowTitle("認証エラー")
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(
                "Bearer Tokenが無効または期限切れです。\n"
                "RDEシステムへの再ログインが必要です。"
            )
            msg_box.setInformativeText(
                "「再ログイン」をクリックしてログイン画面を開くか、\n"
                "「キャンセル」で操作を中止してください。"
            )
            
            relogin_button = msg_box.addButton("再ログイン", QMessageBox.AcceptRole)
            cancel_button = msg_box.addButton("キャンセル", QMessageBox.RejectRole)
            
            msg_box.exec_()
            
            if msg_box.clickedButton() == relogin_button:
                logger.info("ユーザーが再ログインを選択しました")
                # 実際のログイン処理は呼び出し元で実装
                return True
            else:
                logger.info("ユーザーが再ログインをキャンセルしました")
                return False
                
        except Exception as e:
            logger.error(f"再ログイン促進エラー: {e}")
            return False
    
    @staticmethod
    def get_token_with_relogin_prompt(parent_widget=None) -> Optional[str]:
        """
        トークン取得（無効時は再ログイン促進付き）
        
        Args:
            parent_widget: 再ログインダイアログの親ウィジェット
            
        Returns:
            str: 有効なBearer Token、取得失敗時はNone
        """
        print("[TOKEN-DEBUG] get_token_with_relogin_prompt() 開始")
        print("[TOKEN-DEBUG] get_valid_token()呼び出し前")
        token = BearerTokenManager.get_valid_token()
        print(f"[TOKEN-DEBUG] get_valid_token()結果: {token[:20] if token else 'None'}...")
        
        if token:
            print(f"[TOKEN-DEBUG] トークン取得成功、返却: {token[:20]}...")
            return token
        
        # 無効時は再ログイン促進
        print("[TOKEN-DEBUG] トークン取得失敗、再ログイン促進を実行")
        if BearerTokenManager.request_relogin_if_invalid(parent_widget):
            # 再ログイン後の再試行（実装は呼び出し元で行う）
            logger.info("再ログイン促進を実行しました")
            print("[TOKEN-DEBUG] 再ログイン促進完了")
        
        print("[TOKEN-DEBUG] None返却")
        return None