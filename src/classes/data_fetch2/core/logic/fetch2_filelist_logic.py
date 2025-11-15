import json
import os
import logging
from qt_compat.widgets import QMessageBox
from qt_compat.core import QMetaObject, Qt, Q_ARG
from config.common import OUTPUT_DIR
from classes.utils.api_request_helper import api_request, fetch_binary, download_request  # refactored to use api_request_helper
from core.bearer_token_manager import BearerTokenManager

# ログ設定
logger = logging.getLogger(__name__)

def safe_show_message(parent, title, message, message_type="warning"):
    """
    スレッドセーフなメッセージ表示
    """
    if parent is None:
        return
    
    try:
        from qt_compat.core import QThread
        if hasattr(parent, 'thread') and parent.thread() != QThread.currentThread():
            # 別スレッドからの呼び出しの場合はメタオブジェクトを使用
            if message_type == "warning":
                QMetaObject.invokeMethod(parent, "show_warning_message", 
                                       Qt.QueuedConnection,
                                       Q_ARG(str, title),
                                       Q_ARG(str, message))
            elif message_type == "critical":
                QMetaObject.invokeMethod(parent, "show_critical_message", 
                                       Qt.QueuedConnection,
                                       Q_ARG(str, title),
                                       Q_ARG(str, message))
            elif message_type == "information":
                QMetaObject.invokeMethod(parent, "show_information_message", 
                                       Qt.QueuedConnection,
                                       Q_ARG(str, title),
                                       Q_ARG(str, message))
        else:
            # メインスレッドからの呼び出しの場合は直接表示
            if message_type == "warning":
                QMessageBox.warning(parent, title, message)
            elif message_type == "critical":
                QMessageBox.critical(parent, title, message)
            elif message_type == "information":
                QMessageBox.information(parent, title, message)
    except Exception as e:
        logger.error(f"メッセージボックス表示エラー: {e}")
        # フォールバック：ログのみ
        logger.error(f"[{message_type.upper()}] {title}: {message}")

# ファイルパスに使用できない文字を全角記号に置換
def replace_invalid_path_chars(s):
    if not s:
        return ""
    # Windowsの禁止文字: \ / : * ? " < > | 
    # 代表的な全角記号に置換
    table = str.maketrans({
        '\\': '￥',
        '/': '／',
        ':': '：',
        '*': '＊',
        '?': '？',
        '"': '”',
        '<': '＜',
        '>': '＞',
        '|': '｜',
    })
    return s.translate(table)

