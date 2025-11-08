"""
Qt互換レイヤー - Core モジュール

PyQt5とPySide6のQtCoreモジュールの違いを吸収する互換レイヤー。
主な違い:
- pyqtSignal → Signal
- pyqtSlot → Slot

バージョン: 1.0.0
作成日: 2025-11-08
"""

from . import QtCore, USE_PYSIDE6, Signal, Slot

# よく使用されるクラスのエイリアス
Qt = QtCore.Qt
QTimer = QtCore.QTimer
QThread = QtCore.QThread
QUrl = QtCore.QUrl
QObject = QtCore.QObject
QEvent = QtCore.QEvent
QEventLoop = QtCore.QEventLoop
QCoreApplication = QtCore.QCoreApplication
QDateTime = QtCore.QDateTime
QDate = QtCore.QDate
QTime = QtCore.QTime
QStringListModel = QtCore.QStringListModel
QMetaObject = QtCore.QMetaObject
QSize = QtCore.QSize
QSizeF = QtCore.QSizeF
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
QRect = QtCore.QRect
QRectF = QtCore.QRectF

# Q_ARG互換レイヤー（PySide6専用）
# PySide6ではQMetaObject.invokeMethodが直接Pythonオブジェクトを受け取る
def Q_ARG(type_obj, value):
    """PySide6互換のQ_ARG（実際には何もしない）"""
    return value

__all__ = [
    'QtCore',
    'Qt',
    'QTimer',
    'QThread',
    'QUrl',
    'QObject',
    'QEvent',
    'QEventLoop',
    'QCoreApplication',
    'QDateTime',
    'QDate',
    'QTime',
    'QStringListModel',
    'QMetaObject',
    'QSize',
    'QSizeF',
    'QPoint',
    'QPointF',
    'QRect',
    'QRectF',
    'Signal',
    'Slot',
    'Q_ARG',
]
