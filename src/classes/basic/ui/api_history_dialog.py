"""
API アクセス履歴表示・検査ダイアログ

基本情報取得などの複数ステップ処理で実行された
各APIアクセスの詳細を表示し、ペイロードやヘッダ、
レスポンス情報を検査・確認できるUIを提供します。
"""

import logging
from typing import Optional, List
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QTabWidget,
    QPushButton, QTextEdit, QLabel, QHeaderView,
    QMessageBox, QFileDialog, QScrollArea
)
from qt_compat.core import Qt, QSize
from net.api_call_recorder import APICallRecord, APICallRecorder, get_global_recorder
from pathlib import Path

logger = logging.getLogger(__name__)


class APICallDetailsDialog(QDialog):
    """APIコール詳細表示ダイアログ"""
    
    def __init__(self, record: APICallRecord, parent=None):
        """
        初期化
        
        Args:
            record: APICallRecord インスタンス
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.record = record
        self.setup_ui()
    
    def setup_ui(self):
        """UIをセットアップ"""
        self.setWindowTitle(f"API Call Details - {self.record.call_type}")
        self.setGeometry(100, 100, 900, 700)
        
        layout = QVBoxLayout()
        
        # タブウィジェット
        tabs = QTabWidget()
        
        # 1. リクエストタブ
        request_widget = self._create_request_tab()
        tabs.addTab(request_widget, "Request")
        
        # 2. レスポンスタブ
        response_widget = self._create_response_tab()
        tabs.addTab(response_widget, "Response")
        
        # 3. メタデータタブ
        metadata_widget = self._create_metadata_tab()
        tabs.addTab(metadata_widget, "Metadata")
        
        layout.addWidget(tabs)
        
        # ボタンレイアウト
        btn_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy Request as cURL")
        copy_btn.clicked.connect(self._copy_as_curl)
        btn_layout.addWidget(copy_btn)
        
        save_btn = QPushButton("Save as JSON")
        save_btn.clicked.connect(self._save_as_json)
        btn_layout.addWidget(save_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def _create_request_tab(self):
        """リクエストタブを作成"""
        widget = QTabWidget()
        
        # URLタブ
        url_text = QTextEdit()
        url_text.setPlainText(self.record.request.url)
        url_text.setReadOnly(True)
        widget.addTab(url_text, "URL")
        
        # メソッド + ヘッダ
        headers_text = QTextEdit()
        headers_text.setPlainText(self._format_headers())
        headers_text.setReadOnly(True)
        widget.addTab(headers_text, "Headers")
        
        # ボディ
        body_text = QTextEdit()
        if self.record.request.body:
            import json
            try:
                body_obj = json.loads(self.record.request.body)
                body_text.setPlainText(json.dumps(body_obj, ensure_ascii=False, indent=2))
            except:
                body_text.setPlainText(self.record.request.body)
        else:
            body_text.setPlainText("(No request body)")
        body_text.setReadOnly(True)
        widget.addTab(body_text, "Body")
        
        # クエリパラメータ
        query_text = QTextEdit()
        if self.record.request.query_params:
            import json
            query_text.setPlainText(json.dumps(self.record.request.query_params, ensure_ascii=False, indent=2))
        else:
            query_text.setPlainText("(No query parameters)")
        query_text.setReadOnly(True)
        widget.addTab(query_text, "Query Params")
        
        return widget
    
    def _create_response_tab(self):
        """レスポンスタブを作成"""
        widget = QTabWidget()
        
        # ステータス + メタデータ
        status_text = QTextEdit()
        status_text.setPlainText(self.record.response.get_summary())
        status_text.setReadOnly(True)
        widget.addTab(status_text, "Status & Info")
        
        # エラーメッセージ
        error_text = QTextEdit()
        error_text.setPlainText(
            self.record.response.error_message or "(No error)"
        )
        error_text.setReadOnly(True)
        widget.addTab(error_text, "Error Message")
        
        return widget
    
    def _create_metadata_tab(self):
        """メタデータタブを作成"""
        text = QTextEdit()
        
        metadata = f"""Call Type: {self.record.call_type}
Step Index: {self.record.step_index}
Step Name: {self.record.step_name}
Timestamp: {self.record.timestamp}
Notes: {self.record.notes or '(None)'}

Request Summary:
{self.record.request.get_summary()}

