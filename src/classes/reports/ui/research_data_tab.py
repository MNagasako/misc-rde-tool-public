"""
報告書タブ - 研究データ生成タブ

設備別研究情報の生成機能を提供します。
"""

import os
import logging
from datetime import datetime

from classes.equipment.util.output_paths import get_equipment_root_dir
from classes.reports.util.output_paths import get_reports_root_dir

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


class ResearchDataTab(QWidget):
    """研究データ生成タブ
    
    設備別研究情報のJSON生成を行うタブUI
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 状態変数
        self.is_generating = False
        
        # ファイルパス
        self.excel_path = None
        self.merged_data_path = None
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
        title_label = QLabel("<h2>📄 研究データ生成（設備別研究情報JSON）</h2>")
        main_layout.addWidget(title_label)
        
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
        
        # 報告書Excelファイル（データ取得タブで生成）
        excel_layout = QHBoxLayout()
        excel_layout.addWidget(QLabel("報告書Excel:"))
        
        self.excel_path_edit = QLineEdit()
        self.excel_path_edit.setPlaceholderText("converted.xlsx（変換タブで生成）")
        self.excel_path_edit.setReadOnly(True)
        excel_layout.addWidget(self.excel_path_edit)
        
        self.excel_browse_button = QPushButton("📁 参照")
        self.excel_browse_button.clicked.connect(self.on_excel_browse_clicked)
        excel_layout.addWidget(self.excel_browse_button)
        
        layout.addLayout(excel_layout)
        
        # 設備データJSONファイル
        merged_layout = QHBoxLayout()
        merged_layout.addWidget(QLabel("設備データJSON:"))
        
        self.merged_path_edit = QLineEdit()
        self.merged_path_edit.setPlaceholderText("merged_data2.json（設備情報マージJSON）")
        self.merged_path_edit.setReadOnly(True)
        merged_layout.addWidget(self.merged_path_edit)
        
        self.merged_browse_button = QPushButton("📁 参照")
        self.merged_browse_button.clicked.connect(self.on_merged_browse_clicked)
        merged_layout.addWidget(self.merged_browse_button)
        
        layout.addLayout(merged_layout)
        
        # 出力ファイル
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("出力JSON:"))
        
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("research_data.json（自動生成）")
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
        
        # 生成開始ボタン
        self.generate_button = QPushButton("📄 生成開始")
        self.generate_button.setMinimumHeight(40)
        self.generate_button.setEnabled(False)
        self.generate_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        layout.addWidget(self.generate_button)
        
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
        self.generate_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
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
        self.generate_button.clicked.connect(self.on_generate_clicked)
        self.clear_log_button.clicked.connect(self.on_clear_log_clicked)
        self.open_folder_button.clicked.connect(self.on_open_folder_clicked)
    
    def load_default_files(self):
        """デフォルトファイルを読み込み"""
        self.refresh_from_disk()

    def refresh_from_disk(self):
        """ディスク上の最新ファイルを反映"""
        reports_dir = get_reports_root_dir()
        equipment_dir = get_equipment_root_dir()

        converted_path = reports_dir / "converted.xlsx"
        if converted_path.exists():
            converted_str = str(converted_path)
            if self.excel_path != converted_str:
                self.log_message("✅ 報告書Excel設定: converted.xlsx")
            self.excel_path = converted_str
            self.excel_path_edit.setText(converted_str)
        else:
            self.excel_path = None
            self.excel_path_edit.clear()

        merged_path = equipment_dir / "merged_data2.json"
        if merged_path.exists():
            merged_str = str(merged_path)
            if self.merged_data_path != merged_str:
                self.log_message("✅ 設備データJSON設定: merged_data2.json")
            self.merged_data_path = merged_str
            self.merged_path_edit.setText(merged_str)
        else:
            self.merged_data_path = None
            self.merged_path_edit.clear()

        output_path = reports_dir / "research_data.json"
        self.output_path = str(output_path)
        self.output_path_edit.setText(self.output_path)
        self.check_enable_generate()
    
    def on_excel_browse_clicked(self):
        """変換済みExcel参照ボタンクリック"""
        reports_dir = get_reports_root_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "変換済みExcelファイルを選択",
            str(reports_dir),
            "Excel Files (*.xlsx);;All Files (*)"
        )
        
        if file_path:
            self.excel_path = file_path
            self.excel_path_edit.setText(file_path)
            self.check_enable_generate()
            self.log_message(f"変換済みExcel設定: {file_path}")
    
    def on_merged_browse_clicked(self):
        """設備データJSON参照ボタンクリック"""
        facilities_dir = get_equipment_root_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "設備データJSONファイルを選択",
            str(facilities_dir),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.merged_data_path = file_path
            self.merged_path_edit.setText(file_path)
            self.check_enable_generate()
            self.log_message(f"設備データJSON設定: {file_path}")
    
    def on_output_browse_clicked(self):
        """出力JSON参照ボタンクリック"""
        reports_dir = get_reports_root_dir()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "出力JSONファイルを指定",
            str(reports_dir / "research_data.json"),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.output_path = file_path
            self.output_path_edit.setText(file_path)
            self.log_message(f"出力JSON設定: {file_path}")
    
    def on_auto_detect_clicked(self):
        """自動検出ボタンクリック"""
        reports_dir = get_reports_root_dir()
        equipment_dir = get_equipment_root_dir()

        excel_path = reports_dir / "converted.xlsx"
        if excel_path.exists():
            self.excel_path = str(excel_path)
            self.excel_path_edit.setText(self.excel_path)
            self.log_message(f"🔍 変換済みExcelを検出: {excel_path.name}")
        else:
            QMessageBox.warning(self, "エラー", f"converted.xlsx が見つかりません:\n{reports_dir}")
            return

        merged_path = equipment_dir / "merged_data2.json"
        if merged_path.exists():
            self.merged_data_path = str(merged_path)
            self.merged_path_edit.setText(self.merged_data_path)
            self.log_message(f"🔍 設備データJSONを検出: {merged_path.name}")
        else:
            QMessageBox.warning(self, "エラー", f"merged_data2.json が見つかりません:\n{equipment_dir}")
            return

        self.output_path = str(reports_dir / "research_data.json")
        self.output_path_edit.setText(self.output_path)
        self.check_enable_generate()
    
    def check_enable_generate(self):
        """生成ボタンの有効化チェック"""
        if self.excel_path and self.merged_data_path:
            # 出力パスが未設定の場合は自動設定
            if not self.output_path:
                reports_dir = get_reports_root_dir()
                self.output_path = str(reports_dir / "research_data.json")
                self.output_path_edit.setText(self.output_path)
            
            self.generate_button.setEnabled(True)
        else:
            self.generate_button.setEnabled(False)
    
    def on_generate_clicked(self):
        """生成開始ボタンクリック"""
        if self.is_generating:
            return
        
        if not self.excel_path or not os.path.exists(self.excel_path):
            QMessageBox.warning(self, "エラー", "変換済みExcelファイルを選択してください。")
            return
        
        if not self.merged_data_path or not os.path.exists(self.merged_data_path):
            QMessageBox.warning(self, "エラー", "設備データJSONファイルを選択してください。")
            return
        
        # 確認
        reply = QMessageBox.question(
            self,
            "確認",
            f"以下の設定で研究データを生成します:\n\n"
            f"変換済みExcel: {os.path.basename(self.excel_path)}\n"
            f"設備データJSON: {os.path.basename(self.merged_data_path)}\n"
            f"出力JSON: {os.path.basename(self.output_path)}\n\n"
            f"よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 生成開始
        self.start_generate()
    
    def start_generate(self):
        """生成開始"""
        self.log_message(f"=" * 60)
        self.log_message(f"研究データ生成開始")
        self.log_message(f"  変換済みExcel: {self.excel_path}")
        self.log_message(f"  設備データJSON: {self.merged_data_path}")
        self.log_message(f"  出力JSON: {self.output_path}")
        self.log_message(f"=" * 60)
        
        # 状態更新
        self.is_generating = True
        self.generate_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.reports.ui.research_data_worker import ResearchDataWorker
        
        self.worker_thread = ResearchDataWorker(
            excel_path=self.excel_path,
            merged_data_path=self.merged_data_path,
            output_path=self.output_path
        )
        
        self.worker_thread.progress_message.connect(self.log_message)
        self.worker_thread.completed.connect(self.on_generate_completed)
        
        self.worker_thread.start()
    
    def on_generate_completed(self, success: bool, message: str, summary: dict):
        """生成完了"""
        self.log_message(f"=" * 60)
        self.log_message(message)
        
        if success and summary:
            self.log_message(f"設備数: {summary.get('device_count', 0)}")
            self.log_message(f"研究数: {summary.get('research_count', 0)}")
            self.log_message("カテゴリ別研究数:")
            for device_id, count in summary.get('summary', {}).items():
                self.log_message(f"  {device_id}: {count}")
        
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_generating = False
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # 完了メッセージ
        if success:
            QMessageBox.information(self, "完了", f"研究データ生成が完了しました。\n\n{message}")
        else:
            QMessageBox.warning(self, "エラー", f"研究データ生成に失敗しました。\n\n{message}")
    
    def on_clear_log_clicked(self):
        """ログクリアボタンクリック"""
        self.log_textedit.clear()
    
    def on_open_folder_clicked(self):
        """フォルダを開くボタンクリック"""
        folder_path = get_reports_root_dir()
        if folder_path.exists():
            os.startfile(str(folder_path))
        else:
            QMessageBox.warning(self, "エラー", f"フォルダが存在しません:\n{folder_path}")
    
    def log_message(self, message: str):
        """ログメッセージ追加"""
        self.log_textedit.append(message)
        
        # 自動スクロール
        cursor = self.log_textedit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_textedit.setTextCursor(cursor)
