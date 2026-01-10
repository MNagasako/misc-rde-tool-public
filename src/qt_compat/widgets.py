"""
Qt互換レイヤー - Widgets モジュール

PyQt5とPySide6のQtWidgetsモジュールの互換レイヤー。
ほとんどのウィジェットクラスは互換性があるため、
主にエイリアスを提供する。

バージョン: 1.0.0
作成日: 2025-11-08
"""

from . import QtWidgets

# QShortcutの場所はフレームワークによって異なる
try:
    # PySide6では QtGui にある
    from . import QtGui
    QShortcut = QtGui.QShortcut
    QAction = QtGui.QAction  # PySide6ではQActionもQtGuiにある
except (AttributeError, ImportError):
    # PyQt5では QtWidgets にある
    QShortcut = QtWidgets.QShortcut
    QAction = QtWidgets.QAction

# よく使用されるウィジェットクラスのエイリアス
QApplication = QtWidgets.QApplication
QMainWindow = QtWidgets.QMainWindow
QWidget = QtWidgets.QWidget
QLabel = QtWidgets.QLabel
QPushButton = QtWidgets.QPushButton
QLineEdit = QtWidgets.QLineEdit
QTextEdit = QtWidgets.QTextEdit
QPlainTextEdit = QtWidgets.QPlainTextEdit
QTextBrowser = QtWidgets.QTextBrowser
QComboBox = QtWidgets.QComboBox
QCheckBox = QtWidgets.QCheckBox
QRadioButton = QtWidgets.QRadioButton
QButtonGroup = QtWidgets.QButtonGroup
QSpinBox = QtWidgets.QSpinBox
QDoubleSpinBox = QtWidgets.QDoubleSpinBox
QDateEdit = QtWidgets.QDateEdit
QTimeEdit = QtWidgets.QTimeEdit
QDateTimeEdit = QtWidgets.QDateTimeEdit
QSlider = QtWidgets.QSlider
QProgressBar = QtWidgets.QProgressBar

# レイアウト
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QGridLayout = QtWidgets.QGridLayout
QFormLayout = QtWidgets.QFormLayout

# コンテナ
QScrollArea = QtWidgets.QScrollArea
QSplitter = QtWidgets.QSplitter
QGroupBox = QtWidgets.QGroupBox
QFrame = QtWidgets.QFrame
QTabWidget = QtWidgets.QTabWidget
QStackedWidget = QtWidgets.QStackedWidget

# ダイアログ
QDialog = QtWidgets.QDialog
QMessageBox = QtWidgets.QMessageBox
QFileDialog = QtWidgets.QFileDialog
QProgressDialog = QtWidgets.QProgressDialog
QInputDialog = QtWidgets.QInputDialog
QDialogButtonBox = QtWidgets.QDialogButtonBox

# テーブル/リスト
QTableWidget = QtWidgets.QTableWidget
QTableWidgetItem = QtWidgets.QTableWidgetItem
QHeaderView = QtWidgets.QHeaderView
QListWidget = QtWidgets.QListWidget
QListWidgetItem = QtWidgets.QListWidgetItem
QTreeWidget = QtWidgets.QTreeWidget
QTreeWidgetItem = QtWidgets.QTreeWidgetItem
QAbstractItemView = QtWidgets.QAbstractItemView

# その他
QSizePolicy = QtWidgets.QSizePolicy
QCompleter = QtWidgets.QCompleter
# QShortcut and QAction are defined at the top due to framework differences
QMenu = QtWidgets.QMenu
QMenuBar = QtWidgets.QMenuBar
QToolBar = QtWidgets.QToolBar
QStatusBar = QtWidgets.QStatusBar

__all__ = [
    'QtWidgets',
    'QApplication',
    'QMainWindow',
    'QWidget',
    'QLabel',
    'QPushButton',
    'QLineEdit',
    'QTextEdit',
    'QPlainTextEdit',
    'QTextBrowser',
    'QComboBox',
    'QCheckBox',
    'QRadioButton',
    'QButtonGroup',
    'QSpinBox',
    'QDoubleSpinBox',
    'QDateEdit',
    'QTimeEdit',
    'QDateTimeEdit',
    'QSlider',
    'QProgressBar',
    'QVBoxLayout',
    'QHBoxLayout',
    'QGridLayout',
    'QFormLayout',
    'QScrollArea',
    'QSplitter',
    'QGroupBox',
    'QFrame',
    'QTabWidget',
    'QStackedWidget',
    'QDialog',
    'QMessageBox',
    'QFileDialog',
    'QProgressDialog',
    'QInputDialog',
    'QDialogButtonBox',
    'QTableWidget',
    'QTableWidgetItem',
    'QHeaderView',
    'QListWidget',
    'QListWidgetItem',
    'QTreeWidget',
    'QTreeWidgetItem',
    'QAbstractItemView',
    'QSizePolicy',
    'QCompleter',
    'QShortcut',
    'QMenu',
    'QMenuBar',
    'QToolBar',
    'QStatusBar',
    'QAction',
]
