"""
RDE API 実装ベーステスト（実際のアプリケーションコードと完全一致）

このテストは実際のアプリケーションコードから抽出した正確なヘッダとペイロード構造を使用します。

実装元:
- POST /datasets: src/classes/dataset/core/dataset_open_logic.py:783-835
- PATCH /datasets/{id}: src/classes/dataset/core/dataset_edit_functions.py:250-450

実行方法:
    python tests/test_rde_api_production_match.py
"""

import sys
import os
import json
import time
from typing import Optional, Dict

# プロジェクトルートとsrcをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(project_root, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, project_root)

from classes.managers.token_manager import TokenManager
from classes.utils.api_request_helper import api_request

# ==========================================
# テンプレートID取得ヘルパー
# ==========================================

def get_available_templates(bearer_token: str) -> list:
    """
    利用可能なテンプレート一覧を取得
    
    Returns:
        list: テンプレート情報のリスト [{"id": "...", "nameJa": "..."}, ...]
    """
    url = "https://rde-api.nims.go.jp/datasetTemplates"
    
    try:
        response = api_request('GET', url, bearer_token=bearer_token, timeout=10)
        
        if response and response.status_code == 200:
            data = response.json()
            templates = []
            
            for template in data.get('data', []):
                templates.append({
                    'id': template.get('id'),
                    'nameJa': template.get('attributes', {}).get('nameJa'),
                    'nameEn': template.get('attributes', {}).get('nameEn'),
                    'datasetType': template.get('attributes', {}).get('datasetType'),
                    'version': template.get('attributes', {}).get('version')
                })
            
            return templates
        else:
            print(f"[ERROR] テンプレート取得失敗: {response.status_code if response else 'No Response'}")
            return []
            
    except Exception as e:
        print(f"[ERROR] テンプレート取得エラー: {e}")
        return []


# ==========================================
# Production 準拠ヘッダ作成
# ==========================================

def create_production_headers(bearer_token: str) -> Dict[str, str]:
    """
    実際のアプリケーションコードと完全に一致するヘッダを作成
    
    実装元: dataset_open_logic.py:795-808, dataset_edit_functions.py:286-299
    """
    return {
        "Accept": "application/vnd.api+json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Authorization": f"Bearer {bearer_token}",
        "Connection": "keep-alive",
        "Content-Type": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }


# ==========================================
# Production 準拠ペイロード作成
# ==========================================

def create_production_dataset_payload(
    group_id: str,
    manager_id: str,
    dataset_name: str = "APIテスト_データセット",
    grant_number: str = "20250930-2test",  # 既存の付与番号（新規作成不可）
    template_id: str = "ARIM-R6_TU-504_TEM-STEM_20241121",
    dataset_type: str = "ANALYSIS",
    share_core_scope: bool = False,
    anonymize: bool = False
) -> Dict:
    """
    実際のアプリケーションコードと完全に一致するPOSTペイロードを作成
    
    実装元: dataset_open_logic.py:84-105
    
    注意: template_id は実際に存在する有効なIDを指定する必要があります。
    テンプレート一覧は以下で取得可能:
      GET https://rde-api.nims.go.jp/datasetTemplates
    
    実際の動作例:
    {
      "data": {
        "type": "dataset",
        "attributes": {
          "datasetType": "ANALYSIS",
          "name": "test4",
          "grantNumber": "20250930-2test",
          "embargoDate": "2027-03-31T03:00:00.000Z",
          "dataListingType": "GALLERY",
          "sharingPolicies": [...],
          "isAnonymized": false
        },
        "relationships": {
          "group": {"data": {"type": "group", "id": "..."}},
          "manager": {"data": {"type": "user", "id": "..."}},
          "template": {"data": {"type": "datasetTemplate", "id": "..."}}
        }
      }
    }
    """
    # 実際の動作例に合わせて2027年に設定
    embargo_date_iso = "2027-03-31T03:00:00.000Z"
    
    payload = {
        "data": {
            "type": "dataset",
            "attributes": {
                "datasetType": dataset_type,
                "name": dataset_name,
                "grantNumber": grant_number,
                "embargoDate": embargo_date_iso,
                "dataListingType": "GALLERY",
                "sharingPolicies": [
                    {
                        "scopeId": "4df8da18-a586-4a0d-81cb-ff6c6f52e70f",
                        "permissionToView": True,
                        "permissionToDownload": False
                    },
                    {
                        "scopeId": "22aec474-bbf2-4826-bf63-60c82d75df41",
                        "permissionToView": share_core_scope,
                        "permissionToDownload": False
                    }
                ],
                "isAnonymized": anonymize
            },
            "relationships": {
                "group": {
                    "data": {
                        "type": "group",
                        "id": group_id
                    }
                },
                "manager": {
                    "data": {
                        "type": "user",
                        "id": manager_id
                    }
                },
                "template": {
                    "data": {
                        "type": "datasetTemplate",
                        "id": template_id
                    }
                }
            }
        }
    }
    
    return payload


