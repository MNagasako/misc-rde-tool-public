"""
設備データ処理モジュール

取得した生データを加工・検証する機能を提供します。
"""

import logging
import re
from typing import Dict, List, Optional
from classes.equipment.conf.field_definitions import EXCEL_COLUMNS, DEFAULT_VALUES
from classes.equipment.util.name_parser import split_device_name_from_facility_name


logger = logging.getLogger(__name__)


class FacilityDataProcessor:
    """設備データ処理クラス
    
    生データの加工、検証、フォーマット変換を行います。
    """
    
    def __init__(self):
        """初期化"""
        logger.info("FacilityDataProcessor初期化")
    
    def process(self, raw_data: Dict[str, str]) -> Dict[str, str]:
        """設備データを処理
        
        Args:
            raw_data: 生データ辞書
            
        Returns:
            Dict[str, str]: 処理済みデータ辞書
        """
        processed = raw_data.copy()
        
        # 装置名の設定（日本語・英語）
        # 優先順位: 設備名称 > 型番
        source_name = processed.get("設備名称") or processed.get("型番", "")

        # 既存互換: 装置名列が空なら設備名称から生成
        if not processed.get("装置名_日") or not processed.get("装置名_英"):
            ja, en = split_device_name_from_facility_name(source_name)
            if not processed.get("装置名_日"):
                processed["装置名_日"] = ja
            if not processed.get("装置名_英"):
                processed["装置名_英"] = en
        
        # PREFIXの設定
        if "設備ID" in processed and processed["設備ID"]:
            if "PREFIX" not in processed or not processed["PREFIX"]:
                prefix_match = re.search(r'^[A-Za-z]*', processed["設備ID"])
                processed["PREFIX"] = prefix_match.group(0) if prefix_match else ""
        
        # デフォルト値の設定（空フィールドの補完）
        for field in EXCEL_COLUMNS:
            if field not in processed:
                processed[field] = DEFAULT_VALUES.get(field, "")
        
        return processed
    
    def validate(self, data: Dict[str, str]) -> bool:
        """データの妥当性を検証
        
        Args:
            data: 検証対象データ
            
        Returns:
            bool: 有効な場合True
        """
        # 必須フィールドのチェック
        if not data.get("設備ID"):
            logger.warning("検証失敗: 設備IDが空")
            return False
        
        if not data.get("code"):
            logger.warning("検証失敗: codeが空")
            return False
        
        return True
    
    def to_excel_row(self, data: Dict[str, str]) -> List[str]:
        """ExcelXX形式に変換
        
        Args:
            data: 設備データ辞書
            
        Returns:
            List[str]: Excel行データ（EXCEL_COLUMNSの順序）
        """
        row = []
        for column in EXCEL_COLUMNS:
            value = data.get(column, DEFAULT_VALUES.get(column, ""))
            row.append(value)
        return row
    
    def process_batch(self, raw_data_list: List[Dict[str, str]]) -> tuple[List[Dict[str, str]], List[Dict]]:
        """複数データの一括処理
        
        Args:
            raw_data_list: 生データのリスト
            
        Returns:
            tuple: (処理済みデータのリスト, エラー情報のリスト)
        """
        processed_list = []
        errors = []
        
        for index, raw_data in enumerate(raw_data_list):
            try:
                processed = self.process(raw_data)
                if self.validate(processed):
                    processed_list.append(processed)
                else:
                    error_info = {
                        "index": index,
                        "code": raw_data.get('code', 'N/A'),
                        "reason": "データ検証失敗"
                    }
                    errors.append(error_info)
                    logger.warning(f"データ検証失敗: {raw_data.get('code', 'N/A')}")
            except Exception as e:
                error_info = {
                    "index": index,
                    "code": raw_data.get('code', 'N/A'),
                    "reason": str(e)
                }
                errors.append(error_info)
                logger.error(f"データ処理エラー: {raw_data.get('code', 'N/A')} - {e}")
        
        logger.info(f"一括処理完了: {len(processed_list)}/{len(raw_data_list)}件 (エラー: {len(errors)}件)")
        return processed_list, errors
    
    def get_statistics(self, data_list: List[Dict[str, str]]) -> Dict[str, any]:
        """データ統計情報を取得
        
        Args:
            data_list: データリスト
            
        Returns:
            Dict: 統計情報
        """
        if not data_list:
            return {
                "total_count": 0,
                "prefix_distribution": {},
                "classification_distribution": {}
            }
        
        # PREFIX分布
        prefix_count = {}
        for data in data_list:
            prefix = data.get("PREFIX", "")
            if prefix:
                prefix_count[prefix] = prefix_count.get(prefix, 0) + 1
        
        # 分類分布
        classification_count = {}
        for data in data_list:
            classification = data.get("分類", "")
            if classification:
                classification_count[classification] = classification_count.get(classification, 0) + 1
        
        return {
            "total_count": len(data_list),
            "prefix_distribution": prefix_count,
            "classification_distribution": classification_count
        }
