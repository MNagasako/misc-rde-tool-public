"""
テンプレート対応ファイル形式検証モジュール

データ登録機能で、選択されたデータセットに対応するテンプレートの
必須ファイル形式（拡張子）を検証する機能を提供。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

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


@dataclass
class TemplateResolution:
    """テンプレート解決結果"""

    requested_template_id: str
    resolved_template_id: str
    required_extensions: List[str]
    is_latest_for_equipment: bool
    is_exact_match: bool
    used_fallback: bool
    message: str


class TemplateFormatValidator:
    """テンプレート対応ファイル形式検証クラス"""
    
    def __init__(self):
        self._formats_cache: Optional[Dict[str, List[str]]] = None
        self._entries_cache: Optional[List[Dict[str, Any]]] = None
        self._equipment_candidates_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._json_path = self._get_json_path()

    def _parse_template_meta(self, template_name: str) -> Dict[str, Any]:
        """テンプレート名から装置ID・版・日付を抽出"""
        name = str(template_name or "").strip()
        upper = name.upper()

        equipment_id = ""
        m_eq = re.search(r'([A-Z]{1,5}-\d{3,4})', upper)
        if m_eq:
            equipment_id = m_eq.group(1)

        version = None
        m_v = re.search(r'[-_](?:V|R)(\d+)(?:[-_]|$)', upper)
        if m_v:
            try:
                version = int(m_v.group(1))
            except Exception:
                version = None

        date_str = ""
        m_date = re.search(r'(20\d{6})(?:$|\D)', name)
        if m_date:
            date_str = m_date.group(1)

        return {
            "equipment_id": equipment_id,
            "version": version,
            "date": date_str,
        }

    def _candidate_sort_key(self, item: Dict[str, Any]) -> tuple:
        """候補を新しい順に並べるためのキー"""
        version = item.get("version")
        date = item.get("date") or ""
        return (version if isinstance(version, int) else -1, date)

    def _distance_for_requested(self, *, requested: Dict[str, Any], candidate: Dict[str, Any]) -> tuple:
        """要求テンプレートに対する候補距離を計算（小さいほど近い）"""
        req_v = requested.get("version")
        req_d = requested.get("date") or ""
        c_v = candidate.get("version")
        c_d = candidate.get("date") or ""

        newer_penalty = 0
        version_gap = 9999
        date_gap = 99999999

        if isinstance(req_v, int) and isinstance(c_v, int):
            if c_v > req_v:
                newer_penalty = 1
            version_gap = abs(c_v - req_v)
        elif isinstance(req_v, int):
            newer_penalty = 1

        if req_d and c_d and req_d.isdigit() and c_d.isdigit():
            if int(c_d) > int(req_d):
                newer_penalty = 1
            date_gap = abs(int(c_d) - int(req_d))

        return (newer_penalty, version_gap, date_gap)
    
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
            entries_cache: List[Dict[str, Any]] = []
            entries = data.get('entries', [])
            
            for entry in entries:
                template_name = entry.get('template_name', '')
                file_exts = entry.get('file_exts', [])
                equipment_id = str(entry.get('equipment_id') or '').strip().upper()
                template_version = entry.get('template_version')
                
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

                parsed_meta = self._parse_template_meta(template_name)
                if not equipment_id:
                    equipment_id = parsed_meta.get('equipment_id') or ''

                version_value = parsed_meta.get('version')
                if not isinstance(version_value, int) and isinstance(template_version, int):
                    version_value = template_version

                entries_cache.append(
                    {
                        'template_name': template_name,
                        'equipment_id': equipment_id,
                        'version': version_value,
                        'date': parsed_meta.get('date') or '',
                        'extensions': normalized_exts,
                    }
                )
            
            self._formats_cache = formats_map
            self._entries_cache = entries_cache
            self._equipment_candidates_cache = None
            return self._formats_cache
        
        except Exception as e:
            print(f"Error loading supported_formats.json: {e}")
            self._formats_cache = {}
            self._entries_cache = []
            self._equipment_candidates_cache = None
            return self._formats_cache

    def _build_equipment_candidates(self) -> Dict[str, List[Dict[str, Any]]]:
        if self._equipment_candidates_cache is not None:
            return self._equipment_candidates_cache

        self.load_supported_formats()
        grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for item in self._entries_cache or []:
            equipment_id = str(item.get('equipment_id') or '').strip().upper()
            template_name = str(item.get('template_name') or '').strip()
            if not equipment_id or not template_name:
                continue

            eq_map = grouped.setdefault(equipment_id, {})
            current = eq_map.get(template_name)
            if current is None:
                current = {
                    'template_name': template_name,
                    'equipment_id': equipment_id,
                    'version': item.get('version'),
                    'date': item.get('date') or '',
                    'extensions': [],
                }
                eq_map[template_name] = current

            merged = set(current.get('extensions') or [])
            merged.update(item.get('extensions') or [])
            current['extensions'] = sorted(merged)

        result: Dict[str, List[Dict[str, Any]]] = {}
        for equipment_id, templates in grouped.items():
            values = list(templates.values())
            values.sort(key=self._candidate_sort_key, reverse=True)
            result[equipment_id] = values

        self._equipment_candidates_cache = result
        return result

    def resolve_template(self, template_id: str) -> TemplateResolution:
        """指定テンプレートに対する実解決結果を返す（版フォールバック対応）"""
        requested = str(template_id or '').strip()
        if not requested:
            return TemplateResolution(
                requested_template_id='',
                resolved_template_id='',
                required_extensions=[],
                is_latest_for_equipment=False,
                is_exact_match=False,
                used_fallback=False,
                message='テンプレートID未指定',
            )

        formats_map = self.load_supported_formats()
        if requested in formats_map:
            meta = self._parse_template_meta(requested)
            equipment_id = str(meta.get('equipment_id') or '').upper()
            candidates = self._build_equipment_candidates().get(equipment_id, []) if equipment_id else []
            latest_id = candidates[0]['template_name'] if candidates else requested
            return TemplateResolution(
                requested_template_id=requested,
                resolved_template_id=requested,
                required_extensions=formats_map.get(requested, []),
                is_latest_for_equipment=(requested == latest_id),
                is_exact_match=True,
                used_fallback=False,
                message='完全一致',
            )

        requested_meta = self._parse_template_meta(requested)
        requested_eq = str(requested_meta.get('equipment_id') or '').upper()
        if not requested_eq:
            return TemplateResolution(
                requested_template_id=requested,
                resolved_template_id=requested,
                required_extensions=[],
                is_latest_for_equipment=False,
                is_exact_match=False,
                used_fallback=False,
                message='装置IDを特定できないため解決不可',
            )

        candidates = self._build_equipment_candidates().get(requested_eq, [])
        if not candidates:
            return TemplateResolution(
                requested_template_id=requested,
                resolved_template_id=requested,
                required_extensions=[],
                is_latest_for_equipment=False,
                is_exact_match=False,
                used_fallback=False,
                message=f'装置ID {requested_eq} の候補なし',
            )

        matched = sorted(
            candidates,
            key=lambda c: self._distance_for_requested(requested=requested_meta, candidate=c),
        )[0]
        resolved_id = matched.get('template_name') or requested
        resolved_exts = list(matched.get('extensions') or formats_map.get(resolved_id, []))
        latest_id = candidates[0].get('template_name') if candidates else resolved_id

        return TemplateResolution(
            requested_template_id=requested,
            resolved_template_id=resolved_id,
            required_extensions=resolved_exts,
            is_latest_for_equipment=(resolved_id == latest_id),
            is_exact_match=False,
            used_fallback=(resolved_id != requested),
            message=f'装置ID {requested_eq} で近い版へフォールバック',
        )
    
    def get_extensions_for_template(self, template_id: str) -> List[str]:
        """
        テンプレートIDに対応する拡張子リストを取得
        
        Args:
            template_id: テンプレートID（例: "ARIM-R6_NM-001_20241111"）
        
        Returns:
            List[str]: 正規化済み拡張子リスト（例: ["jdf", "xlsx"]）
        """
        return self.resolve_template(template_id).required_extensions

    def get_template_reference_text(self, template_id: str) -> str:
        """UI表示用: 参照テンプレート情報文字列"""
        res = self.resolve_template(template_id)
        if not res.resolved_template_id:
            return "参照テンプレート: なし"

        status = "最新" if res.is_latest_for_equipment else "旧版"
        if res.is_exact_match:
            return f"参照テンプレート: {res.resolved_template_id}（{status}）"
        if res.used_fallback:
            return (
                f"参照テンプレート: {res.resolved_template_id}（{status}・フォールバック）"
                f" / 指定: {res.requested_template_id}"
            )
        return f"参照テンプレート: {res.resolved_template_id}（{status}）"
    
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
        self._entries_cache = None
        self._equipment_candidates_cache = None
