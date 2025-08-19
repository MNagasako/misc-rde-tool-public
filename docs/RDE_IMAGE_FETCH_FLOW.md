
# RDE画像取得フロー（ARIM-RDE-TOOL）

## 概要
本ドキュメントは、ARIM-RDE-TOOLにおけるRDE画像（BLOB画像）取得の一連の流れをまとめたものです。API・WebView遷移・IDの扱いなど、実装・デバッグ時の参照用とします。

---

## RDEのデータ階層モデル

RDE内のデータセットは、以下のような3階層構造となっています。

```
課題番号（grantNumber）
└─ データセット名（subjectTitle/name）
    └─ データセット詳細名（data[].attributes.name）
```

- **課題番号（grantNumber）**
  - 例: `JPMXP1222TU0195`
  - API: `/datasets?searchWords={grantNumber}`
  - JSONフィールド: `attributes.grantNumber`

- **データセット名**
  - 例: `A-22-TU-0079　VERSA_01`
  - API: `/datasets?searchWords={grantNumber}`
  - JSONフィールド: `attributes.name` または `attributes.subjectTitle`
  - `data[].id` が datasetId となる

- **データセット詳細名**
  - 例: `鉄鋼材料破断面観察`
  - API: `/data?filter[dataset.id]={datasetId}`
  - JSONフィールド: `data[].attributes.name`
  - `data[].id` が datasetDetailId（画像取得に使うID）
  - datatree.jsonには attributes（instrument情報など詳細属性）も格納

### datatree.json格納例

#### dataset_detail要素（データセット詳細ディレクトリ情報）
```json
{
  "id3": "a4865a7a-56c1-42bf-b3f9-d7c75917ec51",
  "type": "dataset_detail",
  "subdir": "C:/vscode/rde/src/output/datasets/JPMXP1222TU0195/A-22-TU-0079　VERSA_01",
  "arim_id": "JPMXP1222TU0195",
  "parent_dataset_id": "a4865a7a-56c1-42bf-b3f9-d7c75917ec51"
}
```

#### dataset_detail3要素（データセット詳細名・属性付き）
```json
{
  "data_id": "012ba9ce-1bed-4ffc-be3e-176545a134e8",
  "name": "鉄鋼材料破断面観察",
  "type": "dataset_detail3",
  "subdir": "output/datasets/JPMXP1222TU0195/A-22-TU-0079　VERSA_01/鉄鋼材料破断面観察",
  "arim_id": "a4865a7a-56c1-42bf-b3f9-d7c75917ec51",
  "parent_dataset_id": "a4865a7a-56c1-42bf-b3f9-d7c75917ec51",
  "attributes": {
    "dataNumber": 1,
    "name": "鉄鋼材料破断面観察",
    // ...他属性...
  }
}
```
