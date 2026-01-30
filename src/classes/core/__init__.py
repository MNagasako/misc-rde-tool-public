"""
コア機能モジュール

このモジュールは、アプリケーションの基盤機能を提供します：
- AppInitializer: アプリケーション初期化
- BrowserController: ブラウザ制御機能
- EventHandler: イベントハンドリング
- BatchProcessor: バッチ処理機能
- ImageInterceptor: 画像インターセプト機能  
- ImageProcessor: 画像処理機能
"""

from __future__ import annotations

from importlib import import_module
import sys

__all__ = [
    "AppInitializer",
    "BrowserController",
    "EventHandler",
    "BatchProcessor",
    "ImageInterceptor",
    "ImageProcessor",
]

_LAZY_IMPORTS = {
    "AppInitializer": ".app_initializer",
    "BrowserController": ".browser_controller",
    "EventHandler": ".event_handler",
    "BatchProcessor": ".batch_processor",
    "ImageInterceptor": ".image_interceptor",
    "ImageProcessor": ".image_processor",
}

# PyInstaller frozen builds cannot always detect lazy imports.
# Import explicitly in frozen mode to ensure modules are bundled.
try:
    if getattr(sys, "frozen", False):
        from .app_initializer import AppInitializer  # noqa: F401
        from .browser_controller import BrowserController  # noqa: F401
        from .event_handler import EventHandler  # noqa: F401
        from .batch_processor import BatchProcessor  # noqa: F401
        from .image_interceptor import ImageInterceptor  # noqa: F401
        from .image_processor import ImageProcessor  # noqa: F401
except Exception:
    pass


def __getattr__(name: str):
    module_name = _LAZY_IMPORTS.get(name)
    if not module_name:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
