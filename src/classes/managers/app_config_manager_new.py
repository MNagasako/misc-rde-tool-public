#!/usr/bin/env python3
"""
アプリケーション設定管理クラス - ARIM RDE Tool
"""

import json
import os
import logging
from typing import Any, Dict, Optional, Union
from pathlib import Path
from config.common import get_dynamic_file_path


class AppConfigManager:
    """アプリケーション設定管理クラス"""
    
    def __init__(self, config_file_path: Optional[str] = None):
        """設定管理クラスの初期化"""
        self.logger = logging.getLogger(__name__)
        self._config: Dict[str, Any] = {}
        self._config_file_path = config_file_path or self._get_default_config_path()
        self._load_config()
    
    def _get_default_config_path(self) -> str:
        """デフォルト設定ファイルパスの取得"""
        return get_dynamic_file_path("config/app_config.json")
    
    def _load_config(self):
        """設定ファイルからの読み込み"""
        try:
            if os.path.exists(self._config_file_path):
                with open(self._config_file_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                self.logger.info(f"設定ファイルを読み込みました: {self._config_file_path}")
            else:
                self.logger.warning(f"設定ファイルが見つかりません: {self._config_file_path}")
                self._config = {}
        except Exception as e:
            self.logger.error(f"設定ファイル読み込みエラー: {e}")
            self._config = {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """設定値の取得"""
        return self._config.get(key, default)


# グローバルインスタンス
_config_manager = None

def get_config_manager() -> AppConfigManager:
    """設定管理クラスのシングルトンインスタンスを取得"""
    global _config_manager
    if _config_manager is None:
        _config_manager = AppConfigManager()
    return _config_manager
