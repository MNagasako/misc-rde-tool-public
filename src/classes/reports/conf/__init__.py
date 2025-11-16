"""
報告書機能 - 設定モジュール

フィールド定義、URL定義、検索条件などの設定を提供します。
"""

from .field_definitions import (
    EXCEL_COLUMNS,
    BASE_URL,
    REPORT_LIST_URL,
    REPORT_DETAIL_URL,
)

__all__ = [
    "EXCEL_COLUMNS",
    "BASE_URL",
    "REPORT_LIST_URL",
    "REPORT_DETAIL_URL",
]
