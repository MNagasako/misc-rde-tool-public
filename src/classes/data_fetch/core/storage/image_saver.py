import os
import base64

class ImageSaver:
    """
    画像保存専用クラス。
    - バイナリ/BASE64画像の保存を担当
    """
    def save_image(self, path, data):
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)

    def save_base64_image(self, path, b64str):
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(base64.b64decode(b64str))
