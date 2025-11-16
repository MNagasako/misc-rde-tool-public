"""
報告書機能 - データ処理プロセッサ

報告書データの検証、クリーニング、フォーマット変換を担当します。

Version: 2.1.0
"""

import logging
from typing import Dict, List, Tuple
import re

from ..conf.field_definitions import EXCEL_COLUMNS


class ReportDataProcessor:
    """
    報告書データ処理プロセッサ
    
    取得した報告書データの検証、クリーニング、フォーマット統一を行います。
    """
    
    def __init__(self):
        """初期化"""
        self.logger = logging.getLogger(__name__)
        self.required_fields = EXCEL_COLUMNS
    
    def process_batch(
        self,
        raw_data: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        バッチデータを処理
        
        Args:
            raw_data: 生の報告書データのリスト
        
        Returns:
            (valid_data, invalid_data) のタプル
            - valid_data: 検証に合格したデータ
            - invalid_data: 検証に失敗したデータ（エラー情報付き）
        
        Examples:
            >>> processor = ReportDataProcessor()
            >>> valid, invalid = processor.process_batch(raw_reports)
            >>> print(f"成功: {len(valid)}, 失敗: {len(invalid)}")
        """
        valid_data = []
        invalid_data = []
        
        for idx, report in enumerate(raw_data):
            try:
                # 検証
                if not self.validate_report(report):
                    self.logger.warning(f"報告書 {idx} の検証失敗")
                    invalid_data.append({
                        "index": idx,
                        "data": report,
                        "error": "Validation failed"
                    })
                    continue
                
                # クリーニング
                cleaned_report = self.clean_report(report)
                
                # フォーマット統一
                formatted_report = self.format_report(cleaned_report)
                
                valid_data.append(formatted_report)
                
            except Exception as e:
                self.logger.error(f"報告書 {idx} の処理エラー: {e}", exc_info=True)
                invalid_data.append({
                    "index": idx,
                    "data": report,
                    "error": str(e)
                })
        
        self.logger.info(f"バッチ処理完了: 成功={len(valid_data)}, 失敗={len(invalid_data)}")
        return valid_data, invalid_data
    
    def validate_report(self, report: Dict) -> bool:
        """
        報告書データの検証
        
        Args:
            report: 報告書データ
        
        Returns:
            検証結果（True=合格、False=不合格）
        
        Note:
            必須フィールドの存在チェックと基本的なデータ型チェックを行います。
        """
        # 必須フィールドのチェック
        required_basic_fields = [
            "課題番号 / Project Issue Number",
            "利用課題名 / Title",
        ]
        
        for field in required_basic_fields:
            if field not in report:
                self.logger.warning(f"必須フィールド欠如: {field}")
                return False
            
            # 空文字列でないことを確認
            value = report[field]
            if not value or (isinstance(value, str) and not value.strip()):
                self.logger.warning(f"必須フィールドが空: {field}")
                return False
        
        # code/keyの存在チェック
        if 'code' not in report or 'key' not in report:
            self.logger.warning("code または key が欠如")
            return False
        
        return True
    
    def clean_report(self, report: Dict) -> Dict:
        """
        報告書データのクリーニング
        
        Args:
            report: 生の報告書データ
        
        Returns:
            クリーニング済み報告書データ
        
        Note:
            テキストの前後空白除去、改行正規化などを行います。
        """
        cleaned = {}
        
        for field, value in report.items():
            if isinstance(value, str):
                # テキストフィールドのクリーニング
                cleaned[field] = self.clean_text(value)
            elif isinstance(value, list):
                # リストフィールドのクリーニング
                cleaned[field] = [self.clean_text(str(item)) for item in value if item]
            else:
                # その他（そのまま）
                cleaned[field] = value
        
        return cleaned
    
    def clean_text(self, text: str) -> str:
        """
        テキストのクリーニング
        
        Args:
            text: クリーニング対象のテキスト
        
        Returns:
            クリーニング済みテキスト
        
        Note:
            - 前後の空白除去
            - 連続する空白を1つに
            - 不要な改行の除去
        """
        if not text:
            return ""
        
        # 前後の空白除去
        text = text.strip()
        
        # 連続する空白を1つに（改行は保持）
        text = re.sub(r'[ \t]+', ' ', text)
        
        # 3つ以上の連続する改行を2つに
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text
    
    def format_report(self, report: Dict) -> Dict:
        """
        報告書データのフォーマット統一
        
        Args:
            report: クリーニング済み報告書データ
        
        Returns:
            フォーマット統一済み報告書データ
        
        Note:
            Excel出力用に全フィールドを確実に存在させます。
            欠けているフィールドは空文字列で補完します。
        """
        formatted = {}
        
        # 全EXCEL_COLUMNSフィールドを確実に存在させる
        for field in self.required_fields:
            if field in report:
                value = report[field]
                
                # リストは文字列に変換
                if isinstance(value, list):
                    formatted[field] = ", ".join(value) if value else ""
                else:
                    formatted[field] = value
            else:
                # 欠けているフィールドは空文字列
                formatted[field] = ""
        
        return formatted
    
    def validate_batch(self, reports: List[Dict]) -> Tuple[int, int]:
        """
        バッチデータの簡易検証
        
        Args:
            reports: 報告書データのリスト
        
        Returns:
            (合格数, 不合格数) のタプル
        
        Note:
            実際の処理は行わず、検証結果の統計のみを返します。
        """
        valid_count = 0
        invalid_count = 0
        
        for report in reports:
            if self.validate_report(report):
                valid_count += 1
            else:
                invalid_count += 1
        
        return valid_count, invalid_count
