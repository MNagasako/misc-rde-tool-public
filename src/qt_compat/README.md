# Qt互換レイヤー (qt_compat)

PyQt5からPySide6への段階的移行を可能にする互換レイヤー

## 概要

このモジュールは、PyQt5とPySide6の両方を透過的にサポートし、アプリケーションコードを変更することなくQt実装を切り替えることができます。

## 主な機能

- **自動フォールバック**: PySide6のインポートに失敗した場合、自動的にPyQt5を使用
- **シグナル/スロット互換**: `pyqtSignal` → `Signal`, `pyqtSlot` → `Slot` の自動変換
- **WebEngine初期化**: PyQt5/PySide6の初期化の違いを吸収
- **環境変数サポート**: `USE_PYSIDE6` で実装を選択可能

## 使用方法

### 基本的な使用

```python
# 従来のPyQt5形式
# from PyQt5.QtWidgets import QApplication, QWidget
# from PyQt5.QtCore import Qt, pyqtSignal

# 互換レイヤー使用
from qt_compat import QtWidgets, QtCore, Signal

app = QtWidgets.QApplication([])
widget = QtWidgets.QWidget()

class MyWidget(QtWidgets.QWidget):
    # pyqtSignal → Signal
    my_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
```

### 便利なエイリアス

```python
# 個別インポート
from qt_compat.widgets import QApplication, QWidget, QPushButton
from qt_compat.core import Qt, QTimer, Signal, Slot
from qt_compat.gui import QFont, QIcon

# WebEngine
from qt_compat.webengine import QWebEngineView, QWebEngineProfile
```

### WebEngineの初期化

```python
from qt_compat import initialize_webengine, QtWidgets

# QApplication作成前に初期化
initialize_webengine()

app = QtWidgets.QApplication([])
# ... アプリケーションコード
```

### 現在の実装を確認

```python
from qt_compat import QT_VERSION, USE_PYSIDE6, get_qt_implementation

print(f"Using: {QT_VERSION}")
print(f"PySide6: {USE_PYSIDE6}")
print(f"Implementation: {get_qt_implementation()}")
```

## 環境変数

### USE_PYSIDE6

Qt実装の選択を制御します。

```bash
# PySide6を優先（デフォルト）
export USE_PYSIDE6=true
python your_app.py

# PyQt5を強制使用
export USE_PYSIDE6=false
python your_app.py
```

Windows PowerShell:
```powershell
$env:USE_PYSIDE6="true"
python your_app.py
```

## モジュール構成

```
src/qt_compat/
  ├── __init__.py       # メインモジュール・自動選択ロジック
  ├── core.py           # QtCore互換（Signal, Slot含む）
  ├── widgets.py        # QtWidgets互換
  ├── gui.py            # QtGui互換
  └── webengine.py      # QtWebEngine互換
```

## PyQt5からの移行手順

### ステップ1: インポート文の置換

```python
# Before
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

# After
from qt_compat.widgets import QApplication
from qt_compat.core import Qt, QTimer, Signal
```

### ステップ2: シグナル/スロットの更新

```python
# Before
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class MyClass(QObject):
    my_signal = pyqtSignal(str)
    
    @pyqtSlot()
    def my_slot(self):
        pass

# After
from qt_compat.core import QObject, Signal, Slot

class MyClass(QObject):
    my_signal = Signal(str)
    
    @Slot()
    def my_slot(self):
        pass
```

### ステップ3: WebEngine初期化の更新

```python
# Before
from PyQt5.QtCore import QCoreApplication, Qt
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PyQt5.QtWidgets import QApplication

# After
from qt_compat import initialize_webengine
from qt_compat.widgets import QApplication

initialize_webengine()
app = QApplication([])
```

## 互換性マトリックス

| 機能 | PyQt5 | PySide6 | 互換レイヤー |
|------|-------|---------|-------------|
| QtWidgets | ✓ | ✓ | ✓ |
| QtCore | ✓ | ✓ | ✓ |
| QtGui | ✓ | ✓ | ✓ |
| QtWebEngineWidgets | ✓ | ✓ | ✓ |
| QtWebEngineCore | ✓ | ✓ | ✓ |
| pyqtSignal/Signal | ✓ | ✓ | ✓ (自動変換) |
| pyqtSlot/Slot | ✓ | ✓ | ✓ (自動変換) |

## 既知の制限事項

1. **複雑なシグナル定義**: 一部の複雑なシグナル定義では、手動調整が必要な場合があります
2. **WebEngine詳細動作**: Cookie管理などの詳細動作に微妙な違いがある場合があります
3. **スタイルシート**: 一部のQSSプロパティに互換性問題がある可能性があります

## トラブルシューティング

### PySide6とPyQt5の両方がインストールされていない

```
ImportError: PyQt5またはPySide6が必要です。
```

**解決方法**:
```bash
pip install PySide6
# または
pip install PyQt5
```

### WebEngineが利用できない

```
WARNING: WebEngineモジュールが利用できません
```

**解決方法**:
```bash
pip install PySide6-WebEngine
# または
pip install PyQtWebEngine
```

### 環境変数が反映されない

環境変数は、Pythonプロセス起動時に読み込まれます。
変更後は、新しいターミナルセッションでアプリケーションを再起動してください。

## テスト

互換レイヤーのテスト:

```bash
# 互換レイヤーの情報を表示
python -m qt_compat

# PySide6で実行
USE_PYSIDE6=true python your_app.py

# PyQt5で実行
USE_PYSIDE6=false python your_app.py
```

## バージョン情報

- バージョン: 1.0.0
- 作成日: 2025-11-08
- 対応PyQt5: 5.15.x
- 対応PySide6: 6.x

## 参考資料

- [PySide6公式ドキュメント](https://doc.qt.io/qtforpython/)
- [PyQt5→PySide6移行ガイド](https://doc.qt.io/qtforpython/porting_from2.html)
- [Qt 6 for Python変更点](https://wiki.qt.io/Qt_for_Python)
