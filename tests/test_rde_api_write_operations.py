"""
RDE API 書き込み系操作テスト (OPTIONS 判定付き)

このテストは以下を検証します:
1. OPTIONS メソッドで各エンドポイントが POST/PATCH/DELETE をサポートしているか確認
2. サポートしている場合のみ、実際の操作をテスト
3. 既存データに影響を与えないよう、テストデータは作成後に削除

実行方法:
    python tests/test_rde_api_write_operations.py
"""

import sys
import os
import json
import time
from typing import Optional, Dict, List, Any

# プロジェクトルートとsrcをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(project_root, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, project_root)

from classes.managers.token_manager import TokenManager
from classes.utils.api_request_helper import api_request
from net.http_helpers import proxy_request

# ==========================================
# OPTIONS 判定ユーティリティ
# ==========================================

def check_options_support(url: str, method: str) -> bool:
    """
    OPTIONS メソッドで指定したHTTPメソッドがサポートされているか確認
    
    Args:
        url: チェック対象のURL
        method: 確認したいHTTPメソッド (POST, PATCH, DELETE, etc.)
    
    Returns:
        bool: サポートされている場合 True
    """
    try:
        response = api_request('OPTIONS', url, timeout=10)
        
        if response is None:
            print(f"  ⚠️  OPTIONS {url} - レスポンスなし")
            return False
        
        # Allow ヘッダーから対応メソッドを取得
        allowed_methods = response.headers.get('Allow', '')
        access_control_allow_methods = response.headers.get('Access-Control-Allow-Methods', '')
        
        # 両方のヘッダーをチェック
        all_methods = f"{allowed_methods},{access_control_allow_methods}".upper()
        
        supported = method.upper() in all_methods
        
        status_symbol = "✅" if supported else "❌"
        print(f"  {status_symbol} OPTIONS {url}")
        print(f"     Allow: {allowed_methods}")
        print(f"     CORS Allow: {access_control_allow_methods}")
        print(f"     → {method} サポート: {supported}")
        
        return supported
        
    except Exception as e:
        print(f"  ⚠️  OPTIONS {url} - エラー: {e}")
        return False


def check_endpoint_availability(url: str, methods: List[str]) -> Dict[str, bool]:
    """
    複数のHTTPメソッドについて利用可能性を一括チェック
    
    Args:
        url: チェック対象のURL
        methods: チェックするメソッドのリスト
    
    Returns:
        Dict[str, bool]: {メソッド名: サポート状況}
    """
    print(f"\n{'='*70}")
    print(f"📋 OPTIONS チェック: {url}")
    print(f"{'='*70}")
    
    result = {}
    for method in methods:
        result[method] = check_options_support(url, method)
        time.sleep(0.5)  # レート制限対策
    
    return result


# ==========================================
# テストクラス
# ==========================================

