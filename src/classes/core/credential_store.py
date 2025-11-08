#!/usr/bin/env python3
"""
認証情報ストア - ARIM RDE Tool v1.16
安全な認証情報の保存・取得・削除を提供する抽象化レイヤー

主要機能:
- OSキーチェーン（Windows Credential Manager, macOS Keychain, Linux Secret Service）
- 暗号化ファイル（AES-GCM + DPAPI/キーチェーン鍵保護）
- レガシーファイル（input/login.txt 互換）
- 認証情報のマスキング・ゼロ化
"""

import logging
import os
import json
import platform
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class CredentialInfo:
    """認証情報データクラス"""
    username: str
    password: str
    login_mode: Optional[str] = None
    updated_at: Optional[str] = None
    
    def mask_password(self) -> 'CredentialInfo':
        """パスワードをマスクしたコピーを返す"""
        return CredentialInfo(
            username=self.username,
            password="****" if self.password else "",
            login_mode=self.login_mode,
            updated_at=self.updated_at
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（パスワード除外）"""
        return {
            "username": self.username,
            "login_mode": self.login_mode,
            "updated_at": self.updated_at
        }

class CredentialStoreHealthCheck:
    """認証情報ストアのヘルスチェック結果"""
    
    def __init__(self):
        self.os_ok = False
        self.enc_ok = False
        self.legacy_exists = False
        self.os_error: Optional[str] = None
        self.enc_error: Optional[str] = None
        self.legacy_path: Optional[str] = None
        
        # 下位互換性のための別名
        self.keyring_available = False
        self.encryption_available = False
        self.legacy_file_exists = False
        self.recommended_source = "auto"
        self.error: Optional[str] = None
    
    def update_compatibility_attrs(self):
        """下位互換性のための属性更新"""
        self.keyring_available = self.os_ok
        self.encryption_available = self.enc_ok
        self.legacy_file_exists = self.legacy_exists
        
        # 推奨ソースの決定
        if self.os_ok:
            self.recommended_source = "os_keychain"
        elif self.enc_ok:
            self.recommended_source = "encrypted_file"
        elif self.legacy_exists:
            self.recommended_source = "legacy_file"
        else:
            self.recommended_source = "none"
        
        # エラーメッセージの統合
        errors = []
        if self.os_error:
            errors.append(f"OSキーチェーン: {self.os_error}")
        if self.enc_error:
            errors.append(f"暗号化ファイル: {self.enc_error}")
        
        self.error = "; ".join(errors) if errors else None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式で結果を返す"""
        return {
            "os_keychain": {
                "available": self.os_ok,
                "error": self.os_error
            },
            "encrypted_file": {
                "available": self.enc_ok,
                "error": self.enc_error
            },
            "legacy_file": {
                "exists": self.legacy_exists,
                "path": self.legacy_path
            }
        }

class BaseCredentialStore(ABC):
    """認証情報ストアの基底クラス"""
    
    SERVICE_NAME = "ARIM_RDE_Tool"
    
    @abstractmethod
    def is_available(self) -> bool:
        """ストアが利用可能かチェック"""
        pass
    
    @abstractmethod
    def save_credentials(self, creds: CredentialInfo) -> bool:
        """認証情報を保存"""
        pass
    
    @abstractmethod
    def load_credentials(self) -> Optional[CredentialInfo]:
        """認証情報を読み込み"""
        pass
    
    @abstractmethod
    def delete_credentials(self) -> bool:
        """認証情報を削除"""
        pass
    
    def get_store_type(self) -> str:
        """ストアタイプを返す"""
        return self.__class__.__name__

class KeyringCredentialStore(BaseCredentialStore):
    """OSキーチェーン使用の認証情報ストア"""
    
    def __init__(self):
        self._keyring = None
        try:
            import keyring
            self._keyring = keyring
        except ImportError:
            logger.warning("keyringライブラリが利用できません")
    
    def is_available(self) -> bool:
        """keyringが利用可能かチェック"""
        if not self._keyring:
            return False
        
        try:
            # テスト用のダミー操作で利用可能性を確認
            backend = self._keyring.get_keyring()
            if backend and hasattr(backend, 'priority') and backend.priority > 0:
                return True
        except Exception as e:
            logger.debug(f"keyring利用可能性チェック失敗: {e}")
        
        return False
    
    def save_credentials(self, creds: CredentialInfo) -> bool:
        """認証情報をキーチェーンに保存"""
        if not self.is_available():
            logger.error("keyringが利用できません")
            return False
        
        try:
            logger.info(f"キーチェーンへの認証情報保存開始 - ユーザー: {creds.username}")
            
            # パスワードを保存
            self._keyring.set_password(
                self.SERVICE_NAME, 
                creds.username, 
                creds.password
            )
            logger.info(f"パスワード保存完了 - サービス: {self.SERVICE_NAME}, ユーザー: {creds.username}")
            
            # 保存確認テスト
            test_password = self._keyring.get_password(self.SERVICE_NAME, creds.username)
            if test_password != creds.password:
                logger.error(f"パスワード保存確認失敗 - 期待値と実際値が異なります")
                return False
            logger.info("パスワード保存確認テスト: 成功")
            
            # メタデータを保存
            metadata = {
                "login_mode": creds.login_mode,
                "updated_at": datetime.now().isoformat()
            }
            self._keyring.set_password(
                f"{self.SERVICE_NAME}_meta",
                creds.username,
                json.dumps(metadata)
            )
            logger.info(f"メタデータ保存完了")
            
            # メタデータ保存確認テスト
            test_metadata_str = self._keyring.get_password(f"{self.SERVICE_NAME}_meta", creds.username)
            if test_metadata_str:
                try:
                    test_metadata = json.loads(test_metadata_str)
                    if test_metadata.get("login_mode") == creds.login_mode:
                        logger.info("メタデータ保存確認テスト: 成功")
                    else:
                        logger.warning("メタデータ保存確認テスト: ログインモードが一致しません")
                except json.JSONDecodeError:
                    logger.warning("メタデータ保存確認テスト: JSON解析エラー")
            else:
                logger.warning("メタデータ保存確認テスト: メタデータが読み込めませんでした")
            
            logger.info(f"認証情報をキーチェーンに保存: {creds.username}")
            
            # 最後に保存したユーザー名を設定ファイルに記録（次回の検索用）
            try:
                from classes.managers.app_config_manager import get_config_manager
                config_manager = get_config_manager()
                if config_manager:
                    config_manager.set("autologin.last_username", creds.username)
                    config_manager.save()
                    logger.info(f"設定ファイルに最後のユーザー名を記録: {creds.username}")
            except Exception as e:
                logger.debug(f"ユーザー名記録失敗: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"キーチェーン保存エラー: {e}")
            return False
    
    def load_credentials(self) -> Optional[CredentialInfo]:
        """認証情報をキーチェーンから読み込み"""
        if not self.is_available():
            logger.error("keyringが利用できません")
            return None
        
        try:
            logger.info("キーチェーンからの認証情報読み込み開始")
            
            # 既存のユーザー名を検索（メタデータから）
            username = self._find_stored_username()
            if not username:
                logger.info("保存されたユーザー名が見つかりませんでした")
                return None
            
            logger.info(f"検索されたユーザー名: {username}")
            
            # パスワードを取得
            password = self._keyring.get_password(self.SERVICE_NAME, username)
            if not password:
                logger.warning(f"ユーザー {username} のパスワードが見つかりませんでした")
                return None
            
            logger.info(f"パスワード取得成功: {username} (長さ: {len(password)}文字)")
            
            # メタデータを取得
            metadata_str = self._keyring.get_password(f"{self.SERVICE_NAME}_meta", username)
            metadata = {}
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                    logger.info(f"メタデータ取得成功: {metadata}")
                except json.JSONDecodeError:
                    logger.warning("メタデータのJSON解析に失敗しました")
            else:
                logger.info("メタデータが見つかりませんでした")
            
            credential_info = CredentialInfo(
                username=username,
                password=password,
                login_mode=metadata.get("login_mode"),
                updated_at=metadata.get("updated_at")
            )
            
            logger.info(f"認証情報読み込み完了: ユーザー={username}, モード={credential_info.login_mode}")
            return credential_info
            
        except Exception as e:
            logger.error(f"キーチェーン読み込みエラー: {e}")
            return None
    
    def delete_credentials(self) -> bool:
        """認証情報をキーチェーンから削除"""
        if not self.is_available():
            return False
        
        try:
            username = self._find_stored_username()
            if not username:
                return True  # 削除対象がない場合は成功とみなす
            
            # パスワードとメタデータを削除
            try:
                self._keyring.delete_password(self.SERVICE_NAME, username)
            except:
                pass  # 削除失敗は警告のみ
            
            try:
                self._keyring.delete_password(f"{self.SERVICE_NAME}_meta", username)
            except:
                pass
            
            logger.info(f"認証情報をキーチェーンから削除: {username}")
            return True
            
        except Exception as e:
            logger.error(f"キーチェーン削除エラー: {e}")
            return False
    
    def _find_stored_username(self) -> Optional[str]:
        """保存されたユーザー名を検索"""
        # keyringライブラリには列挙機能がないため、複数の方法で検索
        
        # 方法1: 設定ファイルから最後に保存したユーザー名を取得
        try:
            from classes.managers.app_config_manager import get_config_manager
            config_manager = get_config_manager()
            if config_manager:
                last_username = config_manager.get("autologin.last_username")
                if last_username:
                    # 実際にキーチェーンに保存されているかテスト
                    password = self._keyring.get_password(self.SERVICE_NAME, last_username)
                    if password:
                        return last_username
        except Exception as e:
            logger.debug(f"設定ファイルからのユーザー名取得失敗: {e}")
        
        # 方法2: レガシーファイルから推測
        try:
            from functions.common_funcs import read_login_info
            username, _, _ = read_login_info()
            if username:
                # 実際にキーチェーンに保存されているかテスト
                password = self._keyring.get_password(self.SERVICE_NAME, username)
                if password:
                    return username
        except Exception as e:
            logger.debug(f"レガシーファイルからのユーザー名取得失敗: {e}")
        
        # 方法3: 現在のアプリケーションフォームから取得
        try:
            from qt_compat.widgets import QApplication
            app = QApplication.instance()
            if app:
                # アクティブウィンドウから自動ログインタブを検索
                for widget in app.allWidgets():
                    if hasattr(widget, 'username_edit') and hasattr(widget, 'objectName'):
                        if 'autologin' in widget.objectName().lower() or 'login' in widget.objectName().lower():
                            username = widget.username_edit.text().strip()
                            if username:
                                # 実際にキーチェーンに保存されているかテスト
                                password = self._keyring.get_password(self.SERVICE_NAME, username)
                                if password:
                                    return username
        except Exception as e:
            logger.debug(f"UIからのユーザー名取得失敗: {e}")
        
        return None

class EncryptedFileCredentialStore(BaseCredentialStore):
    """暗号化ファイル使用の認証情報ストア"""
    
    def __init__(self):
        from config.common import get_dynamic_file_path
        self.creds_file = get_dynamic_file_path('output/.private/creds.enc.json')
        self._crypto = None
        self._init_crypto()
    
    def _init_crypto(self):
        """暗号化ライブラリの初期化"""
        try:
            from Cryptodome.Cipher import AES
            from Cryptodome.Random import get_random_bytes
            from Cryptodome.Protocol.KDF import PBKDF2
            self._crypto = {
                'AES': AES,
                'get_random_bytes': get_random_bytes,
                'PBKDF2': PBKDF2
            }
        except ImportError:
            logger.warning("暗号化ライブラリ（pycryptodomex）が利用できません")
    
    def is_available(self) -> bool:
        """暗号化ファイルストアが利用可能かチェック"""
        if not self._crypto:
            return False
        
        # 暗号鍵の保護が可能かチェック
        return self._can_protect_key()
    
    def _can_protect_key(self) -> bool:
        """暗号鍵の安全な保護が可能かチェック"""
        system = platform.system().lower()
        
        if system == "windows":
            # Windows: DPAPI利用可能性チェック
            try:
                import win32crypt
                # テスト暗号化
                test_data = b"test"
                encrypted = win32crypt.CryptProtectData(test_data, None, None, None, None, 0)
                decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
                return decrypted == test_data
            except:
                return False
        
        elif system in ["darwin", "linux"]:
            # macOS/Linux: キーチェーンで鍵保護
            try:
                import keyring
                backend = keyring.get_keyring()
                if backend and hasattr(backend, 'priority') and backend.priority > 0:
                    return True
            except:
                pass
            return False
        
        return False
    
    def _protect_key(self, key: bytes) -> bytes:
        """プラットフォーム固有の方法で鍵を保護"""
        system = platform.system().lower()
        
        if system == "windows":
            import win32crypt
            return win32crypt.CryptProtectData(key, None, None, None, None, 0)
        
        elif system in ["darwin", "linux"]:
            # macOS/Linux: キーチェーンに保存し、ハッシュを返す
            import keyring
            key_id = hashlib.sha256(key).hexdigest()[:16]
            keyring.set_password(f"{self.SERVICE_NAME}_key", "encryption_key", key.hex())
            return key_id.encode()
        
        raise NotImplementedError(f"プラットフォーム {system} での鍵保護は未対応")
    
    def _unprotect_key(self, protected_key: bytes) -> bytes:
        """保護された鍵を復号"""
        system = platform.system().lower()
        
        if system == "windows":
            import win32crypt
            return win32crypt.CryptUnprotectData(protected_key, None, None, None, 0)[1]
        
        elif system in ["darwin", "linux"]:
            # macOS/Linux: キーチェーンから取得
            import keyring
            key_hex = keyring.get_password(f"{self.SERVICE_NAME}_key", "encryption_key")
            if not key_hex:
                raise ValueError("暗号鍵が見つかりません")
            return bytes.fromhex(key_hex)
        
        raise NotImplementedError(f"プラットフォーム {system} での鍵復号は未対応")
    
    def save_credentials(self, creds: CredentialInfo) -> bool:
        """認証情報を暗号化ファイルに保存"""
        if not self.is_available():
            return False
        
        try:
            # 暗号化キーの生成
            key = self._crypto['get_random_bytes'](32)  # AES-256
            protected_key = self._protect_key(key)
            
            # データの準備
            data = {
                "username": creds.username,
                "password": creds.password,
                "login_mode": creds.login_mode,
                "updated_at": datetime.now().isoformat()
            }
            
            # 暗号化
            cipher = self._crypto['AES'].new(key, self._crypto['AES'].MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(json.dumps(data).encode())
            
            # ファイル保存
            os.makedirs(os.path.dirname(self.creds_file), exist_ok=True)
            encrypted_data = {
                "protected_key": protected_key.hex(),
                "nonce": cipher.nonce.hex(),
                "ciphertext": ciphertext.hex(),
                "tag": tag.hex(),
                "version": "1.0"
            }
            
            with open(self.creds_file, 'w', encoding='utf-8') as f:
                json.dump(encrypted_data, f)
            
            # 鍵をメモリから削除
            key = b'\x00' * len(key)
            
            logger.info("認証情報を暗号化ファイルに保存")
            return True
            
        except Exception as e:
            logger.error(f"暗号化ファイル保存エラー: {e}")
            return False
    
    def load_credentials(self) -> Optional[CredentialInfo]:
        """認証情報を暗号化ファイルから読み込み"""
        if not self.is_available() or not os.path.exists(self.creds_file):
            return None
        
        try:
            # ファイル読み込み
            with open(self.creds_file, 'r', encoding='utf-8') as f:
                encrypted_data = json.load(f)
            
            # 鍵の復号
            protected_key = bytes.fromhex(encrypted_data["protected_key"])
            key = self._unprotect_key(protected_key)
            
            # データの復号
            nonce = bytes.fromhex(encrypted_data["nonce"])
            ciphertext = bytes.fromhex(encrypted_data["ciphertext"])
            tag = bytes.fromhex(encrypted_data["tag"])
            
            cipher = self._crypto['AES'].new(key, self._crypto['AES'].MODE_GCM, nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
            # データの解析
            data = json.loads(plaintext.decode())
            
            # 鍵をメモリから削除
            key = b'\x00' * len(key)
            
            return CredentialInfo(
                username=data["username"],
                password=data["password"],
                login_mode=data.get("login_mode"),
                updated_at=data.get("updated_at")
            )
            
        except Exception as e:
            logger.error(f"暗号化ファイル読み込みエラー: {e}")
            return None
    
    def delete_credentials(self) -> bool:
        """暗号化ファイルを削除"""
        try:
            if os.path.exists(self.creds_file):
                os.remove(self.creds_file)
            
            # macOS/Linuxの場合はキーチェーンからも削除
            system = platform.system().lower()
            if system in ["darwin", "linux"]:
                try:
                    import keyring
                    keyring.delete_password(f"{self.SERVICE_NAME}_key", "encryption_key")
                except:
                    pass
            
            logger.info("暗号化ファイルを削除")
            return True
            
        except Exception as e:
            logger.error(f"暗号化ファイル削除エラー: {e}")
            return False

class LegacyFileCredentialProvider(BaseCredentialStore):
    """レガシーファイル（input/login.txt）の認証情報プロバイダー"""
    
    def __init__(self):
        from config.common import LOGIN_FILE
        self.login_file = LOGIN_FILE
    
    def is_available(self) -> bool:
        """login.txtファイルが存在するかチェック"""
        return os.path.exists(self.login_file)
    
    def save_credentials(self, creds: CredentialInfo) -> bool:
        """レガシーファイルは読み取り専用として扱う"""
        logger.warning("レガシーファイルへの書き込みは非対応")
        return False
    
    def load_credentials(self) -> Optional[CredentialInfo]:
        """login.txtから認証情報を読み込み"""
        if not self.is_available():
            return None
        
        try:
            from functions.common_funcs import read_login_info
            username, password, extra = read_login_info()
            
            if username and password:
                return CredentialInfo(
                    username=username,
                    password=password,
                    login_mode=extra,
                    updated_at=None  # レガシーファイルでは更新日時不明
                )
            
        except Exception as e:
            logger.error(f"レガシーファイル読み込みエラー: {e}")
        
        return None
    
    def delete_credentials(self) -> bool:
        """レガシーファイルは削除しない"""
        logger.warning("レガシーファイルの削除は非対応")
        return False

def perform_health_check() -> CredentialStoreHealthCheck:
    """認証情報ストアのヘルスチェックを実行"""
    health = CredentialStoreHealthCheck()
    
    # OSキーチェーンのチェック
    keyring_store = KeyringCredentialStore()
    try:
        health.os_ok = keyring_store.is_available()
    except Exception as e:
        health.os_error = str(e)
    
    # 暗号化ファイルのチェック
    encrypted_store = EncryptedFileCredentialStore()
    try:
        health.enc_ok = encrypted_store.is_available()
    except Exception as e:
        health.enc_error = str(e)
    
    # レガシーファイルのチェック
    legacy_provider = LegacyFileCredentialProvider()
    try:
        health.legacy_exists = legacy_provider.is_available()
        if health.legacy_exists:
            health.legacy_path = legacy_provider.login_file
    except Exception as e:
        pass  # レガシーファイルのエラーは無視
    
    # 互換性属性の更新
    health.update_compatibility_attrs()
    
    return health

def decide_autologin_source(preference: str = None, health: CredentialStoreHealthCheck = None) -> str:
    """自動ログインソースを決定"""
    # デフォルト引数処理
    if health is None:
        health = perform_health_check()
    if preference is None:
        from classes.managers.app_config_manager import get_config_manager
        config_manager = get_config_manager()
        preference = config_manager.get("autologin.credential_storage", "auto")
    
    if preference == 'none':
        return 'none'
    if preference == 'os_keychain' and health.os_ok:
        return 'os_keychain'
    if preference == 'encrypted_file' and health.enc_ok:
        return 'encrypted_file'
    if preference == 'legacy_file' and health.legacy_exists:
        return 'legacy_file'
    
    # auto 選択
    if health.os_ok:
        return 'os_keychain'
    if health.enc_ok:
        return 'encrypted_file'
    if health.legacy_exists:
        return 'legacy_file'
    
    return 'none'

def get_credential_store(store_type: str) -> Optional[BaseCredentialStore]:
    """指定されたタイプの認証情報ストアを取得"""
    if store_type == 'os_keychain':
        return KeyringCredentialStore()
    elif store_type == 'encrypted_file':
        return EncryptedFileCredentialStore()
    elif store_type == 'legacy_file':
        return LegacyFileCredentialProvider()
    
    return None
