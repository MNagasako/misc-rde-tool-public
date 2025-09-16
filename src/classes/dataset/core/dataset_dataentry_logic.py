"""
データセット データエントリー取得ロジック
データエントリー情報をAPIから取得してJSONファイルに保存する機能
"""
import os
import json
import requests
import logging
from config.common import OUTPUT_DIR
from net.http_helpers import create_request_session

# ロガー設定
logger = logging.getLogger(__name__)

def fetch_dataset_dataentry(dataset_id, bearer_token, force_refresh=False):
    """
    指定されたデータセットのデータエントリー情報を取得
    
    Args:
        dataset_id (str): データセットID
        bearer_token (str): 認証トークン
        force_refresh (bool): 強制更新フラグ
    
    Returns:
        bool: 取得成功の場合True
    """
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
        
        # APIエンドポイントURL
        api_url = f"https://rde.nims.go.jp/rde-api/api/v1/datasets/{dataset_id}/data"
        
        # HTTPセッションを作成
        session = create_request_session()
        
        # ヘッダー設定
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        logger.info(f"データエントリー情報を取得開始: {dataset_id}")
        
        # API呼び出し
        response = session.get(api_url, headers=headers, timeout=60)
        
        if response.status_code == 200:
            # 成功：JSONデータを保存
            data = response.json()
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            entry_count = len(data.get('data', []))
            logger.info(f"データエントリー情報取得完了: {dataset_id} ({entry_count}件)")
            
            return True
            
        elif response.status_code == 404:
            # データセットにデータエントリーが存在しない
            logger.warning(f"データセットにデータエントリーが存在しません: {dataset_id}")
            
            # 空のデータ構造を保存
            empty_data = {"data": [], "meta": {"total": 0}}
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(empty_data, f, ensure_ascii=False, indent=2)
            
            return True
            
        else:
            # その他のエラー
            logger.error(f"データエントリー取得エラー: {dataset_id}, ステータス: {response.status_code}")
            logger.error(f"レスポンス: {response.text[:500]}")
            return False
    
    except requests.RequestException as e:
        logger.error(f"データエントリー取得リクエストエラー: {dataset_id}, エラー: {e}")
        return False
        
    except Exception as e:
        logger.error(f"データエントリー取得処理エラー: {dataset_id}, エラー: {e}")
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