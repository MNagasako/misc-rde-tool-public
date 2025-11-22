"""
テーマ管理モジュール - ARIM RDE Tool v2.1.6

ライト/ダークモード対応のテーマ管理システム。
Material Design準拠の配色を提供。

主要コンポーネント:
- ThemeKey: UI要素の色キー定義
- LightTheme: ライトモード配色
- DarkTheme: ダークモード配色
- ThemeManager: テーマ管理・切替機能
- get_theme_manager: グローバルアクセス用ヘルパー
- get_color: 色取得用ヘルパー
"""

from .theme_keys import ThemeKey
from .theme_manager import ThemeManager, ThemeMode, get_theme_manager, get_color
from .light_theme import LightTheme
from .dark_theme import DarkTheme

__all__ = [
    'ThemeKey',
    'ThemeManager',
    'ThemeMode',
    'get_theme_manager',
    'get_color',
    'LightTheme',
    'DarkTheme',
]

__version__ = '1.0.0'
