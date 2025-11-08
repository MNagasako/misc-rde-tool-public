"""
Qt互換レイヤー - Gui モジュール

PyQt5とPySide6のQtGuiモジュールの互換レイヤー。

バージョン: 1.0.0
作成日: 2025-11-08
"""

from . import QtGui

# よく使用されるクラスのエイリアス
QFont = QtGui.QFont
QIcon = QtGui.QIcon
QPixmap = QtGui.QPixmap
QImage = QtGui.QImage
QColor = QtGui.QColor
QPainter = QtGui.QPainter
QPen = QtGui.QPen
QBrush = QtGui.QBrush
QKeySequence = QtGui.QKeySequence
QFontMetrics = QtGui.QFontMetrics
QTextCursor = QtGui.QTextCursor
QDesktopServices = QtGui.QDesktopServices
QPalette = QtGui.QPalette
QCursor = QtGui.QCursor
QIntValidator = QtGui.QIntValidator  # PySide6/PyQt5共通
QDoubleValidator = QtGui.QDoubleValidator
QValidator = QtGui.QValidator
QShortcut = QtGui.QShortcut

__all__ = [
    'QtGui',
    'QFont',
    'QIcon',
    'QPixmap',
    'QImage',
    'QColor',
    'QPainter',
    'QPen',
    'QBrush',
    'QKeySequence',
    'QFontMetrics',
    'QTextCursor',
    'QDesktopServices',
    'QPalette',
    'QCursor',
    'QIntValidator',
    'QDoubleValidator',
    'QValidator',
    'QShortcut',
]
