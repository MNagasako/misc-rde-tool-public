
"""
基本情報取得・処理ロジック

RDEシステムから基本情報（データセット、装置、組織等）を取得し、
JSONファイルとして保存する処理を提供します。

主要機能:
- ユーザー情報取得（self.json）
- データセット情報取得（dataset.json）
- データエントリ情報取得
- 装置タイプ・組織情報取得
- テンプレート・設備情報取得
- Excel出力機能

技術仕様:
- 統一ログシステム
- 堅牢なエラーハンドリング
- API リクエストの共通化
"""

import os
import json
import logging
import sys
import traceback
import glob

from datetime import datetime, timedelta, timezone
from dateutil.parser import parse as parse_datetime  # ISO8601対応のため
from ..util.xlsx_exporter import apply_basic_info_to_Xlsx_logic, summary_basic_info_to_Xlsx_logic
from classes.utils.api_request_helper import api_request  # refactored to use api_request_helper
from config.common import SUBGROUP_JSON_PATH, get_dynamic_file_path

# ロガー設定（標準出力にも出す）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# === 設定値 ===
OUTPUT_DIR = "output"

def stage_error_handler(operation_name: str):
    """
    段階実行メソッド用統一エラーハンドリングデコレータ
    
    Args:
        operation_name: 操作名（エラーメッセージ用）
    
    Returns:
        エラー時は '{operation_name}でエラーが発生しました: {error}'
        成功時は元の戻り値をそのまま返す
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = f"{operation_name}でエラーが発生しました: {e}"
                logger.error(error_msg)
                return error_msg
        return wrapper
    return decorator

def save_json(data, *path):
    """JSONファイルを保存する共通関数"""
    filepath = os.path.join(*path)
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"JSONファイル保存完了: {filepath}")
    except Exception as e:
        logger.error(f"JSONファイル保存失敗: {filepath}, error={e}")
        raise

def _make_headers(bearer_token, host, origin, referer):
    """API リクエスト用ヘッダーを生成"""
    return {
        "Accept": "application/vnd.api+json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Authorization": f"Bearer {bearer_token}",
        "Connection": "keep-alive",
        "Host": host,
        "Origin": origin,
        "Referer": referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

def fetch_invoice_schemas(bearer_token, output_dir, progress_callback=None):
    """template.jsonの全テンプレートIDについてinvoiceSchemasを取得し保存する"""
    try:
        if progress_callback:
            if not progress_callback(0, 100, "invoiceSchemas取得を開始しています..."):
                return "キャンセルされました"
                
        os.makedirs(os.path.join(output_dir, "invoiceSchemas"), exist_ok=True)
        template_json_path = os.path.join(output_dir, "template.json")
        log_path = os.path.join(output_dir, "invoiceSchemas", "invoiceSchemas_fetch.log")

        if progress_callback:
            if not progress_callback(5, 100, "template.jsonを読み込み中..."):
                return "キャンセルされました"

        try:
            with open(template_json_path, encoding="utf-8") as f:
                template_data = json.load(f)
            template_ids = [t["id"] for t in template_data.get("data", []) if "id" in t]
            logger.info(f"template.json読み込み完了: {len(template_ids)}件のテンプレートID取得")
        except Exception as e:
            logger.error(f"template.json読み込み失敗: {e}")
            template_ids = []

        if progress_callback:
            if not progress_callback(10, 100, f"取得対象: {len(template_ids)}件のテンプレート"):
                return "キャンセルされました"

        summary_path = os.path.join(output_dir, "invoiceSchemas", "summary.json")
        # 既存summary.jsonの読み込み
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        else:
            summary = {"success": [], "failed": {}}

        skipped_count = 0
        skipped_ids = []
        total_templates = len(template_ids)
        
        for idx, template_id in enumerate(template_ids):
            if progress_callback:
                progress_percent = 10 + int((idx / total_templates) * 85)
                message = f"invoiceSchema取得中... ({idx + 1}/{total_templates}): {template_id}"
                if not progress_callback(progress_percent, 100, message):
                    return "キャンセルされました"
                    
            try:
                fetch_invoice_schema_from_api(bearer_token, template_id, output_dir, summary, log_path, summary_path)
            except Exception as e:
                logger.error(f"invoiceSchema取得失敗 (template_id: {template_id}): {e}")
                summary.setdefault("failed", {})[template_id] = str(e)

        # 最終保存
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        if progress_callback:
            progress_callback(100, 100, "invoiceSchema取得完了")
            
        success_count = len(summary.get("success", []))
        failed_count = len(summary.get("failed", {}))
        result_msg = f"invoiceSchema取得完了: 成功={success_count}, 失敗={failed_count}, 総数={total_templates}"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"invoiceSchema取得処理でエラー: {e}"
        logger.error(error_msg)
        if progress_callback:
            progress_callback(100, 100, f"エラー: {error_msg}")
        return error_msg

def get_self_username_from_json(json_path="output/rde/data/self.json"):
    """self.json から userName を取得して返す。存在しない場合は空文字列。"""
    abs_json = os.path.abspath(json_path)
    if not os.path.exists(abs_json):
        logger.warning(f"self.jsonが存在しません: {abs_json}")
        return ""
    try:
        with open(abs_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        username = data.get("data", {}).get("attributes", {}).get("userName", "")
        logger.debug(f"self.jsonからuserName取得: {username}")
        return username
    except Exception as e:
        logger.error(f"self.jsonのuserName取得失敗: {e}")
        return ""
# --- ユーザー自身情報取得 ---
def fetch_self_info_from_api(bearer_token=None, output_dir="output/rde/data", parent_widget=None):
    """
    https://rde-user-api.nims.go.jp/users/self からユーザー情報を取得し、self.jsonとして保存
    
    v2.0.1改善:
    - HTTPエラーの詳細ハンドリング
    - 401/403エラーの明示的な検出と通知
    - エラーメッセージの改善
    
    Args:
        bearer_token: Bearer Token（非推奨、互換性のため残存。Noneの場合は自動選択）
        output_dir: 出力ディレクトリ
        parent_widget: 親ウィジェット（未使用、互換性のため残存）
    """
    # v1.18.4: bearer_token引数は互換性のために残しているが、
    # api_request_helperが自動選択するため、明示的に渡さない
    
    url = "https://rde-user-api.nims.go.jp/users/self"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-user-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        logger.info("ユーザー情報取得開始")
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        
        # レスポンスチェック
        if resp is None:
            error_msg = "ユーザー情報取得失敗: APIリクエストがNoneを返しました（ネットワークエラーまたはタイムアウト）"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # HTTPステータスコードチェック（v2.0.1改善）
        if resp.status_code == 401:
            error_msg = "認証エラー（401）: Bearer Tokenが無効または期限切れです。再ログインしてください。"
            logger.error(error_msg)
            raise Exception(error_msg)
        elif resp.status_code == 403:
            error_msg = "アクセス拒否（403）: このユーザーにはユーザー情報取得の権限がありません。"
            logger.error(error_msg)
            raise Exception(error_msg)
        elif resp.status_code != 200:
            error_msg = f"ユーザー情報取得失敗: HTTPステータス {resp.status_code}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # JSONパース
        try:
            data = resp.json()
        except Exception as json_error:
            error_msg = f"ユーザー情報のJSONパース失敗: {json_error}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # ファイル保存
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "self.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"self.json取得・保存完了: {save_path}")
        return True
        
    except Exception as e:
        logger.error(f"self.json取得・保存失敗: {e}")
        # v2.0.1: エラーを呼び出し元に伝播させる
        raise


def fetch_all_data_entrys_info(bearer_token, output_dir="output/rde/data", progress_callback=None):
    """
    dataset.json内の全データセットIDでfetch_data_entry_info_from_apiを呼び出す
    
    改善版: データセット総数を事前計算し、プログレス更新頻度を向上
    
    Args:
        bearer_token: 認証トークン
        output_dir: 出力ディレクトリ
        progress_callback: プログレスコールバック関数 (current, total, message) -> bool
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        dataset_json = os.path.join(output_dir, "dataset.json")
        
        if not os.path.exists(dataset_json):
            logger.error(f"dataset.jsonが存在しません: {dataset_json}")
            return
        
        if progress_callback:
            if not progress_callback(0, 100, "データエントリ情報取得準備中..."):
                return "キャンセルされました"
            
        with open(dataset_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        datasets = data.get("data", [])
        total_datasets = len(datasets)
        logger.info(f"データエントリ情報取得開始: {total_datasets}件のデータセット処理")
        
        if progress_callback:
            if not progress_callback(5, 100, f"データセット総数: {total_datasets}件"):
                return "キャンセルされました"
        
        processed_count = 0
        error_count = 0
        
        for idx, ds in enumerate(datasets):
            ds_id = ds.get("id")
            if ds_id:
                # プログレス更新（5-95%の範囲）
                if progress_callback:
                    progress_percent = 5 + int((idx / total_datasets) * 90)
                    msg = f"データエントリ取得中 ({idx + 1}/{total_datasets}): {ds_id}"
                    if not progress_callback(progress_percent, 100, msg):
                        return "キャンセルされました"
                
                try:
                    fetch_data_entry_info_from_api(bearer_token, ds_id)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"データエントリ処理失敗: ds_id={ds_id}, error={e}")
                    error_count += 1
        
        result_msg = f"データエントリ情報取得完了: 処理={processed_count}/{total_datasets}, エラー={error_count}"
        logger.info(result_msg)
        
        if progress_callback:
            progress_callback(100, 100, result_msg)
        
        return result_msg
        
    except Exception as e:
        error_msg = f"fetch_all_data_entrys_info処理失敗: {e}"
        logger.error(error_msg)
        if progress_callback:
            progress_callback(100, 100, f"エラー: {error_msg}")
        raise




