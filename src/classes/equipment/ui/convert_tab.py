"""
設備タブ - カタログ変換タブ

Excelカタログ→JSON変換機能を提供するタブUIです。
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


class ConvertTab(QWidget):
    """カタログ変換タブ
    
    Excelカタログを読み込み、JSON形式に変換するタブUI
    """
    
    # シグナル定義
    convert_started = Signal()
    convert_progress = Signal(str)
    convert_completed = Signal(bool, str)  # success, message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 状態変数
        self.is_converting = False
        
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
            if hasattr(self, "convert_button"):
                self.convert_button.setStyleSheet(get_button_style("info"))
        except Exception:
            pass
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("<h2>カタログ変換（Excel → JSON）</h2>")
        main_layout.addWidget(title_label)
        
        # 説明
        desc_label = QLabel(
            "Excelカタログファイルを読み込み、JSON形式（fasi_ext.json）に変換します。\n"
            "複数のExcelファイルがある場合、prefixで絞り込みます。"
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
        group = QGroupBox("変換設定")
        layout = QVBoxLayout(group)
        
        # Prefix設定
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Excelファイルprefix:"))
        
        self.prefix_lineedit = QLineEdit()
        self.prefix_lineedit.setText("ARIM 計測装置カタログ")
        self.prefix_lineedit.setPlaceholderText("例: ARIM 計測装置カタログ")
        self.prefix_lineedit.setToolTip("Excelファイル名の前方一致で検索")
        prefix_layout.addWidget(self.prefix_lineedit)
        
        layout.addLayout(prefix_layout)
        
        # 出力ファイル名設定
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("出力JSONファイル名:"))
        
        self.output_filename_lineedit = QLineEdit()
        self.output_filename_lineedit.setText("fasi_ext.json")
        self.output_filename_lineedit.setPlaceholderText("例: fasi_ext.json")
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
        
        # 変換開始ボタン
        self.convert_button = QPushButton("変換開始")
        self.convert_button.setMinimumHeight(40)
        self.convert_button.setStyleSheet(get_button_style("info"))
        layout.addWidget(self.convert_button)
        
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
        self.convert_button.clicked.connect(self.on_convert_clicked)
        self.clear_log_button.clicked.connect(self.on_clear_log_clicked)
        
        # 内部シグナル
        self.convert_progress.connect(self.log_message)
        self.convert_completed.connect(self.on_convert_completed)
    
    def on_convert_clicked(self):
        """変換開始ボタンクリック"""
        if self.is_converting:
            return
        
        # 設定取得
        prefix = self.prefix_lineedit.text().strip()
        output_filename = self.output_filename_lineedit.text().strip()
        
        # 検証
        if not prefix:
            QMessageBox.warning(self, "エラー", "Excelファイルのprefixを入力してください。")
            return
        
        if not output_filename:
            QMessageBox.warning(self, "エラー", "出力ファイル名を入力してください。")
            return
        
        output_filename = self._ensure_json_filename(output_filename)
        
        # 確認
        reply = QMessageBox.question(
            self,
            "確認",
            f"以下の設定で変換を開始します。\n\n"
            f"  Prefix: {prefix}\n"
            f"  出力ファイル: {output_filename}\n"
            f"  バックアップ: {'有効' if self.create_backup_checkbox.isChecked() else '無効'}\n"
            f"  エントリーログ: {'有効' if self.create_entry_log_checkbox.isChecked() else '無効'}\n\n"
            f"よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 変換開始
        self.start_convert(prefix, output_filename)
    
    def start_convert(self, prefix: str, output_filename: str):
        """変換開始"""
        self.log_message(f"=" * 60)
        self.log_message(f"カタログ変換開始")
        self.log_message(f"  Prefix: {prefix}")
        self.log_message(f"  出力ファイル: {output_filename}")
        self.log_message(f"=" * 60)
        
        # 状態更新
        self.is_converting = True
        self.convert_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.equipment.ui.convert_worker import CatalogConvertWorker
        
        self.worker_thread = CatalogConvertWorker(
            prefix=prefix,
            output_filename=output_filename,
            create_backup=self.create_backup_checkbox.isChecked(),
            create_entry_log=self.create_entry_log_checkbox.isChecked()
        )
        
        self.worker_thread.progress.connect(self.convert_progress.emit)
        self.worker_thread.completed.connect(self.convert_completed.emit)
        self.worker_thread.results.connect(self.on_convert_results)
        
        self.worker_thread.start()
    
    def on_clear_log_clicked(self):
        """ログクリアボタンクリック"""
        self.log_textedit.clear()
    
    def on_convert_completed(self, success: bool, message: str):
        """変換完了"""
        self.log_message(f"=" * 60)
        if success:
            self.log_message(f"✅ 変換成功: {message}")
        else:
            self.log_message(f"❌ 変換失敗: {message}")
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_converting = False
        self.convert_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # 完了メッセージ
        if success:
            QMessageBox.information(self, "完了", message)
        else:
            QMessageBox.critical(self, "エラー", message)
    
    def on_convert_results(self, file_results: dict):
        """変換結果（ファイルパス）受信"""
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
        from classes.core.platform import open_path

        folder_path = get_equipment_root_dir()
        folder_path.mkdir(parents=True, exist_ok=True)
        if not open_path(str(folder_path)):
            QMessageBox.warning(self, "エラー", "フォルダを開けませんでした。")
    
    def on_open_latest_json_clicked(self):
        """最新JSONを開くボタンクリック"""
        if self.latest_json_path and os.path.exists(self.latest_json_path):
            from classes.core.platform import open_path

            if not open_path(self.latest_json_path):
                QMessageBox.warning(self, "エラー", "JSONファイルを開けませんでした。")

    def refresh_from_disk(self):
        """ディスク上の出力状況を読み込む"""
        output_filename = self._ensure_json_filename(
            self.output_filename_lineedit.text().strip() or "fasi_ext.json"
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
