"""
報告書タブ - データ取得ワーカー

報告書データの並列取得処理を実行するワーカースレッドです。
"""

import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

try:
    from qt_compat.core import QThread, Signal
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class ReportFetchWorker(QThread):
    """報告書取得ワーカースレッド"""
    
    progress = Signal(int, int, str)
    completed = Signal(int, int)
    log_message = Signal(str)
    results = Signal(dict)
    
    def __init__(self, start_page: int, page_count: int, max_workers: int):
        super().__init__()
        self.start_page = start_page
        self.page_count = page_count
        self.max_workers = max_workers
        self.cancel_requested = False
    
    def run(self):
        """スレッド実行"""
        try:
            from classes.reports.core.parallel_fetcher import ParallelReportFetcher
            from classes.reports.core.report_data_processor import ReportDataProcessor
            from classes.reports.core.report_file_exporter import ReportFileExporter
            
            # コンポーネント初期化
            self.log_message.emit("=" * 60)
            self.log_message.emit("📦 コンポーネント初期化...")
            fetcher = ParallelReportFetcher(max_workers=self.max_workers)
            processor = ReportDataProcessor()
            exporter = ReportFileExporter()
            
            # 全件取得モードのログ
            if self.page_count is None:
                self.log_message.emit("🔍 全件取得モード: 最大ページ数を自動取得します")
            
            # 並列取得
            self.log_message.emit("=" * 60)
            self.log_message.emit("🚀 報告書並列取得開始...")
            
            # プログレスコールバック（キャンセル対応）
            def progress_callback(current, total, message):
                # キャンセルチェック
                if self.cancel_requested:
                    self.log_message.emit("⚠ キャンセルされました")
                    return False  # Falseを返してキャンセル
                
                self.progress.emit(current, total, message)
                # 詳細ログ（10件ごと）
                if current % 10 == 0 or current == total:
                    self.log_message.emit(f"  [{current}/{total}] {message}")
                
                return True  # 続行
            
            # 実際の取得処理
            try:
                success_data, error_data = fetcher.fetch_range(
                    start_page=self.start_page,
                    max_pages=self.page_count,
                    progress_callback=progress_callback
                )
                
                self.log_message.emit("=" * 60)
                self.log_message.emit(f"✅ 取得完了: 成功={len(success_data)}, 失敗={len(error_data)}")
            
            except Exception as fetch_error:
                logger.error(f"fetch_range エラー: {fetch_error}", exc_info=True)
                self.log_message.emit(f"❌ 取得エラー: {str(fetch_error)}")
                success_data = []
                error_data = []
            
            # データ処理
            if success_data:
                self.log_message.emit("=" * 60)
                self.log_message.emit("🔄 データ処理中...")
                valid_data, invalid_data = processor.process_batch(success_data)
                self.log_message.emit(f"✅ 処理完了: 有効={len(valid_data)}, 無効={len(invalid_data)}")
                
                # ファイル出力
                self.log_message.emit("=" * 60)
                self.log_message.emit("💾 ファイル出力中...")
                file_results = exporter.export_with_backup(valid_data, "output")
                self.log_message.emit("✅ ファイル出力完了")
                self.log_message.emit("=" * 60)
                
                # 結果送信
                self.results.emit(file_results)
            
            # 完了通知
            self.completed.emit(len(success_data), len(error_data))
            
        except Exception as e:
            logger.error(f"ワーカーエラー: {e}", exc_info=True)
            self.log_message.emit(f"エラー: {str(e)}")
            self.completed.emit(0, 0)
