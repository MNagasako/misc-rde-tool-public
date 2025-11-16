"""
設備データ取得・管理モジュール

ARIM設備情報サイトからデータを取得し、Excel/JSON形式で出力する機能を提供します。

主要コンポーネント:
- core: データ取得・処理ロジック
- ui: ユーザーインターフェース
- util: ユーティリティ関数
- conf: 設定・定義
"""

__version__ = "1.0.0"
__author__ = "ARIM RDE Tool"

# UIコンポーネント（Qt環境が利用可能な場合のみインポート）
try:
    from classes.equipment.ui import EquipmentWidget
    __all__ = ['EquipmentWidget']
except ImportError:
    # Qt環境がない場合はスキップ（テスト環境など）
    __all__ = []