Response Summary:
{self.record.response.get_summary()}
"""
        
        text.setPlainText(metadata)
        text.setReadOnly(True)
        
        return text
    
    def _format_headers(self) -> str:
        """ヘッダを整形して返す"""
        lines = [f"Method: {self.record.request.method}"]
        lines.append("")
        
        for key, value in self.record.request.headers.items():
            # Authorizationトークンはマスク
            if key == 'Authorization':
                value = value[:20] + "..." if len(value) > 20 else value
            lines.append(f"{key}: {value}")
        
        return "\n".join(lines)
    
    def _copy_as_curl(self):
        """cURLコマンドとしてクリップボードにコピー"""
        import subprocess
        
        curl_cmd = f"curl -X {self.record.request.method}"
        curl_cmd += f" '{self.record.request.url}'"
        
        for key, value in self.record.request.headers.items():
            # Authorizationはマスク
            if key == 'Authorization':
                value = value[:20] + "..."
            curl_cmd += f" -H '{key}: {value}'"
        
        if self.record.request.body:
            curl_cmd += f" -d '{self.record.request.body}'"
        
        # クリップボードにコピー
        try:
            import pyperclip
            pyperclip.copy(curl_cmd)
            QMessageBox.information(self, "Success", "cURL command copied to clipboard")
        except ImportError:
            # pyperclipなしの場合
            text = QTextEdit()
            text.setPlainText(curl_cmd)
            text.setReadOnly(True)
            
            dialog = QDialog(self)
            dialog.setWindowTitle("cURL Command")
            layout = QVBoxLayout()
            layout.addWidget(text)
            dialog.setLayout(layout)
            dialog.exec()
    
    def _save_as_json(self):
        """JSONファイルとして保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save API Call Record",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            import json
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.record.to_dict(), f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "Success", f"Saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save: {e}")


class APIAccessHistoryDialog(QDialog):
    """API アクセス履歴ダイアログ"""
    
    def __init__(self, recorder: Optional[APICallRecorder] = None, parent=None):
        """
        初期化
        
        Args:
            recorder: APICallRecorder インスタンス（未指定時はグローバルを使用）
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.recorder = recorder or get_global_recorder()
        self.setup_ui()
    
    def setup_ui(self):
        """UIをセットアップ"""
        self.setWindowTitle("API Access History")
        self.setGeometry(50, 50, 1200, 700)
        
        layout = QVBoxLayout()
        
        # タイトル
        title_label = QLabel(f"API Call History - Session: {self.recorder.session_id}")
        layout.addWidget(title_label)
        
        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "#", "Type", "Method", "Status", "Time (ms)", "URL", "Result"
        ])
        
        # テーブルにデータを追加
        self._populate_table()
        
        # テーブルのカラム幅を調整
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # #
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Method
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Time
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # URL
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Result
        
        layout.addWidget(self.table)
        
        # サマリーテキスト
        summary_text = QTextEdit()
        summary_text.setPlainText(self.recorder.get_summary())
        summary_text.setReadOnly(True)
        summary_text.setMaximumHeight(200)
        layout.addWidget(summary_text)
        
        # ボタンレイアウト
        btn_layout = QHBoxLayout()
        
        export_btn = QPushButton("Export as JSON")
        export_btn.clicked.connect(self._export_json)
        btn_layout.addWidget(export_btn)
        
        export_html_btn = QPushButton("Export as HTML")
        export_html_btn.clicked.connect(self._export_html)
        btn_layout.addWidget(export_html_btn)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_table)
        btn_layout.addWidget(refresh_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        # テーブル行をダブルクリックで詳細表示
        self.table.doubleClicked.connect(self._on_row_double_clicked)
    
    def _populate_table(self):
        """テーブルにデータを追加"""
        records = self.recorder.get_records()
        self.table.setRowCount(len(records))
        
        for row, record in enumerate(records):
            # #
            item = QTableWidgetItem(str(record.step_index + 1))
            self.table.setItem(row, 0, item)
            
            # Type
            item = QTableWidgetItem(record.call_type)
            self.table.setItem(row, 1, item)
            
            # Method
            item = QTableWidgetItem(record.request.method)
            self.table.setItem(row, 2, item)
            
            # Status
            status_text = f"{record.response.status_code}"
            item = QTableWidgetItem(status_text)
            self.table.setItem(row, 3, item)
            
            # Time (ms)
            item = QTableWidgetItem(f"{record.response.elapsed_ms:.1f}")
            self.table.setItem(row, 4, item)
            
            # URL (切り詰め)
            url_display = record.request.url[:80] + "..." if len(record.request.url) > 80 else record.request.url
            item = QTableWidgetItem(url_display)
            self.table.setItem(row, 5, item)
            
            # Result
            result_icon = "✅" if record.response.success else "❌"
            item = QTableWidgetItem(result_icon)
            self.table.setItem(row, 6, item)
    
    def _on_row_double_clicked(self, index):
        """テーブル行がダブルクリックされたときの処理"""
        row = index.row()
        records = self.recorder.get_records()
        
        if 0 <= row < len(records):
            record = records[row]
            details_dialog = APICallDetailsDialog(record, self)
            details_dialog.exec()
    
    def _refresh_table(self):
        """テーブルを更新"""
        self.table.setRowCount(0)
        self._populate_table()
    
    def _export_json(self):
        """JSONファイルとしてエクスポート"""
        output_path = self.recorder.save_to_file()
        QMessageBox.information(self, "Success", f"API Call history exported to:\n{output_path}")
    
    def _export_html(self):
        """HTMLレポートとしてエクスポート"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export as HTML",
            f"api_calls_{self.recorder.session_id}.html",
            "HTML Files (*.html);;All Files (*)"
        )
        
        if file_path:
            try:
                html_content = self.recorder.get_html_report()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                QMessageBox.information(self, "Success", f"HTML report saved to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")


def show_api_history_dialog(parent=None):
    """APIアクセス履歴ダイアログを表示（便利関数）"""
    dialog = APIAccessHistoryDialog(parent=parent)
    dialog.exec()
