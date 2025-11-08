"""
Qt互換レイヤー - PySide6専用

このモジュールは、PySide6 (LGPL)を使用してライセンス問題に対応します。
PyQt5の依存を完全に削除し、PySide6のみで動作します。

使用方法:
    from qt_compat import QtCore, QtWidgets, QtGui, Signal, Slot
    
    # 現在使用中のQt実装を確認
    from qt_compat import QT_VERSION
    print(f"Using: {QT_VERSION}")

バージョン: 2.0.0 (PySide6 Only)
作成日: 2025-11-08
更新日: 2025-11-08
"""

import sys
import logging

logger = logging.getLogger(__name__)

# PySide6のインポート（必須）
try:
    import PySide6
    from PySide6 import QtCore, QtWidgets, QtGui
    try:
        from PySide6 import QtWebEngineWidgets, QtWebEngineCore
        WEBENGINE_AVAILABLE = True
    except ImportError:
        logger.warning("PySide6.QtWebEngine* モジュールが利用できません")
        QtWebEngineWidgets = None
        QtWebEngineCore = None
        WEBENGINE_AVAILABLE = False
    
    USE_PYSIDE6 = True
    QT_VERSION = f'PySide6 {PySide6.__version__}'
    logger.info(f"Qt互換レイヤー: {QT_VERSION} を使用")
except ImportError as e:
    logger.error(f"PySide6のインポートに失敗しました: {e}")
    raise ImportError(
        "PySide6が必要です。\n"
        "pip install PySide6 でインストールしてください。"
    ) from e

# シグナル/スロットのエイリアス
from PySide6.QtCore import Signal, Slot

# WebEngine初期化の互換性処理
def initialize_webengine():
    """
    WebEngineの初期化処理を実行
    
    PyQt5とPySide6の両方で正しく動作するように初期化します。
    この関数はQApplicationインスタンス作成前に呼び出す必要があります。
    
    Returns:
        bool: 初期化が成功した場合True
    """
    if not WEBENGINE_AVAILABLE:
        logger.warning("WebEngineが利用できません")
        return False
    
    try:
        # OpenGLコンテキスト共有の設定
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
        
        # PySide6固有の設定
        if USE_PYSIDE6:
            # PySide6では追加の設定が必要な場合がある
            pass
        
        logger.info("WebEngine初期化完了")
        return True
    except Exception as e:
        logger.error(f"WebEngine初期化エラー: {e}")
        return False

# 互換性ユーティリティ関数
def get_qt_implementation():
    """
    現在使用中のQt実装の名前を取得
    
    Returns:
        str: 'PySide6'
    """
    return 'PySide6'

def is_pyside6():
    """
    PySide6を使用しているか確認
    
    Returns:
        bool: 常にTrue
    """
    return True

def is_pyqt5():
    """
    PyQt5を使用しているか確認（互換性のため残存）
    
    Returns:
        bool: 常にFalse
    """
    return False

# エクスポート
__all__ = [
    # Qt モジュール
    'QtCore',
    'QtWidgets',
    'QtGui',
    'QtWebEngineWidgets',
    'QtWebEngineCore',
    # シグナル/スロット
    'Signal',
    'Slot',
    # ステータス情報
    'USE_PYSIDE6',
    'QT_VERSION',
    'WEBENGINE_AVAILABLE',
    # ユーティリティ関数
    'initialize_webengine',
    'get_qt_implementation',
    'is_pyside6',
    'is_pyqt5',
]

# ユーティリティ関数のインポート
from .utils import get_screen_geometry, get_screen_size, get_available_geometry
__all__.extend(['get_screen_geometry', 'get_screen_size', 'get_available_geometry'])

# バージョン情報の出力
if __name__ == '__main__':
    print(f"Qt互換レイヤー (PySide6 Only)")
    print(f"  使用中: {QT_VERSION}")
    print(f"  WebEngine: {WEBENGINE_AVAILABLE}")
