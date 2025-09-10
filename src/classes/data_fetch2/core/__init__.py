"""
Data Fetch2 Package - ARIM RDE Tool v1.17.0

データセット選択・ファイル一括取得機能の改良版パッケージ
データ取得UIウィジェットとファイル取得ロジックを統合

主要機能:
- データセット選択UIウィジェット
- ファイル一括取得処理
- プログレス表示対応
- パス安全化処理

Modules:
- ui.data_fetch2_widget: UIウィジェット作成
- logic.fetch2_filelist_logic: ファイル取得処理ロジック
"""

from .ui.data_fetch2_widget import create_data_fetch2_widget
from .logic.fetch2_filelist_logic import (
    fetch_files_json_for_dataset,
    download_all_files_from_files_json,
    safe_show_message,
    replace_invalid_path_chars
)

__all__ = [
    'create_data_fetch2_widget',
    'fetch_files_json_for_dataset',
    'download_all_files_from_files_json',
    'safe_show_message',
    'replace_invalid_path_chars'
]
