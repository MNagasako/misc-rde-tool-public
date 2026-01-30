"""
報告書タブ - データ取得タブ

報告書データの並列取得機能を提供するタブUIです。
"""

import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from classes.reports.util.output_paths import (
    find_latest_child_directory,
    find_latest_matching_file,
    get_reports_backups_root,
    get_reports_root_dir,
)

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
        QPushButton, QLineEdit, QTextEdit, QProgressBar,
        QGroupBox, QSpinBox, QCheckBox, QMessageBox, QRadioButton
    )
    from qt_compat.gui import QTextCursor
    from qt_compat.core import Signal, QThread
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")

from classes.theme import get_color, ThemeKey


class ReportFetchTab(QWidget):
    """報告書データ取得タブ
    
    報告書データの取得・処理・出力を行うタブUI
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
        
        self.setup_ui()
        self.connect_signals()
    
    def setup_ui(self):
        """UI構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("<h2>📊 報告書データ取得</h2>")
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
        self.fetch_all_checkbox = QCheckBox("全件取得（全ページ自動取得）")
        self.fetch_all_checkbox.setToolTip("チェックすると、サイト内の全報告書を自動で取得します")
        self.fetch_all_checkbox.toggled.connect(self.on_fetch_all_toggled)
        layout.addWidget(self.fetch_all_checkbox)
        
        # ページ範囲指定
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("取得範囲:"))
        
        self.start_page_spinbox = QSpinBox()
        self.start_page_spinbox.setRange(1, 999)
        self.start_page_spinbox.setValue(1)
        self.start_page_spinbox.setMinimumWidth(100)
        range_layout.addWidget(self.start_page_spinbox)
        
        range_layout.addWidget(QLabel("～"))
        
        self.end_page_spinbox = QSpinBox()
        self.end_page_spinbox.setRange(1, 999)
        self.end_page_spinbox.setValue(10)
        self.end_page_spinbox.setMinimumWidth(100)
        range_layout.addWidget(self.end_page_spinbox)
        
        range_layout.addWidget(QLabel("（ページ）"))
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

        # キャッシュ設定
        cache_group = QGroupBox("キャッシュ設定")
        cache_layout = QVBoxLayout(cache_group)

        self.cache_skip_radio = QRadioButton("既存キャッシュを再利用（取得済みをスキップ）")
        self.cache_skip_radio.setChecked(True)
        cache_layout.addWidget(self.cache_skip_radio)

        self.cache_overwrite_radio = QRadioButton("常に再取得してキャッシュを上書き保存")
        cache_layout.addWidget(self.cache_overwrite_radio)

        layout.addWidget(cache_group)
        
        return group

    def current_cache_mode(self):
        """選択中のキャッシュモードを取得"""
        from classes.reports.core.report_cache_manager import ReportCacheMode

        return (
            ReportCacheMode.SKIP
            if self.cache_skip_radio.isChecked()
            else ReportCacheMode.OVERWRITE
        )

    def cache_mode_description(self) -> str:
        if self.cache_skip_radio.isChecked():
            return "既存キャッシュを再利用（取得済みをスキップ）"
        return "常に再取得してキャッシュを上書き"
    
    def create_button_area(self) -> QHBoxLayout:
        """ボタンエリア作成"""
        layout = QHBoxLayout()
        
        # 取得開始ボタン
        self.fetch_button = QPushButton("📥 取得開始")
        self.fetch_button.setMinimumHeight(40)
        self.fetch_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        layout.addWidget(self.fetch_button)
        
        # 一括処理ボタン（取得→変換→研究データ生成）
        self.batch_process_button = QPushButton("🚀 一括処理（取得→変換→研究データ生成）")
        self.batch_process_button.setMinimumHeight(40)
        self.batch_process_button.setStyleSheet(f"""
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
        layout.addWidget(self.batch_process_button)
        
        # キャンセルボタン
        self.cancel_button = QPushButton("⛔ キャンセル")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        layout.addWidget(self.cancel_button)
        
        # ログクリアボタン
        self.clear_log_button = QPushButton("🗑️ ログクリア")
        self.clear_log_button.setMinimumHeight(40)
        layout.addWidget(self.clear_log_button)
        
        return layout
    
    def _apply_button_styles(self):
        """ボタンスタイルを適用"""
        # 取得開始ボタン
        self.fetch_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        
        # 一括処理ボタン
        self.batch_process_button.setStyleSheet(f"""
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
        
        # キャンセルボタン
        self.cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
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
        """全件取得チェックボックス切り替え"""
        # ページ範囲入力を無効化/有効化
        self.start_page_spinbox.setEnabled(not checked)
        self.end_page_spinbox.setEnabled(not checked)
        
        if checked:
            self.log_message("ℹ️ 全件取得モード: サイト内の全報告書を取得します")
        else:
            self.log_message("ℹ️ 範囲指定モード: 指定ページのみ取得します")
    
    def on_fetch_clicked(self):
        """取得開始ボタンクリック"""
        if self.is_fetching:
            return
        
        # 全件取得モードの判定
        fetch_all = self.fetch_all_checkbox.isChecked()
        
        if fetch_all:
            # 全件取得モード
            reply = QMessageBox.question(
                self,
                "確認",
                "全件取得モードで実行します。\n"
                "サイト内の全報告書を取得するため、時間がかかる場合があります。\n\n"
                "よろしいですか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 全件取得（start_page=1, page_count=None）
            max_workers = self.max_workers_spinbox.value()
            self.start_fetch(start_page=1, page_count=None, max_workers=max_workers)
        else:
            # 範囲指定モード（既存ロジック）
            start_page = self.start_page_spinbox.value()
            end_page = self.end_page_spinbox.value()
            max_workers = self.max_workers_spinbox.value()
            
            # 検証
            if start_page > end_page:
                QMessageBox.warning(self, "エラー", "開始ページは終了ページより小さくしてください。")
                return
            
            # 確認
            page_count = end_page - start_page + 1
            reply = QMessageBox.question(
                self,
                "確認",
                f"ページ {start_page} ～ {end_page} ({page_count}ページ) の報告書を取得します。\n"
                f"並列数: {max_workers}\n\n"
                f"よろしいですか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 取得開始
            self.start_fetch(start_page, page_count, max_workers)
    
    def start_fetch(self, start_page: int, page_count: Optional[int], max_workers: int):
        """取得開始
        
        Args:
            start_page: 開始ページ
            page_count: ページ数（Noneの場合は全件取得）
            max_workers: 並列数
        """
        if page_count is None:
            self.log_message(f"=" * 60)
            self.log_message(f"報告書全件取得開始")
            self.log_message(f"  開始ページ: {start_page}")
            self.log_message(f"  ページ数: 全件（100件/ページ・display_result=2）")
            self.log_message(f"  並列数: {max_workers}")
            self.log_message(f"=" * 60)
        else:
            self.log_message(f"=" * 60)
            self.log_message(f"報告書取得開始")
            self.log_message(f"  開始ページ: {start_page}")
            self.log_message(f"  ページ数: {page_count}")
            self.log_message(f"  並列数: {max_workers}")
            self.log_message(f"=" * 60)
        self.log_message(f"  キャッシュ: {self.cache_mode_description()}")
        
        # 状態更新
        self.is_fetching = True
        self.cancel_requested = False
        self.fetch_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定状態
        
        # ワーカースレッド起動
        from classes.reports.ui.fetch_worker import ReportFetchWorker
        
        self.worker_thread = ReportFetchWorker(
            start_page=start_page,
            page_count=page_count,
            max_workers=max_workers,
            cache_mode=self.current_cache_mode()
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
            f"報告書取得が完了しました。\n\n"
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
        self.open_folder_button.setEnabled(True)
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

        if not found:
            if show_empty:
                self.file_info_label.setText("📁 出力ファイル: 見つかりません")
            return

        self.file_info_label.setText("\n".join(info_lines))
        self.open_folder_button.setEnabled(True)
    
    def on_open_folder_clicked(self):
        """フォルダを開くボタンクリック"""
        from classes.core.platform import open_path

        folder_path = get_reports_root_dir()
        folder_path.mkdir(parents=True, exist_ok=True)
        if not open_path(str(folder_path)):
            QMessageBox.warning(self, "エラー", "フォルダを開けませんでした。")
    
    def on_open_latest_excel_clicked(self):
        """最新Excelを開くボタンクリック"""
        from classes.core.platform import open_path

        excel_path = self._path_if_exists(self.latest_excel_path)
        if excel_path:
            if not open_path(str(excel_path)):
                QMessageBox.warning(self, "エラー", "Excelファイルを開けませんでした。")
        else:
            QMessageBox.warning(self, "エラー", "Excelファイルが見つかりません。")
    
    def on_open_latest_json_clicked(self):
        """最新JSONを開くボタンクリック"""
        from classes.core.platform import open_path

        json_path = self._path_if_exists(self.latest_json_path)
        if json_path:
            if not open_path(str(json_path)):
                QMessageBox.warning(self, "エラー", "JSONファイルを開けませんでした。")
        else:
            QMessageBox.warning(self, "エラー", "JSONファイルが見つかりません。")
    
    def log_message(self, message: str):
        """ログメッセージ追加"""
        self.log_textedit.append(message)
        
        # 自動スクロール
        cursor = self.log_textedit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_textedit.setTextCursor(cursor)
    
    def on_batch_process_clicked(self):
        """一括処理ボタンクリック（取得→変換→研究データ生成）"""
        if self.is_fetching:
            return
        
        fetch_all = self.fetch_all_checkbox.isChecked()
        max_workers = self.max_workers_spinbox.value()

        if fetch_all:
            reply = QMessageBox.question(
                self,
                "確認",
                "報告書の全件取得を含む一括処理を実行します。\n"
                "表示件数: 100件/ページ (display_result=2)\n"
                "全ページを自動で取得し、変換・研究データ生成まで実行します。\n\n"
                "処理には時間がかかる場合があります。\n"
                "よろしいですか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            self.start_batch_process(start_page=1, page_count=None, max_workers=max_workers)
            return

        # 設定取得（範囲指定）
        start_page = self.start_page_spinbox.value()
        page_count = self.end_page_spinbox.value() - start_page + 1
        
        if start_page > self.end_page_spinbox.value():
            QMessageBox.warning(self, "エラー", "開始ページは終了ページより小さくしてください。")
            return
        
        reply = QMessageBox.question(
            self,
            "確認",
            f"以下の処理を一括実行します：\n\n"
            f"1. 報告書データ取得（ページ {start_page}～{self.end_page_spinbox.value()}, {page_count}ページ）\n"
            f"2. 研究データ生成（設備別研究情報JSON）\n\n"
            f"処理には時間がかかる場合があります。\n"
            f"よろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.start_batch_process(start_page, page_count, max_workers)
    
    def start_batch_process(
        self,
        start_page: int,
        page_count: Optional[int],
        max_workers: int
    ):
        """一括処理開始"""
        self.log_message(f"=" * 60)
        self.log_message(f"🚀 一括処理開始（取得→研究データ生成）")
        if page_count is None:
            self.log_message("  ページ範囲: 全件取得（100件/ページ）")
        else:
            self.log_message(f"  ページ範囲: {start_page}～{start_page + page_count - 1}")
        self.log_message(f"=" * 60)
        self.log_message(f"  キャッシュ: {self.cache_mode_description()}")
        
        # 状態更新
        self.is_fetching = True
        self.fetch_button.setEnabled(False)
        self.batch_process_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不定形
        
        # ワーカースレッド作成・開始
        from classes.reports.ui.batch_process_worker import ReportBatchWorker
        
        cache_mode = self.current_cache_mode()

        self.worker_thread = ReportBatchWorker(
            start_page=start_page,
            page_count=page_count,
            max_workers=max_workers,
            cache_mode=cache_mode
        )
        
        # シグナル接続
        self.worker_thread.progress.connect(self.on_batch_progress)
        self.worker_thread.log_message.connect(self.log_message)
        self.worker_thread.completed.connect(self.on_batch_completed)
        self.worker_thread.error.connect(self.on_batch_error)
        
        # 開始
        self.worker_thread.start()
    
    def on_batch_progress(self, current: int, total: int, message: str):
        """一括処理プログレス"""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.log_message(message)
    
    def on_batch_completed(self, results: dict):
        """一括処理完了"""
        self.log_message(f"=" * 60)
        self.log_message(f"✅ 一括処理完了")
        self.log_message(f"=" * 60)
        
        # 状態リセット
        self.is_fetching = False
        self.fetch_button.setEnabled(True)
        self.batch_process_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        # 結果サマリー
        summary = f"一括処理が完了しました。\n\n"
        summary += f"取得: {results['success_count']} 件\n"
        summary += f"変換済みExcel: {os.path.basename(results['output_excel'])}\n"
        if results.get('output_json'):
            summary += f"研究データJSON: {os.path.basename(results['output_json'])}"
        
        QMessageBox.information(self, "完了", summary)
        
        # ファイル情報更新
        self.latest_excel_path = results['output_excel']
        if results.get('output_json'):
            self.latest_json_path = results['output_json']
        self.update_file_info()
    
    def on_batch_error(self, error_message: str):
        """一括処理エラー"""
        self.log_message(f"❌ エラー: {error_message}")
        
        # 状態リセット
        self.is_fetching = False
        self.fetch_button.setEnabled(True)
        self.batch_process_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        QMessageBox.critical(
            self,
            "エラー",
            f"一括処理でエラーが発生しました。\n\n{error_message}"
        )

    def refresh_from_disk(self):
        """ディスク上の最新出力を反映"""
        base_dir = get_reports_root_dir()
        self.latest_excel_path = self._path_to_str(
            find_latest_matching_file(base_dir, ["ARIM-extracted2*.xlsx"])
        )
        self.latest_json_path = self._path_to_str(
            find_latest_matching_file(base_dir, ["ARIM-extracted2*.json"])
        )
        backups_dir = get_reports_backups_root()
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
