#!/usr/bin/env python3
"""
ログ管理クラス - ARIM RDE Tool
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from config.common import get_dynamic_file_path, DEBUG_LOG_ENABLED, DEBUG_LOG_FULL_ARGS


class LogManager:
    """ログ管理クラス"""
    
    def __init__(self, config_manager=None):
        """ログ管理クラスの初期化"""
        self.config_manager = config_manager
        self._loggers: Dict[str, logging.Logger] = {}
        self._handlers: Dict[str, logging.Handler] = {}
        self._initialized = False
        self._setup_logging()
    
    def _setup_logging(self):
        """ログの基本設定初期化"""
        if self._initialized:
            return
        
        # ルートロガーの設定
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        self._initialized = True
    
    def get_logger(self, name: str) -> logging.Logger:
        """ロガーの取得"""
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]


# グローバルインスタンス
_log_manager = None

def get_log_manager():
    """ログ管理クラスのシングルトンインスタンスを取得"""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager

def get_logger(name: str = __name__) -> logging.Logger:
    """ロガーの取得（便利関数）"""
    return get_log_manager().get_logger(name)
