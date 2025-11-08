"""
Qt互換レイヤー - WebEngine モジュール

PyQt5とPySide6のQtWebEngineモジュールの互換レイヤー。

注意:
- WebEngineWidgets と WebEngineCore は Qt 5.15/6.x で大きな違いがないが、
  一部のAPIに微妙な違いがある
- Cookie管理とインターセプター機能は特に注意が必要

バージョン: 1.0.0
作成日: 2025-11-08
"""

from . import QtWebEngineWidgets, QtWebEngineCore, WEBENGINE_AVAILABLE
import logging

logger = logging.getLogger(__name__)

if not WEBENGINE_AVAILABLE:
    logger.warning("WebEngineモジュールが利用できません")
    # ダミークラスを定義して、importエラーを回避
    class QWebEngineView:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WebEngineが利用できません")
    
    class QWebEngineProfile:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WebEngineが利用できません")
    
    class QWebEngineCookieStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WebEngineが利用できません")
    
    class QWebEngineUrlRequestInterceptor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WebEngineが利用できません")
    
    class QWebEngineSettings:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WebEngineが利用できません")
else:
    # よく使用されるクラスのエイリアス
    QWebEngineView = QtWebEngineWidgets.QWebEngineView
    
    # QWebEngineProfile の場所はフレームワークによって異なる
    try:
        # PySide6では QtWebEngineCore にある
        QWebEngineProfile = QtWebEngineCore.QWebEngineProfile
        QWebEngineSettings = QtWebEngineCore.QWebEngineSettings
    except AttributeError:
        # PyQt5では QtWebEngineWidgets にある
        QWebEngineProfile = QtWebEngineWidgets.QWebEngineProfile
        QWebEngineSettings = QtWebEngineWidgets.QWebEngineSettings
    
    QWebEngineCookieStore = QtWebEngineCore.QWebEngineCookieStore
    QWebEngineUrlRequestInterceptor = QtWebEngineCore.QWebEngineUrlRequestInterceptor

__all__ = [
    'QtWebEngineWidgets',
    'QtWebEngineCore',
    'QWebEngineView',
    'QWebEngineProfile',
    'QWebEngineCookieStore',
    'QWebEngineUrlRequestInterceptor',
    'QWebEngineSettings',
    'WEBENGINE_AVAILABLE',
]