def create_production_dataset_update_payload(
    dataset_id: str,
    original_dataset: Dict,
    updates: Dict[str, any]
) -> Dict:
    """
    実際のアプリケーションコードと完全に一致するPATCHペイロードを作成
    
    実装元: dataset_edit_functions.py:12-247
    
    実際の動作例（PATCH時）:
    {
      "data": {
        "type": "dataset",
        "id": "fc33cf4d-ddec-4226-b26b-0e52fe9727a5",
        "attributes": {
          "grantNumber": "20251001-test-111",
          "name": "20251001-test-111",
          "description": "",
          "relatedLinks": [],
          "tags": [],
          "citationFormat": "",
          "contact": "",
          "taxonomyKeys": [],
          "dataListingType": "GALLERY",
          "isDataEntryProhibited": false,
          "embargoDate": "2027-03-31T03:00:00.000Z",
          "sharingPolicies": [...],
          "isAnonymized": false
        },
        "relationships": {
          "relatedDatasets": {"data": []},
          "applicant": {"data": {"id": "...", "type": "user"}},
          "instruments": {"data": [{"id": "...", "type": "instrument"}]},
          "manager": {"data": {"id": "...", "type": "user"}},
          "template": {"data": {"id": "...", "type": "datasetTemplate"}},
          "license": {"data": null}
        }
      }
    }
    """
    original_attrs = original_dataset.get("attributes", {})
    original_relationships = original_dataset.get("relationships", {})
    
    # 既存値をベースに更新
    attributes = {
        "name": updates.get("name", original_attrs.get("name")),
        "grantNumber": updates.get("grantNumber", original_attrs.get("grantNumber")),
        "description": updates.get("description", original_attrs.get("description", "")),
        "embargoDate": updates.get("embargoDate", original_attrs.get("embargoDate")),
        "contact": updates.get("contact", original_attrs.get("contact", "")),
        "taxonomyKeys": updates.get("taxonomyKeys", original_attrs.get("taxonomyKeys", [])),
        "relatedLinks": updates.get("relatedLinks", original_attrs.get("relatedLinks", [])),
        "tags": updates.get("tags", original_attrs.get("tags", [])),
        "citationFormat": updates.get("citationFormat", original_attrs.get("citationFormat", "")),
        "dataListingType": updates.get("dataListingType", original_attrs.get("dataListingType", "GALLERY")),
        "isAnonymized": updates.get("isAnonymized", original_attrs.get("isAnonymized", False)),
        "isDataEntryProhibited": updates.get("isDataEntryProhibited", original_attrs.get("isDataEntryProhibited", False)),
        "sharingPolicies": updates.get("sharingPolicies", original_attrs.get("sharingPolicies", []))
    }
    
    # 既存リレーションシップを保持
    relationships = {}
    
    # 重要なリレーションシップを保持（実際の動作例に基づく）
    important_relationships = [
        "applicant", "dataOwners", "instruments", 
        "manager", "template", "group", "license"
    ]
    
    for rel_name in important_relationships:
        if rel_name in original_relationships:
            relationships[rel_name] = original_relationships[rel_name]
    
    # 関連データセット（実際の例では空配列でも含まれる）
    if "relatedDatasets" in updates:
        relationships["relatedDatasets"] = {
            "data": updates["relatedDatasets"]
        }
    elif "relatedDatasets" in original_relationships:
        relationships["relatedDatasets"] = original_relationships["relatedDatasets"]
    else:
        # デフォルトで空配列を設定（実際の動作例に準拠）
        relationships["relatedDatasets"] = {"data": []}
    
    # ライセンス（実際の動作例では {"data": null} の形式）
    # important_relationshipsで既に処理されているが、明示的に上書き可能
    if "license" in updates:
        if updates["license"]:
            relationships["license"] = {
                "data": {
                    "type": "license",
                    "id": updates["license"]
                }
            }
        else:
            relationships["license"] = {"data": None}
    # 既にimportant_relationshipsで処理済みなので、ここでは何もしない
    
    payload = {
        "data": {
            "type": "dataset",
            "id": dataset_id,  # 必須
            "attributes": attributes,
            "relationships": relationships
        }
    }
    
    return payload


