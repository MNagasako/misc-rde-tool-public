from __future__ import annotations

import json
import shutil
from typing import List

from classes.config.core.models import SupportedFileFormatEntry
from classes.config.core.xlsx_supported_formats import parse_supported_formats

try:
    from config import common as common_paths
except Exception:
    common_paths = None  # テスト環境で未解決でも機能は動作可能に


def get_default_input_dir() -> str:
    # デモ配置に合わせた既定ディレクトリ
    sub = "input/arim"
    if common_paths and hasattr(common_paths, "get_dynamic_file_path"):
        return common_paths.get_dynamic_file_path(sub)
    # フォールバック: 相対
    return sub


def get_default_output_path() -> str:
    sub = "output/supported_formats.json"
    if common_paths and hasattr(common_paths, "get_dynamic_file_path"):
        return common_paths.get_dynamic_file_path(sub)
    return sub


def copy_to_input(src_path: str) -> str:
    """選択されたXLSXを`input/arim/`配下へコピーして保存パスを返す。"""
    import os
    in_dir = get_default_input_dir()
    os.makedirs(in_dir, exist_ok=True)
    base = os.path.basename(src_path)
    dst = os.path.join(in_dir, base)
    # 同名がある場合は上書き（要件に応じて重複回避へ拡張可）
    shutil.copy2(src_path, dst)
    return dst


def parse_and_save(xlsx_path: str) -> List[SupportedFileFormatEntry]:
    """XLSXを解析し、JSONへ保存する。元ファイルパスも記録。"""
    entries = parse_supported_formats(xlsx_path)
    out_path = get_default_output_path()
    # JSON保存
    payload = [
        {
            "equipment_id": e.equipment_id,
            "file_exts": e.file_exts,
            "file_descs": e.file_descs,
            "template_name": e.template_name,
            "template_version": e.template_version,
            "source_sheet": e.source_sheet,
            "original_format": e.original_format,
        }
        for e in entries
    ]
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    # メタ情報も保存（元ファイルパス、解析日時）
    import datetime
    meta = {
        "source_file": xlsx_path,
        "parsed_at": datetime.datetime.now().isoformat(),
        "entries": payload,
    }
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return entries
