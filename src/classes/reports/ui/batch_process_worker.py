"""
報告書タブ - 一括処理ワーカー

データ取得→Excel変換→研究データ生成を一括で実行するワーカースレッドです。
"""

import os
import logging
from datetime import datetime

from classes.equipment.util.output_paths import get_equipment_root_dir
from classes.reports.util.output_paths import get_reports_root_dir

logger = logging.getLogger(__name__)

try:
    from qt_compat.core import QThread, Signal
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class ReportBatchWorker(QThread):
    """一括処理ワーカースレッド
    
    報告書データ取得→Excel変換→研究データ生成を自動で実行します。
    """
    
    # シグナル定義
    progress = Signal(int, int, str)  # current, total, message
    log_message = Signal(str)
    completed = Signal(dict)  # results
    error = Signal(str)
    
    def __init__(
        self,
        start_page: int,
        page_count: int,
        max_workers: int = 5,
        parent=None
    ):
        super().__init__(parent)
        
        self.start_page = start_page
        self.page_count = page_count
        self.max_workers = max_workers
        
        self.cancel_requested = False
    
    def run(self):
        """一括処理実行"""
        try:
            reports_dir = get_reports_root_dir()
            equipment_dir = get_equipment_root_dir()
            
            # ========================================
            # Step 1: 報告書データ取得
            # ========================================
            self.log_message.emit("=" * 60)
            self.log_message.emit("📊 Step 1/3: 報告書データ取得")
            self.log_message.emit("=" * 60)
            
            from classes.reports.core.parallel_fetcher import ParallelReportFetcher
            from classes.reports.core.report_data_processor import ReportDataProcessor
            from classes.reports.core.report_file_exporter import ReportFileExporter
            
            self.log_message.emit(f"🔄 {self.page_count}ページの報告書データを取得開始...")
            
            # 並列取得
            fetcher = ParallelReportFetcher(max_workers=self.max_workers)
            
            def fetch_progress_callback(current, total, message):
                """取得プログレスコールバック"""
                self.progress.emit(current, total, f"[取得] {message}")
                self.log_message.emit(f"[取得 {current}/{total}] {message}")
                return not self.cancel_requested
            
            success_data, error_data = fetcher.fetch_range(
                start_page=self.start_page,
                max_pages=self.page_count,
                progress_callback=fetch_progress_callback
            )
            
            success_count = len(success_data)
            error_count = len(error_data)
            
            self.log_message.emit(f"✅ 取得完了: 成功={success_count}, 失敗={error_count}")
            
            if not success_data:
                self.error.emit("報告書データの取得に失敗しました。")
                return
            
            # データ処理
            self.log_message.emit("🔄 データ処理中...")
            processor = ReportDataProcessor()
            valid_data, invalid_data = processor.process_batch(success_data)
            
            self.log_message.emit(f"✅ {len(valid_data)}件のデータを処理")
            
            # ファイル出力（ARIM-extracted2フォーマット）
            exporter = ReportFileExporter()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"ARIM-extracted2_{timestamp}"
            
            self.log_message.emit("📊 Excel/JSON出力中（バックアップ付き）...")
            file_results = exporter.export_with_backup(valid_data, base_filename)
            extracted_excel = file_results.get('latest_excel')
            latest_json = file_results.get('latest_json')
            
            self.log_message.emit(f"✅ Excel出力完了: {extracted_excel}")
            self.log_message.emit(f"✅ JSON出力完了: {latest_json}")
            
            # ========================================
            # Step 2: Excel変換
            # ========================================
            self.log_message.emit("")
            self.log_message.emit("=" * 60)
            self.log_message.emit("🔄 Step 2/3: Excel変換（ARIM-extracted2 → converted）")
            self.log_message.emit("=" * 60)
            
            from classes.reports.core.report_converter import ReportConverter
            
            converter = ReportConverter()
            converted_excel = reports_dir / "converted.xlsx"
            
            self.log_message.emit(f"🔄 変換開始: {os.path.basename(extracted_excel)} → converted.xlsx")
            
            def convert_progress_callback(current, total, message):
                """変換プログレスコールバック"""
                self.progress.emit(current, total, f"[変換] {message}")
                self.log_message.emit(f"[変換 {current}/{total}] {message}")
                return not self.cancel_requested
            
            result = converter.convert_report_data(
                input_path=extracted_excel,
                output_path=str(converted_excel)
            )
            
            if not result.success:
                self.error.emit(f"Excel変換エラー: {result.error}")
                return
            
            self.log_message.emit(f"✅ 変換完了: {converted_excel}")
            self.log_message.emit(f"  変換行数: {result.row_count}")
            
            # ========================================
            # Step 3: 研究データ生成
            # ========================================
            self.log_message.emit("")
            self.log_message.emit("=" * 60)
            self.log_message.emit("🔗 Step 3/3: 研究データ生成（設備別研究情報JSON）")
            self.log_message.emit("=" * 60)
            
            merged_json = equipment_dir / "merged_data2.json"
            output_json = reports_dir / "research_data.json"
            
            if not merged_json.exists():
                self.log_message.emit(f"⚠️ 設備データが見つかりません: {merged_json}")
                self.log_message.emit("⚠️ 研究データ生成をスキップします")
                self.log_message.emit("💡 設備タブで設備データ（merged_data2.json）を先に取得してください")
                output_json = None
            else:
                from classes.reports.core.research_data_generator import ResearchDataGenerator
                
                generator = ResearchDataGenerator()
                
                self.log_message.emit("🔄 研究データ生成開始...")
                
                result = generator.generate_research_data(
                    excel_path=str(converted_excel),  # 変換後のファイルを使用
                    merged_data_path=str(merged_json),
                    output_path=str(output_json)
                )
                
                if not result.success:
                    self.error.emit(f"研究データ生成エラー: {result.error}")
                    return
                
                self.log_message.emit(f"✅ 研究データ生成完了: {output_json}")
                self.log_message.emit(f"  設備数: {result.device_count}")
                self.log_message.emit(f"  報告書数: {result.research_count}")
            
            # ========================================
            # 完了
            # ========================================
            self.log_message.emit("")
            self.log_message.emit("=" * 60)
            self.log_message.emit("🎉 一括処理完了！")
            self.log_message.emit("=" * 60)
            
            # 結果送信
            results = {
                'success_count': success_count,
                'error_count': error_count,
                'output_excel': str(converted_excel),  # 変換後ファイル
                'output_json': str(output_json) if output_json else None
            }
            
            self.completed.emit(results)
        
        except Exception as e:
            logger.exception("一括処理エラー")
            self.log_message.emit(f"❌ エラー: {str(e)}")
            self.error.emit(str(e))
    
    def cancel(self):
        """キャンセル要求"""
        self.cancel_requested = True
