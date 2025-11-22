"""
報告書タブ - Excel変換タブ

ARIM-extracted2フォーマットから標準フォーマットへの変換機能を提供します。
"""

import os
import logging
from typing import Optional
from datetime import datetime
from config.common import OUTPUT_DIR

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
        QPushButton, QLineEdit, QTextEdit, QProgressBar,
        QGroupBox, QFileDialog, QMessageBox
    )
    from qt_compat.gui import QTextCursor
    from qt_compat.core import Signal, QThread
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")

from classes.theme import get_color, ThemeKey


class ReportConvertTab(QWidget):
    """Excel変換タブ
    
    報告書データのExcel変換を行うタブUI
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 状態変数
        self.is_converting = False
        
        # ファイルパス
        self.input_path = None
        self.output_path = None
        
        self.setup_ui()
        self.connect_signals()
        
        # デフォルト値を設定
        self.load_default_files()
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("<h2>🔄 Excel変換</h2>")
        main_layout.addWidget(title_label)
        
        # 説明
        desc_label = QLabel(
            "ARIM-extracted2フォーマットのExcelファイルを標準フォーマット（converted.xlsx）に変換します。<br>"
            "データ取得タブで出力されたファイルを選択し、変換を実行してください。"
        )
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # ファイル選択グループ
        file_group = self.create_file_selection_group()
        main_layout.addWidget(file_group)
        
        # 実行ボタンエリア
        button_layout = self.create_button_area()
        main_layout.addLayout(button_layout)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # ログ表示エリア
        log_group = self.create_log_area()
        main_layout.addWidget(log_group)
        
        # ストレッチ追加
        main_layout.addStretch()
    
    def create_file_selection_group(self) -> QGroupBox:
        """ファイル選択グループ作成"""
        group = QGroupBox("ファイル選択")
        layout = QVBoxLayout(group)
        
        # 入力ファイル
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("入力Excel:"))
        
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("ARIM-extracted2フォーマットのExcelファイル")
        self.input_path_edit.setReadOnly(True)
        input_layout.addWidget(self.input_path_edit)
        
        self.input_browse_button = QPushButton("📁 参照")
        self.input_browse_button.clicked.connect(self.on_input_browse_clicked)
        input_layout.addWidget(self.input_browse_button)
        
        layout.addLayout(input_layout)
        
        # 出力ファイル
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("出力Excel:"))
        
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("変換後のExcelファイル（自動生成: converted.xlsx）")
        self.output_path_edit.setReadOnly(True)
        output_layout.addWidget(self.output_path_edit)
        
        self.output_browse_button = QPushButton("📁 参照")
        self.output_browse_button.clicked.connect(self.on_output_browse_clicked)
        output_layout.addWidget(self.output_browse_button)
        
        layout.addLayout(output_layout)
        
        # 自動検出ボタン
        auto_layout = QHBoxLayout()
        self.auto_detect_button = QPushButton("🔍 最新ファイルを自動検出")
        self.auto_detect_button.clicked.connect(self.on_auto_detect_clicked)
        auto_layout.addWidget(self.auto_detect_button)
        auto_layout.addStretch()
        layout.addLayout(auto_layout)
        
        return group
    
    def create_button_area(self) -> QHBoxLayout:
        """ボタンエリア作成"""
        layout = QHBoxLayout()
        
        # 変換開始ボタン
        self.convert_button = QPushButton("🔄 変換開始")
        self.convert_button.setMinimumHeight(40)
        self.convert_button.setEnabled(False)
        self.convert_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        layout.addWidget(self.convert_button)
        
        # ログクリアボタン
        self.clear_log_button = QPushButton("🗑️ ログクリア")
        self.clear_log_button.setMinimumHeight(40)
        layout.addWidget(self.clear_log_button)
        
        # フォルダを開くボタン
        self.open_folder_button = QPushButton("📁 出力フォルダを開く")
        self.open_folder_button.setMinimumHeight(40)
        layout.addWidget(self.open_folder_button)
        
        return layout
    
    def _apply_button_styles(self):
        """ボタンスタイルを適用"""
        self.convert_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        self._apply_button_styles()
        self.update()
    
    def create_log_area(self) -> QGroupBox:
        """ログ表示エリア作成"""
        group = QGroupBox("ログ")
        layout = QVBoxLayout(group)
        
        self.log_textedit = QTextEdit()
        self.log_textedit.setReadOnly(True)
        self.log_textedit.setMinimumHeight(300)
        layout.addWidget(self.log_textedit)
        
        return group
    
    def connect_signals(self):
        """シグナル接続"""
        self.convert_button.clicked.connect(self.on_convert_clicked)
        self.clear_log_button.clicked.connect(self.on_clear_log_clicked)
        self.open_folder_button.clicked.connect(self.on_open_folder_clicked)
    
    def load_default_files(self):
        """デフォルトファイルを読み込み"""
        reports_dir = os.path.join(OUTPUT_DIR, "arim-site", "reports")
        
        if not os.path.exists(reports_dir):
            return
        
        # Excelファイルを検索（ARIM-extracted2*.xlsxを検索）
        excel_files = []
        for file in os.listdir(reports_dir):
            if file.startswith('ARIM-extracted2') and file.endswith('.xlsx') and not file.startswith('~'):
                excel_files.append(os.path.join(reports_dir, file))
        
        if excel_files:
            # 最新のファイルを取得
            latest_file = max(excel_files, key=os.path.getmtime)
            self.input_path = latest_file
            self.input_path_edit.setText(latest_file)
            
            # 出力ファイルを自動設定
            self.output_path = os.path.join(reports_dir, "converted.xlsx")
            self.output_path_edit.setText(self.output_path)
            
            # 変換ボタン有効化
            self.convert_button.setEnabled(True)
            
            self.log_message(f"✅ デフォルトファイル設定: {os.path.basename(latest_file)}")
    
    def on_input_browse_clicked(self):
        """入力ファイル参照ボタンクリック"""
        reports_dir = os.path.join(OUTPUT_DIR, "arim-site", "reports")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "入力Excelファイルを選択",
            reports_dir,
            "Excel Files (*.xlsx);;All Files (*)"
        )
        
        if file_path:
            self.input_path = file_path
            self.input_path_edit.setText(file_path)
            
            # 出力ファイルを自動設定
            if not self.output_path:
                output_dir = os.path.dirname(file_path)
                self.output_path = os.path.join(output_dir, "converted.xlsx")
                self.output_path_edit.setText(self.output_path)
            
            # 変換ボタン有効化
            self.convert_button.setEnabled(True)
            self.log_message(f"入力ファイル設定: {file_path}")
    
    def on_output_browse_clicked(self):
        """出力ファイル参照ボタンクリック"""
        reports_dir = os.path.join(OUTPUT_DIR, "arim-site", "reports")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "出力Excelファイルを指定",
            os.path.join(reports_dir, "converted.xlsx"),
            "Excel Files (*.xlsx);;All Files (*)"
        )
        
        if file_path:
            self.output_path = file_path
            self.output_path_edit.setText(file_path)
            self.log_message(f"出力ファイル設定: {file_path}")
    
    def on_auto_detect_clicked(self):
        """自動検出ボタンクリック"""
        reports_dir = os.path.join(OUTPUT_DIR, "arim-site", "reports")
        
        if not os.path.exists(reports_dir):
            QMessageBox.warning(self, "エラー", f"報告書フォルダが見つかりません:\n{reports_dir}")
            return
        
        # Excelファイルを検索（ARIM-extracted2*.xlsx）
        excel_files = []
        for file in os.listdir(reports_dir):
            if file.startswith('ARIM-extracted2') and file.endswith('.xlsx') and not file.startswith('~'):
                excel_files.append(os.path.join(reports_dir, file))
        
        if not excel_files:
            QMessageBox.information(self, "結果", "Excelファイルが見つかりませんでした。")
            return
        
        # 最新のファイルを取得
        latest_file = max(excel_files, key=os.path.getmtime)
        self.input_path = latest_file
        self.input_path_edit.setText(latest_file)
        
        # 出力ファイルを自動設定
        self.output_path = os.path.join(reports_dir, "converted.xlsx")
        self.output_path_edit.setText(self.output_path)
        
        # 変換ボタン有効化
        self.convert_button.setEnabled(True)
        
        self.log_message(f"🔍 最新ファイルを検出: {os.path.basename(latest_file)}")
        self.log_message(f"  更新日時: {datetime.fromtimestamp(os.path.getmtime(latest_file)).strftime('%Y-%m-%d %H:%M:%S')}")
    
    def on_convert_clicked(self):
        """変換開始ボタンクリック"""
        if self.is_converting:
            return
        
        if not self.input_path or not os.path.exists(self.input_path):
            QMessageBox.warning(self, "エラー", "入力ファイルを選択してください。")
            return
        
        # 確認
        reply = QMessageBox.question(
            self,
            "確認",
            f"以下の設定で変換を実行します:\n\n"
            f"入力: {os.path.basename(self.input_path)}\n"
            f"出力: {os.path.basename(self.output_path)}\n\n"
            f"よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 変換開始
        self.start_convert()
    
    def start_convert(self):
        """変換開始"""
        self.log_message(f"=" * 60)
        self.log_message(f"Excel変換開始")
        self.log_message(f"  入力: {self.input_path}")
        self.log_message(f"  出力: {self.output_path}")
        self.log_message(f"=" * 60)
        
        # 状態更新
        self.is_converting = True
        self.convert_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.reports.ui.convert_worker import ReportConvertWorker
        
        self.worker_thread = ReportConvertWorker(
            input_path=self.input_path,
            output_path=self.output_path
        )
        
        self.worker_thread.progress_message.connect(self.log_message)
        self.worker_thread.completed.connect(self.on_convert_completed)
        
        self.worker_thread.start()
    
    def on_convert_completed(self, success: bool, message: str):
        """変換完了"""
        self.log_message(f"=" * 60)
        self.log_message(message)
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_converting = False
        self.convert_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # 完了メッセージ
        if success:
            QMessageBox.information(self, "完了", f"Excel変換が完了しました。\n\n{message}")
        else:
            QMessageBox.warning(self, "エラー", f"Excel変換に失敗しました。\n\n{message}")
    
    def on_clear_log_clicked(self):
        """ログクリアボタンクリック"""
        self.log_textedit.clear()
    
    def on_open_folder_clicked(self):
        """フォルダを開くボタンクリック"""
        folder_path = os.path.join(OUTPUT_DIR, "arim-site", "reports")
        if os.path.exists(folder_path):
            os.startfile(folder_path)
        else:
            QMessageBox.warning(self, "エラー", f"フォルダが存在しません:\n{folder_path}")
    
    def log_message(self, message: str):
        """ログメッセージ追加"""
        self.log_textedit.append(message)
        
        # 自動スクロール
        cursor = self.log_textedit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_textedit.setTextCursor(cursor)
