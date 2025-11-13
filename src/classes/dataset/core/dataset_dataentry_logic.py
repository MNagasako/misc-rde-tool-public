"""
データセット データエントリー取得ロジック
データエントリー情報をAPIから取得してJSONファイルに保存する機能
Bearer Token統一管理システム対応
"""
import os
import json
import logging
from config.common import OUTPUT_DIR
from classes.utils.api_request_helper import api_request
from core.bearer_token_manager import BearerTokenManager

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
        output_dir = os.path.join(OUTPUT_DIR, "rde", "data", "dataEntry")
        os.makedirs(output_dir, exist_ok=True)
        
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
        
        # 既存実装と同じapi_requestを使用
        response = api_request("GET", api_url, bearer_token=bearer_token, headers=headers, timeout=60)
        
        if response is None:
            logger.error(f"データエントリー取得失敗: {dataset_id}")
            return False
        
        # レスポンス確認
        response.raise_for_status()
        
        # 成功：JSONデータを保存
        data = response.json()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
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