"""
研究データ生成モジュール

設備別研究情報の生成処理。
変換済みExcelファイルと設備データJSONから研究データJSONを生成。
"""

import pandas as pd
import json
import os
import re
import math
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass


@dataclass
class ResearchDataResult:
    """研究データ生成結果"""
    success: bool
    output_path: Optional[str] = None
    device_count: int = 0
    research_count: int = 0
    summary: Dict[str, int] = None
    error: Optional[str] = None


class ResearchDataGenerator:
    """研究データ生成クラス
    
    変換済みExcelファイルと設備データJSONから設備別研究情報JSONを生成。
    """
    
    # 装置列定義
    DEVICE_COLUMNS = [
        '利用した主な設備1', '利用した主な設備2', '利用した主な設備3', 
        '利用した主な設備4', '利用した主な設備5'
    ]
    
    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            progress_callback: プログレスコールバック関数
        """
        self.progress_callback = progress_callback
    
    def _log(self, message: str):
        """ログ出力"""
        if self.progress_callback:
            self.progress_callback(message)
    
    @staticmethod
    def process_facility_code(code: Any) -> Any:
        """設備コードのクリーニング処理
        
        Args:
            code: 設備コード
            
        Returns:
            クリーニング後の設備コード（int/float/str/None）
        """
        if code is None:
            return None
        try:
            code_float = float(code)
            if code_float.is_integer():
                return int(code_float)
            else:
                return code_float
        except (ValueError, TypeError):
            return code
    
    @staticmethod
    def extract_device_id(device_str: Any) -> Optional[str]:
        """装置ID(アルファベット-数字部分)を抽出
        
        Args:
            device_str: 装置文字列
            
        Returns:
            装置ID（見つからない場合はNone）
        """
        if pd.isnull(device_str):
            return None
        match = re.search(r'[A-Za-z]+-\d+', str(device_str))
        return match.group() if match else None
    
    @staticmethod
    def extract_device_name(device_str: Any) -> Optional[str]:
        """装置名(装置ID:を除いた部分)を抽出
        
        Args:
            device_str: 装置文字列
            
        Returns:
            装置名（見つからない場合はNone）
        """
        if pd.isnull(device_str):
            return None
        match = re.search(r'：(.+)', str(device_str))
        return match.group(1).strip() if match else None
    
    def generate_research_data(
        self,
        excel_path: str,
        merged_data_path: str,
        output_path: str
    ) -> ResearchDataResult:
        """研究データの生成
        
        Args:
            excel_path: 変換済みExcelファイルパス
            merged_data_path: 設備データJSONファイルパス
            output_path: 出力JSONファイルパス
            
        Returns:
            ResearchDataResult
        """
        try:
            # ファイル存在確認
            if not os.path.exists(excel_path):
                return ResearchDataResult(
                    success=False,
                    error=f"Excelファイルが見つかりません: {excel_path}"
                )
            
            if not os.path.exists(merged_data_path):
                return ResearchDataResult(
                    success=False,
                    error=f"設備データファイルが見つかりません: {merged_data_path}"
                )
            
            self._log(f"処理中のExcelファイル: {excel_path}")
            self._log(f"使用する設備データ: {merged_data_path}")
            
            # データ読み込み
            df = pd.read_excel(excel_path)
            with open(merged_data_path, 'r', encoding='utf-8') as file:
                facility_codes = json.load(file)
            
            # 設備IDからcodeへのマッピング作成
            facility_code_mapping = {
                item['設備ID']: item['code'] 
                for item in facility_codes
            }
            
            # 装置IDごとに研究情報を格納する辞書
            device_research_dict = {}
            processed_count = 0
            
            # データ処理
            total_rows = len(df)
            for index, row in df.iterrows():
                # 進捗表示
                if index % 100 == 0:
                    progress_pct = (index / total_rows) * 100
                    self._log(f"処理中: {index}/{total_rows}行 ({progress_pct:.1f}%)")
                
                # コード、keyの取得
                code_value = row['コード']
                key_value = row['key']
                
                # NaN/infをNoneに変換
                if pd.isnull(code_value) or (
                    isinstance(code_value, float) and 
                    (math.isnan(code_value) or math.isinf(code_value))
                ):
                    code_value = None
                
                if pd.isnull(key_value) or (
                    isinstance(key_value, float) and 
                    (math.isnan(key_value) or math.isinf(key_value))
                ):
                    key_value = None
                
                # 研究情報オブジェクト作成
                research_info = {
                    "research_title": row['利用課題名'],
                    "ARIMNO": row['ARIMNO'],
                    "key": key_value,
                    "code": code_value,
                    "user_name": row['利用者名'],
                    "affiliation_name": row['所属名']
                }
                
                # 各装置列から情報抽出
                for col in self.DEVICE_COLUMNS:
                    device_id = self.extract_device_id(row[col])
                    device_name = self.extract_device_name(row[col])
                    
                    if device_id:
                        # 装置IDが新規の場合は初期化
                        if device_id not in device_research_dict:
                            device_research_dict[device_id] = {
                                "facility_name": device_name,
                                "facility_code": self.process_facility_code(
                                    facility_code_mapping.get(device_id)
                                ),
                                "data": []
                            }
                        
                        # 研究情報を追加
                        device_research_dict[device_id]["data"].append(research_info)
                        processed_count += 1
            
            self._log(
                f"処理完了: {len(device_research_dict)}個の設備に関して"
                f"{processed_count}件の研究情報を処理しました"
            )
            
            # JSON保存
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as json_file:
                json.dump(
                    device_research_dict, 
                    json_file, 
                    ensure_ascii=False, 
                    indent=4
                )
            
            self._log(f"研究データJSON生成完了: {output_path}")
            
            # サマリー作成
            summary = {
                device_id: len(info['data']) 
                for device_id, info in device_research_dict.items()
            }
            
            # サマリー表示
            self._log(f"設備数: {len(device_research_dict)}")
            self._log("カテゴリ別研究数:")
            for device_id, count in summary.items():
                self._log(f"  {device_id}: {count}")
            
            return ResearchDataResult(
                success=True,
                output_path=output_path,
                device_count=len(device_research_dict),
                research_count=processed_count,
                summary=summary
            )
            
        except Exception as e:
            return ResearchDataResult(
                success=False,
                error=f"研究データ生成エラー: {str(e)}"
            )
