"""
使用方法タブ - ARIM RDE Tool v2.4.13
アプリケーションの使用方法を表示
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QLabel, QTextBrowser
    )
    from qt_compat.core import Qt
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

from classes.help.util.markdown_renderer import load_help_markdown, set_markdown_document


# ダミーの使用方法テキスト（後で実際の内容に置き換え）
DEFAULT_USAGE_TEXT = """
# ARIM RDE Tool 使用方法

## 概要
このツールは、DICE/RDEシステムからARIMデータポータルへデータを移行するためのアプリケーションです。

## 基本的な使い方

### 1. ログイン
左側のメニューから「ログイン」を選択し、RDEシステムにログインします。

### 2. データセット選択
「基本情報」メニューから課題番号を入力し、データセットを選択します。

### 3. データ取得
「データ取得」または「データ取得2」メニューから、必要なデータをダウンロードします。

### 4. データ登録
「データ登録」メニューから、ARIMデータポータルにデータをアップロードします。

## 詳細機能

### AI分析機能
「AI分析」メニューから、データセットの書誌情報を自動生成できます。

### データポータル連携
「データポータル」メニューから、ARIMデータポータルと直接連携できます。

## 設定

「設定」メニューから、以下の設定を変更できます：
- プロキシ設定
- ネットワーク設定
- アプリケーション設定
- 自動ログイン設定
- トークン状態確認

## トラブルシューティング

### ログインできない場合
1. ネットワーク接続を確認してください
2. プロキシ設定を確認してください
3. ブラウザのキャッシュをクリアしてください

### データ取得できない場合
1. トークンの有効期限を確認してください
2. 課題番号が正しいか確認してください


---

**注意**: この使用方法は後で詳細な内容に更新される予定です。
"""


class UsageTab(QWidget):
    """使用方法タブ - アプリケーション使用方法表示"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # タイトル
        title_label = QLabel("使用方法")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 使用方法表示エリア
        self.usage_browser = QTextBrowser()
        self.usage_browser.setOpenExternalLinks(True)
        # ドキュメントマージンを小さく設定
        self.usage_browser.document().setDocumentMargin(8)
        
        # 使用方法テキストを読み込み
        usage_text, base_dir = self.load_usage_text()

        # Markdownを直接適用
        set_markdown_document(self.usage_browser, usage_text, base_dir)
        
        layout.addWidget(self.usage_browser)
    
    def load_usage_text(self) -> Tuple[str, Optional[str]]:
        """使用方法テキストを読み込み"""
        try:
            return load_help_markdown('usage.md')
        except FileNotFoundError as e:
            logger.warning("使用方法ファイルが見つかりません: %s", e)
            return DEFAULT_USAGE_TEXT, None
        except Exception as e:
            logger.error(f"使用方法ファイル読み込みエラー: {e}")
            return DEFAULT_USAGE_TEXT, None


def create_usage_tab(parent=None):
    """使用方法タブを作成"""
    try:
        return UsageTab(parent)
    except Exception as e:
        logger.error(f"使用方法タブ作成エラー: {e}")
        return None
