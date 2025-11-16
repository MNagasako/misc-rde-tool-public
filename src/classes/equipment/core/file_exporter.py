"""
設備データ出力モジュール

Excel/JSON形式でのデータ出力機能を提供します。
v2.1.3: バックアップ機能追加
"""

import os
import json
import logging
import shutil
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import openpyxl
from openpyxl import Workbook
from classes.equipment.conf.field_definitions import EXCEL_COLUMNS
from config.common import OUTPUT_DIR


logger = logging.getLogger(__name__)


class FacilityExporter:
    """設備データ出力クラス
    
    Excel/JSON形式でデータを出力します。
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        """初期化
        
        Args:
            output_dir: 出力ディレクトリパス（Noneの場合はデフォルト）
        """
        if output_dir is None:
            # デフォルトはOUTPUT_DIR/arim-site/equipment
            output_dir = os.path.join(OUTPUT_DIR, "arim-site", "equipment")
        
        # ディレクトリが存在しなければ作成
        os.makedirs(output_dir, exist_ok=True)
        
        self.output_dir = output_dir
        logger.info(f"FacilityExporter初期化: output_dir={output_dir}")
    
    def export_excel(self, facilities: List[Dict[str, str]], 
                     filename: str = "facilities.xlsx",
                     append: bool = False) -> str:
        """Excel形式で出力
        
        Args:
            facilities: 設備データリスト
            filename: ファイル名
            append: Trueの場合は既存ファイルに追記
            
        Returns:
            str: 出力ファイルパス
        """
        output_path = os.path.join(self.output_dir, filename)
        
        # ワークブック作成または読み込み
        if append and os.path.exists(output_path):
            logger.info(f"既存ファイルに追記: {output_path}")
            wb = openpyxl.load_workbook(output_path)
            ws = wb.active
        else:
            logger.info(f"新規ファイル作成: {output_path}")
            wb = Workbook()
            ws = wb.active
            # ヘッダー行を追加
            ws.append(EXCEL_COLUMNS)
        
        # データ行を追加
        for facility in facilities:
            row = [facility.get(col, "") for col in EXCEL_COLUMNS]
            ws.append(row)
        
        # 保存
        try:
            wb.save(output_path)
            logger.info(f"Excel保存成功: {output_path} ({len(facilities)}件)")
        except PermissionError:
            # ファイルロック対策: 別名で保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            alt_filename = f"{os.path.splitext(filename)[0]}_{timestamp}.xlsx"
            alt_path = os.path.join(self.output_dir, alt_filename)
            wb.save(alt_path)
            logger.warning(f"ファイルロック検出、別名で保存: {alt_path}")
            output_path = alt_path
        
        return output_path
    
    def export_json(self, facilities: List[Dict[str, str]], 
                    filename: str = "facilities.json") -> str:
        """JSON形式で出力（全データ）
        
        Args:
            facilities: 設備データリスト
            filename: ファイル名
            
        Returns:
            str: 出力ファイルパス
        """
        output_path = os.path.join(self.output_dir, filename)
        
        # メタデータ付きJSON構造
        output_data = {
            "facilities": facilities,
            "count": len(facilities),
            "exported_at": datetime.now().isoformat()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON保存成功: {output_path} ({len(facilities)}件)")
        return output_path
    
    def export_json_entries(self, facilities: List[Dict[str, str]], 
                           entries_dir: Optional[str] = None) -> str:
        """JSON形式で個別エントリ出力
        
        Args:
            facilities: 設備データリスト
            entries_dir: エントリ保存ディレクトリ（Noneの場合はデフォルト）
            
        Returns:
            str: 出力ディレクトリパス
        """
        if entries_dir is None:
            entries_dir = os.path.join(self.output_dir, "json_entries")
        
        os.makedirs(entries_dir, exist_ok=True)
        
        saved_count = 0
        for facility in facilities:
            code = facility.get("code", "unknown")
            entry_filename = f"facility_{code}.json"
            entry_path = os.path.join(entries_dir, entry_filename)
            
            # メタデータ付きエントリ（オリジナル実装と互換）
            entry = {
                "source": "web_scraping",
                "facility_id": code,
                "processed_at": datetime.now().isoformat(),
                "data": facility
            }
            
            with open(entry_path, 'w', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            
            saved_count += 1
        
        logger.info(f"JSONエントリ保存完了: {entries_dir} ({saved_count}件)")
        return entries_dir
    
    def export_all_formats(self, facilities: List[Dict[str, str]], 
                          base_filename: str = "facilities") -> Dict[str, str]:
        """全形式で一括出力
        
        Args:
            facilities: 設備データリスト
            base_filename: ベースファイル名
            
        Returns:
            Dict[str, str]: 出力ファイルパスの辞書
        """
        results = {}
        
        # Excel出力
        excel_path = self.export_excel(facilities, f"{base_filename}.xlsx")
        results["excel"] = excel_path
        
        # JSON出力
        json_path = self.export_json(facilities, f"{base_filename}.json")
        results["json"] = json_path
        
        # JSONエントリ出力
        entries_dir = self.export_json_entries(facilities)
        results["json_entries"] = entries_dir
        
        logger.info(f"全形式出力完了: Excel={excel_path}, JSON={json_path}, Entries={entries_dir}")
        return results
    
    def create_backup(self, source_files: List[str]) -> str:
        """バックアップディレクトリを作成
        
        Args:
            source_files: バックアップ対象ファイルリスト
            
        Returns:
            str: バックアップディレクトリパス
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(
            os.path.dirname(self.output_dir),
            "backups",
            timestamp
        )
        os.makedirs(backup_dir, exist_ok=True)
        
        import shutil
        for source_file in source_files:
            if os.path.exists(source_file):
                filename = os.path.basename(source_file)
                backup_path = os.path.join(backup_dir, filename)
                shutil.copy2(source_file, backup_path)
                logger.info(f"バックアップ作成: {backup_path}")
        
        return backup_dir
    
    def export_with_backup(self, facilities: List[Dict[str, str]], 
                          base_filename: str = "facilities_full") -> Dict[str, str]:
        """最新版とバックアップの両方を作成
        
        Args:
            facilities: 設備データリスト
            base_filename: ベースファイル名（拡張子なし）
            
        Returns:
            dict: 作成されたファイルパス情報
                - latest_excel: 最新版Excelパス
                - latest_json: 最新版JSONパス  
                - backup_dir: バックアップディレクトリパス
                - backup_excel: バックアップExcelパス
                - backup_json: バックアップJSONパス
        """
        results = {}
        
        # 1. 最新版を作成（output/equipment/facilities/）
        latest_excel = self.export_excel(facilities, f"{base_filename}.xlsx")
        results['latest_excel'] = latest_excel
        logger.info(f"[完了] 最新版Excel: {latest_excel}")
        
        latest_json = self.export_json(facilities, f"{base_filename}.json")
        results['latest_json'] = latest_json
        logger.info(f"[完了] 最新版JSON: {latest_json}")
        
        # 2. バックアップディレクトリを作成（output/equipment/backups/YYYYMMDD_HHMMSS/）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(
            os.path.dirname(self.output_dir),
            "backups",
            timestamp
        )
        os.makedirs(backup_dir, exist_ok=True)
        results['backup_dir'] = backup_dir
        
        # 3. バックアップファイルを作成
        backup_excel = os.path.join(backup_dir, f"{base_filename}.xlsx")
        shutil.copy2(latest_excel, backup_excel)
        results['backup_excel'] = backup_excel
        logger.info(f"バックアップ作成: {backup_excel}")
        
        backup_json = os.path.join(backup_dir, f"{base_filename}.json")
        shutil.copy2(latest_json, backup_json)
        results['backup_json'] = backup_json
        logger.info(f"バックアップ作成: {backup_json}")
        
        logger.info(f"[完了] バックアップも作成されました: {backup_dir}")
        
        return results

