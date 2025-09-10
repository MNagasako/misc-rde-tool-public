import os
import json

class FileSaver:
    """
    ファイル保存専用クラス。
    - テキスト・JSON・バイナリ等の保存を担当
    """
    def save_text(self, path, text):
        dir_ = os.path.dirname(path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def save_json(self, path, obj):
        dir_ = os.path.dirname(path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def save_binary(self, path, data):
        dir_ = os.path.dirname(path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
