"""
データエントリー登録修正モジュール

このモジュールは、データエントリー登録修正に関連するUIを提供します：
- 通常登録機能（従来）
- タブ対応データ登録機能（新規）
"""

from .data_register_ui_creator import create_data_register_widget
from .data_register_tab_widget import create_data_register_tab_widget, DataRegisterTabWidget

__all__ = [
    "DataRegisterWidget",
    "create_data_register_widget",
    "create_data_register_tab_widget", 
    "DataRegisterTabWidget"
]