class TestRDEWriteOperations:
    """RDE API 書き込み系操作テスト"""
    
    def __init__(self):
        self.token_manager = TokenManager.get_instance()
        self.created_resources = []  # クリーンアップ用
        
        # テスト結果記録
        self.test_results = {
            'options_checks': {},
            'operation_tests': {},
            'total': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def cleanup(self):
        """作成したリソースをクリーンアップ"""
        print(f"\n{'='*70}")
        print("🧹 クリーンアップ開始")
        print(f"{'='*70}")
        
        for resource in reversed(self.created_resources):
            try:
                resource_type = resource['type']
                resource_id = resource['id']
                delete_url = resource['delete_url']
                
                print(f"  削除中: {resource_type} (ID: {resource_id})")
                
                response = api_request('DELETE', delete_url, timeout=15)
                
                if response and response.status_code in [200, 204]:
                    print(f"  ✅ {resource_type} 削除成功")
                else:
                    status = response.status_code if response else 'None'
                    print(f"  ⚠️  {resource_type} 削除失敗 (Status: {status})")
                    
            except Exception as e:
                print(f"  ❌ {resource_type} 削除エラー: {e}")
    
    def run_all_tests(self):
        """全テストを実行"""
        print(f"\n{'='*70}")
        print("🚀 RDE API 書き込み系操作テスト開始")
        print(f"{'='*70}")
        
        # トークン確認
        if not self._check_tokens():
            print("❌ トークンが取得できません。先にログインしてください。")
            return
        
        try:
            # 1. グループ管理API
            self.test_group_operations()
            
            # 2. データセット管理API
            self.test_dataset_operations()
            
            # 3. データエントリAPI
            self.test_data_entry_operations()
            
            # 4. ファイルアップロードAPI
            self.test_file_upload_operations()
            
            # 5. マテリアル管理API
            self.test_material_operations()
            
        except KeyboardInterrupt:
            print("\n⚠️  ユーザーによる中断")
        
        finally:
            # クリーンアップ
            self.cleanup()
            
            # 結果サマリー
            self._print_summary()
    
    def _check_tokens(self) -> bool:
        """トークンの有効性確認"""
        print("\n🔑 トークン確認中...")
        
        rde_token = self.token_manager.get_access_token('rde.nims.go.jp')
        material_token = self.token_manager.get_access_token('rde-material.nims.go.jp')
        
        if rde_token:
            print("  ✅ rde.nims.go.jp トークン OK")
        else:
            print("  ❌ rde.nims.go.jp トークン なし")
        
        if material_token:
            print("  ✅ rde-material.nims.go.jp トークン OK")
        else:
            print("  ❌ rde-material.nims.go.jp トークン なし")
        
        return bool(rde_token or material_token)
    
    # ==========================================
    # グループ管理API テスト
    # ==========================================
    
    def test_group_operations(self):
        """グループ作成・削除テスト"""
        print(f"\n{'='*70}")
        print("📦 1. グループ管理API テスト")
        print(f"{'='*70}")
        
        base_url = "https://rde-api.nims.go.jp/api/v2/groups"
        
        # OPTIONS チェック
        support = check_endpoint_availability(base_url, ['POST', 'GET'])
        self.test_results['options_checks']['groups'] = support
        
        if not support.get('POST', False):
            print("  ⏭️  POST /groups 非サポート - スキップ")
            self.test_results['skipped'] += 1
            return
        
        # POST テスト
        self._test_create_group(base_url)
    
    def _test_create_group(self, url: str):
        """グループ作成テスト"""
        print(f"\n  🧪 テスト: POST {url}")
        self.test_results['total'] += 1
        
        payload = {
            "data": {
                "type": "group",
                "attributes": {
                    "name": f"TEST_GROUP_{int(time.time())}",
                    "description": "APIテスト用グループ (自動削除されます)"
                }
            }
        }
        
        try:
            response = api_request('POST', url, json_data=payload, timeout=15)
            
            if response is None:
                print("  ❌ レスポンスなし")
                self.test_results['failed'] += 1
                return
            
            if response.status_code == 201:
                data = response.json()
                group_id = data['data']['id']
                group_name = data['data']['attributes']['name']
                
                print(f"  ✅ グループ作成成功")
                print(f"     ID: {group_id}")
                print(f"     Name: {group_name}")
                
                # クリーンアップ用に記録
                self.created_resources.append({
                    'type': 'group',
                    'id': group_id,
                    'delete_url': f"{url}/{group_id}"
                })
                
                self.test_results['passed'] += 1
                self.test_results['operation_tests']['create_group'] = 'PASS'
                
            elif response.status_code == 403:
                print(f"  ⏭️  グループ作成権限なし (403) - スキップ")
                self.test_results['skipped'] += 1
                self.test_results['operation_tests']['create_group'] = 'SKIP (403)'
                
            else:
                print(f"  ❌ グループ作成失敗 (Status: {response.status_code})")
                print(f"     Response: {response.text[:200]}")
                self.test_results['failed'] += 1
                self.test_results['operation_tests']['create_group'] = f'FAIL ({response.status_code})'
                
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            self.test_results['failed'] += 1
            self.test_results['operation_tests']['create_group'] = f'ERROR ({e})'
    
    # ==========================================
    # データセット管理API テスト
    # ==========================================
    
    def test_dataset_operations(self):
        """データセット作成・更新・削除テスト"""
        print(f"\n{'='*70}")
        print("📊 2. データセット管理API テスト")
        print(f"{'='*70}")
        
        base_url = "https://rde-api.nims.go.jp/api/v2/datasets"
        
        # OPTIONS チェック
        support = check_endpoint_availability(base_url, ['POST', 'GET'])
        self.test_results['options_checks']['datasets'] = support
        
        if not support.get('POST', False):
            print("  ⏭️  POST /datasets 非サポート - スキップ")
            self.test_results['skipped'] += 1
            return
        
        # POST テスト
        dataset_id = self._test_create_dataset(base_url)
        
        if dataset_id:
            # PATCH テスト
            self._test_update_dataset(base_url, dataset_id)
    
    def _test_create_dataset(self, url: str) -> Optional[str]:
        """データセット作成テスト"""
        print(f"\n  🧪 テスト: POST {url}")
        self.test_results['total'] += 1
        
        payload = {
            "data": {
                "type": "dataset",
                "attributes": {
                    "name": f"TEST_DATASET_{int(time.time())}",
                    "description": "APIテスト用データセット (自動削除されます)",
                    "datasetType": "ANALYSIS",
                    "isOpen": False,
                    "globalShareDataset": False
                }
            }
        }
        
        try:
            response = api_request('POST', url, json_data=payload, timeout=15)
            
            if response is None:
                print("  ❌ レスポンスなし")
                self.test_results['failed'] += 1
                return None
            
            if response.status_code == 201:
                data = response.json()
                dataset_id = data['data']['id']
                dataset_name = data['data']['attributes']['name']
                
                print(f"  ✅ データセット作成成功")
                print(f"     ID: {dataset_id}")
                print(f"     Name: {dataset_name}")
                
                # クリーンアップ用に記録
                self.created_resources.append({
                    'type': 'dataset',
                    'id': dataset_id,
                    'delete_url': f"{url}/{dataset_id}"
                })
                
                self.test_results['passed'] += 1
                self.test_results['operation_tests']['create_dataset'] = 'PASS'
                
                return dataset_id
                
            elif response.status_code == 403:
                print(f"  ⏭️  データセット作成権限なし (403) - スキップ")
                self.test_results['skipped'] += 1
                self.test_results['operation_tests']['create_dataset'] = 'SKIP (403)'
                return None
                
            else:
                print(f"  ❌ データセット作成失敗 (Status: {response.status_code})")
                print(f"     Response: {response.text[:200]}")
                self.test_results['failed'] += 1
                self.test_results['operation_tests']['create_dataset'] = f'FAIL ({response.status_code})'
                return None
                
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            self.test_results['failed'] += 1
            self.test_results['operation_tests']['create_dataset'] = f'ERROR ({e})'
            return None
    
    def _test_update_dataset(self, base_url: str, dataset_id: str):
        """データセット更新テスト (PATCH)"""
        url = f"{base_url}/{dataset_id}"
        
        print(f"\n  🧪 テスト: PATCH {url}")
        self.test_results['total'] += 1
        
        # OPTIONS チェック
        support = check_endpoint_availability(url, ['PATCH', 'GET', 'DELETE'])
        self.test_results['options_checks'][f'datasets/{dataset_id}'] = support
        
        if not support.get('PATCH', False):
            print("  ⏭️  PATCH /datasets/{id} 非サポート - スキップ")
            self.test_results['skipped'] += 1
            return
        
        payload = {
            "data": {
                "type": "dataset",
                "id": dataset_id,
                "attributes": {
                    "description": "更新テスト完了 (自動削除されます)"
                }
            }
        }
        
        try:
            response = api_request('PATCH', url, json_data=payload, timeout=15)
            
            if response is None:
                print("  ❌ レスポンスなし")
                self.test_results['failed'] += 1
                return
            
            if response.status_code == 200:
                data = response.json()
                updated_desc = data['data']['attributes'].get('description', '')
                
                print(f"  ✅ データセット更新成功")
                print(f"     Updated Description: {updated_desc[:50]}...")
                
                self.test_results['passed'] += 1
                self.test_results['operation_tests']['update_dataset'] = 'PASS'
                
            elif response.status_code == 403:
                print(f"  ⏭️  データセット更新権限なし (403) - スキップ")
                self.test_results['skipped'] += 1
                self.test_results['operation_tests']['update_dataset'] = 'SKIP (403)'
                
            else:
                print(f"  ❌ データセット更新失敗 (Status: {response.status_code})")
                print(f"     Response: {response.text[:200]}")
                self.test_results['failed'] += 1
                self.test_results['operation_tests']['update_dataset'] = f'FAIL ({response.status_code})'
                
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            self.test_results['failed'] += 1
            self.test_results['operation_tests']['update_dataset'] = f'ERROR ({e})'
    
    # ==========================================
    # データエントリAPI テスト
    # ==========================================
    
    def test_data_entry_operations(self):
        """データエントリ作成テスト"""
        print(f"\n{'='*70}")
        print("📝 3. データエントリAPI テスト")
        print(f"{'='*70}")
        
        base_url = "https://rde-entry-api-arim.nims.go.jp/entries"
        
        # OPTIONS チェック
        support = check_endpoint_availability(base_url, ['POST', 'GET'])
        self.test_results['options_checks']['entries'] = support
        
        if not support.get('POST', False):
            print("  ⏭️  POST /entries 非サポート - スキップ")
            self.test_results['skipped'] += 1
            return
        
        print("  ℹ️  データエントリ作成にはデータセットIDが必要")
        print("  ℹ️  実際の作成テストは手動確認が推奨されます")
        self.test_results['skipped'] += 1
    
    # ==========================================
    # ファイルアップロードAPI テスト
    # ==========================================
    
    def test_file_upload_operations(self):
        """ファイルアップロードテスト"""
        print(f"\n{'='*70}")
        print("📤 4. ファイルアップロードAPI テスト")
        print(f"{'='*70}")
        
        base_url = "https://rde-entry-api-arim.nims.go.jp/uploads"
        
        # OPTIONS チェック
        support = check_endpoint_availability(base_url, ['POST', 'GET'])
        self.test_results['options_checks']['uploads'] = support
        
        if not support.get('POST', False):
            print("  ⏭️  POST /uploads 非サポート - スキップ")
            self.test_results['skipped'] += 1
            return
        
        print("  ℹ️  ファイルアップロードは実際のバイナリデータが必要")
        print("  ℹ️  実際のアップロードテストは手動確認が推奨されます")
        self.test_results['skipped'] += 1
    
    # ==========================================
    # マテリアル管理API テスト
    # ==========================================
    
    def test_material_operations(self):
        """マテリアル共有グループ管理テスト"""
        print(f"\n{'='*70}")
        print("🧪 5. マテリアル管理API テスト")
        print(f"{'='*70}")
        
        # サンプルIDが必要なため、実際のテストは困難
        print("  ℹ️  マテリアル共有グループ操作には既存のサンプルIDが必要")
        print("  ℹ️  OPTIONS チェックのみ実施")
        
        sample_id = "dummy-sample-id"
        url = f"https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups"
        
        # OPTIONS チェック
        support = check_endpoint_availability(url, ['POST', 'DELETE', 'GET'])
        self.test_results['options_checks']['material_sharing'] = support
        
        self.test_results['skipped'] += 1
    
    # ==========================================
    # サマリー出力
    # ==========================================
    
    def _print_summary(self):
        """テスト結果サマリーを出力"""
        print(f"\n{'='*70}")
        print("📊 テスト結果サマリー")
        print(f"{'='*70}")
        
        print(f"\n総テスト数: {self.test_results['total']}")
        print(f"  ✅ 成功: {self.test_results['passed']}")
        print(f"  ❌ 失敗: {self.test_results['failed']}")
        print(f"  ⏭️  スキップ: {self.test_results['skipped']}")
        
        print(f"\n【OPTIONS チェック結果】")
        for endpoint, methods in self.test_results['options_checks'].items():
            print(f"\n  {endpoint}:")
            for method, supported in methods.items():
                symbol = "✅" if supported else "❌"
                print(f"    {symbol} {method}")
        
        print(f"\n【操作テスト結果】")
        for operation, result in self.test_results['operation_tests'].items():
            symbol = "✅" if result == 'PASS' else "⏭️" if 'SKIP' in result else "❌"
            print(f"  {symbol} {operation}: {result}")
        
        # 結果をJSONファイルに保存
        result_file = os.path.join(project_root, 'test_results', 'api_write_operations_test_results.json')
        os.makedirs(os.path.dirname(result_file), exist_ok=True)
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 詳細結果を保存: {result_file}")


# ==========================================
# メイン実行
# ==========================================

if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║  RDE API 書き込み系操作テスト (OPTIONS 判定付き)                      ║
║                                                                        ║
║  このテストは各エンドポイントの書き込み操作をテストします。           ║
║  既存データに影響を与えないよう、以下の手順で実施します:              ║
║                                                                        ║
║  1. OPTIONS メソッドで事前にサポート状況を確認                        ║
║  2. サポートされている操作のみ実施                                    ║
║  3. テストデータは作成後に自動削除                                    ║
║                                                                        ║
║  注意: ログインが必要です。先に bearer_tokens.json を用意してください ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)
    
    tester = TestRDEWriteOperations()
    
    try:
        tester.run_all_tests()
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*70}")
    print("🏁 テスト完了")
    print(f"{'='*70}\n")
