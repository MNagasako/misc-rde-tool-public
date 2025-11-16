"""
報告書タブ - 研究データ生成ワーカー

研究データ生成処理を実行するワーカースレッドです。
"""

import logging

logger = logging.getLogger(__name__)

try:
    from qt_compat.core import QThread, Signal
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class ResearchDataWorker(QThread):
    """研究データ生成ワーカースレッド"""
    
    progress_message = Signal(str)
    completed = Signal(bool, str, dict)
    
    def __init__(self, excel_path: str, merged_data_path: str, output_path: str):
        super().__init__()
        self.excel_path = excel_path
        self.merged_data_path = merged_data_path
        self.output_path = output_path
    
    def run(self):
        """スレッド実行"""
        try:
            from classes.reports.core.research_data_generator import ResearchDataGenerator
            
            # ジェネレーター初期化
            self.progress_message.emit("ResearchDataGenerator初期化...")
            
            def progress_callback(message):
                self.progress_message.emit(message)
            
            generator = ResearchDataGenerator(progress_callback=progress_callback)
            
            # 生成実行
            self.progress_message.emit("研究データ生成処理開始...")
            result = generator.generate_research_data(
                excel_path=self.excel_path,
                merged_data_path=self.merged_data_path,
                output_path=self.output_path
            )
            
            if result.success:
                summary = {
                    'device_count': result.device_count,
                    'research_count': result.research_count,
                    'summary': result.summary or {}
                }
                self.completed.emit(
                    True, 
                    f"生成完了: {result.device_count}設備、{result.research_count}件の研究情報\n出力: {result.output_path}",
                    summary
                )
            else:
                self.completed.emit(False, result.error, {})
            
        except Exception as e:
            logger.error(f"研究データ生成ワーカーエラー: {e}", exc_info=True)
            self.completed.emit(False, f"エラー: {str(e)}", {})
