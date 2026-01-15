"""
設備機能 - Excel+JSONマージモジュール

Excel設備情報とJSON methodsデータをマージします。

"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

from classes.equipment.util.output_paths import (
    get_equipment_root_dir,
    get_equipment_backups_root,
    get_equipment_entries_dir,
)

logger = logging.getLogger(__name__)


class DataMerger:
    """
    Excel+JSONデータマージクラス
    
    Excel設備情報とJSON methodsデータをマージし、統合JSONを生成します。
    既存実装（arim-site/getFacilities/merge_excel_json_to_json.py）と互換性を保ちます。
    """
    
    def __init__(self):
        """初期化"""
        pass
    
    def merge_excel_json(
        self,
        excel_filename: str = "facilities_full.xlsx",
        json_filename: str = "fasi_ext.json",
        output_filename: str = "merged_data2.json",
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        ExcelデータとJSONデータをマージ
        
        Args:
            excel_filename: マージ元Excelファイル名
            json_filename: マージ元JSONファイル名（methodsデータ）
            output_filename: 出力JSONファイル名
            progress_callback: 進捗コールバック関数 callback(current, total, message)
        
        Returns:
            マージ結果情報（ファイルパス、件数など）
        """
        logger.info("データマージ開始")
        
        try:
            # 入出力パス設定
            output_dir = get_equipment_root_dir()
            xlsx_path = output_dir / excel_filename
            json_path = output_dir / json_filename
            output_path = output_dir / output_filename
            
            # プログレス通知
            if progress_callback:
                progress_callback(0, 3, "ファイル存在チェック中...")
            
            # ファイル存在チェック
            if not xlsx_path.exists():
                error_msg = f"Excelファイルが見つかりません: {xlsx_path}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            if not json_path.exists():
                error_msg = f"JSONファイルが見つかりません: {json_path}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            logger.info(f"処理中: Excel={xlsx_path}, JSON={json_path}")
            
            # プログレス通知
            if progress_callback:
                progress_callback(1, 3, "データ読み込み中...")
            
            # データ読み込み
            xlsx_df = pd.read_excel(str(xlsx_path))
            
            with json_path.open("r", encoding="utf-8") as json_file:
                json_data = json.load(json_file)
            
            logger.info(f"Excel行数: {len(xlsx_df)}, JSON件数: {len(json_data)}")
            
            # 空行除去とデータ型変換
            xlsx_df = xlsx_df.dropna(how='all')
            xlsx_df['設備ID'] = xlsx_df['設備ID'].astype(str)
            
            if 'code' in xlsx_df.columns:
                xlsx_df['code'] = xlsx_df['code'].astype(str)
            
            # Additional_Info_JSON列の初期化
            if 'Additional_Info_JSON' not in xlsx_df.columns:
                xlsx_df['Additional_Info_JSON'] = [{} for _ in range(len(xlsx_df))]
            
            # プログレス通知
            if progress_callback:
                progress_callback(2, 3, "データマージ中...")
            
            # メソッドデータのマージ
            methods_matched = 0
            
            def merge_methods(row):
                nonlocal methods_matched
                if row['設備ID'] in json_data:
                    if isinstance(row['Additional_Info_JSON'], str):
                        try:
                            row['Additional_Info_JSON'] = json.loads(row['Additional_Info_JSON'])
                        except:
                            row['Additional_Info_JSON'] = {}
                    
                    if not isinstance(row['Additional_Info_JSON'], dict):
                        row['Additional_Info_JSON'] = {}
                    
                    row['Additional_Info_JSON']['methods'] = json_data[row['設備ID']]['methods']
                    methods_matched += 1
                return row
            
            merged_df = xlsx_df.apply(merge_methods, axis=1)
            
            logger.info(f"マージ完了: {methods_matched} 件のメソッドデータを統合")
            
            # JSON形式で保存
            final_merged_json = merged_df.to_json(orient='records', force_ascii=False)
            
            with output_path.open('w', encoding='utf-8') as f:
                f.write(final_merged_json)
            
            logger.info(f"マージ結果保存: {output_path}")
            
            # JSONエントリー保存
            entry_data = {
                'source': 'excel_json_merge',
                'excel_source': excel_filename,
                'json_source': json_filename,
                'processed_at': datetime.now().isoformat(),
                'merged_count': len(merged_df),
                'methods_matched': methods_matched
            }
            
            json_entries_dir = get_equipment_entries_dir()
            entry_filename = f"merge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            entry_path = json_entries_dir / entry_filename
            
            with entry_path.open('w', encoding='utf-8') as f:
                json.dump(entry_data, f, ensure_ascii=False, indent=4)
            
            logger.info(f"マージログエントリー保存: {entry_path}")
            
            # バックアップ作成
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = get_equipment_backups_root() / timestamp
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / output_filename
            
            with backup_path.open('w', encoding='utf-8') as f:
                f.write(final_merged_json)
            
            logger.info(f"バックアップ作成: {backup_path}")
            
            # プログレス通知
            if progress_callback:
                progress_callback(3, 3, "マージ完了")
            
            return {
                'success': True,
                'output_path': output_path,
                'entry_path': entry_path,
                'backup_path': backup_path,
                'merged_count': len(merged_df),
                'methods_matched': methods_matched,
                'excel_source': excel_filename,
                'json_source': json_filename
            }
            
        except Exception as e:
            error_msg = f"データマージエラー: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'error': error_msg
            }