def download_all_files_from_files_json(data_id, bearer_token=None, parent=None, progress_callback=None):
    """
    dataFiles/{data_id}.json の data 配列内の各ファイルID・fileNameで全ファイルをダウンロードし保存
    保存先: output/rde/data/dataFiles/{data_id}/{fileName}
    
    Args:
        data_id: データID
        bearer_token: 認証トークン（省略時はBearerTokenManagerから取得）
        parent: 親ウィジェット
        progress_callback: プログレスコールバック関数 (current, total, message) -> None
    """
    from urllib.parse import unquote
    
    # Bearer Token統一管理システムで取得
    if not bearer_token:
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            logger.error("Bearer Tokenが取得できません。ログインを確認してください")
            safe_show_message(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。", "critical")
            return False
    
    files_json_path = os.path.normpath(os.path.join(OUTPUT_DIR, f'rde/data/dataFiles/{data_id}.json'))
    save_dir = os.path.normpath(os.path.join(OUTPUT_DIR, f'rde/data/dataFiles/{data_id}'))
    
    if not os.path.exists(files_json_path):
        error_msg = f"ファイルが存在しません: {files_json_path}"
        logger.error(error_msg)
        if parent:
            safe_show_message(parent, "エラー", error_msg, "warning")
        return
        
    try:
        with open(files_json_path, encoding="utf-8") as f:
            obj = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        error_msg = f"ファイル読み込みエラー: {files_json_path}, {e}"
        logger.error(error_msg)
        if parent:
            safe_show_message(parent, "エラー", error_msg, "warning")
        return
    
    file_entries = obj.get("data", [])
    os.makedirs(save_dir, exist_ok=True)
    
    # 画像ファイル（JPG/PNG）のみを抽出し、ベース名で重複を排除
    image_entries = []
    seen_basenames = set()
    skipped_count = 0
    for entry in file_entries:
        attrs = entry.get("attributes", {})
        fname = attrs.get("fileName")
        if fname:
            fext = os.path.splitext(fname)[1].lower()
            if fext in ['.jpg', '.jpeg', '.png']:
                # ベース名（拡張子を除く）を取得
                basename = os.path.splitext(fname)[0]
                # 重複チェック: 同じベース名のファイルは1回だけダウンロード
                if basename not in seen_basenames:
                    seen_basenames.add(basename)
                    image_entries.append(entry)
                    logger.debug(f"画像ファイル登録: {fname} (basename: {basename})")
                else:
                    skipped_count += 1
                    logger.debug(f"重複スキップ: {fname} (basename: {basename} は既に登録済み)")
    
    total_images = len(image_entries)
    if skipped_count > 0:
        logger.info(f"ファイルダウンロード開始: data_id={data_id}, 画像ファイル数={total_images}/{len(file_entries)} (重複{skipped_count}件除外)")
    else:
        logger.info(f"ファイルダウンロード開始: data_id={data_id}, 画像ファイル数={total_images}/{len(file_entries)}")
    downloaded_count = 0
    
    for idx, file_entry in enumerate(image_entries):
        file_id = file_entry.get("id")
        attributes = file_entry.get("attributes", {})
        file_name = attributes.get("fileName")
        
        if not file_id or not file_name:
            logger.warning(f"無効なファイル情報をスキップ: file_id={file_id}, file_name={file_name}")
            continue
        
        # プログレスコールバック更新
        if progress_callback:
            progress_callback(idx + 1, total_images, file_name)
            
        url = f"https://rde-api.nims.go.jp/files/{file_id}"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "*/*",
            "Referer": "https://rde.nims.go.jp/",
            "Origin": "https://rde.nims.go.jp",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        }
        
        try:
            resp = download_request(url, bearer_token=bearer_token, headers=headers, stream=True)  # use download_request for Response object
            if resp is None:
                logger.warning(f"リクエスト失敗: {url}")
                continue
            if resp.status_code == 422:
                # 422エラー（利用不可能なファイル）は警告としてログのみ
                logger.warning(f"ファイル利用不可: {file_name} (HTTP 422)")
                continue
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code}エラー: {file_name}")
                continue
            
            # Content-Dispositionヘッダーから正しいファイル名を取得
            from urllib.parse import unquote
            import re
            
            final_file_name = file_name
            cd = resp.headers.get('Content-Disposition')
            if cd:
                # filename*=UTF-8''... 形式を優先
                match_star = re.search(r"filename\*=(?:UTF-8'')?([^;\r\n]+)", cd)
                if match_star:
                    final_file_name = unquote(match_star.group(1).strip('"'))
                else:
                    # filename="..." 形式
                    match = re.search(r'filename="?([^";\r\n]+)"?', cd)
                    if match:
                        final_file_name = match.group(1)
            
            # 拡張子の正規化（.jpegを.jpgに統一）
            name_without_ext, ext = os.path.splitext(final_file_name)
            if ext.lower() == '.jpeg':
                ext = '.jpg'
            final_file_name = name_without_ext + ext
                
            save_path = os.path.join(save_dir, final_file_name)
            with open(save_path, 'wb') as outf:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        outf.write(chunk)
            logger.info(f"ファイル保存完了: {save_path}")
            downloaded_count += 1
            
        except Exception as e:
            error_msg = f"ファイルダウンロード失敗: {url}, {e}"
            logger.error(error_msg)
            if parent:
                safe_show_message(parent, "ファイルダウンロード失敗", error_msg, "critical")
    
    logger.info(f"ファイルダウンロード完了: data_id={data_id}, 成功={downloaded_count}/{total_images}")
    # DatasetUploadTabからの呼び出しの場合はメッセージ表示をスキップ（独自の完了メッセージを表示するため）
    if parent and parent.__class__.__name__ != 'DatasetUploadTab':
        safe_show_message(parent, "完了", f"{data_id} の全ファイルを保存しました。（{downloaded_count}/{total_images}件成功）", "information")