def fetch_data_entry_info_from_api(bearer_token, dataset_id, output_dir="output/rde/data/dataEntry"):
    """
    指定データセットIDのデータエントリ情報をAPIから取得し、dataEntry.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&sort=-created&page%5Boffset%5D=0&page%5Blimit%5D=24&include=owner%2Csample%2CthumbnailFile%2Cfiles"
    save_path = os.path.join(output_dir, f"{dataset_id}.json")
    
    if os.path.exists(save_path):
        logger.info(f"データエントリファイル既存のためスキップ: {dataset_id}.json")
        return
        
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    
    try:
        logger.debug(f"データエントリ取得開始: dataset_id={dataset_id}")
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        if resp is None:
            logger.error(f"データエントリ取得失敗: dataset_id={dataset_id}")
            return
        resp.raise_for_status()
        data = resp.json()
        
        os.makedirs(output_dir, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"データエントリ取得・保存完了: {dataset_id}.json -> {save_path}")
        
    except Exception as e:
        logger.error(f"データエントリ取得・保存失敗: dataset_id={dataset_id}, error={e}")
        raise


def fetch_invoice_info_from_api(bearer_token, entry_id, output_dir="output/rde/data/invoice"):
    """指定エントリIDのインボイス情報をAPIから取得し、invoice.jsonとして保存"""
    url = f"https://rde-api.nims.go.jp/invoices/{entry_id}?include=submittedBy%2CdataOwner%2Cinstrument"
    save_path = os.path.join(output_dir, f"{entry_id}.json")
    
    if os.path.exists(save_path):
        logger.info(f"インボイスファイル既存のためスキップ: {entry_id}.json")
        return
        
    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    
    try:
        logger.debug(f"インボイス取得開始: entry_id={entry_id}")
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)
        if resp is None:
            logger.error(f"インボイス取得失敗: entry_id={entry_id}")
            return
        resp.raise_for_status()
        data = resp.json()
        
        os.makedirs(output_dir, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"インボイス取得・保存完了: {entry_id}.json -> {save_path}")
        
    except Exception as e:
        logger.error(f"インボイス取得・保存失敗: entry_id={entry_id}, error={e}")
        raise


def fetch_all_invoices_info(bearer_token, output_dir="output/rde/data", progress_callback=None):
    """
    dataEntry.json内の全エントリIDでfetch_invoice_info_from_apiを呼び出す
    
    改善版: データセット数とタイル数から総予定取得数を事前計算し、
    プログレス更新頻度を大幅に向上させて処理の進行状況を明確化
    
    Args:
        bearer_token: 認証トークン
        output_dir: 出力ディレクトリ
        progress_callback: プログレスコールバック関数 (current, total, message) -> bool
    """
    try:
        dataentry_dir = os.path.join(output_dir, "dataEntry")
        invoice_dir = os.path.join(output_dir, "invoice")
        
        if not os.path.exists(dataentry_dir):
            logger.error(f"dataEntryディレクトリが存在しません: {dataentry_dir}")
            return
        
        # === 事前カウント：総予定取得数を計算 ===
        if progress_callback:
            if not progress_callback(0, 100, "インボイス総数を計算中..."):
                return "キャンセルされました"
        
        dataentry_files = glob.glob(os.path.join(dataentry_dir, "*.json"))
        
        # 既存のインボイスファイルをカウント（スキップ予定）
        existing_invoices = set()
        if os.path.exists(invoice_dir):
            existing_invoices = set(os.listdir(invoice_dir))
        
        # 全データエントリファイルを読み込み、総エントリ数を計算
        total_entries = 0
        entry_list = []  # [(file_path, entry_id), ...]
        
        logger.info(f"インボイス情報取得開始: {len(dataentry_files)}件のデータエントリファイルを解析中")
        
        for file_path in dataentry_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                entries = data.get("data", [])
                for entry in entries:
                    entry_id = entry.get("id")
                    if entry_id:
                        entry_list.append((file_path, entry_id))
                        total_entries += 1
                        
            except Exception as e:
                logger.error(f"データエントリファイル読み込み失敗: file={file_path}, error={e}")
        
        # 既存ファイルを除外した新規取得予定数
        new_entries = [e for e in entry_list if f"{e[1]}.json" not in existing_invoices]
        new_count = len(new_entries)
        skip_count = len(entry_list) - new_count
        
        logger.info(f"インボイス取得計画: 総数={total_entries}, 新規取得={new_count}, スキップ={skip_count}")
        
        if progress_callback:
            msg = f"インボイス取得開始 (データセット: {len(dataentry_files)}件, タイル総数: {total_entries}件, 新規: {new_count}件)"
            if not progress_callback(5, 100, msg):
                return "キャンセルされました"
        
        # === メイン処理：インボイス取得 ===
        processed_count = 0
        success_count = 0
        error_count = 0
        
        for idx, (file_path, entry_id) in enumerate(entry_list):
            # プログレス更新（5-95%の範囲で更新）
            if progress_callback:
                progress_percent = 5 + int((idx / total_entries) * 90)
                msg = f"インボイス取得中 ({idx + 1}/{total_entries}): {entry_id}"
                if not progress_callback(progress_percent, 100, msg):
                    return "キャンセルされました"
            
            try:
                fetch_invoice_info_from_api(bearer_token, entry_id, invoice_dir)
                success_count += 1
            except Exception as e:
                logger.error(f"インボイス処理失敗: entry_id={entry_id}, error={e}")
                error_count += 1
            
            processed_count += 1
        
        # === 完了処理 ===
        result_msg = f"インボイス情報取得完了: 処理={processed_count}/{total_entries}, 成功={success_count}, エラー={error_count}"
        logger.info(result_msg)
        
        if progress_callback:
            progress_callback(100, 100, result_msg)
        
        return result_msg
        
    except Exception as e:
        error_msg = f"fetch_all_invoices_info処理失敗: {e}"
        logger.error(error_msg)
        if progress_callback:
            progress_callback(100, 100, f"エラー: {error_msg}")
        raise


def fetch_dataset_info_respectively_from_api(bearer_token, dataset_id, output_dir="output/rde/data/datasets"):
    """指定データセットIDのエントリ情報をAPIから取得し、{dataset_id}.jsonとして保存"""
    url = f"https://rde-api.nims.go.jp/datasets/{dataset_id}?updateViews=true&include=releases%2Capplicant%2Cprogram%2Cmanager%2CrelatedDatasets%2Ctemplate%2Cinstruments%2Clicense%2CsharingGroups&fields%5Brelease%5D=id%2CreleaseNumber%2Cversion%2Cdoi%2Cnote%2CreleaseTime&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Bgroup%5D=id%2Cname&fields%5BdatasetTemplate%5D=id%2CnameJa%2CnameEn%2Cversion%2CdatasetType%2CisPrivate%2CworkflowEnabled&fields%5Binstrument%5D=id%2CnameJa%2CnameEn%2Cstatus&fields%5Blicense%5D=id%2Curl%2CfullName"

    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    
    try:
        logger.debug(f"データセット詳細取得開始: dataset_id={dataset_id}")
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)  # refactored to use api_request_helper
        if resp is None:
            logger.error(f"データセット詳細取得失敗: dataset_id={dataset_id}")
            return
        resp.raise_for_status()
        data = resp.json()
        
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, f"{dataset_id}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"データセット詳細取得・保存完了: {dataset_id}.json -> {save_path}")
        
    except Exception as e:
        logger.error(f"データセット詳細取得・保存失敗: dataset_id={dataset_id}, error={e}")
        raise

# --- API取得系 ---
def fetch_all_dataset_info(bearer_token, output_dir="output/rde/data",onlySelf=False,searchWords=None):
    """データセット情報をAPIから取得し、dataset.jsonとして保存"""
    # デフォルト引数のパス区切りを修正（バックスラッシュ→スラッシュ）
    # output_dir="output/rde/data" に変更
    #url = "https://rde-api.nims.go.jp/datasets?sort=-modified&include=manager%2Creleases&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Brelease%5D=version%2CreleaseNumber"
    userName = get_self_username_from_json()
    
    # パス区切りを統一
    output_dir = os.path.normpath(output_dir)
    if onlySelf is True:
        if searchWords and len(searchWords) > 0 :
            logger.debug("searchWords: %s", searchWords)
            escapedUserName = searchWords.replace(" ", "%20").replace(",", "%2C")
        else:
            logger.debug("UserName: %s", userName)
            escapedUserName = userName.replace(" ", "%20").replace(",", "%2C")
        url = f"https://rde-api.nims.go.jp/datasets?searchWords={escapedUserName}&sort=-modified&page%5Blimit%5D=5000&include=manager%2Creleases&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Brelease%5D=version%2CreleaseNumber"
    else:
        url = "https://rde-api.nims.go.jp/datasets?sort=-modified&page%5Blimit%5D=5000&include=manager%2Creleases&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Brelease%5D=version%2CreleaseNumber"

    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    try:
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)  # refactored to use api_request_helper
        if resp is None:
            logger.error("データセット一覧取得失敗")
            return
        resp.raise_for_status()
        data = resp.json()
        
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "dataset.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info("データセット情報(dataset.json)取得・保存完了")
        
    except Exception as e:
        logger.error(f"データセット情報取得・保存失敗: {e}, URL: {url}")
        raise

    with open(save_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    datasets = data.get("data", [])

    for ds in datasets:
        ds_id = ds.get("id")
        attr = ds.get("attributes", {})
        modifiedAt = attr.get("modified", "")
        filePath = os.path.join("output/rde/data/datasets", f"{ds_id}.json")

        if not ds_id or not modifiedAt:
            continue

        try:
            modified_dt = parse_datetime(modifiedAt)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filePath), timezone.utc) if os.path.exists(filePath) else None

            # ファイルが存在しない、または更新日時より古いなら取得
            if file_mtime is None or file_mtime < modified_dt:
                fetch_dataset_info_respectively_from_api(bearer_token, ds_id)
            else:
                logger.info("%s.jsonは最新です。再取得は行いません。", ds_id)

        except Exception as e:
            logger.error("ds_id=%s の処理中にエラー: %s", ds_id, e)


def fetch_instrument_type_info_from_api(bearer_token, save_path):
    """
    装置タイプ情報をAPIから取得し、instrumentType.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = "https://rde-instrument-api.nims.go.jp/typeTerms?programId=4bbf62be-f270-4a46-9682-38cd064607ba"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-instrument-api.nims.go.jp",
        "Origin": "https://rde-entry-arim.nims.go.jp",
        "Referer": "https://rde-entry-arim.nims.go.jp/"
    }
    try:
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        if resp is None:
            logger.error("装置タイプ情報の取得に失敗しました: リクエストエラー")
            return
        resp.raise_for_status()
        data = resp.json()
        save_json(data, *save_path)
        logger.info("装置タイプ情報の取得・保存に成功しました: %s", os.path.join(*save_path))
    except Exception as e:
        logger.error("装置タイプ情報の取得・保存に失敗しました: %s", e)

def fetch_organization_info_from_api(bearer_token, save_path):
    """
    組織情報をAPIから取得し、organization.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = "https://rde-instrument-api.nims.go.jp/organizations"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-instrument-api.nims.go.jp",
        "Origin": "https://rde-entry-arim.nims.go.jp",
        "Referer": "https://rde-entry-arim.nims.go.jp/"
    }
    try:
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        if resp is None:
            logger.error("組織情報の取得に失敗しました: リクエストエラー")
            return
        resp.raise_for_status()
        data = resp.json()
        save_json(data, *save_path)
        logger.info("組織情報の取得・保存に成功しました: %s", os.path.join(*save_path))
    except Exception as e:
        logger.error("組織情報の取得・保存に失敗しました: %s", e)


def fetch_template_info_from_api(bearer_token, output_dir="output/rde/data"):
    """
    テンプレート情報をAPIから取得し、template.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = "https://rde-api.nims.go.jp/datasetTemplates?programId=4bbf62be-f270-4a46-9682-38cd064607ba&teamId=22398c55-8620-430e-afa5-2405c57dd03c&sort=id&page[limit]=10000&page[offset]=0&include=instruments&fields[instrument]=nameJa%2CnameEn"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=30)  # datasetTemplates は重い処理のためタイムアウト延長
        if resp is None:
            logger.error("テンプレート情報の取得に失敗しました: リクエストエラー")
            return
        resp.raise_for_status()
        data = resp.json()
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "template.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("テンプレート(template.json)の取得・保存に成功しました。")
    except Exception as e:
        logger.error("テンプレートの取得・保存に失敗しました: %s", e)

def fetch_instruments_info_from_api(bearer_token, output_dir="output/rde/data"):
    """
    設備リスト情報をAPIから取得し、instruments.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = "https://rde-instrument-api.nims.go.jp/instruments?programId=4bbf62be-f270-4a46-9682-38cd064607ba&page%5Blimit%5D=10000&sort=id&page%5Boffset%5D=0"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-instrument-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        if resp is None:
            logger.error("装置情報の取得に失敗しました: リクエストエラー")
            return
        resp.raise_for_status()
        data = resp.json()
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "instruments.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("設備情報(instruments.json)の取得・保存に成功しました。")
    except Exception as e:
        logger.error("設備情報の取得・保存に失敗しました: %s", e)

def fetch_licenses_info_from_api(bearer_token, output_dir="output/rde/data"):
    """
    利用ライセンスマスタ情報をAPIから取得し、licenses.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = "https://rde-api.nims.go.jp/licenses"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        if resp is None:
            logger.error("利用ライセンス情報の取得に失敗しました: リクエストエラー")
            return
        resp.raise_for_status()
        data = resp.json()
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "licenses.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("利用ライセンス情報(licenses.json)の取得・保存に成功しました。")
        logger.info(f"利用ライセンス情報取得完了: {len(data.get('data', []))}件のライセンス")
    except Exception as e:
        logger.error("利用ライセンス情報の取得・保存に失敗しました: %s", e)
        logger.error(f"利用ライセンス情報取得失敗: {e}")


# --- グループ情報取得・WebView・info生成 ---
def fetch_group_info_from_api(url, headers, save_path, bearer_token=None):
    resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)  # refactored to use api_request_helper
    if resp is None:
        raise Exception("グループ情報取得失敗: リクエストエラー")
    resp.raise_for_status()
    data = resp.json()
    save_json(data, *save_path)
    return data

def parse_group_id_from_data(data):
    included = data.get("included", [])
    for item in included:
        if item.get("type") == "group" and "id" in item:
            return item["id"]
    return None

