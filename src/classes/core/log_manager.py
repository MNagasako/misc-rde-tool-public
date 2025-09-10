#!/usr/bin/env python3
"""
ログ管理クラス - ARIM RDE Tool v1.13.1

概要:
アプリケーション全体のログ設定と管理を統一的に行うクラスです。
複数箇所に散在していたログ設定を一元化し、保守性と一貫性を向上させます。

主要機能:
- 統一ログ設定の管理
- 複数ハンドラの統合制御
- ログレベルの動的変更
- ログローテーション機能
- フォーマット設定の統一
- パフォーマンス最適化

設計思想:
アプリケーション全体で一貫したログ出力を実現し、
デバッグやトラブルシューティングの効率を向上させます。
"""

import os
import logging
import logging.handlers
from typing import Optional, Dict, Any
from config.common import OUTPUT_LOG_DIR
from classes.core.app_config_manager import get_config_manager

class LogManager:
    """ログ管理クラス"""
    
    def __init__(self, config_manager=None):
        """
        ログ管理クラスの初期化
        
        Args:
            config_manager: 設定管理インスタンス（Noneの場合は自動取得）
        """
        self.config_manager = config_manager or get_config_manager()
        self._loggers: Dict[str, logging.Logger] = {}
        self._handlers: Dict[str, logging.Handler] = {}
        self._initialized = False
        
        # ログディレクトリの確保
        self._ensure_log_directory()
        
        # 基本設定の初期化
        self._initialize_logging()
    
    def _ensure_log_directory(self):
        """ログディレクトリの確保"""
        try:
            os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)
        except Exception as e:
            print(f"ログディレクトリ作成失敗: {OUTPUT_LOG_DIR}, error: {e}")
    
    def _initialize_logging(self):
        """ログの基本設定初期化"""
        if self._initialized:
            return
        
        # ルートロガーの設定
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # 既存ハンドラの除去（重複防止）
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        self._initialized = True
    
    def get_logger(self, name: str = "RDE_WebView") -> logging.Logger:
        """
        ロガーインスタンスの取得
        
        Args:
            name: ロガー名
            
        Returns:
            logging.Logger: 設定済みロガーインスタンス
        """
        if name in self._loggers:
            return self._loggers[name]
        
        # 新しいロガーの作成
        logger = logging.getLogger(name)
        logger.setLevel(self._get_log_level())
        
        # ハンドラの追加
        self._setup_handlers(logger, name)
        
        # キャッシュに保存
        self._loggers[name] = logger
        
        return logger
    
    def _get_log_level(self) -> int:
        """設定からログレベルを取得"""
        level_str = self.config_manager.get("logging.level", "INFO").upper()
        
        level_mapping = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        
        return level_mapping.get(level_str, logging.INFO)
    
    def _setup_handlers(self, logger: logging.Logger, name: str):
        """ハンドラの設定"""
        # コンソールハンドラ
        if self.config_manager.get("logging.console_enabled", True):
            console_handler = self._get_console_handler()
            logger.addHandler(console_handler)
        
        # ファイルハンドラ
        if self.config_manager.get("logging.file_enabled", True):
            file_handler = self._get_file_handler(name)
            logger.addHandler(file_handler)
        
        # プロパゲーションを無効化（重複ログ防止）
        logger.propagate = False
    
    def _get_console_handler(self) -> logging.StreamHandler:
        """コンソールハンドラの取得"""
        handler_key = "console"
        
        if handler_key not in self._handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(self._get_formatter())
            self._handlers[handler_key] = handler
        
        return self._handlers[handler_key]
    
    def _get_file_handler(self, logger_name: str) -> logging.Handler:
        """ファイルハンドラの取得"""
        handler_key = f"file_{logger_name}"
        
        if handler_key not in self._handlers:
            log_file_path = os.path.join(OUTPUT_LOG_DIR, f"{logger_name.lower()}.log")
            
            # ローテーション機能付きハンドラ
            max_bytes = self.config_manager.get("logging.max_file_size_mb", 10) * 1024 * 1024
            backup_count = self.config_manager.get("logging.backup_count", 5)
            
            handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8"
            )
            handler.setFormatter(self._get_formatter())
            self._handlers[handler_key] = handler
        
        return self._handlers[handler_key]
    
    def _get_formatter(self) -> logging.Formatter:
        """ログフォーマッターの取得"""
        return logging.Formatter(
            '[%(levelname)s] %(asctime)s - %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def set_log_level(self, level: str):
        """
        ログレベルの動的変更
        
        Args:
            level: ログレベル文字列（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        """
        # 設定を更新
        self.config_manager.set("logging.level", level.upper())
        
        # 既存ロガーのレベルを更新
        log_level = self._get_log_level()
        for logger in self._loggers.values():
            logger.setLevel(log_level)
    
    def add_custom_handler(self, logger_name: str, handler: logging.Handler):
        """
        カスタムハンドラの追加
        
        Args:
            logger_name: ロガー名
            handler: 追加するハンドラ
        """
        logger = self.get_logger(logger_name)
        handler.setFormatter(self._get_formatter())
        logger.addHandler(handler)
    
    def get_log_file_paths(self) -> Dict[str, str]:
        """
        全ログファイルのパス取得
        
        Returns:
            Dict[str, str]: ロガー名とログファイルパスのマッピング
        """
        paths = {}
        for logger_name in self._loggers.keys():
            log_file_path = os.path.join(OUTPUT_LOG_DIR, f"{logger_name.lower()}.log")
            if os.path.exists(log_file_path):
                paths[logger_name] = log_file_path
        return paths
    
    def cleanup_old_logs(self, days: int = 30):
        """
        古いログファイルのクリーンアップ
        
        Args:
            days: 保持日数
        """
        import time
        
        try:
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 60 * 60)
            
            for filename in os.listdir(OUTPUT_LOG_DIR):
                file_path = os.path.join(OUTPUT_LOG_DIR, filename)
                if os.path.isfile(file_path) and filename.endswith('.log'):
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_time:
                        os.remove(file_path)
                        print(f"古いログファイル削除: {filename}")
        
        except Exception as e:
            print(f"ログクリーンアップ失敗: {e}")
    
    def get_log_statistics(self) -> Dict[str, Any]:
        """
        ログ統計情報の取得
        
        Returns:
            Dict[str, Any]: ログ統計情報
        """
        stats = {
            "total_loggers": len(self._loggers),
            "total_handlers": len(self._handlers),
            "log_level": self.config_manager.get("logging.level", "INFO"),
            "log_files": {}
        }
        
        # ファイルサイズ情報
        for logger_name in self._loggers.keys():
            log_file_path = os.path.join(OUTPUT_LOG_DIR, f"{logger_name.lower()}.log")
            if os.path.exists(log_file_path):
                file_size = os.path.getsize(log_file_path)
                stats["log_files"][logger_name] = {
                    "path": log_file_path,
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2)
                }
        
        return stats

# グローバルインスタンス（シングルトンパターン）
_log_manager_instance = None

def get_log_manager() -> LogManager:
    """ログ管理インスタンスの取得"""
    global _log_manager_instance
    if _log_manager_instance is None:
        _log_manager_instance = LogManager()
    return _log_manager_instance

def get_logger(name: str = "RDE_WebView") -> logging.Logger:
    """ロガー取得のショートカット関数"""
    return get_log_manager().get_logger(name)

def set_log_level(level: str):
    """ログレベル設定のショートカット関数"""
    get_log_manager().set_log_level(level)
