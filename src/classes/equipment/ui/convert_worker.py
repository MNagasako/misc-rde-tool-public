"""
設備タブ - カタログ変換ワーカー

カタログ変換処理をバックグラウンドで実行するワーカースレッドです。
"""

import logging
from typing import Optional

from classes.equipment.util.output_paths import get_equipment_root_dir

logger = logging.getLogger(__name__)

try:
    from qt_compat.core import QThread, Signal
    PYSIDE6_AVAILABLE = True
except ImportError as e:
    PYSIDE6_AVAILABLE = False
    logger.error(f"Qt互換モジュールのインポートエラー: {e}")
    raise ImportError(f"Qt互換モジュールが必要です: {e}")


class CatalogConvertWorker(QThread):
    """カタログ変換ワーカースレッド
    
    CatalogConverterを呼び出し、変換処理を実行します。
    """
    
    # シグナル定義
    progress = Signal(str)  # ログメッセージ
    completed = Signal(bool, str)  # success, message
    results = Signal(dict)  # file_results
    
    def __init__(
        self,
        prefix: str,
        output_filename: str,
        create_backup: bool = True,
        create_entry_log: bool = True,
        parent=None
    ):
        super().__init__(parent)
        
        self.prefix = prefix
        self.output_filename = output_filename
        self.create_backup = create_backup
        self.create_entry_log = create_entry_log
    
    def run(self):
        """変換処理実行"""
        try:
            from classes.equipment.core.catalog_converter import CatalogConverter
            
            self.progress.emit(f"📂 OUTPUT_DIRを確認: {get_equipment_root_dir()}")
            
            # コンバータ初期化
            converter = CatalogConverter()
            
            self.progress.emit("🔍 Excelファイル検索中...")
            
            # Excelファイル取得
            excel_files = converter.get_excel_files(self.prefix)
            
            if not excel_files:
                self.completed.emit(False, f"Excelファイルが見つかりません（prefix: {self.prefix}）")
                return
            
            self.progress.emit(f"✅ {len(excel_files)} 個のExcelファイルを検出")
            for excel_file in excel_files:
                self.progress.emit(f"  - {excel_file}")
            
            self.progress.emit("🔄 変換処理開始...")
            
            # プログレスコールバック
            def progress_callback(current, total, message):
                self.progress.emit(f"[{current}/{total}] {message}")
            
            # 変換実行
            result = converter.convert_catalog_to_json(
                prefix=self.prefix,
                output_filename=self.output_filename,
                progress_callback=progress_callback
            )
            
            if not result.get('success'):
                self.completed.emit(False, result.get('error', '不明なエラー'))
                return
            
            self.progress.emit(f"✅ 変換完了: {result['output_path']}")
            self.progress.emit(f"📝 エントリーログ: {result['entry_path']}")
            self.progress.emit(f"💾 バックアップ: {result['backup_path']}")
            
            # 結果送信
            self.results.emit({
                'json_path': result['output_path'],
                'backup_dir': result.get('backup_path')
            })
            
            # 完了通知
            self.completed.emit(True, f"カタログ変換が完了しました。\n出力: {self.output_filename}")
        
        except Exception as e:
            logger.exception("カタログ変換エラー")
            self.progress.emit(f"❌ エラー: {str(e)}")
            self.completed.emit(False, f"変換処理でエラーが発生しました。\n{str(e)}")
