import json

input_path = r"c:\vscode\rde\input\ai\EQUIPMENTS_pretty.json"
output_path = r"c:\vscode\rde\input\ai\EQUIPMENTS_min_compact.json"

with open(input_path, encoding="utf-8") as f:
    data = json.load(f)

# 項目順: 設備ID, 装置名_日, 型番, キーワード, 仕様・特徴, 分類
compact_data = [
    [
        e.get("設備ID"),
        e.get("装置名_日"),
        e.get("型番"),
        e.get("キーワード").split() if e.get("キーワード") else [],
        e.get("仕様・特徴"),
        e.get("分類")
    ]
    for e in data
]

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(compact_data, f, ensure_ascii=False, separators=(",", ":"))

print(f"コンパクトJSONを保存しました: {output_path}")
