"""
データセット編集専用ウィジェット
"""
import os
import sys
import json
import datetime
import webbrowser
import shutil
import codecs
import logging
import re
from typing import Iterable, Callable, Optional

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QGridLayout, 
    QPushButton, QMessageBox, QScrollArea, QCheckBox, QRadioButton, 
    QButtonGroup, QDialog, QTextEdit, QComboBox, QCompleter, QDateEdit,
    QListWidget, QListWidgetItem, QProgressDialog, QApplication, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
)
from qt_compat.core import Qt, QDate, QTimer
from config.common import get_dynamic_file_path
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
from classes.dataset.util.show_event_refresh import RefreshOnShowWidget
from classes.dataset.ui.taxonomy_builder_dialog import TaxonomyBuilderDialog
from classes.dataset.ui.ai_suggestion_dialog import AISuggestionDialog
from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload
from classes.managers.log_manager import get_logger

# ロガー設定
logger = get_logger(__name__)


def _format_user_label_user_org(user_data: dict) -> str:
    """Display user as `userName (organizationName)`.

    Falls back to kanji name / latin name / email when userName is missing.
    """
    if not isinstance(user_data, dict):
        return ""

    user_name = (user_data.get("userName") or "").strip()
    org = (user_data.get("organizationName") or "").strip()
    email = (user_data.get("emailAddress") or "").strip()

    family_kanji = (user_data.get("familyNameKanji") or "").strip()
    given_kanji = (user_data.get("givenNameKanji") or "").strip()
    kanji_name = " ".join([family_kanji, given_kanji]).strip()

    family = (user_data.get("familyName") or "").strip()
    given = (user_data.get("givenName") or "").strip()
    latin_name = " ".join([family, given]).strip()

    base_name = user_name or kanji_name or latin_name or email or "(氏名未設定)"
    if org:
        return f"{base_name} ({org})"
    return base_name


def _resolve_user_label_with_fallback(
    user_id: str | None,
    member_info: dict | None,
    dataset_user_info: dict | None = None,
    fallback_text: str | None = None,
) -> tuple[str, str]:
    """Resolve a user display label and its source.

    Returns (label, source) where source is one of:
    - "member": resolved from current group member info
    - "dataset_json": resolved from dataset JSON `included` user attributes
    - "fallback_text": resolved from provided fallback text
    - "id_only": could not resolve attributes; fall back to user_id or placeholder
    """

    if not user_id:
        return "", "missing"

    member_info = member_info or {}
    dataset_user_info = dataset_user_info or {}

    user_data = None
    source = "id_only"

    if user_id in member_info:
        user_data = member_info[user_id]
        source = "member"
    elif user_id in dataset_user_info:
        user_data = dataset_user_info[user_id]
        source = "dataset_json"
    elif fallback_text:
        # fallback_text は JSON 内の素の表示名をそのまま使う
        return fallback_text, "fallback_text"

    if not user_data:
        user_data = {"id": user_id}

    label = _format_user_label_user_org(user_data)
    if not label or label == "(氏名未設定)":
        label = fallback_text or user_id

    return label, source


def _should_block_update_for_users(
    applicant_id: str | None,
    applicant_source: str,
    manager_id: str | None,
    manager_source: str,
) -> bool:
    """Determine if update should be blocked when user names are unresolved.

    - Block when applicant_id exists but not resolved from member info.
    - Block when manager_id exists but not resolved from member info.
    - Missing IDs do not block.
    """

    if applicant_id and applicant_source != "member":
        return True
    if manager_id and manager_source != "member":
        return True
    return False


def _fetch_dataset_detail_from_api(dataset_id: str, bearer_token: str | None = None) -> dict | None:
    """Fetch dataset detail from RDE API and cache it as JSON file.

    Expected path: output/rde/data/datasets/{dataset_id}.json

    Args:
        dataset_id: Target dataset ID
        bearer_token: Bearer token for authentication (optional; will auto-detect if not provided)

    Returns:
        dict: Full dataset detail from API, or None on error
    """
    if not dataset_id:
        return None

    try:
        # Bearer Token取得（提供されていない場合）
        if not bearer_token:
            try:
                from core.bearer_token_manager import BearerTokenManager
                bearer_token = BearerTokenManager.get_valid_token()
            except Exception as e:
                logger.debug("Bearer Token自動取得失敗: %s", e)
                bearer_token = None

        if not bearer_token:
            logger.warning("dataset_edit: API再取得用のBearer Tokenが取得できません")
            return None

        # API URLを構築（include パラメータで必要な関連情報を含める）
        from config.site_rde import URLS
        api_url = URLS["api"]["dataset_detail"].format(id=dataset_id)

        # ヘッダーを設定
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Authorization": f"Bearer {bearer_token}",
            "Connection": "keep-alive",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        # APIリクエストを実行
        from classes.utils.api_request_helper import api_request
        response = api_request("GET", api_url, headers=headers, timeout=15)

        if response is None:
            logger.warning("dataset_edit: API再取得失敗（リクエストエラー） dataset_id=%s", dataset_id)
            return None

        if response.status_code != 200:
            logger.warning(
                "dataset_edit: API再取得失敗（ステータス %s） dataset_id=%s",
                response.status_code,
                dataset_id,
            )
            return None

        # レスポンスをJSON形式でパース
        try:
            payload = response.json()
        except Exception as e:
            logger.warning("dataset_edit: API再取得レスポンスのJSON解析失敗: %s", e)
            return None

        # JSONをファイルに保存
        try:
            datasets_dir = get_dynamic_file_path("output/rde/data/datasets")
            if datasets_dir and not os.path.exists(datasets_dir):
                os.makedirs(datasets_dir, exist_ok=True)

            dataset_json_path = os.path.join(datasets_dir, f"{dataset_id}.json")
            with open(dataset_json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            logger.info("dataset_edit: API再取得成功し、キャッシュに保存 dataset_id=%s path=%s", dataset_id, dataset_json_path)
        except Exception as e:
            logger.warning("dataset_edit: キャッシュファイル保存失敗: %s", e)
            # ファイル保存に失敗してもJSONデータは返却
            pass

        # レスポンスのdataセクションを返却
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and data.get("id"):
            # includedセクションも付与
            included = payload.get("included") if isinstance(payload, dict) else None
            if included:
                data["included"] = included
            return data

        logger.warning("dataset_edit: API再取得が空またはidがありません dataset_id=%s", dataset_id)
        return None

    except Exception as e:
        logger.error("dataset_edit: API再取得エラー dataset_id=%s: %s", dataset_id, e, exc_info=True)
        return None


def _load_dataset_detail_from_output(dataset_id: str) -> dict | None:
    """Load full dataset detail from output cache.

    Expected path: output/rde/data/datasets/{dataset_id}.json
    Returns the inner `data` dict when available.
    Includes any top-level `included` list by attaching it to the returned dict.
    """
    if not dataset_id:
        return None
    try:
        detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dataset_id}.json")
        if not detail_path or not os.path.exists(detail_path):
            return None
        with open(detail_path, encoding="utf-8") as f:
            payload = json.load(f)
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and data.get("id"):
            included = payload.get("included") if isinstance(payload, dict) else None
            if included:
                data["included"] = included
            return data
    except Exception:
        logger.debug("dataset_edit: dataset detail load failed id=%s", dataset_id, exc_info=True)
    return None


def _resolve_dataset_for_edit(dataset_dict: dict | None) -> dict | None:
    """Prefer full dataset detail JSON over digest entry when available."""
    if not isinstance(dataset_dict, dict):
        return None
    dataset_id = str(dataset_dict.get("id") or "")
    if not dataset_id:
        return dataset_dict
    detailed = _load_dataset_detail_from_output(dataset_id)
    return detailed or dataset_dict


def relax_dataset_edit_filters_for_launch(
    all_radio,
    other_radios: Optional[Iterable] = None,
    grant_filter_edit=None,
    apply_filter_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """Switch filter UI to the loosest mode prior to dataset handoff."""
    controls = []
    for control in filter(None, [all_radio, grant_filter_edit]):
        if hasattr(control, 'blockSignals'):
            controls.append((control, control.blockSignals(True)))
    for radio in other_radios or []:
        if hasattr(radio, 'blockSignals'):
            controls.append((radio, radio.blockSignals(True)))

    changed = False
    try:
        if all_radio is not None and hasattr(all_radio, 'isChecked') and not all_radio.isChecked():
            all_radio.setChecked(True)
            changed = True
        if grant_filter_edit is not None and hasattr(grant_filter_edit, 'text'):
            if grant_filter_edit.text().strip():
                if hasattr(grant_filter_edit, 'clear'):
                    grant_filter_edit.clear()
                    changed = True
    finally:
        for control, previous in controls:
            control.blockSignals(previous)

    if changed and callable(apply_filter_callback):
        try:
            apply_filter_callback()
        except Exception:  # pragma: no cover - defensive fallback
            logger.debug("dataset_edit: filter reload failed", exc_info=True)
    return changed
def _create_refresh_on_show_widget(parent=None):
    return RefreshOnShowWidget(parent)


def match_registration_candidates(dataset_name: str, data_name: str, owner_id: str, instrument_id: str | None,
                                  created_ts: str | None, registration_entries: list, threshold_seconds: int = 7200):
    """登録状況候補マッチング (24h 緩和ウィンドウ)
    条件:
      - datasetName 完全一致
      - dataName 完全一致
      - createdByUserId 一致
      - instrumentId 両方存在すれば一致
      - startTime と created の絶対秒差 <= threshold_seconds (両方パース可能な場合)
    戻り値: マッチした登録状況エントリー(dict)のリスト
    """
    import datetime as _dt
    results = []
    created_dt = None
    if created_ts:
        try:
            created_dt = _dt.datetime.fromisoformat(created_ts.replace('Z', '+00:00'))
        except Exception:
            created_dt = None
    for r in registration_entries:
        try:
            if r.get('datasetName') != dataset_name:
                continue
            if r.get('dataName') != data_name:
                continue
            if r.get('createdByUserId') != owner_id:
                continue
            if instrument_id and r.get('instrumentId') and r.get('instrumentId') != instrument_id:
                continue
            if created_dt:
                start_time = r.get('startTime')
                if start_time:
                    try:
                        start_dt = _dt.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        if abs((start_dt - created_dt).total_seconds()) > threshold_seconds:
                            continue
                    except Exception:
                        pass
            results.append(r)
        except Exception as ie:
            logger.debug("match_registration_candidates 内部エラー: %s", ie)
    return results

def format_start_time_jst(start_time: str) -> str:
    """UTC時刻文字列を日本時間（JST）に変換してYYYY-MM-DD HH:MM:SS形式で返す
    
    Args:
        start_time: ISO 8601形式のUTC時刻文字列（例: '2024-12-01T10:30:45Z'）
    
    Returns:
        日本時間の年月日時分秒文字列（例: '2024-12-01 19:30:45'）
        変換失敗時は元の文字列をそのまま返す
    """
    if not start_time:
        return ''
    try:
        import datetime as _dt
        # UTC時刻としてパース
        utc_dt = _dt.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        # JST（UTC+9時間）に変換
        jst_dt = utc_dt + _dt.timedelta(hours=9)
        # YYYY-MM-DD HH:MM:SS形式で返す
        return jst_dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.debug("start_time変換エラー: %s", e)
        return start_time

def build_expanded_rows_for_dataset_entries(items: list, dataset_name: str | None, registration_entries: list, collapse_tight: bool = True) -> list:
    """UIテーブル拡張行構築ロジックを分離 (テスト用)。
    items: dataEntry JSON内の data 配列
    戻り値: [{data_entry_id, data_name, reg_id, reg_status, linkable}, ...]
    """
    status_map = {r.get('id'): r.get('status') for r in registration_entries if isinstance(r, dict)}
    expanded_rows = []
    for item in items:
        eid = item.get('id') or ''
        attrs = item.get('attributes') or {}
        data_name = attrs.get('name', '')
        created_ts = attrs.get('created')
        rels = item.get('relationships') or {}
        owner_id = rels.get('owner', {}).get('data', {}).get('id', '')
        instrument_id = rels.get('instrument', {}).get('data', {}).get('id') if rels.get('instrument') else None
        matches = []
        if dataset_name:
            matches = match_registration_candidates(dataset_name, data_name, owner_id, instrument_id, created_ts, registration_entries, threshold_seconds=7200)
        # 5分(300秒)以内に収まる候補がある場合は最も時間差が小さいものを1件に絞り込む（UIテーブルでは無効化可能）
        if created_ts and collapse_tight:
            import datetime as _dt
            try:
                created_dt = _dt.datetime.fromisoformat(created_ts.replace('Z', '+00:00'))
            except Exception:
                created_dt = None
            if created_dt and matches:
                tight = []
                for m in matches:
                    st = m.get('startTime')
                    if not st:
                        continue
                    try:
                        start_dt = _dt.datetime.fromisoformat(st.replace('Z', '+00:00'))
                        diff = abs((start_dt - created_dt).total_seconds())
                        if diff <= 300:
                            tight.append((diff, m))
                    except Exception:
                        continue
                if tight:
                    tight.sort(key=lambda x: x[0])
                    matches = [tight[0][1]]
        if not matches:
            expanded_rows.append({
                'data_entry_id': eid,
                'data_name': data_name,
                'reg_id': '',
                'reg_status': '',
                'start_time': '',
                'linkable': False
            })
        else:
            for m in matches:
                rid = m.get('id', '')
                expanded_rows.append({
                    'data_entry_id': eid,
                    'data_name': data_name,
                    'reg_id': rid,
                    'reg_status': status_map.get(rid, ''),
                    'start_time': m.get('startTime', ''),
                    'linkable': bool(rid)
                })
    return expanded_rows


def _normalize_display_text(text: str) -> str:
    """表示テキストの微差（全角/半角・連続空白・改行等）を吸収する簡易正規化"""
    try:
        if not isinstance(text, str):
            return str(text)
        import unicodedata
        t = unicodedata.normalize('NFKC', text)
        # 連続空白を1つに、前後空白除去
        t = re.sub(r"\s+", " ", t).strip()
        return t
    except Exception:
        return text


def extract_dataset_id_from_text(text):
    """
    Completer選択テキストからデータセットIDを抽出
    
    Args:
        text: Completerから受け取ったテキスト
        
    Returns:
        str: 抽出されたID、失敗時はNone
    """
    # パターン: "ID: xxxx-xxxx-xxxx-xxxx"形式（大文字小文字不問）
    id_match = re.search(r'ID:\s*([a-f0-9\-]+)', text, re.IGNORECASE)
    if id_match:
        return id_match.group(1)
    return None


def resolve_dataset_selection(combo_box, text):
    """表示テキストから対象データセットのインデックスを解決するヘルパー。

    1) _display_to_dataset_map に直接マッピングがあれば高速解決
    2) 既存アイテムの itemText 完全一致で探索
    3) テキストから ID 抽出し、itemData(dict)の id と突き合わせ

    Args:
        combo_box (QComboBox): 対象コンボボックス
        text (str): Completer等から渡された表示テキスト

    Returns:
        int: 見つかったインデックス（失敗時は -1）
    """
    try:
        if not text:
            return -1

        total_items = combo_box.count()
        norm_text = _normalize_display_text(text)

        # 1) 直接マップ
        display_map = getattr(combo_box, '_display_to_dataset_map', None)
        if display_map and (text in display_map or norm_text in display_map):
            target_dataset = display_map.get(text) or display_map.get(norm_text)
            target_id = target_dataset.get("id") if isinstance(target_dataset, dict) else None
            if target_id:
                for i in range(total_items):
                    item_data = combo_box.itemData(i)
                    if isinstance(item_data, dict) and item_data.get("id") == target_id:
                        return i
            # ID無しの場合は参照一致で探索
            for i in range(total_items):
                if combo_box.itemData(i) is target_dataset:
                    return i

        # 2) 完全一致（正規化比較）
        for i in range(total_items):
            if _normalize_display_text(combo_box.itemText(i)) == norm_text:
                return i

        # 3) ID抽出して突合
        target_id = extract_dataset_id_from_text(text)
        if target_id:
            for i in range(total_items):
                item_data = combo_box.itemData(i)
                if isinstance(item_data, dict) and item_data.get("id") == target_id:
                    return i
        return -1
    except Exception as e:
        logger.debug("resolve_dataset_selection error: %s", e)
        return -1

def rebuild_display_map(combo_box):
    """コンボボックス内の現在の表示テキストとitemData(dict)からマップを再構築"""
    try:
        mapping = {}
        for i in range(combo_box.count()):
            data = combo_box.itemData(i)
            text = combo_box.itemText(i)
            if isinstance(data, dict) and text and text.startswith("-- データセットを選択") is False:
                mapping[_normalize_display_text(text)] = data
        if mapping:
            combo_box._display_to_dataset_map = mapping
            logger.debug("display_to_dataset_map 再構築: %s件", len(mapping))
    except Exception as e:
        logger.debug("rebuild_display_map 失敗: %s", e)


def repair_json_file(file_path):
    """破損したJSONファイルの修復を試行"""
    try:
        import codecs
        import re
        
        logger.info("JSONファイル修復を開始")
        logger.debug("対象ファイル: %s", file_path)
        
        # 複数のエンコーディングでの読み込みを試行
        encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'latin1', 'shift_jis']
        
        for encoding in encodings:
            try:
                logger.debug("エンコーディング '%s' で読み込み試行", encoding)
                with codecs.open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    content = f.read()
                
                logger.debug("読み込み完了。文字数: %s", len(content))
                
                # より包括的なクリーンアップ
                # 1. すべての制御文字を除去（\t, \n, \r, スペースは保持）
                logger.debug("制御文字クリーンアップを実行")
                original_len = len(content)
                # \x00-\x1F の制御文字のうち、\t(\x09), \n(\x0A), \r(\x0D), space(\x20)以外を除去
                content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', content)
                
                # 2. Unicode置換文字(\uFFFD)を除去
                content = content.replace('\uFFFD', '')
                
                # 3. その他の問題のある文字を除去
                # NULL文字やその他の問題を引き起こす可能性のある文字
                content = content.replace('\x00', '')
                
                logger.debug("クリーンアップ後の文字数: %s (削減: %s文字)", len(content), original_len - len(content))
                
                # JSONとしてパース可能かテスト
                try:
                    data = json.loads(content)
                    logger.info("エンコーディング '%s' で読み込み成功", encoding)
                    
                    # 修復したファイルをUTF-8で保存
                    backup_path = file_path + '.corrupted_backup'
                    shutil.copy2(file_path, backup_path)
                    logger.info("破損ファイルをバックアップ: %s", backup_path)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info("ファイルをUTF-8で再保存しました")
                    
                    return data
                    
                except json.JSONDecodeError as json_err:
                    # JSONパースエラーの詳細を表示
                    logger.debug("JSONパースエラー詳細: %s", json_err)
                    logger.debug("エラー位置: 行%s 列%s", getattr(json_err, 'lineno', '不明'), getattr(json_err, 'colno', '不明'))
                    
                    # エラー位置周辺のテキストを表示
                    if hasattr(json_err, 'pos') and json_err.pos:
                        start_pos = max(0, json_err.pos - 50)
                        end_pos = min(len(content), json_err.pos + 50)
                        context = content[start_pos:end_pos]
                        logger.debug("エラー位置周辺のテキスト: %r", context)
                    
                    continue
                
            except (UnicodeError, Exception) as e:
                logger.debug("エンコーディング '%s' 失敗: %s", encoding, e)
                continue
        
        logger.error("すべてのエンコーディング試行が失敗しました")
        
        # 最後の手段として、ファイルの修復を試みる
        logger.info("最後の手段として、部分的な修復を試行")
        try:
            return attempt_partial_recovery(file_path)
        except Exception as recovery_err:
            logger.error("部分回復も失敗: %s", recovery_err)
        
        return None
        
    except Exception as e:
        logger.error("ファイル修復中の予期しないエラー: %s", e)
        import traceback
        traceback.print_exc()
        return None


def attempt_partial_recovery(file_path):
    """部分的な修復を試行"""
    import re
    
    logger.debug("部分的修復を開始")
    
    # バイナリモードで読み込み、有効なJSON部分を抽出を試みる
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    # UTF-8で読み込み、エラー文字を置換
    content = raw_data.decode('utf-8', errors='replace')
    
    # JSON構造の開始と終了を見つける
    json_start = content.find('{"data"')
    if json_start == -1:
        json_start = content.find('{"')
    
    if json_start == -1:
        logger.error("JSON構造の開始が見つかりません")
        return None
    
    logger.debug("JSON開始位置: %s", json_start)
    
    # 後方から有効な終了位置を見つける
    json_end = content.rfind('}')
    if json_end == -1:
        logger.error("JSON構造の終了が見つかりません")
        return None
    
    logger.debug("JSON終了位置: %s", json_end)
    
    # 部分的なJSONを抽出
    partial_json = content[json_start:json_end + 1]
    
    # 基本的なクリーンアップ
    partial_json = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', partial_json)
    partial_json = partial_json.replace('\uFFFD', '')
    
    try:
        data = json.loads(partial_json)
        logger.info("部分的修復に成功")
        return data
    except json.JSONDecodeError as e:
        logger.error("部分的修復も失敗: %s", e)
        return None


def get_grant_numbers_from_dataset(dataset_data):
    """
    データセットから対応するサブグループの課題番号リストを取得
    
    Args:
        dataset_data (dict): データセット情報
        
    Returns:
        set: 課題番号のセット
    """
    if not dataset_data:
        return set()
    
    grant_numbers = set()
    try:
        # データセットのgrantNumberを取得
        dataset_grant_number = dataset_data.get("attributes", {}).get("grantNumber", "")
        if dataset_grant_number:
            grant_numbers.add(dataset_grant_number)
            logger.debug("データセットの課題番号: %s", dataset_grant_number)
            
            # このgrantNumberを持つサブグループを探し、そのサブグループの全課題番号を取得
            sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
            if os.path.exists(sub_group_path):
                with open(sub_group_path, encoding="utf-8") as f:
                    sub_group_data = json.load(f)
                
                # このgrantNumberを含むサブグループを検索
                for item in sub_group_data.get("included", []):
                    if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                        subjects = item.get("attributes", {}).get("subjects", [])
                        # このグループにデータセットのgrantNumberが含まれているかチェック
                        group_grant_numbers = set()
                        dataset_grant_found = False
                        
                        for subject in subjects:
                            subject_grant_number = subject.get("grantNumber", "")
                            if subject_grant_number:
                                group_grant_numbers.add(subject_grant_number)
                                if subject_grant_number == dataset_grant_number:
                                    dataset_grant_found = True
                        
                        # このサブグループがデータセットの課題番号を含む場合、このグループの全課題番号を返す
                        if dataset_grant_found:
                            grant_numbers = group_grant_numbers
                            group_name = item.get("attributes", {}).get("name", "不明")
                            logger.debug("データセットのサブグループ '%s' の全課題番号: %s", group_name, sorted(grant_numbers))
                            break
    
    except Exception as e:
        logger.error("データセットから課題番号取得に失敗: %s", e)
    
    return grant_numbers


