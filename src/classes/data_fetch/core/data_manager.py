"""
データ管理クラス - ARIM RDE Tool
データセットの取得・保存・管理を担当
画像データ取得・詳細情報管理機能
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認
"""
import os
import json
import logging
from qt_compat.core import QObject, Signal
from classes.utils.debug_log import debug_log
from .datatree_manager import DataTreeManager
from config.common import DATATREE_FILE_PATH, OUTPUT_DIR, get_cookie_file_path
from .api.rde_api_client import RDEApiClient  # core内のapi構造に修正
from .storage.file_saver import FileSaver
from .storage.image_saver import ImageSaver
from classes.utils.anonymizer import Anonymizer
from functions.utils import sanitize_path_name
from classes.utils.api_request_helper import api_request, fetch_binary  # 共通化済み
from core.bearer_token_manager import BearerTokenManager

class DataManager(QObject):
    """
    RDEのAPIアクセス・データ保存・データ抽出などを担当するデータマネージャクラス。
    """
    # シグナル定義
    processing_completed = Signal(str, bool)  # (grant_number, success)
    
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger or logging.getLogger("RDE_DataManager")
        self.datatree_manager = DataTreeManager(DATATREE_FILE_PATH, logger)
        from config import RDE_BASE_URL
        self.api_client = RDEApiClient(RDE_BASE_URL)
        self.file_saver = FileSaver()
        self.image_saver = ImageSaver()
        self.anonymizer = Anonymizer()

    @debug_log
    def build_headers(self, cookies, bearer_token):
        if not cookies:
            self.logger.warning("Cookiesが空です。ヘッダーを正しく構築できません。")
        if not bearer_token:
            self.logger.warning("Bearer Tokenが空です。ヘッダーを正しく構築できません。")
        
        cookie_header = '; '.join([f"{k}={v}" for k, v in cookies.items()]) if cookies else ""
        from config import USER_AGENT, RDE_BASE_URL
        return {
            'Cookie': cookie_header,
            'User-Agent': USER_AGENT,
            'Accept': 'application/vnd.api+json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Origin': RDE_BASE_URL,
            'Referer': RDE_BASE_URL + '/',
            'Authorization': f'Bearer {bearer_token}' if bearer_token else ""
    }

    @debug_log
    def fetch_and_save_search_result(self, url, headers, output_dir, search_result_path, bearer_token=None):
        try:
            # urlがフルパスの場合はそのまま、そうでなければAPIクライアント経由
            if url.startswith("http"):
                resp = api_request("GET", url, headers=headers)  # Bearer Token統一管理システム対応
                if resp is None:
                    self.logger.warning(f"APIリクエスト失敗: {url}")
                    return
            else:
                resp = self.api_client.get(url, headers=headers)
            self.logger.info(f"Status: {resp.status_code}")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            self.file_saver.save_text(search_result_path, resp.text)
            self.logger.info(f"検索結果を {search_result_path} に保存しました。")
        except Exception as e:
            self.logger.warning(f"APIリクエスト失敗: {e}")

    @debug_log
    def fetch_and_save_multiple_datasets(self, grant_number, set_webview_message, datatree_json_path, search_result_path, details_dir, extract_ids_and_names, parse_cookies_txt, COOKIE_FILE_RDE, bearer_token, build_headers, process_dataset_id, apply_arim_anonymization):
        # 現在のgrant_numberを保存（fetch_and_save_data_listで使用）
        self.current_grant_number = grant_number
        
        set_webview_message('課題情報開始！')
        if not os.path.exists(details_dir):
            os.makedirs(details_dir)
        if not os.path.exists(search_result_path):
            self.logger.info(f"検索結果ファイルが存在しません: {search_result_path}")
            return
        #datatree = load_datatree_json(datatree_json_path)
        #existing_ids = set(entry['id'] for entry in datatree if 'id' in entry)
        ids_and_names = extract_ids_and_names(search_result_path)
        self.logger.info(f"{len(ids_and_names)}件のデータセットIDを取得: {ids_and_names}")
        set_webview_message(f"[課題情報]{ids_and_names}")
        for id, name in ids_and_names:
            set_webview_message(f"[課題情報][{id}][{name}]")
            #insert_datatree_element(datatree_json_path, {"id": id, "name": name, "type": "dataset", "arim_id": grant_number})
            #self.logger.info(f"datatree.jsonを {datatree_json_path} に保存 ({len(load_datatree_json(datatree_json_path))}件)")
        cookies = parse_cookies_txt(get_cookie_file_path())
        if not bearer_token:
            self.logger.warning("Bearerトークンが取得できていません。手動で貼り付けてください。")
        headers = build_headers(cookies, bearer_token)
        for id, name in ids_and_names:
            set_webview_message(f"[CALL][process_dataset_id][{id}][{name}][{details_dir}]")
            process_dataset_id(id, name, details_dir, headers)
        if os.path.exists(details_dir):
            apply_arim_anonymization(details_dir, grant_number)

    @debug_log
    def process_dataset_id(self, id, name, details_dir, headers, set_webview_message, fetch_and_save_dataset_detail, datatree_json_path, save_webview_blob_images, image_dir):
        safe_name = sanitize_path_name(name)
        subdir = os.path.join(details_dir, safe_name)
        self.logger.info(f"process_dataset_id[{subdir}")
        if not os.path.exists(subdir):
            os.makedirs(subdir)
        set_webview_message(f"[process_dataset_id][{id}][{name}]")
        fetch_and_save_dataset_detail(id, subdir, headers, datatree_json_path)  # ←datatree_json_pathを渡す

        data_ids = self.datatree_manager.get_details_by_dataset_id(id)
        
        self.logger.info(f"[data_ids]{data_ids}")
        
        for data_id in data_ids:
            set_webview_message(f"[save_webview_blob_images][{data_id}]")
            self.logger.info(f"[data_id]:{data_id}")
            
            # data_idに対応する正しい詳細フォルダパスを取得
            detail_subdir = subdir  # デフォルトはデータセットレベル
            try:
                # DataTreeManagerから詳細情報を取得
                grant_number = getattr(self, 'current_grant_number', None)
                if grant_number:
                    detail = self.datatree_manager.get_detail(grant_number, id, data_id)
                    if detail and detail.get('subdir'):
                        detail_subdir = detail['subdir']
                        self.logger.info(f"[BLOB] 詳細フォルダパス取得: data_id={data_id} -> {detail_subdir}")
                    else:
                        self.logger.warning(f"[BLOB] 詳細フォルダパス取得失敗、デフォルト使用: data_id={data_id} -> {detail_subdir}")
            except Exception as e:
                self.logger.warning(f"[BLOB] 詳細フォルダパス取得エラー: data_id={data_id}, error={e}")
            
            save_webview_blob_images(f"{data_id}", detail_subdir, headers)

    @debug_log
    def fetch_and_save_dataset_detail(self, id, subdir, headers, fetch_and_save_data_list, fetch_data_list_json, datatree_json_path):
        from config.site_rde import URLS
        url = URLS["api"]["dataset_detail"].format(id=id)
        try:
            resp = api_request("GET", url, headers=headers)
            if resp.status_code == 200:
                outpath = os.path.join(subdir, f"{id}.json")
                self.file_saver.save_text(outpath, resp.text)
                self.logger.info(f"[OK] {id} の詳細を {outpath} に保存")
                
                # DataTreeManagerにデータセットを追加 (重要な修正)
                grant_number = getattr(self, 'current_grant_number', None)
                if grant_number and self.datatree_manager:
                    try:
                        # データセット名を取得（JSONからパース）
                        import json
                        dataset_data = json.loads(resp.text)
                        dataset_name = dataset_data.get('data', {}).get('attributes', {}).get('name', id)
                        
                        # DataTreeManagerにgrant情報を事前に作成（dataset追加の前提条件）
                        try:
                            self.datatree_manager.add_or_update_grant(grant_number, name=grant_number)
                            self.logger.info(f"[OK] DataTreeManagerにgrant確保: {grant_number}")
                        except Exception as e:
                            self.logger.warning(f"DataTreeManagerへのgrant追加失敗: {e}")
                        
                        # DataTreeManagerにデータセットを追加
                        self.datatree_manager.add_or_update_dataset(
                            grant_number, id, 
                            name=dataset_name, 
                            subdir=subdir
                        )
                        self.logger.info(f"[OK] DataTreeManagerにデータセット追加: {id}")
                    except Exception as e:
                        self.logger.warning(f"DataTreeManagerへのデータセット追加失敗: {e}")
                
                fetch_and_save_data_list(id, subdir, headers, datatree_json_path)
               
            else:
                self.logger.info(f"[NG] {id} の取得失敗: status={resp.status_code}")
        except Exception as e:
            self.logger.info(f"[NG] {id} の取得例外１: {e}")

    @debug_log
    def fetch_and_save_data_list(self, id, subdir, headers,  datatree_json_path):
        from config.site_rde import URLS
        import os, json
        data_api_url = URLS["api"]["data"].format(id=id)
        try:
            data_resp = api_request("GET", data_api_url, headers=headers)
            if data_resp.status_code == 200:
                try:
                    data_json = data_resp.json()
                    if 'data' in data_json and isinstance(data_json['data'], list):
                        for entry in data_json['data']:
                            data_id = entry.get('id', 'unknown')
                            data_attributes = entry.get('attributes', {})
                            data_name = data_attributes.get('name', data_id)
                            data_dir = os.path.join(subdir, sanitize_path_name(data_name))
                            if not os.path.exists(data_dir):
                                os.makedirs(data_dir)
                            data_outpath = os.path.join(data_dir, f"{data_id}.json")
                            self.file_saver.save_json(data_outpath, entry)
                            
                            # DataTreeManagerにdetailを追加 (重要な修正)
                            grant_number = getattr(self, 'current_grant_number', None)
                            if grant_number and self.datatree_manager:
                                try:
                                    # grant確保
                                    self.datatree_manager.add_or_update_grant(grant_number, name=grant_number)
                                    # dataset確保（detailを追加する前提条件）
                                    self.datatree_manager.add_or_update_dataset(grant_number, id, name=id)
                                    # detail追加
                                    self.datatree_manager.add_or_update_detail(
                                        grant_number, id, data_id, 
                                        name=data_name, 
                                        subdir=data_dir
                                    )
                                except Exception as e:
                                    self.logger.warning(f"DataTreeManagerへの詳細追加失敗: {e}")
                        
                        self.logger.info(f"[OK] {id} のデータリスト({len(data_json['data'])}件)を {data_dir} に保存")
                    else:
                        self.logger.info(f"[NG] {id} のデータリストに 'data' 配列がありません")
                except Exception as e:
                    self.logger.info(f"[NG] {id} のデータリストJSONパース失敗: {e}")
            else:
                self.logger.info(f"[NG] {id} のデータリスト取得失敗: status={data_resp.status_code}")
        except Exception as e:
            self.logger.info(f"[NG] {id} のデータリスト取得例外: {e}")

    @debug_log
    def extract_ids_and_names(self, search_result_path):
        """
        search_result.html(JSON)からデータセットIDと名前のタプルリストを抽出
        """
        try:
            with open(search_result_path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.logger.warning(f"search_result.htmlのJSONパース失敗: {e}")
            return []
        return [
            (d['id'], d.get('attributes', {}).get('name', d['id']))
            for d in data.get('data', []) if 'id' in d
        ]

    @debug_log
    def fetch_data_list_json(self, dataset_id, headers):
        """
        指定データセットIDのdata APIを叩き、JSONを返す
        """
        from config.site_rde import URLS
        try:
            url = URLS["api"]["data"].format(id=dataset_id)
            resp = api_request("GET", url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                self.logger.info(f"[NG] data API取得失敗: status={resp.status_code}")
                return None
        except Exception as e:
            self.logger.info(f"[NG] data API取得例外: {e}")
            return None

    @debug_log
    def fetch_and_save_data_detail(self, data_id, data_subdir, headers):
        from config.site_rde import URLS
        import os, json, requests
        url = URLS["api"]["data_detail"].format(id=data_id)
        try:
            resp = api_request("GET", url, headers=headers)
            if resp.status_code == 200:
                detail_json = resp.json()
                thumb_json_path = os.path.join(data_subdir, 'thumbnail.json')
                self.file_saver.save_json(thumb_json_path, detail_json)
                thumb_url = None
                thumb_file = detail_json.get('data', {}).get('attributes', {}).get('thumbnailFile')
                if thumb_file and isinstance(thumb_file, dict):
                    thumb_url = thumb_file.get('url')
                self.fetch_and_save_files_json(data_id, data_subdir, headers)
                if thumb_url and thumb_url.startswith('https://'):
                    self.download_image(thumb_url, os.path.join(data_subdir, 'thumbnail.jpg'), data_id)
                else:
                    self.logger.info(f"{data_id} サムネイル画像URLなしまたは未対応形式")
            else:
                self.logger.info(f"[NG] {data_id} サムネイル情報取得失敗: status={resp.status_code}")
        except Exception as e:
            self.logger.info(f"[NG] {data_id} サムネイル情報取得例外: {e}")

    @debug_log
    def fetch_and_save_files_json(self, data_id, data_subdir, headers):
        from config.site_rde import URLS
        import os, requests
        files_api_url = URLS["api"]["data_files"].format(id=data_id)
        try:
            files_resp = api_request("GET", files_api_url, headers=headers)
            if files_resp.status_code == 200:
                files_json_path = os.path.join(data_subdir, 'files.json')
                self.file_saver.save_text(files_json_path, files_resp.text)
                self.logger.info(f"[OK] {data_id} files.json保存: {files_api_url}")
            else:
                self.logger.info(f"[NG] {data_id} files.json取得失敗: status={files_resp.status_code}")
        except Exception as e:
            self.logger.info(f"[NG] {data_id} files.json取得例外: {e}")

    @debug_log
    def download_image(self, url, outpath, data_id):
        # 既に fetch_binary をインポート済みなので、追加インポート不要
        try:
            img_data = fetch_binary(url)
            if img_data:
                self.image_saver.save_image(outpath, img_data)
                self.logger.info(f"[OK] {data_id} サムネイル画像保存: {url}")
            else:
                self.logger.info(f"[NG] {data_id} サムネイル画像取得失敗")
        except Exception as e:
            self.logger.warning(f"画像ダウンロード失敗: {e}")


    @debug_log
    def save_blob_images(self, image_dir, b64_list, filenames, max_images=None):
        # base64リストとファイル名リストを受け取り、画像ファイルとして保存する
        count = 0
        for b64, filename in zip(b64_list, filenames):
            if max_images is not None and count >= max_images:
                break
            if not b64 or not filename:
                continue
            try:
                outpath = os.path.join(image_dir, filename)
                self.image_saver.save_base64_image(outpath, b64)
                count += 1
            except Exception as e:
                self.logger.warning(f"画像保存失敗: {filename}: {e}")

    @debug_log
    def save_blob_images_fullpath(self, b64_list, fullpaths):
        # base64リストとフルパスリストを受け取り、画像ファイルとして保存する
        for b64, path in zip(b64_list, fullpaths):
            if not b64 or not path:
                continue
            try:
                self.image_saver.save_base64_image(path, b64)
            except Exception as e:
                self.logger.warning(f"画像保存失敗: {path}: {e}")

    @debug_log
    def apply_arim_anonymization(self, dataset_dir, grant_number, set_webview_message=None):
        try:
            from pathlib import Path
            dataset_path = Path(dataset_dir)
            if set_webview_message:
                set_webview_message(f"[匿名化処理開始!!] {dataset_path}")
            self.logger.info(f"[ARIM] 匿名化処理開始: {dataset_path}")
            import glob
            import re
            uuid_pattern = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.json$")
            # grantNumber直下の全サブディレクトリを走査
            for subdir in dataset_path.iterdir():
                if subdir.is_dir():
                    # サブディレクトリ直下のUUID名.jsonのみ匿名化
                    for json_path in subdir.glob("*.json"):
                        if uuid_pattern.match(json_path.name):
                            out_path = str(json_path).replace(".json", ".anon.json")
                            self.anonymizer.anonymize_file(str(json_path), out_path, grant_number)
                            self.logger.info(f"[ARIM] 匿名化: {json_path} -> {out_path}")
            if set_webview_message:
                set_webview_message(f"[匿名化処理完了_!] {dataset_path}")
            self.logger.info(f"[ARIM] 匿名化処理完了: {dataset_path}")
        except Exception as e:
            error_msg = f"[ARIM] 匿名化処理例外: {e}"
            self.logger.error(error_msg)
            if set_webview_message:
                set_webview_message(error_msg)

    @debug_log
    def search_and_save_result(self, grant_number, bearer_token=None, set_webview_message=None):
        """
        grant_numberでAPI検索し、結果を保存。UI通知も行う。
        
        Args:
            grant_number: グラント番号
            bearer_token: 認証トークン（省略時はBearerTokenManagerから取得）
            set_webview_message: WebViewメッセージ設定関数
        """
        import os
        from config.site_rde import URLS
        
        # Bearer Token統一管理システムで取得
        if not bearer_token:
            bearer_token = BearerTokenManager.get_current_token()
            if not bearer_token:
                error_msg = "Bearer Tokenが取得できません。ログインを確認してください。"
                self.logger.error(error_msg)
                if set_webview_message:
                    set_webview_message(error_msg)
                return
        # クッキー取得
        cookie_path = get_cookie_file_path()
        try:
            with open(cookie_path, encoding='utf-8') as f:
                cookies = {}
                for line in f:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        cookies[k] = v
        except Exception as e:
            self.logger.warning(f"クッキー取得失敗: {e}")
            set_webview_message(f"[NG] クッキー取得失敗: {e}")
            return
        # ヘッダー生成
        headers = self.build_headers(cookies, bearer_token)
        # API URL生成
        url = URLS["api"]["search"].format(id=grant_number)
        output_dir = os.path.join(OUTPUT_DIR, 'search_results')
        os.makedirs(output_dir, exist_ok=True)
        search_result_path = os.path.join(output_dir, f"{grant_number}.json")
        try:
            resp = api_request("GET", url, headers=headers)
            if resp.status_code == 200:
                self.file_saver.save_text(search_result_path, resp.text)
                msg = f"[OK] 検索結果を {search_result_path} に保存"
                self.logger.info(msg)
                set_webview_message(msg)
                # 処理完了シグナル発信（成功）
                self.processing_completed.emit(grant_number, True)
            else:
                msg = f"[NG] API取得失敗: status={resp.status_code}"
                self.logger.warning(msg)
                set_webview_message(msg)
                # 処理完了シグナル発信（失敗）
                self.processing_completed.emit(grant_number, False)
        except Exception as e:
            msg = f"[NG] APIリクエスト例外: {e}"
            self.logger.warning(msg)
            set_webview_message(msg)
            # 処理完了シグナル発信（例外）
            self.processing_completed.emit(grant_number, False)
