from dataclasses import dataclass
from typing import Optional


@dataclass
class SupportedFileFormatEntry:
    equipment_id: str
    # 正規化後の拡張子リスト（例: ['xlsx', 'csv']）
    file_exts: list
    # 拡張子ごとの説明（例: {'xlsx': '測定条件', 'csv': 'データ'}）
    file_descs: dict
    template_name: str = ""
    template_version: Optional[int] = None
    source_sheet: str = ""
    # 元の複合記述（デバッグ用）
    original_format: str = ""
