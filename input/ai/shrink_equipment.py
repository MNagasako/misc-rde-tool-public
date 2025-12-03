
import json

input_path = r"c:\vscode\rde\input\ai\EQUIPMENTS_pretty.json"
output_path = r"c:\vscode\rde\input\ai\EQUIPMENTS_min.json"

with open(input_path, encoding="utf-8") as f:
    data = json.load(f)

# 設備ID, 装置名_日, 型番, キーワード, 仕様・特徴, 分類のみ抽出
min_data = [
    {
        "設備ID": e.get("設備ID"),
        "装置名_日": e.get("装置名_日"),
        "型番": e.get("型番"),
        "キーワード": e.get("キーワード").split() if e.get("キーワード") else [],
        "仕様・特徴": e.get("仕様・特徴"),
        "分類": e.get("分類")
    }
    for e in data
]

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(min_data, f, ensure_ascii=False, indent=2)

print(f"縮小済みJSONを保存しました: {output_path}")
