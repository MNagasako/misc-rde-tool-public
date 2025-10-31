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
            print(f"[DEBUG] データセット詳細情報を取得開始: dataset_id={dataset_id}")
            details = self._collect_dataset_details(dataset_id)
            context.update(details)
            
            print(f"[DEBUG] 取得した詳細情報のキー: {list(details.keys())}")
            if 'file_info' in details:
                print(f"[DEBUG] file_info の長さ: {len(details['file_info'])} 文字")
                print(f"[DEBUG] file_info の先頭100文字: {details['file_info'][:100]}")
                print(f"[DEBUG] file_info の型: {type(details['file_info'])}")
                print(f"[DEBUG] file_info が空: {not details['file_info']}")
            
            # ファイルツリー情報を個別キーとしても設定（プロンプトテンプレート用）
            if 'file_info' in details and details['file_info']:
                context['file_tree'] = details['file_info']
                print(f"[DEBUG] ✅ file_tree をセット: {len(context['file_tree'])} 文字")
            else:
                # file_infoが空の場合もメッセージを設定
                context['file_tree'] = details.get('file_info', '（ファイルツリー情報の取得に失敗しました）')
                print(f"[DEBUG] ⚠️  file_info が空またはFalsy - file_tree = '{context['file_tree'][:50]}...'")
            
            print(f"[DEBUG] 最終的な context['file_tree'] の長さ: {len(context.get('file_tree', ''))} 文字")
        else:
            # 新規作成時はフォームデータのみ
            context.update(self._collect_general_data())
            context['file_tree'] = '（新規作成のためファイルツリー情報なし）'
            
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
            details['file_info'] = f'（データセット詳細取得中にエラーが発生しました: {str(e)}）'
            details['metadata'] = '（メタデータ取得失敗）'
            details['related_datasets'] = '（関連データセット取得失敗）'
            
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
        データセットのファイル情報を取得（RDE API使用）
        
        Args:
            dataset_id: データセットID
            
        Returns:
            ファイル情報の文字列（プロンプトテンプレート用にフォーマット済み）
        """
        try:
            print(f"[DEBUG] ファイル情報取得開始: dataset_id={dataset_id}")
            from core.bearer_token_manager import BearerTokenManager
            from net.http_helpers import proxy_get
            
            # Bearer Token取得
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt()
            if not bearer_token:
                print("[WARNING] Bearer Token取得失敗 - ログインが必要です")
                return '（ファイルツリー情報の取得にはログインが必要です。RDEシステムにログインしてから再試行してください）'
            
            print(f"[DEBUG] Bearer Token取得成功: {bearer_token[:20]}...")
            
            # RDE APIでデータ情報を取得
            api_url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&sort=-created&page%5Boffset%5D=0&page%5Blimit%5D=24&include=owner%2Csample%2CthumbnailFile%2Cfiles"
            
            print(f"[DEBUG] API URL: {api_url}")
            
            headers = {
                "Accept": "application/vnd.api+json",
                "Authorization": f"Bearer {bearer_token}",
                "Host": "rde-api.nims.go.jp",
                "Origin": "https://rde.nims.go.jp",
                "Referer": "https://rde.nims.go.jp/"
            }
            
            response = proxy_get(api_url, headers=headers)
            
            print(f"[DEBUG] API Response Status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = f"（データ情報取得API失敗: HTTP {response.status_code}）"
                print(f"[WARNING] {error_msg}")
                if response.status_code == 401:
                    error_msg += "\n認証エラー - 再ログインが必要です"
                elif response.status_code == 403:
                    error_msg += "\nアクセス権限がありません"
                elif response.status_code == 404:
                    error_msg += "\n指定されたデータセットが見つかりません"
                return error_msg
            
            data = response.json()
            
            print(f"[DEBUG] API Response Data: {len(data.get('data', []))} タイル取得")
            
            # ファイルツリー情報をフォーマット
            formatted_result = self._format_file_tree(data)
            print(f"[DEBUG] フォーマット結果の長さ: {len(formatted_result)} 文字")
            return formatted_result
            
        except Exception as e:
            error_msg = f"（ファイル情報取得中にエラーが発生: {str(e)}）"
            print(f"[WARNING] {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg
    
    def _format_file_tree(self, api_data: Dict[str, Any]) -> str:
        """
        APIレスポンスからファイルツリー情報をフォーマット
        RDEシステムではファイルはフラット配置（階層構造なし）
        
        Args:
            api_data: RDE API /data のレスポンス
            
        Returns:
            プロンプトテンプレート用にフォーマットされた文字列
        """
        try:
            data_list = api_data.get('data', [])
            included = api_data.get('included', [])
            
            if not data_list:
                return '（このデータセットにはまだデータ（タイル）が登録されていません。データ登録後にファイルツリー情報が利用可能になります）'
            
            # includedをIDでインデックス化
            file_dict = {}
            for item in included:
                if item.get('type') == 'file':
                    file_dict[item['id']] = item.get('attributes', {})
            
            # 各タイル（データ詳細）の情報を整形
            tile_info_list = []
            
            # ファイルタイプの日本語名マッピング
            file_type_names = {
                'MAIN_IMAGE': '主要画像',
                'STRUCTURED': 'データファイル',
                'META': 'メタデータ',
                'ATTACHMENT': '添付ファイル',
                'THUMBNAIL': 'サムネイル'
            }
            
            for idx, data_item in enumerate(data_list, 1):
                attributes = data_item.get('attributes', {})
                data_name = attributes.get('name', '名前なし')
                data_number = attributes.get('dataNumber', idx)
                description = attributes.get('description', '')
                num_files = attributes.get('numberOfFiles', 0)
                num_images = attributes.get('numberOfImageFiles', 0)
                experiment_id = attributes.get('experimentId', '')
                
                # メタデータから主要情報を抽出
                metadata = attributes.get('metadata', {})
                instrument_name = metadata.get('instrument.name', {}).get('value', '')
                
                # ファイル情報を取得
                relationships = data_item.get('relationships', {})
                file_ids = [f['id'] for f in relationships.get('files', {}).get('data', [])]
                
                # タイル基本情報
                tile_info = f"■ タイル#{data_number}: {data_name}"
                if description and description != data_name:
                    tile_info += f"\n  説明: {description}"
                if experiment_id:
                    tile_info += f"\n  実験ID: {experiment_id}"
                if instrument_name:
                    tile_info += f"\n  使用装置: {instrument_name}"
                tile_info += f"\n  ファイル統計: 全{num_files}件 (画像ファイル: {num_images}件)"
                
                # ファイル詳細情報
                if file_ids:
                    file_types = {
                        'MAIN_IMAGE': [],
                        'STRUCTURED': [],
                        'META': [],
                        'ATTACHMENT': [],
                        'THUMBNAIL': []
                    }
                    
                    for file_id in file_ids:
                        if file_id in file_dict:
                            file_attr = file_dict[file_id]
                            file_name = file_attr.get('fileName', '')
                            file_type = file_attr.get('fileType', 'UNKNOWN')
                            file_size = file_attr.get('fileSize', 0)
                            media_type = file_attr.get('mediaType', '')
                            
                            # ファイルサイズを読みやすく変換
                            if file_size < 1024:
                                size_str = f"{file_size}B"
                            elif file_size < 1024 * 1024:
                                size_str = f"{file_size / 1024:.1f}KB"
                            else:
                                size_str = f"{file_size / (1024 * 1024):.1f}MB"
                            
                            file_info_item = {
                                'name': file_name,
                                'size': size_str,
                                'type': media_type
                            }
                            
                            if file_type in file_types:
                                file_types[file_type].append(file_info_item)
                            else:
                                file_types['STRUCTURED'].append(file_info_item)
                    
                    # ファイルタイプごとに整形して表示（意味のある順序で）
                    for ftype in ['MAIN_IMAGE', 'STRUCTURED', 'ATTACHMENT', 'META', 'THUMBNAIL']:
                        if file_types[ftype]:
                            type_name = file_type_names.get(ftype, ftype)
                            tile_info += f"\n  【{type_name}】"
                            for f_item in file_types[ftype]:
                                tile_info += f"\n    - {f_item['name']} ({f_item['size']}, {f_item['type']})"
                
                tile_info_list.append(tile_info)
            
            # サマリー情報
            total_tiles = len(data_list)
            total_files = sum(d.get('attributes', {}).get('numberOfFiles', 0) for d in data_list)
            total_images = sum(d.get('attributes', {}).get('numberOfImageFiles', 0) for d in data_list)
            
            result = f"【データセット内ファイル構成】\n"
            result += f"タイル数: {total_tiles}件 / 全ファイル数: {total_files}件 (画像: {total_images}件)\n"
            result += f"※ RDEシステムではファイルはフラット配置（階層構造なし）\n\n"
            result += "\n\n".join(tile_info_list)
            
            print(f"[INFO] ファイルツリー情報を生成しました: {total_tiles}タイル, {total_files}ファイル")
            return result
            
        except Exception as e:
            print(f"[ERROR] ファイルツリーフォーマットエラー: {e}")
            import traceback
            traceback.print_exc()
            return f'（ファイルツリーのフォーマット中にエラーが発生しました: {str(e)}）'
            
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