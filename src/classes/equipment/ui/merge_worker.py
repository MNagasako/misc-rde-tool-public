"""
設備タブ - データマージワーカー

データマージ処理をバックグラウンドで実行するワーカースレッドです。
"""

import logging
from pathlib import Path
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


class DataMergeWorker(QThread):
    """データマージワーカースレッド
    
    DataMergerを呼び出し、マージ処理を実行します。
    """
    
    # シグナル定義
    progress = Signal(str)  # ログメッセージ
    completed = Signal(bool, str)  # success, message
    results = Signal(dict)  # file_results
    
    def __init__(
        self,
        excel_filename: str,
        json_filename: str,
        output_filename: str,
        create_backup: bool = True,
        create_entry_log: bool = True,
        parent=None
    ):
        super().__init__(parent)
        
        self.excel_filename = excel_filename
        self.json_filename = json_filename
        self.output_filename = output_filename
        self.create_backup = create_backup
        self.create_entry_log = create_entry_log
    
    def run(self):
        """マージ処理実行"""
        try:
            from classes.equipment.core.data_merger import DataMerger
            from pathlib import Path
            
            equipment_dir = get_equipment_root_dir()
            self.progress.emit(f"📂 OUTPUT_DIRを確認: {equipment_dir}")
            
            # マージャー初期化
            merger = DataMerger()
            
            self.progress.emit("🔍 入力ファイル確認中...")
            
            # ファイル存在確認
            facilities_dir = equipment_dir
            excel_path = facilities_dir / self.excel_filename
            json_path = facilities_dir / self.json_filename
            
            if not excel_path.exists():
                self.completed.emit(False, f"Excelファイルが見つかりません: {excel_path}")
                return
            
            if not json_path.exists():
                self.completed.emit(False, f"JSONファイルが見つかりません: {json_path}")
                return
            
            self.progress.emit(f"✅ Excelファイル: {self.excel_filename}")
            self.progress.emit(f"✅ JSONファイル: {self.json_filename}")
            
            self.progress.emit("🔄 マージ処理開始...")
            
            # プログレスコールバック
            def progress_callback(current, total, message):
                self.progress.emit(f"[{current}/{total}] {message}")
            
            # マージ実行
            result = merger.merge_excel_json(
                excel_filename=self.excel_filename,
                json_filename=self.json_filename,
                output_filename=self.output_filename,
                progress_callback=progress_callback
            )
            
            if not result.get('success'):
                self.completed.emit(False, result.get('error', '不明なエラー'))
                return
            
            self.progress.emit(f"✅ マージ完了: {result['output_path']}")
            self.progress.emit(f"📝 エントリーログ: {result['entry_path']}")
            self.progress.emit(f"💾 バックアップ: {result['backup_path']}")
            self.progress.emit(f"📊 統合件数: {result['merged_count']}, methods: {result['methods_matched']}")
            
            # 結果送信
            self.results.emit({
                'json_path': result['output_path'],
                'backup_dir': result.get('backup_path')
            })
            
            # 完了通知
            self.completed.emit(True, f"データマージが完了しました。\n出力: {self.output_filename}")
        
        except Exception as e:
            logger.exception("データマージエラー")
            self.progress.emit(f"❌ エラー: {str(e)}")
            self.completed.emit(False, f"マージ処理でエラーが発生しました。\n{str(e)}")
