"""
報告書タブ - Excel変換ワーカー

Excel変換処理を実行するワーカースレッドです。
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


class ReportConvertWorker(QThread):
    """Excel変換ワーカースレッド"""
    
    progress_message = Signal(str)
    completed = Signal(bool, str)
    
    def __init__(self, input_path: str, output_path: str):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
    
    def run(self):
        """スレッド実行"""
        try:
            from classes.reports.core.report_converter import ReportConverter
            
            # コンバーター初期化
            self.progress_message.emit("ReportConverter初期化...")
            
            def progress_callback(message):
                self.progress_message.emit(message)
            
            converter = ReportConverter(progress_callback=progress_callback)
            
            # 変換実行
            self.progress_message.emit("変換処理開始...")
            result = converter.convert_report_data(
                input_path=self.input_path,
                output_path=self.output_path,
                resume=True
            )
            
            if result.success:
                self.completed.emit(
                    True, 
                    f"変換完了: {result.row_count}行処理\n出力: {result.output_path}"
                )
            else:
                self.completed.emit(False, result.error)
            
        except Exception as e:
            logger.error(f"変換ワーカーエラー: {e}", exc_info=True)
            self.completed.emit(False, f"エラー: {str(e)}")