def download_file_for_data_id(data_id, bearer_token=None, save_dir_base=None, file_name=None, grantNumber=None, dataset_name=None, tile_name=None, tile_number=None, parent=None):
    """
    指定data_idのファイル本体をAPIから取得し、output/rde/data/dataFiles/{data_id}/ に保存
    
    Args:
        data_id: データID
        bearer_token: 認証トークン（省略時はBearerTokenManagerから取得）
        save_dir_base: 保存ディレクトリベース
        file_name: ファイル名
        grantNumber: グラント番号
        dataset_name: データセット名
        tile_name: タイル名
        tile_number: タイル番号
        parent: 親ウィジェット
    """
    import os
    
    # Bearer Token統一管理システムで取得
    if not bearer_token:
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            logger.error("Bearer Tokenが取得できません。ログインを確認してください")
            safe_show_message(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。", "critical")
            return False
    from urllib.parse import unquote, urlparse
    #base_dir = os.path.abspath(os.path.dirname(__file__))

    safe_dataset_name = (replace_invalid_path_chars(dataset_name) or "unknown_dataset").strip()
    safe_tile_name = (replace_invalid_path_chars(tile_name) or "unknown_tile").strip()
    safe_grant_number = (str(grantNumber) if grantNumber is not None else "unknown_grant").strip()
    safe_tile_number = (str(tile_number) if tile_number is not None else "unknown_number").strip()
    # 改行や空白を除去してから連結
    def safe_path_join(*args):
        return os.path.join(*(str(a).strip().replace('\n','').replace('\r','') for a in args if a is not None))
    try:
        save_dir = safe_path_join(save_dir_base, safe_grant_number, safe_dataset_name, f"{safe_tile_number}_{safe_tile_name}")
        os.makedirs(save_dir, exist_ok=True)
    except Exception as e:
        base_log_dir = save_dir_base
        log_path = os.path.join(base_log_dir, "download_error.log")
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"[ERROR] makedirs failed for data_id={data_id}, grantNumber={grantNumber}, dataset_name={dataset_name}, tile_name={tile_name}, tile_number={tile_number}\nException: {e}\n")
        logger.error("makedirs failed: %s", e)
        return False
    url = f"https://rde-api.nims.go.jp/files/{data_id}?isDownload=true"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "*/*",
        "Referer": "https://rde.nims.go.jp/",
        "Origin": "https://rde.nims.go.jp",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }
    logger.info("Downloading file for data_id: %s from %s", data_id, url)
    try:
        resp = download_request(url, bearer_token=None, timeout=30, headers=headers, stream=True)  # download_request returns Response object
        logger.debug("%s -> HTTP %s ", url, resp.status_code if resp else 'No Response')
        if resp is None:
            logger.error("Request failed for data_id: %s", data_id)
            if parent:
                safe_show_message(parent, "エラー", f"data_id {data_id} のダウンロードに失敗しました。", "warning")
            return False
        if resp.status_code != 200:
            if parent:
                from qt_compat.widgets import QMessageBox
                logger.warning("data_id %s has no fileName in attributes, skipping download.", data_id)
            else:
                logger.error("%s: %s\n%s", resp.status_code, url, resp.text)
            return False
        # ファイル名決定: Content-Disposition優先、なければURL末尾
        fname = None
        cd = resp.headers.get('Content-Disposition')
        import re
        if cd:
            match_star = re.search(r"filename\*=((?:UTF-8'')?[^;\r\n]+)", cd)
            if match_star:
                fname = unquote(match_star.group(1).strip('"'))
            else:
                match = re.search(r'filename="?([^";\r\n]+)"?', cd)
                if match:
                    fname = match.group(1)
        if not fname:
            fname = os.path.basename(urlparse(url).path)
        fname = re.sub(r'[\\/:*?"<>|]', '_', fname)
        save_path = os.path.join(save_dir, file_name)
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info("Saved: %s", save_path)
        return save_path
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 失敗時は最も浅い保存フォルダにエラーログを残す
        base_log_dir = save_dir_base
        log_path = os.path.join(base_log_dir, "download_error.log")
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"[ERROR] download failed for data_id={data_id}, grantNumber={grantNumber}, dataset_name={dataset_name}, tile_name={tile_name}, tile_number={tile_number}\nException: {e}\n")
        if parent:
            safe_show_message(parent, "ファイルダウンロード失敗", f"{url}\n{e}", "critical")
        else:
            logger.error("%s: %s", url, e)
        return False
# 任意のJSONファイルからdata配列内のidを全て取得し表示する関数


def show_all_data_ids_from_json(json_path, parent=None):
    if not os.path.exists(json_path):
        msg = f"ファイルが存在しません: {json_path}"
        if parent:
            safe_show_message(parent, "エラー", msg, "warning")
        else:
            print(msg)
        return
    with open(json_path, encoding="utf-8") as f:
        obj = json.load(f)
    ids = [entry.get("id") for entry in obj.get("data", []) if "id" in entry]
    msg = "\n".join(ids) if ids else "IDが見つかりませんでした。"
    if parent:
        safe_show_message(parent, "ID一覧", msg, "information")
    else:
        print(msg)


import shutil

