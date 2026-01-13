"""
データポータル認証情報管理モジュール

OS keyringを使用した安全な認証情報の保存・取得を提供
テスト環境と本番環境の2つの設定を個別に管理
"""

import logging
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

try:
    import keyring
    import keyring.errors
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

from classes.managers.log_manager import get_logger

logger = get_logger("DataPortal.AuthManager")


@dataclass
class PortalCredentials:
    """データポータル認証情報"""
    basic_username: str  # Basic認証ユーザー名
    basic_password: str  # Basic認証パスワード
    login_username: str  # ログインユーザー名（メールアドレス等）
    login_password: str  # ログインパスワード
    

class AuthManager:
    """
    データポータル認証情報管理クラス
    
    機能:
    - OS keyringを使用した安全な認証情報保存
    - テスト環境/本番環境の個別管理
    - 認証情報の保存・取得・削除
    """
    
    SERVICE_NAME = "ARIM_RDE_TOOL_DataPortal"
    ENV_TEST = "test"
    ENV_PRODUCTION = "production"
    
    def __init__(self):
        """初期化"""
        self.keyring_available = KEYRING_AVAILABLE
        
        if not self.keyring_available:
            logger.warning("keyring ライブラリが利用できません。認証情報は安全に保存されません。")
    
    def is_available(self) -> bool:
        """
        keyringが利用可能かチェック
        
        Returns:
            bool: keyringが利用可能な場合True
        """
        return self.keyring_available
    
    def _get_key_name(self, environment: str, credential_type: str) -> str:
        """
        keyring用のキー名を生成
        
        Args:
            environment: 環境識別子 ('test' or 'production')
            credential_type: 認証情報タイプ ('basic_user', 'basic_pass', 'login_user', 'login_pass')
        
        Returns:
            str: keyring用のキー名
        """
        return f"{environment}_{credential_type}"
    
    def store_credentials(self, environment: str, credentials: PortalCredentials) -> bool:
        """
        認証情報をkeyringに保存
        
        Args:
            environment: 'test' または 'production'
            credentials: 保存する認証情報
        
        Returns:
            bool: 保存成功時True
        """
        if not self.keyring_available:
            logger.warning("keyring が利用できないため、認証情報を保存できません。")
            return False
        
        try:
            # Basic認証情報を保存
            keyring.set_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "basic_user"),
                credentials.basic_username
            )
            keyring.set_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "basic_pass"),
                credentials.basic_password
            )
            
            # ログイン情報を保存
            keyring.set_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "login_user"),
                credentials.login_username
            )
            keyring.set_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "login_pass"),
                credentials.login_password
            )
            
            logger.info(f"認証情報を保存しました: {environment} 環境")
            return True
            
        except keyring.errors.PasswordSetError as e:
            logger.error(f"認証情報の保存に失敗しました: {e}")
            return False
        except Exception as e:
            logger.error(f"予期しないエラーが発生しました: {e}")
            return False
    
    def get_credentials(self, environment: str) -> Optional[PortalCredentials]:
        """
        保存された認証情報を取得
        
        Args:
            environment: 'test' または 'production'
        
        Returns:
            PortalCredentials: 認証情報 (取得できない場合None)
        """
        if not self.keyring_available:
            logger.debug("keyring が利用できません。")
            return None
        
        try:
            # Basic認証情報を取得
            basic_user = keyring.get_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "basic_user")
            )
            basic_pass = keyring.get_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "basic_pass")
            )
            
            # ログイン情報を取得
            login_user = keyring.get_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "login_user")
            )
            login_pass = keyring.get_password(
                self.SERVICE_NAME,
                self._get_key_name(environment, "login_pass")
            )
            
            # ログイン情報は必須 / Basic認証は任意
            login_user_text = (login_user or "").strip()
            login_pass_text = (login_pass or "").strip()

            if login_user_text and login_pass_text:
                logger.info(f"認証情報を取得しました: {environment} 環境")
                return PortalCredentials(
                    basic_username=(basic_user or ""),
                    basic_password=(basic_pass or ""),
                    login_username=login_user_text,
                    login_password=login_pass_text,
                )

            logger.debug(f"認証情報が不完全です: {environment} 環境")
            return None
            
        except keyring.errors.KeyringError as e:
            logger.error(f"認証情報の取得に失敗しました: {e}")
            return None
        except Exception as e:
            logger.error(f"予期しないエラーが発生しました: {e}")
            return None
    
    def delete_credentials(self, environment: str) -> bool:
        """
        保存された認証情報を削除
        
        Args:
            environment: 'test' または 'production'
        
        Returns:
            bool: 削除成功時True
        """
        if not self.keyring_available:
            logger.warning("keyring が利用できません。")
            return False
        
        try:
            # すべての認証情報を削除
            for cred_type in ["basic_user", "basic_pass", "login_user", "login_pass"]:
                try:
                    keyring.delete_password(
                        self.SERVICE_NAME,
                        self._get_key_name(environment, cred_type)
                    )
                except keyring.errors.PasswordDeleteError:
                    # 該当の認証情報が存在しない場合は無視
                    pass
            
            logger.info(f"認証情報を削除しました: {environment} 環境")
            return True
            
        except Exception as e:
            logger.error(f"認証情報の削除に失敗しました: {e}")
            return False
    
    def has_credentials(self, environment: str) -> bool:
        """
        認証情報が保存されているかチェック
        
        Args:
            environment: 'test' または 'production'
        
        Returns:
            bool: 認証情報が保存されている場合True
        """
        credentials = self.get_credentials(environment)
        return credentials is not None


# シングルトンインスタンス
_auth_manager_instance = None


def get_auth_manager() -> AuthManager:
    """
    AuthManagerのシングルトンインスタンスを取得
    
    Returns:
        AuthManager: シングルトンインスタンス
    """
    global _auth_manager_instance
    if _auth_manager_instance is None:
        _auth_manager_instance = AuthManager()
    return _auth_manager_instance