def get_user_grant_numbers():
    """
    ログインユーザーが属するサブグループのgrantNumberリストを取得
    dataset_open_logic.pyと同様の処理
    """
    sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
    self_path = get_dynamic_file_path('output/rde/data/self.json')
    user_grant_numbers = set()
    
    logger.debug("サブグループファイルパス: %s", sub_group_path)
    logger.debug("セルフファイルパス: %s", self_path)
    logger.debug("サブグループファイル存在: %s", os.path.exists(sub_group_path))
    logger.debug("セルフファイル存在: %s", os.path.exists(self_path))
    
    try:
        # ログインユーザーID取得
        with open(self_path, encoding="utf-8") as f:
            self_data = json.load(f)
        user_id = self_data.get("data", {}).get("id", None)
        logger.debug("ユーザーID: %s", user_id)
        
        if not user_id:
            logger.error("self.jsonからユーザーIDが取得できませんでした。")
            return user_grant_numbers
        
        # ユーザーが属するサブグループを抽出
        with open(sub_group_path, encoding="utf-8") as f:
            sub_group_data = json.load(f)
        
        groups_count = 0
        for item in sub_group_data.get("included", []):
            if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                groups_count += 1
                roles = item.get("attributes", {}).get("roles", [])
                # ユーザーがこのグループのメンバーかチェック
                user_in_group = False
                for r in roles:
                    if r.get("userId") == user_id:
                        if r.get("role") in ["OWNER", "ASSISTANT"]:
                            user_in_group = True
                            break
                
                if user_in_group:
                    # このグループのgrantNumbersを取得
                    subjects = item.get("attributes", {}).get("subjects", [])
                    group_name = item.get("attributes", {}).get("name", "不明")
                    logger.debug("ユーザーが所属するグループ: '%s' (課題数: %s)", group_name, len(subjects))
                    
                    for subject in subjects:
                        grant_number = subject.get("grantNumber", "")
                        if grant_number:
                            user_grant_numbers.add(grant_number)
                            logger.debug("課題番号追加: %s", grant_number)
        
        logger.debug("検査したTEAMグループ数: %s", groups_count)
        logger.debug("最終的なユーザー課題番号: %s", sorted(user_grant_numbers))
    
    except Exception as e:
        logger.error("ユーザーgrantNumber取得に失敗: %s", e)
        import traceback
        traceback.print_exc()
    
    return user_grant_numbers


