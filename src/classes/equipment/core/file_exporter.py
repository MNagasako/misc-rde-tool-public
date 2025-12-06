"""
設備データ出力モジュール

Excel/JSON形式でのデータ出力機能を提供します。
v2.1.3: バックアップ機能追加
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import openpyxl
from openpyxl import Workbook

from classes.equipment.conf.field_definitions import EXCEL_COLUMNS
from classes.equipment.util.output_paths import (
    get_equipment_root_dir,
    get_equipment_backups_root,
)


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
            base_path = get_equipment_root_dir()
        else:
            base_path = Path(output_dir)
        base_path.mkdir(parents=True, exist_ok=True)

        self._output_path = base_path
        self.output_dir = str(base_path)
        logger.info("FacilityExporter初期化: output_dir=%s", self.output_dir)
    
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
        output_path = self._output_path / filename
        
        # ワークブック作成または読み込み
        if append and output_path.exists():
            logger.info("既存ファイルに追記: %s", output_path)
            wb = openpyxl.load_workbook(str(output_path))
            ws = wb.active
        else:
            logger.info("新規ファイル作成: %s", output_path)
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
            wb.save(str(output_path))
            logger.info("Excel保存成功: %s (%s件)", output_path, len(facilities))
        except PermissionError:
            # ファイルロック対策: 別名で保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            alt_filename = f"{Path(filename).stem}_{timestamp}.xlsx"
            alt_path = self._output_path / alt_filename
            wb.save(str(alt_path))
            logger.warning("ファイルロック検出、別名で保存: %s", alt_path)
            output_path = alt_path
        
        return str(output_path)
    
    def export_json(self, facilities: List[Dict[str, str]], 
                    filename: str = "facilities.json") -> str:
        """JSON形式で出力（全データ）
        
        Args:
            facilities: 設備データリスト
            filename: ファイル名
            
        Returns:
            str: 出力ファイルパス
        """
        output_path = self._output_path / filename
        
        # メタデータ付きJSON構造
        output_data = {
            "facilities": facilities,
            "count": len(facilities),
            "exported_at": datetime.now().isoformat()
        }
        
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info("JSON保存成功: %s (%s件)", output_path, len(facilities))
        return str(output_path)
    
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
            entries_dir = self._output_path / "json_entries"
        else:
            entries_dir = Path(entries_dir)
        
        entries_dir.mkdir(parents=True, exist_ok=True)
        
        saved_count = 0
        for facility in facilities:
            code = facility.get("code", "unknown")
            entry_filename = f"facility_{code}.json"
            entry_path = entries_dir / entry_filename
            
            # メタデータ付きエントリ（オリジナル実装と互換）
            entry = {
                "source": "web_scraping",
                "facility_id": code,
                "processed_at": datetime.now().isoformat(),
                "data": facility
            }
            
            with entry_path.open('w', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
            
            saved_count += 1
        
        logger.info("JSONエントリ保存完了: %s (%s件)", entries_dir, saved_count)
        return str(entries_dir)
    
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
        backup_dir = get_equipment_backups_root() / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        for source_file in source_files:
            source_path = Path(source_file)
            if source_path.exists():
                backup_path = backup_dir / source_path.name
                shutil.copy2(str(source_path), str(backup_path))
                logger.info("バックアップ作成: %s", backup_path)
        
        return str(backup_dir)
    
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
        logger.info("[完了] 最新版Excel: %s", latest_excel)
        
        latest_json = self.export_json(facilities, f"{base_filename}.json")
        results['latest_json'] = latest_json
        logger.info("[完了] 最新版JSON: %s", latest_json)
        
        # 2. バックアップディレクトリを作成（output/equipment/backups/YYYYMMDD_HHMMSS/）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = get_equipment_backups_root() / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        results['backup_dir'] = str(backup_dir)
        
        # 3. バックアップファイルを作成
        backup_excel = backup_dir / f"{base_filename}.xlsx"
        shutil.copy2(latest_excel, str(backup_excel))
        results['backup_excel'] = str(backup_excel)
        logger.info("バックアップ作成: %s", backup_excel)
        
        backup_json = backup_dir / f"{base_filename}.json"
        shutil.copy2(latest_json, str(backup_json))
        results['backup_json'] = str(backup_json)
        logger.info("バックアップ作成: %s", backup_json)
        
        logger.info("[完了] バックアップも作成されました: %s", backup_dir)
        
        return results

