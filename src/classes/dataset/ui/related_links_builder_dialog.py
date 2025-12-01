"""
関連情報ビルダーダイアログ - RelatedLinksBuilderDialog
タイトルとURLのペアを管理するダイアログ
"""
import logging

# MagicMock汚染回避のため、PySide6から直接インポート
try:
    from qt_compat.widgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
    )
    from qt_compat.core import Qt, Signal
    from unittest.mock import MagicMock
    # qt_compatがMagicMockを返している場合はPySide6実体へフォールバック
    if isinstance(QDialog, MagicMock):
        raise ImportError("qt_compat contaminated by MagicMock")
except Exception:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
    )
    from PySide6.QtCore import Qt, Signal

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)


class RelatedLinksBuilderDialog(QDialog):
    """関連情報ビルダーダイアログ
    
    タイトルとURLのペアをテーブルで管理し、追加・削除機能を提供する。
    
    Signals:
        links_changed: 関連情報が変更された時に発火 (str: "title1:url1,title2:url2" 形式)
    """
    
    links_changed = Signal(str)
    
    def __init__(self, parent=None, current_links=""):
        """
        Args:
            parent: 親ウィジェット
            current_links: 現在の関連情報 ("title1:url1,title2:url2" 形式)
        """
        super().__init__(parent)
        self.setWindowTitle("関連情報ビルダー")
        self.setMinimumWidth(700)
        self.setMinimumHeight(400)
        
        # ダイアログレイアウト
        layout = QVBoxLayout()
        
        # 説明ラベル
        desc_label = QLabel("関連情報（タイトルとURLのペア）を管理します")
        desc_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)}; margin-bottom: 8px;")
        layout.addWidget(desc_label)
        
        # テーブル作成
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["タイトル", "URL", "操作"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        # 追加エリア
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("タイトル:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例: 関連論文")
        add_layout.addWidget(self.title_edit)
        
        add_layout.addWidget(QLabel("URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("例: https://example.com/paper")
        add_layout.addWidget(self.url_edit)
        
        add_button = QPushButton("追加")
        add_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
        """)
        add_button.clicked.connect(self.add_link)
        add_layout.addWidget(add_button)
        
        layout.addLayout(add_layout)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.setMinimumWidth(100)
        ok_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.setMinimumWidth(100)
        cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 現在のリンクを読み込み
        self._load_links(current_links)
        
        # Enterキーで追加
        self.title_edit.returnPressed.connect(self.add_link)
        self.url_edit.returnPressed.connect(self.add_link)
    
    def _load_links(self, links_text):
        """関連情報テキストからテーブルにデータを読み込む
        
        Args:
            links_text: "title1:url1,title2:url2" 形式の文字列
        """
        if not links_text or not links_text.strip():
            return
        
        items = links_text.split(',')
        for item in items:
            item = item.strip()
            if not item or ':' not in item:
                continue
            
            parts = item.split(':', 1)
            if len(parts) == 2:
                title = parts[0].strip()
                url = parts[1].strip()
                if title and url:
                    self._add_row(title, url)
    
    def _add_row(self, title, url):
        """テーブルに新しい行を追加
        
        Args:
            title: タイトル
            url: URL
        """
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        title_item = QTableWidgetItem(title)
        url_item = QTableWidgetItem(url)
        
        self.table.setItem(row, 0, title_item)
        self.table.setItem(row, 1, url_item)
        
        # 削除ボタン
        delete_button = QPushButton("削除")
        delete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
        """)
        delete_button.clicked.connect(lambda checked=False, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 2, delete_button)
        
        logger.debug("関連情報行を追加: title='%s', url='%s'", title, url)
    
    def _delete_row(self, row):
        """指定された行を削除
        
        Args:
            row: 削除する行番号
        """
        # 削除ボタンから実際の行を特定
        for i in range(self.table.rowCount()):
            widget = self.table.cellWidget(i, 2)
            if widget and widget.sender() == widget:
                self.table.removeRow(i)
                logger.debug("関連情報行を削除: row=%s", i)
                return
    
    def add_link(self):
        """テーブルに新しいリンクを追加"""
        title = self.title_edit.text().strip()
        url = self.url_edit.text().strip()
        
        if not title:
            QMessageBox.warning(self, "入力エラー", "タイトルを入力してください。")
            return
        
        if not url:
            QMessageBox.warning(self, "入力エラー", "URLを入力してください。")
            return
        
        # 簡易URL検証
        if not (url.startswith("http://") or url.startswith("https://")):
            result = QMessageBox.question(
                self, "確認",
                "URLが http:// または https:// で始まっていません。\nこのまま追加しますか?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result != QMessageBox.Yes:
                return
        
        self._add_row(title, url)
        
        # 入力欄をクリア
        self.title_edit.clear()
        self.url_edit.clear()
        self.title_edit.setFocus()
    
    def get_links_text(self):
        """テーブルの内容を "title1:url1,title2:url2" 形式で取得
        
        Returns:
            str: カンマ区切りの関連情報テキスト
        """
        links = []
        for row in range(self.table.rowCount()):
            title_item = self.table.item(row, 0)
            url_item = self.table.item(row, 1)
            
            if title_item and url_item:
                title = title_item.text().strip()
                url = url_item.text().strip()
                if title and url:
                    links.append(f"{title}:{url}")
        
        return ",".join(links)
    
    def accept(self):
        """OKボタンが押された時の処理"""
        links_text = self.get_links_text()
        logger.info("関連情報ビルダー完了: %s", links_text)
        self.links_changed.emit(links_text)
        super().accept()
