"""
データセット関連データ読み込みロジック
AIプロンプト生成のためのデータセット関連情報を取得
ARIM課題データ（実験データ・拡張情報・実験データ）も統合対応
"""

import os
import json
from typing import Dict, List, Optional, Any
from config.common import get_dynamic_file_path
from .arim_data_collector import get_arim_data_collector
from .arim_data_collector import get_arim_data_collector


class DatasetContextCollector:
    """データセット関連のコンテキストデータ収集クラス"""
    
    def __init__(self):
        self.cache = {}
        
    def collect_full_context(self, dataset_id: Optional[str] = None, **form_data) -> Dict[str, Any]:
        """
        データセットの完全なコンテキストデータを収集
        ARIM課題データ（実験データ・拡張情報・実験データ）も統合
        
        Args:
            dataset_id: データセットID（修正時に使用）
            **form_data: フォームから取得した基本データ
            
        Returns:
            収集されたコンテキストデータ
        """
        context = {}
        
        # フォームデータを基本情報として設定
        context.update(form_data)
        
        # 既存の説明文を取得
        context['existing_description'] = form_data.get('description', '')
        
        # 課題番号を取得
        grant_number = form_data.get('grant_number', '').strip()
        
        # 追加データを収集
        if dataset_id:
            # データセットIDが指定されている場合（修正時）
            context.update(self._collect_dataset_details(dataset_id))
        else:
            # 新規作成時はフォームデータのみ
            context.update(self._collect_general_data())
            
        # ARIM課題データを収集（課題番号が存在する場合）
        if grant_number:
            arim_data = self._collect_arim_data(grant_number, context)
            context.update(arim_data)
            
        return context
        
    def _collect_arim_data(self, grant_number: str, form_data: Dict[str, Any] = None) -> Dict[str, str]:
        """
        課題番号からARIM課題データを収集
        AIテスト機能と同じデータソースを使用
        
        Args:
            grant_number: 課題番号
            form_data: フォームデータ（データセット名など）
            
        Returns:
            ARIM課題データ（プロンプトテンプレート用）
        """
        arim_formatted = {}
        
        try:
            print(f"[INFO] ARIM課題データ収集開始: {grant_number}")
            
            # ARIMデータコレクターを使用してデータを取得
            arim_collector = get_arim_data_collector()
            arim_data = arim_collector.collect_arim_data_by_grant_number(grant_number)
            
            # プロンプトテンプレート用にフォーマット
            arim_formatted = arim_collector.format_for_prompt_template(arim_data)
            
            # 設備IDを抽出してコンテキストに追加
            equipment_ids = arim_collector.extract_equipment_ids(grant_number)
            
            # データセット名からも設備IDを抽出（フォームデータから）
            if form_data:
                dataset_name = form_data.get('name', '')
                if dataset_name:
                    dataset_equipment_ids = arim_collector._extract_equipment_from_dataset_name(dataset_name)
                    for eq_id in dataset_equipment_ids:
                        if eq_id not in equipment_ids:
                            equipment_ids.append(eq_id)
                            print(f"[INFO] データセット名から設備ID抽出: {eq_id} from {dataset_name}")
                
                # データセットJSONデータからも設備IDを抽出（データセットテンプレートIDを含む）
                dataset_json_data = form_data.get('dataset_json_data')
                if dataset_json_data:
                    json_equipment_ids = arim_collector.extract_equipment_from_dataset_json(dataset_json_data)
                    for eq_id in json_equipment_ids:
                        if eq_id not in equipment_ids:
                            equipment_ids.append(eq_id)
            
            arim_formatted['equipment_ids'] = equipment_ids
            
            print(f"[INFO] ARIM課題データ収集完了: {arim_formatted.get('collection_summary', 'N/A')}")
            print(f"[INFO] 設備ID抽出結果: {equipment_ids}")
            
            # 詳細ログ追加
            for key, value in arim_formatted.items():
                if key not in ['collection_summary', 'equipment_ids']:
                    has_data = '[ARIM拡張情報なし]' not in str(value) and '[ARIM課題データ取得エラー]' not in str(value)
                    status = "○" if has_data else "×"
                    print(f"[DEBUG] {key}: {status} ({len(str(value))}文字)")
            
        except Exception as e:
            print(f"[WARNING] ARIM課題データ収集エラー: {e}")
            # エラー時のフォールバック
            arim_formatted = {
                'dataset_existing_info': '[ARIM課題データ取得エラー]',
                'arim_extension_data': '[ARIM課題データ取得エラー]',
                'arim_experiment_data': '[ARIM課題データ取得エラー]',
                'collection_summary': 'エラーのため取得失敗'
            }
            
        return arim_formatted
        
    def _collect_dataset_details(self, dataset_id: str) -> Dict[str, Any]:
        """
        特定のデータセットの詳細情報を収集
        
        Args:
            dataset_id: データセットID
            
        Returns:
            データセット詳細情報
        """
        details = {}
        
        try:
            # TODO: 実際のデータセット詳細取得ロジックを実装
            # 現在はダミーデータを返す
            
            # ファイル情報を取得
            details['file_info'] = self._get_file_info(dataset_id)
            
            # メタデータを取得
            details['metadata'] = self._get_metadata(dataset_id)
            
            # 関連データセットを取得
            details['related_datasets'] = self._get_related_datasets(dataset_id)
            
        except Exception as e:
            print(f"[WARNING] データセット詳細取得エラー: {e}")
            details['file_info'] = ''
            details['metadata'] = ''
            details['related_datasets'] = ''
            
        return details
        
    def _collect_general_data(self) -> Dict[str, Any]:
        """
        一般的なデータセット情報を収集
        
        Returns:
            一般的なデータセット情報
        """
        general = {}
        
        try:
            # TODO: 一般的なデータセット統計や傾向を取得
            # 現在はダミーデータを返す
            
            general['file_info'] = 'ファイル情報は作成時に自動設定されます'
            general['metadata'] = 'メタデータは登録後に生成されます'
            general['related_datasets'] = '関連データセットは自動検出されます'
            
        except Exception as e:
            print(f"[WARNING] 一般データ取得エラー: {e}")
            general['file_info'] = ''
            general['metadata'] = ''
            general['related_datasets'] = ''
            
        return general
        
    def _get_file_info(self, dataset_id: str) -> str:
        """
        データセットのファイル情報を取得
        
        Args:
            dataset_id: データセットID
            
        Returns:
            ファイル情報の文字列
        """
        try:
            # TODO: 実際のファイル情報取得ロジック
            # 例: API呼び出し、ローカルファイル解析など
            
            # ダミー実装
            file_info_list = [
                f"データセット{dataset_id}には複数のファイルが含まれています",
                "主要なファイル形式: CSV, JSON, TXT",
                "総サイズ: 約100MB"
            ]
            
            return '; '.join(file_info_list)
            
        except Exception as e:
            print(f"[WARNING] ファイル情報取得エラー: {e}")
            return ''
            
    def _get_metadata(self, dataset_id: str) -> str:
        """
        データセットのメタデータを取得
        
        Args:
            dataset_id: データセットID
            
        Returns:
            メタデータの文字列
        """
        try:
            # TODO: 実際のメタデータ取得ロジック
            # 例: RDE API呼び出し、データベースクエリなど
            
            # ダミー実装
            metadata_items = [
                f"作成日: 2024-01-01",
                f"最終更新: 2024-02-01", 
                f"データタイプ: 実験データ",
                f"分野: 材料科学"
            ]
            
            return '; '.join(metadata_items)
            
        except Exception as e:
            print(f"[WARNING] メタデータ取得エラー: {e}")
            return ''
            
    def _get_related_datasets(self, dataset_id: str) -> str:
        """
        関連するデータセットを取得
        
        Args:
            dataset_id: データセットID
            
        Returns:
            関連データセットの文字列
        """
        try:
            # TODO: 実際の関連データセット検索ロジック
            # 例: 同じ課題番号、同じ研究者、類似タグなど
            
            # ダミー実装
            related_list = [
                f"同一課題の関連データセット: 3件",
                f"同じ研究者による関連データセット: 5件",
                f"類似分野のデータセット: 10件"
            ]
            
            return '; '.join(related_list)
            
        except Exception as e:
            print(f"[WARNING] 関連データセット取得エラー: {e}")
            return ''


# グローバルインスタンス
_dataset_context_collector = None

def get_dataset_context_collector() -> DatasetContextCollector:
    """データセットコンテキストコレクターのシングルトンインスタンスを取得"""
    global _dataset_context_collector
    if _dataset_context_collector is None:
        _dataset_context_collector = DatasetContextCollector()
    return _dataset_context_collector