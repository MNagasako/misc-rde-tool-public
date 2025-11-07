"""
データポータル設定管理モジュール

input/data_portal_config.json から設定を読み込む
テスト環境のURL等はGit管理外の設定ファイルで管理
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

from config.common import get_dynamic_file_path
from classes.managers.log_manager import get_logger

logger = get_logger("DataPortal.Config")


@dataclass
class EnvironmentConfig:
    """環境別設定"""
    url: str
    # ベーシック認証情報はkeyringで管理するため削除
    # basic_username / basic_password はauth_managerで管理


class DataPortalConfig:
    """
    データポータル設定管理クラス
    
    設定ファイル: input/data_portal_config.json
    
    設定形式:
    {
        "test": {
            "url": "https://...",
            "basic_auth": {
                "username": "...",
                "password": "..."
            }
        },
        "production": {
            "url": "https://nanonet.go.jp/data_service/system_arim_data/"
        }
    }
    """
    
    # デフォルト設定（本番環境のみ）
    DEFAULT_CONFIG = {
        "production": {
            "url": "https://nanonet.go.jp/data_service/system_arim_data/"
        }
    }
    
    CONFIG_FILENAME = "data_portal_config.json"
    
    def __init__(self):
        """初期化"""
        self.config_data = self._load_config()
        # 有効な環境のみをフィルタリング（コメント行を除外）
        self.environments = self._filter_valid_environments()
        logger.info(f"利用可能な環境: {self.environments}")
    
    def _load_config(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込む
        
        Returns:
            Dict: 設定データ
        """
        try:
            config_path = get_dynamic_file_path(f"input/{self.CONFIG_FILENAME}")
            
            if not Path(config_path).exists():
                logger.warning(
                    f"設定ファイルが見つかりません: {config_path}\n"
                    "デフォルト設定（本番環境のみ）を使用します。\n"
                    f"テスト環境を使用する場合は、input/{self.CONFIG_FILENAME} を作成してください。"
                )
                return self.DEFAULT_CONFIG.copy()
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            logger.info(f"設定ファイル読み込み成功: {config_path}")
            return config_data
            
        except json.JSONDecodeError as e:
            logger.error(f"設定ファイルのJSON解析エラー: {e}")
            logger.warning("デフォルト設定を使用します")
            return self.DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {e}")
            logger.warning("デフォルト設定を使用します")
            return self.DEFAULT_CONFIG.copy()
    
    def get_environment_config(self, environment: str) -> Optional[EnvironmentConfig]:
        """
        環境別設定を取得
        
        Args:
            environment: 環境名 ('test', 'production')
        
        Returns:
            EnvironmentConfig: 環境設定（存在しない場合None）
        """
        if environment not in self.config_data:
            logger.warning(f"環境 '{environment}' の設定が見つかりません")
            return None
        
        env_data = self.config_data[environment]
        
        # URLは必須
        if "url" not in env_data:
            logger.error(f"環境 '{environment}' にURLが設定されていません")
            return None
        
        # ベーシック認証情報はkeyringで管理するため、ここでは取得しない
        return EnvironmentConfig(url=env_data["url"])
    
    def has_environment(self, environment: str) -> bool:
        """
        指定環境が設定されているかチェック
        
        Args:
            environment: 環境名
        
        Returns:
            bool: 設定されている場合True
        """
        return environment in self.config_data
    
    def _filter_valid_environments(self) -> list:
        """
        有効な環境のみをフィルタリング
        
        Returns:
            list: 有効な環境名リスト（'test', 'production'のみ）
        """
        valid_envs = []
        for env in self.config_data.keys():
            # コメント行（//で始まるキー）を除外
            if env.startswith("//"):
                continue
            # test と production のみを許可
            if env in ["test", "production"]:
                valid_envs.append(env)
            else:
                logger.warning(f"未対応の環境 '{env}' は無視されます")
        return valid_envs
    
    def get_available_environments(self) -> list:
        """
        利用可能な環境一覧を取得
        
        Returns:
            list: 環境名リスト（'test', 'production'のみ）
        """
        return self.environments.copy()
    
    def get_url(self, environment: str) -> Optional[str]:
        """
        環境のURLを取得
        
        Args:
            environment: 環境名
        
        Returns:
            str: URL（存在しない場合None）
        """
        config = self.get_environment_config(environment)
        return config.url if config else None


# シングルトンインスタンス
_config_instance = None


def get_data_portal_config() -> DataPortalConfig:
    """
    DataPortalConfigのシングルトンインスタンスを取得
    
    Returns:
        DataPortalConfig: シングルトンインスタンス
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = DataPortalConfig()
    return _config_instance
