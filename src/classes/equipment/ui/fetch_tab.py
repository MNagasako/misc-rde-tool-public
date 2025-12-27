"""
設備タブ - データ取得タブ

設備データの並列取得機能を提供するタブUIです。
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from classes.equipment.util.output_paths import (
    find_latest_child_directory,
    find_latest_matching_file,
    get_equipment_backups_root,
    get_equipment_root_dir,
)
from classes.utils.button_styles import get_button_style

logger = logging.getLogger(__name__)

FETCH_ALL_START_ID = 1
FETCH_ALL_END_ID = 99999
FETCH_ALL_CHUNK_SIZE = 100
FETCH_ALL_STOP_LIMIT = 200

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
        QPushButton, QLineEdit, QTextEdit, QProgressBar,
        QGroupBox, QSpinBox, QCheckBox, QMessageBox
    )
    from qt_compat.gui import QTextCursor
    from qt_compat.core import Signal, QThread
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class FetchTab(QWidget):
    """データ取得タブ
    
    設備データの取得・処理・出力を行うタブUI
    """
    
    # シグナル定義
    fetch_started = Signal()
    fetch_progress = Signal(int, int, str)
    fetch_completed = Signal(int, int)
    fetch_cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 状態変数
        self.is_fetching = False
        self.cancel_requested = False
        
        # ファイルパス保存用
        self.latest_excel_path = None
        self.latest_json_path = None
        self.latest_backup_dir = None
        
        # コンポーネント（遅延初期化）
        self.fetcher = None
        self.processor = None
        self.exporter = None
        
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
            if hasattr(self, "fetch_button"):
                self.fetch_button.setStyleSheet(get_button_style("success"))
            if hasattr(self, "batch_process_button"):
                self.batch_process_button.setStyleSheet(get_button_style("warning"))
            if hasattr(self, "cancel_button"):
                self.cancel_button.setStyleSheet(get_button_style("danger"))
        except Exception:
            pass
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("<h2>設備データ取得</h2>")
        main_layout.addWidget(title_label)
        
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
        group = QGroupBox("取得設定")
        layout = QVBoxLayout(group)
        
        # 全件取得チェックボックス
        self.fetch_all_checkbox = QCheckBox("全件取得（全設備自動取得）")
        self.fetch_all_checkbox.setToolTip("チェックすると、サイト内の全設備情報を自動で取得します")
        self.fetch_all_checkbox.toggled.connect(self.on_fetch_all_toggled)
        layout.addWidget(self.fetch_all_checkbox)
        
        # 範囲指定
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("取得範囲:"))
        
        self.start_id_spinbox = QSpinBox()
        self.start_id_spinbox.setRange(1, 999999)
        self.start_id_spinbox.setValue(1)
        self.start_id_spinbox.setMinimumWidth(100)
        range_layout.addWidget(self.start_id_spinbox)
        
        range_layout.addWidget(QLabel("～"))
        
        self.end_id_spinbox = QSpinBox()
        self.end_id_spinbox.setRange(1, 999999)
        self.end_id_spinbox.setValue(50)
        self.end_id_spinbox.setMinimumWidth(100)
        range_layout.addWidget(self.end_id_spinbox)
        
        range_layout.addWidget(QLabel("（設備ID）"))
        range_layout.addStretch()
        
        layout.addLayout(range_layout)
        
        # 並列数設定
        parallel_layout = QHBoxLayout()
        parallel_layout.addWidget(QLabel("並列数:"))
        
        self.max_workers_spinbox = QSpinBox()
        self.max_workers_spinbox.setRange(1, 10)
        self.max_workers_spinbox.setValue(5)
        self.max_workers_spinbox.setMinimumWidth(100)
        self.max_workers_spinbox.setToolTip("同時に取得するスレッド数（推奨: 3-5）")
        parallel_layout.addWidget(self.max_workers_spinbox)
        
        parallel_layout.addStretch()
        layout.addLayout(parallel_layout)
        
        # 全件取得時の停止条件（連続不在件数）
        stop_condition_layout = QHBoxLayout()
        stop_condition_layout.addWidget(QLabel("全件取得時の停止条件（連続不在件数）:"))
        
        self.consecutive_not_found_spinbox = QSpinBox()
        self.consecutive_not_found_spinbox.setMinimum(1)
        self.consecutive_not_found_spinbox.setMaximum(500)
        self.consecutive_not_found_spinbox.setValue(FETCH_ALL_STOP_LIMIT)
        self.consecutive_not_found_spinbox.setToolTip(
            "全件取得時、この件数連続でデータが見つからなかった場合に取得を停止します"
            "（100件単位のスキャンを実施）"
        )
        stop_condition_layout.addWidget(self.consecutive_not_found_spinbox)
        
        stop_condition_layout.addStretch()
        layout.addLayout(stop_condition_layout)
        
        # 出力オプション
        output_layout = QHBoxLayout()
        
        self.export_excel_checkbox = QCheckBox("Excel出力")
        self.export_excel_checkbox.setChecked(True)
        output_layout.addWidget(self.export_excel_checkbox)
        
        self.export_json_checkbox = QCheckBox("JSON出力")
        self.export_json_checkbox.setChecked(True)
        output_layout.addWidget(self.export_json_checkbox)
        
        self.export_entries_checkbox = QCheckBox("個別エントリ出力")
        self.export_entries_checkbox.setChecked(True)
        output_layout.addWidget(self.export_entries_checkbox)
        
        output_layout.addStretch()
        layout.addLayout(output_layout)
        
        return group
    
    def create_button_area(self) -> QHBoxLayout:
        """実行ボタンエリア作成"""
        layout = QHBoxLayout()
        
        # 取得開始ボタン
        self.fetch_button = QPushButton("取得開始")
        self.fetch_button.setMinimumHeight(40)
        self.fetch_button.setStyleSheet(get_button_style("success"))
        layout.addWidget(self.fetch_button)
        
        # 一括処理ボタン（取得→変換→マージ）
        self.batch_process_button = QPushButton("🚀 一括処理（取得→変換→マージ）")
        self.batch_process_button.setMinimumHeight(40)
        self.batch_process_button.setStyleSheet(get_button_style("warning"))
        layout.addWidget(self.batch_process_button)
        
        # キャンセルボタン
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setStyleSheet(get_button_style("danger"))
        layout.addWidget(self.cancel_button)
        
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
        
        # フォルダを開くボタン（常に有効）
        self.open_folder_button = QPushButton("📁 フォルダを開く")
        self.open_folder_button.setEnabled(True)  # 常に有効
        self.open_folder_button.clicked.connect(self.on_open_folder_clicked)
        button_layout.addWidget(self.open_folder_button)
        
        # 最新Excelを開くボタン
        self.open_latest_excel_button = QPushButton("📊 最新Excelを開く")
        self.open_latest_excel_button.setEnabled(False)
        self.open_latest_excel_button.clicked.connect(self.on_open_latest_excel_clicked)
        button_layout.addWidget(self.open_latest_excel_button)
        
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
        self.fetch_button.clicked.connect(self.on_fetch_clicked)
        self.batch_process_button.clicked.connect(self.on_batch_process_clicked)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        self.clear_log_button.clicked.connect(self.on_clear_log_clicked)
        
        # 内部シグナル
        self.fetch_progress.connect(self.on_fetch_progress)
        self.fetch_completed.connect(self.on_fetch_completed)
    
    def on_fetch_all_toggled(self, checked: bool):
        """全件取得チェックボックス切り替え
        
        Args:
            checked: チェック状態
        """
        # 全件取得モードではID範囲入力を無効化
        self.start_id_spinbox.setEnabled(not checked)
        self.end_id_spinbox.setEnabled(not checked)
    
    def on_fetch_clicked(self):
        """取得開始ボタンクリック"""
        if self.is_fetching:
            return
        
        # 全件取得モード判定
        fetch_all = self.fetch_all_checkbox.isChecked()
        max_workers = self.max_workers_spinbox.value()
        
        if fetch_all:
            # 全件取得（固定範囲 + 連続不在判定）
            reply = QMessageBox.question(
                self,
                "確認",
                "設備の全件取得を実行します。\n"
                f"ID範囲: {FETCH_ALL_START_ID} ～ {FETCH_ALL_END_ID}\n"
                f"検索単位: {FETCH_ALL_CHUNK_SIZE}件 / 停止条件: 連続{FETCH_ALL_STOP_LIMIT}件不在\n"
                f"並列数: {max_workers}\n\n"
                "※大量のデータ取得となるため、時間がかかる場合があります。\n"
                "よろしいですか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 全件取得開始（1～9999）
            self.start_fetch(
                start_id=FETCH_ALL_START_ID,
                end_id=FETCH_ALL_END_ID,
                max_workers=max_workers,
                fetch_all=True
            )
        else:
            # 範囲指定モード
            start_id = self.start_id_spinbox.value()
            end_id = self.end_id_spinbox.value()
            
            # 検証
            if start_id > end_id:
                QMessageBox.warning(self, "エラー", "開始IDは終了IDより小さくしてください。")
                return
            
            # 確認
            count = end_id - start_id + 1
            reply = QMessageBox.question(
                self,
                "確認",
                f"設備ID {start_id} ～ {end_id} ({count}件) を取得します。\n"
                f"並列数: {max_workers}\n\n"
                f"よろしいですか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 取得開始
            self.start_fetch(start_id, end_id, max_workers)
    
    def start_fetch(self, start_id: int, end_id: int, max_workers: int, fetch_all: bool = False):
        """取得開始
        
        Args:
            start_id: 開始ID
            end_id: 終了ID
            max_workers: 並列数
        """
        consecutive_not_found_limit = (
            FETCH_ALL_STOP_LIMIT if fetch_all else self.consecutive_not_found_spinbox.value()
        )
        chunk_size = FETCH_ALL_CHUNK_SIZE if fetch_all else None
        
        self.log_message(f"=" * 60)
        if fetch_all:
            self.log_message(f"設備データ全件取得開始")
            self.log_message(
                f"  ID範囲: 全件（{FETCH_ALL_START_ID}～{FETCH_ALL_END_ID}、存在しないIDはスキップ）"
            )
            self.log_message(
                f"  検索単位: {FETCH_ALL_CHUNK_SIZE}件 / "
                f"停止条件: 連続{consecutive_not_found_limit}件不在"
            )
        else:
            self.log_message(f"設備データ取得開始")
            self.log_message(f"  開始ID: {start_id}")
            self.log_message(f"  終了ID: {end_id}")
        self.log_message(f"  並列数: {max_workers}")
        self.log_message(f"=" * 60)
        
        # 状態更新
        self.is_fetching = True
        self.cancel_requested = False
        self.fetch_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.equipment.ui.fetch_worker import FacilityFetchWorker

        worker_consecutive_limit = consecutive_not_found_limit if fetch_all else None
        worker_chunk_size = chunk_size if fetch_all else None

        self.worker_thread = FacilityFetchWorker(
            start_id=start_id,
            end_id=end_id,
            max_workers=max_workers,
            export_excel=self.export_excel_checkbox.isChecked(),
            export_json=self.export_json_checkbox.isChecked(),
            export_entries=self.export_entries_checkbox.isChecked(),
            consecutive_not_found_limit=worker_consecutive_limit,
            fetch_all_chunk_size=worker_chunk_size
        )
        
        self.worker_thread.progress.connect(self.fetch_progress.emit)
        self.worker_thread.completed.connect(self.fetch_completed.emit)
        self.worker_thread.log_message.connect(self.log_message)
        self.worker_thread.results.connect(self.on_fetch_results)
        
        self.worker_thread.start()
    
    def on_cancel_clicked(self):
        """キャンセルボタンクリック"""
        self.cancel_requested = True
        self.log_message("⚠ キャンセル要求されました...")
        self.cancel_button.setEnabled(False)
        
        # ワーカースレッドにもキャンセル要求を伝達
        if hasattr(self, 'worker_thread') and self.worker_thread:
            self.worker_thread.cancel_requested = True
    
    def on_clear_log_clicked(self):
        """ログクリアボタンクリック"""
        self.log_textedit.clear()
    
    def on_fetch_progress(self, current: int, total: int, message: str):
        """進捗更新"""
        # プログレスバー更新
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        
        # ログ出力
        self.log_message(message)
    
    def on_fetch_completed(self, success_count: int, error_count: int):
        """取得完了"""
        self.log_message(f"=" * 60)
        self.log_message(f"取得完了: 成功={success_count}, 失敗={error_count}")
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_fetching = False
        self.fetch_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        # 完了メッセージ
        QMessageBox.information(
            self,
            "完了",
            f"設備データ取得が完了しました。\n\n"
            f"成功: {success_count} 件\n"
            f"失敗: {error_count} 件"
        )
    
    def on_fetch_results(self, file_results: dict):
        """取得結果（ファイルパス）受信"""
        self.latest_excel_path = file_results.get('latest_excel')
        self.latest_json_path = file_results.get('latest_json')
        self.latest_backup_dir = file_results.get('backup_dir')
        
        # ファイル情報更新
        self.update_file_info()
    
    def update_file_info(self, show_empty: bool = False):
        """ファイル情報表示更新"""
        info_lines = ["📁 出力ファイル:"]
        found = False
        
        excel_path = self._path_if_exists(self.latest_excel_path)
        if excel_path:
            info_lines.append(self._format_file_info("📊 Excel", excel_path))
            self.open_latest_excel_button.setEnabled(True)
            found = True
        else:
            self.open_latest_excel_button.setEnabled(False)
        
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
    
    def on_open_latest_excel_clicked(self):
        """最新Excelを開くボタンクリック"""
        if self.latest_excel_path and os.path.exists(self.latest_excel_path):
            os.startfile(self.latest_excel_path)
    
    def on_open_latest_json_clicked(self):
        """最新JSONを開くボタンクリック"""
        if self.latest_json_path and os.path.exists(self.latest_json_path):
            os.startfile(self.latest_json_path)

    def refresh_from_disk(self):
        """ディスク上の最新ファイル情報を読み取り"""
        base_dir = get_equipment_root_dir()
        self.latest_excel_path = self._path_to_str(
            find_latest_matching_file(base_dir, ["facilities_*.xlsx", "facilities_full.xlsx"])
        )
        self.latest_json_path = self._path_to_str(
            find_latest_matching_file(base_dir, ["facilities_*.json"])
        )
        backups_dir = get_equipment_backups_root()
        latest_backup = find_latest_child_directory(backups_dir)
        self.latest_backup_dir = self._path_to_str(latest_backup)
        self.update_file_info(show_empty=True)

    @staticmethod
    def _path_to_str(path: Optional[Path]) -> Optional[str]:
        return str(path) if path else None

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
    
    def on_batch_process_clicked(self):
        """一括処理ボタンクリック（取得→変換→マージ）"""
        if self.is_fetching:
            return
        
        fetch_all = self.fetch_all_checkbox.isChecked()
        max_workers = self.max_workers_spinbox.value()

        if fetch_all:
            reply = QMessageBox.question(
                self,
                "確認",
                "設備の全件取得を含む一括処理を実行します。\n"
                f"ID範囲: {FETCH_ALL_START_ID} ～ {FETCH_ALL_END_ID}\n"
                f"検索単位: {FETCH_ALL_CHUNK_SIZE}件 / 停止条件: 連続{FETCH_ALL_STOP_LIMIT}件不在\n\n"
                "処理には時間がかかる場合があります。\n"
                "よろしいですか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            self.start_batch_process(
                FETCH_ALL_START_ID,
                FETCH_ALL_END_ID,
                max_workers,
                fetch_all=True
            )
            return

        # 範囲指定モード
        start_id = self.start_id_spinbox.value()
        end_id = self.end_id_spinbox.value()

        if start_id > end_id:
            QMessageBox.warning(self, "エラー", "開始IDは終了IDより小さくしてください。")
            return

        count = end_id - start_id + 1
        reply = QMessageBox.question(
            self,
            "確認",
            f"以下の処理を一括実行します：\n\n"
            f"1. 設備データ取得（ID {start_id}～{end_id}, {count}件）\n"
            f"2. カタログ変換（Excel→JSON）\n"
            f"3. データマージ（Excel+JSON）\n\n"
            f"処理には時間がかかる場合があります。\n"
            f"よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.start_batch_process(start_id, end_id, max_workers)
    
    def start_batch_process(
        self,
        start_id: int,
        end_id: int,
        max_workers: int,
        fetch_all: bool = False
    ):
        """一括処理開始"""
        self.log_message(f"=" * 60)
        self.log_message(f"🚀 一括処理開始（取得→変換→マージ）")
        if fetch_all:
            self.log_message(
                f"  設備ID範囲: {FETCH_ALL_START_ID}～{FETCH_ALL_END_ID}"
            )
            self.log_message(
                f"  検索単位: {FETCH_ALL_CHUNK_SIZE}件 / 停止条件: 連続{FETCH_ALL_STOP_LIMIT}件不在"
            )
        else:
            self.log_message(f"  設備ID範囲: {start_id}～{end_id}")
        self.log_message(f"=" * 60)
        
        # 状態更新
        self.is_fetching = True
        self.fetch_button.setEnabled(False)
        self.batch_process_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.equipment.ui.batch_process_worker import BatchProcessWorker
        
        worker_consecutive_limit = FETCH_ALL_STOP_LIMIT if fetch_all else None
        worker_chunk_size = FETCH_ALL_CHUNK_SIZE if fetch_all else None

        self.worker_thread = BatchProcessWorker(
            start_id=start_id,
            end_id=end_id,
            max_workers=max_workers,
            fetch_all=fetch_all,
            consecutive_not_found_limit=worker_consecutive_limit,
            fetch_all_chunk_size=worker_chunk_size
        )
        
        self.worker_thread.progress.connect(self.fetch_progress.emit)
        self.worker_thread.completed.connect(self.on_batch_process_completed)
        self.worker_thread.log_message.connect(self.log_message)
        self.worker_thread.results.connect(self.on_fetch_results)
        
        self.worker_thread.start()
    
    def on_batch_process_completed(self, success: bool, message: str):
        """一括処理完了"""
        self.log_message(f"=" * 60)
        if success:
            self.log_message(f"✅ 一括処理完了")
        else:
            self.log_message(f"❌ 一括処理失敗: {message}")
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_fetching = False
        self.fetch_button.setEnabled(True)
        self.batch_process_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        # 完了メッセージ
        if success:
            QMessageBox.information(
                self,
                "完了",
                f"一括処理が完了しました。\n\n{message}"
            )
        else:
            QMessageBox.critical(
                self,
                "エラー",
                f"一括処理でエラーが発生しました。\n\n{message}"
            )
