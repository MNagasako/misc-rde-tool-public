"""
使用方法タブ - ARIM RDE Tool v2.1.3
アプリケーションの使用方法を表示
"""

import logging
from pathlib import Path

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

## お問い合わせ
不明な点がございましたら、ARIM事業までお問い合わせください。

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # タイトル
        title_label = QLabel("使用方法")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 使用方法表示エリア
        self.usage_browser = QTextBrowser()
        self.usage_browser.setOpenExternalLinks(True)
        
        # 使用方法テキストを読み込み
        usage_text = self.load_usage_text()
        
        # Markdownレンダリング
        try:
            from classes.help.util.markdown_renderer import render_markdown_to_html
            html = render_markdown_to_html(usage_text)
            self.usage_browser.setHtml(html)
        except ImportError:
            # フォールバック: プレーンテキスト
            self.usage_browser.setPlainText(usage_text)
        
        layout.addWidget(self.usage_browser)
    
    def load_usage_text(self) -> str:
        """使用方法テキストを読み込み"""
        try:
            # Markdownファイルから読み込み
            from config.common import get_base_dir
            import os
            
            md_path = os.path.join(get_base_dir(), 'docs', 'help', 'usage.md')
            
            if os.path.exists(md_path):
                with open(md_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.warning(f"使用方法ファイルが見つかりません: {md_path}")
                return DEFAULT_USAGE_TEXT
        except Exception as e:
            logger.error(f"使用方法ファイル読み込みエラー: {e}")
            return DEFAULT_USAGE_TEXT


def create_usage_tab(parent=None):
    """使用方法タブを作成"""
    try:
        return UsageTab(parent)
    except Exception as e:
        logger.error(f"使用方法タブ作成エラー: {e}")
        return None
