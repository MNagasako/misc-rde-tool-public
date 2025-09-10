"""
UI関連のダイアログクラス - ARIM RDE Tool v1.13.1
UIControllerから分離したダイアログクラス群
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QLabel, QShortcut, QApplication
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QKeySequence


class TextAreaExpandDialog:
    """テキストエリア拡大表示用のダイアログクラス"""
    
    def __init__(self, parent, title, content, editable=False, source_widget=None):
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setModal(True)
        self.dialog.resize(800, 600)
        self.source_widget = source_widget  # 元のテキストエリアへの参照を保持
        self.editable = editable
        
        # レイアウト設定
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # タイトルラベル
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1976d2; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # テキストエリア
        self.text_area = QTextEdit()
        
        # HTMLコンテンツかプレーンテキストかを判定して設定
        if content.strip().startswith('<') and content.strip().endswith('>'):
            self.text_area.setHtml(content)
        else:
            self.text_area.setPlainText(content)
        
        # フォント設定
        if "レスポンス" in title or "JSON" in title or "DEBUG" in title:
            font = QFont("Consolas", 10)
        else:
            font = QFont("Yu Gothic UI", 11)
        self.text_area.setFont(font)
        
        # 編集可能性設定
        self.text_area.setReadOnly(not editable)
        
        # スタイル設定
        self.text_area.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px;
                background-color: white;
                line-height: 1.4;
            }
        """)
        
        layout.addWidget(self.text_area)
        
        # ボタンレイアウト
        button_layout = QHBoxLayout()
        
        # 全選択ボタン（Ctrl+Aショートカット）
        select_all_btn = QPushButton("全選択 (Ctrl+A)")
        select_all_btn.setStyleSheet("background-color: #4caf50; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        select_all_btn.clicked.connect(self.text_area.selectAll)
        button_layout.addWidget(select_all_btn)
        
        # コピーボタン（Ctrl+Cショートカット）
        copy_btn = QPushButton("コピー (Ctrl+C)")
        copy_btn.setStyleSheet("background-color: #2196f3; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        copy_btn.clicked.connect(self._copy_text)
        button_layout.addWidget(copy_btn)
        
        button_layout.addStretch()
        
        # 閉じるボタン（Escapeキー）
        close_btn = QPushButton("閉じる (Esc)")
        close_btn.setStyleSheet("background-color: #757575; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        close_btn.clicked.connect(self._close_dialog)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.dialog.setLayout(layout)
        
        # キーボードショートカットを設定
        # Ctrl+A で全選択
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, self.dialog)
        select_all_shortcut.activated.connect(self.text_area.selectAll)
        
        # Ctrl+C でコピー
        copy_shortcut = QShortcut(QKeySequence.Copy, self.dialog)
        copy_shortcut.activated.connect(self._copy_text)
        
        # Escape で閉じる
        escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self.dialog)
        escape_shortcut.activated.connect(self._close_dialog)
        
        # ダイアログが閉じられるときのイベント処理
        self.dialog.closeEvent = self._on_close_event
    
    def _copy_text(self):
        """選択されたテキストまたは全テキストをクリップボードにコピー"""
        cursor = self.text_area.textCursor()
        
        if cursor.hasSelection():
            # 選択されたテキストをコピー
            selected_text = cursor.selectedText()
            QApplication.clipboard().setText(selected_text)
        else:
            # 全テキストをコピー（プレーンテキストとして）
            plain_text = self.text_area.toPlainText()
            QApplication.clipboard().setText(plain_text)
    
    def _close_dialog(self):
        """ダイアログを閉じる（編集内容を反映）"""
        self._apply_changes()
        self.dialog.close()
    
    def _on_close_event(self, event):
        """ダイアログのcloseEventをオーバーライド"""
        self._apply_changes()
        event.accept()
    
    def _apply_changes(self):
        """編集可能な場合、変更内容を元のウィジェットに反映"""
        if self.editable and self.source_widget is not None:
            try:
                # プレーンテキストとして取得して元のウィジェットに設定
                content = self.text_area.toPlainText()
                if hasattr(self.source_widget, 'setPlainText'):
                    self.source_widget.setPlainText(content)
                elif hasattr(self.source_widget, 'setText'):
                    self.source_widget.setText(content)
                print(f"[DEBUG] ポップアップの編集内容を元のウィジェットに反映しました")
            except Exception as e:
                print(f"[DEBUG] 編集内容の反映中にエラー: {e}")
    
    def show(self):
        """ダイアログを表示（ノンモーダル）"""
        self.dialog.show()
    
    def exec_(self):
        """ダイアログをモーダルで表示（PyQt5互換）"""
        return self.dialog.exec_()
    
    def exec(self):
        """ダイアログをモーダルで表示（PyQt6互換）"""
        try:
            return self.dialog.exec()
        except AttributeError:
            # PyQt5の場合は exec_() を使用
            return self.dialog.exec_()


class PopupDialog:
    """汎用ポップアップダイアログクラス"""
    
    def __init__(self, parent, title, content, editable=False):
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setModal(True)
        self.dialog.resize(900, 700)
        
        # レイアウト設定
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # タイトルラベル
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1976d2; margin-bottom: 15px;")
        layout.addWidget(title_label)
        
        # テキストエリア
        self.text_area = QTextEdit()
        self.text_area.setPlainText(content)
        
        # フォント設定（内容に応じて）
        if "リクエスト" in title or "レスポンス" in title or "JSON" in title or "ARIM" in title:
            font = QFont("Consolas", 11)
        else:
            font = QFont("Yu Gothic UI", 11)
        self.text_area.setFont(font)
        
        # 読み取り専用に設定
        self.text_area.setReadOnly(True)
        
        # スタイル設定
        self.text_area.setStyleSheet("""
            QTextEdit {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                background-color: #fafafa;
                line-height: 1.5;
                selection-background-color: #2196f3;
                selection-color: white;
            }
        """)
        
        layout.addWidget(self.text_area)
        
        # ボタンレイアウト
        button_layout = QHBoxLayout()
        
        # 全選択ボタン
        select_all_btn = QPushButton("全選択 (Ctrl+A)")
        select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #4caf50;
                color: white;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        select_all_btn.clicked.connect(self.text_area.selectAll)
        button_layout.addWidget(select_all_btn)
        
        # コピーボタン
        copy_btn = QPushButton("コピー (Ctrl+C)")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
        """)
        copy_btn.clicked.connect(self._copy_text)
        button_layout.addWidget(copy_btn)
        
        button_layout.addStretch()
        
        # 閉じるボタン
        close_btn = QPushButton("閉じる (Esc)")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        close_btn.clicked.connect(self.dialog.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.dialog.setLayout(layout)
        
        # キーボードショートカット設定
        # Ctrl+A で全選択
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, self.dialog)
        select_all_shortcut.activated.connect(self.text_area.selectAll)
        
        # Ctrl+C でコピー
        copy_shortcut = QShortcut(QKeySequence.Copy, self.dialog)
        copy_shortcut.activated.connect(self._copy_text)
        
        # Escape で閉じる
        escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self.dialog)
        escape_shortcut.activated.connect(self.dialog.close)
    
    def _copy_text(self):
        """選択されたテキストまたは全テキストをクリップボードにコピー"""
        cursor = self.text_area.textCursor()
        
        if cursor.hasSelection():
            # 選択されたテキストをコピー
            selected_text = cursor.selectedText()
            QApplication.clipboard().setText(selected_text)
        else:
            # 全テキストをコピー
            plain_text = self.text_area.toPlainText()
            QApplication.clipboard().setText(plain_text)
    
    def exec_(self):
        """ダイアログを表示"""
        return self.dialog.exec_()