def anonymize_json(data, grant_number):
        # attributes内のdatasetTypeがANALYSISなら特別処理
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                kl = k.lower()
                # attributes特別処理
                if k == "attributes" and isinstance(v, dict):
                    attrs = v.copy()
                    if attrs.get("datasetType") == "ANALYSIS":
                        attrs["grantNumber"] = "JPMXP12********"
                        attrs["subjectTitle"] = "*******非開示*******"
                        attrs["name"] = "*******非開示*******"
                    else:
                        for key, val in [("grantNumber", "JPMXP12********"), ("subjectTitle", "*******非開示*******"), ("name", "*******非開示*******")]:
                            if key in attrs:
                                attrs[key] = val
                    out[k] = attrs
                # grantNumber/grant_number/subjectTitle/nameは再帰的に匿名化
                elif kl in ("grantnumber", "grant_number"):
                    out[k] = "***"
                elif kl == "subjecttitle":
                    out[k] = "*******非開示*******"
                elif kl == "name":
                    out[k] = "*******非開示*******"
                else:
                    out[k] = anonymize_json(v, grant_number)
            return out
        elif isinstance(data, list):
            return [anonymize_json(v, grant_number) for v in data]
        return data

def _process_data_entry_for_parallel(bearer_token, data_entry, save_dir_base, grantNumber, dataset_name, file_filter_config, parent=None, file_progress_callback=None):
    """
    並列処理用ワーカー関数: 単一data_entryのfiles API呼び出しとファイルダウンロード
    
    Args:
        bearer_token: 認証トークン
        data_entry: データエントリオブジェクト
        save_dir_base: 保存ディレクトリベース
        grantNumber: グラント番号
        dataset_name: データセット名
        file_filter_config: ファイルフィルタ設定
        parent: 親ウィジェット（エラーメッセージ用）
        file_progress_callback: ファイル単位のプログレスコールバック (file_name) -> None
        
    Returns:
        dict: {"status": "success"/"failed"/"skipped", "downloaded_count": int, "error": str}
    """
    try:
        data_id = data_entry.get('id')
        attributes = data_entry.get('attributes', {})
        tile_name = attributes.get("name", "")
        tile_number = attributes.get("dataNumber", "")
        
        if not data_id:
            logger.warning(f"データIDが空のエントリをスキップ: {data_entry}")
            return {"status": "skipped", "downloaded_count": 0}
        
        # 1. files API (json)を従来通り保存
        files_dir = os.path.normpath(os.path.join(OUTPUT_DIR, f'rde/data/dataFiles/sub'))
        os.makedirs(files_dir, exist_ok=True)
        
        files_url = (
            f"https://rde-api.nims.go.jp/data/{data_id}/files"
            "?page%5Blimit%5D=100"
            "&page%5Boffset%5D=0"
            "&filter%5BfileType%5D%5B%5D=META"
            "&filter%5BfileType%5D%5B%5D=MAIN_IMAGE"
            "&filter%5BfileType%5D%5B%5D=OTHER_IMAGE"
            "&filter%5BfileType%5D%5B%5D=NONSHARED_RAW"
            "&filter%5BfileType%5D%5B%5D=RAW"
            "&filter%5BfileType%5D%5B%5D=STRUCTURED"
            "&fileTypeOrder=RAW%2CNONSHARED_RAW%2CMETA%2CSTRUCTURED%2CMAIN_IMAGE%2COTHER_IMAGE"
        )
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {bearer_token}",
            "Connection": "keep-alive",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        
        resp = api_request("GET", files_url, headers=headers)  # Bearer Token統一管理システム対応
        
        if resp is None:
            logger.error(f"リクエスト失敗 (data_id: {data_id}): {files_url}")
            return {"status": "failed", "downloaded_count": 0, "error": "API request failed"}
            
        if resp.status_code == 404:
            logger.warning(f"データが見つかりません (data_id: {data_id}): 404エラー")
            return {"status": "skipped", "downloaded_count": 0}
            
        if resp.status_code != 200:
            logger.error(f"HTTP {resp.status_code}エラー (data_id: {data_id}): {files_url}")
            return {"status": "failed", "downloaded_count": 0, "error": f"HTTP {resp.status_code}"}
            
        resp.raise_for_status()
        files_data = resp.json()
        save_path = os.path.join(files_dir, f"{data_id}.json")
        
        with open(save_path, "w", encoding="utf-8") as outf:
            logger.info(f"ファイルデータ保存: {save_path}")
            json.dump(files_data, outf, ensure_ascii=False, indent=2)
        
        # 2. ファイル本体も取得して保存
        save_dir_base_full = os.path.join(os.path.join(OUTPUT_DIR,"rde","data","dataFiles"))
        logger.debug(f"save_path: {save_path}, data_id: {data_id}")
        
        # files_dataはdict型のはずなのでdataキーを直接参照
        data_entries_files = files_data.get("data", [])
        
        # フィルタ処理を適用
        try:
            from classes.data_fetch2.util.file_filter_util import filter_file_list
            filtered_files = filter_file_list(data_entries_files, file_filter_config)
            logger.debug(f"フィルタ適用: {len(data_entries_files)}件 → {len(filtered_files)}件")
        except ImportError:
            # フォールバック: 従来のMAIN_IMAGEフィルタのみ
            logger.warning("フィルタユーティリティがインポートできません。従来フィルタを使用します。")
            filtered_files = [entry for entry in data_entries_files 
                            if entry.get("attributes", {}).get("fileType") == "MAIN_IMAGE"]
        
        download_count = 0
        max_download = file_filter_config.get("max_download_count", 0)
        
        for dataentry in filtered_files:
            # ダウンロード数上限チェック
            if max_download > 0 and download_count >= max_download:
                logger.info(f"ダウンロード数上限に達しました: {max_download}件")
                break
                
            logger.debug(f"データエントリ処理中: {dataentry}")
            
            if not isinstance(dataentry, dict):
                logger.warning(f"辞書型でないエントリをスキップ: {dataentry}")
                continue
                
            if dataentry.get("type") != "file":
                logger.warning(f"ファイル型でないエントリをスキップ: {dataentry}")
                continue
                
            attributes_file = dataentry.get("attributes", {})
            fileType = attributes_file.get("fileType", "")
            logger.debug(f"fileType: {fileType} for data_id: {data_id}")
            
            # idを取得
            entry_data_id = dataentry.get("id")
            if not entry_data_id:
                logger.warning(f"IDが無いエントリをスキップ: {dataentry}")
                continue
                
            # attributes.fileNameを参照
            file_name = attributes_file.get('fileName', '')
            if not file_name:
                logger.warning(f"ファイル名が無いエントリをスキップ: data_id={entry_data_id}")
                continue
                
            # ファイル本体をダウンロード
            download_success = download_file_for_data_id(entry_data_id, bearer_token, save_dir_base_full, file_name, grantNumber, dataset_name, tile_name, tile_number, parent)
            if download_success:
                download_count += 1
                
            # ファイル単位のプログレス通知
            if file_progress_callback:
                file_progress_callback(file_name)
        
        logger.info(f"データエントリ処理完了: data_id={data_id}, ファイル数: {download_count}")
        return {"status": "success", "downloaded_count": download_count}
        
    except Exception as e:
        error_msg = f"データエントリ処理中にエラー (data_id: {data_id}): {e}"
        logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return {"status": "failed", "downloaded_count": 0, "error": str(e)}