def create_dataset_edit_widget(parent, title, create_auto_resize_button):
    """データセット編集専用ウィジェット"""
    widget = _create_refresh_on_show_widget()
    layout = QVBoxLayout()
    
    # タイトル
    title_label = QLabel(f"{title}機能")
    title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; padding: 10px;")
    #layout.addWidget(title_label)
    
    # フィルタ設定エリア
    filter_widget = QWidget()
    filter_layout = QVBoxLayout()
    filter_layout.setContentsMargins(0, 0, 0, 0)
    
    # フィルタタイプ選択（ラジオボタン）
    filter_type_widget = QWidget()
    filter_type_layout = QHBoxLayout()
    filter_type_layout.setContentsMargins(0, 0, 0, 0)
    
    filter_type_label = QLabel("表示データセット:")
    filter_type_label.setMinimumWidth(120)
    filter_type_label.setStyleSheet("font-weight: bold;")
    
    filter_user_only_radio = QRadioButton("ユーザー所属のみ")
    filter_user_only_radio.setObjectName("dataset_filter_user_only_radio")
    filter_others_only_radio = QRadioButton("その他のみ")
    filter_others_only_radio.setObjectName("dataset_filter_others_radio")
    filter_all_radio = QRadioButton("すべて")
    filter_all_radio.setObjectName("dataset_filter_all_radio")
    filter_user_only_radio.setChecked(True)  # デフォルトは「ユーザー所属のみ」
    
    filter_type_layout.addWidget(filter_type_label)
    filter_type_layout.addWidget(filter_user_only_radio)
    filter_type_layout.addWidget(filter_others_only_radio)
    filter_type_layout.addWidget(filter_all_radio)
    enable_update_override_button = QPushButton("更新有効化")
    enable_update_override_button.setObjectName("dataset_update_override_button")
    enable_update_override_button.setEnabled(False)
    enable_update_override_button.setMaximumWidth(130)
    enable_update_override_button.setStyleSheet(f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
            font-weight: bold;
            border-radius: 4px;
            padding: 4px 8px;
            border: 1px solid {get_color(ThemeKey.BUTTON_DANGER_BORDER)};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """)
    enable_update_override_button.setToolTip("ユーザー所属のみ、課題番号フィルタなしの状態では常に更新できます")
    filter_type_layout.addWidget(enable_update_override_button)
    filter_type_layout.addStretch()  # 右側にスペースを追加
    
    filter_type_widget.setLayout(filter_type_layout)
    filter_layout.addWidget(filter_type_widget)
    
    # 課題番号部分一致検索
    grant_number_filter_widget = QWidget()
    grant_number_filter_layout = QHBoxLayout()
    grant_number_filter_layout.setContentsMargins(0, 0, 0, 0)
    
    grant_number_filter_label = QLabel("課題番号絞り込み:")
    grant_number_filter_label.setMinimumWidth(120)
    grant_number_filter_label.setStyleSheet("font-weight: bold;")
    
    grant_number_filter_edit = QLineEdit()
    grant_number_filter_edit.setPlaceholderText("課題番号の一部を入力（部分一致検索・リアルタイム絞り込み）")
    grant_number_filter_edit.setMinimumWidth(400)
    
    # エントリーリスト更新ボタンを追加
    cache_refresh_button = QPushButton("エントリーリスト更新")
    cache_refresh_button.setObjectName("dataset_entry_list_refresh_button")
    cache_refresh_button.setMaximumWidth(150)
    # 警告系ボタンスタイルへ統一（ThemeKey）
    cache_refresh_button.setStyleSheet(f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
            font-weight: bold;
            border-radius: 4px;
            padding: 5px;
            border: 1px solid {get_color(ThemeKey.BUTTON_WARNING_BORDER)};
        }}
        QPushButton:hover {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """)
    cache_refresh_button.setToolTip("選択中データセットのエントリー一覧をAPIから再取得して更新します")

    # データセット再取得ボタン（APIから詳細再取得し、フォーム表示を更新）
    dataset_refetch_button = QPushButton("再取得")
    dataset_refetch_button.setObjectName("dataset_refetch_button")
    dataset_refetch_button.setMaximumWidth(80)
    dataset_refetch_button.setStyleSheet(f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
            font-weight: bold;
            border-radius: 4px;
            padding: 5px;
            border: 1px solid {get_color(ThemeKey.BUTTON_WARNING_BORDER)};
        }}
        QPushButton:hover {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """)
    dataset_refetch_button.setToolTip("選択中データセットの詳細をAPIから再取得し、表示を更新します")
    
    grant_number_filter_layout.addWidget(grant_number_filter_label)
    grant_number_filter_layout.addWidget(grant_number_filter_edit)
    grant_number_filter_layout.addWidget(cache_refresh_button)
    grant_number_filter_layout.addWidget(dataset_refetch_button)
    grant_number_filter_layout.addStretch()
    
    grant_number_filter_widget.setLayout(grant_number_filter_layout)
    filter_layout.addWidget(grant_number_filter_widget)
    
    filter_widget.setLayout(filter_layout)
    layout.addWidget(filter_widget)
    
    # 既存データセットドロップダウン（ラベルとコンボボックスを一行で表示）
    dataset_selection_widget = QWidget()
    dataset_selection_layout = QHBoxLayout()
    dataset_selection_layout.setContentsMargins(0, 0, 0, 0)
    
    existing_dataset_label = QLabel("表示するデータセット:")
    existing_dataset_label.setMinimumWidth(150)
    existing_dataset_combo = QComboBox()
    existing_dataset_combo.setObjectName("datasetEditCombo")
    existing_dataset_combo.setMinimumWidth(650)  # 幅を広げてID表示対応
    existing_dataset_combo.setEditable(True)  # 検索補完のために編集可能にする
    existing_dataset_combo.setInsertPolicy(QComboBox.NoInsert)  # 新しいアイテムの挿入を禁止
    existing_dataset_combo.setMaxVisibleItems(12)  # ドロップダウンの表示行数を12行に
    existing_dataset_combo.view().setMinimumHeight(240)  # 12行分程度（1行約20px想定）
    
    # パフォーマンス最適化設定
    existing_dataset_combo.view().setUniformItemSizes(True)  # アイテムサイズを統一（高速化）
    existing_dataset_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)  # サイズ調整ポリシー
    existing_dataset_combo.setToolTip("クリックでデータセット一覧を展開します\n大量データの場合はプログレス表示されます\nカーソルキーで選択可能")
    
    # キー入力対応: lineEdit の keyPressEvent をラップして、カーソルキーでポップアップ操作を実現
    def setup_combo_key_handling():
        """コンボボックスのキー入力ハンドリングをセットアップ"""
        if not existing_dataset_combo.lineEdit():
            logger.debug("dataset_edit: lineEdit が見つかりません")
            return
        
        original_key_press = existing_dataset_combo.lineEdit().keyPressEvent
        
        def combo_key_press_event(event):
            """カーソルキー・ホイール対応のキープレスハンドラ"""
            key = event.key()
            
            # ポップアップが未表示の場合、上/下キーでポップアップを表示
            if not existing_dataset_combo.view().isVisible():
                if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                    existing_dataset_combo.showPopup()
                    return  # イベントを消費
            
            # ポップアップが表示中の場合、キーをポップアップに委譲
            if existing_dataset_combo.view().isVisible():
                if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                    # ポップアップのListViewに対してキーイベントを送信
                    from qt_compat.core import QKeyEvent
                    popup_event = QKeyEvent(event.type(), key, event.modifiers(), event.text())
                    existing_dataset_combo.view().keyPressEvent(popup_event)
                    return  # イベントを消費
            
            # その他のキーは通常処理
            original_key_press(event)
        
        existing_dataset_combo.lineEdit().keyPressEvent = combo_key_press_event
    
    # lineEdit が作成された後にハンドラを設定（遅延実行）
    def setup_combo_key_handling_deferred():
        QTimer.singleShot(0, setup_combo_key_handling)
    
    existing_dataset_combo.focusInEvent_original = existing_dataset_combo.focusInEvent
    def combo_focus_in(event):
        """フォーカスイン時にlineEditハンドラをセットアップ"""
        existing_dataset_combo.focusInEvent_original(event)
        setup_combo_key_handling_deferred()
    
    existing_dataset_combo.focusInEvent = combo_focus_in
    
    dataset_selection_layout.addWidget(existing_dataset_label)
    dataset_selection_layout.addWidget(existing_dataset_combo)
    dataset_selection_widget.setLayout(dataset_selection_layout)
    layout.addWidget(dataset_selection_widget)

    launch_controls_widget = QWidget()
    launch_controls_layout = QHBoxLayout()
    launch_controls_layout.setContentsMargins(0, 0, 0, 0)
    launch_label = QLabel("他機能連携:")
    launch_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;")
    launch_controls_layout.addWidget(launch_label)

    from classes.utils.launch_ui_styles import get_launch_button_style

    launch_button_style = get_launch_button_style()

    launch_targets = [
        ("data_fetch2", "データ取得2"),
        ("dataset_dataentry", "データエントリー"),
        ("data_register", "データ登録"),
        ("data_register_batch", "データ登録(一括)"),
    ]

    launch_buttons = []

    def _has_dataset_selection() -> bool:
        idx = existing_dataset_combo.currentIndex()
        if idx <= 0:
            return False
        dataset_data = existing_dataset_combo.itemData(idx)
        return isinstance(dataset_data, dict) and bool(dataset_data.get("id"))

    def _update_launch_button_state() -> None:
        enabled = _has_dataset_selection()
        for button in launch_buttons:
            button.setEnabled(enabled)

    def _load_dataset_record(dataset_id: str):
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        if not dataset_id or not os.path.exists(dataset_path):
            return None
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            items = data.get('data') if isinstance(data, dict) else data
            for dataset in items or []:
                if isinstance(dataset, dict) and dataset.get('id') == dataset_id:
                    return dataset
        except Exception as exc:
            logger.debug("dataset_edit: dataset.json読み込み失敗 %s", exc)
        return None

    def _get_selected_dataset_payload():
        idx = existing_dataset_combo.currentIndex()
        if idx <= 0:
            QMessageBox.warning(widget, "データセット未選択", "連携するデータセットを選択してください。")
            return None
        dataset_data = existing_dataset_combo.itemData(idx)
        if not isinstance(dataset_data, dict):
            QMessageBox.warning(widget, "データセット未取得", "選択したデータセット情報を取得できません。")
            return None
        dataset_id = dataset_data.get("id")
        if not dataset_id:
            QMessageBox.warning(widget, "データセット未取得", "選択したデータセットIDを取得できません。")
            return None
        display_text = existing_dataset_combo.itemText(idx) or dataset_id
        return {
            "dataset_id": dataset_id,
            "display_text": display_text,
            "raw_dataset": dataset_data,
        }

    def _handle_dataset_launch(target_key: str):
        payload = _get_selected_dataset_payload()
        if not payload:
            return
        DatasetLaunchManager.instance().request_launch(
            target_key=target_key,
            dataset_id=payload["dataset_id"],
            display_text=payload["display_text"],
            raw_dataset=payload["raw_dataset"],
            source_name="dataset_edit",
        )

    for target_key, caption in launch_targets:
        btn = QPushButton(caption)
        btn.setStyleSheet(launch_button_style)
        btn.clicked.connect(lambda _=None, key=target_key: _handle_dataset_launch(key))
        launch_controls_layout.addWidget(btn)
        launch_buttons.append(btn)

    # テーマ切替時に「他機能連携」の個別styleSheetを再適用（更新漏れ対策）
    try:
        from classes.utils.launch_ui_styles import apply_launch_controls_theme, bind_launch_controls_to_theme

        apply_launch_controls_theme(launch_label, launch_buttons)
        bind_launch_controls_to_theme(launch_label, launch_buttons)
    except Exception:
        pass

    launch_controls_layout.addStretch()
    launch_controls_widget.setLayout(launch_controls_layout)
    layout.addWidget(launch_controls_widget)

    widget._dataset_launch_buttons = launch_buttons  # type: ignore[attr-defined]
    existing_dataset_combo.currentIndexChanged.connect(lambda *_: _update_launch_button_state())
    _update_launch_button_state()

    def _find_dataset_index(dataset_id: str) -> int:
        if not dataset_id:
            return -1
        for idx in range(existing_dataset_combo.count()):
            data = existing_dataset_combo.itemData(idx)
            if isinstance(data, dict) and data.get("id") == dataset_id:
                return idx
        return -1

    def _get_current_dataset_id() -> str | None:
        current_data = existing_dataset_combo.currentData()
        if isinstance(current_data, dict):
            return current_data.get("id")
        return None

    def _restore_dataset_selection(dataset_id: str | None) -> None:
        attempts = {"count": 0, "expanded": False}

        def _apply_restore():
            if not dataset_id:
                logger.debug("dataset_edit: restore skipped (no dataset)")
                existing_dataset_combo.setCurrentIndex(-1)
                return

            # ComboBoxは遅延展開のため、リフレッシュ直後はアイテムが未展開のことがあります。
            # その場合はキャッシュから一度だけ展開してから復元を試みます。
            if not attempts["expanded"]:
                try:
                    has_any_dataset_item = False
                    for idx in range(existing_dataset_combo.count()):
                        data = existing_dataset_combo.itemData(idx)
                        if isinstance(data, dict) and data.get("id"):
                            has_any_dataset_item = True
                            break

                    if not has_any_dataset_item:
                        cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', None)
                        cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', None)
                        if (
                            isinstance(cached_datasets, list)
                            and isinstance(cached_display_names, list)
                            and cached_datasets
                        ):
                            attempts["expanded"] = True
                            populate_combo_box_with_progress(
                                existing_dataset_combo,
                                cached_datasets,
                                cached_display_names,
                            )
                except Exception:
                    logger.debug("dataset_edit: restore combo expansion from cache failed", exc_info=True)

            target_index = _find_dataset_index(dataset_id)
            if target_index < 0:
                if attempts["count"] < 5:
                    attempts["count"] += 1
                    QTimer.singleShot(50, _apply_restore)
                    return
                logger.debug("dataset_edit: restore target not found id=%s", dataset_id)
                available_ids = []
                for idx in range(existing_dataset_combo.count()):
                    data = existing_dataset_combo.itemData(idx)
                    if isinstance(data, dict):
                        available_ids.append(data.get("id"))
                logger.debug("dataset_edit: available ids=%s", available_ids)
                existing_dataset_combo.setCurrentIndex(-1)
                return
            previous_index = existing_dataset_combo.currentIndex()
            logger.debug(
                "dataset_edit: restoring dataset id=%s target_index=%s previous=%s",
                dataset_id,
                target_index,
                previous_index,
            )
            existing_dataset_combo.setCurrentIndex(target_index)
            if previous_index == target_index:
                try:
                    on_dataset_selection_changed()
                except Exception:
                    logger.debug("dataset_edit: manual refresh after restore failed", exc_info=True)
            _update_launch_button_state()

        QTimer.singleShot(0, _apply_restore)

    def _format_dataset_display(dataset_dict: dict, fallback: str | None = None) -> str:
        attrs = dataset_dict.get("attributes", {}) if isinstance(dataset_dict, dict) else {}
        grant = attrs.get("grantNumber") or ""
        name = attrs.get("name") or ""
        result_parts = [part for part in (grant, name) if part]
        return " - ".join(result_parts) if result_parts else (fallback or dataset_dict.get("id", ""))

    def _insert_dataset_into_combo(dataset_dict: dict, display_text: str | None = None) -> int:
        if not isinstance(dataset_dict, dict):
            return -1
        dataset_id = dataset_dict.get("id")
        if not dataset_id:
            return -1
        current_index = _find_dataset_index(dataset_id)
        if current_index >= 0:
            return current_index
        text = display_text or _format_dataset_display(dataset_dict, dataset_id)
        existing_dataset_combo.blockSignals(True)
        existing_dataset_combo.addItem(text, dataset_dict)
        existing_dataset_combo.blockSignals(False)

        cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', None)
        if isinstance(cached_datasets, list):
            cached_datasets.append(dataset_dict)
        cached_display = getattr(existing_dataset_combo, '_display_names_cache', None)
        if isinstance(cached_display, list):
            cached_display.append(text)
        display_map = getattr(existing_dataset_combo, '_display_to_dataset_map', None)
        if isinstance(display_map, dict):
            try:
                display_map[_normalize_display_text(text)] = dataset_dict
            except Exception:
                pass
        return existing_dataset_combo.count() - 1
    
    # データセットキャッシュシステム
    dataset_cache = {
        "raw_data": None,  # 元のJSONデータ
        "last_modified": None,  # ファイルの最終更新時刻
        "user_grant_numbers": None,  # ユーザーのgrantNumber一覧
        "filtered_datasets": {},  # フィルタごとのキャッシュ: {(filter_type, grant_filter): datasets}
        "display_data": {}  # 表示用データのキャッシュ: {(filter_type, grant_filter): display_names}
    }
    
    def get_cache_key(filter_type, grant_number_filter):
        """キャッシュキーを生成"""
        return (filter_type, grant_number_filter.lower().strip())
    
    def is_cache_valid():
        """キャッシュが有効かどうかを判定"""
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        if not os.path.exists(dataset_path):
            return False
        
        current_modified = os.path.getmtime(dataset_path)
        return (dataset_cache["last_modified"] is not None and 
                dataset_cache["last_modified"] == current_modified and
                dataset_cache["raw_data"] is not None)
    
    def clear_cache():
        """キャッシュをクリア"""
        dataset_cache["raw_data"] = None
        dataset_cache["last_modified"] = None
        dataset_cache["user_grant_numbers"] = None
        dataset_cache["filtered_datasets"].clear()
        dataset_cache["display_data"].clear()
        logger.info("データセットキャッシュをクリアしました")
    
    is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))

    class _NullProgress:
        def show(self):
            return None

        def setValue(self, _value):
            return None

        def setLabelText(self, _text):
            return None

        def close(self):
            return None

    def _process_events():
        if not is_pytest:
            QApplication.processEvents()

    # プログレスダイアログを作成
    def create_progress_dialog(title, text, maximum=0):
        """プログレスダイアログを作成"""
        # Windows + pytest-qt 環境でネイティブUI/イベント処理が不安定になり得るため、テスト時はno-op化
        if is_pytest:
            return _NullProgress()

        progress = QProgressDialog(text, "キャンセル", 0, maximum, widget)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(500)  # 500ms後に表示
        progress.setCancelButton(None)  # キャンセルボタンを無効化
        progress.setAutoClose(True)
        progress.setAutoReset(True)
        return progress
    
    def process_datasets_with_progress(datasets, user_grant_numbers, filter_type, grant_number_filter):
        """プログレス表示付きでデータセットを処理"""
        total_datasets = len(datasets)
        if total_datasets == 0:
            return [], []
        
        # プログレスダイアログを作成
        progress = create_progress_dialog(
            "データ処理中", 
            f"データセットを処理しています... (0/{total_datasets})",
            total_datasets
        )
        
        filtered_datasets = []
        other_datasets = []
        user_datasets = []
        grant_number_matches = {}
        
        try:
            for i, dataset in enumerate(datasets):
                # プログレス更新
                if i % 50 == 0 or i == total_datasets - 1:  # 50件ごと、または最後の処理時に更新
                    progress.setValue(i)
                    progress.setLabelText(f"データセットを処理しています... ({i+1}/{total_datasets})")
                    _process_events()  # UIの更新を強制
                
                try:
                    # データ構造の検証
                    if not isinstance(dataset, dict):
                        logger.warning("データセット%s: 無効なデータ構造（dict以外）- スキップ", i+1)
                        continue
                    
                    attributes = dataset.get("attributes")
                    if not isinstance(attributes, dict):
                        logger.warning("データセット%s: attributes が dict でない - スキップ", i+1)
                        continue
                    
                    dataset_grant_number = attributes.get("grantNumber", "")
                    dataset_name = attributes.get("name", "名前なし")
                    
                    # デバッグ用：最初の10件のデータセットの課題番号を表示
                    if i < 10:
                        logger.debug("データセット%s: '%s' (課題番号: '%s')", i+1, dataset_name, dataset_grant_number)
                    
                    # 課題番号部分一致フィルタを適用
                    if grant_number_filter and grant_number_filter.lower() not in dataset_grant_number.lower():
                        continue
                    
                    # ユーザー所属かどうかで分類
                    if dataset_grant_number in user_grant_numbers:
                        user_datasets.append(dataset)
                        if dataset_grant_number not in grant_number_matches:
                            grant_number_matches[dataset_grant_number] = 0
                        grant_number_matches[dataset_grant_number] += 1
                    else:
                        other_datasets.append(dataset)
                        
                except Exception as dataset_error:
                    logger.error("データセット%s の処理中にエラー: %s", i+1, dataset_error)
                    continue
            
            # 最終プログレス更新
            progress.setValue(total_datasets)
            progress.setLabelText("処理完了")
            _process_events()
            
        finally:
            progress.close()
        
        # フィルタタイプに基づいて表示対象を決定
        if filter_type == "user_only":
            filtered_datasets = user_datasets
            logger.debug("フィルタ適用: ユーザー所属のみ (%s件)", len(filtered_datasets))
        elif filter_type == "others_only":
            filtered_datasets = other_datasets
            logger.debug("フィルタ適用: その他のみ (%s件)", len(filtered_datasets))
        elif filter_type == "all":
            filtered_datasets = user_datasets + other_datasets
            logger.debug("フィルタ適用: すべて (ユーザー所属: %s件, その他: %s件, 合計: %s件)", len(user_datasets), len(other_datasets), len(filtered_datasets))
        
        return filtered_datasets, grant_number_matches
    
    def create_display_names_with_progress(datasets, user_grant_numbers):
        """プログレス表示付きで表示名リストを作成"""
        total_datasets = len(datasets)
        if total_datasets == 0:
            return []
        
        # 表示名作成のプログレスダイアログ
        progress = create_progress_dialog(
            "表示データ作成中",
            f"表示用データを作成しています... (0/{total_datasets})",
            total_datasets
        )
        
        display_names = []
        
        try:
            for i, dataset in enumerate(datasets):
                # プログレス更新（表示名作成は高速なので100件ごと）
                if i % 100 == 0 or i == total_datasets - 1:
                    progress.setValue(i)
                    progress.setLabelText(f"表示用データを作成しています... ({i+1}/{total_datasets})")
                    _process_events()
                
                try:
                    # データ構造の検証
                    if not isinstance(dataset, dict):
                        logger.warning("表示名作成%s: 無効なデータ構造 - スキップ", i+1)
                        display_names.append(f"[エラー: 無効なデータ] (インデックス: {i+1})")
                        continue
                    
                    attrs = dataset.get("attributes", {})
                    if not isinstance(attrs, dict):
                        logger.warning("表示名作成%s: attributes が dict でない - スキップ", i+1)
                        display_names.append(f"[エラー: 属性なし] (インデックス: {i+1})")
                        continue
                    
                    dataset_id = dataset.get("id", "")
                    name = attrs.get("name", "名前なし")
                    grant_number = attrs.get("grantNumber", "")
                    dataset_type = attrs.get("datasetType", "")
                    
                    # ユーザー所属かどうかで表示を区別
                    if grant_number in user_grant_numbers:
                        display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
                    else:
                        display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                    
                    if dataset_type:
                        display_text += f" [{dataset_type}]"
                    display_names.append(display_text)
                    
                except Exception as display_error:
                    logger.error("表示名作成%s でエラー: %s", i+1, display_error)
                    display_names.append(f"[エラー: {str(display_error)}] (インデックス: {i+1})")
                    continue
            
            # 最終プログレス更新
            progress.setValue(total_datasets)
            progress.setLabelText("表示データ作成完了")
            _process_events()
            
        finally:
            progress.close()
        
        return display_names

    def populate_combo_box_with_progress(combo_box, datasets, display_names):
        """プログレス表示付きでコンボボックスにアイテムを追加"""
        total_items = len(datasets)
        if total_items == 0:
            return
        
        # アイテム数が多い場合のみプログレス表示
        if total_items > 100:
            progress = create_progress_dialog(
                "リスト展開中",
                f"データセット一覧を展開しています... (0/{total_items})",
                total_items
            )
        else:
            progress = None
        
        try:
            # 効率化のため、blockSignalsを使用してシグナルを一時的に無効化
            combo_box.blockSignals(True)
            
            # 最初にヘッダーアイテムを追加
            combo_box.addItem("-- データセットを選択してください --", None)
            
            # バッチでアイテムを追加（応答性を保つため）
            batch_size = 50  # 50件ずつ処理
            for i in range(0, total_items, batch_size):
                batch_end = min(i + batch_size, total_items)
                
                # バッチ処理
                for j in range(i, batch_end):
                    display_text = display_names[j] if j < len(display_names) else f"データセット{j+1}"
                    dataset = datasets[j]
                    combo_box.addItem(display_text, dataset)
                
                # プログレス更新（大量データの場合のみ）
                if progress:
                    progress.setValue(batch_end)
                    progress.setLabelText(f"データセット一覧を展開しています... ({batch_end}/{total_items})")
                    _process_events()
                
                # 応答性を保つため、バッチごとに少し待機
                if total_items > 500:  # 500件以上の場合のみ
                    QTimer.singleShot(1, lambda: None)  # 1msの非ブロッキング待機
                    _process_events()
            # 追加完了後にマップ再構築
            rebuild_display_map(combo_box)
            # 初期選択を未選択状態に（ラインエディットのプレースホルダのみ表示）
            combo_box.setCurrentIndex(-1)
            
        finally:
            combo_box.blockSignals(False)
            if progress:
                progress.close()

    update_override_state = {"enabled": False}

    UPDATE_BUTTON_ENABLED_STYLE = f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
            font-weight: bold;
            border-radius: 6px;
            border: 1px solid {get_color(ThemeKey.BUTTON_WARNING_BORDER)};
        }}
        QPushButton:hover {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
        }}
        QPushButton:pressed {{
            background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_PRESSED)};
        }}
    """

    UPDATE_BUTTON_DISABLED_STYLE = f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            font-weight: bold;
            border-radius: 6px;
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """

    def get_current_filter_type():
        if filter_user_only_radio.isChecked():
            return "user_only"
        if filter_others_only_radio.isChecked():
            return "others_only"
        if filter_all_radio.isChecked():
            return "all"
        return "user_only"

    def _is_default_filter_state(filter_type, grant_number_filter):
        normalized_filter = grant_number_filter or ""
        return filter_type == "user_only" and not normalized_filter

    def apply_update_button_state(filter_type, grant_number_filter):
        is_default_filter = _is_default_filter_state(filter_type, grant_number_filter)

        if is_default_filter and update_override_state["enabled"]:
            logger.info("フィルタがデフォルトに戻ったため手動有効化を解除します")
            update_override_state["enabled"] = False

        effective_enabled = is_default_filter or update_override_state["enabled"]

        if update_permission_blocked:
            effective_enabled = False
            update_override_state["enabled"] = False
            update_button.setEnabled(False)
            update_button.setStyleSheet(UPDATE_BUTTON_DISABLED_STYLE)
            update_button.setToolTip("申請者/管理者のユーザー名が解決できないため更新できません")
            enable_update_override_button.setEnabled(False)
            enable_update_override_button.setText("更新有効化")
            enable_update_override_button.setToolTip("申請者/管理者のユーザー名が未解決のため更新できません")
            return

        update_button.setEnabled(effective_enabled)

        if effective_enabled:
            update_button.setStyleSheet(UPDATE_BUTTON_ENABLED_STYLE)
            if is_default_filter:
                update_button.setToolTip("")
            else:
                update_button.setToolTip("手動で更新制限を解除しています。権限がないデータセットはRDE側で拒否されます")
        else:
            update_button.setToolTip("デフォルト設定（ユーザー所属のみ、課題番号フィルタなし）でのみ更新可能です")
            update_button.setStyleSheet(UPDATE_BUTTON_DISABLED_STYLE)

        if is_default_filter:
            enable_update_override_button.setEnabled(False)
            enable_update_override_button.setText("更新有効化")
            enable_update_override_button.setToolTip("ユーザー所属のみ、課題番号フィルタなしの状態では常に更新できます")
        else:
            if update_override_state["enabled"]:
                enable_update_override_button.setEnabled(False)
                enable_update_override_button.setText("更新有効化済")
            else:
                enable_update_override_button.setEnabled(True)
                enable_update_override_button.setText("更新有効化")
            enable_update_override_button.setToolTip("安全確保のため更新が無効です。自己責任で一時的に有効化できます")

    def refresh_update_controls(filter_type=None, grant_number_filter=None):
        current_filter_type = filter_type if filter_type is not None else get_current_filter_type()
        current_grant_filter = (grant_number_filter if grant_number_filter is not None
                                else grant_number_filter_edit.text().strip())
        apply_update_button_state(current_filter_type, current_grant_filter)

    def reset_update_override(reason="", filter_type=None, grant_number_filter=None):
        if update_override_state["enabled"]:
            logger.info("更新ボタンの手動有効化を解除: %s", reason or "理由未指定")
            update_override_state["enabled"] = False
        refresh_update_controls(filter_type, grant_number_filter)

    def update_combo_box_ui(datasets, display_names, filter_type, grant_number_filter, dataset_count):
        """コンボボックスのUIを更新する"""
        refresh_update_controls(filter_type, grant_number_filter)

        was_blocked = existing_dataset_combo.signalsBlocked()
        existing_dataset_combo.blockSignals(True)
        try:
            # コンボボックスを完全にクリア（キャッシュも含む）
            existing_dataset_combo.clear()
            if hasattr(existing_dataset_combo, '_datasets_cache'):
                delattr(existing_dataset_combo, '_datasets_cache')
            if hasattr(existing_dataset_combo, '_display_names_cache'):
                delattr(existing_dataset_combo, '_display_names_cache')

            # 既存のCompleterがあればクリア
            if existing_dataset_combo.completer():
                existing_dataset_combo.completer().deleteLater()

            # コンボボックスにアイテムを追加（重要：カーソルキー操作に必要）
            if not datasets or not display_names:
                existing_dataset_combo.addItem("-- データセットを選択してください --", None)
                logger.debug("データセットなし: プレースホルダのみ追加")
            else:
                # 全データセットをコンボボックスに追加
                for i in range(min(len(display_names), len(datasets))):
                    display_text = display_names[i]
                    dataset = datasets[i]
                    if isinstance(dataset, dict):
                        existing_dataset_combo.addItem(display_text, dataset)
                    else:
                        logger.warning("データセットが辞書ではありません: index=%s, type=%s", i, type(dataset))
                logger.debug("コンボボックスに %s 件のアイテムを追加", len(datasets))

            # QCompleterを設定
            completer = QCompleter(display_names, existing_dataset_combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            # 検索時の補完リスト（popup）の高さを12行分に制限
            popup_view = completer.popup()
            popup_view.setMinimumHeight(240)
            popup_view.setMaximumHeight(240)
            existing_dataset_combo.setCompleter(completer)
            # Completerからの選択シグナルを接続
            completer.activated.connect(on_completer_activated)

            # プレースホルダーテキストを設定
            if existing_dataset_combo.lineEdit():
                filter_desc = f"フィルタ: {filter_type}"
                if grant_number_filter:
                    filter_desc += f", 課題番号: '{grant_number_filter}'"
                existing_dataset_combo.lineEdit().setPlaceholderText(f"データセット ({dataset_count}件) から検索... [{filter_desc}]")

            # データセット一覧をComboBoxに保存（mousePressEvent用）
            existing_dataset_combo._datasets_cache = datasets
            existing_dataset_combo._display_names_cache = display_names
            # 表示テキスト→データセット(dict)の高速マップを構築（Completer選択用）
            # キーを正規化してCompleter選択時のマッチング精度を向上
            try:
                existing_dataset_combo._display_to_dataset_map = {
                    _normalize_display_text(display_names[i]): datasets[i]
                    for i in range(min(len(display_names), len(datasets)))
                    if isinstance(datasets[i], dict)
                }
                logger.debug("display_to_dataset_map 構築完了: %s エントリ", len(existing_dataset_combo._display_to_dataset_map))
            except Exception as map_err:
                logger.debug("display_to_dataset_map 構築失敗: %s", map_err)

            # コンボを未選択状態にする（ヘッダー/プレースホルダのみ）
            try:
                existing_dataset_combo.setCurrentIndex(-1)
            except Exception:
                pass
        finally:
            existing_dataset_combo.blockSignals(was_blocked)

    # データセット情報を読み込んでドロップダウンに追加
    def load_existing_datasets(
        filter_type="user_only",
        grant_number_filter="",
        force_reload=False,
        preserve_selection_id: str | None = None,
    ):
        """
        データセット一覧を読み込み、フィルタ条件に基づいて表示
        
        Args:
            filter_type: "user_only", "others_only", "all"
            grant_number_filter: 課題番号の部分一致検索文字列
            force_reload: キャッシュを無視して強制再読み込み
            preserve_selection_id: 再読み込み後に再選択したいデータセットID
        """
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        logger.debug("データセットファイルパス: %s", dataset_path)
        logger.debug("ファイル存在確認: %s", os.path.exists(dataset_path))
        logger.debug("フィルタタイプ: %s, 課題番号フィルタ: '%s'", filter_type, grant_number_filter)
        logger.debug("強制再読み込み: %s", force_reload)
        
        # キャッシュキーを生成
        cache_key = get_cache_key(filter_type, grant_number_filter)
        
        # キャッシュが有効で、強制再読み込みでない場合はキャッシュを使用
        if not force_reload and is_cache_valid() and cache_key in dataset_cache["filtered_datasets"]:
            logger.info("キャッシュからデータセット一覧を読み込み: %s", cache_key)
            datasets = dataset_cache["filtered_datasets"][cache_key]
            display_names = dataset_cache["display_data"][cache_key]
            user_grant_numbers = dataset_cache["user_grant_numbers"]
            
            # UIを更新
            update_combo_box_ui(datasets, display_names, filter_type, grant_number_filter, len(datasets))
            if preserve_selection_id:
                _restore_dataset_selection(preserve_selection_id)
            logger.info("キャッシュからの読み込み完了: %s件", len(datasets))
            return
        
        try:
            logger.info("データセット一覧の再読み込みを開始")
            
            if not os.path.exists(dataset_path):
                logger.error("データセットファイルが見つかりません: %s", dataset_path)
                return
            
            # ファイルの最終更新時刻を取得
            current_modified = os.path.getmtime(dataset_path)
            
                # 基本データの読み込み（キャッシュまたは新規読み込み）
            if not is_cache_valid() or force_reload:
                logger.info("基本データを新規読み込み")
                
                # 統合プログレス表示
                # ※明示 show() は minimumDuration を無効化して一瞬ポップアップの原因になり得るため呼ばない
                loading_progress = create_progress_dialog("データ読み込み中", "データセット情報を読み込んでいます...", 0)
                
                try:
                    loading_progress.setLabelText("dataset.jsonを読み込んでいます...")
                    _process_events()
                    
                    try:
                        with open(dataset_path, encoding="utf-8", errors='replace') as f:
                            data = json.load(f)
                            
                        loading_progress.setLabelText("JSONデータを解析中...")
                        _process_events()
                        
                    except (json.JSONDecodeError, UnicodeDecodeError) as json_error:
                        logger.error("データセット読み込みエラー: %s", json_error)
                        logger.error("ファイルパス: %s", dataset_path)
                        
                        # UTF-8デコードエラーの場合は修復を試行
                        if isinstance(json_error, UnicodeDecodeError):
                            logger.info("UTF-8デコードエラーを検出、ファイル修復を試行します")
                            try:
                                repaired_data = repair_json_file(dataset_path)
                                if repaired_data:
                                    data = repaired_data
                                    logger.info("ファイル修復に成功しました")
                                else:
                                    logger.error("ファイル修復に失敗しました")
                                    return
                            except Exception as repair_error:
                                logger.error("ファイル修復中にエラー: %s", repair_error)
                                return
                        else:
                            # ファイルサイズ確認
                            file_size = os.path.getsize(dataset_path)
                            logger.error("ファイルサイズ: %s bytes", file_size)
                        
                        # バックアップファイルの確認と復旧試行
                        backup_file = dataset_path + ".backup"
                        if os.path.exists(backup_file):
                            logger.info("バックアップファイルから復旧を試行: %s", backup_file)
                            try:
                                # バックアップファイルも修復機能を使用
                                backup_data = repair_json_file(backup_file)
                                if backup_data:
                                    data = backup_data
                                    logger.info("バックアップファイルから正常に読み込み、元ファイルを置き換えました")
                                    # 修復したバックアップで元ファイルを置き換え
                                    shutil.copy2(backup_file, dataset_path)
                                else:
                                    logger.error("バックアップファイルも破損しています")
                                    return
                                
                            except Exception as backup_error:
                                logger.error("バックアップファイルからの復旧も失敗: %s", backup_error)
                                return
                        else:
                            logger.error("バックアップファイルが見つかりません: %s", backup_file)
                            logger.info("最初から読み込みなおしを試行します...")
                            
                            # 最後の手段として、元ファイルを修復機能で直接修復
                            try:
                                repaired_original = repair_json_file(dataset_path)
                                if repaired_original:
                                    data = repaired_original
                                    logger.info("元ファイルの直接修復が成功しました")
                                else:
                                    logger.error("元ファイルの修復も失敗しました")
                                    if not is_pytest:
                                        QMessageBox.critical(
                                            widget,
                                            "エラー",
                                            "データセットファイルが破損しており、修復できませんでした。\n"
                                            "新しいファイルが作成されます。",
                                        )
                                    data = {"data": [], "links": {}, "meta": {}}
                            except Exception as final_error:
                                logger.error("最終修復試行も失敗: %s", final_error)
                                if not is_pytest:
                                    QMessageBox.critical(
                                        widget,
                                        "エラー",
                                        "データセットファイルの読み込みに完全に失敗しました。\n"
                                        "空のデータセットリストから開始します。",
                                    )
                                data = {"data": [], "links": {}, "meta": {}}
                    
                    # ユーザーのgrantNumber取得
                    loading_progress.setLabelText("ユーザーの権限情報を取得しています...")
                    _process_events()
                    
                    # データをキャッシュに保存
                    dataset_cache["raw_data"] = data.get("data", [])
                    dataset_cache["last_modified"] = current_modified
                    dataset_cache["user_grant_numbers"] = get_user_grant_numbers()
                    logger.info("基本データキャッシュ更新: データセット数=%s", len(dataset_cache['raw_data']))
                    
                finally:
                    loading_progress.close()
            else:
                logger.info("キャッシュから基本データを使用")
            
            # キャッシュからデータを取得
            all_datasets = dataset_cache["raw_data"]
            # RDE側で削除済み（404/410確認済み）のデータセットはローカル候補から除外
            try:
                from classes.utils.remote_resource_pruner import filter_out_marked_missing_ids

                all_datasets = filter_out_marked_missing_ids(
                    all_datasets or [],
                    resource_type="dataset",
                    id_key="id",
                )
            except Exception:
                pass
            user_grant_numbers = dataset_cache["user_grant_numbers"]
            logger.debug("データセット数: %s", len(all_datasets))
            logger.debug("ユーザーのgrantNumber一覧: %s", sorted(user_grant_numbers))
            
            # フィルタリング処理（プログレス表示付き）
            datasets, grant_number_matches = process_datasets_with_progress(
                all_datasets, user_grant_numbers, filter_type, grant_number_filter
            )
            
            # 課題番号ごとのマッチ結果を表示（ユーザー所属のみ）
            if grant_number_matches:
                logger.debug("課題番号別マッチ結果（ユーザー所属）:")
                for grant_number, count in grant_number_matches.items():
                    logger.debug("%s: %s件", grant_number, count)
            
            # セキュリティ情報をログ出力
            logger.info("データセット編集: 全データセット数=%s, 表示データセット数=%s", len(all_datasets), len(datasets))
            logger.info("ユーザーが属するgrantNumber: %s", sorted(user_grant_numbers))
            logger.info("フィルタ設定: タイプ=%s, 課題番号='%s'", filter_type, grant_number_filter)
            
            # 表示名リストを作成（プログレス表示付き）
            display_names = create_display_names_with_progress(datasets, user_grant_numbers)
            
            # キャッシュに保存
            dataset_cache["filtered_datasets"][cache_key] = datasets
            dataset_cache["display_data"][cache_key] = display_names
            logger.info("フィルタ結果をキャッシュに保存: %s -> %s件", cache_key, len(datasets))
            
            # UIを更新
            update_combo_box_ui(datasets, display_names, filter_type, grant_number_filter, len(datasets))
            if preserve_selection_id:
                _restore_dataset_selection(preserve_selection_id)
            
            logger.info("データセット一覧の再読み込み完了: %s件", len(datasets))
            
            # QComboBox自体のmousePressEventをラップして全リスト表示＋popup（初回のみ設定）
            if not hasattr(existing_dataset_combo, '_mouse_press_event_set'):
                orig_mouse_press = existing_dataset_combo.mousePressEvent
                def combo_mouse_press_event(event):
                    # ドロップダウンボタンクリック時は常に全リスト表示
                    # テキストボックス部分のクリックでもCompleterが機能するため問題なし
                    current_text = existing_dataset_combo.lineEdit().text() if existing_dataset_combo.lineEdit() else ""
                    
                    # コンボボックスが空、またはアイテム数が0の場合はキャッシュから復元
                    if existing_dataset_combo.count() == 0:
                        # コンボボックスをクリア
                        existing_dataset_combo.clear()
                        
                        # キャッシュされたデータセット一覧と表示名を使用
                        cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', [])
                        cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', [])
                        
                        logger.debug("コンボボックス展開（キャッシュから復元）: %s件のデータセット", len(cached_datasets))
                        
                        # 高速化されたアイテム追加処理
                        if cached_datasets:
                            populate_combo_box_with_progress(existing_dataset_combo, cached_datasets, cached_display_names)
                        else:
                            # フォールバック：キャッシュがない場合は従来の方法
                            existing_dataset_combo.addItem("-- データセットを選択してください --", None)
                        
                        # 復元後、元のテキストを設定
                        if current_text and existing_dataset_combo.lineEdit():
                            existing_dataset_combo.lineEdit().setText(current_text)
                    
                    existing_dataset_combo.showPopup()
                    orig_mouse_press(event)
                
                existing_dataset_combo.mousePressEvent = combo_mouse_press_event
                existing_dataset_combo._mouse_press_event_set = True
            
        except Exception as e:
            QMessageBox.warning(widget, "エラー", f"データセット情報の読み込みに失敗しました: {e}")
            logger.error("データセット読み込みエラー: %s", e)
            import traceback
            traceback.print_exc()
    
    # 関連データセット選択機能
    def setup_related_datasets(related_dataset_combo, exclude_dataset_id=None):
        """関連データセット選択機能のセットアップ
        
        Args:
            related_dataset_combo: 関連データセット選択用のコンボボックス
            exclude_dataset_id: 除外するデータセットID（現在編集中のデータセット）
        """
        try:
            datasets_file = get_dynamic_file_path("output/rde/data/dataset.json")
            logger.debug("関連データセット用全データセット読み込み開始: %s", datasets_file)
            
            if not os.path.exists(datasets_file):
                logger.error("データセットファイルが見つかりません: %s", datasets_file)
                return
            
            try:
                with open(datasets_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as json_error:
                logger.error("JSONパースエラー: %s", json_error)
                logger.error("ファイルパス: %s", datasets_file)
                
                # ファイルサイズ確認
                file_size = os.path.getsize(datasets_file)
                logger.error("ファイルサイズ: %s bytes", file_size)
                
                # バックアップファイルの確認と復旧試行
                backup_file = datasets_file + ".backup"
                if os.path.exists(backup_file):
                    logger.info("バックアップファイルから復旧を試行: %s", backup_file)
                    try:
                        with open(backup_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        logger.info("バックアップファイルから正常に読み込みました")
                        
                        # 破損したファイルを置き換え
                        import shutil
                        shutil.copy2(backup_file, datasets_file)
                        logger.info("バックアップファイルで破損ファイルを置き換えました")
                        
                    except Exception as backup_error:
                        logger.error("バックアップファイルからの復旧も失敗: %s", backup_error)
                        return
                else:
                    logger.error("バックアップファイルが見つかりません: %s", backup_file)
                    return
            
            all_datasets = data.get("data", [])
            
            # 除外するデータセットIDがある場合はフィルタリング
            if exclude_dataset_id:
                all_datasets = [dataset for dataset in all_datasets if dataset.get("id") != exclude_dataset_id]
                logger.debug("データセットID '%s' を除外", exclude_dataset_id)
            
            logger.info("全データセット読み込み完了: %s件", len(all_datasets))
            
            # ユーザーのgrantNumberを取得
            user_grant_numbers = get_user_grant_numbers()
            
            # ユーザーのデータセットとその他のデータセットに分離
            user_datasets = []
            other_datasets = []
            
            for dataset in all_datasets:
                attrs = dataset.get("attributes", {})
                grant_number = attrs.get("grantNumber", "")
                
                if grant_number in user_grant_numbers:
                    user_datasets.append(dataset)
                else:
                    other_datasets.append(dataset)
            
            # ユーザーのデータセットを先頭に配置
            sorted_datasets = user_datasets + other_datasets
            
            # 表示名リストを作成
            display_names = []
            for i, dataset in enumerate(sorted_datasets):
                attrs = dataset.get("attributes", {})
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if i < len(user_datasets):
                    display_text = f"★ {grant_number} - {name}"  # ユーザー所属
                else:
                    display_text = f"{grant_number} - {name}"  # その他
                    
                if dataset_type:
                    display_text += f" ({dataset_type})"
                display_names.append(display_text)
            
            # コンボボックスのクリアとCompleter設定
            related_dataset_combo.clear()
            if hasattr(related_dataset_combo, '_all_datasets_cache'):
                delattr(related_dataset_combo, '_all_datasets_cache')
            
            # コンボボックスにアイテムを追加
            for i, dataset in enumerate(sorted_datasets):
                attrs = dataset.get("attributes", {})
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if i < len(user_datasets):
                    display_text = f"★ {grant_number} - {name}"  # ユーザー所属
                else:
                    display_text = f"{grant_number} - {name}"  # その他
                    
                if dataset_type:
                    display_text += f" ({dataset_type})"
                
                # コンボボックスにアイテムを追加（データセット情報も保存）
                related_dataset_combo.addItem(display_text, dataset)
            
            # QCompleterを設定
            completer = QCompleter(display_names, related_dataset_combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            popup_view = completer.popup()
            popup_view.setMinimumHeight(240)
            popup_view.setMaximumHeight(240)
            related_dataset_combo.setCompleter(completer)
            
            # プレースホルダーテキストを設定
            if related_dataset_combo.lineEdit():
                related_dataset_combo.lineEdit().setPlaceholderText(f"関連データセット ({len(sorted_datasets)}件) から検索...")
            
            # データセット一覧をComboBoxに保存
            related_dataset_combo._all_datasets_cache = sorted_datasets
            
            logger.info("関連データセット選択機能セットアップ完了: ユーザー所属=%s件, その他=%s件", len(user_datasets), len(other_datasets))
            
        except Exception as e:
            logger.error("関連データセット読み込み中にエラー: %s", e)
    
    # 関連データセット追加処理（共通化）
    def add_related_dataset_to_list(selected_datasets_list, dataset_id, dataset_name):
        """関連データセットをリストに追加（削除ボタン付きウィジェット）"""
        # 既に選択済みかチェック
        for i in range(selected_datasets_list.count()):
            item = selected_datasets_list.item(i)
            if item and item.data(Qt.UserRole) == dataset_id:
                logger.info("データセット '%s' は既に選択済みです", dataset_name)
                return False
        
        # リストアイテム作成
        item = QListWidgetItem()
        item.setData(Qt.UserRole, dataset_id)
        selected_datasets_list.addItem(item)
        
        # 削除ボタン付きウィジェットを作成
        item_widget = QWidget()
        item_layout = QHBoxLayout()
        item_layout.setContentsMargins(4, 2, 4, 2)
        
        # データセット名ラベル
        dataset_label = QLabel(f"{dataset_name} (ID: {dataset_id})")
        item_layout.addWidget(dataset_label, 1)  # stretch factor 1
        
        # 削除ボタン
        remove_btn = QPushButton("❌")
        remove_btn.setMaximumWidth(30)
        remove_btn.setToolTip("この関連データセットを削除")
        remove_btn.setStyleSheet("QPushButton { padding: 2px; }")
        remove_btn.clicked.connect(
            lambda checked=False, i=item: selected_datasets_list.takeItem(selected_datasets_list.row(i))
        )
        item_layout.addWidget(remove_btn)
        
        item_widget.setLayout(item_layout)
        selected_datasets_list.setItemWidget(item, item_widget)
        
        # アイテムのサイズを調整
        item.setSizeHint(item_widget.sizeHint())
        
        return True
    
    # 関連データセット選択イベント処理
    def on_related_dataset_selected(related_dataset_combo, selected_datasets_list):
        """関連データセットが選択された時の処理"""
        current_text = related_dataset_combo.lineEdit().text().strip()
        if not current_text:
            return
        
        # キャッシュからデータセットを検索
        cached_datasets = getattr(related_dataset_combo, '_all_datasets_cache', [])
        selected_dataset = None
        
        for dataset in cached_datasets:
            attrs = dataset.get("attributes", {})
            name = attrs.get("name", "名前なし")
            grant_number = attrs.get("grantNumber", "")
            dataset_type = attrs.get("datasetType", "")
            display_text = f"{grant_number} - {name}"
            if dataset_type:
                display_text += f" ({dataset_type})"
            
            # ★マークありでもなしでも一致検索
            if current_text.replace("★ ", "") == display_text:
                selected_dataset = dataset
                break
        
        if selected_dataset:
            dataset_id = selected_dataset.get("id", "")
            dataset_name = selected_dataset.get("attributes", {}).get("name", "名前なし")
            
            # 既に選択済みかチェックと追加は共通関数で処理
            if add_related_dataset_to_list(selected_datasets_list, dataset_id, dataset_name):
                logger.info("関連データセットを追加: %s (ID: %s)", dataset_name, dataset_id)
            
            # コンボボックスをクリア
            related_dataset_combo.lineEdit().clear()
    
    # 関連データセット削除処理
    def on_remove_dataset(selected_datasets_list):
        """選択されたデータセットを削除"""
        current_item = selected_datasets_list.currentItem()
        if current_item:
            dataset_id = current_item.data(Qt.UserRole)
            dataset_text = current_item.text()
            selected_datasets_list.takeItem(selected_datasets_list.row(current_item))
            logger.info("関連データセットを削除: %s", dataset_text)
    
    # 編集フォーム作成
    def create_edit_form():
        """編集フォームを作成"""
        form_widget = QWidget()
        form_layout = QGridLayout()
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(6)
        # 2列レイアウト（左: ラベル, 右: 入力/ボタン）
        form_layout.setColumnStretch(1, 1)
        
        # データセット名
        form_layout.addWidget(QLabel("データセット名:"), 0, 0)
        edit_dataset_name_edit = QLineEdit()
        edit_dataset_name_edit.setPlaceholderText("データセット名を入力")
        form_layout.addWidget(edit_dataset_name_edit, 0, 1)
        
        # 課題番号（コンボボックスに変更）
        form_layout.addWidget(QLabel("課題番号:"), 1, 0)
        edit_grant_number_combo = QComboBox()
        edit_grant_number_combo.setEditable(True)
        edit_grant_number_combo.setInsertPolicy(QComboBox.NoInsert)
        edit_grant_number_combo.lineEdit().setPlaceholderText("課題番号を選択または入力")
        
        # 初期状態でユーザーの課題番号を設定
        def update_grant_number_combo_local(grant_numbers):
            """課題番号コンボボックスを更新する"""
            # 既存のアイテムをクリア
            edit_grant_number_combo.clear()
            
            # 既存のCompleterがあればクリア
            if edit_grant_number_combo.completer():
                edit_grant_number_combo.completer().deleteLater()
            
            if grant_numbers:
                sorted_grant_numbers = sorted(grant_numbers)
                for grant_number in sorted_grant_numbers:
                    edit_grant_number_combo.addItem(grant_number, grant_number)
                edit_grant_number_combo.setCurrentIndex(-1)  # 初期選択なし
                
                # 自動補完機能を追加
                grant_completer = QCompleter(sorted_grant_numbers, edit_grant_number_combo)
                grant_completer.setCaseSensitivity(Qt.CaseInsensitive)
                grant_completer.setFilterMode(Qt.MatchContains)
                edit_grant_number_combo.setCompleter(grant_completer)
                
                logger.debug("課題番号コンボボックスを更新: %s", sorted_grant_numbers)
            else:
                logger.debug("課題番号が空のため、コンボボックスは空のまま")
        
        # この関数をedit_grant_number_comboのプロパティとして保存
        edit_grant_number_combo.update_grant_numbers = update_grant_number_combo_local
        
        try:
            user_grant_numbers = get_user_grant_numbers()
            update_grant_number_combo_local(user_grant_numbers)
        except Exception as e:
            logger.debug("初期課題番号リスト取得エラー: %s", e)
        
        form_layout.addWidget(edit_grant_number_combo, 1, 1)
        
        # 説明
        form_layout.addWidget(QLabel("説明:"), 2, 0)
        
        # 説明フィールド用の水平レイアウト
        description_layout = QHBoxLayout()
        edit_description_edit = QTextEdit()
        edit_description_edit.setPlaceholderText("データセットの説明を入力")
        edit_description_edit.setMaximumHeight(80)  # 4行程度

        # QTextEdit/QTextBrowser は環境によって ::viewport の描画が揺れるため、
        # viewport側の枠線/背景(QSS)が確実に描画されるよう StyledBackground を付与する。
        try:
            edit_description_edit.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            edit_description_edit.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        description_layout.addWidget(edit_description_edit)
        
        # AIサジェストボタン用の縦並びレイアウト
        ai_buttons_layout = QVBoxLayout()
        ai_buttons_layout.setContentsMargins(0, 0, 0, 0)
        ai_buttons_layout.setSpacing(4)  # ボタン間の間隔
        
        # SpinnerButtonをインポート
        from classes.dataset.ui.spinner_button import SpinnerButton
        
        # AIボタン（通常版・ダイアログ表示）
        ai_suggest_button = SpinnerButton("🤖 AI提案")
        ai_suggest_button.setMinimumWidth(80)
        ai_suggest_button.setMaximumWidth(100)
        ai_suggest_button.setMinimumHeight(32)
        ai_suggest_button.setMaximumHeight(36)
        ai_suggest_button.setToolTip("AIによる説明文の提案（ダイアログ表示）\n複数の候補から選択できます")
        ai_suggest_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-size: 11px;
                font-weight: bold;
                border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                border-radius: 6px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
            }}
        """)
        
        # クイックAIボタン（即座反映版）
        quick_ai_button = SpinnerButton("⚡ Quick AI")
        quick_ai_button.setMinimumWidth(80)
        quick_ai_button.setMaximumWidth(100)
        quick_ai_button.setMinimumHeight(32)
        quick_ai_button.setMaximumHeight(36)
        quick_ai_button.setToolTip("AIによる説明文の即座生成（直接反映）\nワンクリックで自動入力されます")
        quick_ai_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-size: 11px;
                font-weight: bold;
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
                border-radius: 6px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
            }}
        """)
        
        ai_buttons_layout.addWidget(ai_suggest_button)
        ai_buttons_layout.addWidget(quick_ai_button)
        
        # AI CHECKボタン（品質チェック版）
        ai_check_button = SpinnerButton("📋 AI CHECK")
        ai_check_button.setMinimumWidth(80)
        ai_check_button.setMaximumWidth(100)
        ai_check_button.setMinimumHeight(32)
        ai_check_button.setMaximumHeight(36)
        ai_check_button.setToolTip("説明文の簡易品質チェック\nAIが妥当性を評価します")
        ai_check_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                font-size: 11px;
                font-weight: bold;
                border: 1px solid {get_color(ThemeKey.BUTTON_INFO_BORDER)};
                border-radius: 6px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_PRESSED)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
            }}
        """)
        
        ai_buttons_layout.addWidget(ai_check_button)
        
        # AI提案ダイアログ表示のコールバック関数（既存）
        def show_ai_suggestion():
            try:
                # スピナー開始（ボタン無効化）
                ai_suggest_button.start_loading("AI生成中")
                _process_events()  # UI更新
                
                # 現在のフォームデータを収集してコンテキストとして使用
                context_data = {}
                
                # 【重要】現在選択されているデータセットIDを取得
                current_index = existing_dataset_combo.currentIndex()
                if current_index > 0:  # 0は"選択してください"項目
                    selected_dataset = existing_dataset_combo.itemData(current_index)
                    if selected_dataset:
                        dataset_id = selected_dataset.get("id")
                        if dataset_id:
                            context_data['dataset_id'] = dataset_id
                            logger.debug("データセットID設定: %s", dataset_id)
                
                # データセット名
                if hasattr(edit_dataset_name_edit, 'text'):
                    context_data['name'] = edit_dataset_name_edit.text().strip()
                
                # データセットタイプ（デフォルトまたは推定）
                context_data['type'] = 'mixed'  # デフォルト
                
                # 課題番号
                if hasattr(edit_grant_number_combo, 'currentText'):
                    grant_text = edit_grant_number_combo.currentText().strip()
                    if grant_text and grant_text != "課題番号を選択してください":
                        context_data['grant_number'] = grant_text
                    else:
                        context_data['grant_number'] = ''
                
                # 既存の説明文
                if hasattr(edit_description_edit, 'toPlainText'):
                    existing_desc = edit_description_edit.toPlainText().strip()
                    context_data['description'] = existing_desc if existing_desc else ''
                
                # アクセスポリシー（必要に応じて）
                context_data['access_policy'] = 'restricted'  # デフォルト
                
                # その他のフォーム情報
                if hasattr(edit_contact_edit, 'text'):
                    context_data['contact'] = edit_contact_edit.text().strip()
                
                # データセットIDが未設定の場合のフォールバック取得
                if not context_data.get('dataset_id'):
                    try:
                        # コンボボックスの現在選択から抽出（"ID: XXXXX" の形式を想定）
                        if hasattr(existing_dataset_combo, 'currentText'):
                            txt = existing_dataset_combo.currentText()
                            import re
                            m = re.search(r"ID:\s*([A-Za-z0-9_-]+)", txt)
                            fallback_id = m.group(1) if m else None
                            if fallback_id:
                                context_data['dataset_id'] = fallback_id
                                logger.debug("フォールバックでデータセットID設定: %s", fallback_id)
                    except Exception as _e:
                        logger.debug("データセットIDフォールバック取得に失敗: %s", _e)

                logger.debug("AI提案に渡すコンテキストデータ: %s", context_data)
                
                # AI提案ダイアログを表示（自動生成有効、データセット提案モード）
                dialog = AISuggestionDialog(
                    parent=widget, 
                    context_data=context_data, 
                    auto_generate=True,
                    mode="dataset_suggestion"  # データセット提案モード: AI提案、プロンプト全文、詳細情報タブ
                )
                
                # ダイアログをモーダルで開く（完了/キャンセルまで待機）
                if dialog.exec() == QDialog.Accepted:
                    suggestion = dialog.get_selected_suggestion()
                    if suggestion:
                        # QTextEditの場合はsetPlainTextを使用して改行を保持
                        if hasattr(edit_description_edit, 'setPlainText'):
                            edit_description_edit.setPlainText(suggestion)
                        else:
                            edit_description_edit.setText(suggestion)
                        
            except Exception as e:
                QMessageBox.critical(widget, "エラー", f"AI提案機能でエラーが発生しました: {str(e)}")
            finally:
                # 完了/キャンセル/エラー時にボタンを再有効化
                ai_suggest_button.stop_loading()
        
        # クイックAI生成のコールバック関数（新規）
        def show_quick_ai_suggestion():
            try:
                # スピナー開始
                quick_ai_button.start_loading("生成中")
                _process_events()  # UI更新
                
                # 現在のフォームデータを収集してコンテキストとして使用
                context_data = {}
                
                # 【重要】現在選択されているデータセットIDを取得
                current_index = existing_dataset_combo.currentIndex()
                if current_index > 0:  # 0は"選択してください"項目
                    selected_dataset = existing_dataset_combo.itemData(current_index)
                    if selected_dataset:
                        dataset_id = selected_dataset.get("id")
                        if dataset_id:
                            context_data['dataset_id'] = dataset_id
                            logger.debug("データセットID設定（クイック版）: %s", dataset_id)
                
                # データセット名
                if hasattr(edit_dataset_name_edit, 'text'):
                    context_data['name'] = edit_dataset_name_edit.text().strip()
                
                # データセットタイプ（デフォルトまたは推定）
                context_data['type'] = 'mixed'  # デフォルト
                
                # 課題番号
                if hasattr(edit_grant_number_combo, 'currentText'):
                    grant_text = edit_grant_number_combo.currentText().strip()
                    if grant_text and grant_text != "課題番号を選択してください":
                        context_data['grant_number'] = grant_text
                    else:
                        context_data['grant_number'] = ''
                
                # 既存の説明文
                if hasattr(edit_description_edit, 'toPlainText'):
                    existing_desc = edit_description_edit.toPlainText().strip()
                    context_data['description'] = existing_desc if existing_desc else ''
                
                # アクセスポリシー（必要に応じて）
                context_data['access_policy'] = 'restricted'  # デフォルト
                
                # その他のフォーム情報
                if hasattr(edit_contact_edit, 'text'):
                    context_data['contact'] = edit_contact_edit.text().strip()
                
                logger.debug("クイックAI提案に渡すコンテキストデータ: %s", context_data)
                
                # クイック版AI機能を実行（ダイアログなし）
                from classes.dataset.core.quick_ai_suggestion import generate_quick_suggestion
                suggestion = generate_quick_suggestion(context_data)
                
                if suggestion:
                    # 既存の説明文を置き換え（QTextEditの場合はsetPlainTextを使用して改行を保持）
                    if hasattr(edit_description_edit, 'setPlainText'):
                        edit_description_edit.setPlainText(suggestion)
                    else:
                        edit_description_edit.setText(suggestion)
                    logger.info("クイックAI提案を適用: %s文字", len(suggestion))
                else:
                    QMessageBox.warning(widget, "警告", "クイックAI提案の生成に失敗しました")
                    
            except Exception as e:
                QMessageBox.critical(widget, "エラー", f"クイックAI提案機能でエラーが発生しました: {str(e)}")
            finally:
                # 必ずスピナーを停止
                quick_ai_button.stop_loading()
        
        ai_suggest_button.clicked.connect(show_ai_suggestion)
        quick_ai_button.clicked.connect(show_quick_ai_suggestion)
        
        # AI CHECKボタンのコールバック関数
        def check_description_quality():
            """説明文の簡易品質チェック（AIテスト2と同じロジック）"""
            try:
                # データセットが選択されているかチェック
                selected_dataset = _get_selected_dataset_from_combo()
                if not selected_dataset:
                    QMessageBox.warning(widget, "警告", "データセットを選択してください")
                    return
                
                dataset_id = selected_dataset.get("id")
                if not dataset_id:
                    QMessageBox.warning(widget, "警告", "データセットIDが取得できません")
                    return
                
                # 説明文が入力されているかチェック
                current_description = edit_description_edit.toPlainText().strip()
                if not current_description:
                    QMessageBox.warning(widget, "警告", "説明文を入力してください")
                    return
                
                # スピナー開始
                ai_check_button.start_loading("チェック中")
                _process_events()
                
                # コンテキスト収集
                context_data = {
                    'dataset_id': dataset_id,
                    'name': selected_dataset.get("attributes", {}).get("name", ""),
                    'description': current_description
                }
                
                logger.info("AI CHECKボタン: dataset_id=%s", dataset_id)
                
                # AIテスト2と同じパターンでAI実行
                from classes.ai.core.ai_manager import AIManager
                from classes.dataset.util.ai_extension_helper import load_ai_extension_config
                from config.common import get_dynamic_file_path
                
                ai_manager = AIManager()
                ai_ext_config = load_ai_extension_config()
                
                # 設定から "json_check_dataset_summary_simple_quality" を取得
                button_config = None
                for entry in ai_ext_config.get("buttons", []):
                    if entry.get("id") == "json_check_dataset_summary_simple_quality":
                        button_config = entry
                        break
                
                if not button_config:
                    QMessageBox.critical(widget, "エラー", "品質チェック設定が見つかりません")
                    ai_check_button.stop_loading()
                    return
                
                # プロンプトファイルを読み込み
                prompt_file = button_config.get("prompt_file")
                prompt_path = get_dynamic_file_path(prompt_file)
                
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
                
                # コンテキストをプロンプトに適用（AIテスト2と同じ）
                from classes.dataset.util.ai_extension_helper import format_prompt_with_context
                
                # 完全コンテキスト収集
                from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
                context_collector = get_dataset_context_collector()
                full_context = context_collector.collect_full_context(
                    dataset_id=dataset_id,
                    name=context_data['name'],
                    type=selected_dataset.get("attributes", {}).get("datasetType", ""),
                    existing_description=current_description,
                    grant_number=selected_dataset.get("attributes", {}).get("grantNumber", "")
                )
                
                # AI設定を取得（llm_model_name プレースホルダ置換用）
                from classes.ai.core.ai_manager import AIManager
                ai_manager = AIManager()
                provider = ai_manager.get_default_provider()
                model = ai_manager.get_default_model(provider)
                
                # AI設定をコンテキストに追加
                full_context['llm_provider'] = provider
                full_context['llm_model'] = model
                full_context['llm_model_name'] = f"{provider}:{model}"
                
                # プロンプトテンプレートで {description} が使用されているため、エイリアスを設定
                full_context['description'] = current_description
                
                prompt = format_prompt_with_context(prompt_template, full_context)
                
                # プロンプトをログ出力（デバッグ用）
                logger.debug("AI CHECKボタン: プロンプト長=%s文字", len(prompt))
                logger.debug("AI CHECKボタン: コンテキストキー=%s", list(full_context.keys()))
                
                # AI実行スレッド
                from classes.dataset.ui.ai_suggestion_dialog import AIRequestThread
                
                def _show_ai_check_details(prompt_text: str, response_text: str, parent_dialog=None):
                    """問い合わせ内容とレスポンスを詳細表示するモーダルダイアログ"""
                    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QSplitter
                    from PySide6.QtCore import Qt
                    
                    detail_dialog = QDialog(widget)
                    detail_dialog.setWindowTitle("AI チェック詳細内容")
                    detail_dialog.setGeometry(150, 150, 1200, 700)
                    detail_dialog.setModal(True)
                    detail_dialog.setWindowModality(Qt.ApplicationModal)
                    
                    layout = QVBoxLayout()
                    
                    # スプリッターで左右分割
                    splitter = QSplitter(Qt.Horizontal)
                    
                    # 左側: 問い合わせ内容
                    left_container = QVBoxLayout()
                    left_label = QLabel("【問い合わせ内容】")
                    left_label.setStyleSheet("font-weight: bold; font-size: 12px;")
                    left_container.addWidget(left_label)
                    prompt_edit = QTextEdit()
                    prompt_edit.setPlainText(prompt_text)
                    prompt_edit.setReadOnly(True)
                    prompt_edit.setStyleSheet("QTextEdit { font-family: Courier; font-size: 11px; line-height: 1.5; }")
                    left_container.addWidget(prompt_edit)
                    
                    left_widget = QWidget()
                    left_widget.setLayout(left_container)
                    splitter.addWidget(left_widget)
                    
                    # 右側: レスポンス
                    right_container = QVBoxLayout()
                    right_label = QLabel("【AI レスポンス】")
                    right_label.setStyleSheet("font-weight: bold; font-size: 12px;")
                    right_container.addWidget(right_label)
                    response_edit = QTextEdit()
                    response_edit.setPlainText(response_text)
                    response_edit.setReadOnly(True)
                    response_edit.setStyleSheet("QTextEdit { font-family: Courier; font-size: 11px; line-height: 1.5; }")
                    right_container.addWidget(response_edit)
                    
                    right_widget = QWidget()
                    right_widget.setLayout(right_container)
                    splitter.addWidget(right_widget)
                    
                    splitter.setStretchFactor(0, 1)
                    splitter.setStretchFactor(1, 1)
                    layout.addWidget(splitter)
                    
                    # 閉じるボタン
                    close_btn = QPushButton("閉じる")
                    close_btn.clicked.connect(detail_dialog.close)
                    layout.addWidget(close_btn)
                    
                    detail_dialog.setLayout(layout)

                    if parent_dialog is not None:
                        parent_dialog.setEnabled(False)

                        def restore_parent():
                            parent_dialog.setEnabled(True)
                            parent_dialog.activateWindow()
                        detail_dialog.finished.connect(restore_parent)
                    
                    detail_dialog.exec()
                
                def on_check_success(result):
                    """チェック完了"""
                    response_text = result.get('response', '')

                    # ログ保存（結果一覧タブで参照できるようにする）
                    try:
                        from classes.dataset.util.ai_suggest_result_log import append_result

                        append_result(
                            target_kind='dataset',
                            target_key=str(dataset_id or '').strip() or str(selected_dataset.get('attributes', {}).get('grantNumber', '') or '').strip() or 'unknown',
                            button_id='ai_check',
                            button_label='AI CHECK',
                            prompt=prompt,
                            display_format='text',
                            display_content=str(response_text or ''),
                            provider=(result.get('provider') if isinstance(result, dict) else None),
                            model=(result.get('model') if isinstance(result, dict) else None),
                            request_params=(result.get('request_params') if isinstance(result, dict) else None),
                            response_params=(result.get('response_params') if isinstance(result, dict) else None),
                            started_at=(result.get('started_at') if isinstance(result, dict) else None),
                            finished_at=(result.get('finished_at') if isinstance(result, dict) else None),
                            elapsed_seconds=(result.get('elapsed_seconds') if isinstance(result, dict) else None),
                        )
                    except Exception:
                        pass
                    
                    # JSON検証・修正
                    try:
                        import json
                        # JSON抽出（「```json」などの囲みがあれば除去）
                        json_str = response_text
                        if '```json' in json_str:
                            json_str = json_str.split('```json')[1].split('```')[0].strip()
                        elif '```' in json_str:
                            json_str = json_str.split('```')[1].split('```')[0].strip()
                        
                        # JSONパース検証
                        check_result = json.loads(json_str)
                        
                        # 情報抽出
                        score = check_result.get('score', 'N/A')
                        judge = check_result.get('judge', '判定不能')
                        reason = check_result.get('reason', '理由なし')
                        char_count = check_result.get('char_count', 'N/A')
                        judge_comment = check_result.get('judge_comment', '')
                        
                        # 見やすいカスタムダイアログを作成
                        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
                        from PySide6.QtGui import QFont
                        from PySide6.QtCore import Qt
                        
                        result_dialog = QDialog(widget)
                        result_dialog.setWindowTitle("AI チェック結果")
                        result_dialog.setGeometry(200, 200, 700, 600)
                        result_dialog.setModal(True)
                        
                        main_layout = QVBoxLayout()
                        
                        # ============ ヘッダ: 評価概要 ============
                        header_layout = QHBoxLayout()
                        
                        # スコア表示
                        score_label = QLabel(f"スコア")
                        score_label.setStyleSheet("font-weight: bold; font-size: 13px;")
                        score_value = QLabel(f"{score}/10")
                        try:
                            score_num = float(score)
                        except Exception:
                            score_num = None

                        if score_num is not None and score_num >= 8:
                            score_color = get_color(ThemeKey.TEXT_SUCCESS)
                        elif score_num is not None and 6 <= score_num < 8:
                            score_color = get_color(ThemeKey.TEXT_WARNING)
                        else:
                            score_color = get_color(ThemeKey.TEXT_ERROR)
                        score_value.setStyleSheet(
                            f"font-size: 24px; font-weight: bold; color: {score_color};"
                        )
                        header_layout.addWidget(score_label)
                        header_layout.addWidget(score_value)
                        header_layout.addSpacing(20)
                        
                        # 文字数表示
                        char_label = QLabel(f"文字数")
                        char_label.setStyleSheet("font-weight: bold; font-size: 13px;")
                        char_value = QLabel(f"{char_count}字")
                        char_value.setStyleSheet("font-size: 20px; font-weight: bold;")
                        header_layout.addWidget(char_label)
                        header_layout.addWidget(char_value)
                        header_layout.addStretch()
                        
                        main_layout.addLayout(header_layout)
                        main_layout.addSpacing(10)
                        
                        # ============ 判定結果 ============
                        judge_header = QLabel("【判定結果】")
                        judge_header.setStyleSheet("font-weight: bold; font-size: 13px;")
                        main_layout.addWidget(judge_header)
                        
                        judge_value = QLabel(judge)
                        if judge in ['合格', '微修正推奨（合格）']:
                            judge_color = get_color(ThemeKey.TEXT_SUCCESS)
                        elif judge in ['要修正（不合格）', '判定不能（不合格）']:
                            judge_color = get_color(ThemeKey.TEXT_ERROR)
                        else:
                            judge_color = get_color(ThemeKey.TEXT_WARNING)
                        judge_value.setStyleSheet(
                            f"font-size: 18px; font-weight: bold; color: {judge_color}; padding: 10px; "
                            f"background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)}; "
                            f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; border-radius: 4px;"
                        )
                        main_layout.addWidget(judge_value)
                        main_layout.addSpacing(10)
                        
                        # ============ 判定コメント ============
                        if judge_comment:
                            comment_header = QLabel("【判定コメント】")
                            comment_header.setStyleSheet("font-weight: bold; font-size: 12px;")
                            main_layout.addWidget(comment_header)
                            
                            comment_text = QTextEdit()
                            comment_text.setPlainText(judge_comment)
                            comment_text.setReadOnly(True)
                            comment_text.setMaximumHeight(120)
                            comment_text.setStyleSheet("QTextEdit { font-size: 11px; line-height: 1.5; }")
                            main_layout.addWidget(comment_text)
                            main_layout.addSpacing(10)
                        
                        # ============ 評価理由 ============
                        reason_header = QLabel("【評価理由】")
                        reason_header.setStyleSheet("font-weight: bold; font-size: 12px;")
                        main_layout.addWidget(reason_header)
                        
                        reason_text = QTextEdit()
                        reason_text.setPlainText(reason)
                        reason_text.setReadOnly(True)
                        reason_text.setStyleSheet("QTextEdit { font-size: 11px; line-height: 1.5; }")
                        main_layout.addWidget(reason_text)
                        main_layout.addSpacing(10)
                        
                        # ============ ボタン ============
                        button_layout = QHBoxLayout()
                        
                        detail_btn = QPushButton("詳細を表示")
                        detail_btn.setMinimumWidth(100)
                        detail_btn.setMinimumHeight(36)
                        detail_btn.setStyleSheet("QPushButton { font-size: 12px; }")
                        detail_btn.clicked.connect(lambda: _show_ai_check_details(prompt, response_text, result_dialog))
                        button_layout.addWidget(detail_btn)
                        
                        button_layout.addStretch()
                        
                        ok_btn = QPushButton("閉じる")
                        ok_btn.setMinimumWidth(80)
                        ok_btn.setMinimumHeight(36)
                        ok_btn.setStyleSheet("QPushButton { font-size: 12px; }")
                        ok_btn.clicked.connect(result_dialog.close)
                        button_layout.addWidget(ok_btn)
                        
                        main_layout.addLayout(button_layout)
                        
                        result_dialog.setLayout(main_layout)
                        result_dialog.exec()
                        
                        logger.info("AI CHECKボタン: チェック完了, verdict=%s, score=%s", judge, score)
                        
                    except json.JSONDecodeError as json_err:
                        logger.error("JSON解析エラー: %s", json_err)
                        error_msg = f"AI応答のJSON解析に失敗しました\n{str(json_err)}\n\nレスポンス内容:\n{response_text[:500]}"
                        
                        msg_box = QMessageBox(widget)
                        msg_box.setWindowTitle("エラー")
                        msg_box.setText(error_msg)
                        msg_box.setIcon(QMessageBox.Critical)
                        
                        detail_btn = msg_box.addButton("レスポンスを表示", QMessageBox.ActionRole)
                        ok_btn = msg_box.addButton(QMessageBox.Ok)
                        msg_box.setDefaultButton(ok_btn)
                        msg_box.exec()
                        
                        if msg_box.clickedButton() == detail_btn:
                            _show_ai_check_details(prompt, response_text)
                    finally:
                        ai_check_button.stop_loading()
                        # スレッド参照をクリア
                        widget._ai_check_thread = None
                
                def on_check_error(error_msg):
                    """エラー処理"""
                    logger.error("AI CHECKボタン: エラー = %s", error_msg)
                    QMessageBox.critical(widget, "AIエラー", f"品質チェック実行中にエラーが発生しました\n{error_msg}")
                    ai_check_button.stop_loading()
                    # スレッド参照をクリア
                    widget._ai_check_thread = None
                
                # AIスレッド実行 - widget に参照を保持
                ai_thread = AIRequestThread(prompt, full_context)
                widget._ai_check_thread = ai_thread  # スレッド参照を保持
                ai_thread.result_ready.connect(on_check_success)
                ai_thread.error_occurred.connect(on_check_error)
                ai_thread.start()
                
            except Exception as e:
                logger.error("AI CHECKボタン: 予期しないエラー = %s", e)
                QMessageBox.critical(widget, "エラー", f"予期しないエラーが発生しました\n{str(e)}")
                ai_check_button.stop_loading()
        
        ai_check_button.clicked.connect(check_description_quality)
        
        # ボタンレイアウトをウィジェット化
        ai_buttons_widget = QWidget()
        ai_buttons_widget.setLayout(ai_buttons_layout)
        description_layout.addWidget(ai_buttons_widget)
        
        # 水平レイアウトを含むウィジェットを作成
        description_widget = QWidget()
        description_widget.setLayout(description_layout)
        form_layout.addWidget(description_widget, 2, 1)
        
        # エンバーゴ期間終了日
        form_layout.addWidget(QLabel("エンバーゴ期間終了日:"), 3, 0)
        edit_embargo_edit = QDateEdit()
        edit_embargo_edit.setDisplayFormat("yyyy-MM-dd")
        edit_embargo_edit.setCalendarPopup(True)
        edit_embargo_edit.setFixedWidth(140)
        # デフォルトを翌年度末日に設定
        today = datetime.date.today()
        next_year = today.year + 1
        embargo_date = QDate(next_year, 3, 31)
        edit_embargo_edit.setDate(embargo_date)
        form_layout.addWidget(edit_embargo_edit, 3, 1)
        
        # データセットテンプレート（表示のみ）
        form_layout.addWidget(QLabel("データセットテンプレート:"), 4, 0)
        edit_template_display = QLineEdit()
        edit_template_display.setPlaceholderText("データセットテンプレート名（表示のみ）")
        edit_template_display.setReadOnly(True)
        # 読み取り専用視覚表示: 未定義キー INPUT_BACKGROUND_READONLY -> 既存 INPUT_BACKGROUND_DISABLED へ置換
        # edit_template_display.setStyleSheet(f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.TEXT_MUTED)};")
        form_layout.addWidget(edit_template_display, 4, 1)
        
        # 申請者（表示のみ）
        applicant_label = QLabel("申請者:")
        edit_applicant_display = QLineEdit()
        edit_applicant_display.setPlaceholderText("申請者（表示のみ）")
        edit_applicant_display.setReadOnly(True)
        edit_applicant_display.setStyleSheet(
            f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.TEXT_MUTED)};"
        )
        edit_applicant_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form_layout.addWidget(applicant_label, 5, 0)
        form_layout.addWidget(edit_applicant_display, 5, 1)

        # データセット管理者（変更可）
        manager_label = QLabel("管理者:")
        edit_manager_combo = QComboBox()
        edit_manager_combo.setEditable(True)
        edit_manager_combo.setInsertPolicy(QComboBox.NoInsert)
        if edit_manager_combo.lineEdit():
            edit_manager_combo.lineEdit().setPlaceholderText("グループメンバーから選択")
        edit_manager_combo.setEnabled(False)
        edit_manager_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        try:
            edit_manager_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            edit_manager_combo.setMinimumContentsLength(24)
            edit_manager_combo.view().setTextElideMode(Qt.ElideRight)
        except Exception:
            logger.debug("管理者コンボの表示調整に失敗", exc_info=True)
        form_layout.addWidget(manager_label, 6, 0)
        form_layout.addWidget(edit_manager_combo, 6, 1)
        
        # タクソノミーキー（ビルダーダイアログ使用）
        taxonomy_layout = QHBoxLayout()
        taxonomy_layout.setContentsMargins(0, 0, 0, 0)
        taxonomy_layout.setSpacing(6)
        edit_taxonomy_edit = QLineEdit()
        edit_taxonomy_edit.setPlaceholderText("タクソノミーキー（設定ボタンで編集）")
        edit_taxonomy_edit.setReadOnly(True)  # 読み取り専用

        taxonomy_builder_button = QPushButton("設定...")
        taxonomy_builder_button.setMaximumWidth(90)

        taxonomy_layout.addWidget(edit_taxonomy_edit)
        taxonomy_layout.addWidget(taxonomy_builder_button)

        taxonomy_widget = QWidget()
        taxonomy_widget.setLayout(taxonomy_layout)

        # 問い合わせ先
        edit_contact_edit = QLineEdit()
        edit_contact_edit.setPlaceholderText("問い合わせ先を入力")
        edit_contact_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit_contact_edit.setFixedHeight(26)
        form_layout.addWidget(QLabel("問い合わせ先:"), 7, 0)
        form_layout.addWidget(edit_contact_edit, 7, 1)

        # タクソノミーキー（ビルダーダイアログ使用）
        taxonomy_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form_layout.addWidget(QLabel("タクソノミーキー:"), 8, 0)
        form_layout.addWidget(taxonomy_widget, 8, 1)
        
        # タクソノミービルダーボタンのイベントハンドラー
        def open_taxonomy_builder():
            """タクソノミービルダーダイアログを開く"""
            try:
                # 現在選択されているデータセットからテンプレートIDを取得
                template_id = getattr(widget, 'current_template_id', '')
                
                current_taxonomy = edit_taxonomy_edit.text().strip()
                
                dialog = TaxonomyBuilderDialog(
                    parent=widget,
                    current_taxonomy=current_taxonomy,
                    dataset_template_id=template_id
                )
                
                # タクソノミー変更シグナルに接続
                dialog.taxonomy_changed.connect(
                    lambda taxonomy: edit_taxonomy_edit.setText(taxonomy)
                )
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.warning(widget, "エラー", f"タクソノミービルダーの起動に失敗しました:\n{e}")
        
        taxonomy_builder_button.clicked.connect(open_taxonomy_builder)
        
        # 関連情報（旧：関連リンク）- ビルダーダイアログ使用
        form_layout.addWidget(QLabel("関連情報:"), 9, 0)
        related_links_layout = QHBoxLayout()
        related_links_layout.setContentsMargins(0, 2, 0, 2)
        related_links_layout.setSpacing(8)
        edit_related_links_edit = QLineEdit()
        edit_related_links_edit.setPlaceholderText("関連情報を入力（タイトル1:URL1,タイトル2:URL2 の形式、設定ボタンでも編集可能）")
        
        related_links_builder_button = QPushButton("設定...")
        related_links_builder_button.setMaximumWidth(80)
        
        related_links_layout.addWidget(edit_related_links_edit)
        related_links_layout.addWidget(related_links_builder_button)
        
        # レイアウトをWidgetでラップしてGridLayoutに追加
        related_links_widget = QWidget()
        related_links_widget.setLayout(related_links_layout)
        form_layout.addWidget(related_links_widget, 9, 1)
        
        # TAGフィールド（ビルダーダイアログ使用）
        form_layout.addWidget(QLabel("TAG:"), 10, 0)
        tag_layout = QHBoxLayout()
        tag_layout.setContentsMargins(0, 2, 0, 2)
        tag_layout.setSpacing(8)
        edit_tags_edit = QLineEdit()
        edit_tags_edit.setPlaceholderText("TAGを入力（カンマ区切り、設定ボタンでも編集可能）")
        
        tag_builder_button = QPushButton("設定...")
        tag_builder_button.setMaximumWidth(80)
        
        tag_layout.addWidget(edit_tags_edit)
        tag_layout.addWidget(tag_builder_button)
        
        # レイアウトをWidgetでラップしてGridLayoutに追加
        tag_widget = QWidget()
        tag_widget.setLayout(tag_layout)
        form_layout.addWidget(tag_widget, 10, 1)
        
        # TAGビルダーボタンのイベントハンドラー
        def open_tag_builder():
            """TAGビルダーダイアログを開く"""
            try:
                from classes.dataset.ui.tag_builder_dialog import TagBuilderDialog
                
                current_tags = edit_tags_edit.text().strip()

                # 現在選択されているデータセット情報（AI提案タブ用）
                selected_dataset_id = None
                dataset_context = {}
                try:
                    current_index = existing_dataset_combo.currentIndex()
                    if current_index > 0:
                        selected_dataset = existing_dataset_combo.itemData(current_index)
                        if isinstance(selected_dataset, dict):
                            selected_dataset_id = selected_dataset.get("id")
                            attrs = selected_dataset.get("attributes", {})
                            if isinstance(attrs, dict):
                                dataset_context = {
                                    "name": attrs.get("name", ""),
                                    "type": attrs.get("type") or attrs.get("datasetType") or "",
                                    "grant_number": attrs.get("grantNumber", ""),
                                    "description": attrs.get("description", ""),
                                }
                except Exception:
                    dataset_context = {}
                
                dialog = TagBuilderDialog(
                    parent=widget,
                    current_tags=current_tags,
                    dataset_id=selected_dataset_id,
                    dataset_context=dataset_context,
                )
                
                # TAG変更シグナルに接続
                dialog.tags_changed.connect(
                    lambda tags: edit_tags_edit.setText(tags)
                )
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.warning(widget, "エラー", f"TAGビルダーの起動に失敗しました:\n{e}")
        
        tag_builder_button.clicked.connect(open_tag_builder)
        
        # 関連データセットビルダーボタンのイベントハンドラー
        def open_related_datasets_builder():
            """関連データセットビルダーダイアログを開く"""
            try:
                from classes.dataset.ui.related_datasets_builder_dialog import RelatedDatasetsBuilderDialog
                
                # 現在選択されているデータセットIDを取得
                current_dataset_id = None
                current_grant_number = None
                current_index = existing_dataset_combo.currentIndex()
                if current_index > 0:
                    selected_dataset = existing_dataset_combo.itemData(current_index)
                    if selected_dataset:
                        current_dataset_id = selected_dataset.get("id")
                        current_grant_number = selected_dataset.get("attributes", {}).get("grantNumber")
                
                # 現在の関連データセットIDリスト
                current_dataset_ids = getattr(widget, '_selected_related_dataset_ids', [])
                
                dialog = RelatedDatasetsBuilderDialog(
                    parent=widget,
                    current_dataset_ids=current_dataset_ids,
                    exclude_dataset_id=current_dataset_id,
                    current_grant_number=current_grant_number
                )
                
                # 関連データセット変更シグナルに接続
                def on_datasets_changed(dataset_ids):
                    widget._selected_related_dataset_ids = dataset_ids
                    count = len(dataset_ids)
                    edit_related_datasets_display.setText(f"{count}件")
                    logger.debug("関連データセット更新: %s件", count)
                
                dialog.datasets_changed.connect(on_datasets_changed)
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.warning(widget, "エラー", f"関連データセットビルダーの起動に失敗しました:\n{e}")
        
        # 関連情報ビルダーボタンのイベントハンドラー
        def open_related_links_builder():
            """関連情報ビルダーダイアログを開く"""
            try:
                from classes.dataset.ui.related_links_builder_dialog import RelatedLinksBuilderDialog
                
                current_links = edit_related_links_edit.text().strip()
                
                dialog = RelatedLinksBuilderDialog(
                    parent=widget,
                    current_links=current_links
                )
                
                # 関連情報変更シグナルに接続
                dialog.links_changed.connect(
                    lambda links: edit_related_links_edit.setText(links)
                )
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.warning(widget, "エラー", f"関連情報ビルダーの起動に失敗しました:\n{e}")
        
        related_links_builder_button.clicked.connect(open_related_links_builder)
        
        # データセット引用の書式
        edit_citation_format_edit = QLineEdit()
        edit_citation_format_edit.setPlaceholderText("データセット引用の書式を入力")
        edit_citation_format_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit_citation_format_edit.textChanged.connect(lambda text: edit_citation_format_edit.setToolTip(text))

        # 利用ライセンス選択
        edit_license_combo = QComboBox()
        edit_license_combo.setEditable(True)
        edit_license_combo.setInsertPolicy(QComboBox.NoInsert)
        edit_license_combo.lineEdit().setPlaceholderText("ライセンスを選択または検索")
        edit_license_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        try:
            edit_license_combo.view().setTextElideMode(Qt.ElideRight)
        except Exception:
            logger.debug("ライセンスコンボのElide設定に失敗", exc_info=True)
        
        # ライセンスデータをlicenses.jsonから読み込み
        license_data = []
        try:
            from config.common import LICENSES_JSON_PATH
            if os.path.exists(LICENSES_JSON_PATH):
                with open(LICENSES_JSON_PATH, 'r', encoding='utf-8') as f:
                    licenses_json = json.load(f)
                    license_data = licenses_json.get("data", [])
                logger.info("licenses.jsonから%s件のライセンス情報を読み込みました", len(license_data))
            else:
                logger.warning("licenses.jsonが見つかりません: %s", LICENSES_JSON_PATH)
        except Exception as e:
            logger.error("licenses.json読み込みエラー: %s", e)
        
        # フォールバック用のデフォルトライセンスリスト
        if not license_data:
            logger.info("デフォルトライセンスリストを使用します")
            license_data = [
                {"id": "CC0-1.0", "fullName": "Creative Commons Zero v1.0 Universal"},
                {"id": "CC-BY-4.0", "fullName": "Creative Commons Attribution 4.0 International"},
                {"id": "CC-BY-SA-4.0", "fullName": "Creative Commons Attribution Share Alike 4.0 International"},
                {"id": "CC-BY-NC-4.0", "fullName": "Creative Commons Attribution Non Commercial 4.0 International"},
                {"id": "CC-BY-NC-SA-4.0", "fullName": "Creative Commons Attribution Non Commercial Share Alike 4.0 International"},
                {"id": "CC-BY-ND-4.0", "fullName": "Creative Commons Attribution No Derivatives 4.0 International"},
                {"id": "CC-BY-NC-ND-4.0", "fullName": "Creative Commons Attribution Non Commercial No Derivatives 4.0 International"},
                {"id": "MIT", "fullName": "MIT License"},
                {"id": "Apache-2.0", "fullName": "Apache License 2.0"},
                {"id": "GPL-3.0-only", "fullName": "GNU General Public License v3.0 only"},
                {"id": "BSD-3-Clause", "fullName": "BSD 3-Clause \"New\" or \"Revised\" License"},
                {"id": "MPL-2.0", "fullName": "Mozilla Public License 2.0"},
                {"id": "Unlicense", "fullName": "The Unlicense"},
                {"id": "ISC", "fullName": "ISC License"},
                {"id": "LGPL-3.0-only", "fullName": "GNU Lesser General Public License v3.0 only"},
            ]
        
        # ライセンス選択肢を追加
        for license_item in license_data:
            license_id = license_item.get("id", "")
            attributes = license_item.get("attributes", {})
            # fullNameまたはnameフィールドを使用
            license_name = attributes.get("fullName") or attributes.get("name", "")
            if license_id and license_name:
                display_text = f"{license_id} - {license_name}"
                edit_license_combo.addItem(display_text, license_id)
        
        edit_license_combo.setCurrentIndex(-1)  # 初期選択なし
        
        # 自動補完機能を追加
        license_display_texts = []
        for item in license_data:
            license_id = item.get("id", "")
            attributes = item.get("attributes", {})
            license_name = attributes.get("fullName") or attributes.get("name", "")
            if license_id and license_name:
                license_display_texts.append(f"{license_id} - {license_name}")
        
        license_completer = QCompleter(license_display_texts, edit_license_combo)
        license_completer.setCaseSensitivity(Qt.CaseInsensitive)
        license_completer.setFilterMode(Qt.MatchContains)
        edit_license_combo.setCompleter(license_completer)

        form_layout.addWidget(QLabel("データセット引用の書式:"), 11, 0)
        form_layout.addWidget(edit_citation_format_edit, 11, 1)
        form_layout.addWidget(QLabel("利用ライセンス:"), 12, 0)
        form_layout.addWidget(edit_license_combo, 12, 1)
        
        # 関連データセット - ビルダーダイアログ使用
        form_layout.addWidget(QLabel("関連データセット:"), 13, 0)
        related_datasets_layout = QHBoxLayout()
        edit_related_datasets_display = QLineEdit()
        edit_related_datasets_display.setReadOnly(True)
        edit_related_datasets_display.setPlaceholderText("関連データセット（設定ボタンで編集）")
        edit_related_datasets_display.setStyleSheet(f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.TEXT_MUTED)};")
        
        related_datasets_builder_button = QPushButton("設定...")
        related_datasets_builder_button.setMaximumWidth(80)
        related_datasets_builder_button.clicked.connect(open_related_datasets_builder)
        
        related_datasets_layout.addWidget(edit_related_datasets_display)
        related_datasets_layout.addWidget(related_datasets_builder_button)
        
        # レイアウトをWidgetでラップしてGridLayoutに追加
        related_datasets_widget = QWidget()
        related_datasets_widget.setLayout(related_datasets_layout)
        form_layout.addWidget(related_datasets_widget, 13, 1)
        
        # 内部データ保持用（IDリスト）
        widget._selected_related_dataset_ids = []
        
        # データ一覧表示タイプ選択（ラジオボタン）- 関連データセットの下に移動
        form_layout.addWidget(QLabel("データ一覧表示タイプ:"), 14, 0)
        data_listing_type_widget = QWidget()
        data_listing_type_layout = QHBoxLayout()
        data_listing_type_layout.setContentsMargins(0, 0, 0, 0)
        
        edit_data_listing_gallery_radio = QRadioButton("ギャラリー表示")
        edit_data_listing_tree_radio = QRadioButton("ツリー表示")
        edit_data_listing_gallery_radio.setChecked(True)  # デフォルトはギャラリー表示
        
        data_listing_type_layout.addWidget(edit_data_listing_gallery_radio)
        data_listing_type_layout.addWidget(edit_data_listing_tree_radio)
        data_listing_type_layout.addStretch()  # 右側にスペースを追加
        
        data_listing_type_widget.setLayout(data_listing_type_layout)
        form_layout.addWidget(data_listing_type_widget, 14, 1)
        
        # チェックボックス（横並び1行）
        checkbox_widget = QWidget()
        checkbox_layout = QHBoxLayout()
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setSpacing(12)

        edit_anonymize_checkbox = QCheckBox("データセットを匿名にする")
        # 既存互換: 個別の『データ登録を禁止する』チェックボックスも生成（非表示行）
        edit_data_entry_prohibited_checkbox = QCheckBox("データ登録を禁止する")
        edit_data_entry_delete_prohibited_checkbox = QCheckBox("データの登録及び削除を禁止する")
        edit_share_core_scope_checkbox = QCheckBox("データ中核拠点広域シェア（RDE全体での共有）を有効にする")

        checkbox_layout.addWidget(edit_anonymize_checkbox)
        # 横並び3つの指定に合わせ、『データ登録を禁止する』を採用
        checkbox_layout.addWidget(edit_data_entry_prohibited_checkbox)
        checkbox_layout.addWidget(edit_share_core_scope_checkbox)

        checkbox_widget.setLayout(checkbox_layout)

        form_layout.addWidget(QLabel("共有範囲/利用制限:"), 15, 0)
        form_layout.addWidget(checkbox_widget, 15, 1)
        
        form_widget.setLayout(form_layout)
        
        # フォーム内のウィジェットを返す
        return (
            form_widget,
            edit_dataset_name_edit,
            edit_grant_number_combo,
            edit_description_edit,
            edit_embargo_edit,
            edit_contact_edit,
            edit_taxonomy_edit,
            edit_related_links_edit,
            edit_tags_edit,
            edit_citation_format_edit,
            edit_license_combo,
            edit_data_listing_gallery_radio,
            edit_data_listing_tree_radio,
            edit_related_datasets_display,
            edit_anonymize_checkbox,
            edit_data_entry_prohibited_checkbox,
            edit_data_entry_delete_prohibited_checkbox,
            edit_share_core_scope_checkbox,
            edit_template_display,
            edit_manager_combo,
            edit_applicant_display,
        )
    
    # 編集フォームを作成
    (
        edit_form_widget,
        edit_dataset_name_edit,
        edit_grant_number_combo,
        edit_description_edit,
        edit_embargo_edit,
        edit_contact_edit,
        edit_taxonomy_edit,
        edit_related_links_edit,
        edit_tags_edit,
        edit_citation_format_edit,
        edit_license_combo,
        edit_data_listing_gallery_radio,
        edit_data_listing_tree_radio,
        edit_related_datasets_display,
        edit_anonymize_checkbox,
        edit_data_entry_prohibited_checkbox,
        edit_data_entry_delete_prohibited_checkbox,
        edit_share_core_scope_checkbox,
        edit_template_display,
        edit_manager_combo,
        edit_applicant_display,
    ) = create_edit_form()
    
    # 上: 既存フォーム / 下: データエントリー一覧 の縦スプリッターを追加
    manager_entries = []
    current_member_info = {}
    current_group_id = None
    dataset_user_info_map: dict[str, dict] = {}
    dataset_user_role_fallback: dict[str, str | None] = {"applicant": None, "manager": None}
    user_resolution_state = {"applicant": "missing", "manager": "missing"}
    update_permission_blocked = False
    current_applicant_id: str | None = None
    current_manager_id: str | None = None

    def _reset_manager_combo(placeholder: str = "グループメンバーから選択"):
        """管理者コンボの表示と内部状態を初期化する。"""
        nonlocal manager_entries, current_member_info, current_group_id
        manager_entries = []
        current_member_info = {}
        current_group_id = None
        try:
            edit_manager_combo.blockSignals(True)
            edit_manager_combo.clear()
            edit_manager_combo.setEnabled(False)
            edit_manager_combo.blockSignals(False)
        except Exception:
            logger.debug("管理者コンボのリセットに失敗", exc_info=True)
        if edit_manager_combo.lineEdit():
            edit_manager_combo.lineEdit().setPlaceholderText(placeholder)
        edit_manager_combo.setToolTip("")

    def _build_user_label_from_data(user_data: dict) -> str:
        """仕様: userName (organizationName) を表示する。"""
        return _format_user_label_user_org(user_data)

    def _format_user_display(user_id: str | None, fallback_text: str | None = None) -> tuple[str, str]:
        nonlocal dataset_user_info_map
        if not user_id:
            return "", "missing"
        user_data = current_member_info.get(user_id)
        if not user_data and current_group_id:
            try:
                from classes.subgroup.core import subgroup_api_helper
                detail_attr_map = subgroup_api_helper._load_detail_user_attributes(current_group_id)  # noqa: SLF001
                detail = detail_attr_map.get(user_id)
                if detail:
                    user_data = {
                        "id": user_id,
                        "userName": detail.get("userName", ""),
                        "emailAddress": detail.get("emailAddress", ""),
                        "familyName": detail.get("familyName", ""),
                        "givenName": detail.get("givenName", ""),
                        "familyNameKanji": detail.get("familyNameKanji", ""),
                        "givenNameKanji": detail.get("givenNameKanji", ""),
                        "organizationName": detail.get("organizationName", ""),
                    }
                    current_member_info[user_id] = user_data
            except Exception:
                logger.debug("詳細属性の補完に失敗", exc_info=True)

        label, source = _resolve_user_label_with_fallback(
            user_id,
            current_member_info,
            dataset_user_info_map,
            fallback_text=fallback_text,
        )
        return label, source

    def _populate_members_for_group(group_id: str | None):
        nonlocal current_member_info, current_group_id, manager_entries
        if current_group_id and group_id and group_id == current_group_id and manager_entries:
            return
        if not group_id:
            _reset_manager_combo("グループ未選択")
            return

        _reset_manager_combo("グループメンバーを取得中…")
        try:
            from classes.subgroup.core import subgroup_api_helper

            unified_users, member_info = subgroup_api_helper.load_unified_member_list(subgroup_id=group_id)

            # 仕様: subGroups/{id}.json または subGroupsAncestors/{id}.json の included(user) を選択肢にする
            # 既存ロジックは統合候補を広めに拾うため、詳細ファイルがある場合は included のユーザーIDに限定する
            try:
                detail_attr_map = subgroup_api_helper._load_detail_user_attributes(group_id)  # noqa: SLF001
                if isinstance(detail_attr_map, dict) and detail_attr_map:
                    allowed_ids = set(detail_attr_map.keys())
                    unified_users = [u for u in (unified_users or []) if str(u.get("id") or "") in allowed_ids]
                    member_info = {uid: info for uid, info in (member_info or {}).items() if uid in allowed_ids}
            except Exception:
                logger.debug("管理者候補の限定に失敗 (fallback to unified list)", exc_info=True)

            current_member_info = member_info or {}
        except Exception:
            logger.warning("グループメンバーの読み込みに失敗: %s", group_id, exc_info=True)
            _reset_manager_combo("メンバー情報を読み込めませんでした")
            return

        manager_entries = []
        try:
            edit_manager_combo.blockSignals(True)
            for user in unified_users or []:
                uid = str(user.get("id") or "")
                if not uid or user.get("isDeleted"):
                    continue
                label = _build_user_label_from_data(user)
                manager_entries.append((label, uid))
                edit_manager_combo.addItem(label, uid)
                email = user.get("emailAddress")
                if email:
                    try:
                        edit_manager_combo.setItemData(edit_manager_combo.count() - 1, email, Qt.ToolTipRole)
                    except Exception:
                        logger.debug("管理者コンボのToolTip設定に失敗", exc_info=True)
            edit_manager_combo.blockSignals(False)
        except Exception:
            logger.debug("管理者コンボの更新に失敗", exc_info=True)
            _reset_manager_combo("メンバー情報の更新に失敗しました")
            return

        if manager_entries:
            edit_manager_combo.setEnabled(True)
            if edit_manager_combo.lineEdit():
                edit_manager_combo.lineEdit().setPlaceholderText("データセット管理者を選択")
            try:
                manager_completer = QCompleter([label for label, _ in manager_entries], edit_manager_combo)
                manager_completer.setCaseSensitivity(Qt.CaseInsensitive)
                manager_completer.setFilterMode(Qt.MatchContains)
                edit_manager_combo.setCompleter(manager_completer)
                try:
                    edit_manager_combo.view().setTextElideMode(Qt.ElideRight)
                except Exception:
                    logger.debug("管理者コンボのElide設定に失敗", exc_info=True)
            except Exception:
                logger.debug("管理者コンボのCompleter設定に失敗", exc_info=True)
            current_group_id = group_id
        else:
            _reset_manager_combo("メンバー情報が見つかりません")

    def _set_applicant_display(user_id: str | None):
        nonlocal update_permission_blocked, current_applicant_id
        if not user_id:
            edit_applicant_display.clear()
            edit_applicant_display.setToolTip("")
            user_resolution_state["applicant"] = "missing"
            current_applicant_id = None
            return

        text, source = _format_user_display(
            user_id,
            fallback_text=dataset_user_role_fallback.get("applicant"),
        )
        user_resolution_state["applicant"] = source
        current_applicant_id = user_id

        edit_applicant_display.setText(text)
        tooltip_parts = [text]
        try:
            if current_member_info.get(user_id, {}).get("emailAddress"):
                tooltip_parts.append(current_member_info[user_id]["emailAddress"])
        except Exception:
            pass
        edit_applicant_display.setToolTip("\n".join([p for p in tooltip_parts if p]))

    def _apply_manager_selection(manager_id: str | None):
        nonlocal update_permission_blocked, current_manager_id
        if manager_id:
            idx = -1
            for i, (_label, uid) in enumerate(manager_entries):
                if uid == manager_id:
                    idx = i
                    user_resolution_state["manager"] = "member"
                    break
            if idx < 0:
                fallback_label, source = _format_user_display(
                    manager_id,
                    fallback_text=dataset_user_role_fallback.get("manager"),
                )
                user_resolution_state["manager"] = source
                manager_entries.append((fallback_label, manager_id))
                edit_manager_combo.addItem(fallback_label, manager_id)
                try:
                    edit_manager_combo.setItemData(edit_manager_combo.count() - 1, manager_id, Qt.ToolTipRole)
                except Exception:
                    logger.debug("管理者コンボのToolTip設定に失敗", exc_info=True)
                idx = edit_manager_combo.count() - 1
            current_manager_id = manager_id
            edit_manager_combo.setCurrentIndex(idx)
        else:
            user_resolution_state["manager"] = "missing"
            current_manager_id = None
            try:
                edit_manager_combo.setCurrentIndex(-1)
            except Exception:
                logger.debug("管理者コンボの選択クリアに失敗", exc_info=True)

    def _recompute_update_permission_block(applicant_id: str | None = None, manager_id: str | None = None):
        nonlocal update_permission_blocked, current_applicant_id, current_manager_id
        if applicant_id is not None:
            current_applicant_id = applicant_id
        if manager_id is not None:
            current_manager_id = manager_id

        blocked = _should_block_update_for_users(
            current_applicant_id,
            user_resolution_state.get("applicant", "missing"),
            current_manager_id,
            user_resolution_state.get("manager", "missing"),
        )

        if blocked and update_override_state.get("enabled"):
            update_override_state["enabled"] = False

        if blocked != update_permission_blocked:
            update_permission_blocked = blocked
        refresh_update_controls()

    def _extract_user_id(rel_data: dict | None) -> str:
        if not rel_data:
            return ""
        data = rel_data.get("data") if isinstance(rel_data, dict) else None
        if isinstance(data, dict):
            return str(data.get("id") or "")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                return str(first.get("id") or "")
        return ""

    content_splitter = QSplitter(Qt.Vertical)
    content_splitter.setChildrenCollapsible(False)
    content_splitter.addWidget(edit_form_widget)

    # データエントリー一覧パネル
    entries_panel = QWidget()
    entries_panel_layout = QVBoxLayout()
    entries_panel_layout.setContentsMargins(0, 0, 0, 0)
    entries_title = QLabel("データエントリー一覧（選択データセット）")
    entries_title.setStyleSheet("font-weight: bold;")
    entries_panel_layout.addWidget(entries_title)

    # データエントリー一覧の上に操作ボタンを表示
    entries_button_layout = QHBoxLayout()
    entries_button_layout.setContentsMargins(0, 0, 0, 0)

    open_dataset_page_button = create_auto_resize_button(
        "RDEデータセットページを開く", 200, 40,
        f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; border-radius: 6px; border:1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};"
    )
    try:
        open_dataset_page_button.setObjectName("dataset_open_page_button")
    except Exception:
        pass
    entries_button_layout.addWidget(open_dataset_page_button)

    update_button = create_auto_resize_button(
        "データセット更新", 200, 40,
        f"background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)}; font-weight: bold; border-radius: 6px; border:1px solid {get_color(ThemeKey.BUTTON_WARNING_BORDER)};"
    )
    try:
        update_button.setObjectName("dataset_update_button")
    except Exception:
        pass
    entries_button_layout.addWidget(update_button)
    entries_button_layout.addStretch()
    entries_panel_layout.addLayout(entries_button_layout)

    entries_table = QTableWidget()
    # 列拡張: 登録状況開始日時とリンク列を追加 (複数候補は行分割表示)
    entries_table.setColumnCount(6)
    entries_table.setHorizontalHeaderLabels(["データエントリーID", "名称", "登録状況ID", "登録状況ステータス", "登録開始日時", "リンク"])
    entries_header = entries_table.horizontalHeader()
    entries_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    entries_header.setSectionResizeMode(1, QHeaderView.Stretch)
    entries_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    entries_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
    entries_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
    entries_header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
    entries_table.setSortingEnabled(True)
    entries_table.setEditTriggers(QTableWidget.NoEditTriggers)

    # 外側（タブ全体）のスクロールに集約するため、内側スクロールバーは表示しない
    try:
        entries_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        entries_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        entries_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        entries_table.setObjectName("dataset_dataentry_table")
    except Exception:
        pass
    entries_panel_layout.addWidget(entries_table)
    entries_panel.setLayout(entries_panel_layout)

    content_splitter.addWidget(entries_panel)
    content_splitter.setStretchFactor(0, 1)
    content_splitter.setStretchFactor(1, 1)

    # スプリッターをメインレイアウトに追加
    layout.addWidget(content_splitter)

    # 参照をウィジェットに保持
    widget._entries_table = entries_table

    def _load_registration_entries():
        """登録状況キャッシュ (entries_all / entries_latest) から生データリストを読み取る"""
        entries = []
        try:
            candidates = [
                get_dynamic_file_path('output/rde/entries_all.json'),
                get_dynamic_file_path('output/rde/entries_latest.json'),
            ]
            for p in candidates:
                if p and os.path.exists(p):
                    try:
                        with open(p, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if isinstance(data, list) and data:
                            entries.extend(data)
                            # entries_all があればそれを優先し終了
                            if 'entries_all' in p:
                                break
                    except Exception as ie:
                        logger.debug("登録状況キャッシュ読み込み失敗: %s", ie)
        except Exception as e:
            logger.debug("登録状況エントリー読み込み失敗: %s", e)
        return entries

    def _match_registration_for_entry(dataset_name: str, data_name: str, owner_id: str, instrument_id: str | None,
                                      created_ts: str | None, registration_entries: list, threshold_seconds: int = 86400):
        """単一データエントリーに対応する登録状況候補を抽出 (24h以内 / 複合キー一致)
        条件:
          - datasetName 完全一致 (選択データセットの name)
          - dataName 完全一致 (エントリー attributes.name)
          - createdByUserId 一致 (エントリー owner.id)
          - (instrumentId が両方に存在する場合は一致)
          - startTime と created の絶対差が threshold_seconds 以内 (両方取れた場合)
        """
        import datetime as _dt
        results = []
        # created_ts を datetime へ
        created_dt = None
        if created_ts:
            try:
                created_dt = _dt.datetime.fromisoformat(created_ts.replace('Z', '+00:00'))
            except Exception:
                created_dt = None

        for r in registration_entries:
            try:
                if r.get('datasetName') != dataset_name:
                    continue
                if r.get('dataName') != data_name:
                    continue
                if r.get('createdByUserId') != owner_id:
                    continue
                if instrument_id and r.get('instrumentId') and r.get('instrumentId') != instrument_id:
                    continue
                # 時刻差判定
                if created_dt:
                    start_time = r.get('startTime')
                    if start_time:
                        try:
                            start_dt = _dt.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                            if abs((start_dt - created_dt).total_seconds()) > threshold_seconds:
                                continue
                        except Exception:
                            # パース失敗時は時刻条件無視 (緩く)
                            pass
                results.append(r)
            except Exception as ie:
                logger.debug("マッチング判定中エラー: %s", ie)
        return results

    def update_entries_table_for_dataset(dataset_id: str, dataset_name: str | None, force_refresh: bool = False):
        """選択データセットのエントリー一覧をテーブルへ反映 (登録状況ID相関付き・複数候補行分割)

        行生成ルール:
          - マッチ0件: 1行 (登録状況ID/ステータス空, リンク列はボタン無効)
          - マッチ1件: 1行 (登録状況ID/ステータス/リンクボタン有効)
          - マッチ複数: マッチ件数分の行 (各行に個別ID/ステータス/リンク)
        """
        try:
            entries_table.setRowCount(0)
            if not dataset_id:
                try:
                    header_h = entries_table.horizontalHeader().height() if entries_table.horizontalHeader() else 25
                    target_h = max(120, int(header_h + 6))
                    entries_table.setMinimumHeight(target_h)
                    entries_table.setMaximumHeight(target_h)
                except Exception:
                    pass
                return

            # データエントリーJSONの存在確認と取得
            dataentry_dir = get_dynamic_file_path("output/rde/data/dataEntry")
            os.makedirs(dataentry_dir, exist_ok=True)
            dataentry_path = os.path.join(dataentry_dir, f"{dataset_id}.json")

            if force_refresh or not os.path.exists(dataentry_path):
                try:
                    from classes.basic.core.basic_info_logic import fetch_data_entry_info_from_api
                    # bearer_token=None で自動選択（関数内で扱う）
                    fetch_data_entry_info_from_api(None, dataset_id, dataentry_dir)
                except Exception as fe:
                    logger.warning("データエントリー情報の取得に失敗: %s", fe)

            if not os.path.exists(dataentry_path):
                # 取得できていない場合は空のまま
                return

            # JSONを読み込み
            with open(dataentry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            items = data.get('data') or []
            registration_entries = _load_registration_entries()
            status_map = {r.get('id'): r.get('status') for r in registration_entries if isinstance(r, dict)}

            # 行データ構築 (スプリット後合計行数計算)
            # 新しいヘルパー関数で行展開（2時間上限）
            # UIテーブルでは複数候補をそのまま分割表示するため、tight collapse を無効化
            expanded_rows = build_expanded_rows_for_dataset_entries(items, dataset_name, registration_entries, collapse_tight=False)

            entries_table.setRowCount(len(expanded_rows))
            for row, rdata in enumerate(expanded_rows):
                full_id = str(rdata['data_entry_id'])
                trunc_id = (full_id[:10] + "…") if len(full_id) > 10 else full_id
                id_item = QTableWidgetItem(trunc_id)
                id_item.setToolTip(full_id)
                name_item = QTableWidgetItem(str(rdata['data_name']))
                full_reg_id = str(rdata['reg_id'])
                trunc_reg_id = (full_reg_id[:10] + "…") if len(full_reg_id) > 10 else full_reg_id
                reg_id_item = QTableWidgetItem(trunc_reg_id)
                reg_id_item.setToolTip(full_reg_id)
                reg_status_item = QTableWidgetItem(str(rdata['reg_status']))
                entries_table.setItem(row, 0, id_item)
                entries_table.setItem(row, 1, name_item)
                entries_table.setItem(row, 2, reg_id_item)
                entries_table.setItem(row, 3, reg_status_item)
                # 列4: 登録開始日時（JST年月日時分秒）
                start_time_jst = format_start_time_jst(rdata.get('start_time', ''))
                start_time_item = QTableWidgetItem(start_time_jst)
                entries_table.setItem(row, 4, start_time_item)
                # 列5: リンクボタン
                if rdata['linkable']:
                    btn = QPushButton("開く")
                    rid_local = rdata['reg_id']
                    btn.clicked.connect(lambda _=None, rid=rid_local: webbrowser.open(f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{rid}"))
                    entries_table.setCellWidget(row, 5, btn)
                else:
                    btn = QPushButton("開く")
                    btn.setEnabled(False)
                    entries_table.setCellWidget(row, 5, btn)

            # コンテキストメニューで元の値をコピー可能にする
            try:
                from qt_compat.core import QClipboard
                entries_table.setContextMenuPolicy(Qt.CustomContextMenu)

                def on_table_context_menu(pos):
                    index = entries_table.indexAt(pos)
                    if not index.isValid():
                        return
                    col = index.column()
                    if col in (0, 2):
                        item = entries_table.item(index.row(), col)
                        if item:
                            # ツールチップにフルIDを保持している
                            full_value = item.toolTip() or item.text()
                            cb = QApplication.clipboard()
                            cb.setText(full_value)
                            # 目立つ通知は避け、静かなログのみ
                            logger.debug("テーブルのフルIDをクリップボードへコピー: col=%s value=%s", col, full_value)

                entries_table.customContextMenuRequested.connect(on_table_context_menu)
            except Exception as _:
                # 失敗しても致命的ではないため無視
                pass

            # 行数に合わせてテーブル高さを固定（内側スクロールを出さない）
            try:
                header_h = entries_table.horizontalHeader().height() if entries_table.horizontalHeader() else 25
                row_h = entries_table.verticalHeader().defaultSectionSize() if entries_table.verticalHeader() else 22
                target_h = max(120, int(header_h + (row_h * entries_table.rowCount()) + 8))
                entries_table.setMinimumHeight(target_h)
                entries_table.setMaximumHeight(target_h)
            except Exception:
                pass

        except Exception as e:
            logger.error("エントリー一覧更新時にエラー: %s", e)

    # 外部テストから直接呼び出せるように参照を公開
    widget.update_entries_table_for_dataset = update_entries_table_for_dataset
    
    # フォームクリア処理
    def clear_edit_form():
        """編集フォームをクリア"""
        nonlocal dataset_user_info_map, dataset_user_role_fallback, user_resolution_state, update_permission_blocked, current_applicant_id, current_manager_id
        edit_dataset_name_edit.clear()
        edit_grant_number_combo.setCurrentIndex(-1)
        edit_description_edit.clear()
        edit_contact_edit.clear()
        edit_applicant_display.clear()
        edit_applicant_display.setToolTip("")
        _reset_manager_combo()
        dataset_user_info_map = {}
        dataset_user_role_fallback = {"applicant": None, "manager": None}
        user_resolution_state["applicant"] = "missing"
        user_resolution_state["manager"] = "missing"
        current_applicant_id = None
        current_manager_id = None
        update_permission_blocked = False
        edit_taxonomy_edit.clear()
        edit_related_links_edit.clear()  # 関連情報もクリア
        edit_tags_edit.clear()  # TAGフィールドをクリア
        edit_citation_format_edit.clear()  # 引用書式フィールドをクリア
        edit_license_combo.setCurrentIndex(-1)  # ライセンス選択をクリア
        edit_template_display.clear()  # テンプレート表示をクリア
        edit_related_datasets_display.clear()  # 関連データセット表示をクリア
        widget._selected_related_dataset_ids = []  # 関連データセットIDリストをクリア
        edit_anonymize_checkbox.setChecked(False)
        edit_data_entry_prohibited_checkbox.setChecked(False)
        edit_data_entry_delete_prohibited_checkbox.setChecked(False)  # 新しいチェックボックス
        edit_share_core_scope_checkbox.setChecked(False)
        
        # データ一覧表示タイプをデフォルト（ギャラリー）に設定
        edit_data_listing_gallery_radio.setChecked(True)
        edit_data_listing_tree_radio.setChecked(False)
        
        # エンバーゴ期間終了日をデフォルト値に戻す
        today = datetime.date.today()
        next_year = today.year + 1
        embargo_date = QDate(next_year, 3, 31)
        edit_embargo_edit.setDate(embargo_date)

        _recompute_update_permission_block(applicant_id=None, manager_id=None)
    
    # 関連情報バリデーション機能（QLineEdit対応）
    def validate_related_links(text):
        """関連情報の書式をバリデーション"""
        if not text.strip():
            return True, "関連情報が空です"
        
        errors = []
        valid_links = []
        
        # コンマ区切りで分割
        items = text.split(',')
        for i, item in enumerate(items, 1):
            item = item.strip()
            if not item:
                continue
                
            # TITLE:URL の形式をチェック
            if ':' not in item:
                errors.append(f"項目{i}: ':' が見つかりません")
                continue
                
            # タイトルとURLを分離
            try:
                title, url = item.split(':', 1)
                title = title.strip()
                url = url.strip()
                
                if not title:
                    errors.append(f"項目{i}: タイトルが空です")
                    continue
                    
                if not url:
                    errors.append(f"項目{i}: URLが空です")
                    continue
                    
                valid_links.append({"title": title, "url": url})
                
            except Exception as e:
                errors.append(f"項目{i}: 解析エラー - {e}")
        
        if errors:
            return False, "\\n".join(errors)
        else:
            return True, f"{len(valid_links)}件の関連情報が有効です"
    
    # 関連情報のリアルタイムバリデーション（QLineEdit対応）
    def on_related_links_changed():
        text = edit_related_links_edit.text()
        is_valid, message = validate_related_links(text)
        
        if is_valid:
            edit_related_links_edit.setStyleSheet("border: 1px solid green;")
        else:
            edit_related_links_edit.setStyleSheet("border: 1px solid red;")
        
        # ツールチップでメッセージを表示
        edit_related_links_edit.setToolTip(message)
    
    edit_related_links_edit.textChanged.connect(on_related_links_changed)
    
    # 選択されたデータセットの情報をフォームに反映
    def populate_edit_form_local(selected_dataset):
        """選択されたデータセットの情報をフォームに反映"""
        if not selected_dataset:
            clear_edit_form()  # データセットが選択されていない場合はフォームをクリア
            return

        nonlocal dataset_user_info_map, dataset_user_role_fallback, user_resolution_state

        # dataset.json はダイジェストのため、詳細ファイル(output/rde/data/datasets/{id}.json)があれば優先して使用
        selected_dataset = _resolve_dataset_for_edit(selected_dataset) or selected_dataset
        
        # テンプレートIDを保存（タクソノミービルダーで使用）
        current_template_id = ""
        relationships = selected_dataset.get("relationships", {})
        template_data = relationships.get("template", {}).get("data", {})
        if template_data:
            current_template_id = template_data.get("id", "")
        
        # テンプレートIDをウィジェットに保存し、表示フィールドにも設定
        widget.current_template_id = current_template_id
        edit_template_display.setText(current_template_id)
        logger.debug("テンプレートID保存・表示: %s", current_template_id)
        
        attrs = selected_dataset.get("attributes", {})

        # データセットJSONに含まれるユーザー情報を保持（applicant/manager名のフォールバック用）
        dataset_user_info_map = {}
        dataset_user_role_fallback = {
            "applicant": attrs.get("applicantName") or attrs.get("applicantDisplayName"),
            "manager": attrs.get("managerName") or attrs.get("managerDisplayName"),
        }
        for item in selected_dataset.get("included", []) or []:
            try:
                if item.get("type") != "user":
                    continue
                uid = str(item.get("id") or "")
                if not uid:
                    continue
                dataset_user_info_map[uid] = item.get("attributes", {}) or {}
            except Exception:
                logger.debug("dataset JSONのユーザー情報抽出に失敗", exc_info=True)

        user_resolution_state["applicant"] = "missing"
        user_resolution_state["manager"] = "missing"

        # 基本情報
        edit_dataset_name_edit.setText(attrs.get("name", ""))
        
        # 課題番号の設定 - 選択されたデータセットに対応するサブグループの課題番号を取得
        dataset_grant_numbers = get_grant_numbers_from_dataset(selected_dataset)
        if hasattr(edit_grant_number_combo, 'update_grant_numbers'):
            edit_grant_number_combo.update_grant_numbers(dataset_grant_numbers)
        
        # 現在のデータセットの課題番号を選択状態にする
        current_grant_number = attrs.get("grantNumber", "")
        if current_grant_number and dataset_grant_numbers:
            # コンボボックスに該当アイテムがあるかチェック
            found_index = -1
            for i in range(edit_grant_number_combo.count()):
                if edit_grant_number_combo.itemData(i) == current_grant_number:
                    found_index = i
                    break
            
            if found_index >= 0:
                edit_grant_number_combo.setCurrentIndex(found_index)
                logger.debug("課題番号 '%s' を選択状態に設定", current_grant_number)
            else:
                # 見つからない場合はテキストとして設定
                edit_grant_number_combo.lineEdit().setText(current_grant_number)
                logger.debug("課題番号 '%s' をテキストとして設定", current_grant_number)
        else:
            logger.debug("課題番号設定スキップ: current='%s', available=%s", current_grant_number, len(dataset_grant_numbers) if dataset_grant_numbers else 0)
        edit_description_edit.setText(attrs.get("description", ""))

        # 申請者/管理者情報の反映
        group_id = relationships.get("group", {}).get("data", {}).get("id") if isinstance(relationships, dict) else None
        _populate_members_for_group(group_id)

        applicant_id = _extract_user_id(relationships.get("applicant") if isinstance(relationships, dict) else None)
        _set_applicant_display(applicant_id)

        manager_id = _extract_user_id(relationships.get("manager") if isinstance(relationships, dict) else None)
        _apply_manager_selection(manager_id)

        _recompute_update_permission_block(applicant_id=applicant_id, manager_id=manager_id)

        edit_contact_edit.setText(attrs.get("contact", ""))
        
        # エンバーゴ期間終了日
        embargo_date_str = attrs.get("embargoDate", "")
        if embargo_date_str:
            try:
                # ISO形式の日付をパース（簡易版）
                # "2026-03-31T03:00:00.000Z" のような形式を想定
                if "T" in embargo_date_str:
                    date_part = embargo_date_str.split("T")[0]
                else:
                    date_part = embargo_date_str.split()[0] if " " in embargo_date_str else embargo_date_str
                
                year, month, day = map(int, date_part.split("-"))
                qdate = QDate(year, month, day)
                edit_embargo_edit.setDate(qdate)
            except Exception as e:
                logger.warning("エンバーゴ日付のパースに失敗: %s", e)
                # デフォルト値のまま
        
        # タクソノミーキー（スペース区切りで表示）
        taxonomy_keys = attrs.get("taxonomyKeys", [])
        if taxonomy_keys:
            edit_taxonomy_edit.setText(" ".join(taxonomy_keys))
        else:
            edit_taxonomy_edit.clear()  # 空の場合は明示的にクリア
        
        # 関連情報（新しい書式で表示）
        related_links = attrs.get("relatedLinks", [])
        logger.debug("データセットの関連リンク: %s", related_links)
        
        if related_links:
            links_text = []
            for link in related_links:
                title = link.get("title", "")
                url = link.get("url", "")
                if title and url:
                    # 新しい書式: タイトル:URL
                    link_line = f"{title}:{url}"
                    links_text.append(link_line)
                    logger.debug("関連情報行追加: '%s'", link_line)
            
            final_text = ",".join(links_text)  # カンマ区切りに変更
            logger.debug("テキストエリアに設定する関連情報: '%s'", final_text)
            edit_related_links_edit.setText(final_text)
        else:
            logger.debug("関連情報が空 - テキストエリアをクリアします")
            edit_related_links_edit.clear()  # 関連情報が空の場合は明示的にクリア
        
        # TAGフィールド
        tags = attrs.get("tags", [])
        if tags:
            tags_text = ", ".join(tags)
            edit_tags_edit.setText(tags_text)
            logger.debug("TAGを設定: '%s'", tags_text)
        else:
            edit_tags_edit.clear()
            logger.debug("TAGが空 - テキストエリアをクリアします")
        
        # データセット引用の書式
        citation_format = attrs.get("citationFormat", "")
        if citation_format:
            edit_citation_format_edit.setText(citation_format)
            logger.debug("引用書式を設定: '%s'", citation_format)
        else:
            edit_citation_format_edit.clear()
            logger.debug("引用書式が空 - テキストエリアをクリアします")
        
        # 利用ライセンスの設定（relationshipsから取得）
        license_value = ""
        relationships = selected_dataset.get("relationships", {})
        if "license" in relationships:
            license_data = relationships["license"].get("data")
            if license_data is not None:
                license_value = license_data.get("id", "")
            # license_data が None の場合は license_value は空文字のまま
            
        if license_value:
            # コンボボックスに該当アイテムがあるかチェック
            found_index = -1
            for i in range(edit_license_combo.count()):
                if edit_license_combo.itemData(i) == license_value:
                    found_index = i
                    break
            
            if found_index >= 0:
                edit_license_combo.setCurrentIndex(found_index)
                logger.debug("ライセンス設定 (コンボボックス): '%s'", license_value)
            else:
                # 見つからない場合はテキストとして設定
                edit_license_combo.lineEdit().setText(license_value)
                logger.debug("ライセンス設定 (テキスト): '%s'", license_value)
        else:
            edit_license_combo.setCurrentIndex(-1)
            logger.debug("ライセンスが空 - 選択をクリア")
        
        # 関連データセット表示
        relationships = selected_dataset.get("relationships", {})
        related_datasets_data = relationships.get("relatedDatasets", {}).get("data", [])
        
        # 関連データセットIDリストを更新
        dataset_ids = [rd.get("id", "") for rd in related_datasets_data if rd.get("id")]
        widget._selected_related_dataset_ids = dataset_ids
        
        # 件数を表示
        count = len(dataset_ids)
        if count > 0:
            edit_related_datasets_display.setText(f"{count}件")
            logger.debug("関連データセット: %s件", count)
        else:
            edit_related_datasets_display.clear()
            logger.debug("関連データセットが空")
        
        # チェックボックス
        edit_anonymize_checkbox.setChecked(attrs.get("isAnonymized", False))
        edit_data_entry_prohibited_checkbox.setChecked(attrs.get("isDataEntryProhibited", False))
        
        # 新しいチェックボックス: データ登録及び削除を禁止する
        # isDataEntryProhibitedがTrueの場合にこちらもチェック（仮の実装）
        edit_data_entry_delete_prohibited_checkbox.setChecked(attrs.get("isDataEntryProhibited", False))
        
        # データ一覧表示タイプの設定
        data_listing_type = attrs.get("dataListingType", "GALLERY")
        if data_listing_type == "TREE":
            edit_data_listing_tree_radio.setChecked(True)
            edit_data_listing_gallery_radio.setChecked(False)
        else:
            edit_data_listing_gallery_radio.setChecked(True)
            edit_data_listing_tree_radio.setChecked(False)
        
        # 共有ポリシーから広域シェア設定を取得
        sharing_policies = attrs.get("sharingPolicies", [])
        core_scope_enabled = False
        for policy in sharing_policies:
            # RDE全体共有のscope ID（データセット開設機能と同じID）
            if policy.get("scopeId") == "22aec474-bbf2-4826-bf63-60c82d75df41":
                core_scope_enabled = policy.get("permissionToView", False)
                break
        edit_share_core_scope_checkbox.setChecked(core_scope_enabled)
    
    # ドロップダウン選択時の処理
    def _get_selected_dataset_from_combo() -> dict | None:
        """Return selected dataset dict from combo, or None when not selected.

        index==0 を未選択扱いにする前提に依存せず、itemData の実体で判断する。
        """
        try:
            idx = existing_dataset_combo.currentIndex()
            if idx < 0:
                return None
            data = existing_dataset_combo.itemData(idx)
            if not isinstance(data, dict):
                return None
            if not data.get("id"):
                return None
            return data
        except Exception:
            return None

    def on_dataset_selection_changed():
        current_index = existing_dataset_combo.currentIndex()
        logger.debug("データセット選択変更: インデックス=%s", current_index)
        reset_update_override("データセット選択変更")
        _update_launch_button_state()

        def _running_under_pytest() -> bool:
            try:
                return bool(os.environ.get("PYTEST_CURRENT_TEST")) or ("pytest" in sys.modules)
            except Exception:
                return False

        selected_dataset = _get_selected_dataset_from_combo()
        if not selected_dataset:
            logger.debug("データセット未選択状態 - フォームをクリアします")
            clear_edit_form()
            update_entries_table_for_dataset(None, None)
            return

        # RDE側で削除済みのデータセットを選択してしまうケースの対策
        # - 404/410 が確定した場合のみ、候補から除外する（ネットワーク不調時は除外しない）
        if not _running_under_pytest():
            try:
                from classes.utils.remote_resource_pruner import check_dataset_exists

                dataset_id = str(selected_dataset.get("id", "") or "")
                check = check_dataset_exists(dataset_id, timeout=3.0)
                if check.exists is False:
                    try:
                        existing_dataset_combo.blockSignals(True)
                        # コンボから除去
                        for i in range(existing_dataset_combo.count()):
                            data = existing_dataset_combo.itemData(i)
                            if isinstance(data, dict) and str(data.get("id", "") or "") == dataset_id:
                                existing_dataset_combo.removeItem(i)
                                break

                        # 遅延展開キャッシュからも除去（再出現防止）
                        cached_datasets = getattr(existing_dataset_combo, "_datasets_cache", None)
                        if isinstance(cached_datasets, list):
                            cached_datasets[:] = [
                                d
                                for d in cached_datasets
                                if not (isinstance(d, dict) and str(d.get("id", "") or "") == dataset_id)
                            ]
                        cached_display = getattr(existing_dataset_combo, "_display_names_cache", None)
                        if isinstance(cached_display, list) and isinstance(cached_datasets, list):
                            # display_names 側は完全同期が難しいため、長さ不一致時は再構築を後続処理に委ねる
                            pass
                        display_map = getattr(existing_dataset_combo, "_display_to_dataset_map", None)
                        if isinstance(display_map, dict):
                            try:
                                # 値側が一致するものを掃除
                                for k in list(display_map.keys()):
                                    v = display_map.get(k)
                                    if isinstance(v, dict) and str(v.get("id", "") or "") == dataset_id:
                                        display_map.pop(k, None)
                            except Exception:
                                pass

                        existing_dataset_combo.setCurrentIndex(-1)
                    finally:
                        existing_dataset_combo.blockSignals(False)

                    clear_edit_form()
                    update_entries_table_for_dataset(None, None)
                    try:
                        QMessageBox.warning(
                            widget,
                            "データセット削除検知",
                            "選択したデータセットはRDE上で削除済みのため、候補から除外しました。\n"
                            "基本情報タブでJSONを再取得してください。",
                        )
                    except Exception:
                        pass
                    return
            except Exception:
                # 判定不能時は従来どおり継続
                pass

        resolved_dataset = _resolve_dataset_for_edit(selected_dataset) or selected_dataset
        dataset_name = resolved_dataset.get("attributes", {}).get("name", "不明")
        dataset_id = str(resolved_dataset.get("id", "") or "")
        logger.debug("データセット '%s' を選択 - フォームに反映します", dataset_name)
        populate_edit_form_local(resolved_dataset)
        update_entries_table_for_dataset(dataset_id, dataset_name, force_refresh=False)
    
    def on_completer_activated(text):
        """QCompleterでフィルタ選択された場合の処理（直接フォーム更新版）"""
        logger.info("Completer選択テキスト: %r", text)
        logger.debug("Completer選択時のコンボボックス状態: count=%s", existing_dataset_combo.count())
        
        # コンボボックスのシグナルブロック状態を検証
        signals_blocked_before = existing_dataset_combo.signalsBlocked()
        logger.debug("Completer起動時のシグナルブロック状態: %s", signals_blocked_before)
        
        # マップから直接データセットを取得
        display_map = getattr(existing_dataset_combo, '_display_to_dataset_map', None)
        if not display_map:
            logger.error("Completer選択失敗: マップが存在しません")
            return
        
        # 正規化テキストでマップ検索
        norm_text = _normalize_display_text(text)
        dataset_dict = display_map.get(norm_text)
        
        if dataset_dict:
            dataset_dict = _resolve_dataset_for_edit(dataset_dict) or dataset_dict
            # データセット辞書が見つかった場合、直接フォームに反映
            dataset_id = dataset_dict.get("id", "")
            dataset_name = dataset_dict.get("attributes", {}).get("name", "不明")
            logger.info("Completer選択成功: id=%s name=%s", dataset_id, dataset_name)
            reset_update_override("Completerによるデータセット選択")
            
            # コンボボックスが空の場合はキャッシュから復元
            if existing_dataset_combo.count() == 0:
                logger.warning("Completer選択後にコンボボックスが空 - キャッシュから復元を試みます")
                cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', [])
                cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', [])
                
                if cached_datasets and cached_display_names:
                    logger.info("キャッシュから %s 件のアイテムを復元", len(cached_datasets))
                    # シグナルブロックして復元
                    existing_dataset_combo.blockSignals(True)
                    populate_combo_box_with_progress(existing_dataset_combo, cached_datasets, cached_display_names)
                    existing_dataset_combo.blockSignals(False)
                else:
                    logger.error("キャッシュが空 - 復元できません")
            
            # コンボボックスのインデックスを設定（可能であれば）
            idx = -1
            for i in range(existing_dataset_combo.count()):
                item_data = existing_dataset_combo.itemData(i)
                if isinstance(item_data, dict) and item_data.get("id") == dataset_id:
                    idx = i
                    break
            
            if idx >= 0:
                # シグナルブロックしてインデックス設定（二重呼び出し防止）
                logger.debug("setCurrentIndex前のシグナルブロック状態: %s", existing_dataset_combo.signalsBlocked())
                existing_dataset_combo.blockSignals(True)
                logger.debug("blockSignals(True)後の状態: %s", existing_dataset_combo.signalsBlocked())
                existing_dataset_combo.setCurrentIndex(idx)
                existing_dataset_combo.blockSignals(False)
                logger.debug("blockSignals(False)後の状態: %s", existing_dataset_combo.signalsBlocked())
            else:
                logger.warning("Completer選択後にコンボボックスから該当アイテムが見つかりませんでした (ID: %s)", dataset_id)
                logger.debug("コンボボックスアイテム数: %s", existing_dataset_combo.count())
            
            # 直接フォーム更新
            populate_edit_form_local(dataset_dict)
            # エントリー一覧を更新
            update_entries_table_for_dataset(dataset_id, dataset_name, force_refresh=False)
        else:
            # マップに見つからない場合の詳細ログ
            logger.error("Completer選択解決失敗: text=%s norm=%s", text, norm_text)
            logger.error("マップエントリ数: %s", len(display_map))
            logger.error("マップの先頭3キー: %s", list(display_map.keys())[:3])
            # 正規化キーでの再検索試行
            logger.error("マップ内の正規化キー例（最初の3件）:")
            for i, key in enumerate(list(display_map.keys())[:3]):
                logger.error("  [%s] '%s'", i, key[:100])
            # アイテム数確認
            total_items = existing_dataset_combo.count()
            logger.error("全アイテム数: %s", total_items)

    
    existing_dataset_combo.currentIndexChanged.connect(on_dataset_selection_changed)

    def _apply_dataset_launch_payload(payload: DatasetPayload) -> bool:
        if not payload or not payload.id:
            return False

        # デバッグ用: 呼び出し先(dataset_edit)で受け取った dataset_id をログへ出す
        logger.info(
            "dataset_edit: launch payload received dataset_id=%s display=%s has_raw=%s",
            payload.id,
            payload.display_text,
            bool(payload.raw),
        )
        relax_dataset_edit_filters_for_launch(
            filter_all_radio,
            (filter_user_only_radio, filter_others_only_radio),
            grant_number_filter_edit,
            lambda: apply_filter(force_reload=False),
        )

        # ComboBoxは通常、初期ロード時にアイテムを展開せず（placeholder + completer + cacheのみ）
        # mousePressEvent 等で必要時に展開します。
        # 連携起動では「選択状態」を作る必要があるため、キャッシュがある場合はここで展開します。
        try:
            if existing_dataset_combo.count() == 0:
                cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', None)
                cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', None)
                if isinstance(cached_datasets, list) and isinstance(cached_display_names, list) and cached_datasets:
                    populate_combo_box_with_progress(existing_dataset_combo, cached_datasets, cached_display_names)
        except Exception:
            logger.debug("dataset_edit: combo expansion from cache failed", exc_info=True)

        target_index = _find_dataset_index(payload.id)
        dataset_dict = payload.raw
        if target_index < 0:
            if dataset_dict is None:
                dataset_dict = _load_dataset_record(payload.id)
            if dataset_dict is None:
                logger.warning("dataset_edit: 連携データセットが見つかりません: %s", payload.id)
                return False

            # フォールバック: キャッシュ展開できない/対象が無い場合は単体で挿入。
            # index==0 を未選択扱いにしているため、ヘッダーが無い場合は先に追加します。
            if existing_dataset_combo.count() == 0:
                existing_dataset_combo.addItem("-- データセットを選択してください --", None)
            target_index = _insert_dataset_into_combo(dataset_dict, payload.display_text)
        if target_index < 0:
            return False

        previous_index = existing_dataset_combo.currentIndex()
        existing_dataset_combo.setCurrentIndex(target_index)
        if previous_index == target_index:
            try:
                on_dataset_selection_changed()
            except Exception:
                logger.debug("dataset_edit: manual dataset refresh failed", exc_info=True)
        _update_launch_button_state()
        return True

    # NOTE: DatasetLaunchManager の receiver 登録は、初期データロード後に行う。
    # 連携ペイロードが widget 生成前に到着している場合、register_receiver() が即時適用を試みるため、
    # ここで登録するとキャッシュ未構築の状態で選択処理が走りやすい。
    
    # フィルタ機能のイベントハンドラー
    def apply_filter(force_reload=False):
        """フィルタを適用してデータセット一覧を更新"""
        # 現在のフィルタ設定を取得
        filter_type = get_current_filter_type()
        grant_number_filter = grant_number_filter_edit.text().strip()
        reset_update_override("フィルタ変更", filter_type, grant_number_filter)
        
        if force_reload:
            logger.info("キャッシュ更新: タイプ=%s, 課題番号='%s'", filter_type, grant_number_filter)
        else:
            logger.info("フィルタ適用: タイプ=%s, 課題番号='%s'", filter_type, grant_number_filter)
        
        # データセット一覧を再読み込み
        load_existing_datasets(filter_type, grant_number_filter, force_reload)
        
        # 選択をクリア
        existing_dataset_combo.setCurrentIndex(-1)
        clear_edit_form()
    
    def refresh_cache():
        """エントリーリスト更新（選択中データセットのみ）"""
        selected_dataset = _get_selected_dataset_from_combo()
        if not selected_dataset:
            QMessageBox.warning(widget, "データセット未選択", "更新するデータセットを選択してください。")
            return

        dataset_id = selected_dataset.get("id")
        dataset_name = (selected_dataset.get("attributes") or {}).get("name")
        if not dataset_id:
            QMessageBox.warning(widget, "データエラー", "選択されたデータセットのIDが取得できません。")
            return

        update_entries_table_for_dataset(str(dataset_id), str(dataset_name) if dataset_name else None, force_refresh=True)

    def on_refetch_current_dataset():
        """選択中データセット詳細をAPIから再取得し、フォーム表示を更新"""
        current_index = existing_dataset_combo.currentIndex()
        selected_dataset = _get_selected_dataset_from_combo()
        if not selected_dataset:
            QMessageBox.warning(widget, "データセット未選択", "再取得するデータセットを選択してください。")
            return

        dataset_id = selected_dataset.get("id")
        if not dataset_id:
            QMessageBox.warning(widget, "データエラー", "選択されたデータセットのIDが取得できません。")
            return

        try:
            from core.bearer_token_manager import BearerTokenManager
            bearer_token = BearerTokenManager.get_valid_token()
        except Exception:
            bearer_token = None

        refreshed = _fetch_dataset_detail_from_api(str(dataset_id), bearer_token)
        if not refreshed:
            QMessageBox.warning(widget, "再取得失敗", "データセット詳細の再取得に失敗しました。ログイン状態や権限を確認してください。")
            return

        # コンボボックスの itemData を最新詳細へ差し替え
        try:
            existing_dataset_combo.setItemData(current_index, refreshed)
        except Exception:
            pass

        populate_edit_form_local(refreshed)

        # エントリー一覧も選択中データセットで再描画（強制ではない）
        dataset_name = (refreshed.get("attributes") or {}).get("name")
        update_entries_table_for_dataset(str(dataset_id), str(dataset_name) if dataset_name else None, force_refresh=False)
    
    # 動的フィルタリング用のタイマー
    # 親無しの QTimer は widget 破棄後も生存し得て、timeout が遅れて発火すると
    # 破棄済み QObject 参照で Windows/PySide6 がクラッシュすることがある。
    filter_timer = QTimer(widget)
    filter_timer.setSingleShot(True)
    filter_timer.timeout.connect(apply_filter)
    
    def on_filter_text_changed():
        """フィルタテキスト変更時の処理（遅延実行）"""
        filter_timer.stop()  # 既存のタイマーを停止
        filter_timer.start(500)  # 500ms後にフィルタを実行
    
    def on_enable_update_override():
        """安全ロック解除ボタンの処理"""
        if not enable_update_override_button.isEnabled():
            return

        current_filter_type = get_current_filter_type()
        current_grant_filter = grant_number_filter_edit.text().strip()

        if _is_default_filter_state(current_filter_type, current_grant_filter):
            refresh_update_controls(current_filter_type, current_grant_filter)
            return

        message = (
            "データセット更新ボタンを一時的に有効化します。\n"
            "ユーザー所属以外や課題番号で絞り込んだ状態でも更新できます。\n"
            "権限がない場合はRDE側で拒否されます。\n"
            "※ データセットを切り替えると自動で無効化されます。"
        )
        reply = QMessageBox.question(
            widget,
            "更新有効化の確認",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            update_override_state["enabled"] = True
            logger.info("更新ボタンを手動で有効化: filter=%s grant='%s'", current_filter_type, current_grant_filter or "なし")
            refresh_update_controls(current_filter_type, current_grant_filter)

    # フィルタイベントを接続
    cache_refresh_button.clicked.connect(refresh_cache)
    dataset_refetch_button.clicked.connect(on_refetch_current_dataset)
    filter_user_only_radio.toggled.connect(lambda: apply_filter() if filter_user_only_radio.isChecked() else None)
    filter_others_only_radio.toggled.connect(lambda: apply_filter() if filter_others_only_radio.isChecked() else None)
    filter_all_radio.toggled.connect(lambda: apply_filter() if filter_all_radio.isChecked() else None)
    grant_number_filter_edit.textChanged.connect(on_filter_text_changed)  # リアルタイム絞り込み
    enable_update_override_button.clicked.connect(on_enable_update_override)
    
    def on_open_dataset_page():
        """データセットページをブラウザで開く"""
        selected_dataset = _get_selected_dataset_from_combo()
        if not selected_dataset:
            QMessageBox.warning(widget, "データセット未選択", "開くデータセットを選択してください。")
            return
        
        dataset_id = selected_dataset.get("id")
        if not dataset_id:
            QMessageBox.warning(widget, "データエラー", "選択されたデータセットのIDが取得できません。")
            return
        
        # データセットページのURLを生成してブラウザで開く
        url = f"https://rde.nims.go.jp/rde/datasets/{dataset_id}"
        try:
            webbrowser.open(url)
            logger.info("データセットページをブラウザで開きました: %s", url)
        except Exception as e:
            QMessageBox.warning(widget, "エラー", f"ブラウザでページを開けませんでした: {str(e)}")
    
    def on_update_dataset():
        """データセット更新処理"""
        selected_dataset = _get_selected_dataset_from_combo()
        if not selected_dataset:
            QMessageBox.warning(widget, "データセット未選択", "修正するデータセットを選択してください。")
            return

        # 更新ペイロードは重要なrelationships(applicant/group等)を保持するため、詳細JSONを優先
        selected_dataset = _resolve_dataset_for_edit(selected_dataset) or selected_dataset
        
        # 現在選択されているデータセットIDを保存（更新後の再選択用）
        current_dataset_id = selected_dataset.get("id")
        
        def refresh_ui_after_update():
            """データセット更新後のUI再読み込み"""
            try:
                logger.info("データセット更新後のUI再読み込みを開始")
                
                # 【重要】更新したデータセットIDに対してAPI再取得を実行
                logger.info("更新データセットIDのAPI再取得を開始: %s", current_dataset_id)
                try:
                    from core.bearer_token_manager import BearerTokenManager
                    bearer_token = BearerTokenManager.get_valid_token()
                    refreshed_dataset = _fetch_dataset_detail_from_api(current_dataset_id, bearer_token)
                    if refreshed_dataset:
                        logger.info("API再取得成功: dataset_id=%s", current_dataset_id)
                    else:
                        logger.warning("API再取得失敗（データなし）: dataset_id=%s", current_dataset_id)
                except Exception as api_error:
                    logger.warning("API再取得エラー: %s", api_error, exc_info=True)
                
                # 現在のフィルタ設定でデータセットリストを再読み込み（強制再読み込み）
                filter_type = get_current_filter_type()
                grant_number_filter = grant_number_filter_edit.text().strip()
                # キャッシュをクリアして強制再読み込み
                clear_cache()
                load_existing_datasets(filter_type, grant_number_filter, force_reload=True)
                
                # 更新したデータセットを再選択
                if current_dataset_id:
                    # キャッシュされたデータセットから検索
                    cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', [])
                    updated_dataset = None
                    for dataset in cached_datasets:
                        if dataset.get("id") == current_dataset_id:
                            updated_dataset = dataset
                            break
                    
                    if updated_dataset:
                        # キャッシュされた表示名も取得
                        cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', [])
                        
                        # 高速化されたアイテム追加処理を使用
                        existing_dataset_combo.clear()
                        if cached_datasets and cached_display_names:
                            logger.info("高速再選択処理: %s件のデータセット", len(cached_datasets))
                            populate_combo_box_with_progress(existing_dataset_combo, cached_datasets, cached_display_names)
                        else:
                            # フォールバック処理
                            existing_dataset_combo.addItem("-- データセットを選択してください --", None)
                            for ds in cached_datasets:
                                attrs = ds.get("attributes", {})
                                dataset_id = ds.get("id", "")
                                name = attrs.get("name", "名前なし")
                                grant_number = attrs.get("grantNumber", "")
                                dataset_type = attrs.get("datasetType", "")
                                
                                # ユーザー所属かどうかで表示を区別
                                user_grant_numbers = get_user_grant_numbers()
                                if grant_number in user_grant_numbers:
                                    display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
                                else:
                                    display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                                    
                                if dataset_type:
                                    display_text += f" [{dataset_type}]"
                                existing_dataset_combo.addItem(display_text, ds)
                        
                        # 更新したデータセットを検索して選択
                        selected_index = 0
                        for i in range(existing_dataset_combo.count()):
                            item_data = existing_dataset_combo.itemData(i)
                            if item_data and item_data.get("id") == current_dataset_id:
                                selected_index = i
                                break
                        
                        # 更新したデータセットを選択
                        existing_dataset_combo.setCurrentIndex(selected_index)
                        logger.info("データセット '%s' を再選択しました (インデックス: %s)", current_dataset_id, selected_index)
                        
                        # 選択されたデータセットの情報をフォームに再表示
                        if selected_index > 0:
                            selected_dataset_new = existing_dataset_combo.itemData(selected_index)
                            if selected_dataset_new:
                                populate_edit_form_local(selected_dataset_new)
                    else:
                        logger.warning("更新後のデータセット '%s' がキャッシュに見つかりません", current_dataset_id)
                        # コンボボックスをクリア状態に戻す
                        existing_dataset_combo.clear()
                else:
                    # コンボボックスをクリア状態に戻す
                    existing_dataset_combo.clear()
                    
            except Exception as e:
                logger.error("UI再読み込み中にエラー: %s", e)
        
        # 編集機能を実装（後で追加）
        from classes.dataset.core.dataset_edit_functions import send_dataset_update_request
        send_dataset_update_request(
            widget, parent, selected_dataset,
            edit_dataset_name_edit, edit_grant_number_combo, edit_description_edit,
            edit_embargo_edit, edit_contact_edit, edit_taxonomy_edit,
            edit_related_links_edit, edit_tags_edit, edit_citation_format_edit, edit_license_combo,
            edit_data_listing_gallery_radio, edit_data_listing_tree_radio, widget, edit_anonymize_checkbox, 
            edit_data_entry_prohibited_checkbox, edit_data_entry_delete_prohibited_checkbox,
            edit_share_core_scope_checkbox, edit_manager_combo, ui_refresh_callback=refresh_ui_after_update
        )
    
    # イベント接続
    open_dataset_page_button.clicked.connect(on_open_dataset_page)
    update_button.clicked.connect(on_update_dataset)
    
    # データ読み込み実行（デフォルトフィルタで）
    # 初回表示をブロックしないよう、イベントループ復帰後に読み込みを開始。
    # 連携ペイロードは初期ロード後に適用する（初期ロードが選択状態をリセットするため）。
    _dataset_launch_receiver_registered = {"done": False}

    def _register_dataset_launch_receiver_once() -> None:
        if _dataset_launch_receiver_registered["done"]:
            return
        DatasetLaunchManager.instance().register_receiver("dataset_edit", _apply_dataset_launch_payload)
        _dataset_launch_receiver_registered["done"] = True

    def _initial_load_and_register_receiver() -> None:
        try:
            load_existing_datasets("user_only", "")
        finally:
            _register_dataset_launch_receiver_once()

    def _safe_initial_load_and_register_receiver() -> None:
        try:
            from shiboken6 import isValid

            if not isValid(widget):
                return
        except Exception:
            pass
        _initial_load_and_register_receiver()

    # 初回表示をブロックしないため、イベントループ復帰後に1度だけ実行する。
    # widgetテストでは teardown 中の processEvents で走ると不安定になる場合があるため、
    # タイマー参照を widget に保持し、テスト側が close 前に停止できるようにする。
    _initial_load_scheduled = {"done": False}

    def _initial_load_once() -> None:
        if _initial_load_scheduled["done"]:
            return
        _initial_load_scheduled["done"] = True
        _safe_initial_load_and_register_receiver()

    try:
        initial_timer = QTimer(widget)
        initial_timer.setSingleShot(True)
        initial_timer.timeout.connect(_initial_load_once)

        timer_bucket = getattr(widget, "_rde_dataset_edit_timers", None)
        if timer_bucket is None:
            timer_bucket = []
            setattr(widget, "_rde_dataset_edit_timers", timer_bucket)
        timer_bucket.append(initial_timer)

        initial_timer.start(0)
    except Exception:
        QTimer.singleShot(0, _initial_load_once)
    
    # 初期状態でフォームをクリア
    clear_edit_form()
    logger.info("データセット編集ウィジェット初期化完了 - フォームをクリアしました")

    # 他機能からの連携（target dataset 指定）を受け取る
    # ※ receiver 登録は初期ロード後に行う（上の _initial_load_and_register_receiver を参照）
    
    # 外部からリフレッシュできるように関数を属性として追加
    def refresh_with_current_filter(force_reload=False):
        """現在のフィルタ設定でリフレッシュ"""
        filter_type = get_current_filter_type()
        grant_number_filter = grant_number_filter_edit.text().strip()
        selection_id = _get_current_dataset_id()
        
        if force_reload:
            logger.info("外部からキャッシュクリア付きリフレッシュ")
            clear_cache()
        
        load_existing_datasets(
            filter_type,
            grant_number_filter,
            force_reload,
            preserve_selection_id=selection_id,
        )
    
    def refresh_cache_from_external():
        """外部からキャッシュを強制更新"""
        refresh_with_current_filter(force_reload=True)
    
    widget._refresh_dataset_list = refresh_with_current_filter
    widget._refresh_cache = refresh_cache_from_external
    widget.add_show_refresh_callback(lambda: refresh_with_current_filter())
    widget._restore_dataset_selection = _restore_dataset_selection
    
    # グローバル通知システムに登録
    notifier = get_dataset_refresh_notifier()
    notifier.register_callback(refresh_with_current_filter)
    
    # ウィジェットが削除されるときに通知システムから登録解除
    def cleanup():
        try:
            try:
                filter_timer.stop()
            except Exception:
                pass
            try:
                timers = getattr(widget, "_rde_dataset_edit_timers", None)
                if timers:
                    for t in list(timers):
                        try:
                            t.stop()
                        except Exception:
                            pass
                    timers.clear()
            except Exception:
                pass
            notifier.unregister_callback(refresh_with_current_filter)
        except:
            pass
        try:
            if _dataset_launch_receiver_registered["done"]:
                DatasetLaunchManager.instance().unregister_receiver("dataset_edit")
        except Exception:
            pass
    widget.destroyed.connect(cleanup)
    
    layout.addStretch()
    widget.setLayout(layout)
    return widget
