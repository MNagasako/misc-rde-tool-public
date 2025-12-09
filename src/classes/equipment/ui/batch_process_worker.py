"""
設備タブ - 一括処理ワーカー

データ取得→カタログ変換→データマージを一括で実行するワーカースレッドです。
"""

import logging
from typing import Optional
from datetime import datetime
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


class BatchProcessWorker(QThread):
    """一括処理ワーカースレッド
    
    設備データ取得→カタログ変換→データマージを自動で実行します。
    """
    
    # シグナル定義
    progress = Signal(int, int, str)  # current, total, message
    completed = Signal(bool, str)  # success, message
    log_message = Signal(str)
    results = Signal(dict)  # file_results
    
    def __init__(
        self,
        start_id: int,
        end_id: int,
        max_workers: int = 5,
        fetch_all: bool = False,
        consecutive_not_found_limit: Optional[int] = None,
        fetch_all_chunk_size: Optional[int] = None,
        parent=None
    ):
        super().__init__(parent)
        
        self.start_id = start_id
        self.end_id = end_id
        self.max_workers = max_workers
        self.fetch_all = fetch_all
        self.consecutive_not_found_limit = consecutive_not_found_limit
        self.fetch_all_chunk_size = fetch_all_chunk_size
        
        self.cancel_requested = False
    
    def run(self):
        """一括処理実行"""
        try:
            # ========================================
            # Step 1: 設備データ取得
            # ========================================
            self.log_message.emit("=" * 60)
            self.log_message.emit("📊 Step 1/3: 設備データ取得")
            self.log_message.emit("=" * 60)
            
            from classes.equipment.core.parallel_fetcher import ParallelFacilityFetcher
            from classes.equipment.core.data_processor import FacilityDataProcessor
            from classes.equipment.core.file_exporter import FacilityExporter
            
            # 取得範囲生成
            if (
                self.fetch_all
                and self.consecutive_not_found_limit
                and self.fetch_all_chunk_size
            ):
                facility_ids = collect_valid_facility_ids(
                    start_id=self.start_id,
                    end_id=self.end_id,
                    chunk_size=self.fetch_all_chunk_size,
                    stop_threshold=self.consecutive_not_found_limit,
                    log_callback=self.log_message.emit,
                    cancel_checker=lambda: self.cancel_requested,
                    listing_scraper=FacilityListingScraper()
                )
            else:
                facility_ids = list(range(self.start_id, self.end_id + 1))

            if not facility_ids:
                self.log_message.emit("⚠ 取得する設備IDがありません")
                self.completed.emit(False, "取得対象が見つかりませんでした。")
                return

            total_count = len(facility_ids)
            self.log_message.emit(f"🔄 {total_count}件の設備データを取得開始...")
            
            # 並列取得
            fetcher = ParallelFacilityFetcher(max_workers=self.max_workers)
            
            def fetch_progress_callback(current, total, message):
                """取得プログレスコールバック"""
                self.progress.emit(current, total, f"[取得] {message}")
                self.log_message.emit(f"[取得 {current}/{total}] {message}")
                return not self.cancel_requested
            
            success_data, error_info = fetcher.fetch_facilities_with_results(
                facility_ids=facility_ids,
                progress_callback=fetch_progress_callback
            )
            
            success_count = len(success_data)
            error_count = len(error_info)
            
            self.log_message.emit(f"✅ 取得完了: 成功={success_count}, 失敗={error_count}")
            
            if not success_data:
                self.completed.emit(False, "設備データの取得に失敗しました。")
                return
            
            # データ処理
            self.log_message.emit("🔄 データ処理中...")
            processor = FacilityDataProcessor()
            processed_data, process_errors = processor.process_batch(success_data)
            
            self.log_message.emit(f"✅ {len(processed_data)}件のデータを処理")
            
            # ファイル出力
            exporter = FacilityExporter()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"facilities_{timestamp}"
            
            self.log_message.emit("📊📄 Excel/JSON出力中（バックアップ付き）...")
            file_results = exporter.export_with_backup(processed_data, base_filename)
            latest_excel = file_results.get('latest_excel')
            latest_json = file_results.get('latest_json')
            backup_dir = file_results.get('backup_dir')
            
            self.log_message.emit(f"✅ Excel出力完了: {latest_excel}")
            self.log_message.emit(f"✅ JSON出力完了: {latest_json}")
            
            # facilities_full.xlsx としてもコピー（マージ用）
            import shutil
            import os
            facilities_full_path = os.path.join(os.path.dirname(latest_excel), "facilities_full.xlsx")
            shutil.copy2(latest_excel, facilities_full_path)
            self.log_message.emit(f"📋 facilities_full.xlsx を作成: {facilities_full_path}")
            
            # ========================================
            # Step 2: カタログ変換
            # ========================================
            self.log_message.emit("=" * 60)
            self.log_message.emit("🔄 Step 2/3: カタログ変換（Excel→JSON）")
            self.log_message.emit("=" * 60)
            
            from classes.equipment.core.catalog_converter import CatalogConverter
            
            converter = CatalogConverter()
            
            def convert_progress_callback(current, total, message):
                """変換プログレスコールバック"""
                self.log_message.emit(f"[変換 {current}/{total}] {message}")
            
            result_convert = converter.convert_catalog_to_json(
                prefix="ARIM 計測装置カタログ",
                output_filename="fasi_ext.json",
                progress_callback=convert_progress_callback
            )
            
            if not result_convert.get('success'):
                self.log_message.emit(f"⚠ カタログ変換スキップ: {result_convert.get('error')}")
            else:
                self.log_message.emit(f"✅ カタログ変換完了: {result_convert['output_path']}")
            
            # ========================================
            # Step 3: データマージ
            # ========================================
            self.log_message.emit("=" * 60)
            self.log_message.emit("🔗 Step 3/3: データマージ（Excel+JSON）")
            self.log_message.emit("=" * 60)
            
            from classes.equipment.core.data_merger import DataMerger
            
            merger = DataMerger()
            
            def merge_progress_callback(current, total, message):
                """マージプログレスコールバック"""
                self.log_message.emit(f"[マージ {current}/{total}] {message}")
            
            result_merge = merger.merge_excel_json(
                excel_filename="facilities_full.xlsx",
                json_filename="fasi_ext.json",
                output_filename="merged_data2.json",
                progress_callback=merge_progress_callback
            )
            
            if not result_merge.get('success'):
                self.log_message.emit(f"⚠ データマージスキップ: {result_merge.get('error')}")
            else:
                self.log_message.emit(f"✅ データマージ完了: {result_merge['output_path']}")
                self.log_message.emit(f"📊 統合件数: {result_merge['merged_count']}, methods: {result_merge['methods_matched']}")
            
            # ========================================
            # 完了
            # ========================================
            
            # 結果送信
            self.results.emit({
                'latest_excel': latest_excel,
                'latest_json': latest_json,
                'backup_dir': backup_dir
            })
            
            # 完了通知
            summary = (
                f"設備データ取得: 成功={success_count}, 失敗={error_count}\n"
                f"カタログ変換: {'✅ 完了' if result_convert.get('success') else '⚠ スキップ'}\n"
                f"データマージ: {'✅ 完了' if result_merge.get('success') else '⚠ スキップ'}"
            )
            self.completed.emit(True, summary)
        
        except Exception as e:
            logger.exception("一括処理エラー")
            self.log_message.emit(f"❌ エラー: {str(e)}")
            self.completed.emit(False, str(e))
    
    def cancel(self):
        """キャンセル要求"""
        self.cancel_requested = True
