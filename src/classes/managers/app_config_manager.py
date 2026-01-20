#!/usr/bin/env python3
"""
アプリケーション設定管理クラス - ARIM RDE Tool

概要:
アプリケーション全体で使用される設定値の統合管理を行うクラスです。
ハードコードされた設定値を一元化し、環境や用途に応じた柔軟な
設定変更を可能にします。

主要機能:
- デフォルト設定値の管理
- 設定ファイルからの読み込み
- 環境変数による上書き対応
- 設定値の型安全性確保
- 設定変更の動的反映

設計思想:
設定値の散在を防ぎ、保守性と拡張性を向上させるために、
全ての設定項目を統一的に管理します。
"""

import os
import json
import logging
from typing import Any, Dict, Optional, Union
from config.common import get_dynamic_file_path

class AppConfigManager:
    """アプリケーション設定管理クラス"""
    
    def __init__(self, config_file_path: Optional[str] = None):
        """
        設定管理クラスの初期化
        
        Args:
            config_file_path: 設定ファイルのパス（Noneの場合はデフォルト使用）
        """
        self.logger = logging.getLogger(__name__)
        self._config: Dict[str, Any] = {}
        self._config_file_path = config_file_path or self._get_default_config_path()
        
        # デフォルト設定の初期化
        self._initialize_default_config()
        
        # 設定ファイルからの読み込み
        self._load_config_file()
        
        # 環境変数による上書き
        self._apply_environment_overrides()
    
    def _get_default_config_path(self) -> str:
        """デフォルト設定ファイルパスの取得"""
        return get_dynamic_file_path("config/app_config.json")
    
    def _initialize_default_config(self):
        """デフォルト設定値の初期化"""
        self._config = {
            # アプリケーション基本設定
            "app": {
                "default_grant_number": "JPMXP1222TU0195",
                "auto_login_enabled": False,
                "auto_close_enabled": False,
                "enable_splash_screen": True,
                "test_mode": False
            },
            
            # UI設定
            "ui": {
                "window_title_suffix": "",
                "webview_width": 1024,
                "webview_height": 768,
                "menu_width": 300,
                "image_load_wait_time": 5000
            },
            
            # ネットワーク設定
            "network": {
                "request_timeout": 30,
                "max_retries": 3,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
            
            # ログ設定
            "logging": {
                "level": "INFO",
                "file_enabled": True,
                "console_enabled": True,
                "max_file_size_mb": 10,
                "backup_count": 5
            },
            
            # 画像処理設定
            "image": {
                "max_concurrent_downloads": 5,
                "thumbnail_size": (150, 150),
                "supported_formats": ["jpg", "jpeg", "png", "gif", "bmp"],
                "quality": 95
            },
            
            # データ処理設定
            "data": {
                "batch_size": 100,
                "max_dataset_size_gb": 10,
                "compression_enabled": True,
                "backup_enabled": True
            },
            
            # 自動ログイン設定（v1.16追加）
            "autologin": {
                "autologin_enabled": False,
                "credential_storage": "auto",  # auto | os_keychain | encrypted_file | legacy_file | none
                "warn_on_legacy_file": True,
                "remember_credentials": True
            },

            # メール設定（Gmailを先行実装）
            # 注意: アプリパスワード等の機微情報はここには保存しない（OSキーチェーンへ保存）
            "mail": {
                "provider": "gmail",  # gmail | microsoft365 | smtp
                "gmail": {
                    "from_address": "",
                    "remember_app_password": False
                },
                "microsoft365": {
                    "client_id": "",
                    "tenant": "common"
                },
                "smtp": {
                    "host": "",
                    "port": 465,
                    "security": "ssl",  # ssl | starttls | none
                    "username": "",
                    "from_address": "",
                    "remember_password": False
                },
                "test": {
                    "to_address": "",
                    "subject": "ARIM RDE Tool テストメール",
                    "body": "これは ARIM RDE Tool のテストメールです。"
                }
            }
        }
    
    def _load_config_file(self):
        """設定ファイルからの読み込み"""
        try:
            if os.path.exists(self._config_file_path):
                with open(self._config_file_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                
                # 深いマージ（ネストされた辞書も統合）
                self._deep_merge(self._config, file_config)
                self.logger.info(f"設定ファイル読み込み完了: {self._config_file_path}")
            else:
                self.logger.info(f"設定ファイルが見つかりません（デフォルト設定使用）: {self._config_file_path}")
                
        except Exception as e:
            self.logger.warning(f"設定ファイル読み込み失敗（デフォルト設定使用）: {e}")
    
    def _apply_environment_overrides(self):
        """環境変数による設定上書き"""
        # 環境変数の命名規則: ARIM_RDE_<SECTION>_<KEY>
        env_mappings = {
            "ARIM_RDE_APP_GRANT_NUMBER": ("app", "default_grant_number"),
            "ARIM_RDE_APP_AUTO_LOGIN": ("app", "auto_login_enabled"),
            "ARIM_RDE_LOGGING_LEVEL": ("logging", "level"),
            "ARIM_RDE_NETWORK_TIMEOUT": ("network", "request_timeout"),
            "ARIM_RDE_UI_WIDTH": ("ui", "webview_width"),
            "ARIM_RDE_UI_HEIGHT": ("ui", "webview_height")
        }
        
        for env_var, (section, key) in env_mappings.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                try:
                    # 型に応じて変換
                    if key.endswith("_enabled"):
                        env_value = env_value.lower() in ("true", "1", "yes", "on")
                    elif key in ("request_timeout", "webview_width", "webview_height"):
                        env_value = int(env_value)
                    
                    self._config[section][key] = env_value
                    self.logger.debug(f"環境変数適用: {env_var} -> {section}.{key} = {env_value}")
                    
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"環境変数の型変換失敗: {env_var} = {env_value}, error: {e}")
    
    def _deep_merge(self, base_dict: Dict, override_dict: Dict):
        """辞書の深いマージ"""
        for key, value in override_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        設定値の取得（ドット記法サポート）
        
        Args:
            key_path: 設定キーのパス（例: "app.default_grant_number"）
            default: デフォルト値
            
        Returns:
            設定値
        """
        try:
            keys = key_path.split('.')
            value = self._config
            
            for key in keys:
                value = value[key]
            
            return value
            
        except (KeyError, TypeError):
            self.logger.debug(f"設定キー未発見（デフォルト値使用）: {key_path} -> {default}")
            return default
    
    def set(self, key_path: str, value: Any) -> bool:
        """
        設定値の設定
        
        Args:
            key_path: 設定キーのパス
            value: 設定する値
            
        Returns:
            bool: 成功時True
        """
        try:
            keys = key_path.split('.')
            target = self._config
            
            # 最後のキー以外を辿る
            for key in keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]
            
            # 最後のキーに値を設定
            target[keys[-1]] = value
            self.logger.debug(f"設定値更新: {key_path} = {value}")
            return True
            
        except Exception as e:
            self.logger.error(f"設定値設定失敗: {key_path} = {value}, error: {e}")
            return False
    
    def save_to_file(self, file_path: Optional[str] = None) -> bool:
        """
        設定をファイルに保存
        
        Args:
            file_path: 保存先ファイルパス（Noneの場合はデフォルト使用）
            
        Returns:
            bool: 成功時True
        """
        target_path = file_path or self._config_file_path
        
        try:
            # ディレクトリの確保
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            # JSONファイル保存
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"設定ファイル保存完了: {target_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"設定ファイル保存失敗: {target_path}, error: {e}")
            return False
    
    def save(self, file_path: Optional[str] = None) -> bool:
        """設定保存（save_to_fileの別名）"""
        return self.save_to_file(file_path)
    
    def get_all(self) -> Dict[str, Any]:
        """全設定の取得（読み取り専用コピー）"""
        return self._config.copy()
    
    def reset_to_defaults(self):
        """設定をデフォルトに戻す"""
        self._initialize_default_config()
        self.logger.info("設定をデフォルトにリセットしました")
    
    def validate_config(self) -> Dict[str, list]:
        """
        設定値の妥当性検証
        
        Returns:
            Dict[str, list]: 検証エラーのリスト（セクション別）
        """
        errors = {}
        
        # アプリケーション設定の検証
        app_errors = []
        if not isinstance(self.get("app.default_grant_number"), str):
            app_errors.append("default_grant_number must be string")
        if self.get("app.default_grant_number") == "":
            app_errors.append("default_grant_number cannot be empty")
        
        if app_errors:
            errors["app"] = app_errors
        
        # UI設定の検証
        ui_errors = []
        if self.get("ui.webview_width") <= 0:
            ui_errors.append("webview_width must be positive")
        if self.get("ui.webview_height") <= 0:
            ui_errors.append("webview_height must be positive")
        
        if ui_errors:
            errors["ui"] = ui_errors
        
        # ネットワーク設定の検証
        network_errors = []
        if self.get("network.request_timeout") <= 0:
            network_errors.append("request_timeout must be positive")
        if self.get("network.max_retries") < 0:
            network_errors.append("max_retries cannot be negative")
        
        if network_errors:
            errors["network"] = network_errors
        
        return errors
    
    def get_autologin_settings(self) -> Dict[str, Any]:
        """自動ログイン設定の取得"""
        return self.get("autologin", {})
    
    def set_autologin_settings(self, settings: Dict[str, Any]) -> bool:
        """自動ログイン設定の保存"""
        try:
            for key, value in settings.items():
                self.set(f"autologin.{key}", value)
            return self.save()
        except Exception as e:
            self.logger.error(f"自動ログイン設定保存失敗: {e}")
            return False

# グローバルインスタンス（シングルトンパターン）
_config_manager_instance = None

def get_config_manager() -> AppConfigManager:
    """アプリケーション設定管理インスタンスの取得"""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = AppConfigManager()
    return _config_manager_instance

def get_config(key_path: str, default: Any = None) -> Any:
    """設定値取得のショートカット関数"""
    return get_config_manager().get(key_path, default)

def set_config(key_path: str, value: Any) -> bool:
    """設定値設定のショートカット関数"""
    return get_config_manager().set(key_path, value)
