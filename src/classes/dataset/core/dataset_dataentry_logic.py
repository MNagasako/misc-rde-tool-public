"""
データセット データエントリー取得ロジック
データエントリー情報をAPIから取得してJSONファイルに保存する機能
Bearer Token統一管理システム対応
"""
import json
import logging
import os

from config.common import ensure_directory_exists, get_dynamic_file_path
from core.bearer_token_manager import BearerTokenManager
from net.http_helpers import proxy_get

# ロガー設定
logger = logging.getLogger(__name__)

def fetch_dataset_dataentry(dataset_id, bearer_token=None, force_refresh=False):
    """
    指定されたデータセットのデータエントリー情報を取得
    
    Args:
        dataset_id (str): データセットID
        bearer_token (str): 認証トークン（Noneの場合は統一管理システムから自動取得）
        force_refresh (bool): 強制更新フラグ
    
    Returns:
        bool: 取得成功の場合True
    """
    logger.debug("fetch_dataset_dataentry called with dataset_id=%s, force_refresh=%s", dataset_id, force_refresh)
    
    # Bearer Token統一管理システムで取得
    if not bearer_token:
        bearer_token = BearerTokenManager.get_current_token()
        if not bearer_token:
            logger.error("Bearer Tokenが取得できません")
            return False
    
    try:
        # 出力ディレクトリの作成
        output_dir = ensure_directory_exists(get_dynamic_file_path("output/rde/data/dataEntry"))

        # 出力ファイルパス
        output_file = os.path.join(output_dir, f"{dataset_id}.json")
        
        # 強制更新でない場合、既存ファイルの存在と更新時間をチェック
        if not force_refresh and os.path.exists(output_file):
            import time
            file_mtime = os.path.getmtime(output_file)
            current_time = time.time()
            # 5分以内なら取得をスキップ
            if current_time - file_mtime < 300:
                logger.info(f"データエントリーキャッシュを使用: {dataset_id}")
                return True
        
        # APIエンドポイントURL（既存実装と同じ形式）
        api_url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&sort=-created&page%5Boffset%5D=0&page%5Blimit%5D=24&include=owner%2Csample%2CthumbnailFile%2Cfiles"
        
        # ヘッダー設定（既存実装と同じ形式）
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {bearer_token}",
            "Connection": "keep-alive",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        
        logger.info(f"データエントリー情報を取得開始: {dataset_id}")
        logger.debug("API URL: %s", api_url)
        
        response = proxy_get(api_url, headers=headers, timeout=60)

        if response is None:
            logger.error(f"データエントリー取得失敗: {dataset_id}")
            return False
        
        # レスポンス確認
        response.raise_for_status()
        
        # 成功：JSONデータを保存
        data = response.json()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # /data/{data_id}/files のレスポンスも保存（NONSHARED_RAW 等が relationships.files に含まれないケースの補完用）
        try:
            from config.site_rde import URLS

            files_dir = ensure_directory_exists(get_dynamic_file_path("output/rde/data/dataFiles"))
            for entry in data.get("data", []) or []:
                data_id = entry.get("id")
                if not data_id:
                    continue

                files_api_url = URLS["api"]["data_files"].format(id=data_id)
                files_headers = {
                    "Accept": "application/vnd.api+json",
                    "Authorization": f"Bearer {bearer_token}",
                    "Origin": "https://rde.nims.go.jp",
                    "Referer": "https://rde.nims.go.jp/",
                }
                files_resp = proxy_get(files_api_url, headers=files_headers, timeout=60)
                if files_resp is None:
                    continue
                try:
                    files_resp.raise_for_status()
                except Exception:
                    continue

                files_payload = files_resp.json()
                files_out = os.path.join(files_dir, f"{data_id}.json")
                with open(files_out, "w", encoding="utf-8") as fh:
                    json.dump(files_payload, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"dataFiles 保存スキップ: {e}")
        
        entry_count = len(data.get('data', []))
        logger.info(f"データエントリー情報取得完了: {dataset_id} ({entry_count}件)")
        logger.debug("データエントリー取得成功: %s件", entry_count)
        
        return True
    
    except Exception as e:
        logger.error(f"データエントリー取得処理エラー: {dataset_id}, エラー: {e}")
        logger.error("fetch_dataset_dataentry failed: %s", e)
        return False

def get_dataentry_info_from_cache(dataset_id):
    """
    キャッシュからデータエントリー情報を取得
    
    Args:
        dataset_id (str): データセットID
    
    Returns:
        dict or None: データエントリー情報、存在しない場合はNone
    """
    try:
        output_file = os.path.join(OUTPUT_DIR, "rde", "data", "dataEntry", f"{dataset_id}.json")
        
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
        
    except Exception as e:
        logger.error(f"データエントリーキャッシュ読み込みエラー: {dataset_id}, エラー: {e}")
        return None