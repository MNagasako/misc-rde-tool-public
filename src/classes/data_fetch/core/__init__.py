"""
データ取得関連機能統合パッケージ v1.17.2

このパッケージは、ARIM RDE Toolのデータ取得関連機能を統合管理します。

モジュール構成:
- core/: コア機能（データ管理、データツリー管理）
- api/: API通信機能（RDE APIクライアント）
- storage/: 保存機能（ファイル保存、画像保存）
- utils/: ユーティリティ機能（データ抽出、検証、整形）

使用例:
    from classes.data.data_fetch.core import DataManager
    from classes.data.data_fetch.api import RDEApiClient
    from classes.data.data_fetch.storage import FileSaver, ImageSaver

"""

__version__ = "1.17.4"
__author__ = "ARIM RDE Tool Team"

# パッケージ内の主要クラス・関数のエクスポート
__all__ = [
    # Core
    "DataManager",
    "DataTreeManager",
    
    # API
    "RDEApiClient",
    
    # Storage
    "FileSaver",
    "ImageSaver",
]

# 遅延インポート（必要時にのみ読み込み）
def __getattr__(name):
    if name in __all__:
        # 動的インポートで循環依存を回避
        if name == "DataManager":
            from core.data_manager import DataManager
            return DataManager
        elif name == "DataTreeManager":
            from core.datatree_manager import DataTreeManager
            return DataTreeManager
        elif name == "RDEApiClient":
            from .api.rde_api_client import RDEApiClient
            return RDEApiClient
        elif name == "FileSaver":
            from .storage.file_saver import FileSaver
            return FileSaver
        elif name == "ImageSaver":
            from .storage.image_saver import ImageSaver
            return ImageSaver
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
