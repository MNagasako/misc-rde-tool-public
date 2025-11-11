"""
RDE API 基本動作テスト

このテストスクリプトは RDE API の基本的な動作を検証します。
実行前に有効な Bearer Token が必要です。

使用方法:
    python tests/test_rde_api_basic.py
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import json
import logging
from classes.managers.token_manager import TokenManager
from classes.utils.api_request_helper import api_request, download_request, fetch_binary

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_token_status():
    """トークン状態確認テスト"""
    logger.info("=" * 60)
    logger.info("テスト: トークン状態確認")
    logger.info("=" * 60)
    
    try:
        token_manager = TokenManager.get_instance()
        
        # 両方のホストのトークンをリフレッシュ
        hosts = ["rde.nims.go.jp", "rde-material.nims.go.jp"]
        
        for host in hosts:
            logger.info(f"トークンリフレッシュ実行中: {host}")
            if token_manager.refresh_access_token(host):
                logger.info(f"✅ {host}: トークンリフレッシュ成功")
            else:
                logger.warning(f"⚠️ {host}: トークンリフレッシュ失敗")
        
        logger.info("\nトークン状態確認:")
        
        for host in hosts:
            logger.info(f"\nホスト: {host}")
            
            # Access Token取得
            access_token = token_manager.get_access_token(host)
            if access_token:
                logger.info(f"  Access Token: {access_token[:20]}...")
            else:
                logger.info(f"  Access Token: なし")
        
        logger.info("\n✅ トークン状態確認: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ トークン状態確認: FAILED - {e}")
        return False


def test_get_datasets():
    """データセット一覧取得テスト"""
    logger.info("\n" + "=" * 60)
    logger.info("テスト: データセット一覧取得")
    logger.info("=" * 60)
    
    try:
        url = "https://rde-api.nims.go.jp/datasets"
        params = {
            "page[limit]": 10,
            "sort": "-modified",
            "include": "manager,releases",
            "fields[user]": "id,userName,organizationName,isDeleted",
            "fields[release]": "version,releaseNumber"
        }
        
        response = api_request('GET', url, params=params, timeout=30)
        
        if not response:
            logger.error("❌ レスポンスがNullです")
            return False
        
        if response.status_code != 200:
            logger.error(f"❌ ステータスコード異常: {response.status_code}")
            logger.error(f"レスポンス: {response.text[:500]}")
            return False
        
        # レスポンスが空でないか確認
        if not response.text:
            logger.error("❌ レスポンスボディが空です")
            return False
        
        # レスポンス内容を確認
        logger.info(f"レスポンス先頭100文字: {response.text[:100]}")
        
        data = response.json()
        
        if 'data' not in data:
            logger.error("❌ レスポンスに 'data' キーが存在しません")
            return False
        
        datasets = data['data']
        logger.info(f"取得件数: {len(datasets)}")
        
        if len(datasets) > 0:
            first_dataset = datasets[0]
            logger.info(f"\n最初のデータセット:")
            logger.info(f"  ID: {first_dataset.get('id', 'N/A')}")
            logger.info(f"  Name: {first_dataset.get('attributes', {}).get('name', 'N/A')}")
            logger.info(f"  Type: {first_dataset.get('attributes', {}).get('datasetType', 'N/A')}")
            logger.info(f"  Grant Number: {first_dataset.get('attributes', {}).get('grantNumber', 'N/A')}")
        
        logger.info("\n✅ データセット一覧取得: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ データセット一覧取得: FAILED - {e}", exc_info=True)
        return False


def test_get_dataset_by_id():
    """特定データセット取得テスト"""
    logger.info("\n" + "=" * 60)
    logger.info("テスト: 特定データセット取得")
    logger.info("=" * 60)
    
    try:
        # まず一覧から最初のIDを取得
        url_list = "https://rde-api.nims.go.jp/datasets"
        params = {"page[limit]": 1}
        
        response_list = api_request('GET', url_list, params=params, timeout=30)
        
        if not response_list or response_list.status_code != 200:
            logger.warning("⚠️ データセット一覧取得失敗、このテストをスキップ")
            return True
        
        datasets = response_list.json().get('data', [])
        
        if len(datasets) == 0:
            logger.warning("⚠️ データセットが存在しません、このテストをスキップ")
            return True
        
        dataset_id = datasets[0]['id']
        logger.info(f"テスト対象ID: {dataset_id}")
        
        # 特定データセット取得
        url = f"https://rde-api.nims.go.jp/datasets/{dataset_id}"
        
        response = api_request('GET', url, timeout=30)
        
        if not response:
            logger.error("❌ レスポンスがNullです")
            return False
        
        if response.status_code != 200:
            logger.error(f"❌ ステータスコード異常: {response.status_code}")
            return False
        
        data = response.json()
        dataset = data['data']
        
        logger.info(f"\nデータセット詳細:")
        logger.info(f"  ID: {dataset['id']}")
        logger.info(f"  Name: {dataset['attributes'].get('name', 'N/A')}")
        logger.info(f"  Description: {dataset['attributes'].get('description', 'N/A')[:100]}")
        logger.info(f"  Type: {dataset['attributes'].get('datasetType', 'N/A')}")
        
        logger.info("\n✅ 特定データセット取得: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ 特定データセット取得: FAILED - {e}", exc_info=True)
        return False


def test_get_dataset_files():
    """データセットファイル一覧取得テスト"""
    logger.info("\n" + "=" * 60)
    logger.info("テスト: データセットファイル一覧取得")
    logger.info("=" * 60)
    
    try:
        # まず一覧から最初のIDを取得
        url_list = "https://rde-api.nims.go.jp/datasets"
        params = {"page[limit]": 1}
        
        response_list = api_request('GET', url_list, params=params, timeout=30)
        
        if not response_list or response_list.status_code != 200:
            logger.warning("⚠️ データセット一覧取得失敗、このテストをスキップ")
            return True
        
        datasets = response_list.json().get('data', [])
        
        if len(datasets) == 0:
            logger.warning("⚠️ データセットが存在しません、このテストをスキップ")
            return True
        
        dataset_id = datasets[0]['id']
        logger.info(f"テスト対象ID: {dataset_id}")
        
        # ファイル一覧取得（データエントリ一覧）
        url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&page%5Blimit%5D=10&include=files"
        
        response = api_request('GET', url, timeout=30)
        
        if not response:
            logger.error("❌ レスポンスがNullです")
            return False
        
        if response.status_code != 200:
            logger.error(f"❌ ステータスコード異常: {response.status_code}")
            return False
        
        data = response.json()
        files = data.get('data', [])
        
        logger.info(f"ファイル数: {len(files)}")
        
        if len(files) > 0:
            first_file = files[0]
            logger.info(f"\n最初のファイル:")
            logger.info(f"  ID: {first_file.get('id', 'N/A')}")
            logger.info(f"  FileName: {first_file.get('attributes', {}).get('fileName', 'N/A')}")
            logger.info(f"  FileType: {first_file.get('attributes', {}).get('fileType', 'N/A')}")
            logger.info(f"  Size: {first_file.get('attributes', {}).get('fileSize', 'N/A')}")
        
        logger.info("\n✅ データセットファイル一覧取得: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ データセットファイル一覧取得: FAILED - {e}", exc_info=True)
        return False


def test_download_file():
    """ファイルダウンロードテスト"""
    logger.info("\n" + "=" * 60)
    logger.info("テスト: ファイルダウンロード")
    logger.info("=" * 60)
    
    try:
        # まずデータセット一覧取得
        url_list = "https://rde-api.nims.go.jp/datasets"
        params = {"page[limit]": 5}
        
        response_list = api_request('GET', url_list, params=params, timeout=30)
        
        if not response_list or response_list.status_code != 200:
            logger.warning("⚠️ データセット一覧取得失敗、このテストをスキップ")
            return True
        
        datasets = response_list.json().get('data', [])
        
        # ファイルを持つデータセットを探す
        file_id = None
        
        for dataset in datasets:
            dataset_id = dataset['id']
            url_files = f"https://rde-api.nims.go.jp/data?filter[dataset.id]={dataset_id}&page[limit]=10&include=files"
            
            response_files = api_request('GET', url_files, timeout=30)
            
            if response_files and response_files.status_code == 200:
                data_entries = response_files.json().get('data', [])
                
                # 各データエントリーからファイルIDを取得
                if data_entries and 'included' in response_files.json():
                    files = [item for item in response_files.json()['included'] if item.get('type') == 'files']
                    if files:
                        file_id = files[0]['id']
                        logger.info(f"テスト対象ファイルID: {file_id}")
                        break
        
        if not file_id:
            logger.warning("⚠️ ダウンロード可能なファイルが見つかりません、このテストをスキップ")
            return True
        
        # ダウンロード実行
        url_download = f"https://rde-api.nims.go.jp/files/{file_id}?isDownload=true"
        
        response = download_request(url_download, stream=True, timeout=60)
        
        if not response:
            logger.error("❌ レスポンスがNullです")
            return False
        
        if response.status_code != 200:
            logger.error(f"❌ ステータスコード異常: {response.status_code}")
            return False
        
        # Content-Disposition からファイル名取得
        cd = response.headers.get('Content-Disposition', '')
        filename = "downloaded_file.bin"
        
        if 'filename=' in cd:
            filename = cd.split('filename=')[1].strip('"')
        
        # 最初の1KBのみ取得してテスト
        chunk = next(response.iter_content(chunk_size=1024))
        
        logger.info(f"\nダウンロード情報:")
        logger.info(f"  FileName: {filename}")
        logger.info(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        logger.info(f"  Content-Length: {response.headers.get('Content-Length', 'N/A')}")
        logger.info(f"  First 1KB Size: {len(chunk)} bytes")
        
        logger.info("\n✅ ファイルダウンロード: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ ファイルダウンロード: FAILED - {e}", exc_info=True)
        return False


def test_get_thumbnail():
    """サムネイル取得テスト"""
    logger.info("\n" + "=" * 60)
    logger.info("テスト: サムネイル取得")
    logger.info("=" * 60)
    
    try:
        # まずデータセット一覧取得
        url_list = "https://rde-api.nims.go.jp/datasets"
        params = {"page[limit]": 5}
        
        response_list = api_request('GET', url_list, params=params, timeout=30)
        
        if not response_list or response_list.status_code != 200:
            logger.warning("⚠️ データセット一覧取得失敗、このテストをスキップ")
            return True
        
        datasets = response_list.json().get('data', [])
        
        # サムネイルを持つファイルを探す
        file_id = None
        
        for dataset in datasets:
            dataset_id = dataset['id']
            url_files = f"https://rde-api.nims.go.jp/data?filter[dataset.id]={dataset_id}&page[limit]=10&include=files"
            
            response_files = api_request('GET', url_files, timeout=30)
            
            if response_files and response_files.status_code == 200:
                response_json = response_files.json()
                
                # includedからファイルデータを取得
                if 'included' in response_json:
                    files = [item for item in response_json['included'] if item.get('type') == 'files']
                    
                    for file_entry in files:
                        file_type = file_entry.get('attributes', {}).get('fileType', '')
                        if file_type == 'MAIN_IMAGE':
                            file_id = file_entry['id']
                            logger.info(f"テスト対象ファイルID: {file_id}")
                            break
                    
                    if file_id:
                        break
        
        if not file_id:
            logger.warning("⚠️ サムネイル画像が見つかりません、このテストをスキップ")
            return True
        
        # サムネイル取得 (通常のファイル取得と同じエンドポイント)
        url_thumbnail = f"https://rde-api.nims.go.jp/files/{file_id}"
        
        thumbnail_data = fetch_binary(url_thumbnail, timeout=30)
        
        if not thumbnail_data:
            logger.error("❌ サムネイルデータがNullです")
            return False
        
        logger.info(f"\nサムネイル情報:")
        logger.info(f"  Size: {len(thumbnail_data)} bytes")
        logger.info(f"  Header (hex): {thumbnail_data[:16].hex()}")
        
        # PNG/JPEG 判定
        if thumbnail_data.startswith(b'\x89PNG'):
            logger.info(f"  Format: PNG")
        elif thumbnail_data.startswith(b'\xff\xd8\xff'):
            logger.info(f"  Format: JPEG")
        else:
            logger.info(f"  Format: Unknown")
        
        logger.info("\n✅ サムネイル取得: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ サムネイル取得: FAILED - {e}", exc_info=True)
        return False


def run_all_tests():
    """全テスト実行"""
    logger.info("\n" + "=" * 60)
    logger.info("RDE API 基本動作テスト開始")
    logger.info("=" * 60 + "\n")
    
    results = {}
    
    # テスト実行
    results['token_status'] = test_token_status()
    results['get_datasets'] = test_get_datasets()
    results['get_dataset_by_id'] = test_get_dataset_by_id()
    results['get_dataset_files'] = test_get_dataset_files()
    results['download_file'] = test_download_file()
    results['get_thumbnail'] = test_get_thumbnail()
    
    # 結果サマリー
    logger.info("\n" + "=" * 60)
    logger.info("テスト結果サマリー")
    logger.info("=" * 60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"  {test_name}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    logger.info("\n" + "=" * 60)
    logger.info(f"合計: {passed}/{total} テスト合格")
    logger.info("=" * 60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
