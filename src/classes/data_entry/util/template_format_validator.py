"""
テンプレート対応ファイル形式検証モジュール

データ登録機能で、選択されたデータセットに対応するテンプレートの
必須ファイル形式（拡張子）を検証する機能を提供。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Dict

try:
    from config import common as common_paths
except Exception:
    common_paths = None


@dataclass
class ValidationResult:
    """ファイル検証結果"""
    template_id: str
    required_extensions: List[str]  # 必須拡張子リスト（正規化済み）
    total_files: int
    valid_files: int
    valid_file_paths: List[str]
    invalid_file_paths: List[str]
    
    @property
    def is_valid(self) -> bool:
        """少なくとも1つの対応ファイルが含まれているか"""
        return self.valid_files > 0
    
    @property
    def validation_message(self) -> str:
        """検証結果メッセージ"""
        if not self.required_extensions:
            return "テンプレート情報なし"
        
        ext_display = " | ".join(self.required_extensions)
        if self.is_valid:
            return f"対応ファイル: {self.valid_files}/{self.total_files} 件 (対象: {ext_display})"
        else:
            return f"⚠ 対応ファイルが含まれていません (必須: {ext_display})"


class TemplateFormatValidator:
    """テンプレート対応ファイル形式検証クラス"""
    
    def __init__(self):
        self._formats_cache: Optional[Dict[str, List[str]]] = None
        self._json_path = self._get_json_path()
    
    def _get_json_path(self) -> str:
        """supported_formats.jsonのパスを取得"""
        sub = "output/supported_formats.json"
        if common_paths and hasattr(common_paths, "get_dynamic_file_path"):
            return common_paths.get_dynamic_file_path(sub)
        return sub
    
    def _normalize_extension(self, ext: str) -> str:
        """拡張子を正規化（小文字・ドットなし）"""
        ext = ext.strip().lower()
        if ext.startswith('.'):
            ext = ext[1:].strip()
        return ext
    
    def is_formats_json_available(self) -> bool:
        """supported_formats.jsonが存在するか"""
        return os.path.exists(self._json_path)
    
    def load_supported_formats(self) -> Dict[str, List[str]]:
        """
        supported_formats.jsonを読み込み、テンプレートID→拡張子リストのマップを構築
        
        Returns:
            Dict[str, List[str]]: {template_id: [正規化済み拡張子リスト]}
        """
        if self._formats_cache is not None:
            return self._formats_cache
        
        if not self.is_formats_json_available():
            self._formats_cache = {}
            return self._formats_cache
        
        try:
            with open(self._json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            formats_map = {}
            entries = data.get('entries', [])
            
            for entry in entries:
                template_name = entry.get('template_name', '')
                file_exts = entry.get('file_exts', [])
                
                if not template_name:
                    continue
                
                # 拡張子を正規化
                normalized_exts = [self._normalize_extension(ext) for ext in file_exts]
                
                # 既存のテンプレートがあれば拡張子をマージ
                if template_name in formats_map:
                    existing = set(formats_map[template_name])
                    existing.update(normalized_exts)
                    formats_map[template_name] = sorted(existing)
                else:
                    formats_map[template_name] = sorted(set(normalized_exts))
            
            self._formats_cache = formats_map
            return self._formats_cache
        
        except Exception as e:
            print(f"Error loading supported_formats.json: {e}")
            self._formats_cache = {}
            return self._formats_cache
    
    def get_extensions_for_template(self, template_id: str) -> List[str]:
        """
        テンプレートIDに対応する拡張子リストを取得
        
        Args:
            template_id: テンプレートID（例: "ARIM-R6_NM-001_20241111"）
        
        Returns:
            List[str]: 正規化済み拡張子リスト（例: ["jdf", "xlsx"]）
        """
        formats_map = self.load_supported_formats()
        return formats_map.get(template_id, [])
    
    def validate_files(
        self,
        file_paths: List[str],
        template_id: str
    ) -> ValidationResult:
        """
        ファイルリストを検証
        
        Args:
            file_paths: 検証対象ファイルパスリスト
            template_id: テンプレートID
        
        Returns:
            ValidationResult: 検証結果
        """
        required_extensions = self.get_extensions_for_template(template_id)
        
        valid_files = []
        invalid_files = []
        
        for file_path in file_paths:
            # ファイルの拡張子を取得・正規化
            _, ext = os.path.splitext(file_path)
            normalized_ext = self._normalize_extension(ext)
            
            if normalized_ext in required_extensions:
                valid_files.append(file_path)
            else:
                invalid_files.append(file_path)
        
        return ValidationResult(
            template_id=template_id,
            required_extensions=required_extensions,
            total_files=len(file_paths),
            valid_files=len(valid_files),
            valid_file_paths=valid_files,
            invalid_file_paths=invalid_files
        )
    
    def get_format_display_text(self, template_id: str) -> str:
        """
        テンプレート対応形式の表示用テキストを取得
        
        Args:
            template_id: テンプレートID
        
        Returns:
            str: 表示用テキスト（例: "xlsx | csv | jdf"）
        """
        if not self.is_formats_json_available():
            return "対応形式情報が読み込まれていません（設定→データ構造化タブでXLSXを読込）"
        
        extensions = self.get_extensions_for_template(template_id)
        
        if not extensions:
            return "このテンプレートの対応形式情報がありません"
        
        return " | ".join(extensions)
    
    def clear_cache(self):
        """キャッシュをクリア（設定更新時などに使用）"""
        self._formats_cache = None
