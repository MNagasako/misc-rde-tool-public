import sys
import os
from config.common import LOGIN_FILE, OUTPUT_DIR, DEBUG_LOG_PATH, get_base_dir, get_static_resource_path
import json
import inspect
# === セッション管理ベースのプロキシ対応 ===
from classes.utils.api_request_helper import api_request
from datetime import datetime
import threading
import functools
DEBUG_LOG_LOCK = threading.Lock()
MAIN_DIR = get_base_dir()
def read_login_info():
    """シェル実行時もバイナリ実行時も対応する login.txt の読み込み"""
    # config.commonのLOGIN_FILEを使用（パス解決は既に適切に処理済み）
    filepath = LOGIN_FILE

    if not os.path.exists(filepath):
        # ログメッセージを統一（INFOレベル）
        print(f"[INFO] login.txt が見つかりません: {filepath}")
        # login.txtがない場合でもエラーとしては扱わず、None を返す
        return None, None, None

    try:
        with open(filepath, encoding='utf-8') as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                user = lines[0].strip()
                password = lines[1].strip()
                extra = lines[2].strip() if len(lines) >= 3 else None
                return user, password, extra
            elif len(lines) == 1:
                # 1行しかない場合（ユーザー名のみ）
                user = lines[0].strip()
                print(f"[WARN] login.txt にパスワードが設定されていません")
                return user, None, None
            else:
                # 空ファイル
                print(f"[WARN] login.txt が空です")
                return None, None, None
    except Exception as e:
        print(f"[WARN] ログイン情報読込エラー: {e}")
        return None, None, None



def parse_cookies_txt(filepath):
    """cookies_rde.txt から requests用のdictを生成"""
    cookies = {}
    if not os.path.exists(filepath):
        print(f"Cookieファイルが存在しません: {filepath}\nWebViewでログインし直してください。")
        return cookies
    try:
        with open(filepath, encoding='utf-8') as f:
            data = f.read()
            for pair in data.strip().split(';'):
                if '=' in pair:
                    name, value = pair.strip().split('=', 1)
                    cookies[name.strip()] = value.strip()
    except Exception as e:
        print(f"Cookieファイル読込エラー: {e}")
    return cookies



def external_path(relative_path):
    """
    バイナリやスクリプトと同じ場所に置いた外部ファイルへのパスを取得。
    - バイナリ：その .exe のある場所
    - スクリプト：その .py のある場所
    """
    if getattr(sys, 'frozen', False):
        # バイナリ実行中
        base_path = os.path.dirname(sys.executable)
    else:
        # スクリプト実行中
        base_path = os.path.dirname(MAIN_DIR)
    return os.path.join(base_path, relative_path)




def save_datatree_json(path, datatree):
    """datatreeリストを指定パスに保存"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(datatree, f, ensure_ascii=False, indent=2)
    
def load_js_template(template_name):
    """JavaScriptテンプレートファイルを読み込み"""
    from config.common import get_static_resource_path
    js_path = get_static_resource_path(os.path.join('js_templates', template_name))
    with open(js_path, 'r', encoding='utf-8') as f:
        return f.read()