# ==========================================
# テストクラス
# ==========================================

class TestRDEProductionAPI:
    """Production コード準拠APIテスト"""
    
    def __init__(self):
        self.token_manager = TokenManager.get_instance()
        self.bearer_token = None
        self.created_dataset_id = None
        self.base_url = "https://rde-api.nims.go.jp"  # ベースURL
        
        # テスト結果
        self.results = {
            'post_dataset': 'NOT_RUN',
            'patch_dataset': 'NOT_RUN',
            'cleanup': 'NOT_RUN'
        }
    
    def setup(self):
        """テスト環境セットアップ"""
        print("\n" + "="*70)
        print("🔧 テスト環境セットアップ")
        print("="*70)
        
        # Bearer Token 取得
        self.bearer_token = self.token_manager.get_access_token('rde.nims.go.jp')
        
        if not self.bearer_token:
            print("❌ Bearer Token が取得できません")
            print("   先にログインしてください: output/.private/bearer_tokens.json")
            return False
        
        print(f"✅ Bearer Token 取得成功: {self.bearer_token[:20]}...")
        return True
    
    def test_post_dataset(self, group_id: str, manager_id: str):
        """
        POST /datasets テスト
        
        実装元: dataset_open_logic.py:783-835
        """
        print("\n" + "="*70)
        print("🧪 テスト1: POST /datasets (データセット作成)")
        print("="*70)
        
        # テンプレート一覧を取得して表示
        print("\n📋 利用可能なテンプレート取得中...")
        templates = get_available_templates(self.bearer_token)
        
        if templates:
            print(f"  取得件数: {len(templates)}件")
            print(f"\n  最初の5件:")
            for i, tmpl in enumerate(templates[:5], 1):
                print(f"    {i}. {tmpl['id']}")
                print(f"       名前: {tmpl['nameJa']}")
                print(f"       タイプ: {tmpl['datasetType']}")
        else:
            print("  ⚠️ テンプレート取得失敗")
        
        url = "https://rde-api.nims.go.jp/datasets"
        
        # Production準拠ヘッダ
        headers = create_production_headers(self.bearer_token)
        
        # テンプレートIDを最初の利用可能なものに設定（存在する場合）
        template_id = templates[0]['id'] if templates else "ARIM-R6_TU-504_TEM-STEM_20241121"
        
        # Production準拠ペイロード
        # 実際の動作例に合わせた形式
        # grantNumberは既存のもののみ使用可能（新規作成不可）
        
        payload = create_production_dataset_payload(
            group_id=group_id,
            manager_id=manager_id,
            dataset_name=f"APIテスト_データセット_{int(time.time())}",
            grant_number="20250930-2test",  # 既存の付与番号（ハードコード）
            template_id=template_id,
            share_core_scope=False,
            anonymize=False
        )
        
        print(f"\n📤 リクエスト:")
        print(f"  URL: {url}")
        print(f"  Method: POST")
        print(f"  Payload preview:")
        print(f"    - Dataset Name: {payload['data']['attributes']['name']}")
        print(f"    - Grant Number: {payload['data']['attributes']['grantNumber']}")
        print(f"    - Group ID: {payload['data']['relationships']['group']['data']['id']}")
        print(f"    - Manager ID: {payload['data']['relationships']['manager']['data']['id']}")
        print(f"    - Template ID: {payload['data']['relationships']['template']['data']['id']}")
        
        # デバッグ: 完全なペイロードを表示
        print(f"\n🔍 完全なペイロード:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        
        try:
            response = api_request("POST", url, bearer_token=self.bearer_token,
                                 headers=headers, json_data=payload, timeout=15)
            
            if response is None:
                print("\n❌ レスポンスなし")
                self.results['post_dataset'] = 'FAIL (No Response)'
                return False
            
            print(f"\n📥 レスポンス:")
            print(f"  Status Code: {response.status_code}")
            
            # デバッグ: レスポンスヘッダとボディを詳細表示
            if response.status_code != 201:
                print(f"\n🔍 レスポンスヘッダ:")
                for key, value in response.headers.items():
                    print(f"    {key}: {value}")
                print(f"\n🔍 レスポンスボディ:")
                print(f"  {response.text}")
            
            if response.status_code == 201:
                data = response.json()
                self.created_dataset_id = data.get("data", {}).get("id")
                dataset_name = data.get("data", {}).get("attributes", {}).get("name")
                
                print(f"\n✅ データセット作成成功!")
                print(f"  ID: {self.created_dataset_id}")
                print(f"  Name: {dataset_name}")
                
                self.results['post_dataset'] = 'PASS'
                return True
                
            elif response.status_code == 404:
                print(f"\n⚠️  404 エラー: アクセス制限")
                print(f"  詳細: {response.text[:500]}")
                print(f"\n  【原因】アカウントに管理者権限がない可能性があります")
                self.results['post_dataset'] = 'SKIP (404 - Permission)'
                return False
                
            elif response.status_code == 403:
                print(f"\n⚠️  403 エラー: 権限不足")
                print(f"  詳細: {response.text[:500]}")
                self.results['post_dataset'] = 'SKIP (403 - Forbidden)'
                return False
            
            elif response.status_code == 500:
                print(f"\n❌ 500 エラー: サーバー内部エラー")
                print(f"  詳細: {response.text[:1000]}")
                print(f"\n  【考えられる原因】")
                print(f"    1. Template ID が無効または存在しない")
                print(f"    2. Group ID が無効または存在しない")
                print(f"    3. Manager ID が無効または存在しない")
                print(f"    4. sharingPolicies の scopeId が無効")
                print(f"    5. サーバー側の一時的な問題")
                print(f"\n  【対処方法】")
                print(f"    - 上記の「利用可能なテンプレート」から有効なIDを確認")
                print(f"    - Group ID と Manager ID が正しいか再確認")
                print(f"    - 実際のアプリケーションで同じ操作ができるか確認")
                self.results['post_dataset'] = 'FAIL (500 - Server Error)'
                return False
                
            else:
                print(f"\n❌ データセット作成失敗")
                print(f"  詳細: {response.text[:500]}")
                self.results['post_dataset'] = f'FAIL ({response.status_code})'
                return False
                
        except Exception as e:
            print(f"\n❌ エラー発生: {e}")
            self.results['post_dataset'] = f'ERROR ({e})'
            return False
    
    def test_patch_dataset(self):
        """
        PATCH /datasets/{id} テスト
        
        実装元: dataset_edit_functions.py:250-450
        """
        if not self.created_dataset_id:
            print("\n⏭️  PATCH テストスキップ (POSTが未実行)")
            self.results['patch_dataset'] = 'SKIP (No Dataset)'
            return False
        
        print("\n" + "="*70)
        print(f"🧪 テスト2: PATCH /datasets/{self.created_dataset_id}")
        print("="*70)
        
        # まず元のデータを取得（実際のRDE APIエンドポイントを使用）
        # 参考: GET https://rde-api.nims.go.jp/datasets/{id}?updateViews=true&include=...
        query_params = (
            "updateViews=true"
            "&include=releases,applicant,program,manager,relatedDatasets,template,instruments,license,sharingGroups"
            "&fields[release]=id,releaseNumber,version,doi,note,releaseTime"
            "&fields[user]=id,userName,organizationName,isDeleted"
            "&fields[group]=id,name"
            "&fields[datasetTemplate]=id,nameJa,nameEn,version,datasetType,isPrivate,workflowEnabled"
            "&fields[instrument]=id,nameJa,nameEn,status"
            "&fields[license]=id,url,fullName"
        )
        
        url_get = f"{self.base_url}/datasets/{self.created_dataset_id}?{query_params}"
        
        # GET用のヘッダー（Bearer Token付き）
        headers_get = {
            'Authorization': f'Bearer {self.bearer_token}',
            'Accept': 'application/vnd.api+json',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Host': 'rde-api.nims.go.jp',
            'Origin': 'https://rde.nims.go.jp',
            'Referer': 'https://rde.nims.go.jp/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        print(f"\n📥 元のデータセット情報を取得中...")
        response_get = api_request('GET', url_get, headers=headers_get, timeout=15)
        
        if not response_get or response_get.status_code != 200:
            status = response_get.status_code if response_get else 'No Response'
            print(f"❌ 元のデータセット情報取得失敗: HTTP {status}")
            if response_get:
                print(f"  詳細: {response_get.text[:500]}")
            self.results['patch_dataset'] = f'FAIL (Cannot GET - {status})'
            return False
        
        original_dataset = response_get.json().get("data", {})
        print(f"✅ 元のデータセット情報取得成功")
        
        # Production準拠ヘッダ
        headers = create_production_headers(self.bearer_token)
        
        # Production準拠ペイロード (更新内容)
        updates = {
            "description": "APIテストによる更新 - Production準拠テスト",
            "tags": ["APIテスト", "Production準拠"],
            "relatedLinks": [
                {
                    "title": "テストサイト",
                    "url": "https://example.com/test"
                }
            ]
        }
        
        payload = create_production_dataset_update_payload(
            dataset_id=self.created_dataset_id,
            original_dataset=original_dataset,
            updates=updates
        )
        
        url_patch = f"{self.base_url}/datasets/{self.created_dataset_id}"
        
        print(f"\n📤 リクエスト:")
        print(f"  URL: {url_patch}")
        print(f"  Method: PATCH")
        print(f"  更新内容:")
        print(f"    - Description: {updates['description']}")
        print(f"    - Tags: {updates['tags']}")
        print(f"    - Related Links: {len(updates['relatedLinks'])}件")
        
        try:
            response = api_request('PATCH', url_patch, headers=headers,
                                 json_data=payload, timeout=15)
            
            if response is None:
                print("\n❌ レスポンスなし")
                self.results['patch_dataset'] = 'FAIL (No Response)'
                return False
            
            print(f"\n📥 レスポンス:")
            print(f"  Status Code: {response.status_code}")
            
            if response.status_code in (200, 201):
                data = response.json()
                updated_desc = data.get("data", {}).get("attributes", {}).get("description")
                
                print(f"\n✅ データセット更新成功!")
                print(f"  Updated Description: {updated_desc[:100]}...")
                
                self.results['patch_dataset'] = 'PASS'
                return True
                
            elif response.status_code == 404:
                print(f"\n⚠️  404 エラー: アクセス制限")
                print(f"  詳細: {response.text[:500]}")
                self.results['patch_dataset'] = 'SKIP (404 - Permission)'
                return False
                
            else:
                print(f"\n❌ データセット更新失敗")
                print(f"  詳細: {response.text[:500]}")
                self.results['patch_dataset'] = f'FAIL ({response.status_code})'
                return False
                
        except Exception as e:
            print(f"\n❌ エラー発生: {e}")
            self.results['patch_dataset'] = f'ERROR ({e})'
            return False
    
    def cleanup(self, skip_cleanup: bool = False):
        """
        作成したデータセットを削除
        
        Args:
            skip_cleanup: True の場合、削除をスキップして手動削除を促す
        """
        if not self.created_dataset_id:
            self.results['cleanup'] = 'SKIP (No Dataset)'
            return
        
        print("\n" + "="*70)
        print("🧹 クリーンアップ")
        print("="*70)
        
        if skip_cleanup:
            print(f"\n⚠️  削除スキップが指定されました")
            print(f"  作成されたデータセット: {self.created_dataset_id}")
            print(f"  URL: https://rde.nims.go.jp/rd            python tests/test_rde_api_production_match.pye/datasets/{self.created_dataset_id}")
            print(f"\n  【重要】テスト用データセットの削除について:")
            print(f"    - 自動削除はスキップされました")
            print(f"    - 必要に応じて手動で削除してください")
            print(f"    - RDE Web UI から削除可能です")
            self.results['cleanup'] = 'SKIPPED (--skip-cleanup が指定されました)'
            return
        
        # 自動削除を実行
        print(f"\n🗑️  データセットを削除中...")
        print(f"  ID: {self.created_dataset_id}")
        
        url = f"{self.base_url}/datasets/{self.created_dataset_id}"
        headers = {
            'Authorization': f'Bearer {self.bearer_token}',
            'Accept': 'application/vnd.api+json',
            'Content-Type': 'application/vnd.api+json'
        }
        
        try:
            response = api_request('DELETE', url, headers=headers, timeout=15)
            
            if response and response.status_code in (200, 204):
                print(f"✅ データセット削除成功")
                self.results['cleanup'] = 'PASS'
            else:
                status = response.status_code if response else 'No Response'
                print(f"⚠️  データセット削除失敗: HTTP {status}")
                print(f"  URL: https://rde.nims.go.jp/rde/datasets/{self.created_dataset_id}")
                print(f"  手動で削除してください")
                self.results['cleanup'] = f'FAIL (HTTP {status})'
                
        except Exception as e:
            print(f"❌ 削除中にエラー: {str(e)}")
            print(f"  URL: https://rde.nims.go.jp/rde/datasets/{self.created_dataset_id}")
            print(f"  手動で削除してください")
            self.results['cleanup'] = f'ERROR ({str(e)})'
    
    def print_summary(self):
        """テスト結果サマリー"""
        print("\n" + "="*70)
        print("📊 テスト結果サマリー")
        print("="*70)
        
        for test_name, result in self.results.items():
            symbol = "✅" if result == "PASS" else "⏭️" if "SKIP" in result else "❌"
            print(f"  {symbol} {test_name}: {result}")
        
        # 結果をJSONに保存
        result_file = os.path.join(project_root, 'test_results', 
                                   'production_match_test_results.json')
        os.makedirs(os.path.dirname(result_file), exist_ok=True)
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 結果保存: {result_file}")


# ==========================================
# メイン実行
# ==========================================

if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description='RDE API Production準拠テスト - POST/PATCHの動作確認'
    )
    parser.add_argument(
        '--skip-cleanup',
        action='store_true',
        help='テスト後のデータセット削除をスキップ (手動削除する場合)'
    )
    args = parser.parse_args()
    
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║  RDE API Production準拠テスト                                         ║
║                                                                        ║
║  実際のアプリケーションコードから抽出した正確なヘッダとペイロードで  ║
║  POST/PATCHが成功するまでテストします。                              ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)
    
    if args.skip_cleanup:
        print("⚠️  削除スキップモード: テスト後の自動削除は行われません\n")
    
    # グループIDとマネージャーIDを指定
    # ※実際の動作例から取得した値
    # 実際の動作例: group_id="27afd43a-0c9e-4e5f-93d7-c756233122a3"
    TEST_GROUP_ID = "27afd43a-0c9e-4e5f-93d7-c756233122a3"
    TEST_MANAGER_ID = "03b8fc123d0a67ba407dd2f06fe49768d9cbddca6438366632366466"
    
    if TEST_GROUP_ID == "あなたのグループID":
        print("⚠️  エラー: TEST_GROUP_ID と TEST_MANAGER_ID を実際の値に設定してください")
        print("\n例:")
        print('  TEST_GROUP_ID = "12345678-1234-1234-1234-123456789012"')
        print('  TEST_MANAGER_ID = "87654321-4321-4321-4321-210987654321"')
        sys.exit(1)
    
    tester = TestRDEProductionAPI()
    
    try:
        # セットアップ
        if not tester.setup():
            print("\n❌ セットアップ失敗")
            sys.exit(1)
        
        # テスト実行
        tester.test_post_dataset(TEST_GROUP_ID, TEST_MANAGER_ID)
        tester.test_patch_dataset()
        
    except KeyboardInterrupt:
        print("\n⚠️  ユーザーによる中断")
    
    finally:
        # クリーンアップ (引数に基づいて削除スキップ可能)
        tester.cleanup(skip_cleanup=args.skip_cleanup)
        
        # サマリー表示
        tester.print_summary()
    
    print("\n" + "="*70)
    print("🏁 テスト完了")
    print("="*70 + "\n")