def fetch_files_json_for_dataset(parent, dataset_obj, bearer_token=None, save_dir=None, progress_callback=None, file_filter_config=None):
    
    tile_name = "tile_name"  # デフォルト値
    tile_number = "tile_number"  # デフォルト値
    """
    指定データセットIDのfiles_{id}.jsonをAPI経由で取得し保存する
    ファイルフィルタ機能付き
    
    Args:
        parent: 親ウィジェット
        dataset_obj: データセットオブジェクト
        bearer_token: 認証トークン（省略時はBearerTokenManagerから取得）
        save_dir: 保存先ディレクトリ
        progress_callback: プログレス通知コールバック
        file_filter_config: ファイルフィルタ設定辞書
    """
    if not dataset_obj:
        error_msg = "データセットIDが選択されていません。"
        logger.error(error_msg)
        if parent:
            safe_show_message(parent, "データセット未選択", error_msg, "warning")
        return None
    
    # Bearer Token統一管理システムで取得
    if not bearer_token:
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            error_msg = "Bearer Tokenが取得できません。ログインを確認してください。"
            logger.error(error_msg)
            if parent:
                safe_show_message(parent, "認証エラー", error_msg, "warning")
            return None

    # フィルタ設定の初期化
    if file_filter_config is None:
        # デフォルトフィルタ（従来通りMAIN_IMAGEのみ）
        file_filter_config = {
            "file_types": ["MAIN_IMAGE"],
            "media_types": [],
            "extensions": [],
            "size_min": 0,
            "size_max": 0,
            "filename_pattern": "",
            "max_download_count": 0
        }

    try:
        # プログレスコールバック初期化
        if progress_callback:
            if not progress_callback(0, 1, "処理を開始しています..."):
                return None

        dataset_id = dataset_obj.get('id', '')
        dataset_attributes = dataset_obj.get('attributes', {})
        dataset_name = dataset_attributes.get('name', 'データセット名未設定')
        grantNumber= dataset_attributes.get('grantNumber', '不明')
        safe_dataset_name = replace_invalid_path_chars(dataset_name)
        
        # データセットIDの形式検証
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, dataset_id):
            error_msg = f"データセットIDの形式が無効です: {dataset_id}"
            logger.error(error_msg)
            if parent:
                safe_show_message(parent, "ID形式エラー", error_msg, "warning")
            return None
        
        logger.info(f"処理対象データセット: ID={dataset_id}, Name={dataset_name}, Grant={grantNumber}")
        
        # プログレス更新
        if progress_callback:
            if not progress_callback(0, 1, "データセット情報を処理中..."):
                return None
        
        # dataset_obj を　保存
        dataset_dir=os.path.join(OUTPUT_DIR, "rde", "data", "dataFiles",grantNumber,safe_dataset_name)
        original_dataset_dir = os.path.join(OUTPUT_DIR, "rde", "data", "datasets")
        os.makedirs(dataset_dir, exist_ok=True)
        dataset_json_path = os.path.join(dataset_dir, f"{dataset_id}.json") 
        original_dataset_json_path = os.path.join(original_dataset_dir, f"{dataset_id}.json")

        # original_dataset_jsonをdataset_dirにコピー 保存
        if os.path.exists(original_dataset_json_path):
            shutil.copy2(original_dataset_json_path, dataset_json_path)

        # プログレス更新
        if progress_callback:
            if not progress_callback(0, 1, "匿名化ファイルを作成中..."):
                return None

        #C:\vscode\rde\src\classes\anonymizer.py を参考にoriginal_dataset_json_path　の匿名化版を同じディレクトリに保存
        dataset_anonymized_path = os.path.join(dataset_dir, f"{dataset_id}_anonymized.json")
        if os.path.exists(original_dataset_json_path):
            with open(original_dataset_json_path, "r", encoding="utf-8") as f:
                dataset_obj = json.load(f)
            # 匿名化処理を行う関数を呼び出す
            anonymized_obj = anonymize_json(dataset_obj, grantNumber)
            with open(dataset_anonymized_path, "w", encoding="utf-8") as f:
                json.dump(anonymized_obj, f, ensure_ascii=False, indent=2)

        # プログレス更新
        if progress_callback:
            if not progress_callback(0, 1, "データエントリファイルを読み込み中..."):
                return None

        # 1. dataEntry/{dataset_id}.jsonを読む
        entry_path = os.path.normpath(os.path.join(OUTPUT_DIR, f'rde/data/dataEntry/{dataset_id}.json'))
        if not os.path.exists(entry_path):
            logger.warning(f"{entry_path} が存在しません。APIから直接取得を試行します。")
            
            # dataEntryファイルが存在しない場合、APIから直接取得を試行
            try:
                logger.info(f"データセット {dataset_id} のエントリ情報をAPIから取得中...")
                
                # プログレス更新（APIリクエスト前）
                if progress_callback:
                    if not progress_callback(0, 1, f"APIからデータエントリ取得中..."):
                        return None
                
                # dataEntry APIを呼び出し（正しいエンドポイント形式）
                # URLクエリパラメータは直接URLに含める方式を使用
                entry_url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&page%5Blimit%5D=100&page%5Boffset%5D=0"
                params = None  # URLに直接含めたためパラメータは使わない
                headers = {
                    "Accept": "application/vnd.api+json",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    "Authorization": f"Bearer {bearer_token}",
                    "Connection": "keep-alive",
                    "Host": "rde-api.nims.go.jp",
                    "Origin": "https://rde.nims.go.jp",
                    "Referer": "https://rde.nims.go.jp/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                }
                
                logger.debug(f"API URL: {entry_url}")
                logger.debug(f"Headers: {headers}")
                
                logger.info(f"APIリクエスト送信: {entry_url}")
                
                resp = api_request("GET", entry_url, headers=headers, params=params)  # Bearer Token統一管理システム対応
                
                if resp is None:
                    error_msg = f"APIからのデータエントリ取得に失敗しました: {dataset_id}"
                    logger.error(error_msg)
                    if parent:
                        safe_show_message(parent, "データ取得失敗", error_msg, "warning")
                    return None
                    
                if resp.status_code == 400:
                    # 400エラーの詳細ログ
                    try:
                        error_detail = resp.json()
                        logger.error(f"API 400エラー詳細: {error_detail}")
                    except:
                        logger.error(f"API 400エラー: {resp.text}")
                    
                    error_msg = f"データセット {dataset_id} のリクエストが無効です（400エラー）\n詳細: APIエンドポイントまたはパラメータが正しくない可能性があります"
                    logger.error(error_msg)
                    if parent:
                        safe_show_message(parent, "リクエストエラー", error_msg, "warning")
                    return None
                    
                if resp.status_code == 404:
                    error_msg = f"データセット {dataset_id} が見つかりません（404エラー）"
                    logger.error(error_msg)
                    if parent:
                        safe_show_message(parent, "データセット未発見", error_msg, "warning")
                    return None
                    
                if resp.status_code == 403:
                    error_msg = f"データセット {dataset_id} へのアクセスが拒否されました（403エラー）\n認証トークンを確認してください"
                    logger.error(error_msg)
                    if parent:
                        safe_show_message(parent, "アクセス拒否", error_msg, "warning")
                    return None
                    
                if resp.status_code != 200:
                    error_msg = f"APIエラー（HTTP {resp.status_code}）: {dataset_id}\nレスポンス: {resp.text[:200]}..."
                    logger.error(error_msg)
                    if parent:
                        safe_show_message(parent, "APIエラー", error_msg, "warning")
                    return None
                
                entry_json = resp.json()
                
                # APIレスポンスの構造確認
                if "data" not in entry_json:
                    logger.warning(f"APIレスポンスに'data'キーがありません: {list(entry_json.keys())}")
                    if "errors" in entry_json:
                        logger.error(f"APIエラー: {entry_json['errors']}")
                
                # 取得したデータを保存（次回以降のため）
                os.makedirs(os.path.dirname(entry_path), exist_ok=True)
                with open(entry_path, "w", encoding="utf-8") as f:
                    json.dump(entry_json, f, ensure_ascii=False, indent=2)
                logger.info(f"取得したデータエントリを保存しました: {entry_path}")
                
            except Exception as e:
                error_msg = f"データエントリの取得中にエラーが発生しました: {e}"
                logger.error(error_msg)
                import traceback
                logger.error(f"スタックトレース: {traceback.format_exc()}")
                if parent:
                    safe_show_message(parent, "取得エラー", error_msg, "critical")
                return None
        else:
            # ファイルが存在する場合の従来処理
            try:
                with open(entry_path, encoding='utf-8') as f:
                    entry_json = json.load(f)
                logger.info(f"既存のデータエントリファイルを読み込みました: {entry_path}")
            except (json.JSONDecodeError, IOError) as e:
                error_msg = f"データエントリファイルの読み込みに失敗しました: {entry_path}, {e}"
                logger.error(error_msg)
                if parent:
                    safe_show_message(parent, "ファイル読み込みエラー", error_msg, "critical")
                return None
        
        data_entries = entry_json.get('data', [])
        if not data_entries:
            warning_msg = f"データセット {dataset_id} にはデータエントリが含まれていません"
            logger.warning(warning_msg)
            if parent:
                safe_show_message(parent, "データなし", warning_msg, "information")
            # データなしの場合でも処理を継続する場合があるため、特別な戻り値を返す
            return "no_data"

        # 2. 各dataエントリのidごとにfiles APIを呼び、dataFiles/{id}.jsonに保存（並列化対応）
        # v2.1.1: 並列ダウンロード対応（50件以上で自動並列化）
        # v2.1.3: ファイル単位プログレス表示対応
        from net.http_helpers import parallel_download
        import threading
        
        files_dir = os.path.normpath(os.path.join(OUTPUT_DIR, f'rde/data/dataFiles/sub'))
        os.makedirs(files_dir, exist_ok=True)
        
        # プログレス管理変数
        total_entries = len(data_entries)
        
        # プログレス更新（処理開始）
        if progress_callback:
            if not progress_callback(0, 1, f"ファイル取得開始... ({total_entries}エントリ)"):
                return None
        
        # ステップ1: 全エントリのファイルリストを取得して総ファイル数を算出
        logger.info("ステップ1: 全エントリのファイル情報取得中...")
        total_files = 0
        entry_file_counts = {}  # {data_entry_id: ファイル数}
        
        for idx, entry in enumerate(data_entries):
            data_id = entry.get('id')
            if not data_id:
                continue
            
            # プログレス更新（ファイルリスト取得中）
            if progress_callback:
                progress_pct = int((idx + 1) / total_entries * 100)
                if not progress_callback(progress_pct, 100, f"ファイルリスト取得中... ({idx+1}/{total_entries}エントリ)"):
                    return None
            
            # files API呼び出し（ファイル情報のみ取得）
            files_url = (
                f"https://rde-api.nims.go.jp/data/{data_id}/files"
                "?page%5Blimit%5D=100"
                "&page%5Boffset%5D=0"
                "&filter%5BfileType%5D%5B%5D=META"
                "&filter%5BfileType%5D%5B%5D=MAIN_IMAGE"
                "&filter%5BfileType%5D%5B%5D=OTHER_IMAGE"
                "&filter%5BfileType%5D%5B%5D=NONSHARED_RAW"
                "&filter%5BfileType%5D%5B%5D=RAW"
                "&filter%5BfileType%5D%5B%5D=STRUCTURED"
                "&fileTypeOrder=RAW%2CNONSHARED_RAW%2CMETA%2CSTRUCTURED%2CMAIN_IMAGE%2COTHER_IMAGE"
            )
            headers = {
                "Accept": "application/vnd.api+json",
                "Authorization": f"Bearer {bearer_token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            
            try:
                resp = api_request("GET", files_url, headers=headers)
                if resp and resp.status_code == 200:
                    files_data = resp.json()
                    data_entries_files = files_data.get("data", [])
                    
                    # フィルタ適用
                    try:
                        from classes.data_fetch2.util.file_filter_util import filter_file_list
                        filtered_files = filter_file_list(data_entries_files, file_filter_config)
                    except ImportError:
                        filtered_files = [e for e in data_entries_files 
                                        if e.get("attributes", {}).get("fileType") == "MAIN_IMAGE"]
                    
                    # ダウンロード数上限チェック
                    max_download = file_filter_config.get("max_download_count", 0)
                    file_count = len(filtered_files)
                    if max_download > 0 and file_count > max_download:
                        file_count = max_download
                    
                    entry_file_counts[data_id] = file_count
                    total_files += file_count
                    logger.debug(f"エントリ {data_id}: {file_count}ファイル")
            except Exception as e:
                logger.warning(f"エントリ {data_id} のファイルリスト取得失敗: {e}")
                entry_file_counts[data_id] = 0
        
        logger.info(f"総ファイル数: {total_files}ファイル ({total_entries}エントリ)")
        
        # ステップ2: ファイルダウンロード実行（並列処理）
        logger.info("ステップ2: ファイルダウンロード開始...")
        
        # スレッドセーフなファイルカウンター
        file_counter_lock = threading.Lock()
        downloaded_file_count = [0]  # リストでラップしてスレッド間共有
        
        def file_progress_callback(file_name):
            """ファイルダウンロード完了時のコールバック"""
            with file_counter_lock:
                downloaded_file_count[0] += 1
                current = downloaded_file_count[0]
            
            if progress_callback:
                progress_pct = int((current / max(total_files, 1)) * 100)
                progress_callback(progress_pct, 100, 
                                f"ファイルダウンロード中... ({current}/{total_files}) - {file_name}")
        
        # 並列化用タスクリスト作成
        tasks = [
            (bearer_token, entry, os.path.join(OUTPUT_DIR, "rde", "data", "dataFiles"), 
             grantNumber, dataset_name, file_filter_config, parent, file_progress_callback)
            for entry in data_entries
        ]
        
        # プログレスコールバックラッパー（エントリ単位は使用しない）
        def entry_progress_callback(current, total, message):
            """エントリ処理進捗（ダミー - ファイル単位で更新するため）"""
            return True
        
        # 並列ダウンロード実行（50件以上で自動並列化、最大10並列）
        result = parallel_download(
            tasks=tasks,
            worker_function=_process_data_entry_for_parallel,
            max_workers=10,
            progress_callback=entry_progress_callback,
            threshold=50  # 50エントリ以上で並列化
        )
        
        # 結果の集計
        success_count = result.get("success_count", 0)
        failed_count = result.get("failed_count", 0)
        skipped_count = result.get("skipped_count", 0)
        cancelled = result.get("cancelled", False)
        errors = result.get("errors", [])
        
        if cancelled:
            logger.warning(f"処理がキャンセルされました: {success_count}件成功, {failed_count}件失敗, {skipped_count}件スキップ")
            return "キャンセルされました"
        
        # エラーログ出力
        if errors:
            logger.error(f"エラーが{len(errors)}件発生しました:")
            for err in errors[:10]:  # 最初の10件のみログ出力
                logger.error(f"  - {err}")
        
        # プログレス完了
        if progress_callback:
            progress_callback(1.0, 1.0, 
                            f"処理完了: {success_count}エントリ成功, {failed_count}エントリ失敗, {skipped_count}エントリスキップ")

        success_msg = f"dataEntry/{dataset_id}.json内の各data idについてdataFiles/に保存しました。成功: {success_count}件, 失敗: {failed_count}件, スキップ: {skipped_count}件"
        logger.info(success_msg)
        return success_msg

    except Exception as e:
        error_msg = f"ファイル取得処理中に予期しないエラーが発生しました: {e}"
        logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return None
