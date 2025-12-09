"""
設備タブ - データ取得ワーカー

設備データ取得処理をバックグラウンドで実行するワーカースレッドです。
"""

import logging
from datetime import datetime
from typing import Optional

from classes.equipment.util.output_paths import get_equipment_root_dir
from classes.equipment.core.fetch_range_builder import collect_valid_facility_ids
from classes.equipment.core.facility_listing import FacilityListingScraper

logger = logging.getLogger(__name__)

try:
    from qt_compat.core import QThread, Signal
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class FacilityFetchWorker(QThread):
    """設備データ取得ワーカースレッド
    
    ParallelFacilityFetcherを使用して設備データを並列取得します。
    """
    
    # シグナル定義
    progress = Signal(int, int, str)  # current, total, message
    completed = Signal(int, int)  # success_count, error_count
    log_message = Signal(str)
    results = Signal(dict)  # file_results
    
    def __init__(
        self,
        start_id: int,
        end_id: int,
        max_workers: int = 5,
        export_excel: bool = True,
        export_json: bool = True,
        export_entries: bool = True,
        consecutive_not_found_limit: Optional[int] = None,
        fetch_all_chunk_size: Optional[int] = None,
        parent=None
    ):
        super().__init__(parent)
        
        self.start_id = start_id
        self.end_id = end_id
        self.max_workers = max_workers
        self.export_excel = export_excel
        self.export_json = export_json
        self.export_entries = export_entries
        self.consecutive_not_found_limit = consecutive_not_found_limit
        self.fetch_all_chunk_size = fetch_all_chunk_size
        
        self.cancel_requested = False
    
    def run(self):
        """取得処理実行"""
        try:
            from classes.equipment.core.parallel_fetcher import ParallelFacilityFetcher
            from classes.equipment.core.data_processor import FacilityDataProcessor
            from classes.equipment.core.file_exporter import FacilityExporter
            
            equipment_dir = get_equipment_root_dir()
            self.log_message.emit(f"📂 設備出力先: {equipment_dir}")
            
            # 連続不在判定モードかどうか
            if self.consecutive_not_found_limit:
                chunk_size = self.fetch_all_chunk_size or 1
                facility_ids = collect_valid_facility_ids(
                    start_id=self.start_id,
                    end_id=self.end_id,
                    chunk_size=chunk_size,
                    stop_threshold=self.consecutive_not_found_limit,
                    log_callback=self.log_message.emit,
                    cancel_checker=lambda: self.cancel_requested,
                    listing_scraper=FacilityListingScraper()
                )
            else:
                # 通常モード: 指定範囲すべて
                facility_ids = list(range(self.start_id, self.end_id + 1))
            
            if not facility_ids:
                self.log_message.emit("⚠ 取得する設備IDがありません")
                self.completed.emit(0, 0)
                return
            
            total_count = len(facility_ids)
            self.log_message.emit(f"🔄 {total_count}件の設備データを取得開始...")
            
            # 並列取得
            fetcher = ParallelFacilityFetcher(max_workers=self.max_workers)
            
            def progress_callback(current, total, message):
                """プログレスコールバック"""
                self.progress.emit(current, total, message)
                self.log_message.emit(f"[{current}/{total}] {message}")
                return not self.cancel_requested
            
            success_data, error_info = fetcher.fetch_facilities_with_results(
                facility_ids=facility_ids,
                progress_callback=progress_callback
            )
            
            success_count = len(success_data)
            error_count = len(error_info)
            
            self.log_message.emit(f"✅ 取得完了: 成功={success_count}, 失敗={error_count}")
            
            # データ処理
            if success_data:
                self.log_message.emit("🔄 データ処理中...")
                processor = FacilityDataProcessor()
                processed_data, process_errors = processor.process_batch(success_data)
                
                self.log_message.emit(f"✅ {len(processed_data)}件のデータを処理")
                if process_errors:
                    self.log_message.emit(f"⚠ {len(process_errors)}件の処理エラー")
                
                # ファイル出力
                exporter = FacilityExporter()
                
                # タイムスタンプ付きファイル名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_filename = f"facilities_{timestamp}"
                
                if self.export_excel and self.export_json:
                    # Excel+JSON出力（バックアップ付き）
                    self.log_message.emit("📊📄 Excel/JSON出力中（バックアップ付き）...")
                    file_results = exporter.export_with_backup(processed_data, base_filename)
                    latest_excel = file_results.get('latest_excel')
                    latest_json = file_results.get('latest_json')
                    backup_dir = file_results.get('backup_dir')
                    self.log_message.emit(f"✅ Excel出力完了: {latest_excel}")
                    self.log_message.emit(f"✅ JSON出力完了: {latest_json}")
                    self.log_message.emit(f"💾 バックアップ: {backup_dir}")
                else:
                    # 個別出力
                    latest_excel = None
                    latest_json = None
                    backup_dir = None
                    
                    if self.export_excel:
                        self.log_message.emit("📊 Excel出力中...")
                        latest_excel = exporter.export_excel(processed_data, f"{base_filename}.xlsx")
                        self.log_message.emit(f"✅ Excel出力完了: {latest_excel}")
                    
                    if self.export_json:
                        self.log_message.emit("📄 JSON出力中...")
                        latest_json = exporter.export_json(processed_data, f"{base_filename}.json")
                        self.log_message.emit(f"✅ JSON出力完了: {latest_json}")
                
                if self.export_entries:
                    self.log_message.emit("📁 個別エントリ出力中...")
                    entry_dir = exporter.export_json_entries(processed_data)
                    self.log_message.emit(f"✅ 個別エントリ出力完了: {entry_dir}")
                
                # 結果送信
                self.results.emit({
                    'latest_excel': latest_excel,
                    'latest_json': latest_json,
                    'backup_dir': backup_dir
                })
            else:
                self.log_message.emit("⚠ 取得されたデータがありません")
            
            # 完了通知
            self.completed.emit(success_count, error_count)
        
        except Exception as e:
            logger.exception("設備データ取得エラー")
            self.log_message.emit(f"❌ エラー: {str(e)}")
            self.completed.emit(0, 0)
    
    def cancel(self):
        """キャンセル要求"""
        self.cancel_requested = True
