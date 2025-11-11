# RDE API エンドポイント完全マップ

**生成日:** 2025-11-10  
**ソースコード調査に基づく実装済みエンドポイント一覧**

---

## 目次

1. [ユーザー管理 API](#ユーザー管理-api)
2. [グループ管理 API](#グループ管理-api)
3. [データセット管理 API](#データセット管理-api)
4. [データエントリー管理 API](#データエントリー管理-api)
5. [ファイル管理 API](#ファイル管理-api)
6. [マテリアル管理 API](#マテリアル管理-api)
7. [装置情報 API](#装置情報-api)
8. [テンプレート API](#テンプレート-api)
9. [ライセンス API](#ライセンス-api)

---

## 凡例

- 🟢 **GET**: データ取得
- 🔵 **POST**: データ作成
- 🟡 **PATCH**: データ更新
- 🔴 **DELETE**: データ削除
- ✅ **実装確認済み**
- ⚠️ **テスト必要**

---

## ユーザー管理 API

### 🟢 GET /users/self

**説明:** 現在のログインユーザー情報を取得

**エンドポイント:**
```
https://rde-user-api.nims.go.jp/users/self
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (202行目)

**HTTPメソッド:** `GET`

**認証:** Bearer Token (rde.nims.go.jp)

**リクエスト例:**
```python
from classes.utils.api_request_helper import api_request

url = "https://rde-user-api.nims.go.jp/users/self"
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

response = api_request('GET', url, headers=headers)

if response and response.status_code == 200:
    user_data = response.json()
    print(f"ユーザーID: {user_data['id']}")
    print(f"ユーザー名: {user_data['userName']}")
    print(f"組織名: {user_data['organizationName']}")
```

**レスポンス例:**
```json
{
  "id": "user-123",
  "userName": "山田太郎",
  "organizationName": "物質・材料研究機構",
  "email": "example@nims.go.jp",
  "roles": ["RESEARCHER", "DATASET_MANAGER"]
}
```

**実装詳細:**
- 関数: `fetch_self_user_info_from_api()`
- 出力: `output/.temp/self.json`

---

### 🟢 GET /users/{user_id}

**説明:** 特定ユーザーの情報を取得

**エンドポイント:**
```
https://rde-user-api.nims.go.jp/users/{user_id}
```

**実装ファイル:**
- `src/classes/subgroup/core/subgroup_api_helper.py` (39行目)

**HTTPメソッド:** `GET`

**パスパラメータ:**
- `user_id`: ユーザーのUUID

**リクエスト例:**
```python
user_id = "abc123-def456-ghi789"
url = f"https://rde-user-api.nims.go.jp/users/{user_id}"

response = api_request('GET', url)
```

---

## グループ管理 API

### 🟢 GET /groups/root

**説明:** ルートグループ情報を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/groups/root?include=children,members
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (947行目)

**HTTPメソッド:** `GET`

**クエリパラメータ:**
- `include`: 含めるリレーション (`children`, `members`)

**リクエスト例:**
```python
url = "https://rde-api.nims.go.jp/groups/root?include=children,members"

response = api_request('GET', url)

if response and response.status_code == 200:
    group_data = response.json()
    for child in group_data['included']:
        if child['type'] == 'group':
            print(f"子グループ: {child['attributes']['name']}")
```

**レスポンス構造:**
```json
{
  "data": {
    "type": "group",
    "id": "root-group-id",
    "attributes": {
      "name": "ARIM",
      "description": "ルートグループ"
    },
    "relationships": {
      "children": {
        "data": [
          {"type": "group", "id": "child-group-1"},
          {"type": "group", "id": "child-group-2"}
        ]
      }
    }
  },
  "included": [...]
}
```

---

### 🟢 GET /groups/{group_id}

**説明:** 特定グループの詳細情報を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/groups/{group_id}?include=children,members
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (961行目)

**パスパラメータ:**
- `group_id`: グループのUUID

---

### 🔵 POST /groups

**説明:** 新規サブグループを作成

**エンドポイント:**
```
https://rde-api.nims.go.jp/groups
```

**実装ファイル:**
- `src/classes/subgroup/core/subgroup_api_helper.py` (798行目)
- `src/classes/subgroup/core/subgroup_api_client.py` (792行目)

**HTTPメソッド:** `POST`

**認証:** Bearer Token (rde.nims.go.jp)

**リクエストボディ:**
```json
{
  "data": {
    "type": "group",
    "attributes": {
      "name": "新規サブグループ",
      "description": "サブグループの説明"
    },
    "relationships": {
      "parent": {
        "data": {
          "type": "group",
          "id": "parent-group-id"
        }
      }
    }
  }
}
```

**実装例:**
```python
from net.http_helpers import proxy_post

api_url = "https://rde-api.nims.go.jp/groups"

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
    "Authorization": f"Bearer {bearer_token}"
}

payload = {
    "data": {
        "type": "group",
        "attributes": {
            "name": "研究グループA",
            "description": "研究グループAの説明"
        },
        "relationships": {
            "parent": {
                "data": {
                    "type": "group",
                    "id": "parent-group-uuid"
                }
            }
        }
    }
}

resp = proxy_post(api_url, headers=headers, json=payload, timeout=15)

if resp.status_code == 201:
    group_data = resp.json()
    print(f"グループ作成成功: {group_data['data']['id']}")
```

**レスポンス例:**
```json
{
  "data": {
    "type": "group",
    "id": "new-group-uuid",
    "attributes": {
      "name": "研究グループA",
      "description": "研究グループAの説明"
    }
  }
}
```

---

## データセット管理 API

### 🟢 GET /datasets

**説明:** データセット一覧を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/datasets?sort=-modified&page[limit]=5000&include=manager,releases
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (525行目)

**HTTPメソッド:** `GET`

**クエリパラメータ:**
- `sort`: ソート順 (`-modified`: 更新日降順)
- `page[limit]`: 取得件数上限
- `page[offset]`: オフセット
- `include`: 含めるリレーション (`manager`, `releases`, `template`, etc.)
- `searchWords`: 検索キーワード
- `fields[user]`: ユーザーフィールド指定
- `fields[release]`: リリースフィールド指定

**リクエスト例:**
```python
url = "https://rde-api.nims.go.jp/datasets"
params = {
    "sort": "-modified",
    "page[limit]": 50,
    "include": "manager,releases",
    "fields[user]": "id,userName,organizationName,isDeleted",
    "fields[release]": "version,releaseNumber"
}

response = api_request('GET', url, params=params)

if response and response.status_code == 200:
    datasets = response.json()['data']
    for ds in datasets:
        attrs = ds['attributes']
        print(f"データセット: {attrs['name']}")
        print(f"  課題番号: {attrs.get('grantNumber', 'N/A')}")
        print(f"  更新日: {attrs['modified']}")
```

**レスポンス構造:**
```json
{
  "data": [
    {
      "type": "dataset",
      "id": "dataset-uuid",
      "attributes": {
        "name": "実験データセットA",
        "description": "実験の説明",
        "grantNumber": "JPMXP1234567890",
        "datasetType": "ANALYSIS",
        "isOpen": false,
        "globalShareDataset": true,
        "created": "2025-01-01T00:00:00Z",
        "modified": "2025-01-10T00:00:00Z"
      },
      "relationships": {
        "manager": {
          "data": {"type": "user", "id": "user-uuid"}
        }
      }
    }
  ],
  "meta": {
    "totalCount": 100
  }
}
```

---

### 🟢 GET /datasets/{dataset_id}

**説明:** 特定データセットの詳細情報を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/datasets/{dataset_id}?updateViews=true&include=releases,applicant,program,manager,relatedDatasets,template,instruments,license,sharingGroups
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (482行目)

**HTTPメソッド:** `GET`

**パスパラメータ:**
- `dataset_id`: データセットのUUID

**クエリパラメータ:**
- `updateViews`: 閲覧数をカウントするか (`true` / `false`)
- `include`: 含めるリレーション
- `fields[...]`: フィールド指定

**リクエスト例:**
```python
dataset_id = "abc123-def456-ghi789"
url = f"https://rde-api.nims.go.jp/datasets/{dataset_id}"
params = {
    "updateViews": "true",
    "include": "releases,applicant,program,manager,template,instruments,license"
}

response = api_request('GET', url, params=params)

if response and response.status_code == 200:
    dataset = response.json()['data']
    attrs = dataset['attributes']
    print(f"データセット名: {attrs['name']}")
    print(f"公開状態: {'公開' if attrs['isOpen'] else '非公開'}")
```

---

### 🔵 POST /datasets

**説明:** 新規データセットを作成

**エンドポイント:**
```
https://rde-api.nims.go.jp/datasets
```

**実装ファイル:**
- `src/classes/dataset/core/dataset_open_logic.py` (783行目)

**HTTPメソッド:** `POST`

**認証:** Bearer Token (rde.nims.go.jp)

**Content-Type:** `application/vnd.api+json`

**リクエストボディ:**
```json
{
  "data": {
    "type": "dataset",
    "attributes": {
      "name": "新規データセット",
      "description": "データセットの説明",
      "grantNumber": "JPMXP1234567890",
      "datasetType": "ANALYSIS",
      "isOpen": false,
      "globalShareDataset": true,
      "tags": ["材料", "実験"],
      "relatedLinks": [
        {
          "url": "https://example.com",
          "label": "関連サイト"
        }
      ]
    },
    "relationships": {
      "template": {
        "data": {
          "type": "datasetTemplate",
          "id": "template-uuid"
        }
      },
      "program": {
        "data": {
          "type": "group",
          "id": "program-group-uuid"
        }
      },
      "team": {
        "data": {
          "type": "group",
          "id": "team-group-uuid"
        }
      }
    }
  }
}
```

**実装例:**
```python
from classes.utils.api_request_helper import api_request

url = "https://rde-api.nims.go.jp/datasets"

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json"
}

payload = {
    "data": {
        "type": "dataset",
        "attributes": {
            "name": "実験データセットA",
            "description": "実験Aの結果データ",
            "grantNumber": "JPMXP1234567890",
            "datasetType": "ANALYSIS",
            "isOpen": False,
            "globalShareDataset": True
        },
        "relationships": {
            "template": {
                "data": {
                    "type": "datasetTemplate",
                    "id": "template-uuid"
                }
            }
        }
    }
}

response = api_request('POST', url, json_data=payload, headers=headers, timeout=15)

if response and response.status_code == 201:
    dataset = response.json()['data']
    print(f"データセット作成成功: {dataset['id']}")
    print(f"データセット名: {dataset['attributes']['name']}")
```

**レスポンス例:**
```json
{
  "data": {
    "type": "dataset",
    "id": "new-dataset-uuid",
    "attributes": {
      "name": "実験データセットA",
      "description": "実験Aの結果データ",
      "grantNumber": "JPMXP1234567890",
      "created": "2025-11-10T12:00:00Z",
      "modified": "2025-11-10T12:00:00Z"
    }
  }
}
```

---

### 🟡 PATCH /datasets/{dataset_id}

**説明:** データセット情報を更新

**エンドポイント:**
```
https://rde-api.nims.go.jp/datasets/{dataset_id}
```

**実装ファイル:**
- `src/classes/dataset/core/dataset_edit_functions.py` (275行目)

**HTTPメソッド:** `PATCH`

**認証:** Bearer Token (rde.nims.go.jp)

**Content-Type:** `application/vnd.api+json`

**リクエストボディ:**
```json
{
  "data": {
    "type": "dataset",
    "id": "dataset-uuid",
    "attributes": {
      "name": "更新後のデータセット名",
      "description": "更新後の説明",
      "tags": ["新しいタグ"],
      "isAnonymized": false,
      "isDataEntryProhibited": false,
      "embargoDate": "2025-12-31",
      "citationFormat": "引用書式"
    },
    "relationships": {
      "license": {
        "data": {
          "type": "license",
          "id": "license-uuid"
        }
      }
    }
  }
}
```

**実装例:**
```python
from classes.utils.api_request_helper import api_request

dataset_id = "abc123-def456-ghi789"
url = f"https://rde-api.nims.go.jp/datasets/{dataset_id}"

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json"
}

payload = {
    "data": {
        "type": "dataset",
        "id": dataset_id,
        "attributes": {
            "name": "更新後のデータセット名",
            "description": "更新後の説明文"
        }
    }
}

response = api_request('PATCH', url, json_data=payload, headers=headers, timeout=15)

if response and response.status_code == 200:
    print("データセット更新成功")
```

---

## データエントリー管理 API

### 🟢 GET /data

**説明:** データエントリー一覧を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/data?filter[dataset.id]={dataset_id}&sort=-created&page[offset]=0&page[limit]=24&include=owner,sample,thumbnailFile,files
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (310行目)
- `src/classes/dataset/core/dataset_dataentry_logic.py` (56行目)

**HTTPメソッド:** `GET`

**クエリパラメータ:**
- `filter[dataset.id]`: データセットIDでフィルタ
- `sort`: ソート順 (`-created`: 作成日降順)
- `page[offset]`: オフセット
- `page[limit]`: 取得件数上限
- `include`: 含めるリレーション (`owner`, `sample`, `thumbnailFile`, `files`)

**リクエスト例:**
```python
dataset_id = "abc123-def456"
url = f"https://rde-api.nims.go.jp/data"
params = {
    "filter[dataset.id]": dataset_id,
    "sort": "-created",
    "page[offset]": 0,
    "page[limit]": 24,
    "include": "owner,sample,thumbnailFile,files"
}

response = api_request('GET', url, params=params)

if response and response.status_code == 200:
    data_entries = response.json()['data']
    for entry in data_entries:
        attrs = entry['attributes']
        print(f"エントリー名: {attrs.get('name', 'N/A')}")
```

---

### 🟢 GET /invoices/{entry_id}

**説明:** 特定データエントリーの詳細情報を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/invoices/{entry_id}?include=submittedBy,dataOwner,instrument
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (347行目)

**パスパラメータ:**
- `entry_id`: データエントリーのUUID

---

### 🔵 POST /entries (ARIM登録API)

**説明:** 新規データエントリーを作成

**エンドポイント:**
```
https://rde-entry-api-arim.nims.go.jp/entries
```

**バリデーション専用エンドポイント:**
```
https://rde-entry-api-arim.nims.go.jp/entries?validationOnly=true
```

**実装ファイル:**
- `src/classes/data_entry/core/data_register_logic.py` (315行目)

**HTTPメソッド:** `POST`

**認証:** Bearer Token (rde.nims.go.jp)

**Content-Type:** `application/vnd.api+json`

**リクエストボディ:**
```json
{
  "data": {
    "type": "data",
    "attributes": {
      "title": "実験データ1",
      "description": "実験の説明",
      "structuredData": {
        "field1": "value1",
        "field2": 123
      }
    },
    "relationships": {
      "dataset": {
        "data": {
          "type": "dataset",
          "id": "dataset-uuid"
        }
      }
    }
  }
}
```

**実装例:**
```python
from classes.utils.api_request_helper import api_request

# バリデーション実行
url_validation = "https://rde-entry-api-arim.nims.go.jp/entries?validationOnly=true"

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json"
}

payload = {
    "data": {
        "type": "data",
        "attributes": {
            "title": "実験データ1",
            "structuredData": {...}
        },
        "relationships": {
            "dataset": {
                "data": {
                    "type": "dataset",
                    "id": "dataset-uuid"
                }
            }
        }
    }
}

# バリデーションチェック
resp_validation = api_request('POST', url_validation, json_data=payload, headers=headers, timeout=60)

if resp_validation and resp_validation.status_code == 204:
    print("バリデーション成功")
    
    # 実際のデータ登録
    url = "https://rde-entry-api-arim.nims.go.jp/entries"
    resp = api_request('POST', url, json_data=payload, headers=headers, timeout=60)
    
    if resp and resp.status_code == 201:
        entry_data = resp.json()['data']
        print(f"データエントリー作成成功: {entry_data['id']}")
```

---

## ファイル管理 API

### 🔵 POST /uploads (ARIM登録API)

**説明:** ファイルをアップロード

**エンドポイント:**
```
https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}
```

**実装ファイル:**
- `src/classes/data_entry/core/data_register_logic.py` (641行目)

**HTTPメソッド:** `POST`

**認証:** Bearer Token (rde.nims.go.jp)

**Content-Type:** `application/octet-stream`

**クエリパラメータ:**
- `datasetId`: アップロード先データセットのUUID

**実装例:**
```python
from classes.utils.api_request_helper import post_binary

dataset_id = "abc123-def456"
url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"

# ファイルを読み込み
with open("sample.txt", "rb") as f:
    binary_data = f.read()

headers = {
    "Accept": "application/json"
}

response = post_binary(url, binary_data, headers=headers)

if response and response.status_code == 201:
    file_data = response.json()
    print(f"ファイルアップロード成功: {file_data['id']}")
    print(f"ファイル名: {file_data['fileName']}")
```

**レスポンス例:**
```json
{
  "id": "file-uuid",
  "fileName": "sample.txt",
  "fileSize": 1024,
  "contentType": "text/plain",
  "uploadedAt": "2025-11-10T12:00:00Z"
}
```

---

## マテリアル管理 API

### 🟢 GET /samples

**説明:** サンプル（マテリアル）一覧を取得

**エンドポイント:**
```
https://rde-material-api.nims.go.jp/samples?groupId={group_id}&page[limit]=1000&page[offset]=0&fields[sample]=names,description,composition
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (1047行目)

**HTTPメソッド:** `GET`

**認証:** Bearer Token (rde-material.nims.go.jp)

**クエリパラメータ:**
- `groupId`: グループIDでフィルタ
- `page[limit]`: 取得件数上限
- `page[offset]`: オフセット
- `fields[sample]`: 取得フィールド指定

**リクエスト例:**
```python
group_id = "group-uuid"
url = f"https://rde-material-api.nims.go.jp/samples"
params = {
    "groupId": group_id,
    "page[limit]": 1000,
    "page[offset]": 0,
    "fields[sample]": "names,description,composition"
}

response = api_request('GET', url, params=params)

if response and response.status_code == 200:
    samples = response.json()['data']
    for sample in samples:
        attrs = sample['attributes']
        print(f"サンプル: {attrs.get('names', {}).get('ja', 'N/A')}")
```

---

### 🟢 GET /samples/{sample_id}

**説明:** 特定サンプルの詳細情報を取得

**エンドポイント:**
```
https://rde-material-api.nims.go.jp/samples/{sample_id}?include=sharingGroups
```

**実装ファイル:**
- `src/classes/subgroup/core/subgroup_api_client.py` (277行目)

**パスパラメータ:**
- `sample_id`: サンプルのUUID

---

### 🔵 POST /samples/{sample_id}/relationships/sharingGroups

**説明:** サンプルにサブグループを追加

**エンドポイント:**
```
https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups
```

**実装ファイル:**
- `src/classes/subgroup/core/subgroup_api_client.py` (386行目)

**HTTPメソッド:** `POST`

**認証:** Bearer Token (rde-material.nims.go.jp)

**リクエストボディ:**
```json
{
  "data": [
    {
      "type": "group",
      "id": "group-uuid"
    }
  ]
}
```

**実装例:**
```python
from net.http_helpers import proxy_post

sample_id = "sample-uuid"
api_url = f"https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups"

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
    "Authorization": f"Bearer {material_token}"
}

payload = {
    "data": [
        {
            "type": "group",
            "id": "group-uuid-1"
        },
        {
            "type": "group",
            "id": "group-uuid-2"
        }
    ]
}

response = proxy_post(api_url, headers=headers, json=payload)

if response.status_code == 204:
    print("サブグループ追加成功")
```

---

### 🔴 DELETE /samples/{sample_id}/relationships/sharingGroups

**説明:** サンプルからサブグループを削除

**エンドポイント:**
```
https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups
```

**実装ファイル:**
- `src/classes/subgroup/core/subgroup_api_client.py` (479行目)

**HTTPメソッド:** `DELETE`

**認証:** Bearer Token (rde-material.nims.go.jp)

**リクエストボディ:**
```json
{
  "data": [
    {
      "type": "group",
      "id": "group-uuid"
    }
  ]
}
```

**実装例:**
```python
from net.http_helpers import proxy_delete

sample_id = "sample-uuid"
api_url = f"https://rde-material-api.nims.go.jp/samples/{sample_id}/relationships/sharingGroups"

headers = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
    "Authorization": f"Bearer {material_token}"
}

payload = {
    "data": [
        {
            "type": "group",
            "id": "group-uuid-to-remove"
        }
    ]
}

response = proxy_delete(api_url, headers=headers, json=payload)

if response.status_code == 204:
    print("サブグループ削除成功")
```

---

## 装置情報 API

### 🟢 GET /typeTerms

**説明:** 装置タイプ一覧を取得

**エンドポイント:**
```
https://rde-instrument-api.nims.go.jp/typeTerms?programId={program_id}
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (579行目)

**パラメータ:**
- `programId`: プログラムID（固定: `4bbf62be-f270-4a46-9682-38cd064607ba`）

---

### 🟢 GET /organizations

**説明:** 組織一覧を取得

**エンドポイント:**
```
https://rde-instrument-api.nims.go.jp/organizations
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (604行目)

---

### 🟢 GET /instruments

**説明:** 装置一覧を取得

**エンドポイント:**
```
https://rde-instrument-api.nims.go.jp/instruments?programId={program_id}&page[limit]=10000&sort=id&page[offset]=0
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (657行目)

---

## テンプレート API

### 🟢 GET /datasetTemplates

**説明:** データセットテンプレート一覧を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/datasetTemplates?programId={program_id}&teamId={team_id}&sort=id&page[limit]=10000&page[offset]=0&include=instruments
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (630行目)

**パラメータ:**
- `programId`: プログラムID
- `teamId`: チームID
- `include`: 含めるリレーション (`instruments`)

---

## ライセンス API

### 🟢 GET /licenses

**説明:** ライセンス一覧を取得

**エンドポイント:**
```
https://rde-api.nims.go.jp/licenses
```

**実装ファイル:**
- `src/classes/basic/core/basic_info_logic.py` (684行目)

**リクエスト例:**
```python
url = "https://rde-api.nims.go.jp/licenses"

response = api_request('GET', url)

if response and response.status_code == 200:
    licenses = response.json()['data']
    for license in licenses:
        attrs = license['attributes']
        print(f"ライセンス: {attrs['fullName']}")
        print(f"  URL: {attrs.get('url', 'N/A')}")
```

---

## エンドポイント一覧表

| エンドポイント | メソッド | 説明 | 実装ファイル |
|-------------|---------|------|------------|
| `/users/self` | GET | ユーザー情報取得 | `basic_info_logic.py` |
| `/users/{id}` | GET | 特定ユーザー情報 | `subgroup_api_helper.py` |
| `/groups/root` | GET | ルートグループ | `basic_info_logic.py` |
| `/groups/{id}` | GET | グループ詳細 | `basic_info_logic.py` |
| `/groups` | POST | グループ作成 | `subgroup_api_client.py` |
| `/datasets` | GET | データセット一覧 | `basic_info_logic.py` |
| `/datasets/{id}` | GET | データセット詳細 | `basic_info_logic.py` |
| `/datasets` | POST | データセット作成 | `dataset_open_logic.py` |
| `/datasets/{id}` | PATCH | データセット更新 | `dataset_edit_functions.py` |
| `/data` | GET | データエントリー一覧 | `basic_info_logic.py` |
| `/entries` | POST | データエントリー作成 | `data_register_logic.py` |
| `/uploads` | POST | ファイルアップロード | `data_register_logic.py` |
| `/samples` | GET | サンプル一覧 | `basic_info_logic.py` |
| `/samples/{id}` | GET | サンプル詳細 | `subgroup_api_client.py` |
| `/samples/{id}/relationships/sharingGroups` | POST | サブグループ追加 | `subgroup_api_client.py` |
| `/samples/{id}/relationships/sharingGroups` | DELETE | サブグループ削除 | `subgroup_api_client.py` |
| `/typeTerms` | GET | 装置タイプ一覧 | `basic_info_logic.py` |
| `/organizations` | GET | 組織一覧 | `basic_info_logic.py` |
| `/instruments` | GET | 装置一覧 | `basic_info_logic.py` |
| `/datasetTemplates` | GET | テンプレート一覧 | `basic_info_logic.py` |
| `/licenses` | GET | ライセンス一覧 | `basic_info_logic.py` |

---

**END OF DOCUMENT**
