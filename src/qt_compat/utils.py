"""
Qt互換レイヤー - ユーティリティ関数

PyQt5とPySide6の差異を吸収するヘルパー関数群
"""

from . import QtWidgets, QtCore, QtGui, USE_PYSIDE6

def get_screen_geometry(widget=None):
    """
    画面サイズを取得（PyQt5/PySide6互換）
    
    Args:
        widget: 基準となるウィジェット（省略時はプライマリスクリーン）
    
    Returns:
        QRect: 画面のジオメトリ
    """
    if USE_PYSIDE6:
        # PySide6: QScreen APIを使用
        app = QtWidgets.QApplication.instance()
        if widget is not None:
            # ウィジェットが表示されている画面を取得
            screen = widget.screen()
        else:
            # プライマリスクリーンを取得
            screen = app.primaryScreen()
        
        if screen:
            return screen.geometry()
        else:
            # フォールバック: デフォルトサイズ
            return QtCore.QRect(0, 0, 1920, 1080)
    else:
        # PyQt5: QDesktopWidget APIを使用
        desktop = QtWidgets.QApplication.desktop()
        if widget is not None:
            screen_num = desktop.screenNumber(widget)
            return desktop.screenGeometry(screen_num)
        else:
            return desktop.screenGeometry()


def get_screen_size(widget=None):
    """
    画面サイズを取得（幅、高さのタプル）
    
    Args:
        widget: 基準となるウィジェット（省略時はプライマリスクリーン）
    
    Returns:
        tuple: (width, height)
    """
    geometry = get_screen_geometry(widget)
    return (geometry.width(), geometry.height())


def get_available_geometry(widget=None):
    """
    利用可能な画面領域を取得（タスクバー等を除く）
    
    Args:
        widget: 基準となるウィジェット（省略時はプライマリスクリーン）
    
    Returns:
        QRect: 利用可能な領域のジオメトリ
    """
    if USE_PYSIDE6:
        # PySide6: QScreen APIを使用
        app = QtWidgets.QApplication.instance()
        if widget is not None:
            screen = widget.screen()
        else:
            screen = app.primaryScreen()
        
        if screen:
            return screen.availableGeometry()
        else:
            # フォールバック
            return QtCore.QRect(0, 0, 1920, 1000)
    else:
        # PyQt5: QDesktopWidget APIを使用
        desktop = QtWidgets.QApplication.desktop()
        if widget is not None:
            screen_num = desktop.screenNumber(widget)
            return desktop.availableGeometry(screen_num)
        else:
            return desktop.availableGeometry()


__all__ = [
    'get_screen_geometry',
    'get_screen_size',
    'get_available_geometry',
]
