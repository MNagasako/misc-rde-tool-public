"""
設備タブ - データマージタブ

ExcelとJSONデータをマージする機能を提供するタブUIです。
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from classes.equipment.util.output_paths import (
    find_latest_child_directory,
    get_equipment_backups_root,
    get_equipment_root_dir,
)
from classes.utils.button_styles import get_button_style

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
        QPushButton, QLineEdit, QTextEdit, QProgressBar,
        QGroupBox, QCheckBox, QMessageBox
    )
    from qt_compat.gui import QTextCursor
    from qt_compat.core import Signal, QThread
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class MergeTab(QWidget):
    """データマージタブ
    
    Excel設備情報とJSON測定方法をマージするタブUI
    """
    
    # シグナル定義
    merge_started = Signal()
    merge_progress = Signal(str)
    merge_completed = Signal(bool, str)  # success, message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 状態変数
        self.is_merging = False
        
        # ファイルパス保存用
        self.latest_json_path = None
        self.latest_backup_dir = None
        
        self.setup_ui()
        self.connect_signals()
        self._connect_theme_signal()
        self.refresh_theme()

    def _connect_theme_signal(self) -> None:
        try:
            from classes.theme.theme_manager import ThemeManager

            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass

    def refresh_theme(self, *_args, **_kwargs) -> None:
        try:
            if hasattr(self, "merge_button"):
                self.merge_button.setStyleSheet(get_button_style("warning"))
        except Exception:
            pass
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("<h2>データマージ（Excel + JSON）</h2>")
        main_layout.addWidget(title_label)
        
        # 説明
        desc_label = QLabel(
            "Excel設備情報とJSON測定方法データをマージします。\n"
            "結果はmerged_data2.json形式で出力されます。"
        )
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # 設定グループ
        settings_group = self.create_settings_group()
        main_layout.addWidget(settings_group)
        
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
        
        # ファイル情報表示エリア
        file_info_group = self.create_file_info_area()
        main_layout.addWidget(file_info_group)
        
        # ストレッチ追加
        main_layout.addStretch()
    
    def create_settings_group(self) -> QGroupBox:
        """設定グループ作成"""
        group = QGroupBox("マージ設定")
        layout = QVBoxLayout(group)
        
        # Excelファイル名設定
        excel_layout = QHBoxLayout()
        excel_layout.addWidget(QLabel("Excelファイル名:"))
        
        self.excel_filename_lineedit = QLineEdit()
        self.excel_filename_lineedit.setText("facilities_full.xlsx")
        self.excel_filename_lineedit.setPlaceholderText("例: facilities_full.xlsx")
        self.excel_filename_lineedit.setToolTip("設備情報が含まれるExcelファイル")
        excel_layout.addWidget(self.excel_filename_lineedit)
        
        layout.addLayout(excel_layout)
        
        # JSONファイル名設定
        json_layout = QHBoxLayout()
        json_layout.addWidget(QLabel("JSONファイル名:"))
        
        self.json_filename_lineedit = QLineEdit()
        self.json_filename_lineedit.setText("fasi_ext.json")
        self.json_filename_lineedit.setPlaceholderText("例: fasi_ext.json")
        self.json_filename_lineedit.setToolTip("測定方法データが含まれるJSONファイル")
        json_layout.addWidget(self.json_filename_lineedit)
        
        layout.addLayout(json_layout)
        
        # 出力ファイル名設定
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("出力ファイル名:"))
        
        self.output_filename_lineedit = QLineEdit()
        self.output_filename_lineedit.setText("merged_data2.json")
        self.output_filename_lineedit.setPlaceholderText("例: merged_data2.json")
        output_layout.addWidget(self.output_filename_lineedit)
        
        layout.addLayout(output_layout)
        
        # オプション
        option_layout = QHBoxLayout()
        
        self.create_backup_checkbox = QCheckBox("バックアップ作成")
        self.create_backup_checkbox.setChecked(True)
        option_layout.addWidget(self.create_backup_checkbox)
        
        self.create_entry_log_checkbox = QCheckBox("エントリーログ作成")
        self.create_entry_log_checkbox.setChecked(True)
        option_layout.addWidget(self.create_entry_log_checkbox)
        
        option_layout.addStretch()
        layout.addLayout(option_layout)
        
        return group
    
    def create_button_area(self) -> QHBoxLayout:
        """実行ボタンエリア作成"""
        layout = QHBoxLayout()
        
        # マージ開始ボタン
        self.merge_button = QPushButton("マージ開始")
        self.merge_button.setMinimumHeight(40)
        self.merge_button.setStyleSheet(get_button_style("warning"))
        layout.addWidget(self.merge_button)
        
        # ログクリアボタン
        self.clear_log_button = QPushButton("ログクリア")
        self.clear_log_button.setMinimumHeight(40)
        layout.addWidget(self.clear_log_button)
        
        layout.addStretch()
        
        return layout
    
    def create_log_area(self) -> QGroupBox:
        """ログ表示エリア作成"""
        group = QGroupBox("ログ")
        layout = QVBoxLayout(group)
        
        self.log_textedit = QTextEdit()
        self.log_textedit.setReadOnly(True)
        self.log_textedit.setMinimumHeight(200)
        layout.addWidget(self.log_textedit)
        
        return group
    
    def create_file_info_area(self) -> QGroupBox:
        """ファイル情報表示エリア作成"""
        group = QGroupBox("出力ファイル情報")
        layout = QVBoxLayout(group)
        
        # ファイル情報ラベル
        self.file_info_label = QLabel("まだファイルは作成されていません")
        self.file_info_label.setWordWrap(True)
        layout.addWidget(self.file_info_label)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        # フォルダを開くボタン
        self.open_folder_button = QPushButton("📁 フォルダを開く")
        self.open_folder_button.setEnabled(True)
        self.open_folder_button.clicked.connect(self.on_open_folder_clicked)
        button_layout.addWidget(self.open_folder_button)
        
        # 最新JSONを開くボタン
        self.open_latest_json_button = QPushButton("📄 最新JSONを開く")
        self.open_latest_json_button.setEnabled(False)
        self.open_latest_json_button.clicked.connect(self.on_open_latest_json_clicked)
        button_layout.addWidget(self.open_latest_json_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group
    
    def connect_signals(self):
        """シグナル接続"""
        self.merge_button.clicked.connect(self.on_merge_clicked)
        self.clear_log_button.clicked.connect(self.on_clear_log_clicked)
        
        # 内部シグナル
        self.merge_progress.connect(self.log_message)
        self.merge_completed.connect(self.on_merge_completed)
    
    def on_merge_clicked(self):
        """マージ開始ボタンクリック"""
        if self.is_merging:
            return
        
        # 設定取得
        excel_filename = self.excel_filename_lineedit.text().strip()
        json_filename = self.json_filename_lineedit.text().strip()
        output_filename = self.output_filename_lineedit.text().strip()
        
        # 検証
        if not excel_filename:
            QMessageBox.warning(self, "エラー", "Excelファイル名を入力してください。")
            return
        
        if not json_filename:
            QMessageBox.warning(self, "エラー", "JSONファイル名を入力してください。")
            return
        
        if not output_filename:
            QMessageBox.warning(self, "エラー", "出力ファイル名を入力してください。")
            return
        
        output_filename = self._ensure_json_filename(output_filename)
        
        # 確認
        reply = QMessageBox.question(
            self,
            "確認",
            f"以下の設定でマージを開始します。\n\n"
            f"  Excelファイル: {excel_filename}\n"
            f"  JSONファイル: {json_filename}\n"
            f"  出力ファイル: {output_filename}\n"
            f"  バックアップ: {'有効' if self.create_backup_checkbox.isChecked() else '無効'}\n"
            f"  エントリーログ: {'有効' if self.create_entry_log_checkbox.isChecked() else '無効'}\n\n"
            f"よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # マージ開始
        self.start_merge(excel_filename, json_filename, output_filename)
    
    def start_merge(self, excel_filename: str, json_filename: str, output_filename: str):
        """マージ開始"""
        self.log_message(f"=" * 60)
        self.log_message(f"データマージ開始")
        self.log_message(f"  Excelファイル: {excel_filename}")
        self.log_message(f"  JSONファイル: {json_filename}")
        self.log_message(f"  出力ファイル: {output_filename}")
        self.log_message(f"=" * 60)
        
        # 状態更新
        self.is_merging = True
        self.merge_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.equipment.ui.merge_worker import DataMergeWorker
        
        self.worker_thread = DataMergeWorker(
            excel_filename=excel_filename,
            json_filename=json_filename,
            output_filename=output_filename,
            create_backup=self.create_backup_checkbox.isChecked(),
            create_entry_log=self.create_entry_log_checkbox.isChecked()
        )
        
        self.worker_thread.progress.connect(self.merge_progress.emit)
        self.worker_thread.completed.connect(self.merge_completed.emit)
        self.worker_thread.results.connect(self.on_merge_results)
        
        self.worker_thread.start()
    
    def on_clear_log_clicked(self):
        """ログクリアボタンクリック"""
        self.log_textedit.clear()
    
    def on_merge_completed(self, success: bool, message: str):
        """マージ完了"""
        self.log_message(f"=" * 60)
        if success:
            self.log_message(f"✅ マージ成功: {message}")
        else:
            self.log_message(f"❌ マージ失敗: {message}")
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_merging = False
        self.merge_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # 完了メッセージ
        if success:
            QMessageBox.information(self, "完了", message)
        else:
            QMessageBox.critical(self, "エラー", message)
    
    def on_merge_results(self, file_results: dict):
        """マージ結果（ファイルパス）受信"""
        self.latest_json_path = file_results.get('json_path')
        self.latest_backup_dir = file_results.get('backup_dir')
        
        # ファイル情報更新
        self.update_file_info()
    
    def update_file_info(self, show_empty: bool = False):
        """ファイル情報表示更新"""
        info_lines = ["📁 出力ファイル:"]
        found = False
        json_path = self._path_if_exists(self.latest_json_path)
        if json_path:
            info_lines.append(self._format_file_info("📄 JSON", json_path))
            self.open_latest_json_button.setEnabled(True)
            found = True
        else:
            self.open_latest_json_button.setEnabled(False)
        
        if self.latest_backup_dir:
            info_lines.append(f"  💾 バックアップ: {os.path.basename(self.latest_backup_dir)}")
            found = True
        
        if not found and show_empty:
            self.file_info_label.setText("📁 出力ファイル: 見つかりません")
            return
        elif not found:
            return
        
        self.file_info_label.setText("\n".join(info_lines))
    
    def log_message(self, message: str):
        """ログメッセージ追加"""
        self.log_textedit.append(message)
        # 自動スクロール
        cursor = self.log_textedit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_textedit.setTextCursor(cursor)
    
    def on_open_folder_clicked(self):
        """フォルダを開くボタンクリック"""
        folder_path = get_equipment_root_dir()
        folder_path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder_path))
    
    def on_open_latest_json_clicked(self):
        """最新JSONを開くボタンクリック"""
        if self.latest_json_path and os.path.exists(self.latest_json_path):
            os.startfile(self.latest_json_path)

    def refresh_from_disk(self):
        """ディスク上のマージ結果を読み込む"""
        output_filename = self._ensure_json_filename(
            self.output_filename_lineedit.text().strip() or "merged_data2.json"
        )
        base_dir = get_equipment_root_dir()
        file_path = base_dir / output_filename
        self.latest_json_path = str(file_path) if file_path.exists() else None

        backups_root = get_equipment_backups_root()
        latest_backup_dir = find_latest_child_directory(backups_root)
        if latest_backup_dir and (latest_backup_dir / output_filename).exists():
            self.latest_backup_dir = str(latest_backup_dir)
        else:
            self.latest_backup_dir = None

        self.update_file_info(show_empty=True)

    @staticmethod
    def _ensure_json_filename(name: str) -> str:
        if not name.endswith('.json'):
            return f"{name}.json"
        return name

    @staticmethod
    def _path_if_exists(path_str: Optional[str]) -> Optional[Path]:
        if not path_str:
            return None
        path = Path(path_str)
        return path if path.exists() else None

    @staticmethod
    def _format_file_info(label: str, path: Path) -> str:
        mtime_str = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        size_kb = path.stat().st_size / 1024
        return f"  {label}: {path.name} ({size_kb:.1f} KB, {mtime_str})"
