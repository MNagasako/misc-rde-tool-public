"""
データ取得2機能 - ファイルフィルタユーティリティ
ファイルフィルタ条件の検証・適用処理
"""

import fnmatch
import os
from typing import Dict, List, Any, Optional

def match_filename_pattern(filename: str, pattern: str) -> bool:
    """
    ファイル名パターンマッチング
    *をワイルドカードとして使用可能
    """
    if not pattern:
        return True
    
    # 完全一致チェック
    if pattern == filename:
        return True
        
    # ワイルドカードパターンマッチング
    return fnmatch.fnmatch(filename.lower(), pattern.lower())

def match_file_extension(filename: str, extensions: List[str]) -> bool:
    """拡張子フィルタマッチング"""
    if not extensions:
        return True
        
    if not filename or '.' not in filename:
        return False
        
    file_ext = filename.split('.')[-1].lower()
    return file_ext in [ext.lower() for ext in extensions]

def match_file_size(file_size: int, size_min: int = 0, size_max: int = 0) -> bool:
    """ファイルサイズフィルタマッチング"""
    if size_min > 0 and file_size < size_min:
        return False
        
    if size_max > 0 and file_size > size_max:
        return False
        
    return True

def apply_file_filter(file_entry: Dict[str, Any], filter_config: Dict[str, Any]) -> bool:
    """
    ファイルエントリに対してフィルタを適用
    
    Args:
        file_entry: ファイル情報（attributes含む）
        filter_config: フィルタ設定
        
    Returns:
        bool: フィルタを通過したかどうか
    """
    if not isinstance(file_entry, dict) or file_entry.get("type") != "file":
        return False
        
    attributes = file_entry.get("attributes", {})
    
    # ファイルタイプフィルタ
    file_types = filter_config.get("file_types", [])
    if file_types:
        file_type = attributes.get("fileType", "")
        if file_type not in file_types:
            return False
    
    # メディアタイプフィルタ        
    media_types = filter_config.get("media_types", [])
    if media_types:
        media_type = attributes.get("mediaType", "")
        if media_type not in media_types:
            return False
    
    # ファイル名・拡張子フィルタ
    filename = attributes.get("fileName", "")
    
    # 拡張子フィルタ
    extensions = filter_config.get("extensions", [])
    if not match_file_extension(filename, extensions):
        return False
    
    # ファイル名パターンフィルタ
    filename_pattern = filter_config.get("filename_pattern", "")
    if not match_filename_pattern(filename, filename_pattern):
        return False
    
    # ファイルサイズフィルタ
    file_size = attributes.get("fileSize", 0)
    size_min = filter_config.get("size_min", 0)
    size_max = filter_config.get("size_max", 0)
    if not match_file_size(file_size, size_min, size_max):
        return False
    
    return True

def filter_file_list(file_entries: List[Dict[str, Any]], 
                    filter_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ファイルリストにフィルタを適用
    
    Args:
        file_entries: ファイルエントリのリスト
        filter_config: フィルタ設定
        
    Returns:
        List[Dict]: フィルタ適用後のファイルエントリリスト
    """
    filtered_files = []
    max_count = filter_config.get("max_download_count", 0)
    
    for entry in file_entries:
        if apply_file_filter(entry, filter_config):
            filtered_files.append(entry)
            
            # ダウンロード上限チェック
            if max_count > 0 and len(filtered_files) >= max_count:
                break
                
    return filtered_files

def validate_filter_config(filter_config: Dict[str, Any]) -> List[str]:
    """
    フィルタ設定の検証
    
    Returns:
        List[str]: エラーメッセージのリスト（空の場合は正常）
    """
    errors = []
    
    # ファイルサイズ設定の検証
    size_min = filter_config.get("size_min", 0)
    size_max = filter_config.get("size_max", 0)
    
    if size_min < 0:
        errors.append("最小ファイルサイズは0以上で指定してください")
        
    if size_max < 0:
        errors.append("最大ファイルサイズは0以上で指定してください")
        
    if size_min > 0 and size_max > 0 and size_min > size_max:
        errors.append("最小ファイルサイズが最大ファイルサイズを上回っています")
    
    # ダウンロード上限の検証
    max_count = filter_config.get("max_download_count", 0)
    if max_count < 0:
        errors.append("ダウンロード上限は0以上で指定してください")
        
    return errors

def get_filter_summary(filter_config: Dict[str, Any]) -> str:
    """フィルタ設定の概要文字列を生成"""
    parts = []
    
    # ファイルタイプ
    file_types = filter_config.get("file_types", [])
    if file_types:
        parts.append(f"タイプ: {', '.join(file_types)}")
    
    # メディアタイプ    
    media_types = filter_config.get("media_types", [])
    if media_types:
        parts.append(f"メディア: {', '.join(media_types)}")
        
    # 拡張子
    extensions = filter_config.get("extensions", [])
    if extensions:
        parts.append(f"拡張子: {', '.join(extensions)}")
        
    # ファイル名パターン
    filename_pattern = filter_config.get("filename_pattern", "")
    if filename_pattern:
        parts.append(f"名前: {filename_pattern}")
        
    # ファイルサイズ
    size_min = filter_config.get("size_min", 0)
    size_max = filter_config.get("size_max", 0)
    if size_min > 0 or size_max > 0:
        if size_min > 0 and size_max > 0:
            parts.append(f"サイズ: {size_min:,}-{size_max:,}bytes")
        elif size_min > 0:
            parts.append(f"サイズ: {size_min:,}bytes以上")
        elif size_max > 0:
            parts.append(f"サイズ: {size_max:,}bytes以下")
    
    # ダウンロード上限
    max_count = filter_config.get("max_download_count", 0)
    if max_count > 0:
        parts.append(f"上限: {max_count}件")
        
    return "; ".join(parts) if parts else "フィルタなし"