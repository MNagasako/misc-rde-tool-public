"""
報告書機能 - ユーティリティモジュール

HTML解析やデータ変換などの補助機能を提供します。
"""

from .html_parser import safe_extract_text, safe_find_tag

__all__ = [
    "safe_extract_text",
    "safe_find_tag",
]
