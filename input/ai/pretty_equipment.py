import json
import os

# 入力・出力ファイルパス
input_path = os.path.join(os.path.dirname(__file__), "EQUIPMENTS.json")
output_path = os.path.join(os.path.dirname(__file__), "EQUIPMENTS_pretty.json")

def load_json_auto_encoding(path):
    encodings = ["utf-8", "utf-8-sig", "cp932"]
    for enc in encodings:
        try:
            with open(path, encoding=enc) as f:
                return json.load(f)
        except Exception:
            continue
    raise Exception("JSONの読み込みに失敗しました。エンコーディングを確認してください。")

def pretty_print_json(input_path, output_path):
    data = load_json_auto_encoding(input_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"整形済みJSONを保存しました: {output_path}")

if __name__ == "__main__":
    pretty_print_json(input_path, output_path)
