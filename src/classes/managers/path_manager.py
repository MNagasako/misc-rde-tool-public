#!/usr/bin/env python3
"""
パス管理ユーティリティクラス - ARIM RDE Tool v1.13.1

概要:
アプリケーション全体のパス管理を統一的に行うユーティリティクラスです。
ソース実行時とバイナリ実行時の透過的な切り替えと、セキュアなパス操作を提供します。

主要機能:
- 環境依存パス解決の統一管理
- パスバリデーション機能
- ディレクトリ自動作成
- セキュアなパス操作
- パス正規化・クリーニング
- 相対パス・絶対パス変換

設計思想:
CWD（カレントワーキングディレクトリ）に依存しない堅牢なパス管理により、
開発時・バイナリ時・異なる実行環境での一貫した動作を保証します。
"""

import os
import sys
import logging
from typing import List, Optional, Tuple, Union
from pathlib import Path
from config.common import get_base_dir, get_static_resource_path, get_dynamic_file_path, is_binary_execution
from classes.managers.log_manager import get_logger

class PathManager:
    """パス管理ユーティリティクラス"""
    
    def __init__(self):
        """パス管理クラスの初期化"""
        self.logger = get_logger("PathManager")
        self._base_dir = get_base_dir()
        self._static_dirs_cache = {}
        self._dynamic_dirs_cache = {}
        
    def get_base_directory(self) -> str:
        """基準ディレクトリの取得"""
        return self._base_dir
    
    def is_binary_mode(self) -> bool:
        """バイナリ実行モードの判定"""
        return is_binary_execution()
    
    def get_static_path(self, relative_path: str) -> str:
        """
        静的リソースパスの取得
        
        Args:
            relative_path: 静的リソースへの相対パス
            
        Returns:
            str: 静的リソースの絶対パス
        """
        try:
            return get_static_resource_path(relative_path)
        except Exception as e:
            self.logger.error(f"静的パス取得失敗: {relative_path}, error: {e}")
            raise
    
    def get_dynamic_path(self, relative_path: str) -> str:
        """
        動的ファイルパスの取得
        
        Args:
            relative_path: 動的ファイルへの相対パス
            
        Returns:
            str: 動的ファイルの絶対パス
        """
        try:
            return get_dynamic_file_path(relative_path)
        except Exception as e:
            self.logger.error(f"動的パス取得失敗: {relative_path}, error: {e}")
            raise
    
    def ensure_directory(self, directory_path: str) -> bool:
        """
        ディレクトリの存在確認と作成
        
        Args:
            directory_path: 作成するディレクトリパス
            
        Returns:
            bool: 成功時True
        """
        try:
            os.makedirs(directory_path, exist_ok=True)
            self.logger.debug(f"ディレクトリ確保: {directory_path}")
            return True
        except Exception as e:
            self.logger.error(f"ディレクトリ作成失敗: {directory_path}, error: {e}")
            return False
    
    def ensure_directory_exists(self, directory_path: str) -> bool:
        """
        ディレクトリの存在確認と作成（ensure_directoryのエイリアス）
        
        Args:
            directory_path: 作成するディレクトリパス
            
        Returns:
            bool: 成功時True
        """
        return self.ensure_directory(directory_path)
    
    def get_safe_file_path(self, file_path: str, base_dir: Optional[str] = None) -> Optional[str]:
        """
        安全なファイルパスの取得
        
        Args:
            file_path: 検証するファイルパス
            base_dir: 基準ディレクトリ（指定時はその配下に制限）
            
        Returns:
            Optional[str]: 安全な場合は正規化されたパス、そうでなければNone
        """
        try:
            # パスの正規化
            normalized_path = os.path.normpath(file_path)
            
            # 絶対パスに変換
            if not os.path.isabs(normalized_path):
                if base_dir:
                    normalized_path = os.path.join(base_dir, normalized_path)
                else:
                    normalized_path = os.path.abspath(normalized_path)
            
            # セキュリティチェック（パストラバーサル攻撃対策）
            if base_dir:
                base_abs = os.path.abspath(base_dir)
                if not normalized_path.startswith(base_abs):
                    self.logger.warning(f"基準ディレクトリ外のパスアクセス試行: {file_path}")
                    return None
            
            # 危険なパターンチェック（../ のみをチェック、通常のパスは許可）
            path_parts = normalized_path.split(os.sep)
            if '..' in path_parts:
                self.logger.warning(f"危険なパスパターン検出: {file_path}")
                return None
            
            return normalized_path
            
        except Exception as e:
            self.logger.error(f"安全パス取得失敗: {file_path}, error: {e}")
            return None
    
    def validate_path(self, file_path: str, must_exist: bool = False) -> bool:
        """
        パスの妥当性検証
        
        Args:
            file_path: 検証するファイルパス
            must_exist: 存在確認を行うかどうか
            
        Returns:
            bool: 妥当な場合True
        """
        try:
            # パスの正規化
            normalized_path = os.path.normpath(file_path)
            
            # セキュリティチェック（パストラバーサル攻撃対策）
            if '..' in normalized_path or normalized_path.startswith('/'):
                self.logger.warning(f"危険なパスパターン検出: {file_path}")
                return False
            
            # 存在確認
            if must_exist and not os.path.exists(normalized_path):
                self.logger.debug(f"パスが存在しません: {file_path}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"パス検証失敗: {file_path}, error: {e}")
            return False
    
    def normalize_path(self, file_path: str) -> str:
        """
        パスの正規化
        
        Args:
            file_path: 正規化するパス
            
        Returns:
            str: 正規化されたパス
        """
        try:
            # パスセパレータの統一
            normalized = file_path.replace('/', os.sep).replace('\\', os.sep)
            # 冗長なセパレータの除去
            normalized = os.path.normpath(normalized)
            # 絶対パス化
            if not os.path.isabs(normalized):
                normalized = os.path.abspath(normalized)
            
            return normalized
            
        except Exception as e:
            self.logger.error(f"パス正規化失敗: {file_path}, error: {e}")
            return file_path
    
    def get_relative_path(self, file_path: str, base_path: Optional[str] = None) -> str:
        """
        相対パスの取得
        
        Args:
            file_path: 対象ファイルパス
            base_path: 基準パス（Noneの場合は基準ディレクトリ使用）
            
        Returns:
            str: 相対パス
        """
        try:
            base = base_path or self._base_dir
            return os.path.relpath(file_path, base)
        except Exception as e:
            self.logger.error(f"相対パス取得失敗: {file_path}, error: {e}")
            return file_path
    
    def split_path_components(self, file_path: str) -> Tuple[str, str, str]:
        """
        パスコンポーネントの分割
        
        Args:
            file_path: 分割するファイルパス
            
        Returns:
            Tuple[str, str, str]: (ディレクトリ, ファイル名, 拡張子)
        """
        try:
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            name, ext = os.path.splitext(filename)
            
            return directory, name, ext
            
        except Exception as e:
            self.logger.error(f"パス分割失敗: {file_path}, error: {e}")
            return "", "", ""
    
    def find_files(self, directory: str, pattern: str = "*", recursive: bool = False) -> List[str]:
        """
        ファイル検索
        
        Args:
            directory: 検索ディレクトリ
            pattern: 検索パターン（グロブ形式）
            recursive: 再帰検索するかどうか
            
        Returns:
            List[str]: 見つかったファイルパスのリスト
        """
        try:
            from glob import glob
            
            if recursive:
                search_pattern = os.path.join(directory, '**', pattern)
                return glob(search_pattern, recursive=True)
            else:
                search_pattern = os.path.join(directory, pattern)
                return glob(search_pattern)
                
        except Exception as e:
            self.logger.error(f"ファイル検索失敗: {directory}, pattern: {pattern}, error: {e}")
            return []
    
    def get_file_info(self, file_path: str) -> dict:
        """
        ファイル情報の取得
        
        Args:
            file_path: 対象ファイルパス
            
        Returns:
            dict: ファイル情報辞書
        """
        try:
            if not os.path.exists(file_path):
                return {"exists": False}
            
            stat = os.stat(file_path)
            return {
                "exists": True,
                "size": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": stat.st_mtime,
                "is_file": os.path.isfile(file_path),
                "is_directory": os.path.isdir(file_path),
                "absolute_path": os.path.abspath(file_path),
                "relative_path": self.get_relative_path(file_path)
            }
            
        except Exception as e:
            self.logger.error(f"ファイル情報取得失敗: {file_path}, error: {e}")
            return {"exists": False, "error": str(e)}
    
    def clean_filename(self, filename: str) -> str:
        """
        ファイル名のクリーニング（不正文字除去）
        
        Args:
            filename: クリーニングするファイル名
            
        Returns:
            str: クリーニングされたファイル名
        """
        try:
            # Windows/Unix共通の禁止文字を除去
            invalid_chars = '<>:"/\\|?*'
            cleaned = filename
            
            for char in invalid_chars:
                cleaned = cleaned.replace(char, '_')
            
            # 連続するアンダースコアを単一に
            while '__' in cleaned:
                cleaned = cleaned.replace('__', '_')
            
            # 先頭・末尾のピリオドやスペースを除去
            cleaned = cleaned.strip('. ')
            
            # 空になった場合のデフォルト値
            if not cleaned:
                cleaned = "unnamed_file"
            
            return cleaned
            
        except Exception as e:
            self.logger.error(f"ファイル名クリーニング失敗: {filename}, error: {e}")
            return "cleaned_file"
    
    def backup_file(self, file_path: str, backup_suffix: str = "_backup") -> Optional[str]:
        """
        ファイルのバックアップ作成
        
        Args:
            file_path: バックアップ対象ファイル
            backup_suffix: バックアップファイルの接尾辞
            
        Returns:
            Optional[str]: バックアップファイルパス（失敗時はNone）
        """
        try:
            if not os.path.exists(file_path):
                self.logger.warning(f"バックアップ対象ファイルが存在しません: {file_path}")
                return None
            
            directory, name, ext = self.split_path_components(file_path)
            backup_filename = f"{name}{backup_suffix}{ext}"
            backup_path = os.path.join(directory, backup_filename)
            
            # 既存バックアップがある場合は番号付きに
            counter = 1
            original_backup_path = backup_path
            while os.path.exists(backup_path):
                backup_filename = f"{name}{backup_suffix}_{counter}{ext}"
                backup_path = os.path.join(directory, backup_filename)
                counter += 1
            
            # ファイルコピー
            import shutil
            shutil.copy2(file_path, backup_path)
            
            self.logger.info(f"バックアップ作成完了: {backup_path}")
            return backup_path
            
        except Exception as e:
            self.logger.error(f"バックアップ作成失敗: {file_path}, error: {e}")
            return None
    
    def get_directory_size(self, directory: str) -> dict:
        """
        ディレクトリサイズの取得
        
        Args:
            directory: 対象ディレクトリ
            
        Returns:
            dict: サイズ情報辞書
        """
        try:
            total_size = 0
            file_count = 0
            dir_count = 0
            
            for root, dirs, files in os.walk(directory):
                dir_count += len(dirs)
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
                        file_count += 1
            
            return {
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "file_count": file_count,
                "directory_count": dir_count
            }
            
        except Exception as e:
            self.logger.error(f"ディレクトリサイズ取得失敗: {directory}, error: {e}")
            return {"error": str(e)}

# グローバルインスタンス（シングルトンパターン）
_path_manager_instance = None

def get_path_manager() -> PathManager:
    """パス管理インスタンスの取得"""
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    return _path_manager_instance

# ショートカット関数群
def ensure_dir(directory_path: str) -> bool:
    """ディレクトリ確保のショートカット"""
    return get_path_manager().ensure_directory(directory_path)

def validate_path(file_path: str, must_exist: bool = False) -> bool:
    """パス検証のショートカット"""
    return get_path_manager().validate_path(file_path, must_exist)

def clean_filename(filename: str) -> str:
    """ファイル名クリーニングのショートカット"""
    return get_path_manager().clean_filename(filename)