def move_webview_to_group(webview, project_group_id):
    import traceback
    logger.debug("move_webview_to_group: called with webview=%s, project_group_id=%s", webview, project_group_id)
    logger.debug("type(webview)=%s, type(project_group_id)=%s", type(webview), type(project_group_id))
    logger.debug("move_webview_to_group")
    try:
        logger.debug("webview: %s", webview)
        logger.debug("project_group_id: %s", project_group_id)
        # webviewの型・状態を詳細に出力
        logger.debug("type(webview): %s", type(webview))
        logger.debug("dir(webview): %s", dir(webview))
        logger.debug("webview is None: %s", webview is None)
        try:
            logger.debug("webview.isWidgetType: %s", getattr(webview, 'isWidgetType', lambda: 'N/A')())
        except Exception as e:
            logger.debug("webview.isWidgetType error: %s", e)
        try:
            logger.debug("webview.isVisible: %s", getattr(webview, 'isVisible', lambda: 'N/A')())
        except Exception as e:
            logger.debug("webview.isVisible error: %s", e)
        try:
            logger.debug("webview.isEnabled: %s", getattr(webview, 'isEnabled', lambda: 'N/A')())
        except Exception as e:
            logger.debug("webview.isEnabled error: %s", e)
        try:
            logger.debug("webview.metaObject: %s", getattr(webview, 'metaObject', lambda: 'N/A')())
        except Exception as e:
            logger.debug("webview.metaObject error: %s", e)
        if webview is None:
            logger.error("webview is None")
            return
        # setUrl前にwebviewを有効化
        try:
            if hasattr(webview, 'setEnabled'):
                webview.setEnabled(True)
                logger.debug("setEnabled(True) 実行")
        except Exception as e:
            logger.error("setEnabled例外: %s", e)
        # setUrlをUIスレッドで実行
        url = f"https://rde.nims.go.jp/rde/datasets/groups/{project_group_id}"
        logger.debug("setUrl前: %s", url)
        try:
            from qt_compat.core import QTimer
            def do_set_url(wv, u):
                try:
                    if wv is None:
                        logger.error("do_set_url: webview is None")
                        return
                    wv.setUrl(u)
                    logger.debug("setUrl後: 正常にsetUrl呼び出し完了")
                except Exception as e:
                    import traceback
                    logger.error("setUrl例外: %s", e)
                    traceback.print_exc()
            QTimer.singleShot(0, lambda: do_set_url(webview, url))
        except Exception as e:
            import traceback
            logger.error("setUrlラップ例外: %s", e)
            traceback.print_exc()
    except Exception as e:
        import traceback
        logger.error("move_webview_to_group例外: %s", e)
        traceback.print_exc()
    else:
        logger.error("move_webview_to_group: webview is None")

def extract_users_and_subgroups(sub_data):
    users = []
    subgroups = []
    for item in sub_data.get('included', []):
        if item.get('type') == 'user':
            attrs = item.get('attributes', {})
            users.append({
                'userId': item.get('id'),
                'userName': attrs.get('userName'),
                'email': attrs.get('emailAddress'),
                'familyName': attrs.get('familyName'),
                'givenName': attrs.get('givenName'),
                'organizationName': attrs.get('organizationName'),
            })
        elif item.get('type') == 'group':
            attrs = item.get('attributes', {})
            subgroups.append({
                'groupId': item.get('id'),
                'name': attrs.get('name'),
                'groupType': attrs.get('groupType'),
                'description': attrs.get('description'),
            })
    return users, subgroups

def show_fetch_confirmation_dialog(parent, onlySelf, searchWords):
    """
    基本情報取得の確認ダイアログを表示
    """
    from qt_compat.widgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QTextEdit
    import json
    
    # 取得対象の情報を生成
    fetch_mode = "検索モード" if onlySelf else "全データセット取得モード"
    search_text = f"検索キーワード: {searchWords}" if searchWords else "検索キーワード: 自分のユーザー名"
    
    # 予想される処理内容
    expected_actions = {
        "共通取得項目": [
            "ユーザー自身情報 (self.json)",
            "グループ情報 (group.json)",
            "グループ詳細情報 (groupDetail.json)",
            "サブグループ情報 (subGroup.json)",
            "組織情報 (organization.json)",
            "装置タイプ情報 (instrumentType.json)",
            "テンプレート情報 (template.json)",
            "設備情報 (instruments.json)",
            "統合情報 (info.json)"
        ],
        "データセット関連": [
            "データセット一覧 (dataset.json)",
            "個別データセット詳細 (datasets/*.json)",
            "データエントリ情報 (dataEntry/*.json)",
            "インボイス情報 (invoice/*.json)"
        ]
    }
    
    if onlySelf:
        warning_text = "検索モード: 指定されたキーワードに一致するデータセットのみを取得します。"
        time_estimate = "推定処理時間: 1-5分程度"
    else:
        warning_text = "全データセット取得モード: 全てのデータセットと個別JSONを取得します。\n⚠️ 大量のデータ取得により長時間を要する可能性があります。"
        time_estimate = "推定処理時間: 5-30分程度（データ量により変動）"
    
    # 詳細情報用のペイロード作成
    payload_info = {
        "取得モード": fetch_mode,
        "検索条件": search_text if onlySelf else "全データセット",
        "取得項目": expected_actions,
        "警告": warning_text,
        "処理時間": time_estimate,
        "出力先": "output/rde/data/",
        "API呼び出し先": [
            "https://rde-user-api.nims.go.jp/users/self",
            "https://rde-api.nims.go.jp/groups/root",
            "https://rde-api.nims.go.jp/datasets",
            "https://rde-instrument-api.nims.go.jp/organizations",
            "https://rde-instrument-api.nims.go.jp/typeTerms",
            "https://rde-api.nims.go.jp/datasetTemplates",
            "https://rde-instrument-api.nims.go.jp/instruments",
            "https://rde-api.nims.go.jp/invoices"
        ]
    }
    
    # 確認メッセージ
    confirmation_text = f"""本当に基本情報取得を実行しますか？

モード: {fetch_mode}
{search_text if onlySelf else '対象: 全データセット'}

{warning_text}
{time_estimate}

この操作により以下の情報が取得されます：
• 共通情報: 9種類のJSON
• データセット関連: 個別データセット + エントリ情報 + インボイス情報

処理中はアプリケーションが応答しなくなる場合があります。"""

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("基本情報取得の確認")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText(confirmation_text)
    yes_btn = msg_box.addButton(QMessageBox.Yes)
    no_btn = msg_box.addButton(QMessageBox.No)
    detail_btn = QPushButton("詳細表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(no_btn)
    msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")

    def show_detail():
        dlg = QDialog(parent)
        dlg.setWindowTitle("取得情報 詳細表示")
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit(dlg)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(json.dumps(payload_info, ensure_ascii=False, indent=2))
        text_edit.setMinimumSize(600, 400)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec()
    
    detail_btn.clicked.connect(show_detail)
    
    reply = msg_box.exec()
    return msg_box.clickedButton() == yes_btn

# === 段階別実行関数 ===

@stage_error_handler("ユーザー情報取得")
def fetch_user_info_stage(bearer_token=None, progress_callback=None, parent_widget=None):
    """段階1: ユーザー情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "ユーザー情報取得中..."):
            return "キャンセルされました"
    
    if not fetch_self_info_from_api(bearer_token, parent_widget=parent_widget):
        return "ユーザー情報取得に失敗しました"
    
    if progress_callback:
        if not progress_callback(100, 100, "ユーザー情報取得完了"):
            return "キャンセルされました"
    
    return "ユーザー情報取得が完了しました"

@stage_error_handler("グループ関連情報取得")
def fetch_group_info_stage(bearer_token, progress_callback=None):
    """段階2: グループ関連情報取得（グループ・詳細・サブグループ）"""
    try:
        headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
        
        if progress_callback:
            if not progress_callback(10, 100, "グループ情報取得中..."):
                return "キャンセルされました"
        
        # グループ情報取得
        group_url = "https://rde-api.nims.go.jp/groups/root?include=children%2Cmembers"
        group_json_path = [OUTPUT_DIR, "rde", "data", "group.json"]
        group_data = fetch_group_info_from_api(group_url, headers, group_json_path)
        
        if progress_callback:
            if not progress_callback(40, 100, "グループ詳細情報取得中..."):
                return "キャンセルされました"
        
        # グループIDを解析
        group_id = parse_group_id_from_data(group_data)
        if not group_id:
            return "グループIDが見つかりません"
        
        # グループ詳細情報取得
        detail_url = f"https://rde-api.nims.go.jp/groups/{group_id}?include=children%2Cmembers"
        detail_json_path = [OUTPUT_DIR, "rde", "data", "groupDetail.json"]
        detail_data = fetch_group_info_from_api(detail_url, headers, detail_json_path)
        
        if progress_callback:
            if not progress_callback(70, 100, "サブグループ情報取得中..."):
                return "キャンセルされました"
        
        # プロジェクトグループIDを解析
        project_group_id = parse_group_id_from_data(detail_data)
        if not project_group_id:
            return "プロジェクトグループIDが見つかりません"
        
        # サブグループ情報取得
        sub_group_url = f"https://rde-api.nims.go.jp/groups/{project_group_id}?include=children%2Cmembers"
        sub_group_json_path = [OUTPUT_DIR, "rde", "data", "subGroup.json"]
        sub_group_data = fetch_group_info_from_api(sub_group_url, headers, sub_group_json_path)
        
        if progress_callback:
            if not progress_callback(100, 100, "グループ関連情報取得完了"):
                return "キャンセルされました"
        
        return "グループ関連情報取得が完了しました"
    except Exception as e:
        error_msg = f"グループ関連情報取得でエラーが発生しました: {e}"
        logger.error(error_msg)
        return error_msg

@stage_error_handler("組織・装置情報取得")
def fetch_organization_stage(bearer_token, progress_callback=None):
    """段階3: 組織・装置情報取得"""
    if progress_callback:
        if not progress_callback(20, 100, "組織情報取得中..."):
            return "キャンセルされました"
    
    org_json_path = [OUTPUT_DIR, "rde", "data", "organization.json"]
    fetch_organization_info_from_api(bearer_token, org_json_path)
    
    if progress_callback:
        if not progress_callback(70, 100, "装置タイプ情報取得中..."):
            return "キャンセルされました"
    
    instrument_type_json_path = [OUTPUT_DIR, "rde", "data", "instrumentType.json"]
    fetch_instrument_type_info_from_api(bearer_token, instrument_type_json_path)
    
    if progress_callback:
        if not progress_callback(100, 100, "組織・装置情報取得完了"):
            return "キャンセルされました"
    
    return "組織・装置情報取得が完了しました"

@stage_error_handler("サンプル情報取得")
def fetch_sample_info_stage(bearer_token, progress_callback=None):
    """段階4: サンプル情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "サブグループ情報確認中..."):
            return "キャンセルされました"
    
    # サブグループ情報から対象グループIDを取得
    if not os.path.exists(SUBGROUP_JSON_PATH):
        return "サブグループ情報が見つかりません。先にグループ関連情報を取得してください。"
    
    with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
        sub_group_data = json.load(f)
        
        sub_group_included = sub_group_data.get("included", [])
        sample_dir = os.path.join(OUTPUT_DIR, "rde", "data", "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        total_samples = len(sub_group_included)
        processed_samples = 0
        
        for idx, included in enumerate(sub_group_included):
            sample_progress = 20 + int((idx / total_samples) * 70) if total_samples > 0 else 90
            group_id_sample = included.get("id", "")
            
            if progress_callback:
                if not progress_callback(sample_progress, 100, f"サンプル情報取得中 ({idx + 1}/{total_samples})"):
                    return "キャンセルされました"
            
            sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")
            
            # 既存ファイルがある場合はスキップ
            if os.path.exists(sample_json_path):
                continue
            
            url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
            try:
                # Material API用のトークンを明示的に取得
                from config.common import load_bearer_token
                material_token = load_bearer_token('rde-material.nims.go.jp')
                headers_sample = _make_headers(material_token, host="rde-material-api.nims.go.jp", origin="https://rde-entry-arim.nims.go.jp", referer="https://rde-entry-arim.nims.go.jp/")
                resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
                if resp is None:
                    continue
                resp.raise_for_status()
                data = resp.json()
                with open(sample_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                processed_samples += 1
            except Exception as e:
                logger.error(f"サンプル情報({group_id_sample})の取得に失敗: {e}")
        
    
    if progress_callback:
        if not progress_callback(100, 100, "サンプル情報取得完了"):
            return "キャンセルされました"
    
    return f"サンプル情報取得が完了しました。処理済み: {processed_samples}件"

@stage_error_handler("データセット情報取得")
def fetch_dataset_info_stage(bearer_token, onlySelf=False, searchWords=None, progress_callback=None):
    """段階5: データセット情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "データセット情報取得中..."):
            return "キャンセルされました"
    
    fetch_all_dataset_info(bearer_token, output_dir=os.path.join(OUTPUT_DIR, "rde", "data"), onlySelf=onlySelf, searchWords=searchWords)
    
    if progress_callback:
        if not progress_callback(100, 100, "データセット情報取得完了"):
            return "キャンセルされました"
    
    return "データセット情報取得が完了しました"

@stage_error_handler("データエントリ情報取得")
def fetch_data_entry_stage(bearer_token, progress_callback=None):
    """段階6: データエントリ情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "データエントリ情報取得中..."):
            return "キャンセルされました"
    
    fetch_all_data_entrys_info(bearer_token)
    
    if progress_callback:
        if not progress_callback(100, 100, "データエントリ情報取得完了"):
            return "キャンセルされました"
    
    return "データエントリ情報取得が完了しました"

@stage_error_handler("インボイス情報取得")
def fetch_invoice_stage(bearer_token, progress_callback=None):
    """段階7: インボイス情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "インボイス情報取得中..."):
            return "キャンセルされました"
    
    fetch_all_invoices_info(bearer_token)
    
    if progress_callback:
        if not progress_callback(100, 100, "インボイス情報取得完了"):
            return "キャンセルされました"
    
    return "インボイス情報取得が完了しました"

@stage_error_handler("テンプレート・設備・ライセンス情報取得")
def fetch_template_instrument_stage(bearer_token, progress_callback=None):
    """段階7: テンプレート・設備・ライセンス情報取得"""
    if progress_callback:
        if not progress_callback(15, 100, "テンプレート情報取得中..."):
            return "キャンセルされました"
    
    fetch_template_info_from_api(bearer_token)
    
    if progress_callback:
        if not progress_callback(50, 100, "設備情報取得中..."):
            return "キャンセルされました"
    
    fetch_instruments_info_from_api(bearer_token)
    
    if progress_callback:
        if not progress_callback(85, 100, "利用ライセンス情報取得中..."):
            return "キャンセルされました"
    
    fetch_licenses_info_from_api(bearer_token)
    
    if progress_callback:
        if not progress_callback(100, 100, "テンプレート・設備・ライセンス情報取得完了"):
            return "キャンセルされました"
    
    return "テンプレート・設備・ライセンス情報取得が完了しました"

@stage_error_handler("invoiceSchema情報取得")
def fetch_invoice_schema_stage(bearer_token, progress_callback=None):
    """段階8: invoiceSchema情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "invoiceSchema情報取得中..."):
            return "キャンセルされました"
    
    output_dir = "output/rde/data"
    result = fetch_invoice_schemas(bearer_token, output_dir, progress_callback)
    
    if progress_callback:
        if not progress_callback(100, 100, "invoiceSchema情報取得完了"):
            return "キャンセルされました"
    
    return result

