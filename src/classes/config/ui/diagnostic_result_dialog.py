"""
診断結果表示ダイアログ - ARIM RDE Tool v2.4.18

プロキシ・SSL診断の結果を見やすく表示

機能:
- 診断サマリー表示
- 個別テスト結果の詳細表示
- レポートファイルの保存
- 詳細ログの表示
"""

import logging
from typing import Dict, Any, List, TYPE_CHECKING
from pathlib import Path

try:
    from qt_compat.widgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
        QPushButton, QTextEdit, QGroupBox, QTableWidget,
        QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox
    )
    from qt_compat.core import Qt
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス
    class QDialog: pass
    class QWidget: pass
    class QGroupBox: pass
    class QHBoxLayout: pass

logger = logging.getLogger(__name__)

from classes.theme import get_color, get_qcolor, ThemeKey


class DiagnosticResultDialog(QDialog):
    """診断結果表示ダイアログ"""
    
    def __init__(self, results: Dict[str, Any], parent=None):
        """
        Args:
            results: 診断結果辞書
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.results = results
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        self.setWindowTitle("プロキシ・SSL診断結果")
        self.setModal(True)
        self.resize(900, 700)
        
        layout = QVBoxLayout(self)
        
        # サマリーセクション
        summary_group = self._create_summary_section()
        layout.addWidget(summary_group)
        
        # テスト詳細セクション
        if self.results.get('tests'):
            details_group = self._create_details_section()
            layout.addWidget(details_group)
        
        # 標準出力セクション（フォールバック時）
        if self.results.get('stdout'):
            stdout_group = self._create_stdout_section()
            layout.addWidget(stdout_group)
        
        # ボタンエリア
        button_layout = self._create_button_layout()
        layout.addLayout(button_layout)
        
    def _create_summary_section(self):
        """サマリーセクション作成"""
        group = QGroupBox("診断結果サマリー")
        layout = QVBoxLayout(group)
        
        # 成功/失敗判定
        if self.results.get('success'):
            total = self.results.get('total_tests', 0)
            passed = self.results.get('passed', 0)
            failed = self.results.get('failed', 0)
            duration = self.results.get('duration', 0)
            
            # 合格率計算
            pass_rate = (passed / total * 100) if total > 0 else 0
            
            # ステータスラベル
            if failed == 0:
                status_text = f"✅ 全テスト合格: {passed}/{total} (100.0%)"
                status_color = get_color(ThemeKey.TEXT_SUCCESS)
            else:
                status_text = f"⚠️ 一部失敗: {passed}/{total} ({pass_rate:.1f}%)"
                status_color = get_color(ThemeKey.TEXT_WARNING)
            
            status_label = QLabel(status_text)
            status_font = QFont()
            status_font.setPointSize(14)
            status_font.setBold(True)
            status_label.setFont(status_font)
            status_label.setStyleSheet(f"color: {status_color};")
            layout.addWidget(status_label)
            
            # 詳細情報
            info_text = f"所要時間: {duration:.1f}秒\n"
            if self.results.get('timestamp'):
                info_text += f"実行日時: {self.results['timestamp']}\n"
            if self.results.get('report_file'):
                info_text += f"レポート: {self.results['report_file']}"
            
            info_label = QLabel(info_text)
            layout.addWidget(info_label)
            
        else:
            # エラー表示
            error_text = f"❌ 診断失敗: {self.results.get('error', '不明なエラー')}"
            error_label = QLabel(error_text)
            error_font = QFont()
            error_font.setPointSize(12)
            error_font.setBold(True)
            error_label.setFont(error_font)
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)};")
            layout.addWidget(error_label)
        
        return group
        
    def _create_details_section(self):
        """テスト詳細セクション作成"""
        group = QGroupBox("個別テスト結果")
        layout = QVBoxLayout(group)
        
        # テーブル作成
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["テスト名", "ステータス", "所要時間", "メッセージ"])
        
        # ヘッダー設定
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        
        # データ挿入
        tests = self.results.get('tests', [])
        total_duration = self.results.get('duration', 0)
        test_count = len(tests) if tests else 1
        
        table.setRowCount(len(tests))
        
        for row, test in enumerate(tests):
            # テスト名
            name_item = QTableWidgetItem(test.get('name', '不明'))
            table.setItem(row, 0, name_item)
            
            # ステータス
            status = test.get('status', 'unknown')
            if status == 'passed':
                status_text = "✅ 合格"
                status_color = get_qcolor(ThemeKey.TEXT_SUCCESS)
            elif status == 'failed':
                status_text = "❌ 失敗"
                status_color = get_qcolor(ThemeKey.TEXT_ERROR)
            else:
                status_text = "❓ 不明"
                status_color = get_qcolor(ThemeKey.TEXT_MUTED)
            
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(status_color)
            table.setItem(row, 1, status_item)
            
            # 所要時間（個別テストの時間がない場合は全体を均等配分）
            duration = test.get('duration', 0)
            if duration == 0 and total_duration > 0:
                # 全体時間を均等配分（概算）
                duration = total_duration / test_count
            duration_item = QTableWidgetItem(f"{duration:.2f}秒")
            table.setItem(row, 2, duration_item)
            
            # メッセージ
            message = test.get('message', '') or test.get('error', '')
            message_item = QTableWidgetItem(message[:100])
            table.setItem(row, 3, message_item)
        
        layout.addWidget(table)
        return group
        
    def _create_stdout_section(self):
        """標準出力セクション作成（フォールバック）"""
        group = QGroupBox("診断ログ詳細")
        layout = QVBoxLayout(group)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(self.results.get('stdout', ''))
        text_edit.setMaximumHeight(200)
        
        layout.addWidget(text_edit)
        return group
        
    def _create_button_layout(self):
        """ボタンエリア作成"""
        layout = QHBoxLayout()
        layout.addStretch()
        
        # レポート保存ボタン
        if self.results.get('report_file'):
            save_button = QPushButton("レポートをコピー")
            save_button.clicked.connect(self._save_report)
            layout.addWidget(save_button)
        
        # 詳細ログ表示ボタン
        if self.results.get('tests'):
            log_button = QPushButton("詳細ログを表示")
            log_button.clicked.connect(self._show_detailed_log)
            layout.addWidget(log_button)
        
        # 閉じるボタン
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        
        return layout
        
    def _save_report(self):
        """レポートファイルを別名保存"""
        try:
            source_file = self.results.get('report_file')
            if not source_file or not Path(source_file).exists():
                QMessageBox.warning(self, "エラー", "レポートファイルが見つかりません")
                return
            
            # 保存先選択
            dest_file, _ = QFileDialog.getSaveFileName(
                self,
                "診断レポートを保存",
                f"diagnostic_report_{self.results.get('timestamp', '')}.json",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not dest_file:
                return
            
            # ファイルコピー
            import shutil
            shutil.copy2(source_file, dest_file)
            
            QMessageBox.information(self, "成功", f"レポートを保存しました:\n{dest_file}")
            
        except Exception as e:
            logger.exception("レポート保存エラー")
            QMessageBox.critical(self, "エラー", f"レポート保存に失敗しました:\n{e}")
            
    def _show_detailed_log(self):
        """詳細ログを別ウィンドウで表示"""
        try:
            # 詳細ログダイアログ
            log_dialog = QDialog(self)
            log_dialog.setWindowTitle("詳細ログ")
            log_dialog.resize(800, 600)
            
            layout = QVBoxLayout(log_dialog)
            
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            
            # 全テストの詳細を整形
            log_text = self._format_detailed_log()
            text_edit.setPlainText(log_text)
            
            layout.addWidget(text_edit)
            
            # 閉じるボタン
            close_button = QPushButton("閉じる")
            close_button.clicked.connect(log_dialog.accept)
            layout.addWidget(close_button)
            
            log_dialog.exec_()
            
        except Exception as e:
            logger.exception("詳細ログ表示エラー")
            QMessageBox.critical(self, "エラー", f"ログ表示に失敗しました:\n{e}")
            
    def _format_detailed_log(self) -> str:
        """詳細ログを整形"""
        lines = []
        lines.append("=" * 80)
        lines.append("プロキシ・SSL診断 詳細ログ")
        lines.append("=" * 80)
        lines.append("")
        
        for test in self.results.get('tests', []):
            lines.append(f"【{test.get('name', '不明')}】")
            lines.append(f"  ステータス: {test.get('status', 'unknown')}")
            lines.append(f"  所要時間: {test.get('duration', 0):.2f}秒")
            
            if test.get('message'):
                lines.append(f"  メッセージ: {test['message']}")
            
            if test.get('error'):
                lines.append(f"  エラー: {test['error']}")
            
            if test.get('details'):
                lines.append(f"  詳細:")
                for key, value in test['details'].items():
                    lines.append(f"    {key}: {value}")
            
            lines.append("")
        
        return "\n".join(lines)
