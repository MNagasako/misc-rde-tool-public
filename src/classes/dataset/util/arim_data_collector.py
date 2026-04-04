"""
ARIM課題データ取得機能
データセットAI機能向けのARIM課題データ（実験データ・拡張情報・実験データ）取得
"""

import os
import json
from typing import Dict, List, Optional, Any, Tuple
from config.common import get_dynamic_file_path
from classes.utils.excel_records import ensure_alias_column, get_record_headers, load_excel_records

import logging

# ロガー設定
logger = logging.getLogger(__name__)


class ARIMDataCollector:
    """ARIM課題データ収集クラス"""
    
    def __init__(self):
        self.cache = {}
        self.arim_extension_data = None
        
    def collect_arim_data_by_grant_number(self, grant_number: str) -> Dict[str, Any]:
        """
        課題番号からARIMデータを包括的に収集
        
        Args:
            grant_number: 課題番号
            
        Returns:
            収集されたARIMデータ（既存情報・拡張情報・実験データ）
        """
        result = {
            'grant_number': grant_number,
            'dataset_info': None,
            'arim_extension': None,
            'experiment_data_list': None,  # 複数実験データ対応
            'collection_status': {
                'dataset_info_loaded': False,
                'arim_extension_loaded': False,
                'experiment_data_loaded': False
            }
        }
        
        try:
            # 1. データセット既存情報を取得
            result['dataset_info'] = self._load_dataset_existing_info(grant_number)
            result['collection_status']['dataset_info_loaded'] = result['dataset_info'] is not None
            
            # 2. ARIM拡張情報を取得
            result['arim_extension'] = self._load_arim_extension_data(grant_number)
            result['collection_status']['arim_extension_loaded'] = result['arim_extension'] is not None
            
            # 3. ARIM実験データを取得（複数実験対応）
            result['experiment_data_list'] = self._load_arim_experiment_data(grant_number)
            result['collection_status']['experiment_data_loaded'] = result['experiment_data_list'] is not None
            
        except Exception as e:
            logger.warning("ARIM課題データ収集エラー: %s", e)
            
        return result
        
    def _load_dataset_existing_info(self, grant_number: str) -> Optional[Dict[str, Any]]:
        """
        データセット既存情報を取得
        AIテスト機能の課題番号選択時と同じ仕組みを使用
        """
        try:
            # AIテスト機能での課題番号対応データセット情報を模擬
            # 実際の実装では、AI機能と同じデータソースを使用
            
            # 基本的なデータセット情報を構築
            dataset_info = {
                "課題番号": grant_number,
                "data_source": "dataset_existing_info",
                "collection_method": "ai_test_compatible"
            }
            
            # 既存データセット情報があれば追加取得
            # TODO: 実際のデータセット取得APIと連携
            
            return dataset_info
            
        except Exception as e:
            logger.warning("データセット既存情報取得エラー: %s", e)
            return None
            
    def _load_arim_extension_data(self, grant_number: str) -> Optional[Dict[str, Any]]:
        """
        ARIM拡張情報を取得（AIテスト機能と同じロジック）
        """
        try:
            # AIテスト機能と同じファイルパスとロジック
            # ARIM拡張ファイルのパス（AIテスト機能と同じ）
            arim_file_path = get_dynamic_file_path("input/ai/arim/converted.xlsx")
            
            if not os.path.exists(arim_file_path):
                logger.debug("ARIM拡張ファイルが見つかりません: %s", arim_file_path)
                return None
            
            # Excelファイルを読み込み（AIテスト機能と同じ）
            if self.arim_extension_data is None:
                _headers, records = load_excel_records(arim_file_path)
                self.arim_extension_data = records
                logger.info("ARIM拡張データ読み込み: %s 件", len(self.arim_extension_data))
            
            # 課題番号でマッチングを検索（AIテスト機能と同じロジック）
            matching_record = self._find_matching_arim_record(grant_number, self.arim_extension_data)
            
            if matching_record:
                logger.info("ARIM拡張データでマッチング成功: %s", grant_number)
                logger.debug("取得データ詳細: ARIMNO=%s, タイトル=%s...", matching_record.get('ARIMNO'), matching_record.get('利用課題名', 'N/A')[:50])
                return matching_record
            else:
                logger.debug("ARIM拡張データでマッチングなし: %s", grant_number)
                logger.debug("完全一致検索のみ実行 - 他の検索方式は無効化済み")
                return None
                
        except Exception as e:
            logger.warning("ARIM拡張情報の読み込みに失敗: %s", e)
            return None
            
    def _find_matching_arim_record(self, grant_number: str, arim_data: List[Dict]) -> Optional[Dict]:
        """
        ARIM拡張データから課題番号にマッチするレコードを検索
        完全一致のみを使用（末尾4桁検索は無効化）
        """
        if not grant_number or not arim_data:
            return None
            
        grant_number = str(grant_number).strip()
        
        # 1. ARIMNO列での完全一致検索（優先）
        for record in arim_data:
            record_arimno = record.get('ARIMNO', '')
            if record_arimno and str(record_arimno) == grant_number:
                logger.debug("ARIMNO完全一致: %s", record_arimno)
                return record
        
        # 2. 課題番号列での完全一致検索
        for record in arim_data:
            record_task = record.get('課題番号', '')
            if record_task and str(record_task) == grant_number:
                logger.debug("課題番号完全一致: %s", record_task)
                return record
        
        # 完全一致のみ - 末尾4桁検索は無効化
        logger.debug("完全一致検索結果なし: %s", grant_number)
        return None
        
    def _load_arim_experiment_data(self, grant_number: str) -> Optional[List[Dict[str, Any]]]:
        """
        ARIM実験データを取得（arim_exp.xlsx から複数実験データ対応）
        """
        try:
            # ARIM実験データファイルを読み込み
            arim_exp_file_path = get_dynamic_file_path("input/ai/arim_exp.xlsx")
            if not os.path.exists(arim_exp_file_path):
                logger.warning("ARIM実験データファイルが見つかりません: %s", arim_exp_file_path)
                return None
            
            # Excelファイルを読み込み
            headers, records = load_excel_records(arim_exp_file_path)
            logger.info("ARIM実験データ読み込み: %s 件", len(records))
            
            # 'ARIM ID'列で課題番号を検索
            if 'ARIM ID' not in headers:
                logger.warning("ARIM実験データに'ARIM ID'列が見つかりません")
                logger.debug("利用可能な列: %s", headers)
                return None

            ensure_alias_column(records, 'ARIM ID', '課題番号')
            
            # 課題番号に一致する実験データを抽出
            matching_experiments = [
                dict(record)
                for record in records
                if str(record.get('ARIM ID', '')).strip() == str(grant_number).strip()
            ]
            
            if not matching_experiments:
                logger.info("課題番号 %s に対応するARIM実験データが見つかりません", grant_number)
                return None
            
            # 複数実験データを辞書リストに変換
            experiments_list = matching_experiments
            logger.info("課題番号 %s の実験データ: %s 件", grant_number, len(experiments_list))
            
            # 各実験データに課題番号を追加（統一性のため）
            for exp in experiments_list:
                exp['課題番号'] = grant_number
                exp['data_source'] = 'arim_exp_xlsx'
                exp['collection_method'] = 'real_experiment_data'
            
            return experiments_list
            
        except Exception as e:
            logger.warning("ARIM実験データ取得エラー: %s", e)
            import traceback
            traceback.print_exc()
            return None
            
    def format_for_prompt_template(self, arim_data: Dict[str, Any]) -> Dict[str, str]:
        """
        収集したARIMデータをプロンプトテンプレート用にフォーマット
        
        Args:
            arim_data: collect_arim_data_by_grant_number で取得したデータ
            
        Returns:
            プロンプトテンプレート変数用の辞書
        """
        formatted = {}
        
        try:
            # データセット既存情報のフォーマット
            if arim_data.get('dataset_info'):
                dataset_info = arim_data['dataset_info']
                formatted['dataset_existing_info'] = self._format_dataset_info(dataset_info)
            else:
                formatted['dataset_existing_info'] = "[データセット既存情報なし]"
            
            # ARIM拡張情報のフォーマット
            if arim_data.get('arim_extension'):
                arim_extension = arim_data['arim_extension']
                formatted['arim_extension_data'] = self._format_arim_extension(arim_extension)
            else:
                formatted['arim_extension_data'] = "[ARIM拡張情報なし]"
            
            # ARIM実験データのフォーマット（複数実験対応）
            if arim_data.get('experiment_data_list'):
                experiment_data_list = arim_data['experiment_data_list']
                formatted['arim_experiment_data'] = self._format_experiment_data(experiment_data_list)
                
                # 実験データサマリーの追加
                experiment_count = len(experiment_data_list)
                formatted['experiment_summary'] = f"実験データ件数: {experiment_count}件（arim_exp.xlsx より）"
            else:
                formatted['arim_experiment_data'] = "[ARIM実験データなし]"
                formatted['experiment_summary'] = "実験データ件数: 0件"
            
            # 【拡張実験情報（ARIM拡張含む）】セクションの追加
            # ARIM拡張情報からの詳細実験データを拡張実験情報として追加表示
            if arim_data.get('arim_extension'):
                arim_ext = arim_data['arim_extension']
                experiment_field = arim_ext.get('実験', '')
                results_field = arim_ext.get('結果と考察', '')
                
                if experiment_field and str(experiment_field).strip() and str(experiment_field).strip().lower() != 'nan':
                    formatted['arim_detailed_experiment'] = f"""=== 【拡張実験情報（ARIM拡張含む）】 ===
課題番号: {arim_ext.get('ARIMNO', 'N/A')}

【実験手法・条件】
{experiment_field}

【結果と考察】
{results_field if results_field and str(results_field).strip().lower() != 'nan' else '結果と考察データなし'}

=== 【拡張実験情報終了】 ==="""
                else:
                    formatted['arim_detailed_experiment'] = "[拡張実験情報なし]"
            else:
                formatted['arim_detailed_experiment'] = "[拡張実験情報なし]"
            
            # 収集状況サマリー
            status = arim_data.get('collection_status', {})
            experiment_count = len(arim_data.get('experiment_data_list', [])) if arim_data.get('experiment_data_list') else 0
            formatted['collection_summary'] = f"データセット情報: {'○' if status.get('dataset_info_loaded') else '×'}, " \
                                            f"ARIM拡張: {'○' if status.get('arim_extension_loaded') else '×'}, " \
                                            f"実験データ: {'○' if status.get('experiment_data_loaded') else '×'} ({experiment_count}件)"
                                            
        except Exception as e:
            logger.warning("ARIMデータフォーマットエラー: %s", e)
            # エラー時のフォールバック
            formatted['dataset_existing_info'] = "[フォーマットエラー]"
            formatted['arim_extension_data'] = "[フォーマットエラー]"
            formatted['arim_experiment_data'] = "[フォーマットエラー]"
            formatted['collection_summary'] = "フォーマット処理エラー"
            
        return formatted
        
    def _format_dataset_info(self, dataset_info: Dict[str, Any]) -> str:
        """データセット情報をプロンプト用文字列にフォーマット"""
        try:
            lines = ["=== データセット既存情報 ==="]
            for key, value in dataset_info.items():
                if value is not None and str(value).strip():
                    lines.append(f"• {key}: {value}")
            return "\n".join(lines)
        except Exception:
            return "[データセット情報フォーマットエラー]"
            
    def _format_arim_extension(self, arim_extension: Dict[str, Any]) -> str:
        """ARIM拡張情報をプロンプト用文字列にフォーマット（AIテスト機能と同等の詳細情報）"""
        try:
            if not arim_extension:
                return "[ARIM拡張情報なし]"
                
            # 実際のARIM拡張データフィールドにマッピング
            grant_number = arim_extension.get('ARIMNO', 'N/A')  # ARIMNOを課題番号として使用
            arim_no = arim_extension.get('ARIMNO', 'N/A')
            key = arim_extension.get('key', 'N/A')
            
            # 基本情報フィールド
            keywords = arim_extension.get('キーワード【自由記述】', 'N/A')
            code = arim_extension.get('コード', 'N/A')
            equipment1 = arim_extension.get('利用した主な設備1', 'N/A')
            usage_type_main = arim_extension.get('利用形態（主）', 'N/A')
            usage_type_sub = arim_extension.get('利用形態（副）', '----')
            user_name = arim_extension.get('利用者名', 'N/A')
            title = arim_extension.get('利用課題名', 'N/A')
            experiment_details = arim_extension.get('実験', 'N/A')
            affiliation = arim_extension.get('所属名', 'N/A')
            summary = arim_extension.get('概要（目的・実施内容）', 'N/A')
            
            # 技術領域情報
            cross_tech_main = arim_extension.get('横断技術領域（主）', 'N/A')
            cross_tech_sub = arim_extension.get('横断技術領域（副）', '----')
            institution_code = arim_extension.get('機関コード', 'N/A')
            internal_external = arim_extension.get('機関外・機関内の利用', 'N/A')
            results_discussion = arim_extension.get('結果と考察', 'N/A')
            task_number_suffix = arim_extension.get('課題番号（下4桁）', 'N/A')
            important_tech_main = arim_extension.get('重要技術領域（主）', 'N/A')
            important_tech_sub = arim_extension.get('重要技術領域（副）', '----')
            
            # 完全なARIM拡張情報を構築（AIテスト機能と同じ詳細レベル）
            lines = [
                "=== ARIM拡張情報 ===",
                f"課題番号: {grant_number}",
                f"ARIMNO: {arim_no}",
                "",
                f"ARIMNO: {arim_no}",
                f"key: {key}",
                f"キーワード【自由記述】: {keywords}",
                f"コード: {code}",
                f"利用した主な設備1: {equipment1}",
                f"利用形態（主）: {usage_type_main}",
                f"利用形態（副）: {usage_type_sub}",
                f"利用者名: {user_name}",
                f"利用課題名: {title}",
                f"実験: {experiment_details}",
                f"所属名: {affiliation}",
                f"概要（目的・実施内容）: {summary}",
                f"横断技術領域（主）: {cross_tech_main}",
                f"横断技術領域（副）: {cross_tech_sub}",
                f"機関コード: {institution_code}",
                f"機関外・機関内の利用: {internal_external}",
                f"結果と考察: {results_discussion}",
                f"課題番号（下4桁）: {task_number_suffix}",
                f"重要技術領域（主）: {important_tech_main}",
                f"重要技術領域（副）: {important_tech_sub}",
                "=== ARIM拡張情報終了 ==="
            ]
            
            return "\n".join(lines)
        except Exception:
            return "[ARIM拡張情報フォーマットエラー]"
            
    def _format_experiment_data(self, experiment_data_list: List[Dict[str, Any]]) -> str:
        """ARIM実験データをプロンプト用文字列にフォーマット（複数実験対応）"""
        try:
            if not experiment_data_list:
                return "[ARIM実験データなし]"
                
            lines = ["=== 【実験情報データ】 ==="]
            
            # 単一実験データの場合
            if len(experiment_data_list) == 1:
                exp_data = experiment_data_list[0]
                grant_number = exp_data.get('課題番号', exp_data.get('ARIM ID', 'N/A'))
                lines.append(f"📋 課題番号: {grant_number}")
                lines.append(f"📊 実験データ件数: 1件")
                lines.append("")
                
                # 主要フィールドの表示
                important_fields = [
                    'タイトル', '概要', '手法', '装置', '測定条件', 
                    '材料', '試料', '温度', '圧力', '時間', '結果'
                ]
                
                for field in important_fields:
                    value = exp_data.get(field)
                    if value is not None and str(value).strip() and str(value).strip().lower() not in ['nan', 'none', '']:
                        lines.append(f"• {field}: {value}")
                
                # その他のフィールド（データソース固有）
                other_fields = []
                for key, value in exp_data.items():
                    if (key not in important_fields and 
                        key not in ['課題番号', 'ARIM ID', 'data_source', 'collection_method'] and
                        value is not None and str(value).strip() and 
                        str(value).strip().lower() not in ['nan', 'none', '']):
                        other_fields.append(f"• {key}: {value}")
                
                if other_fields:
                    lines.append("")
                    lines.append("=== その他の実験情報 ===")
                    lines.extend(other_fields[:15])  # 最大15項目
            
            # 複数実験データの場合
            else:
                grant_number = experiment_data_list[0].get('課題番号', 'N/A')
                lines.append(f"📋 課題番号: {grant_number}")
                lines.append(f"📊 実験データ件数: {len(experiment_data_list)}件")
                lines.append("")
                
                for i, exp_data in enumerate(experiment_data_list, 1):
                    lines.append(f"--- 実験データ {i} ---")
                    
                    # 各実験の主要情報
                    exp_title = exp_data.get('タイトル', exp_data.get('概要', f'実験{i}'))
                    if exp_title and str(exp_title).strip():
                        lines.append(f"実験名: {exp_title}")
                    
                    # 実験固有のフィールド
                    key_fields = ['手法', '装置', '材料', '結果']
                    for field in key_fields:
                        value = exp_data.get(field)
                        if value is not None and str(value).strip() and str(value).strip().lower() not in ['nan', 'none', '']:
                            lines.append(f"{field}: {value}")
                    
                    lines.append("")
            
            lines.append("=== 【実験情報データ終了】 ===")
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning("ARIM実験データフォーマットエラー: %s", e)
            return "[ARIM実験データフォーマットエラー]"
            
    def _get_experiment_count(self, grant_number: str) -> int:
        """実験データ件数を取得"""
        try:
            # AIテストと同じロジックで実験データ件数を取得
            experiment_data_path = get_dynamic_file_path("input/ai/experiment_data.json")
            if os.path.exists(experiment_data_path):
                with open(experiment_data_path, 'r', encoding='utf-8') as f:
                    experiment_records = json.load(f)
                    
                # 課題番号でフィルタリング
                matching_records = [
                    record for record in experiment_records 
                    if record.get('課題番号') == grant_number or record.get('grant_number') == grant_number
                ]
                return len(matching_records)
        except Exception as e:
            logger.warning("実験データ件数取得エラー: %s", e)
            
        return 0
        
    def _get_experiment_count_by_arimno(self, arim_no: str) -> int:
        """ARIMNOから実験データ件数を取得"""
        try:
            # ARIMNOから課題番号を抽出（例: JPMXP1224KU0016 -> JPNP20016 など）
            if arim_no and len(arim_no) >= 4:
                # 末尾4桁を使用
                task_suffix = arim_no[-4:]
                
                experiment_data_path = get_dynamic_file_path("input/ai/experiment_data.json")
                if os.path.exists(experiment_data_path):
                    with open(experiment_data_path, 'r', encoding='utf-8') as f:
                        experiment_records = json.load(f)
                        
                    # 末尾4桁でマッチング
                    matching_records = [
                        record for record in experiment_records 
                        if (record.get('課題番号', '').endswith(task_suffix) or 
                            record.get('grant_number', '').endswith(task_suffix))
                    ]
                    return len(matching_records)
        except Exception as e:
            logger.warning("ARIMNO実験データ件数取得エラー: %s", e)
            
        return 0

    def extract_equipment_ids(self, grant_number: str) -> List[str]:
        """
        ARIM拡張データから設備IDを抽出
        """
        try:
            # ARIM拡張データから設備ID情報を抽出
            arim_data = self._load_arim_extension_data(grant_number)
            if not arim_data:
                return []
            
            equipment_ids = []
            
            # 1. 利用した主な設備1から設備IDを抽出
            equipment_field = arim_data.get('利用した主な設備1', '')
            if equipment_field and isinstance(equipment_field, str):
                # "TU-507：集束イオンビーム加工装置" のような形式から設備IDを抽出
                import re
                # パターン: 英数字とハイフンの組み合わせ（例: TU-507, NM-001）
                equipment_id_match = re.match(r'([A-Z]{1,3}-\d{3,4})', equipment_field)
                if equipment_id_match:
                    equipment_ids.append(equipment_id_match.group(1))
                    logger.info("設備ID抽出成功（設備フィールド）: %s from %s", equipment_id_match.group(1), equipment_field)
            
            # 2. データセット実験データからも設備IDを抽出
            experiment_data = self._load_arim_experiment_data(grant_number)
            if experiment_data:
                for experiment in experiment_data:
                    dataset_name = experiment.get('実験名', '')
                    if dataset_name:
                        extracted_ids = self._extract_equipment_from_dataset_name(dataset_name)
                        for eq_id in extracted_ids:
                            if eq_id not in equipment_ids:
                                equipment_ids.append(eq_id)
                                logger.info("設備ID抽出成功（データセット名）: %s from %s", eq_id, dataset_name)
            
            # 3. その他の設備情報フィールドからも抽出（将来の拡張用）
            # 利用した主な設備2, 設備情報 などがあれば同様に処理
            
            return equipment_ids
            
        except Exception as e:
            logger.warning("設備ID抽出エラー: %s", e)
            return []
    
    def _extract_equipment_from_dataset_name(self, dataset_name: str) -> List[str]:
        """
        データセット名から設備IDを抽出
        例: "ARIM-R6_TU-504_TEM-STEM_20241121" -> ["TU-504"]
        例: "ARIM-R6_TU-FDL-215_20250130" -> ["TU-FDL-215"]
        """
        import re
        equipment_ids = []
        
        if not dataset_name or not isinstance(dataset_name, str):
            return equipment_ids
        
        # アンダースコア区切りで分割し、設備IDパターンを探す
        parts = dataset_name.split('_')
        
        for part in parts:
            # 設備IDパターン1: 英字1-3文字 + ハイフン + 数字3-4桁 (例: TU-507, NM-001)
            equipment_match = re.match(r'^([A-Z]{1,3}-\d{3,4})$', part)
            if equipment_match:
                equipment_ids.append(equipment_match.group(1))
                continue
                
            # 設備IDパターン2: 英字1-3文字 + ハイフン + 英字 + ハイフン + 数字 (例: TU-FDL-215)
            equipment_match_complex = re.match(r'^([A-Z]{1,3}-[A-Z]{2,4}-\d{1,4})$', part)
            if equipment_match_complex:
                equipment_ids.append(equipment_match_complex.group(1))
                continue
        
        return equipment_ids

    def extract_equipment_from_dataset_json(self, dataset_json_data: Dict[str, Any]) -> List[str]:
        """
        データセットJSONからデータセットテンプレートIDを抽出し、設備IDを取得
        
        Args:
            dataset_json_data: データセットJSON情報
            
        Returns:
            抽出された設備IDリスト
        """
        equipment_ids = []
        
        try:
            # データセットテンプレートIDを取得
            template_data = dataset_json_data.get('data', {}).get('relationships', {}).get('template', {}).get('data', {})
            template_id = template_data.get('id', '')
            
            if template_id:
                logger.info("データセットテンプレートID発見: %s", template_id)
                
                # テンプレートIDから設備IDを抽出
                extracted_ids = self._extract_equipment_from_dataset_name(template_id)
                equipment_ids.extend(extracted_ids)
                
                for eq_id in extracted_ids:
                    logger.info("設備ID抽出成功（テンプレートID）: %s from %s", eq_id, template_id)
            
            # データセット名からも抽出
            dataset_name = dataset_json_data.get('data', {}).get('attributes', {}).get('name', '')
            if dataset_name:
                name_equipment_ids = self._extract_equipment_from_dataset_name(dataset_name)
                for eq_id in name_equipment_ids:
                    if eq_id not in equipment_ids:
                        equipment_ids.append(eq_id)
                        logger.info("設備ID抽出成功（データセット名）: %s from %s", eq_id, dataset_name)
            
        except Exception as e:
            logger.warning("データセットJSONからの設備ID抽出エラー: %s", e)
        
        return equipment_ids


# グローバルインスタンス
_arim_data_collector = None

def get_arim_data_collector() -> ARIMDataCollector:
    """ARIMデータコレクターのシングルトンインスタンスを取得"""
    global _arim_data_collector
    if _arim_data_collector is None:
        _arim_data_collector = ARIMDataCollector()
    return _arim_data_collector