def finalize_basic_info_stage(webview=None, progress_callback=None):
    """段階8: 統合情報生成・WebView遷移"""
    try:
        if progress_callback:
            if not progress_callback(20, 100, "統合情報生成中..."):
                return "キャンセルされました"
        
        # サブグループ情報から統合情報を生成
        if os.path.exists(SUBGROUP_JSON_PATH):
            with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
                sub_group_data = json.load(f)
            
            # グループIDの解析
            group_path = os.path.join(OUTPUT_DIR, "rde", "data", "group.json")
            group_detail_path = os.path.join(OUTPUT_DIR, "rde", "data", "groupDetail.json")
            
            group_id = None
            project_group_id = None
            
            if os.path.exists(group_path):
                with open(group_path, "r", encoding="utf-8") as f:
                    group_data = json.load(f)
                group_id = parse_group_id_from_data(group_data)
            
            if os.path.exists(group_detail_path):
                with open(group_detail_path, "r", encoding="utf-8") as f:
                    detail_data = json.load(f)
                project_group_id = parse_group_id_from_data(detail_data)
            
            if progress_callback:
                if not progress_callback(60, 100, "WebView遷移中..."):
                    return "キャンセルされました"
            
            # WebView遷移
            if webview and project_group_id:
                move_webview_to_group(webview, project_group_id)
            
            if progress_callback:
                if not progress_callback(80, 100, "統合情報ファイル作成中..."):
                    return "キャンセルされました"
            
            # info.json生成
            users, subgroups = extract_users_and_subgroups(sub_group_data)
            info = {
                'group_id': group_id,
                'project_group_id': project_group_id,
                'users': users,
                'subgroups': subgroups
            }
            info_json_path = [OUTPUT_DIR, 'rde', 'data', 'info.json']
            save_json(info, *info_json_path)
        
        if progress_callback:
            if not progress_callback(100, 100, "統合情報生成完了"):
                return "キャンセルされました"
        
        return "統合情報生成・WebView遷移が完了しました"
    except Exception as e:
        error_msg = f"統合情報生成でエラーが発生しました: {e}"
        logger.error(error_msg)
        return error_msg

def auto_refresh_subgroup_json(bearer_token, progress_callback=None):
    """
    サブグループ作成成功後にsubGroup.jsonを自動再取得する
    """
    try:
        if progress_callback:
            if not progress_callback(20, 100, "サブグループ情報自動更新中..."):
                return "キャンセルされました"
        
        logger.info("サブグループ作成成功 - subGroup.json自動更新開始")
        result = fetch_group_info_stage(bearer_token, progress_callback)
        
        if progress_callback:
            if not progress_callback(100, 100, "サブグループ情報自動更新完了"):
                return "キャンセルされました"
        
        logger.info("サブグループ情報自動更新完了")
        return result
    except Exception as e:
        error_msg = f"サブグループ情報自動更新でエラーが発生しました: {e}"
        logger.error(error_msg)
        return error_msg

def auto_refresh_dataset_json(bearer_token, progress_callback=None):
    """
    データセット開設成功後にdataset.jsonを自動再取得する
    """
    try:
        if progress_callback:
            if not progress_callback(20, 100, "データセット一覧自動更新中..."):
                return "キャンセルされました"
        
        logger.info("データセット開設成功 - dataset.json自動更新開始")
        
        # データセット一覧のみ更新（個別データセット詳細は除く）
        fetch_dataset_list_only(bearer_token, output_dir=os.path.join(OUTPUT_DIR, "rde", "data"))
        
        if progress_callback:
            if not progress_callback(100, 100, "データセット一覧自動更新完了"):
                return "キャンセルされました"
        
        logger.info("データセット一覧自動更新完了")
        return "データセット一覧の自動更新が完了しました"
    except Exception as e:
        error_msg = f"データセット一覧自動更新でエラーが発生しました: {e}"
        logger.error(error_msg)
        return error_msg

# === 段階選択用の実行関数マップ ===
STAGE_FUNCTIONS = {
    "ユーザー情報": fetch_user_info_stage,
    "グループ関連情報": fetch_group_info_stage,
    "組織・装置情報": fetch_organization_stage,
    "サンプル情報": fetch_sample_info_stage,
    "データセット情報": fetch_dataset_info_stage,
    "データエントリ情報": fetch_data_entry_stage,
    "インボイス情報": fetch_invoice_stage,
    "invoiceSchema情報": fetch_invoice_schema_stage,
    "テンプレート・設備・ライセンス情報": fetch_template_instrument_stage,
    "統合情報生成": finalize_basic_info_stage,
    "--- 軽量取得 ---": None,  # セパレータ
    "サンプル情報（軽量）": lambda bearer_token, **kwargs: fetch_sample_info_from_subgroup_ids_only(bearer_token),
    "--- 自動更新 ---": None,  # セパレータ
    "subGroup.json自動更新": auto_refresh_subgroup_json,
    "dataset.json自動更新": auto_refresh_dataset_json
}

def execute_individual_stage(stage_name, bearer_token, webview=None, onlySelf=False, searchWords=None, progress_callback=None):
    """指定された段階を個別実行する"""
    if stage_name not in STAGE_FUNCTIONS:
        return f"不正な段階名です: {stage_name}"
    
    # セパレータの場合は実行しない
    if STAGE_FUNCTIONS[stage_name] is None:
        return f"セパレータアイテムは実行できません: {stage_name}"
    
    logger.info(f"個別段階実行開始: {stage_name}")
    
    try:
        func = STAGE_FUNCTIONS[stage_name]
        
        # 関数のシグネチャに応じて引数を調整
        if stage_name == "データセット情報":
            result = func(bearer_token, onlySelf=onlySelf, searchWords=searchWords, progress_callback=progress_callback)
        elif stage_name == "統合情報生成":
            result = func(webview=webview, progress_callback=progress_callback)
        elif stage_name in ["subGroup.json自動更新", "dataset.json自動更新"]:
            # 自動更新関数は bearer_token と progress_callback のみ
            result = func(bearer_token, progress_callback=progress_callback)
        else:
            result = func(bearer_token, progress_callback=progress_callback)
        
        logger.info(f"個別段階実行完了: {stage_name}")
        return result
    except Exception as e:
        error_msg = f"個別段階実行でエラーが発生しました ({stage_name}): {e}"
        logger.error(error_msg)
        traceback.print_exc()
        return error_msg

