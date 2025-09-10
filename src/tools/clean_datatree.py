import json
import os

# datatree.jsonのパス
DATATREE_PATH = r"c:\vscode\rde\src\output\datasets\.datatree.json"

# 正しいgrantNumberとsubjectTitleの対応表（例）
GRANT_TITLE_MAP = {
    "JPMXP1222TU0195": "鉄鋼材料の機械的性質",
    # 必要に応じて他のgrantNumberも追加
}

def clean_datatree():
    with open(DATATREE_PATH, encoding="utf-8") as f:
        datatree = json.load(f)
    # 不正なキーを削除
    valid_keys = set(GRANT_TITLE_MAP.keys())
    to_del = [k for k in datatree if k not in valid_keys]
    for k in to_del:
        print(f"remove invalid key: {k}")
        del datatree[k]
    # subjectTitle修正
    for grant, title in GRANT_TITLE_MAP.items():
        if grant in datatree:
            datatree[grant]["subjectTitle"] = title
    with open(DATATREE_PATH, "w", encoding="utf-8") as f:
        json.dump(datatree, f, ensure_ascii=False, indent=2)
    print("datatree.json cleaned.")

if __name__ == "__main__":
    clean_datatree()
