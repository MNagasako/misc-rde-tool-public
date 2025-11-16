"""
設備機能 - Excelカタログ→JSON変換モジュール

ARIMカタログExcelファイルをJSON形式に変換します。

Version: 2.1.0
"""

import json
import glob
import pandas as pd
import re
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from config.common import OUTPUT_DIR, CONFIG_DIR

logger = logging.getLogger(__name__)


class CatalogConverter:
    """
    Excelカタログ→JSON変換クラス
    
    ARIMカタログExcelファイルを読み込み、JSON形式に変換します。
    既存実装（arim-site/getFacilities/excel_catalog_to_json.py）と互換性を保ちます。
    """
    
    # 有効な登録番号の正規表現パターン (例: AA-123)
    VALID_REG_NO_PATTERN = re.compile(r'^[A-Z]{2}-\d+$')
    
    # シンボル→整数変換テーブル
    SYMBOL_CONVERSION = {'◎': 1, '○': 2, '△': 3, '＊': 4, '?': 5, '': 0}
    
    def __init__(self):
        """初期化"""
        self.sheet_name_translation = {}
        self.measurement_methods_translation = {}
        self._load_translation_files()
    
    def _load_translation_files(self):
        """翻訳ファイルをロード"""
        try:
            # 翻訳ファイルパス
            sheet_name_path = os.path.join(CONFIG_DIR, 'facilities', 'sheet_name_translation.json')
            measurement_methods_path = os.path.join(CONFIG_DIR, 'facilities', 'measurement_methods_translation.json')
            
            # 翻訳ファイル読み込み
            if os.path.exists(sheet_name_path):
                with open(sheet_name_path, 'r', encoding='utf-8') as f:
                    self.sheet_name_translation = json.load(f)
                logger.info(f"シート名翻訳ファイル読み込み: {len(self.sheet_name_translation)} 件")
            else:
                logger.warning(f"翻訳ファイルが見つかりません: {sheet_name_path}")
            
            if os.path.exists(measurement_methods_path):
                with open(measurement_methods_path, 'r', encoding='utf-8') as f:
                    self.measurement_methods_translation = json.load(f)
                logger.info(f"測定方法翻訳ファイル読み込み: {len(self.measurement_methods_translation)} 件")
            else:
                logger.warning(f"翻訳ファイルが見つかりません: {measurement_methods_path}")
                
        except Exception as e:
            logger.error(f"翻訳ファイル読み込みエラー: {e}", exc_info=True)
    
    def symbol_to_int(self, symbol: Any) -> int:
        """
        シンボルを整数に変換
        
        Args:
            symbol: 変換するシンボル（◎、○、△、＊、?、空文字）
        
        Returns:
            変換後の整数値（0-5）
        """
        return self.SYMBOL_CONVERSION.get(str(symbol), 0)
    
    def get_excel_files(self, prefix: str) -> List[str]:
        """
        指定プレフィックスのExcelファイルを検索
        
        Args:
            prefix: ファイル名のプレフィックス（例: "ARIM計測装置カタログ"）
        
        Returns:
            見つかったExcelファイルのパスリスト
        """
        # config/facilities/ディレクトリ内で検索
        facilities_config_dir = os.path.join(CONFIG_DIR, 'facilities')
        search_path = os.path.join(facilities_config_dir, f'{prefix}*.xlsx')
        files = glob.glob(search_path)
        
        if files:
            logger.info(f"Excelファイル検索: {len(files)} 件見つかりました")
            return [files[0]]  # 最初の1ファイルのみ
        else:
            logger.warning(f"プレフィックス '{prefix}' にマッチするExcelファイルが見つかりません")
            return []
    
    def process_sheet(
        self,
        excel_path: str,
        sheet: str
    ) -> Dict[str, Any]:
        """
        単一シートを処理
        
        Args:
            excel_path: Excelファイルパス
            sheet: シート名
        
        Returns:
            処理結果（登録番号をキーとする辞書）
        """
        result_data = {}
        
        try:
            # Excelシート読み込み
            df = pd.read_excel(excel_path, sheet_name=sheet, skiprows=1).fillna('')
            sheet_name_translated = self.sheet_name_translation.get(sheet, sheet)
            
            # シート名から方法カテゴリ番号を抽出（例: "8.透過電子顕微鏡解析" → 8）
            match = re.search(r'^(\d+)', sheet)
            if not match:
                logger.warning(f"シート名から番号抽出失敗: {sheet}")
                return {}
            
            method_category_number = match.group(1)
            logger.info(f"シート処理開始: {sheet} (カテゴリ番号: {method_category_number})")
            
            # 各行を処理
            for index, row in df.iterrows():
                reg_no = str(row.iloc[1])
                
                # 有効な登録番号のみ処理
                if not self.VALID_REG_NO_PATTERN.match(reg_no):
                    continue
                
                logger.debug(f"処理中: {reg_no} in sheet {sheet}")
                
                # 登録番号ごとのデータ初期化
                if reg_no not in result_data:
                    result_data[reg_no] = {
                        'type': row.iloc[2],
                        'methods': {},
                        'remarks': str(row.iloc[-1])
                    }
                else:
                    # 備考欄の追記
                    if row.iloc[-1]:
                        result_data[reg_no]['remarks'] += '; ' + str(row.iloc[-1])
                
                # メソッドデータ抽出
                method_data = {}
                
                for col_index, method in enumerate(df.columns[3:-2]):
                    # 翻訳キーを取得
                    method_translated_key = next(
                        (k for k, v in self.measurement_methods_translation.items()
                         if v == method and (k.startswith(f"e_{method_category_number}")
                                            or k.startswith(f"_group_{method_category_number}"))),
                        method
                    )
                    
                    logger.debug(f"メソッド処理: {method} → {method_translated_key}")
                    
                    # Unnamed列はスキップ
                    if 'Unnamed:' in method_translated_key:
                        continue
                    
                    # グループまたは個別メソッドの場合
                    if (method_translated_key.startswith(f"_group_{method_category_number}") or
                        method_translated_key.startswith(f"e_{method_category_number}")):
                        
                        if method == "その他 特記事項":
                            # 特記事項は備考欄に追記
                            result_data[reg_no]['remarks'] += '; ' + str(row.iloc[col_index + 3])
                        else:
                            # シンボルを整数に変換して保存
                            method_data[method_translated_key] = self.symbol_to_int(row.iloc[col_index + 3])
                
                # メソッドデータを保存
                result_data[reg_no]['methods'][sheet_name_translated] = method_data
            
            logger.info(f"シート処理完了: {sheet} ({len(result_data)} 件)")
            
        except Exception as e:
            logger.error(f"シート処理エラー ({sheet}): {e}", exc_info=True)
        
        return result_data
    
    def convert_catalog_to_json(
        self,
        prefix: str = "ARIM計測装置カタログ",
        output_filename: str = "fasi_ext.json",
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Excelカタログを読み込んでJSON形式に変換
        
        Args:
            prefix: Excelファイルのプレフィックス
            output_filename: 出力JSONファイル名
            progress_callback: 進捗コールバック関数 callback(current, total, message)
        
        Returns:
            変換結果情報（ファイルパス、件数など）
        """
        logger.info(f"カタログ変換開始: prefix='{prefix}'")
        
        try:
            # Excelファイル検索
            excel_files = self.get_excel_files(prefix)
            
            if not excel_files:
                error_msg = f"プレフィックス '{prefix}' にマッチするExcelファイルが見つかりません"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            excel_path = excel_files[0]
            logger.info(f"処理中のExcelファイル: {excel_path}")
            
            # プログレス通知
            if progress_callback:
                progress_callback(0, 0, f"Excelファイル読み込み中: {os.path.basename(excel_path)}")
            
            # 全シートを処理
            final_json = {}
            xls = pd.ExcelFile(excel_path)
            sheet_names = xls.sheet_names
            total_sheets = len(sheet_names)
            
            logger.info(f"シート数: {total_sheets}")
            
            for idx, sheet in enumerate(sheet_names):
                if progress_callback:
                    progress_callback(idx, total_sheets, f"シート処理中: {sheet}")
                
                sheet_data = self.process_sheet(excel_path, sheet)
                final_json.update(sheet_data)
            
            # 出力パス設定
            output_dir = os.path.join(OUTPUT_DIR, 'arim-site', 'facilities')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, output_filename)
            
            # JSONファイル保存
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(final_json, f, ensure_ascii=False, indent=4)
            
            logger.info(f"JSON出力完了: {output_path}")
            
            # エントリーデータ作成
            entry_data = {
                'source': 'excel_catalog',
                'source_file': os.path.basename(excel_path),
                'processed_at': datetime.now().isoformat(),
                'data': final_json,
                'sheet_count': total_sheets,
                'entry_count': len(final_json)
            }
            
            # JSONエントリー保存
            json_entries_dir = os.path.join(output_dir, 'json_entries')
            os.makedirs(json_entries_dir, exist_ok=True)
            entry_filename = f"catalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            entry_path = os.path.join(json_entries_dir, entry_filename)
            
            with open(entry_path, 'w', encoding='utf-8') as f:
                json.dump(entry_data, f, ensure_ascii=False, indent=4)
            
            logger.info(f"JSONエントリー保存: {entry_path}")
            
            # バックアップ作成
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = os.path.join(OUTPUT_DIR, 'arim-site', 'facilities', 'backups', timestamp)
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, output_filename)
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(final_json, f, ensure_ascii=False, indent=4)
            
            logger.info(f"バックアップ作成: {backup_path}")
            
            # 完了通知
            if progress_callback:
                progress_callback(total_sheets, total_sheets, "変換完了")
            
            return {
                'success': True,
                'output_path': output_path,
                'entry_path': entry_path,
                'backup_path': backup_path,
                'sheet_count': total_sheets,
                'entry_count': len(final_json)
            }
            
        except Exception as e:
            error_msg = f"カタログ変換エラー: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'error': error_msg
            }