def fetch_basic_info_logic(bearer_token, parent=None, webview=None, onlySelf=False, searchWords=None, skip_confirmation=False, progress_callback=None):
    """
    基本情報取得・保存・WebView遷移（開発用）
    
    v2.0.1改善:
    - 事前トークン検証の追加
    - 認証エラー時の再ログイン促進
    - エラーメッセージの明確化
    """
    import traceback
    from core.bearer_token_manager import BearerTokenManager
    from qt_compat.widgets import QMessageBox
    
    # ===== 1. トークン検証（v2.0.1新規追加） =====
    logger.info("基本情報取得開始: トークン検証")
    
    # bearer_tokenが渡されていない、または空の場合はBearerTokenManagerから取得
    if not bearer_token or bearer_token.strip() == "":
        logger.warning("bearer_tokenが未指定のため、BearerTokenManagerから取得します")
        bearer_token = BearerTokenManager.get_valid_token()
    else:
        # 渡されたトークンの有効性を検証
        logger.debug("渡されたbearer_tokenの有効性を検証します")
        if not BearerTokenManager.validate_token(bearer_token):
            logger.warning("渡されたbearer_tokenが無効です")
            bearer_token = None
    
    # トークンが取得できない、または無効な場合
    if not bearer_token:
        error_msg = "認証トークンが無効または期限切れです。"
        logger.error(error_msg)
        
        # 再ログイン促進ダイアログを表示
        if parent and BearerTokenManager.request_relogin_if_invalid(parent):
            # ユーザーが再ログインを選択した場合
            # ログインタブへの切り替えを試みる
            try:
                if hasattr(parent, 'tabs'):
                    # メインウィンドウのタブを検索
                    for i in range(parent.tabs.count()):
                        if parent.tabs.tabText(i) == "ログイン":
                            parent.tabs.setCurrentIndex(i)
                            logger.info("ログインタブに切り替えました")
                            break
                
                # エラーメッセージを表示
                QMessageBox.information(
                    parent,
                    "再ログインが必要",
                    "ログインタブでRDEシステムに再ログインしてください。\n"
                    "ログイン完了後、再度基本情報取得を実行してください。"
                )
            except Exception as e:
                logger.error(f"ログインタブ切り替えエラー: {e}")
        
        return error_msg
    
    logger.info(f"トークン検証成功: {bearer_token[:20]}...")
    
    # ===== 2. 確認ダイアログ表示 =====
    if not skip_confirmation:
        if not show_fetch_confirmation_dialog(parent, onlySelf, searchWords):
            logger.info("基本情報取得処理はユーザーによりキャンセルされました。")
            return "キャンセルされました"
    
    logger.info("基本情報取得処理を開始します")
    
    try:
        # プログレス管理
        stages = [
            ("ユーザー情報取得", 5),
            ("グループ情報取得", 8), 
            ("グループ詳細情報取得", 8),
            ("サブグループ情報取得", 8),
            ("サンプル情報取得", 12),
            ("組織・装置情報取得", 8),
            ("データセット情報取得", 16),
            ("データエントリ情報取得", 12),
            ("インボイス情報取得", 10),
            ("invoiceSchema情報取得", 10),
            ("テンプレート・設備・ライセンス情報取得", 8),
            ("統合情報生成・WebView遷移", 5)
        ]
        
        current_progress = 0
        
        def update_stage_progress(stage_index, stage_progress=100, sub_message=""):
            nonlocal current_progress
            if stage_index > 0:
                # 前の段階まで完了
                current_progress = sum(stage[1] for stage in stages[:stage_index])
            
            # 現在の段階の進捗を加算
            stage_weight = stages[stage_index][1]
            stage_contribution = (stage_progress / 100) * stage_weight
            total_progress = current_progress + stage_contribution
            
            stage_name = stages[stage_index][0]
            message = f"{stage_name}: {sub_message}" if sub_message else stage_name
            
            if progress_callback:
                return progress_callback(int(total_progress), 100, message)
            return True

        # 1. ユーザー自身情報取得
        if not update_stage_progress(0, 0, "開始"):
            return "キャンセルされました"
        
        logger.debug("fetch_self_info_from_api")
        if not fetch_self_info_from_api(bearer_token, parent_widget=parent):
            return "ユーザー情報取得に失敗しました"
        
        if not update_stage_progress(0, 100, "完了"):
            return "キャンセルされました"

        # 2. グループ情報取得
        if not update_stage_progress(1, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_group_info_from_api: group")
        headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
        group_url = "https://rde-api.nims.go.jp/groups/root?include=children%2Cmembers"
        group_json_path = [OUTPUT_DIR, "rde", "data", "group.json"]
        group_data = fetch_group_info_from_api(group_url, headers, group_json_path)
        logger.info("グループ情報の取得・保存に成功しました。")
        
        if not update_stage_progress(1, 100, "完了"):
            return "キャンセルされました"

        # グループIDを解析
        logger.debug("parse_group_id_from_data: group")
        group_id = parse_group_id_from_data(group_data)
        if not group_id:
            error_msg = "included配列にgroup idが見つかりません。"
            logger.error(error_msg)
            return error_msg

        # 3. グループ詳細情報取得
        if not update_stage_progress(2, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_group_info_from_api: detail")
        detail_url = f"https://rde-api.nims.go.jp/groups/{group_id}?include=children%2Cmembers"
        detail_json_path = [OUTPUT_DIR, "rde", "data", "groupDetail.json"]
        detail_data = fetch_group_info_from_api(detail_url, headers, detail_json_path)
        logger.info(f"グループ詳細情報({group_id})の取得・保存に成功しました。")
        
        if not update_stage_progress(2, 100, "完了"):
            return "キャンセルされました"

        # プロジェクトグループIDを解析
        logger.debug("parse_group_id_from_data: detail")
        project_group_id = parse_group_id_from_data(detail_data)
        if not project_group_id:
            error_msg = "groupDetail.jsonのincluded配列にproject group idが見つかりません。"
            logger.error(error_msg)
            return error_msg

        # 4. サブグループ情報取得
        if not update_stage_progress(3, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_group_info_from_api: sub_group")
        sub_group_url = f"https://rde-api.nims.go.jp/groups/{project_group_id}?include=children%2Cmembers"
        sub_group_json_path = [OUTPUT_DIR, "rde", "data", "subGroup.json"]
        try:
            sub_group_data = fetch_group_info_from_api(sub_group_url, headers, sub_group_json_path)
            logger.info(f"サブグループ情報({project_group_id})の取得・保存に成功しました。")
        except Exception as e:
            logger.error(f"サブグループ情報の取得・保存に失敗しました: {e}")
            sub_group_data = None
            
        if not update_stage_progress(3, 100, "完了"):
            return "キャンセルされました"

        # 5. サンプル情報取得
        if not update_stage_progress(4, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_sample_info_from_api")
        sub_group_included = []
        if sub_group_data and isinstance(sub_group_data, dict):
            sub_group_included = sub_group_data.get("included", [])
            
        sample_dir = os.path.join(OUTPUT_DIR, "rde", "data", "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        total_samples = len(sub_group_included)
        processed_samples = 0
        skipped_samples = 0
        
        for idx, included in enumerate(sub_group_included):
            sample_progress = int((idx / total_samples) * 100) if total_samples > 0 else 100
            group_id_sample = included.get("id", "")
            sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")
            
            # 既存ファイルがある場合はスキップ
            if os.path.exists(sample_json_path):
                skipped_samples += 1
                if not update_stage_progress(4, sample_progress, f"サンプル情報確認中 ({idx + 1}/{total_samples}) - スキップ済み: {skipped_samples}"):
                    return "キャンセルされました"
                logger.debug(f"サンプル情報({group_id_sample})は既に存在するためスキップしました: {sample_json_path}")
                continue
                
            if not update_stage_progress(4, sample_progress, f"サンプル情報取得中 ({idx + 1}/{total_samples}) - 処理済み: {processed_samples}"):
                return "キャンセルされました"
                
            url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
            try:
                # Material API用のトークンを明示的に取得
                from config.common import load_bearer_token
                material_token = load_bearer_token('rde-material.nims.go.jp')
                headers_sample = _make_headers(material_token, host="rde-material-api.nims.go.jp", origin="https://rde-entry-arim.nims.go.jp", referer="https://rde-entry-arim.nims.go.jp/")
                resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
                if resp is None:
                    logger.error(f"サンプル情報({group_id_sample})の取得に失敗しました: リクエストエラー")
                    continue
                resp.raise_for_status()
                data = resp.json()
                with open(sample_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                processed_samples += 1
                logger.info(f"サンプル情報({group_id_sample})の取得・保存に成功しました: {sample_json_path}")
            except Exception as e:
                logger.error(f"サンプル情報({group_id_sample})の取得・保存に失敗しました: {e}")
                
        logger.info(f"サンプル情報取得完了: 処理済み {processed_samples}件, スキップ済み {skipped_samples}件")
        if not update_stage_progress(4, 100, "完了"):
            return "キャンセルされました"

        # 6. 組織・装置情報取得
        if not update_stage_progress(5, 0, "組織情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_organization_info_from_api")
        org_json_path = [OUTPUT_DIR, "rde", "data", "organization.json"]
        fetch_organization_info_from_api(bearer_token, org_json_path)
        
        if not update_stage_progress(5, 50, "装置タイプ情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_instrument_type_info_from_api")
        instrument_type_json_path = [OUTPUT_DIR, "rde", "data", "instrumentType.json"]
        fetch_instrument_type_info_from_api(bearer_token, instrument_type_json_path)
        
        if not update_stage_progress(5, 100, "完了"):
            return "キャンセルされました"

        # 7. データセット情報取得
        if not update_stage_progress(6, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_all_dataset_info")
        fetch_all_dataset_info(bearer_token, output_dir=os.path.join(OUTPUT_DIR, "rde", "data"), onlySelf=onlySelf, searchWords=searchWords)
        
        if not update_stage_progress(6, 100, "完了"):
            return "キャンセルされました"

        # 8. データエントリ情報取得
        if not update_stage_progress(7, 0, "データエントリ情報取得準備中"):
            return "キャンセルされました"
            
        logger.debug("fetch_all_data_entrys_info")
        
        # プログレスコールバックを作成（ステージ7の0-100%をマッピング）
        def dataentry_progress_callback(current, total, message):
            return update_stage_progress(7, current, message)
        
        result = fetch_all_data_entrys_info(bearer_token, progress_callback=dataentry_progress_callback)
        if result == "キャンセルされました":
            return "キャンセルされました"
        
        if not update_stage_progress(7, 100, "データエントリ情報取得完了"):
            return "キャンセルされました"

        # 9. インボイス情報取得
        if not update_stage_progress(8, 0, "インボイス情報取得準備中"):
            return "キャンセルされました"
            
        logger.debug("fetch_all_invoices_info")
        
        # プログレスコールバックを作成（ステージ8の0-100%をマッピング）
        def invoice_progress_callback(current, total, message):
            # current, totalは fetch_all_invoices_info 内部の進捗（0-100%）
            # これをステージ8の進捗にマッピング
            return update_stage_progress(8, current, message)
        
        result = fetch_all_invoices_info(bearer_token, progress_callback=invoice_progress_callback)
        if result == "キャンセルされました":
            return "キャンセルされました"
        
        if not update_stage_progress(8, 100, "インボイス情報取得完了"):
            return "キャンセルされました"

        # 10. invoiceSchema情報取得
        if not update_stage_progress(9, 0, "invoiceSchema情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_invoice_schemas")
        try:
            output_dir = "output/rde/data"
            fetch_invoice_schemas(bearer_token, output_dir)
        except Exception as e:
            logger.warning(f"invoiceSchema取得でエラーが発生しましたが処理を続行します: {e}")
        
        if not update_stage_progress(9, 100, "完了"):
            return "キャンセルされました"

        # 11. テンプレート・設備・ライセンス情報取得
        if not update_stage_progress(10, 0, "テンプレート情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_template_info_from_api")
        fetch_template_info_from_api(bearer_token)
        
        if not update_stage_progress(10, 33, "設備情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_instruments_info_from_api")
        fetch_instruments_info_from_api(bearer_token)
        
        if not update_stage_progress(10, 66, "利用ライセンス情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_licenses_info_from_api")
        fetch_licenses_info_from_api(bearer_token)
        
        if not update_stage_progress(10, 100, "完了"):
            return "キャンセルされました"

        # 12. 統合情報生成・WebView遷移
        if not update_stage_progress(11, 0, "統合情報生成中"):
            return "キャンセルされました"
            
        # WebView遷移はUIスレッドで行う
        logger.debug("move_webview_to_group")
        move_webview_to_group(webview, project_group_id)
        
        if not update_stage_progress(11, 50, "統合情報ファイル作成中"):
            return "キャンセルされました"

        # info.json生成
        if sub_group_data:
            try:
                logger.debug("extract_users_and_subgroups")
                users, subgroups = extract_users_and_subgroups(sub_group_data)
                info = {
                    'group_id': group_id,
                    'project_group_id': project_group_id,
                    'users': users,
                    'subgroups': subgroups
                }
                info_json_path = [OUTPUT_DIR, 'rde', 'data', 'info.json']
                save_json(info, *info_json_path)
                logger.info("info.json（ユーザー・サブグループ情報）を書き出しました。")
            except Exception as e:
                logger.error(f"subGroup.jsonの解析・表示に失敗しました: {e}")
                traceback.print_exc()
                
        if not update_stage_progress(11, 100, "完了"):
            return "キャンセルされました"
            
        result_msg = "基本情報取得が正常に完了しました"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"基本情報取得でエラーが発生しました: {e}"
        logger.error(error_msg)
        traceback.print_exc()
        return error_msg

def fetch_sample_info_only(bearer_token, output_dir="output/rde/data", progress_callback=None):
    """
    サンプル情報のみを強制取得・保存（既存ファイルも上書き）
    """
    if not bearer_token:
        error_msg = "Bearerトークンが取得できません。ログイン状態を確認してください。"
        logger.error(error_msg)
        return error_msg
    
    logger.info("サンプル情報強制取得開始")
    
    try:
        if progress_callback:
            if not progress_callback(5, 100, "サブグループ情報を読み込み中..."):
                return "キャンセルされました"
        
        # サブグループ情報から対象グループIDを取得
        sub_group_path = os.path.join(output_dir, "subGroup.json")
        if not os.path.exists(sub_group_path):
            error_msg = "subGroup.jsonが存在しません。先に基本情報取得または共通情報取得を実行してください。"
            logger.error(error_msg)
            return error_msg
            
        with open(sub_group_path, "r", encoding="utf-8") as f:
            sub_group_data = json.load(f)
            
        sub_group_included = sub_group_data.get("included", [])
        if not sub_group_included:
            error_msg = "subGroup.jsonにincluded配列が見つかりません。"
            logger.error(error_msg)
            return error_msg
            
        if progress_callback:
            if not progress_callback(10, 100, f"対象グループ数: {len(sub_group_included)}"):
                return "キャンセルされました"
        
        sample_dir = os.path.join(output_dir, "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        total_samples = len(sub_group_included)
        processed_samples = 0
        failed_samples = 0
        
        for idx, included in enumerate(sub_group_included):
            sample_progress = 10 + int((idx / total_samples) * 80) if total_samples > 0 else 90
            group_id_sample = included.get("id", "")
            
            if not group_id_sample:
                logger.warning(f"グループID が空のため、サンプル{idx + 1}をスキップしました")
                continue
                
            if progress_callback:
                if not progress_callback(sample_progress, 100, f"サンプル情報取得中 ({idx + 1}/{total_samples}) - ID: {group_id_sample}"):
                    return "キャンセルされました"
                    
            url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
            sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")
            
            try:
                # Material API用のトークンを明示的に取得
                from config.common import load_bearer_token
                material_token = load_bearer_token('rde-material.nims.go.jp')
                headers_sample = _make_headers(material_token, host="rde-material-api.nims.go.jp", origin="https://rde-entry-arim.nims.go.jp", referer="https://rde-entry-arim.nims.go.jp/")
                resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
                if resp is None:
                    failed_samples += 1
                    logger.error(f"サンプル情報({group_id_sample})の取得に失敗しました: リクエストエラー")
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                
                # 強制上書き保存
                with open(sample_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
                processed_samples += 1
                logger.info(f"サンプル情報({group_id_sample})の強制取得・保存に成功しました: {sample_json_path}")
                
            except Exception as e:
                failed_samples += 1
                logger.error(f"サンプル情報({group_id_sample})の取得・保存に失敗しました: {e}")
                
        if progress_callback:
            if not progress_callback(95, 100, "サンプル情報取得完了処理中..."):
                return "キャンセルされました"
                
        result_msg = f"サンプル情報強制取得が完了しました。成功: {processed_samples}件, 失敗: {failed_samples}件, 総数: {total_samples}件"
        logger.info(result_msg)
        
        if progress_callback:
            if not progress_callback(100, 100, "完了"):
                return "キャンセルされました"
                
        return result_msg
        
    except Exception as e:
        error_msg = f"サンプル情報取得でエラーが発生しました: {e}"
        logger.error(error_msg)
        traceback.print_exc()
        return error_msg

def fetch_sample_info_from_subgroup_ids_only(bearer_token, output_dir="output/rde/data"):
    r"""
    subGroup.jsonの各IDについてoutput\rde\data\samples\{id}.jsonのみを軽量取得
    データ登録後の自動取得用に最適化された関数
    """
    if not bearer_token:
        error_msg = "Bearerトークンが取得できません"
        logger.error(error_msg)
        return error_msg
    
    try:
        # サブグループ情報から対象グループIDを取得
        sub_group_path = os.path.join(output_dir, "subGroup.json")
        if not os.path.exists(sub_group_path):
            error_msg = "subGroup.jsonが存在しません"
            logger.error(error_msg)
            return error_msg
            
        with open(sub_group_path, "r", encoding="utf-8") as f:
            sub_group_data = json.load(f)
            
        sub_group_included = sub_group_data.get("included", [])
        if not sub_group_included:
            error_msg = "subGroup.jsonにincluded配列が見つかりません"
            logger.error(error_msg)
            return error_msg
        
        sample_dir = os.path.join(output_dir, "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        total_samples = len(sub_group_included)
        processed_samples = 0
        failed_samples = 0
        
        logger.info(f"サンプル情報軽量取得開始: {total_samples}件")
        
        for idx, included in enumerate(sub_group_included):
            group_id_sample = included.get("id", "")
            
            if not group_id_sample:
                logger.warning(f"グループID が空のため、サンプル{idx + 1}をスキップしました")
                continue
                    
            url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
            sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")
            
            try:
                # Material API用のトークンを明示的に取得
                from config.common import load_bearer_token
                material_token = load_bearer_token('rde-material.nims.go.jp')
                headers_sample = _make_headers(material_token, host="rde-material-api.nims.go.jp", origin="https://rde-entry-arim.nims.go.jp", referer="https://rde-entry-arim.nims.go.jp/")
                resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
                if resp is None:
                    failed_samples += 1
                    logger.error(f"サンプル情報({group_id_sample})の取得に失敗: リクエストエラー")
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                
                # 軽量保存（上書き）
                with open(sample_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
                processed_samples += 1
                logger.debug(f"サンプル情報({group_id_sample})の軽量取得完了: {sample_json_path}")
                
            except Exception as e:
                failed_samples += 1
                logger.error(f"サンプル情報({group_id_sample})の取得失敗: {e}")
                
        result_msg = f"サンプル情報軽量取得完了: 成功={processed_samples}件, 失敗={failed_samples}件, 総数={total_samples}件"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"サンプル情報軽量取得でエラー: {e}"
        logger.error(error_msg)
        return error_msg

def fetch_sample_info_for_dataset_only(bearer_token, dataset_id, output_dir="output/rde/data"):
    """
    指定されたデータセットIDの個別データセットJSONからグループIDを取得し、
    そのグループのサンプル情報のみを取得する（データ登録後の自動取得用）
    
    注意: bearer_tokenはOptional（None可）。API呼び出し時に自動選択される。
    """
    # 注意: Bearer Tokenチェックを削除（API呼び出し時に自動選択される）
        
    if not dataset_id:
        error_msg = "データセットIDが指定されていません"
        logger.error(error_msg)
        return error_msg
    
    try:
        # 個別データセットJSONからグループIDを取得
        dataset_json_path = os.path.join(output_dir, "datasets", f"{dataset_id}.json")
        if not os.path.exists(dataset_json_path):
            error_msg = f"個別データセットJSONが存在しません: {dataset_json_path}"
            logger.error(error_msg)
            return error_msg
            
        with open(dataset_json_path, "r", encoding="utf-8") as f:
            dataset_data = json.load(f)
            
        # data.relationships.group.data.id からグループIDを取得
        group_data = dataset_data.get("data", {}).get("relationships", {}).get("group", {}).get("data", {})
        group_id = group_data.get("id", "")
        
        if not group_id:
            error_msg = f"データセット{dataset_id}からグループIDを取得できません"
            logger.error(error_msg)
            return error_msg
        
        logger.info(f"データセット{dataset_id}のグループID取得: {group_id}")
        
        # サンプル情報を取得
        sample_dir = os.path.join(output_dir, "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
        sample_json_path = os.path.join(sample_dir, f"{group_id}.json")
        
        # ヘッダー設定（Authorizationは削除、api_request内で自動選択）
        headers_sample = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Host": "rde-material-api.nims.go.jp",
            "Origin": "https://rde-entry-arim.nims.go.jp",
            "Referer": "https://rde-entry-arim.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        
        # bearer_token=Noneで自動選択（Material API用トークンが自動的に選ばれる）
        resp = api_request("GET", url, bearer_token=None, headers=headers_sample, timeout=10)
        if resp is None:
            error_msg = f"サンプル情報({group_id})の取得に失敗: リクエストエラー"
            logger.error(error_msg)
            return error_msg
        
        resp.raise_for_status()
        data = resp.json()
        
        # サンプル情報を保存
        with open(sample_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        result_msg = f"データセット{dataset_id}のサンプル情報取得完了: グループ{group_id} -> {sample_json_path}"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"データセット{dataset_id}のサンプル情報取得でエラー: {e}"
        logger.error(error_msg)
        return error_msg

def fetch_common_info_only_logic(bearer_token, parent=None, webview=None, progress_callback=None):
    """
    7種類の共通情報JSONのみを取得・保存（個別データセットJSONは取得しない）
    
    v2.0.1改善:
    - 事前トークン検証の追加
    - 認証エラー時の再ログイン促進
    - エラーメッセージの明確化
    """
    import traceback
    from core.bearer_token_manager import BearerTokenManager
    from qt_compat.widgets import QMessageBox
    
    # ===== 1. トークン検証（v2.0.1新規追加） =====
    logger.info("共通情報取得開始: トークン検証")
    
    # bearer_tokenが渡されていない、または空の場合はBearerTokenManagerから取得
    if not bearer_token or bearer_token.strip() == "":
        logger.warning("bearer_tokenが未指定のため、BearerTokenManagerから取得します")
        bearer_token = BearerTokenManager.get_valid_token()
    else:
        # 渡されたトークンの有効性を検証
        logger.debug("渡されたbearer_tokenの有効性を検証します")
        if not BearerTokenManager.validate_token(bearer_token):
            logger.warning("渡されたbearer_tokenが無効です")
            bearer_token = None
    
    # トークンが取得できない、または無効な場合
    if not bearer_token:
        error_msg = "認証トークンが無効または期限切れです。"
        logger.error(error_msg)
        
        # 再ログイン促進ダイアログを表示
        if parent and BearerTokenManager.request_relogin_if_invalid(parent):
            # ユーザーが再ログインを選択した場合
            # ログインタブへの切り替えを試みる
            try:
                if hasattr(parent, 'tabs'):
                    # メインウィンドウのタブを検索
                    for i in range(parent.tabs.count()):
                        if parent.tabs.tabText(i) == "ログイン":
                            parent.tabs.setCurrentIndex(i)
                            logger.info("ログインタブに切り替えました")
                            break
                
                # エラーメッセージを表示
                QMessageBox.information(
                    parent,
                    "再ログインが必要",
                    "ログインタブでRDEシステムに再ログインしてください。\n"
                    "ログイン完了後、再度共通情報取得を実行してください。"
                )
            except Exception as e:
                logger.error(f"ログインタブ切り替えエラー: {e}")
        
        return error_msg
    
    logger.info(f"トークン検証成功: {bearer_token[:20]}...")
    logger.info("共通情報取得処理を開始します")
    
    try:
        # プログレス管理 - 7段階の共通情報取得
        stages = [
            ("ユーザー情報取得", 15),
            ("グループ関連情報取得", 25), 
            ("組織・装置情報取得", 20),
            ("データセット一覧取得", 15),
            ("テンプレート・設備・ライセンス情報取得", 15),
            ("統合情報生成", 10)
        ]
        
        current_progress = 0
        
        def update_stage_progress(stage_index, stage_progress=100, sub_message=""):
            nonlocal current_progress
            if stage_index > 0:
                # 前の段階まで完了
                current_progress = sum(stage[1] for stage in stages[:stage_index])
            
            # 現在の段階の進捗を加算
            stage_weight = stages[stage_index][1]
            stage_contribution = (stage_progress / 100) * stage_weight
            total_progress = current_progress + stage_contribution
            
            stage_name = stages[stage_index][0]
            message = f"{stage_name}: {sub_message}" if sub_message else stage_name
            
            if progress_callback:
                return progress_callback(int(total_progress), 100, message)
            return True

        # 1. ユーザー自身情報取得
        if not update_stage_progress(0, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_self_info_from_api")
        if not fetch_self_info_from_api(bearer_token, parent_widget=parent):
            return "ユーザー情報取得に失敗しました"
        
        if not update_stage_progress(0, 100, "完了"):
            return "キャンセルされました"

        # 2. グループ関連情報取得（グループ、グループ詳細、サブグループ）
        if not update_stage_progress(1, 0, "グループ情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_group_info_from_api: group")
        headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
        group_url = "https://rde-api.nims.go.jp/groups/root?include=children%2Cmembers"
        group_json_path = [OUTPUT_DIR, "rde", "data", "group.json"]
        group_data = fetch_group_info_from_api(group_url, headers, group_json_path)
        logger.info("グループ情報の取得・保存に成功しました。")
        
        if not update_stage_progress(1, 33, "グループ詳細情報取得中"):
            return "キャンセルされました"

        logger.debug("parse_group_id_from_data: group")
        group_id = parse_group_id_from_data(group_data)
        if not group_id:
            error_msg = "included配列にgroup idが見つかりません。"
            logger.error(error_msg)
            return error_msg

        # グループ詳細情報取得
        logger.debug("fetch_group_info_from_api: detail")
        detail_url = f"https://rde-api.nims.go.jp/groups/{group_id}?include=children%2Cmembers"
        detail_json_path = [OUTPUT_DIR, "rde", "data", "groupDetail.json"]
        detail_data = fetch_group_info_from_api(detail_url, headers, detail_json_path)
        logger.info(f"グループ詳細情報({group_id})の取得・保存に成功しました。")
        
        if not update_stage_progress(1, 67, "サブグループ情報取得中"):
            return "キャンセルされました"

        logger.debug("parse_group_id_from_data: detail")
        project_group_id = parse_group_id_from_data(detail_data)
        if not project_group_id:
            error_msg = "groupDetail.jsonのincluded配列にproject group idが見つかりません。"
            logger.error(error_msg)
            return error_msg

        # サブグループ情報取得
        logger.debug("fetch_group_info_from_api: sub_group")
        sub_group_url = f"https://rde-api.nims.go.jp/groups/{project_group_id}?include=children%2Cmembers"
        sub_group_json_path = [OUTPUT_DIR, "rde", "data", "subGroup.json"]
        try:
            sub_group_data = fetch_group_info_from_api(sub_group_url, headers, sub_group_json_path)
            logger.info(f"サブグループ情報({project_group_id})の取得・保存に成功しました。")
        except Exception as e:
            logger.error(f"サブグループ情報の取得・保存に失敗しました: {e}")
            sub_group_data = None
            
        if not update_stage_progress(1, 100, "完了"):
            return "キャンセルされました"

        # 3. 組織・装置情報取得
        if not update_stage_progress(2, 0, "組織情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_organization_info_from_api")
        org_json_path = [OUTPUT_DIR, "rde", "data", "organization.json"]
        fetch_organization_info_from_api(bearer_token, org_json_path)
        
        if not update_stage_progress(2, 50, "装置タイプ情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_instrument_type_info_from_api")
        instrument_type_json_path = [OUTPUT_DIR, "rde", "data", "instrumentType.json"]
        fetch_instrument_type_info_from_api(bearer_token, instrument_type_json_path)
        
        if not update_stage_progress(2, 100, "完了"):
            return "キャンセルされました"

        # 4. データセット一覧取得（個別詳細は取得しない）
        if not update_stage_progress(3, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_dataset_list_only")
        fetch_dataset_list_only(bearer_token, output_dir=os.path.join(OUTPUT_DIR, "rde", "data"))
        
        if not update_stage_progress(3, 100, "完了"):
            return "キャンセルされました"

        # 5. テンプレート・設備・ライセンス情報取得
        if not update_stage_progress(4, 0, "テンプレート情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_template_info_from_api")
        fetch_template_info_from_api(bearer_token)
        
        if not update_stage_progress(4, 33, "設備情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_instruments_info_from_api")
        fetch_instruments_info_from_api(bearer_token)
        
        if not update_stage_progress(4, 66, "利用ライセンス情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_licenses_info_from_api")
        fetch_licenses_info_from_api(bearer_token)
        
        if not update_stage_progress(4, 100, "完了"):
            return "キャンセルされました"

        # 6. 統合情報生成
        if not update_stage_progress(5, 0, "開始"):
            return "キャンセルされました"
            
        # info.json生成
        if sub_group_data:
            try:
                logger.debug("extract_users_and_subgroups")
                users, subgroups = extract_users_and_subgroups(sub_group_data)
                info = {
                    'group_id': group_id,
                    'project_group_id': project_group_id,
                    'users': users,
                    'subgroups': subgroups
                }
                info_json_path = [OUTPUT_DIR, 'rde', 'data', 'info.json']
                save_json(info, *info_json_path)
                logger.info("info.json（ユーザー・サブグループ情報）を書き出しました。")
            except Exception as e:
                logger.error(f"subGroup.jsonの解析・表示に失敗しました: {e}")
                traceback.print_exc()
                
        if not update_stage_progress(5, 100, "完了"):
            return "キャンセルされました"
            
        result_msg = "共通情報取得が正常に完了しました"
        logger.info(result_msg)
        return result_msg
        
    except Exception as e:
        error_msg = f"共通情報取得でエラーが発生しました: {e}"
        logger.error(error_msg)
        traceback.print_exc()
        return error_msg

def fetch_dataset_list_only(bearer_token, output_dir="output/rde/data"):
    """データセット一覧のみを取得し、dataset.jsonとして保存（個別JSONは取得しない）"""
    userName = get_self_username_from_json()
    
    # パス区切りを統一
    output_dir = os.path.normpath(output_dir)
    url = "https://rde-api.nims.go.jp/datasets?sort=-modified&page%5Blimit%5D=5000&include=manager%2Creleases&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Brelease%5D=version%2CreleaseNumber"

    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    try:
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)  # refactored to use api_request_helper
        if resp is None:
            logger.error("データセット一覧の取得に失敗しました: リクエストエラー")
            return
        data = resp.json()
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "dataset.json")
        
        # 既存ファイルのバックアップを作成
        if os.path.exists(save_path):
            import shutil
            backup_path = save_path + ".backup"
            try:
                shutil.copy2(save_path, backup_path)
                logger.info("既存ファイルのバックアップを作成: %s", backup_path)
            except Exception as backup_error:
                logger.warning("バックアップ作成に失敗: %s", backup_error)
        
        # 新しいファイルを書き込み
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("データセット一覧(dataset.json)の取得・保存に成功しました。")
    except Exception as e:
        logger.error("データセット一覧の取得・保存に失敗しました: %s URL: %s", e, url)

def get_json_status_info():
    """
    JSONファイルの取得状況（日時、ファイル数等）を取得
    """
    import glob
    from datetime import datetime
    
    json_info = {}
    base_path = os.path.join(OUTPUT_DIR, "rde", "data")
    
    # 10種類の共通JSONファイル（ライセンス情報を追加）
    common_files = [
        "self.json", "group.json", "groupDetail.json", "subGroup.json",
        "organization.json", "instrumentType.json", "template.json", 
        "instruments.json", "licenses.json", "info.json", "dataset.json"
    ]
    
    for file_name in common_files:
        file_path = os.path.join(base_path, file_name)
        if os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            json_info[file_name] = {
                "exists": True,
                "modified": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(os.path.getsize(file_path) / 1024, 2)
            }
        else:
            json_info[file_name] = {"exists": False, "modified": "未取得", "size_kb": 0}
    
    # 個別データセットJSON数をカウント
    datasets_dir = os.path.join(base_path, "datasets")
    dataset_count = len(glob.glob(os.path.join(datasets_dir, "*.json"))) if os.path.exists(datasets_dir) else 0
    
    # データエントリJSON数をカウント
    dataentry_dir = os.path.join(base_path, "dataEntry")
    dataentry_count = len(glob.glob(os.path.join(dataentry_dir, "*.json"))) if os.path.exists(dataentry_dir) else 0
    
    # サンプル情報JSON数をカウント
    samples_dir = os.path.join(base_path, "samples")
    sample_count = len(glob.glob(os.path.join(samples_dir, "*.json"))) if os.path.exists(samples_dir) else 0
    
    json_info["summary"] = {
        "individual_datasets": dataset_count,
        "data_entries": dataentry_count,
        "sample_files": sample_count,
        "common_files_count": len([f for f in common_files if json_info[f]["exists"]])
    }
    
    return json_info

# XLSX書き出しロジックは xlsx_exporter.py に分離

## XLSXサマリー書き出しロジックも xlsx_exporter.py に分離

def write_summary_sheet(wb, parent):
    import json, os
    logger.debug("[XLSX] write_summary_sheet called")

    def load_json(path):
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            logger.error("%sが存在しません: %s", path, abs_path)
            return None
        with open(abs_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 各種JSONロード
    sub_group_json = load_json(SUBGROUP_JSON_PATH)
    dataset_json = load_json(get_dynamic_file_path("output/rde/data/dataset.json"))
    instruments_json = load_json(get_dynamic_file_path("output/rde/data/instruments.json"))
    templates_json = load_json(get_dynamic_file_path("output/rde/data/template.json"))
    if not all([sub_group_json, dataset_json, instruments_json, templates_json]):
        return

    subGroup_included = sub_group_json.get("included", [])

def get_stage_completion_status():
    """
    各段階の完了状況を取得する
    """
    base_path = os.path.join(OUTPUT_DIR, "rde", "data")
    
    stages = {
        "ユーザー情報": ["self.json"],
        "グループ関連情報": ["group.json", "groupDetail.json", "subGroup.json"],
        "組織・装置情報": ["organization.json", "instrumentType.json"],
        "サンプル情報": ["samples"],  # ディレクトリ
        "データセット情報": ["dataset.json", "datasets"],  # ファイル+ディレクトリ
        "データエントリ情報": ["dataEntry"],  # ディレクトリ
        "インボイス情報": ["invoice"],  # ディレクトリ
        "invoiceSchema情報": ["invoiceSchemas"],  # ディレクトリ
        "テンプレート・設備情報": ["template.json", "instruments.json"],
        "統合情報生成": ["info.json"]
    }
    
    status = {}
    
    for stage_name, required_items in stages.items():
        completed_items = 0
        total_items = len(required_items)
        
        for item in required_items:
            item_path = os.path.join(base_path, item)
            if os.path.exists(item_path):
                if os.path.isfile(item_path):
                    # ファイルの場合はサイズをチェック
                    if os.path.getsize(item_path) > 0:
                        completed_items += 1
                elif os.path.isdir(item_path):
                    # ディレクトリの場合は中身があるかチェック
                    if os.listdir(item_path):
                        completed_items += 1
        
        completion_rate = (completed_items / total_items) * 100 if total_items > 0 else 0
        status[stage_name] = {
            "completed": completed_items,
            "total": total_items,
            "rate": completion_rate,
            "status": "完了" if completion_rate == 100 else "未完了" if completion_rate == 0 else "部分完了"
        }
    
    return status
    dataset_data = dataset_json.get("data", [])
    instruments_data = instruments_json.get("data", [])

    # --- 3層構造ヘッダ定義 ---
    HEADER_DEF = [
        {"id": "subGroupName", "label": "サブグループ名"},
        {"id": "dataset_manager_name", "label": "管理者名"},
        {"id": "dataset_applicant_name", "label": "申請者名"},
        {"id": "dataset_owner_names_str", "label": "オーナー名リスト"},
        {"id": "grantNumber", "label": "課題番号"},
        {"id": "title", "label": "課題名"},
        {"id": "datasetName", "label": "データセット名"},
        {"id": "instrument_name", "label": "装置名"},
        {"id": "instrument_local_id", "label": "装置 ID"},
        {"id": "template_id", "label": "テンプレートID"},
        {"id": "datasetId", "label": "データセットID"},
        {"id": "dataEntryName", "label": "データエントリ名"},
        {"id": "dataEntryId", "label": "データエントリID"},
        {"id": "number_of_files", "label": "ファイル数"},
        {"id": "number_of_image_files", "label": "画像ファイル数"},
        {"id": "date_of_dataEntry_creation", "label": "データエントリ作成日"},
        {"id": "total_file_size_MB", "label": "ファイル合計サイズ(MB)"},
        {"id": "dataset_embargoDate", "label": "エンバーゴ日"},
        {"id": "dataset_isAnonymized", "label": "匿名化"},
        {"id": "dataset_description", "label": "データセット説明"},
        {"id": "dataset_relatedLinks", "label": "関連リンク"},
        {"id": "dataset_relatedDatasets", "label": "関連データセット"},
    ]
    # instrument_local_id列にはinstruments.jsonのattributes.programs[].localIdを出力
    instrument_id_to_localid = {}
    for inst in instruments_data:
        inst_id = inst.get("id")
        programs = inst.get("attributes", {}).get("programs", [])
        # 複数programsがある場合はカンマ区切りで連結
        local_ids = [prog.get("localId", "") for prog in programs if prog.get("localId")]
        if inst_id and local_ids:
            instrument_id_to_localid[inst_id] = ",".join(local_ids)
    SHEET_NAME = "summary"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        # 既存ヘッダー行（1行目）を取得
        existing_id_row = [cell.value for cell in ws[1]] if ws.max_row >= 1 else []
    else:
        ws = wb.create_sheet(SHEET_NAME)
        existing_id_row = []

    # 既存ID列の順番を優先し、なければHEADER_DEF順で追加（空文字列やNoneは除外）
    header_ids = []
    id_to_label = {coldef["id"]: coldef["label"] for coldef in HEADER_DEF}
    if existing_id_row and any(existing_id_row):
        # 既存ヘッダーの順番（空文字列やNoneは除外）
        header_ids = [id_ for id_ in existing_id_row if id_ not in (None, "") and str(id_).strip() != ""]
        # HEADER_DEFにあるが既存ヘッダーにないものを追加
        for coldef in HEADER_DEF:
            if coldef["id"] not in header_ids:
                header_ids.append(coldef["id"])
    else:
        header_ids = [coldef["id"] for coldef in HEADER_DEF]
    # 1行目:ID（空値列は除外済みだが念のため）
    for col_idx, id_ in enumerate(header_ids, 1):
        if id_ not in (None, "") and str(id_).strip() != "":
            ws.cell(row=1, column=col_idx, value=id_)
    # 2行目:ラベル
    for col_idx, id_ in enumerate(header_ids, 1):
        if id_ not in (None, "") and str(id_).strip() != "":
            ws.cell(row=2, column=col_idx, value=id_to_label.get(id_, id_))
    id_to_col = {id_: idx+1 for idx, id_ in enumerate(header_ids) if id_ not in (None, "") and str(id_).strip() != ""}

    # 既存データの保存（3行目以降）
    # datasetId, dataEntryId をキーに、手動列（HEADER_DEFにない列）の値を保存
    manual_col_ids = [id_ for id_ in header_ids if id_ not in [coldef["id"] for coldef in HEADER_DEF] and id_ not in (None, "") and str(id_).strip() != ""]
    manual_data_map = {}  # key: ("dataEntryId", id) or ("datasetId", id) -> {manual_col: value, ...}
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row, max_col=len(header_ids)):
        # header_idsとrowの長さが異なる場合も安全にペア化
        row_dict = {id_: cell.value for id_, cell in zip(header_ids, row) if id_ not in (None, "") and str(id_).strip() != ""}
        dataset_id = row_dict.get("datasetId", "")
        data_entry_id = row_dict.get("dataEntryId", "")
        if data_entry_id:
            manual_data_map[("dataEntryId", data_entry_id)] = {col: row_dict.get(col, None) for col in manual_col_ids if col not in (None, "") and str(col).strip() != ""}
        elif dataset_id:
            manual_data_map[("datasetId", dataset_id)] = {col: row_dict.get(col, None) for col in manual_col_ids if col not in (None, "") and str(col).strip() != ""}
    # 既存データを一旦全削除（3行目以降）
    if ws.max_row >= 3:
        ws.delete_rows(3, ws.max_row - 2)

    # ユーザーID→名前辞書
    user_id_to_name = {user.get("id"): user.get("attributes", {}).get("userName", "") for user in subGroup_included if user.get("type") == "user"}
    instrument_id_to_name = {inst.get("id"): inst.get("attributes", {}).get("nameJa", "") for inst in instruments_data}

    from dateutil.parser import parse as parse_datetime
    def to_ymd(date_str):
        if not date_str:
            return ""
        try:
            dt = parse_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return date_str

    def get_dataset_related_info(dataset_datum):
        attr = dataset_datum.get("attributes", {})
        rel = dataset_datum.get("relationships", {})
        return {
            "id": dataset_datum.get("id", ""),
            "manager_id": rel.get("manager", {}).get("data", {}).get("id", ""),
            "owners": rel.get("dataOwners", {}).get("data", []),
            "applicant_id": rel.get("applicant", {}).get("data", {}).get("id", ""),
            "template_id": rel.get("template", {}).get("data", {}).get("id", ""),
            "instrument_id": rel.get("instruments", {}).get("data", [{}])[0].get("id", "") if rel.get("instruments", {}).get("data") else "",
            "embargoDate": to_ymd(attr.get("embargoDate", "")),
            "isAnonymized": attr.get("isAnonymized", ""),
            "description": attr.get("description", ""),
            "relatedLinks_str": "\n".join([link.get("url", "") for link in attr.get("relatedLinks", []) if isinstance(link, dict)]),
            "relatedDatasets_urls_str": "\n".join([f"https://rde.nims.go.jp/datasets/rde/{rd.get('id', '')}" for rd in rel.get("relatedDatasets", {}).get("data", []) if isinstance(rd, dict)]),
            "grantNumber": attr.get("grantNumber", ""),
            "name": attr.get("name", ""),
            "title": attr.get("subjectTitle", ""),
            
        }

    row_idx = 3
    for subGroup in subGroup_included:
        if subGroup.get("type") != "group":
            continue
        subGroup_attr = subGroup.get("attributes", {})
        subGroup_name = subGroup_attr.get("name", "")
        subGroup_subjects = subGroup_attr.get("subjects", {})
        for subject in subGroup_subjects:
            grantNumber = subject.get("grantNumber", "") if isinstance(subject, dict) else ""
            title = subject.get("title", "") if isinstance(subject, dict) else ""
            for dataset in dataset_data:
                ds_info = get_dataset_related_info(dataset)
                if ds_info["grantNumber"] != grantNumber:
                    continue
                manager_name = user_id_to_name.get(ds_info["manager_id"], "未設定" if ds_info["manager_id"] in [None, ""] else "")
                applicant_name = user_id_to_name.get(ds_info["applicant_id"], "")
                owner_names = [user_id_to_name.get(owner.get("id", ""), "") for owner in ds_info["owners"] if owner.get("id", "")]
                owner_names_str = "\n".join([n for n in owner_names if n])
                instrument_name = instrument_id_to_name.get(ds_info["instrument_id"], "")
                instrument_local_id = instrument_id_to_localid.get(ds_info["instrument_id"], "")
                dataset_url = f"https://rde.nims.go.jp/datasets/rde/{ds_info['id']}"

                dataEntry_path = os.path.join("output", "rde", "data", "dataEntry", f"{ds_info['id']}.json")
                dataEntry_json = load_json(dataEntry_path)
                if not dataEntry_json:
                    print(f"[ERROR] dataEntry JSONが存在しません: {dataEntry_path} for dataset_id={ds_info['id']}" )
                    continue
                dataEntry_data = dataEntry_json.get("data", [])
                dataEntry_included = dataEntry_json.get("included", [])
                total_file_size = sum(
                    inc.get("attributes", {}).get("fileSize", 0)
                    for inc in dataEntry_included if inc.get("type") == "file"
                )
                total_file_size_MB = total_file_size / (1024 * 1024) if total_file_size else 0

                def write_row(value_dict):
                    # 既存列にデータがなければ既存値を維持
                    # datasetId, dataEntryIdで手動列データを復元
                    dataset_id = value_dict.get("datasetId", "")
                    data_entry_id = value_dict.get("dataEntryId", "")
                    if data_entry_id and ("dataEntryId", data_entry_id) in manual_data_map:
                        manual_restore = manual_data_map[("dataEntryId", data_entry_id)]
                    elif dataset_id and ("datasetId", dataset_id) in manual_data_map:
                        manual_restore = manual_data_map[("datasetId", dataset_id)]
                    else:
                        manual_restore = {}
                    for id_ in header_ids:
                        col = id_to_col[id_]
                        if id_ in value_dict:
                            ws.cell(row=row_idx, column=col, value=value_dict[id_])
                        elif id_ in manual_restore:
                            ws.cell(row=row_idx, column=col, value=manual_restore[id_])
                        else:
                            # 既存値維持（openpyxlは新規行はNoneなので何もしない）
                            pass
                    # value_dictにのみ存在する新規IDは末尾に追加
                    for id_ in value_dict:
                        if id_ not in header_ids:
                            header_ids.append(id_)
                            col = len(header_ids)
                            ws.cell(row=1, column=col, value=id_)
                            ws.cell(row=2, column=col, value=id_to_label.get(id_, id_))
                            ws.cell(row=row_idx, column=col, value=value_dict[id_])
                            id_to_col[id_] = col

                # 複数データエントリ対応
                if dataEntry_data:
                    for entry in dataEntry_data:
                        entry_attr = entry.get("attributes", {})
                        dataEntry_name = entry_attr.get("name", "")
                        dataEntry_id = entry.get("id", "")
                        number_of_files = entry_attr.get("numberOfFiles", "")
                        number_of_image_files = entry_attr.get("numberOfImageFiles", "")
                        date_of_dataEntry_creation = entry_attr.get("created", "")
                        value_dict = {
                            "subGroupName": subGroup_name,
                            "dataset_manager_name": manager_name,
                            "dataset_applicant_name": applicant_name,
                            "dataset_owner_names_str": owner_names_str,
                            "grantNumber": grantNumber,
                            "title": title,
                            "datasetName": ds_info["name"],
                            "instrument_name": instrument_name,
                            "instrument_local_id": instrument_local_id,
                            "template_id": ds_info["template_id"],
                            "datasetId": dataset_url,
                            "dataEntryName": dataEntry_name,
                            "dataEntryId": dataEntry_id,
                            "number_of_files": number_of_files,
                            "number_of_image_files": number_of_image_files,
                            "date_of_dataEntry_creation": to_ymd(date_of_dataEntry_creation),
                            "total_file_size_MB": total_file_size_MB,
                            "dataset_embargoDate": ds_info["embargoDate"],
                            "dataset_isAnonymized": ds_info["isAnonymized"],
                            "dataset_description": ds_info["description"],
                            "dataset_relatedLinks": ds_info["relatedLinks_str"],
                            "dataset_relatedDatasets": ds_info["relatedDatasets_urls_str"],
                        }
                        write_row(value_dict)
                        row_idx += 1
                else:
                    # データエントリがない場合も空で1行出す
                    value_dict = {
                        "subGroupName": subGroup_name,
                        "dataset_manager_name": manager_name,
                        "dataset_applicant_name": applicant_name,
                        "dataset_owner_names_str": owner_names_str,
                        "grantNumber": grantNumber,
                        "title": title,
                        "datasetName": ds_info["name"],
                        "instrument_name": instrument_name,
                        "instrument_local_id": instrument_local_id,
                        "template_id": ds_info["template_id"],
                        "datasetId": dataset_url,
                        "dataEntryName": "",
                        "dataEntryId": "",
                        "number_of_files": "",
                        "number_of_image_files": "",
                        "date_of_dataEntry_creation": "",
                        "total_file_size_MB": total_file_size_MB,
                        "dataset_embargoDate": ds_info["embargoDate"],
                        "dataset_isAnonymized": ds_info["isAnonymized"],
                        "dataset_description": ds_info["description"],
                        "dataset_relatedLinks": ds_info["relatedLinks_str"],
                        "dataset_relatedDatasets": ds_info["relatedDatasets_urls_str"],
                    }
                    write_row(value_dict)
                    row_idx += 1

def fetch_invoice_schema_from_api(bearer_token, template_id, output_dir, summary, log_path, summary_path):
    """
    指定template_idのinvoiceSchemasを取得し保存。成功・失敗をsummary/logに記録。
    既にsummary.success/ファイルがあればスキップ。
    """
    filepath = os.path.join(output_dir, "invoiceSchemas", f"{template_id}.json")
    # 既に成功記録があればスキップ
    if template_id in summary.get("success", []):
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "skipped_summary"
    # 401/403でスキップ記録があればスキップ
    if template_id in summary.get("skipped_401", []):
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "skipped_401"
    if template_id in summary.get("skipped_403", []):
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "skipped_403"
    # 既存ファイルがあればスキップ
    if os.path.exists(filepath):
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "skipped_file"
    url = f"https://rde-api.nims.go.jp/invoiceSchemas/{template_id}"
    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    try:
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)  # refactored to use api_request_helper
        if resp is None:
            # リクエスト失敗をエラーとして記録
            summary.setdefault("failed", []).append(template_id)
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [FAILED] template_id={template_id} error=Request failed\n")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            return "failed"
        if resp.status_code == 401:
            # 401は今後も再取得しない
            summary.setdefault("skipped_401", []).append(template_id)
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [SKIPPED_401] template_id={template_id} error=401 Unauthorized\n")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            return "skipped_401"
        if resp.status_code == 403:
            # 403も今後も再取得しない
            summary.setdefault("skipped_403", []).append(template_id)
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [SKIPPED_403] template_id={template_id} error=403 Forbidden\n")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            return "skipped_403"
        resp.raise_for_status()
        data = resp.json()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        summary.setdefault("success", []).append(template_id)
        if template_id in summary.get("failed", {}):
            summary["failed"].pop(template_id)
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [SUCCESS] template_id={template_id}\n")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "success"
    except Exception as e:
        summary["failed"][template_id] = str(e)
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [FAILED] template_id={template_id} error={e}\n")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "failed"


# ========================================
# UIController用ラッパー関数
# ========================================

