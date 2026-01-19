
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
import shutil
from pathlib import Path

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional
from urllib.parse import quote, urlencode

from dateutil.parser import parse as parse_datetime  # ISO8601対応のため
from ..util.xlsx_exporter import apply_basic_info_to_Xlsx_logic, summary_basic_info_to_Xlsx_logic
from classes.utils.api_request_helper import api_request  # refactored to use api_request_helper
from classes.basic.core.api_recording_wrapper import (
    record_api_call_for_dataset_list,
    record_api_call_for_instruments,
    record_api_call_for_template,
)
from config.common import (
    DATA_ENTRY_DIR,
    DATASET_JSON_CHUNKS_DIR,
    DATASET_JSON_PATH,
    GROUP_DETAIL_JSON_PATH,
    GROUP_JSON_PATH,
    GROUP_ORGNIZATION_DIR,
    GROUP_PROJECT_DIR,
    INFO_JSON_PATH,
    LICENSES_JSON_PATH,
    ORGANIZATION_JSON_PATH,
    INSTRUMENT_JSON_CHUNKS_DIR,
    INSTRUMENTS_JSON_PATH,
    INSTRUMENT_TYPE_JSON_PATH,
    INVOICE_DIR,
    LEGACY_SUBGROUP_DETAILS_DIR,
    OUTPUT_DIR as COMMON_OUTPUT_DIR,
    OUTPUT_RDE_DATA_DIR,
    SELF_JSON_PATH,
    SUBGROUP_REL_DETAILS_DIR,
    SUBGROUP_DETAILS_DIR,
    SUBGROUP_JSON_PATH,
    TEMPLATE_JSON_CHUNKS_DIR,
    TEMPLATE_JSON_PATH,
    get_dynamic_file_path,
)

# ロガー設定（標準出力にも出す）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# === 設定値 ===
OUTPUT_DIR = COMMON_OUTPUT_DIR

PROGRAM_SELECTION_CONTEXT = "basic.program.root"
PROJECT_SELECTION_CONTEXT = "basic.project.detail"
SUBGROUP_SELECTION_CONTEXT = "basic.project.subgroup"

DATASET_LIST_PAGE_SIZE = 1000
DATASET_LIST_REQUEST_TIMEOUT = 30  # seconds
DATASET_CHUNK_FILE_TEMPLATE = "dataset_chunk_{:04d}.json"
_DATASET_RESERVED_KEYS = {"data", "included", "meta", "links"}
TEMPLATE_CHUNK_FILE_TEMPLATE = "template_chunk_{:04d}.json"
INSTRUMENT_CHUNK_FILE_TEMPLATE = "instrument_chunk_{:04d}.json"

# 他エンドポイントでも同一閾値を用いる（ユーザー要望: 1000件単位）
DEFAULT_CHUNK_PAGE_SIZE = 1000

# テンプレートAPIは offset>0 のページング取得でタイムアウト/不安定になりやすい報告があるため、
# 旧実装互換としてまずは大きめlimitで単発取得を優先する（通常は1回で完結）。
# ※実際に 10,000 を超える場合のみページングとなる。
TEMPLATE_PAGE_SIZE = 10_000

INSTRUMENT_PAGE_SIZE = DEFAULT_CHUNK_PAGE_SIZE

# タイムアウトは旧実装相当（短縮すると read timeout を誘発しやすい）
TEMPLATE_REQUEST_TIMEOUT = 30
INSTRUMENT_REQUEST_TIMEOUT = 10

TEMPLATE_API_BASE_URL = "https://rde-api.nims.go.jp/datasetTemplates"
INSTRUMENT_API_BASE_URL = "https://rde-instrument-api.nims.go.jp/instruments"
DEFAULT_PROGRAM_ID = "4bbf62be-f270-4a46-9682-38cd064607ba"
DEFAULT_TEAM_ID = "1e44cefd-85ba-49cb-bc7e-196a0ef379b0"

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
            except GroupFetchCancelled:
                # UIのキャンセル操作はエラー扱いにせず、統一メッセージを返す
                return "キャンセルされました"
            except Exception as e:
                error_msg = f"{operation_name}でエラーが発生しました: {e}"
                logger.error(error_msg)
                return error_msg
        return wrapper
    return decorator

def save_json(data, *path):
    """JSONファイルを保存する共通関数"""
    filepath = os.path.join(*path)
    # 相対パスで渡された場合でも、動的パス解決でユーザーディレクトリ配下に保存する
    if not os.path.isabs(filepath):
        filepath = get_dynamic_file_path(filepath)
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"JSONファイル保存完了: {filepath}")
    except Exception as e:
        logger.error(f"JSONファイル保存失敗: {filepath}, error={e}")
        raise


def _subgroups_folder_complete() -> bool:
    """サブグループ詳細フォルダの完全性をチェックする共通ヘルパー"""
    try:
        expected_ids = set()
        logger.info("\n[フォルダ完全性チェック開始] v2.1.24")

        def _expected_team_ids_from_subgroup_json() -> set[str]:
            """subGroup.json から期待TEAM IDを抽出する（可能ならこれを最優先）。"""
            try:
                subgroup_json_path = Path(SUBGROUP_JSON_PATH)
                if not subgroup_json_path.exists():
                    return set()
                with open(subgroup_json_path, "r", encoding="utf-8") as f:
                    subgroup_data = json.load(f)

                extracted: set[str] = set()
                included = subgroup_data.get("included", [])
                for item in included:
                    if (
                        item.get("type") == "group"
                        and item.get("attributes", {}).get("groupType") == "TEAM"
                    ):
                        gid = item.get("id")
                        if isinstance(gid, str) and gid:
                            extracted.add(gid)

                # included に TEAM が無い場合、relationships.children をフォールバックで利用
                if not extracted:
                    relationships = subgroup_data.get("data", {}).get("relationships", {})
                    children = relationships.get("children", {}).get("data", []) if isinstance(relationships, dict) else []
                    if isinstance(children, list):
                        for child in children:
                            if not isinstance(child, dict):
                                continue
                            gid = child.get("id")
                            if isinstance(gid, str) and gid:
                                extracted.add(gid)

                return extracted
            except Exception as e:
                logger.debug("subGroup.json からのサブグループ推定に失敗（取得を続行）: %s", e)
                return set()

        # v2.2.x: キャッシュ完全性判定は subGroup.json を優先（groupOrgnizations が stale でも引きずられない）
        expected_ids = _expected_team_ids_from_subgroup_json()

        # subGroup.json から取れない場合のみ、互換のため groupOrgnizations/ を参照
        if not expected_ids:
            org_dir = Path(GROUP_ORGNIZATION_DIR)
            if org_dir.exists():
                logger.info(f"  📂 groupOrgnizations/ディレクトリをスキャン: {org_dir}")

                org_json_files = list(org_dir.glob("*.json"))
                logger.info(f"  📋 プロジェクトJSONファイル数: {len(org_json_files)}個")

                for json_file in org_json_files:
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            proj_data = json.load(f)

                        included = proj_data.get("included", [])
                        subgroup_count = 0
                        for item in included:
                            if (
                                item.get("type") == "group" and
                                item.get("attributes", {}).get("groupType") == "TEAM"
                            ):
                                item_id = item.get("id")
                                if isinstance(item_id, str) and item_id:
                                    expected_ids.add(item_id)
                                    subgroup_count += 1

                        logger.debug(f"    ✓ {json_file.name}: {subgroup_count}個のサブグループを抽出")
                    except Exception as e:
                        logger.warning(f"    ❌ プロジェクトJSON読み込みエラー（{json_file.name}）: {e}")
                        continue
            else:
                logger.info(f"  ℹ️  groupOrgnizations/ディレクトリが存在しません: {org_dir}")

        # 期待されるサブグループが0件なら、subGroups/ のファイル有無で欠損扱いにしない
        if not expected_ids:
            logger.info("  ℹ️  期待されるサブグループIDが0件のため、subGroups/完全性チェックをスキップします")
            return True

        expected_count = len(expected_ids)
        logger.info(f"  📊 期待されるサブグループ総数: {expected_count}個")
        logger.debug(f"  📋 期待されるID一覧（最初10個）: {list(expected_ids)[:10]}")

        subgroups_dir = Path(SUBGROUP_DETAILS_DIR)
        if not subgroups_dir.exists():
            logger.warning(f"  ❌ subGroups/ディレクトリが存在しません: {subgroups_dir}")
            logger.warning(f"     期待: {expected_count}件のサブグループファイル")
            return False

        logger.info(f"  📂 subGroups/ディレクトリを確認: {subgroups_dir}")
        json_files = list(subgroups_dir.glob("*.json"))
        actual_count = len(json_files)

        logger.info(f"  📊 実際の保存ファイル数: {actual_count}個")

        actual_ids = {json_file.stem for json_file in json_files}
        missing_ids = expected_ids - actual_ids
        if missing_ids:
            logger.warning("\n  ⚠️  [欠損検出] subGroups/フォルダに欠損ファイル!")
            logger.warning(
                f"     期待: {expected_count}個 | 実際: {actual_count}個 | 欠損: {len(missing_ids)}個"
            )
            logger.warning(f"     欠損ID一覧（最初10個）: {list(missing_ids)[:10]}")
            if len(missing_ids) > 10:
                logger.debug(f"     欠損ID一覧（すべて）: {sorted(list(missing_ids))}")
            return False

        logger.info(f"  ✅ subGroups/フォルダの完全性確認完了: {actual_count}個すべて揃っている")
        logger.info("[フォルダ完全性チェック終了] 欠損なし\n")
        return True
    except Exception as e:
        logger.debug(f"subGroups/フォルダチェックエラー（取得を続行）: {e}")
        return False

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


def _progress_ok(progress_callback, percent: int, total: int, message: str) -> bool:
    """Run progress callback and treat None as OK (only False means cancel)."""
    if not progress_callback:
        return True
    try:
        result = progress_callback(percent, total, message)
        return result is not False
    except Exception as e:
        logger.debug("progress callback error ignored: %s", e)
        return True


def _clear_dataset_entry_cache():
    """
    データセットエントリーのメモリキャッシュをクリア
    
    グループ関連情報取得後に、コンボボックスのメモリ上のキャッシュが古いままにならないようにクリアする
    目的：
    - データ取得2機能のコンボボックスに古い候補しか表示されない問題を解決
    - container.dataset_mapをクリアして、次回アクセス時にdataset.jsonを再読み込みさせる
    """
    try:
        # UIコンテナをグローバル状態から取得
        # （PySide6アプリケーションの場合、QWidgetはグローバルに参照可能）
        from classes.ui.controllers.ui_controller import main_app_instance
        
        if main_app_instance and hasattr(main_app_instance, 'fetch2_dropdown_widget'):
            fetch2_widget = main_app_instance.fetch2_dropdown_widget
            if hasattr(fetch2_widget, 'clear_cache'):
                fetch2_widget.clear_cache()
                logger.info("UIコントローラー経由でデータセットエントリーキャッシュをクリアしました")
                return
        
        # フォールバック: 直接グローバルレジストリをスキャン
        import gc
        for obj in gc.get_objects():
            try:
                if hasattr(obj, 'clear_cache') and hasattr(obj, 'dataset_map'):
                    obj.clear_cache()
                    logger.info("グローバルレジストリ経由でデータセットエントリーキャッシュをクリアしました")
                    return
            except (TypeError, AttributeError):
                pass
        
        logger.debug("データセットエントリーキャッシュのクリア: 対象コンテナが見つかりませんでした")
        
    except ImportError:
        logger.debug("データセットエントリーキャッシュのクリア: UIコントローラーが利用不可")
    except Exception as e:
        logger.warning("データセットエントリーキャッシュのクリア中にエラー: %s", e)


def _prepare_dataset_chunk_directory() -> Path:
    """dataset.jsonチャンク保存用ディレクトリを初期化して返す"""
    chunk_dir = Path(DATASET_JSON_CHUNKS_DIR)
    if chunk_dir.exists():
        for entry in chunk_dir.iterdir():
            try:
                if entry.is_file():
                    entry.unlink()
                elif entry.is_dir():
                    shutil.rmtree(entry)
            except Exception as cleanup_error:
                logger.warning("チャンクファイルの削除に失敗しました (%s): %s", entry, cleanup_error)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("datasetJsonChunksディレクトリを初期化しました: %s", chunk_dir)
    return chunk_dir


def _prepare_template_chunk_directory() -> Path:
    """template.json用チャンクディレクトリを初期化"""
    chunk_dir = Path(TEMPLATE_JSON_CHUNKS_DIR)
    if chunk_dir.exists():
        for entry in chunk_dir.iterdir():
            try:
                if entry.is_file():
                    entry.unlink()
                elif entry.is_dir():
                    shutil.rmtree(entry)
            except Exception as cleanup_error:
                logger.warning("テンプレートチャンクファイルの削除に失敗しました (%s): %s", entry, cleanup_error)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("templateJsonChunksディレクトリを初期化しました: %s", chunk_dir)
    return chunk_dir


def _prepare_instrument_chunk_directory() -> Path:
    """instruments.json用チャンクディレクトリを初期化"""
    chunk_dir = Path(INSTRUMENT_JSON_CHUNKS_DIR)
    if chunk_dir.exists():
        for entry in chunk_dir.iterdir():
            try:
                if entry.is_file():
                    entry.unlink()
                elif entry.is_dir():
                    shutil.rmtree(entry)
            except Exception as cleanup_error:
                logger.warning("設備チャンクファイルの削除に失敗しました (%s): %s", entry, cleanup_error)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("instrumentJsonChunksディレクトリを初期化しました: %s", chunk_dir)
    return chunk_dir


def _load_json_if_exists(path: str) -> Optional[Dict]:
    """存在する場合のみJSONを読み込む"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.debug("JSONファイルが存在しません: %s", path)
    except Exception as exc:
        logger.warning("JSONファイルの読み込みに失敗しました (%s): %s", path, exc)
    return None


def _resolve_program_id_for_templates(
    default_program_id: str = DEFAULT_PROGRAM_ID,
    output_dir: Optional[str] = None,
) -> str:
    """テンプレート取得用のprogramIdを決定"""
    candidate_paths = []
    if output_dir:
        candidate_paths.append(os.path.join(output_dir, "group.json"))
    candidate_paths.append(GROUP_JSON_PATH)

    for path in candidate_paths:
        group_data = _load_json_if_exists(path)
        if group_data:
            program_id = parse_group_id_from_data(group_data, preferred_program_id=default_program_id)
            if program_id:
                return program_id
    return default_program_id


def _iterate_template_team_ids(output_dir: Optional[str] = None) -> List[str]:
    """テンプレート取得に使用するteamId候補を順序付きで返す"""
    env_override = os.environ.get("RDE_TEMPLATE_TEAM_ID") or os.environ.get("ARIM_TEMPLATE_TEAM_ID")
    if env_override:
        team_id = env_override.strip()
        if team_id:
            logger.info("テンプレート取得: 環境変数からteamId=%sのみを候補として使用", team_id[:12])
            return [team_id]

    def _append_unique(target: List[str], value: Optional[str]) -> None:
        if value and value not in target:
            target.append(value)

    def _extract_children_ids(payload: Dict) -> List[str]:
        children = payload.get("data", {}).get("relationships", {}).get("children", {}).get("data", [])
        if not isinstance(children, list):
            return []
        ids: List[str] = []
        for item in children:
            if isinstance(item, dict):
                child_id = item.get("id")
                if isinstance(child_id, str) and child_id:
                    ids.append(child_id)
        return ids

    def _resolve_self_user_id(target_dir: Optional[str]) -> Optional[str]:
        # output_dir が指定されている場合は、そのディレクトリ配下の self.json のみを参照する。
        # 既定パスへフォールバックすると「別ユーザー/別環境のJSON」が混在し得るため。
        candidate_paths: List[str] = []
        if target_dir:
            candidate_paths.append(os.path.join(target_dir, "self.json"))
        else:
            candidate_paths.append(SELF_JSON_PATH)

        for path in candidate_paths:
            payload = _load_json_if_exists(path)
            if not payload:
                continue
            user_id = payload.get("data", {}).get("id")
            if isinstance(user_id, str) and user_id:
                return user_id
        return None

    def _user_has_project_role(project_item: Dict, user_id: str) -> bool:
        attrs = project_item.get("attributes", {})
        if not isinstance(attrs, dict):
            return False
        roles = attrs.get("roles", [])
        if not isinstance(roles, list):
            return False
        for role in roles:
            if isinstance(role, dict) and role.get("userId") == user_id:
                return True
        return False

    def _team_has_user_role(team_id: str, user_id: str, target_dir: Optional[str]) -> Optional[bool]:
        # None: 判定不能（詳細ファイルが無い/壊れている等）
        # True/False: 判定結果
        # output_dir が指定されている場合は、そのディレクトリ配下の subGroups のみを参照する。
        candidate_paths: List[str] = []
        if target_dir:
            candidate_paths.append(os.path.join(target_dir, "subGroups", f"{team_id}.json"))
        else:
            candidate_paths.append(os.path.join(SUBGROUP_DETAILS_DIR, f"{team_id}.json"))
            candidate_paths.append(os.path.join(LEGACY_SUBGROUP_DETAILS_DIR, f"{team_id}.json"))

        subgroup_detail: Optional[Dict] = None
        for path in candidate_paths:
            subgroup_detail = _load_json_if_exists(path)
            if subgroup_detail:
                break
        if not subgroup_detail:
            return None

        roles = subgroup_detail.get("data", {}).get("attributes", {}).get("roles", [])
        if not isinstance(roles, list):
            return None
        for role in roles:
            if isinstance(role, dict) and role.get("userId") == user_id:
                return True
        return False

    # まずは groupDetail.json / subGroup.json から候補teamIdを抽出
    # NOTE: teamId は「アクセス可能なTEAMグループID」である可能性が高い。
    #       groupDetail.json の included(PROJECT) の children が実運用上の有力候補。
    team_ids: List[str] = []

    # groupDetail.json から「ログインユーザーがロールを持つPROJECTのchildren(TEAM)」を優先的に抽出
    user_id = _resolve_self_user_id(output_dir)
    preferred_team_ids: List[str] = []

    group_detail_paths: List[str] = []
    if output_dir:
        group_detail_paths.append(os.path.join(output_dir, "groupDetail.json"))
    else:
        group_detail_paths.append(GROUP_DETAIL_JSON_PATH)
    for path in group_detail_paths:
        group_detail = _load_json_if_exists(path)
        if not group_detail:
            continue

        # groupDetail.json は PROGRAM の詳細で、data.children は PROJECT を指すことがある。
        # そのため、included 内の PROJECT の children (=TEAM) を候補として採用する。
        included = group_detail.get("included", [])
        if isinstance(included, list):
            for item in included:
                if not isinstance(item, dict):
                    continue
                attrs = item.get("attributes", {})
                if not isinstance(attrs, dict):
                    continue
                group_type = attrs.get("groupType")
                if group_type == "PROJECT":
                    # ユーザーがPROJECTロールを持つなら、そのchildren(TEAM)は使える可能性が高い
                    if user_id and _user_has_project_role(item, user_id):
                        for child_id in _extract_children_ids({"data": item}):
                            _append_unique(preferred_team_ids, child_id)
                    for child_id in _extract_children_ids({"data": item}):
                        _append_unique(team_ids, child_id)
                elif group_type == "TEAM":
                    _append_unique(team_ids, item.get("id"))
        if team_ids:
            logger.debug(
                "テンプレート取得: %s の children から %d 件のteamId候補を抽出",
                os.path.basename(path),
                len(team_ids),
            )
            break

    sub_group_paths: List[str] = []
    if output_dir:
        sub_group_paths.append(os.path.join(output_dir, "subGroup.json"))
    else:
        sub_group_paths.append(SUBGROUP_JSON_PATH)
    for path in sub_group_paths:
        sub_group_data = _load_json_if_exists(path)
        if not sub_group_data:
            continue

        # subGroup.json 自体が PROJECT 詳細で、children に TEAM 群が並ぶことがある
        for child_id in _extract_children_ids(sub_group_data):
            _append_unique(team_ids, child_id)

        # 旧来の included(groupType=TEAM) も互換的に拾う
        included = sub_group_data.get("included", [])
        if isinstance(included, list):
            for item in included:
                if not isinstance(item, dict):
                    continue
                attrs = item.get("attributes", {})
                if isinstance(attrs, dict) and attrs.get("groupType") == "TEAM":
                    _append_unique(team_ids, item.get("id"))

        if team_ids:
            logger.debug(
                "テンプレート取得: %s から %d 件のteamId候補を抽出",
                os.path.basename(path),
                len(team_ids),
            )
            break

    # PROJECTロール経由で候補が取れた場合は、それを優先（TEAM詳細での所属判定に依存しない）
    if preferred_team_ids:
        logger.info(
            "テンプレート取得: PROJECTロールに基づきteamId候補を採用します (preferred=%d, total=%d)",
            len(preferred_team_ids),
            len(team_ids),
        )
        return preferred_team_ids

    # 次に「ログイン中ユーザーが所属するTEAM」に絞り込む（TEAM詳細ファイルがある場合）
    if user_id and team_ids:
        member_team_ids: List[str] = []
        unknown_team_ids: List[str] = []
        for team_id in team_ids:
            verdict = _team_has_user_role(team_id, user_id, output_dir)
            if verdict is True:
                member_team_ids.append(team_id)
            elif verdict is None:
                unknown_team_ids.append(team_id)

        # 所属TEAMが特定できた場合はそれを優先。
        # 特定できない場合は従来通り候補全体を返す。
        if member_team_ids:
            logger.info(
                "テンプレート取得: ログインユーザー所属TEAMに絞り込みました (member=%d, unknown=%d, total=%d)",
                len(member_team_ids),
                len(unknown_team_ids),
                len(team_ids),
            )
            return member_team_ids

    if not team_ids:
        logger.info("テンプレート取得: teamId候補が見つからなかったためデフォルト%sのみを使用", DEFAULT_TEAM_ID)
        team_ids.append(DEFAULT_TEAM_ID)

    return team_ids


def _template_payload_is_preferred(payload: Dict) -> bool:
    data_items = payload.get("data") or []
    if data_items:
        return True
    total_counts = payload.get("meta", {}).get("totalCounts")
    return isinstance(total_counts, int) and total_counts > 0


def _build_dataset_list_query_params(page_size: int, offset: int, search_words: Optional[str]) -> Dict[str, str]:
    params = {
        "sort": "-modified",
        "page[limit]": str(page_size),
        "page[offset]": str(offset),
        "include": "manager,releases",
        "fields[user]": "id,userName,organizationName,isDeleted",
        "fields[release]": "version,releaseNumber",
    }
    if search_words is not None:
        params["searchWords"] = search_words
    return params


def _build_dataset_list_url(query_params: Dict[str, str]) -> str:
    query = urlencode(query_params, quote_via=quote)
    return f"https://rde-api.nims.go.jp/datasets?{query}"


def _record_dataset_list_api_call(
    url: str,
    headers: Dict[str, str],
    status_code: int,
    elapsed_ms: float,
    query_params: Dict[str, str],
    success: bool,
    error: Optional[str] = None,
):
    try:
        record_api_call_for_dataset_list(
            url,
            headers,
            status_code,
            elapsed_ms,
            query_params=query_params,
            success=success,
            error=error,
        )
    except Exception as record_error:
        logger.debug("データセット一覧API記録に失敗しました: %s", record_error)


def _merge_dataset_chunk_payloads(chunks: List[Dict]) -> Dict:
    if not chunks:
        return {"data": []}

    merged: Dict = {}
    first_chunk = chunks[0]
    for key, value in first_chunk.items():
        if key not in _DATASET_RESERVED_KEYS:
            merged[key] = value

    combined_data: List[Dict] = []
    included_map: Dict[tuple, Dict] = {}
    include_present = False

    for chunk in chunks:
        chunk_data = chunk.get("data", [])
        if chunk_data:
            combined_data.extend(chunk_data)

        included_section = chunk.get("included")
        if included_section is not None:
            include_present = True
            for item in included_section:
                item_id = item.get("id")
                item_type = item.get("type")
                if not item_id or not item_type:
                    continue
                key = (item_type, item_id)
                if key not in included_map:
                    included_map[key] = item

    merged["data"] = combined_data
    if include_present:
        merged["included"] = list(included_map.values())

    latest_meta = None
    latest_links = None
    for chunk in reversed(chunks):
        if latest_meta is None and chunk.get("meta") is not None:
            latest_meta = chunk.get("meta")
        if latest_links is None and chunk.get("links"):
            latest_links = chunk.get("links")
        if latest_meta is not None and latest_links is not None:
            break

    if latest_meta is not None:
        merged["meta"] = latest_meta
    if latest_links is not None:
        merged["links"] = latest_links

    return merged


def _merge_dataset_search_payloads(payloads: List[Dict]) -> Dict:
    """Merge multiple dataset payloads produced by different search words."""
    if not payloads:
        return {"data": []}

    merged_data: List[Dict] = []
    seen_ids = set()
    included_map: Dict[tuple, Dict] = {}

    for payload in payloads:
        for item in payload.get("data", []) or []:
            ds_id = item.get("id")
            if ds_id and ds_id not in seen_ids:
                merged_data.append(item)
                seen_ids.add(ds_id)

        for inc in payload.get("included", []) or []:
            inc_id = inc.get("id")
            inc_type = inc.get("type")
            if inc_id and inc_type:
                key = (inc_type, inc_id)
                if key not in included_map:
                    included_map[key] = inc

    base_payload = payloads[-1]
    merged: Dict = {k: v for k, v in base_payload.items() if k not in ("data", "included")}
    merged["data"] = merged_data
    if included_map:
        merged["included"] = list(included_map.values())

    meta = dict(base_payload.get("meta", {}) or {})
    meta["totalCounts"] = len(merged_data)
    merged["meta"] = meta
    return merged


def _download_paginated_resource(
    *,
    base_url: str,
    base_params: Dict[str, str],
    headers: Dict[str, str],
    bearer_token: Optional[str],
    page_size: int,
    timeout: int,
    record_callback: Optional[Callable[..., None]] = None,
    progress_callback: Optional[Callable[[int, int, str], bool]] = None,
    chunk_label: str,
    chunk_dir_factory: Optional[Callable[[], Path]] = None,
    chunk_file_template: Optional[str] = None,
) -> Dict:
    """共通のページング取得ロジック（1000件単位の分割取得用）"""
    import time

    chunk_dir: Optional[Path] = None
    if chunk_dir_factory:
        chunk_dir = chunk_dir_factory()

    offset = 0
    chunk_index = 1
    total_expected = None
    total_processed = 0
    chunk_payloads: List[Dict] = []

    while True:
        params = dict(base_params or {})
        params["page[limit]"] = str(page_size)
        params["page[offset]"] = str(offset)
        query = urlencode(params, quote_via=quote)
        url = f"{base_url}?{query}"

        start_time = time.time()
        resp = api_request(
            "GET",
            url,
            bearer_token=bearer_token,
            headers=headers,
            timeout=timeout,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        if resp is None:
            error_msg = "APIリクエストがNoneを返しました"
            if record_callback:
                record_callback(url, headers, 0, elapsed_ms, success=False, error=error_msg)
            raise RuntimeError(f"{chunk_label}: {error_msg}")

        try:
            resp.raise_for_status()
        except Exception as http_error:
            status_code = getattr(resp, "status_code", 500)
            if record_callback:
                record_callback(
                    url,
                    headers,
                    status_code,
                    elapsed_ms,
                    success=False,
                    error=str(http_error),
                )
            raise

        if record_callback:
            record_callback(url, headers, resp.status_code, elapsed_ms, success=True)

        payload = resp.json()
        chunk_payloads.append(payload)

        if chunk_dir and chunk_file_template:
            chunk_path = chunk_dir / chunk_file_template.format(chunk_index)
            try:
                with open(chunk_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except Exception as write_error:
                logger.warning("%s: チャンクファイル書き込みに失敗しました (%s): %s", chunk_label, chunk_path, write_error)

        chunk_count = len(payload.get("data", []))
        total_processed += chunk_count
        if total_expected is None:
            total_expected = payload.get("meta", {}).get("totalCounts")

        if progress_callback:
            try:
                total_for_progress = int(total_expected) if total_expected is not None else 0
            except Exception:
                total_for_progress = 0

            if not _progress_ok(
                progress_callback,
                int(total_processed),
                int(total_for_progress),
                f"{chunk_label}: {total_processed}/{total_for_progress if total_for_progress else '?'} (chunk={chunk_index}, offset={offset})",
            ):
                raise GroupFetchCancelled("キャンセルされました")

        logger.info(
            "%s: チャンク%04dを取得 (件数=%d, offset=%d)",
            chunk_label,
            chunk_index,
            chunk_count,
            offset,
        )

        if total_expected is not None and total_processed >= total_expected:
            break
        if chunk_count == 0:
            break
        if total_expected is None and chunk_count < page_size:
            break

        offset += page_size
        chunk_index += 1

    if not chunk_payloads:
        return {"data": []}

    merged_payload = _merge_dataset_chunk_payloads(chunk_payloads)
    logger.info(
        "%s: チャンク分割取得完了 (chunks=%d, records=%d, expected=%s)",
        chunk_label,
        len(chunk_payloads),
        total_processed,
        total_expected if total_expected is not None else "unknown",
    )
    return merged_payload


def _download_dataset_list_in_chunks(
    bearer_token: Optional[str],
    headers: Dict[str, str],
    search_words: Optional[str] = None,
    page_size: int = DATASET_LIST_PAGE_SIZE,
) -> Dict:
    import time

    chunk_dir = _prepare_dataset_chunk_directory()
    offset = 0
    chunk_index = 1
    total_expected = None
    total_processed = 0
    chunk_payloads: List[Dict] = []

    while True:
        query_params = _build_dataset_list_query_params(page_size, offset, search_words)
        url = _build_dataset_list_url(query_params)
        start_time = time.time()
        resp = api_request(
            "GET",
            url,
            bearer_token=bearer_token,
            headers=headers,
            timeout=DATASET_LIST_REQUEST_TIMEOUT,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        if resp is None:
            error_msg = "APIリクエストがNoneを返しました"
            _record_dataset_list_api_call(url, headers, 0, elapsed_ms, query_params, False, error_msg)
            raise RuntimeError(f"データセット一覧の取得に失敗しました: {error_msg}")

        try:
            resp.raise_for_status()
        except Exception as http_error:
            status_code = getattr(resp, "status_code", 500)
            _record_dataset_list_api_call(url, headers, status_code, elapsed_ms, query_params, False, str(http_error))
            raise

        _record_dataset_list_api_call(url, headers, resp.status_code, elapsed_ms, query_params, True)

        payload = resp.json()
        chunk_payloads.append(payload)
        chunk_path = chunk_dir / DATASET_CHUNK_FILE_TEMPLATE.format(chunk_index)
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        chunk_count = len(payload.get("data", []))
        total_processed += chunk_count
        if total_expected is None:
            total_expected = payload.get("meta", {}).get("totalCounts")

        logger.info(
            "データセット一覧: チャンク%04dを取得 (件数=%d, offset=%d)",
            chunk_index,
            chunk_count,
            offset,
        )

        if total_expected is not None and total_processed >= total_expected:
            break
        if chunk_count == 0:
            break
        if total_expected is None and chunk_count < page_size:
            break

        offset += page_size
        chunk_index += 1

    merged_payload = _merge_dataset_chunk_payloads(chunk_payloads)
    logger.info(
        "データセット一覧: チャンク分割取得完了 (chunks=%d, records=%d, expected=%s)",
        len(chunk_payloads),
        total_processed,
        total_expected if total_expected is not None else "unknown",
    )
    return merged_payload

def fetch_invoice_schemas(bearer_token, output_dir, progress_callback=None, max_workers: int = 10):
    """
    template.jsonの全テンプレートIDについてinvoiceSchemasを取得し保存する
    v2.1.0: 並列ダウンロード対応（50件以上で自動並列化）
    """
    try:
        from net.http_helpers import parallel_download
        import threading
        
        if progress_callback:
            if not progress_callback(0, 100, f"invoiceSchemas取得を開始しています... (並列: {max_workers})"):
                return "キャンセルされました"
                
        os.makedirs(os.path.join(output_dir, "invoiceSchemas"), exist_ok=True)
        template_json_path = os.path.join(output_dir, "template.json")
        log_path = os.path.join(output_dir, "invoiceSchemas", "invoiceSchemas_fetch.log")

        if progress_callback:
            if not progress_callback(5, 100, f"template.jsonを読み込み中... (並列: {max_workers})"):
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
            if not progress_callback(10, 100, f"取得対象: {len(template_ids)}件のテンプレート (並列: {max_workers})"):
                return "キャンセルされました"

        summary_path = os.path.join(output_dir, "invoiceSchemas", "summary.json")
        # 既存summary.jsonの読み込み
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        else:
            summary = {"success": [], "failed": {}}

        # 旧形式/壊れたsummaryの互換補正
        if not isinstance(summary, dict):
            summary = {"success": [], "failed": {}}
        if not isinstance(summary.get("success"), list):
            summary["success"] = []
        if not isinstance(summary.get("failed"), dict):
            summary["failed"] = {}

        # teamId は template.json 取得時と同様に subGroup.json から抽出した候補を使う
        team_id_candidates = _iterate_template_team_ids(output_dir)
        logger.info("invoiceSchemas取得: teamId候補=%s", [t[:12] for t in team_id_candidates])

        # 並列実行時にsummary/log/summary.jsonを書き換えるためロックを共有
        summary_lock = threading.Lock()

        total_templates = len(template_ids)
        
        # タスクリストを作成（並列実行用）
        tasks = [
            (bearer_token, template_id, output_dir, summary, log_path, summary_path, team_id_candidates, summary_lock)
            for template_id in template_ids
        ]
        
        # 並列ダウンロード実行（50件以上で自動並列化）
        def worker(token, template_id, out_dir, summ, log_p, summ_p, team_ids, lock):
            """ワーカー関数"""
            try:
                return fetch_invoice_schema_from_api(token, template_id, out_dir, summ, log_p, summ_p, team_ids, lock)
            except Exception as e:
                logger.error(f"invoiceSchema取得失敗 (template_id: {template_id}): {e}")
                try:
                    with lock:
                        if not isinstance(summ, dict):
                            return f"failed: {e}"
                        summ.setdefault("failed", {})[template_id] = str(e)
                        with open(summ_p, "w", encoding="utf-8") as f:
                            json.dump(summ, f, ensure_ascii=False, indent=2)
                except Exception:
                    logger.debug("invoiceSchemas取得: summary更新に失敗", exc_info=True)
                return f"failed: {e}"
        
        # プログレスコールバックを調整（10-95%の範囲にマッピング）
        def adjusted_progress_callback(current, total, message):
            if progress_callback:
                progress_percent = 10 + int((current / 100) * 85)  # 10-95%
                return progress_callback(progress_percent, 100, f"並列invoiceSchema取得中: {message}")
            return True
        
        result = parallel_download(
            tasks=tasks,
            worker_function=worker,
            max_workers=max_workers,
            progress_callback=adjusted_progress_callback,
            threshold=50
        )

        # 最終保存
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        if progress_callback:
            progress_callback(100, 100, f"invoiceSchema取得完了 (並列: {max_workers})")
            
        success_count = len(summary.get("success", []))
        failed_count = len(summary.get("failed", {}))
        result_msg = f"invoiceSchema取得完了: 成功={success_count}, 失敗={failed_count}, 総数={total_templates}"
        logger.info(result_msg)
        
        if result['cancelled']:
            return "キャンセルされました"
        
        return result_msg
        
    except Exception as e:
        error_msg = f"invoiceSchema取得処理でエラー: {e}"
        logger.error(error_msg)
        if progress_callback:
            progress_callback(100, 100, f"エラー: {error_msg}")
        return error_msg

def get_self_username_from_json(json_path=None):
    """self.json から userName を取得して返す。存在しない場合は空文字列。"""
    resolved_path = json_path or get_dynamic_file_path("output/rde/data/self.json")
    abs_json = os.path.abspath(resolved_path)
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
def fetch_self_info_from_api(bearer_token=None, output_dir=None, parent_widget=None):
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
    
    # API記録機能の初期化
    import time
    start_time = time.time()
    
    try:
        logger.info("ユーザー情報取得開始")
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        elapsed_ms = (time.time() - start_time) * 1000
        
        # レスポンスチェック
        if resp is None:
            error_msg = "ユーザー情報取得失敗: APIリクエストがNoneを返しました（ネットワークエラーまたはタイムアウト）"
            logger.error(error_msg)
            
            # API記録を追加（失敗）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_self_info
                record_api_call_for_self_info(url, headers, 0, elapsed_ms, False, "APIリクエスト失敗")
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            raise Exception(error_msg)
        
        # HTTPステータスコードチェック（v2.0.1改善）
        if resp.status_code == 401:
            error_msg = "認証エラー（401）: Bearer Tokenが無効または期限切れです。再ログインしてください。"
            logger.error(error_msg)
            
            # API記録を追加（401）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_self_info
                record_api_call_for_self_info(url, headers, 401, elapsed_ms, False, error_msg)
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            raise Exception(error_msg)
        elif resp.status_code == 403:
            error_msg = "アクセス拒否（403）: このユーザーにはユーザー情報取得の権限がありません。"
            logger.error(error_msg)
            
            # API記録を追加（403）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_self_info
                record_api_call_for_self_info(url, headers, 403, elapsed_ms, False, error_msg)
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            raise Exception(error_msg)
        elif resp.status_code != 200:
            error_msg = f"ユーザー情報取得失敗: HTTPステータス {resp.status_code}"
            logger.error(error_msg)
            
            # API記録を追加（その他エラー）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_self_info
                record_api_call_for_self_info(url, headers, resp.status_code, elapsed_ms, False, error_msg)
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            raise Exception(error_msg)
        
        # JSONパース
        try:
            data = resp.json()
        except Exception as json_error:
            error_msg = f"ユーザー情報のJSONパース失敗: {json_error}"
            logger.error(error_msg)
            
            # API記録を追加（パースエラー）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_self_info
                record_api_call_for_self_info(url, headers, resp.status_code, elapsed_ms, False, f"JSON解析エラー: {json_error}")
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            raise Exception(error_msg)
        
        # ファイル保存
        output_dir = output_dir or OUTPUT_RDE_DATA_DIR
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "self.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"self.json取得・保存完了: {save_path}")
        
        # API記録を追加（成功）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_self_info
            record_api_call_for_self_info(url, headers, 200, elapsed_ms, True)
        except Exception as e:
            logger.debug(f"API記録追加失敗: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"self.json取得・保存失敗: {e}")
        # v2.0.1: エラーを呼び出し元に伝播させる
        raise


def fetch_all_data_entrys_info(bearer_token, output_dir=None, progress_callback=None, parallel_threshold: int = 50, max_workers: int = 10):
    """
    dataset.json内の全データセットIDでfetch_data_entry_info_from_apiを呼び出す
    
    改善版: データセット総数を事前計算し、プログレス更新頻度を向上
    v2.1.0: 並列ダウンロード対応（50件以上で自動並列化）
    
    Args:
        bearer_token: 認証トークン
        output_dir: 出力ディレクトリ
        progress_callback: プログレスコールバック関数 (current, total, message) -> bool
        parallel_threshold: 並列化閾値（デフォルト: 50件）
        max_workers: 最大並列ワーカー数（デフォルト: 10）
    """
    try:
        from net.http_helpers import parallel_download
        
        output_dir = output_dir or OUTPUT_RDE_DATA_DIR
        os.makedirs(output_dir, exist_ok=True)
        dataset_json = os.path.join(output_dir, "dataset.json")
        
        if not os.path.exists(dataset_json):
            logger.error(f"dataset.jsonが存在しません: {dataset_json}")
            return
        
        if progress_callback:
            if not progress_callback(0, 0, f"データエントリ情報取得準備中... (並列: {max_workers})"):
                return "キャンセルされました"
            
        with open(dataset_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        datasets = data.get("data", [])
        total_datasets = len(datasets)
        logger.info(f"データエントリ情報取得開始: {total_datasets}件のデータセット処理")
        
        if progress_callback:
            if not progress_callback(0, total_datasets, f"データエントリ取得開始: 総数={total_datasets}件 (並列: {max_workers})"):
                return "キャンセルされました"
        
        # タスクリストを作成（並列実行用）
        tasks = [(bearer_token, ds.get("id")) for ds in datasets if ds.get("id")]
        
        # 並列ダウンロード実行（50件以上で自動並列化）
        def worker(token, ds_id):
            """ワーカー関数"""
            try:
                fetch_data_entry_info_from_api(token, ds_id)
                return "success"
            except Exception as e:
                logger.error(f"データエントリ処理失敗: ds_id={ds_id}, error={e}")
                return f"failed: {e}"
        
        # 件数ベースで進捗を通知（QProgressDialog側で current/total と ETA を表示）
        def adjusted_progress_callback(current, total, message):
            if progress_callback:
                return progress_callback(int(current), int(total), f"データエントリ取得中: {message}")
            return True
        
        result = parallel_download(
            tasks=tasks,
            worker_function=worker,
            max_workers=max_workers,
            progress_callback=adjusted_progress_callback,
            threshold=parallel_threshold,
            progress_mode="count",
        )
        
        result_msg = (f"データエントリ情報取得完了: "
                     f"成功={result['success_count']}, "
                     f"失敗={result['failed_count']}, "
                     f"スキップ={result['skipped_count']}, "
                     f"総数={result['total']}")
        logger.info(result_msg)
        
        if progress_callback:
            progress_callback(100, 100, result_msg)
        
        if result['cancelled']:
            return "キャンセルされました"
        
        return result_msg
        
    except Exception as e:
        error_msg = f"fetch_all_data_entrys_info処理失敗: {e}"
        logger.error(error_msg)
        if progress_callback:
            progress_callback(100, 100, f"エラー: {error_msg}")
        raise




def fetch_data_entry_info_from_api(bearer_token, dataset_id, output_dir=None):
    """
    指定データセットIDのデータエントリ情報をAPIから取得し、dataEntry.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&sort=-created&page%5Boffset%5D=0&page%5Blimit%5D=24&include=owner%2Csample%2CthumbnailFile%2Cfiles"
    target_dir = output_dir or DATA_ENTRY_DIR
    save_path = os.path.join(target_dir, f"{dataset_id}.json")
    
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
        
        os.makedirs(target_dir, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"データエントリ取得・保存完了: {dataset_id}.json -> {save_path}")
        
    except Exception as e:
        logger.error(f"データエントリ取得・保存失敗: dataset_id={dataset_id}, error={e}")
        raise


def fetch_invoice_info_from_api(bearer_token, entry_id, output_dir=None):
    """指定エントリIDのインボイス情報をAPIから取得し、invoice.jsonとして保存"""
    url = f"https://rde-api.nims.go.jp/invoices/{entry_id}?include=submittedBy%2CdataOwner%2Cinstrument"
    target_dir = output_dir or INVOICE_DIR
    save_path = os.path.join(target_dir, f"{entry_id}.json")
    
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
        
        os.makedirs(target_dir, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"インボイス取得・保存完了: {entry_id}.json -> {save_path}")
        
    except Exception as e:
        logger.error(f"インボイス取得・保存失敗: entry_id={entry_id}, error={e}")
        raise


def fetch_all_invoices_info(bearer_token, output_dir=None, progress_callback=None, max_workers: int = 10):
    """
    dataEntry.json内の全エントリIDでfetch_invoice_info_from_apiを呼び出す
    
    改善版: データセット数とタイル数から総予定取得数を事前計算し、
    プログレス更新頻度を大幅に向上させて処理の進行状況を明確化
    v2.1.0: 並列ダウンロード対応（50件以上で自動並列化）
    
    Args:
        bearer_token: 認証トークン
        output_dir: 出力ディレクトリ
        progress_callback: プログレスコールバック関数 (current, total, message) -> bool
    """
    try:
        from net.http_helpers import parallel_download
        
        resolved_root = output_dir or OUTPUT_RDE_DATA_DIR
        dataentry_dir = os.path.join(resolved_root, "dataEntry")
        invoice_dir = os.path.join(resolved_root, "invoice")
        
        if not os.path.exists(dataentry_dir):
            logger.error(f"dataEntryディレクトリが存在しません: {dataentry_dir}")
            return
        
        # === 事前カウント：総予定取得数を計算 ===
        if progress_callback:
            if not progress_callback(0, 100, f"インボイス総数を計算中... (並列: {max_workers})"):
                return "キャンセルされました"
        
        dataentry_files = glob.glob(os.path.join(dataentry_dir, "*.json"))
        
        # 全データエントリファイルを読み込み、総エントリ数を計算
        entry_list = []  # [entry_id, ...]
        
        logger.info(f"インボイス情報取得開始: {len(dataentry_files)}件のデータエントリファイルを解析中")
        
        for file_path in dataentry_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                entries = data.get("data", [])
                for entry in entries:
                    entry_id = entry.get("id")
                    if entry_id:
                        entry_list.append(entry_id)
                        
            except Exception as e:
                logger.error(f"データエントリファイル読み込み失敗: file={file_path}, error={e}")
        
        total_entries = len(entry_list)
        logger.info(f"インボイス取得計画: 総数={total_entries}件")
        
        if progress_callback:
            msg = f"インボイス取得開始 (データセット: {len(dataentry_files)}件, タイル総数: {total_entries}件, 並列: {max_workers})"
            if not progress_callback(5, 100, msg):
                return "キャンセルされました"
        
        # タスクリストを作成（並列実行用）
        tasks = [(bearer_token, entry_id) for entry_id in entry_list]
        
        # 並列ダウンロード実行（50件以上で自動並列化）
        def worker(token, entry_id):
            """ワーカー関数"""
            try:
                fetch_invoice_info_from_api(token, entry_id, invoice_dir)
                return "success"
            except Exception as e:
                logger.error(f"インボイス処理失敗: entry_id={entry_id}, error={e}")
                return f"failed: {e}"
        
        # 件数ベースで進捗を通知（QProgressDialog側で current/total と ETA を表示）
        def adjusted_progress_callback(current, total, message):
            if progress_callback:
                return progress_callback(int(current), int(total), f"インボイス取得中: {message}")
            return True
        
        result = parallel_download(
            tasks=tasks,
            worker_function=worker,
            max_workers=max_workers,
            progress_callback=adjusted_progress_callback,
            threshold=50,
            progress_mode="count",
        )
        
        # === 完了処理 ===
        result_msg = (f"インボイス情報取得完了: "
                     f"成功={result['success_count']}, "
                     f"失敗={result['failed_count']}, "
                     f"スキップ={result['skipped_count']}, "
                     f"総数={result['total']}")
        logger.info(result_msg)
        
        if progress_callback:
            progress_callback(100, 100, result_msg)
        
        if result['cancelled']:
            return "キャンセルされました"
        
        return result_msg
        
    except Exception as e:
        error_msg = f"fetch_all_invoices_info処理失敗: {e}"
        logger.error(error_msg)
        if progress_callback:
            progress_callback(100, 100, f"エラー: {error_msg}")
        raise


def fetch_dataset_info_respectively_from_api(bearer_token, dataset_id, output_dir=None):
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
        
        target_dir = output_dir or get_dynamic_file_path("output/rde/data/datasets")
        os.makedirs(target_dir, exist_ok=True)
        save_path = os.path.join(target_dir, f"{dataset_id}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"データセット詳細取得・保存完了: {dataset_id}.json -> {save_path}")
        
    except Exception as e:
        logger.error(f"データセット詳細取得・保存失敗: dataset_id={dataset_id}, error={e}")
        raise

# --- API取得系 ---
def fetch_all_dataset_info(
    bearer_token,
    output_dir=None,
    onlySelf=False,
    searchWords=None,
    searchWordsBatch: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], bool]] = None,
    parallel_threshold: int = 20,
    max_workers: int = 8,
):
    """データセット情報をAPIから取得し、dataset.jsonとして保存しつつ進捗を通知する"""
    user_name = get_self_username_from_json()

    # パス区切りを統一
    output_dir = os.path.normpath(output_dir or OUTPUT_RDE_DATA_DIR)
    detail_dir = os.path.join(output_dir, "datasets")

    search_query = None
    if onlySelf is True:
        if searchWords and len(searchWords) > 0:
            logger.debug("searchWords: %s", searchWords)
            search_query = searchWords
        else:
            logger.debug("UserName: %s", user_name)
            search_query = user_name

    sanitized_batch: List[str] = []
    if searchWordsBatch:
        seen = set()
        for word in searchWordsBatch:
            normalized = (word or "").strip()
            if normalized and normalized not in seen:
                sanitized_batch.append(normalized)
                seen.add(normalized)

    search_targets: List[Optional[str]] = []
    if sanitized_batch:
        search_targets.extend(sanitized_batch)
    elif search_query is not None:
        search_targets.append(search_query)
    else:
        search_targets.append(None)

    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    dataset_payload: Dict = {}
    emit_progress = progress_callback if progress_callback else lambda *_args, **_kwargs: True
    try:
        start_detail = f"検索セット: {len(search_targets)}件, " if len(search_targets) > 1 else ""
        start_message = f"データセット一覧取得を開始しています ({start_detail}並列: 自動)"
        if not emit_progress(0, 100, start_message):
            return "キャンセルされました"

        target_payloads: List[Dict] = []
        for idx, target in enumerate(search_targets, start=1):
            if target:
                label = target
            else:
                label = "ユーザー名" if onlySelf else "全件"
            logger.info(
                "データセット一覧: 検索%02d/%02dを実行中 (条件=%s)",
                idx,
                len(search_targets),
                label,
            )
            chunk_payload = _download_dataset_list_in_chunks(
                bearer_token=bearer_token,
                headers=headers,
                search_words=target,
            )
            target_payloads.append(chunk_payload)

        if len(target_payloads) == 1:
            dataset_payload = target_payloads[0]
        else:
            dataset_payload = _merge_dataset_search_payloads(target_payloads)

        meta = dict(dataset_payload.get("meta") or {})
        if sanitized_batch:
            meta["searchWordsBatch"] = sanitized_batch
        elif search_query:
            meta["searchWords"] = search_query
        dataset_payload["meta"] = meta

        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "dataset.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(dataset_payload, f, ensure_ascii=False, indent=2)

        logger.info("データセット情報(dataset.json)取得・保存完了")

    except Exception as e:
        logger.error("データセット情報取得・保存失敗: %s (searchTargets=%s)", e, search_targets)
        raise

    datasets = dataset_payload.get("data", [])
    total_datasets = len(datasets)
    if not emit_progress(5, 100, f"データセット一覧取得完了 (計画: {total_datasets}件, 並列: 自動)"):
        return "キャンセルされました"

    datasets_with_meta = []
    for ds in datasets:
        ds_id = ds.get("id")
        attr = ds.get("attributes", {})
        modified_at = attr.get("modified", "")
        modified_dt = parse_datetime(modified_at) if modified_at else None
        datasets_with_meta.append((ds_id, modified_dt))

    # 取得が必要なデータセット件数を先に数える（キャッシュ利用時も総数表示用）
    fetch_targets = []
    for ds_id, modified_dt in datasets_with_meta:
        if not ds_id or not modified_dt:
            continue

        detail_path = os.path.join(detail_dir, f"{ds_id}.json")
        file_mtime = datetime.fromtimestamp(os.path.getmtime(detail_path), timezone.utc) if os.path.exists(detail_path) else None
        needs_fetch = file_mtime is None or file_mtime < modified_dt
        fetch_targets.append((ds_id, modified_dt, detail_path, needs_fetch))

    total_targets = len(fetch_targets)
    total_fetch_targets = sum(1 for _ds_id, _modified_dt, _path, need in fetch_targets if need)
    parallel_enabled = total_fetch_targets >= parallel_threshold and total_fetch_targets > 0

    if not emit_progress(
        6,
        100,
        f"データセット詳細取得準備 (計画: {total_targets}件, 取得対象: {total_fetch_targets}件, 並列: {'有効' if parallel_enabled else '無効'})",
    ):
        return "キャンセルされました"

    fetched_count = 0

    if parallel_enabled:
        tasks = [
            (bearer_token, ds_id, detail_dir)
            for ds_id, _modified_dt, _path, needs_fetch in fetch_targets
            if needs_fetch and ds_id
        ]

        def detail_worker(token, ds_id, out_dir):
            try:
                fetch_dataset_info_respectively_from_api(token, ds_id, output_dir=out_dir)
                return "success"
            except Exception as worker_error:
                logger.error("データセット詳細取得失敗 (並列): %s", worker_error)
                return "failed"

        def detail_progress(current, total, message):
            # 進捗は件数ベースで通知（show_progress_dialog 側で current/total/ETA を表示）
            return emit_progress(int(current), int(total), f"データセット詳細取得中 (並列: 有効) {message}")

        try:
            from net.http_helpers import parallel_download

            result = parallel_download(
                tasks=tasks,
                worker_function=detail_worker,
                max_workers=max_workers,
                progress_callback=detail_progress,
                threshold=1,
                progress_mode="count",
            )
        except Exception as parallel_error:
            logger.error("データセット詳細並列取得でエラー: %s", parallel_error)
            result = {"success_count": 0, "failed_count": total_fetch_targets, "cancelled": False}

        if result.get("cancelled"):
            return "キャンセルされました"

        fetched_count = result.get("success_count", 0)
        if not emit_progress(95, 100, f"データセット詳細取得完了 (並列: 有効, 成功: {fetched_count}/{total_fetch_targets})"):
            return "キャンセルされました"
    else:
        processed_count = 0
        for ds_id, modified_dt, detail_path, needs_fetch in fetch_targets:
            processed_count += 1
            if not ds_id:
                continue

            try:
                if needs_fetch:
                    fetch_dataset_info_respectively_from_api(bearer_token, ds_id, output_dir=detail_dir)
                    fetched_count += 1
                else:
                    logger.info("%s.jsonは最新です。再取得は行いません。", ds_id)
            except Exception as e:
                logger.error("ds_id=%s の処理中にエラー: %s", ds_id, e)

            denominator = total_targets if total_targets else 1
            progress_percent = 5 + int((processed_count / denominator) * 90)
            status_message = (
                f"データセット詳細処理 {processed_count}/{denominator}"
                f" (取得対象: {fetched_count}/{total_fetch_targets}, 並列: 無効)"
            )
            if not emit_progress(progress_percent, 100, status_message):
                return "キャンセルされました"

    final_parallel = "有効" if parallel_enabled else "無効"
    if not emit_progress(
        100,
        100,
        f"データセット処理完了 (計画: {total_datasets}件, 実行: {fetched_count}件, 並列: {final_parallel})",
    ):
        return "キャンセルされました"


def fetch_instrument_type_info_from_api(bearer_token, save_path):
    """
    装置タイプ情報をAPIから取得し、instrumentType.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    import time
    start_time = time.time()
    
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
        elapsed_ms = (time.time() - start_time) * 1000
        
        if resp is None:
            # API記録を追加（失敗）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_instrument_type
                record_api_call_for_instrument_type(url, headers, 0, elapsed_ms, False, "APIリクエスト失敗")
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            logger.error("装置タイプ情報の取得に失敗しました: リクエストエラー")
            return
        
        resp.raise_for_status()
        data = resp.json()
        save_json(data, *save_path)
        logger.info("装置タイプ情報の取得・保存に成功しました: %s", os.path.join(*save_path))
        
        # API記録を追加（成功）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_instrument_type
            record_api_call_for_instrument_type(url, headers, 200, elapsed_ms, True)
        except Exception as e:
            logger.debug(f"API記録追加失敗: {e}")
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        
        # API記録を追加（エラー）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_instrument_type
            record_api_call_for_instrument_type(url, headers, 500, elapsed_ms, False, str(e))
        except Exception as e2:
            logger.debug(f"API記録追加失敗: {e2}")
        
        logger.error("装置タイプ情報の取得・保存に失敗しました: %s", e)

def fetch_organization_info_from_api(bearer_token, save_path):
    """
    組織情報をAPIから取得し、organization.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    import time
    start_time = time.time()
    
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
        elapsed_ms = (time.time() - start_time) * 1000
        
        if resp is None:
            # API記録を追加（失敗）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_organization
                record_api_call_for_organization(url, headers, 0, elapsed_ms, False, "APIリクエスト失敗")
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            logger.error("組織情報の取得に失敗しました: リクエストエラー")
            return
        
        resp.raise_for_status()
        data = resp.json()
        save_json(data, *save_path)
        logger.info("組織情報の取得・保存に成功しました: %s", os.path.join(*save_path))
        
        # API記録を追加（成功）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_organization
            record_api_call_for_organization(url, headers, 200, elapsed_ms, True)
        except Exception as e:
            logger.debug(f"API記録追加失敗: {e}")
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        
        # API記録を追加（エラー）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_organization
            record_api_call_for_organization(url, headers, 500, elapsed_ms, False, str(e))
        except Exception as e2:
            logger.debug(f"API記録追加失敗: {e2}")
        
        logger.error("組織情報の取得・保存に失敗しました: %s", e)


def fetch_template_info_from_api(bearer_token, output_dir=None, progress_callback=None):
    """
    テンプレート情報をAPIから取得し、template.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        target_dir = output_dir or OUTPUT_RDE_DATA_DIR
        program_id = _resolve_program_id_for_templates(output_dir=target_dir)
        team_candidates = _iterate_template_team_ids(output_dir=target_dir)

        selected_payload: Optional[Dict] = None
        selected_team_id: Optional[str] = None
        last_payload: Optional[Dict] = None

        for idx, team_id in enumerate(team_candidates, 1):
            logger.info("テンプレート取得: teamId候補(%d/%d)=%s を試行します", idx, len(team_candidates), team_id)

            if progress_callback:
                _progress_ok(
                    progress_callback,
                    0,
                    0,
                    f"テンプレート情報: teamId候補({idx}/{len(team_candidates)})={team_id} を取得中...",
                )

            base_params = {
                "programId": program_id,
                "teamId": team_id,
                "sort": "id",
                "include": "instruments",
                "fields[instrument]": "nameJa,nameEn",
            }
            chunk_dir = _prepare_template_chunk_directory()

            def _reuse_chunk_dir(chunk_dir=chunk_dir):
                return chunk_dir

            try:
                payload = _download_paginated_resource(
                    base_url=TEMPLATE_API_BASE_URL,
                    base_params=base_params,
                    headers=headers,
                    bearer_token=None,
                    page_size=TEMPLATE_PAGE_SIZE,
                    timeout=TEMPLATE_REQUEST_TIMEOUT,
                    record_callback=lambda url, hdrs, status_code, elapsed_ms, success, error=None: record_api_call_for_template(
                        url,
                        hdrs,
                        status_code,
                        elapsed_ms,
                        success=success,
                        error=error,
                    ),
                    progress_callback=progress_callback,
                    chunk_label="テンプレート情報",
                    chunk_dir_factory=_reuse_chunk_dir,
                    chunk_file_template=TEMPLATE_CHUNK_FILE_TEMPLATE,
                )
            except GroupFetchCancelled:
                raise
            except Exception as per_team_error:
                logger.warning(
                    "テンプレート取得: teamId=%s の取得に失敗しました。次の候補を試行します: %s",
                    team_id,
                    per_team_error,
                )
                if progress_callback:
                    _progress_ok(
                        progress_callback,
                        0,
                        0,
                        f"テンプレート情報: teamId候補({idx}/{len(team_candidates)}) 失敗。次の候補へ...",
                    )
                continue

            last_payload = payload
            if _template_payload_is_preferred(payload):
                selected_payload = payload
                selected_team_id = team_id
                logger.info("テンプレート取得: teamId=%s のレスポンスを採用しました", team_id)
                break

            logger.info("テンプレート取得: teamId=%s では有意なデータが得られませんでした。次の候補を試行します。", team_id)

        if selected_payload is None:
            if last_payload is None:
                raise RuntimeError("テンプレート情報: 全teamId候補で取得に失敗しました")

            selected_payload = last_payload
            selected_team_id = team_candidates[-1] if team_candidates else DEFAULT_TEAM_ID
            logger.info(
                "テンプレート取得: 有意なデータが得られなかったため最後のレスポンスを採用します (teamId=%s)",
                selected_team_id,
            )

        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, "template.json"), "w", encoding="utf-8") as f:
            json.dump(selected_payload, f, ensure_ascii=False, indent=2)
        logger.info(
            "テンプレート(template.json)の取得・保存に成功しました (teamId=%s, 候補数=%d)。",
            selected_team_id,
            len(team_candidates),
        )
    except Exception as e:
        logger.error("テンプレートの取得・保存に失敗しました: %s", e)

def fetch_instruments_info_from_api(bearer_token, output_dir=None, progress_callback=None):
    """
    設備リスト情報をAPIから取得し、instruments.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-instrument-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        if progress_callback:
            _progress_ok(progress_callback, 0, 0, "設備情報取得を開始しています...")
        base_params = {
            "programId": DEFAULT_PROGRAM_ID,
            "sort": "id",
        }
        data = _download_paginated_resource(
            base_url=INSTRUMENT_API_BASE_URL,
            base_params=base_params,
            headers=headers,
            bearer_token=None,
            page_size=INSTRUMENT_PAGE_SIZE,
            timeout=INSTRUMENT_REQUEST_TIMEOUT,
            record_callback=lambda url, hdrs, status_code, elapsed_ms, success, error=None: record_api_call_for_instruments(
                url,
                hdrs,
                status_code,
                elapsed_ms,
                success=success,
                error=error,
            ),
            progress_callback=progress_callback,
            chunk_label="設備情報",
            chunk_dir_factory=_prepare_instrument_chunk_directory,
            chunk_file_template=INSTRUMENT_CHUNK_FILE_TEMPLATE,
        )
        target_dir = output_dir or OUTPUT_RDE_DATA_DIR
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, "instruments.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("設備情報(instruments.json)の取得・保存に成功しました。")
    except Exception as e:
        logger.error("設備情報の取得・保存に失敗しました: %s", e)

def fetch_licenses_info_from_api(bearer_token, output_dir=None, progress_callback=None):
    """
    利用ライセンスマスタ情報をAPIから取得し、licenses.jsonとして保存
    v1.18.4: Bearer Token自動選択対応
    """
    import time
    start_time = time.time()
    
    url = "https://rde-api.nims.go.jp/licenses"
    headers = {
        "Accept": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/"
    }
    try:
        if progress_callback:
            _progress_ok(progress_callback, 0, 1, "利用ライセンス情報取得を開始しています...")
        # v1.18.4: bearer_token=Noneで自動選択させる
        resp = api_request("GET", url, bearer_token=None, headers=headers, timeout=10)
        elapsed_ms = (time.time() - start_time) * 1000
        
        if resp is None:
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_licenses
                record_api_call_for_licenses(url, headers, 0, elapsed_ms, False, "APIリクエスト失敗")
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            logger.error("利用ライセンス情報の取得に失敗しました: リクエストエラー")
            return
        resp.raise_for_status()
        data = resp.json()
        target_dir = output_dir or OUTPUT_RDE_DATA_DIR
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, "licenses.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("利用ライセンス情報(licenses.json)の取得・保存に成功しました。")
        logger.info(f"利用ライセンス情報取得完了: {len(data.get('data', []))}件のライセンス")

        if progress_callback:
            _progress_ok(progress_callback, 1, 1, "利用ライセンス情報取得が完了しました")
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_licenses
            record_api_call_for_licenses(url, headers, 200, elapsed_ms, True)
        except Exception as e:
            logger.debug(f"API記録追加失敗: {e}")
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_licenses
            record_api_call_for_licenses(url, headers, 500, elapsed_ms, False, str(e))
        except Exception as e2:
            logger.debug(f"API記録追加失敗: {e2}")
        logger.error("利用ライセンス情報の取得・保存に失敗しました: %s", e)
        logger.error(f"利用ライセンス情報取得失敗: {e}")


# --- グループ情報取得・WebView・info生成 ---
def fetch_group_info_from_api(url, headers, save_path, bearer_token=None):
    import time
    start_time = time.time()
    
    try:
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)  # refactored to use api_request_helper
        elapsed_ms = (time.time() - start_time) * 1000
        
        if resp is None:
            # API記録を追加（失敗）
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_group
                group_type = "subgroup" if "project_group_id" in url else ("detail" if "groupDetail" in str(save_path) else "root")
                record_api_call_for_group(url, headers, 0, elapsed_ms, group_type, False, "APIリクエスト失敗")
            except Exception as e:
                logger.debug(f"API記録追加失敗: {e}")
            
            raise Exception("グループ情報取得失敗: リクエストエラー")
        
        resp.raise_for_status()
        data = resp.json()
        save_json(data, *save_path)
        
        # API記録を追加（成功）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_group
            group_type = "subgroup" if "project_group_id" in url else ("detail" if "groupDetail" in str(save_path) else "root")
            record_api_call_for_group(url, headers, 200, elapsed_ms, group_type, True)
        except Exception as e:
            logger.debug(f"API記録追加失敗: {e}")
        
        return data
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        
        # API記録を追加（エラー）
        try:
            from classes.basic.core.api_recording_wrapper import record_api_call_for_group
            group_type = "subgroup" if "project_group_id" in url else ("detail" if "groupDetail" in str(save_path) else "root")
            record_api_call_for_group(url, headers, 500, elapsed_ms, group_type, False, str(e))
        except Exception as e2:
            logger.debug(f"API記録追加失敗: {e2}")
        
        raise


@dataclass
class GroupFetchResult:
    group_data: Dict
    program_details: Dict[str, Dict]
    project_details: Dict[str, Dict]
    project_groups_by_program: Dict[str, List[Dict]]
    selected_program_id: Optional[str]
    selected_project_id: Optional[str]
    selected_program_data: Optional[Dict]
    selected_project_data: Optional[Dict]
    subgroup_summary: Dict[str, Dict[str, int]]


class GroupFetchCancelled(Exception):
    """グループ階層取得処理がユーザー操作で中断されたことを示す内部例外"""


def _extract_group_items(payload: Dict) -> List[Dict]:
    return [item for item in payload.get("included", []) if item.get("type") == "group"]


def run_group_hierarchy_pipeline(
    bearer_token: str,
    parent_widget=None,
    preferred_program_id: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], bool]] = None,
    headers: Optional[Dict[str, str]] = None,
    force_project_dialog: bool = False,
    force_program_dialog: bool = False,
    force_download: bool = False,
    skip_dialog: bool = False,
    max_workers: int = 10,
) -> GroupFetchResult:
    """root→program→project→subgroup の取得フローを共通実装で実行する
    
    v2.1.22追加:
    - force_download引数を追加（subGroups個別ファイルの強制取得対応）
    """
    from classes.basic.ui.group_selection_dialog import show_group_selection_if_needed

    def emit_progress(percent: int, total_or_message: str, message: str = None):
        """Progress emitter supporting both 2 and 3 argument calls.
        - emit_progress(percent, message) 
        - emit_progress(percent, total, message)
        """
        actual_message = message if message is not None else total_or_message
        if not _progress_ok(progress_callback, percent, 100, actual_message):
            raise GroupFetchCancelled("キャンセルされました")

    headers = headers or _make_headers(
        bearer_token,
        host="rde-api.nims.go.jp",
        origin="https://rde.nims.go.jp",
        referer="https://rde.nims.go.jp/",
    )

    emit_progress(5, "ルートグループ取得中...")
    group_url = "https://rde-api.nims.go.jp/groups/root?include=children%2Cmembers"
    group_json_path = [OUTPUT_DIR, "rde", "data", "group.json"]
    group_data = fetch_group_info_from_api(group_url, headers, group_json_path)

    program_groups = _extract_group_items(group_data)
    if not program_groups:
        raise Exception("Rootレスポンスに参照可能なプログラムが含まれていません。")

    program_ids = {item.get("id") for item in program_groups if item.get("id")}
    selected_program_id = preferred_program_id if preferred_program_id in program_ids else None
    if not selected_program_id:
        selection = show_group_selection_if_needed(
            program_groups,
            parent_widget,
            context_name="プログラム（Root Group）",
            force_dialog=force_program_dialog and not skip_dialog,
            preferred_group_id=preferred_program_id,
            remember_context=PROGRAM_SELECTION_CONTEXT,
            auto_select_saved=True if skip_dialog else not force_program_dialog,
        )
        if not selection:
            raise GroupFetchCancelled("プログラム選択がキャンセルされました")
        selected_program_id = selection["id"]

    emit_progress(15, "プログラム詳細取得中...")
    program_details: Dict[str, Dict] = {}
    selected_program_data: Optional[Dict] = None

    # 速度最適化: プログラム詳細は選択済みの1件のみ取得
    selected_program_name = "名称不明"
    for program in program_groups:
        if program.get("id") == selected_program_id:
            selected_program_name = program.get("attributes", {}).get("name", "名称不明")
            break

    detail_url = f"https://rde-api.nims.go.jp/groups/{selected_program_id}?include=children%2Cmembers"
    save_path = [GROUP_PROJECT_DIR, f"{selected_program_id}.json"]
    emit_progress(25, f"プログラム取得: {selected_program_name[:30]}...")
    selected_program_data = fetch_group_info_from_api(detail_url, headers, save_path)
    if not selected_program_data:
        raise Exception("プログラム詳細の取得に失敗しました。")
    program_details[selected_program_id] = selected_program_data

    save_json(selected_program_data, GROUP_DETAIL_JSON_PATH)


    project_groups_by_program: Dict[str, List[Dict]] = {}
    program_projects = _extract_group_items(selected_program_data)
    project_groups_by_program[selected_program_id] = program_projects

    if not program_projects:
        raise Exception("選択されたプログラムに紐づくプロジェクトが見つかりません。")

    # 速度最適化: プロジェクト詳細は選択後に1件のみ取得
    selection = show_group_selection_if_needed(
        program_projects,
        parent_widget,
        context_name="プロジェクトグループ（Detail）",
        force_dialog=force_project_dialog and not skip_dialog,
        remember_context=PROJECT_SELECTION_CONTEXT,
        auto_select_saved=True if skip_dialog else True,
    )
    if not selection:
        raise GroupFetchCancelled("プロジェクト選択がキャンセルされました")
    selected_project_id = selection["id"]

    emit_progress(35, "プロジェクト詳細取得中...")
    project_details: Dict[str, Dict] = {}
    project_meta: Dict[str, Dict[str, str]] = {}
    selected_project_name = selection.get("attributes", {}).get("name", "名称不明")
    detail_url = f"https://rde-api.nims.go.jp/groups/{selected_project_id}?include=children%2Cmembers"
    emit_progress(50, f"プロジェクト取得: {selected_project_name[:30]}...")
    selected_project_data = fetch_group_info_from_api(
        detail_url,
        headers,
        [GROUP_ORGNIZATION_DIR, f"{selected_project_id}.json"],
    )
    project_details[selected_project_id] = selected_project_data
    project_meta[selected_project_id] = {"name": selected_project_name, "program_id": selected_program_id}

    save_json(selected_project_data, SUBGROUP_JSON_PATH)

    # relationships(parent/children) に対する追加詳細取得（ancestors付き）
    emit_progress(58, "関係グループ詳細取得準備中...")
    fetch_relationship_group_details(
        bearer_token=bearer_token,
        sub_group_data=selected_project_data,
        headers=headers,
        progress_callback=emit_progress,
        base_progress=58,
        progress_range=7,
        destination_dir=SUBGROUP_REL_DETAILS_DIR,
        force_download=force_download,
        max_workers=max_workers,
    )

    emit_progress(60, "サブグループ詳細取得中...")
    subgroup_summary: Dict[str, Dict[str, int]] = {}
    project_id = selected_project_id
    project_data = selected_project_data
    project_name = project_meta.get(project_id, {}).get("name", "名称不明")
    emit_progress(70, f"サブグループ展開: {project_name[:30]}...")
    success, fail, errors = fetch_all_subgroups(
        bearer_token=bearer_token,
        sub_group_data=project_data,
        headers=headers,
        progress_callback=emit_progress,
        base_progress=65,
        progress_range=30,
        destination_dir=SUBGROUP_DETAILS_DIR,
        legacy_dir=LEGACY_SUBGROUP_DETAILS_DIR,
        project_group_id=project_id,
        project_group_name=project_name,
        force_download=force_download,
        max_workers=max_workers,
    )

    subgroup_summary[project_id] = {
        "success": success,
        "fail": fail,
        "errors": len(errors),
        "relationship_success": 0,
        "relationship_fail": 0,
        "relationship_skipped": 0,
    }

    emit_progress(100, "グループ階層取得完了")

    return GroupFetchResult(
        group_data=group_data,
        program_details=program_details,
        project_details=project_details,
        project_groups_by_program=project_groups_by_program,
        selected_program_id=selected_program_id,
        selected_project_id=selected_project_id,
        selected_program_data=selected_program_data,
        selected_project_data=selected_project_data,
        subgroup_summary=subgroup_summary,
    )
def parse_group_id_from_data_old(data, preferred_program_id=None):
    """
    included配列からグループIDを抽出
    
    Args:
        data: group.json等のレスポンスデータ
        preferred_program_id: 優先するプログラムID (None時は最初のgroupを返す)
    
    Returns:
        str: グループID
    """
    included = data.get("included", [])
    
    # 優先IDが指定されている場合は検索
    if preferred_program_id:
        for item in included:
            if (item.get("type") == "group" and 
                item.get("id") == preferred_program_id):
                return item["id"]
        
        # 見つからない場合は警告
        logger.warning(f"指定されたプログラムID '{preferred_program_id[:20]}...' が見つかりません。最初のgroupを使用します。")
    
    # デフォルト: 最初のgroupを返す
    for item in included:
        if item.get("type") == "group" and "id" in item:
            return item["id"]
    
    return None


def fetch_all_subgroups(
    bearer_token: str,
    sub_group_data: dict,
    headers: dict,
    progress_callback=None,
    base_progress: int = 70,
    progress_range: int = 30,
    destination_dir: Optional[str] = None,
    legacy_dir: Optional[str] = None,
    project_group_id: Optional[str] = None,
    project_group_name: Optional[str] = None,
    force_download: bool = False,
    max_workers: int = 10,
):
    """
    複数サブグループの個別詳細を一括取得して保存（v2.1.19改修）
    
    subGroup.jsonのincluded配列から全サブグループIDを抽出し、
    各サブグループの詳細情報を個別にAPIで取得して
    output/rde/data/subGroups/{subgroup_id}.json に保存します（legacy互換でsubgroups/にも保存可能）。
    
    v2.1.21改修:
    - force_download引数を追加。False時は既存ファイルがあればスキップ（個別ファイル確認）
    
    Args:
        bearer_token: 認証トークン
        sub_group_data: subGroup.jsonのデータ
        headers: HTTPヘッダ
        progress_callback: プログレスコールバック関数
        base_progress: プログレスバーの開始位置（%）
        progress_range: プログレスバーの範囲（%）
        force_download: True時は既存ファイルを上書き、False時はスキップ
    
    Returns:
        tuple: (成功数, 失敗数, エラーメッセージリスト)
    """
    import time
    from pathlib import Path
    
    resolved_dir = destination_dir
    if not resolved_dir:
        try:
            resolved_dir = get_dynamic_file_path("subgroups")
        except Exception:
            resolved_dir = SUBGROUP_DETAILS_DIR

    target_dir = Path(resolved_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    legacy_target = None
    if legacy_dir:
        legacy_target = Path(legacy_dir)
        legacy_target.mkdir(parents=True, exist_ok=True)
    
    # included配列から type="group" かつ groupType="TEAM" を抽出（v2.1.17修正：TEAMはサブグループを示す）
    included = sub_group_data.get("included", [])
    subgroups = [
        item for item in included 
        if item.get("type") == "group" 
        and item.get("attributes", {}).get("groupType") == "TEAM"
    ]

    # included に無い場合は data.relationships.children をフォールバックで利用（要求仕様: relationshipsベースで全取得）
    if not subgroups:
        rel_ids = _collect_relationship_group_ids(sub_group_data)
        if rel_ids:
            logger.info("includedにTEAMが無いためrelationshipsからサブグループIDを補完します: %s件", len(rel_ids))
            subgroups = [{"id": gid, "attributes": {"name": gid}, "from_relationships": True} for gid in rel_ids]
        else:
            logger.info("サブグループが見つかりませんでした。")
            return (0, 0, [])
    
    logger.info(f"\n[サブグループ個別取得ループ開始] v2.1.24")
    logger.info(f"  🔄 ループ処理対象: {len(subgroups)}件のサブグループ")
    logger.info(f"  🔧 force_download: {force_download}")
    logger.info(f"  💾 保存先: {target_dir}\n")
    
    success_count = 0
    fail_count = 0
    skipped_count = 0
    error_messages = []

    # 速度最適化: 既存ファイルを除外し、件数が多い場合は並列化
    download_targets: list[tuple[str, str]] = []
    for subgroup in subgroups:
        subgroup_id = subgroup.get("id", "")
        subgroup_name = subgroup.get("attributes", {}).get("name", "名称不明")
        if not subgroup_id:
            continue
        save_path = target_dir / f"{subgroup_id}.json"
        if save_path.exists() and not force_download:
            skipped_count += 1
            continue
        download_targets.append((subgroup_id, subgroup_name))

    def _download_one(subgroup_id: str, subgroup_name: str) -> dict:
        save_path = target_dir / f"{subgroup_id}.json"
        if save_path.exists() and not force_download:
            return {"status": "skipped"}

        subgroup_url = f"https://rde-api.nims.go.jp/groups/{subgroup_id}?include=children%2Cmembers"
        start_time = time.time()
        try:
            resp = api_request("GET", subgroup_url, bearer_token=bearer_token, headers=headers, timeout=10)
            elapsed_ms = (time.time() - start_time) * 1000

            if resp is None:
                try:
                    from classes.basic.core.api_recording_wrapper import record_api_call_for_subgroup_detail
                    record_api_call_for_subgroup_detail(
                        subgroup_url,
                        headers,
                        0,
                        elapsed_ms,
                        subgroup_id,
                        subgroup_name,
                        step_index=1,
                        success=False,
                        error="APIリクエスト失敗",
                    )
                except Exception:
                    pass
                return {"status": "failed", "error": "APIリクエスト失敗"}

            resp.raise_for_status()
            subgroup_detail = resp.json()

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(subgroup_detail, f, ensure_ascii=False, indent=2)
            if legacy_target:
                legacy_path = legacy_target / f"{subgroup_id}.json"
                with open(legacy_path, "w", encoding="utf-8") as f:
                    json.dump(subgroup_detail, f, ensure_ascii=False, indent=2)

            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_subgroup_detail
                record_api_call_for_subgroup_detail(
                    subgroup_url,
                    headers,
                    200,
                    elapsed_ms,
                    subgroup_id,
                    subgroup_name,
                    step_index=1,
                    success=True,
                )
            except Exception:
                pass

            return {"status": "success"}
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            try:
                from classes.basic.core.api_recording_wrapper import record_api_call_for_subgroup_detail
                record_api_call_for_subgroup_detail(
                    subgroup_url,
                    headers,
                    500,
                    elapsed_ms,
                    subgroup_id,
                    subgroup_name,
                    step_index=1,
                    success=False,
                    error=str(e),
                )
            except Exception:
                pass
            return {"status": "failed", "error": str(e)}

    if download_targets:
        from net.http_helpers import parallel_download

        def _pd_progress(progress_percent: int, _total: int, message: str) -> bool:
            mapped_progress = base_progress + int((progress_percent / 100.0) * max(progress_range, 1))
            msg = f"サブグループ取得中... {message}"
            return _progress_ok(progress_callback, mapped_progress, 100, msg)

        result = parallel_download(
            tasks=download_targets,
            worker_function=_download_one,
            max_workers=max(1, int(max_workers)),
            progress_callback=_pd_progress if progress_callback else None,
            threshold=10,
        )

        success_count += int(result.get("success_count", 0))
        fail_count += int(result.get("failed_count", 0))
        skipped_count += int(result.get("skipped_count", 0))

        for item in result.get("errors", []) or []:
            task = item.get("task")
            err = item.get("error")
            if isinstance(task, (list, tuple)) and len(task) >= 2:
                error_messages.append(f"サブグループ {task[1]}: {err}")
            else:
                error_messages.append(f"サブグループ取得失敗: {err}")
    
    # 結果サマリー
    logger.info(f"\n[サブグループ個別取得ループ完了] v2.1.24")
    logger.info(f"  ✅ 成功: {success_count}件")
    logger.info(f"  ❌ 失敗: {fail_count}件")
    logger.info(f"  ⏭️  スキップ: {skipped_count}件")
    logger.info(f"  📊 合計: {success_count + fail_count + skipped_count}件")
    
    if error_messages:
        logger.warning(f"  失敗したサブグループ（最初3件）:")
        for err in error_messages[:3]:
            logger.warning(f"    - {err}")
        if len(error_messages) > 3:
            logger.warning(f"    ... 他 {len(error_messages) - 3}件")
    
    logger.info("[サブグループ個別取得ループ終了]\n")
    
    return (success_count, fail_count, error_messages)


def _collect_relationship_group_ids(sub_group_data: dict) -> list[str]:
    """Extract unique group IDs from parent/children relationships."""
    relationship_ids: list[str] = []

    def _append_id(data_obj: dict | None) -> None:
        if not isinstance(data_obj, dict):
            return
        gid = data_obj.get("id")
        if isinstance(gid, str) and gid and gid not in relationship_ids:
            relationship_ids.append(gid)

    relationships = sub_group_data.get("data", {}).get("relationships", {})
    if not isinstance(relationships, dict):
        return relationship_ids

    _append_id(relationships.get("parent", {}).get("data"))

    children = relationships.get("children", {}).get("data", [])
    if isinstance(children, list):
        for child in children:
            _append_id(child)

    return relationship_ids


def fetch_relationship_group_details(
    bearer_token: str,
    sub_group_data: dict,
    headers: dict,
    progress_callback=None,
    base_progress: int = 85,
    progress_range: int = 10,
    destination_dir: Optional[str] = None,
    force_download: bool = False,
    max_workers: int = 10,
):
    """Fetch additional group details for relationship IDs in subGroup.json.

    The API call uses include=ancestors,members to keep ancestor context and
    membership information. Each response is stored under
    output/rde/data/subGroupsAncestors/{group_id}.json. Existing files are
    preserved unless force_download is True.
    """
    import time
    from pathlib import Path

    resolved_dir = destination_dir or SUBGROUP_REL_DETAILS_DIR

    target_dir = Path(resolved_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    group_ids = _collect_relationship_group_ids(sub_group_data)
    if not group_ids:
        logger.info("関係グループIDが見つからないため追加取得をスキップします")
        return (0, 0, 0)

    logger.info("[関係グループ詳細取得開始] 対象: %s件", len(group_ids))

    success_count = 0
    fail_count = 0
    skipped_count = 0

    download_ids: list[str] = []
    for group_id in group_ids:
        save_path = target_dir / f"{group_id}.json"
        if save_path.exists() and not force_download:
            skipped_count += 1
            continue
        download_ids.append(group_id)

    def _download_one(group_id: str) -> dict:
        save_path = target_dir / f"{group_id}.json"
        if save_path.exists() and not force_download:
            return {"status": "skipped"}

        detail_url = f"https://rde-api.nims.go.jp/groups/{group_id}?include=ancestors%2Cmembers"
        start_time = time.time()
        try:
            resp = api_request("GET", detail_url, bearer_token=bearer_token, headers=headers, timeout=10)
            if resp is None:
                return {"status": "failed", "error": "APIリクエスト失敗"}
            resp.raise_for_status()
            payload = resp.json()
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            _ = (time.time() - start_time) * 1000
            return {"status": "success"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    if download_ids:
        from net.http_helpers import parallel_download

        def _pd_progress(progress_percent: int, _total: int, message: str) -> bool:
            mapped_progress = base_progress + int((progress_percent / 100.0) * max(progress_range, 1))
            msg = f"関係グループ取得中... {message}"
            return _progress_ok(progress_callback, mapped_progress, 100, msg)

        result = parallel_download(
            tasks=[(gid,) for gid in download_ids],
            worker_function=_download_one,
            max_workers=max(1, int(max_workers)),
            progress_callback=_pd_progress if progress_callback else None,
            threshold=10,
        )

        success_count += int(result.get("success_count", 0))
        fail_count += int(result.get("failed_count", 0))
        skipped_count += int(result.get("skipped_count", 0))

    logger.info(
        "[関係グループ詳細取得完了] 成功=%s, 失敗=%s, スキップ=%s",
        success_count,
        fail_count,
        skipped_count,
    )

    return (success_count, fail_count, skipped_count)


def parse_group_id_from_data(data, preferred_program_id=None):
    """
    included配列からグループIDを抽出
    
    Args:
        data: group.json等のレスポンスデータ
        preferred_program_id: 優先するプログラムID (None時は最初のgroupを返す)
    
    Returns:
        str: グループID
    """
    included = data.get("included", [])
    
    # 優先IDが指定されている場合は検索
    if preferred_program_id:
        for item in included:
            if (item.get("type") == "group" and 
                item.get("id") == preferred_program_id):
                return item["id"]
        
        # 見つからない場合は警告
        logger.warning(f"指定されたプログラムID '{preferred_program_id[:20]}...' が見つかりません。最初のgroupを使用します。")
    
    # デフォルト: 最初のgroupを返す
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

def show_fetch_confirmation_dialog(parent, onlySelf, searchWords, searchWordsList: Optional[List[str]] = None):
    """
    基本情報取得の確認ダイアログを表示
    """
    from qt_compat.widgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QTextEdit
    import json
    
    # 取得対象の情報を生成
    fetch_mode = "検索モード" if onlySelf else "全データセット取得モード"
    keyword_lines = None
    if searchWordsList:
        trimmed = [word for word in searchWordsList if word]
        if trimmed:
            limit = 10
            preview = trimmed[:limit]
            keyword_lines = "\n".join(f"• {word}" for word in preview)
            if len(trimmed) > limit:
                keyword_lines += f"\n• ... (他{len(trimmed) - limit}件)"
            search_text = f"検索キーワード({len(trimmed)}件):\n{keyword_lines}"
        elif searchWords:
            search_text = f"検索キーワード: {searchWords}"
        else:
            search_text = "検索キーワード: 自分のユーザー名"
    elif searchWords:
        search_text = f"検索キーワード: {searchWords}"
    else:
        search_text = "検索キーワード: 自分のユーザー名"
    
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
        "出力先": OUTPUT_RDE_DATA_DIR,
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

    if searchWordsList:
        payload_info["検索キーワード一覧"] = searchWordsList
    
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
def fetch_group_info_stage(
    bearer_token,
    progress_callback=None,
    program_id=None,
    parent_widget=None,
    force_program_dialog: bool = False,
    force_download: bool = False,
    force_refresh_subgroup: bool = False,
    skip_dialog: bool = False,
    max_workers: int = 10,
):
    """
    段階2: グループ関連情報取得（グループ・詳細・サブグループ）
    
    v2.1.16追加:
    - program_id引数を追加（グループ選択機能対応）
    
    v2.1.17追加:
    - parent_widget引数を追加（グループ選択ダイアログ表示用）
    - group.json/groupDetail.json取得後にグループ選択ダイアログ統合
    - 複数サブグループの個別詳細取得機能（output/rde/data/subGroups/）

    v2.1.20追加:
    - force_program_dialog引数を追加（UX-GROUP-SEL-ALL-FLOWS対応。プログラム選択を必ず表示）
    
    v2.1.22追加:
    - subGroups/ディレクトリの個別ファイル欠損検出機能
    
    v2.2.10追加:
    - skip_dialog引数を追加（サブグループ自動更新時に確認ダイアログを抑止）
    """
    try:
        force_project_dialog = os.environ.get('FORCE_PROJECT_GROUP_DIALOG', '0') == '1'
        
        # ログ出力：実行モード確認
        if skip_dialog:
            logger.info("[自動更新モード] グループ選択ダイアログを抑止し、保存済み選択を自動適用します")
        else:
            logger.info("[通常モード] グループ選択ダイアログを表示します")

        def stage_progress(percent: int, total: int, message: str):
            if progress_callback:
                return progress_callback(percent, total, message)
            return True

        # 3つのメインファイル + subGroups/フォルダの完全性をチェック
        group_files_ready = all(
            Path(path).exists() for path in (GROUP_JSON_PATH, GROUP_DETAIL_JSON_PATH, SUBGROUP_JSON_PATH)
        )
        subgroups_complete = _subgroups_folder_complete() if group_files_ready else False

        reuse_allowed = not force_download and not force_refresh_subgroup
        if reuse_allowed and group_files_ready and subgroups_complete:
            logger.info("グループ関連情報: 既存ファイルは完全。取得をスキップします")
            # 既存のsubGroup.jsonから関係グループ詳細を補完（ancestors付与）
            try:
                with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
                    existing_subgroup = json.load(f)
            except Exception as e:
                logger.warning("既存subGroup.jsonの読み込みに失敗しました: %s", e)
                existing_subgroup = None

            if existing_subgroup:
                headers = _make_headers(
                    bearer_token,
                    host="rde-api.nims.go.jp",
                    origin="https://rde.nims.go.jp",
                    referer="https://rde.nims.go.jp/",
                )
                fetch_relationship_group_details(
                    bearer_token=bearer_token,
                    sub_group_data=existing_subgroup,
                    headers=headers,
                    progress_callback=progress_callback,
                    base_progress=85,
                    progress_range=10,
                    destination_dir=SUBGROUP_REL_DETAILS_DIR,
                    force_download=False,
                    max_workers=max_workers,
                )

            if progress_callback:
                progress_callback(100, 100, "既存ファイルを再利用しました")
            return "グループ関連情報: 既存ファイルを再利用しました"

        result = run_group_hierarchy_pipeline(
            bearer_token=bearer_token,
            parent_widget=parent_widget,
            preferred_program_id=program_id,
            progress_callback=stage_progress,
            force_project_dialog=force_project_dialog,
            force_program_dialog=force_program_dialog,
            force_download=force_download,
            skip_dialog=skip_dialog,
            max_workers=max_workers,
        )

        total_success = sum(item.get("success", 0) for item in result.subgroup_summary.values())
        total_fail = sum(item.get("fail", 0) for item in result.subgroup_summary.values())
        result_msg = (
            f"グループ関連情報取得が完了しました（サブグループ: 成功 {total_success}件, 失敗 {total_fail}件）"
        )
        logger.info(result_msg)
        
        # グループ関連情報取得後、データセットエントリーキャッシュをクリア
        _clear_dataset_entry_cache()
        
        if progress_callback:
            progress_callback(100, 100, "グループ関連情報取得完了")
        return result_msg

    except GroupFetchCancelled:
        logger.info("グループ関連情報取得はキャンセルされました")
        return "キャンセルされました"
    except Exception as e:
        error_msg = f"グループ関連情報取得でエラーが発生しました: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
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
def fetch_sample_info_stage(bearer_token, progress_callback=None, max_workers: int = 10):
    """
    段階4: サンプル情報取得
    v2.1.1: 並列ダウンロード対応（50件以上で自動並列化）
    """
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
        
        if progress_callback:
            if not progress_callback(15, 100, f"サンプル情報取得準備中... ({total_samples}件)"):
                return "キャンセルされました"
        
        # Material API用のトークンを明示的に取得
        from config.common import load_bearer_token
        material_token = load_bearer_token('rde-material.nims.go.jp')
        
        # 並列化用タスクリスト作成
        tasks = [
            (material_token, included.get("id", ""), sample_dir)
            for included in sub_group_included
            if included.get("id")
        ]
        
        # プログレスコールバックラッパー
        def sample_progress_callback(current, total, message):
            """サンプル取得進捗を通知（20-90%にマッピング）"""
            if progress_callback:
                # parallel_download()からは(progress_percent, 100, message)で呼ばれる
                # currentは0-100のパーセント値なので、20-90%範囲にマッピング
                mapped_percent = 20 + int((current / 100.0) * 70)
                return progress_callback(mapped_percent, 100, message)
            return True
        
        # 並列ダウンロード実行（50件以上で自動並列化）
        from net.http_helpers import parallel_download
        
        result = parallel_download(
            tasks=tasks,
            worker_function=_fetch_single_sample_worker,
            max_workers=max_workers,
            progress_callback=sample_progress_callback,
            threshold=50  # 50サンプル以上で並列化
        )
        
        # 結果の集計
        success_count = result.get("success_count", 0)
        skipped_count = result.get("skipped_count", 0)
        failed_count = result.get("failed_count", 0)
        cancelled = result.get("cancelled", False)
        errors = result.get("errors", [])
        
        if cancelled:
            logger.warning(f"サンプル情報取得がキャンセルされました: {success_count}件成功, {skipped_count}件スキップ")
            return "キャンセルされました"
        
        # エラーログ出力
        if errors:
            logger.error(f"サンプル情報取得でエラーが{len(errors)}件発生:")
            for err in errors[:10]:  # 最初の10件のみ
                logger.error(f"  - {err}")
    
    if progress_callback:
        if not progress_callback(100, 100, "サンプル情報取得完了"):
            return "キャンセルされました"
    
    return f"サンプル情報取得が完了しました。成功: {success_count}件, スキップ: {skipped_count}件, 失敗: {failed_count}件"

def _fetch_single_sample_worker(material_token, group_id_sample, sample_dir):
    """
    並列処理用ワーカー関数: 単一サンプル情報の取得
    
    Args:
        material_token: Material API認証トークン
        group_id_sample: サンプルグループID
        sample_dir: 保存先ディレクトリ
        
    Returns:
        str: "success"/"skipped"/"failed"
    """
    try:
        if not group_id_sample:
            return "skipped"
        
        sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")
        
        # 既存ファイルがある場合はスキップ
        if os.path.exists(sample_json_path):
            logger.debug(f"既存ファイルをスキップ: {sample_json_path}")
            return "skipped"
        
        url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
        
        headers_sample = _make_headers(
            material_token, 
            host="rde-material-api.nims.go.jp", 
            origin="https://rde-entry-arim.nims.go.jp", 
            referer="https://rde-entry-arim.nims.go.jp/"
        )
        
        resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
        
        if resp is None:
            logger.warning(f"サンプル情報取得失敗 (リクエスト失敗): {group_id_sample}")
            return "failed"
        
        if resp.status_code == 404:
            logger.debug(f"サンプル情報が見つかりません: {group_id_sample}")
            return "skipped"
            
        if resp.status_code != 200:
            logger.warning(f"サンプル情報取得失敗 (HTTP {resp.status_code}): {group_id_sample}")
            return "failed"
        
        resp.raise_for_status()
        data = resp.json()
        
        with open(sample_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"サンプル情報保存完了: {sample_json_path}")
        return "success"
        
    except Exception as e:
        logger.error(f"サンプル情報({group_id_sample})の取得に失敗: {e}")
        return "failed"


def _fetch_single_sample_worker_force(material_token, group_id_sample, sample_dir, force_download=False):
    """force_download対応版のサンプル取得ワーカー"""
    try:
        if not group_id_sample:
            return "skipped"

        sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")

        if force_download and os.path.exists(sample_json_path):
            try:
                os.remove(sample_json_path)
            except Exception as remove_error:
                logger.debug(f"既存サンプルファイル削除失敗を無視: {remove_error}")
        elif not force_download and os.path.exists(sample_json_path):
            logger.debug(f"既存ファイルをスキップ: {sample_json_path}")
            return "skipped"

        url = (
            "https://rde-material-api.nims.go.jp/samples?"
            f"groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
        )
        headers_sample = _make_headers(
            material_token,
            host="rde-material-api.nims.go.jp",
            origin="https://rde-entry-arim.nims.go.jp",
            referer="https://rde-entry-arim.nims.go.jp/",
        )

        resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
        if resp is None:
            logger.warning(f"サンプル情報取得失敗 (リクエスト失敗): {group_id_sample}")
            return "failed"

        if resp.status_code == 404:
            logger.debug(f"サンプル情報が見つかりません: {group_id_sample}")
            return "skipped"

        if resp.status_code != 200:
            logger.warning(f"サンプル情報取得失敗 (HTTP {resp.status_code}): {group_id_sample}")
            return "failed"

        resp.raise_for_status()
        data = resp.json()

        with open(sample_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"サンプル情報保存完了: {sample_json_path}")
        return "success"

    except Exception as e:
        logger.error(f"サンプル情報({group_id_sample})の取得・保存に失敗しました: {e}")
        return f"failed: {e}"

@stage_error_handler("データセット情報取得")
def fetch_dataset_info_stage(
    bearer_token,
    onlySelf=False,
    searchWords=None,
    searchWordsBatch: Optional[List[str]] = None,
    progress_callback=None,
    max_workers: int = 10,
):
    """段階5: データセット情報取得"""
    result = fetch_all_dataset_info(
        bearer_token,
        output_dir=os.path.join(OUTPUT_DIR, "rde", "data"),
        onlySelf=onlySelf,
        searchWords=searchWords,
        searchWordsBatch=searchWordsBatch,
        progress_callback=progress_callback,
        max_workers=max_workers,
    )

    return result or "データセット情報取得が完了しました"

@stage_error_handler("データエントリ情報取得")
def fetch_data_entry_stage(bearer_token, progress_callback=None, max_workers: int = 10):
    """段階6: データエントリ情報取得"""
    result = fetch_all_data_entrys_info(
        bearer_token,
        output_dir=os.path.join(OUTPUT_DIR, "rde", "data"),
        progress_callback=progress_callback,
        max_workers=max_workers,
    )

    return result or "データエントリ情報取得が完了しました"

@stage_error_handler("インボイス情報取得")
def fetch_invoice_stage(bearer_token, progress_callback=None, max_workers: int = 10):
    """段階7: インボイス情報取得"""
    result = fetch_all_invoices_info(
        bearer_token,
        output_dir=os.path.join(OUTPUT_DIR, "rde", "data"),
        progress_callback=progress_callback,
        max_workers=max_workers,
    )

    return result or "インボイス情報取得が完了しました"

@stage_error_handler("テンプレート・設備・ライセンス情報取得")
def fetch_template_instrument_stage(bearer_token, progress_callback=None, max_workers: int = 10):
    """段階7: テンプレート・設備・ライセンス情報取得"""
    if progress_callback:
        if not progress_callback(15, 100, "テンプレート情報取得中..."):
            return "キャンセルされました"

    def _map_percent(current: int, total: int, start: int, span: int) -> int:
        try:
            c = int(current)
        except Exception:
            c = 0
        try:
            t = int(total)
        except Exception:
            t = 0

        if t <= 0:
            return int(start)
        if c < 0:
            c = 0
        if c > t:
            c = t
        return int(start + int((c / max(t, 1)) * span))

    def template_progress(current, total, message):
        if not progress_callback:
            return True
        mapped = _map_percent(current, total, 15, 35)  # 15% → 50%
        return _progress_ok(progress_callback, mapped, 100, str(message))

    # テンプレート取得（ページング進捗を 15→50% にマップ）
    fetch_template_info_from_api(bearer_token, progress_callback=template_progress)
    
    # 速度最適化: instruments/licenses は独立なので並列実行
    if progress_callback:
        if not progress_callback(50, 100, "設備・利用ライセンス情報取得中..."):
            return "キャンセルされました"

    resolved_workers = 1
    try:
        resolved_workers = max(1, int(max_workers))
    except Exception:
        resolved_workers = 1

    if resolved_workers <= 1:
        def instruments_progress(current, total, message):
            if not progress_callback:
                return True
            mapped = _map_percent(current, total, 50, 35)  # 50% → 85%
            return _progress_ok(progress_callback, mapped, 100, str(message))

        fetch_instruments_info_from_api(bearer_token, progress_callback=instruments_progress)
        if progress_callback:
            if not progress_callback(85, 100, "利用ライセンス情報取得中..."):
                return "キャンセルされました"
        fetch_licenses_info_from_api(bearer_token)
    else:
        from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
        import threading
        import time

        state_lock = threading.Lock()
        # 進捗状態（各タスクは自分の state を更新するだけ。UIへの反映はメインループがまとめて行う）
        states = {
            "instruments": {"current": 0, "total": 0, "message": "設備情報取得中..."},
            "licenses": {"current": 0, "total": 1, "message": "利用ライセンス情報取得中..."},
        }

        def make_state_updater(name: str):
            def _update(current, total, message):
                with state_lock:
                    try:
                        states[name]["current"] = int(current)
                    except Exception:
                        states[name]["current"] = 0
                    try:
                        states[name]["total"] = int(total)
                    except Exception:
                        states[name]["total"] = 0
                    states[name]["message"] = str(message)
                return True

            return _update

        def instruments_job():
            fetch_instruments_info_from_api(bearer_token, progress_callback=make_state_updater("instruments"))

        def licenses_job():
            # licenses は単発なので擬似的に 0/1 → 1/1 を更新
            updater = make_state_updater("licenses")
            updater(0, 1, "利用ライセンス情報取得中...")
            fetch_licenses_info_from_api(bearer_token)
            updater(1, 1, "利用ライセンス情報取得完了")

        with ThreadPoolExecutor(max_workers=min(resolved_workers, 2)) as executor:
            future_to_name = {
                executor.submit(instruments_job): "instruments",
                executor.submit(licenses_job): "licenses",
            }

            remaining = set(future_to_name.keys())
            completed = 0
            total = len(remaining)

            # ポーリングしながら進捗表示を更新
            while remaining:
                done, not_done = wait(remaining, timeout=0.2, return_when=FIRST_COMPLETED)

                # 進捗の合成（平均進捗率）
                if progress_callback:
                    with state_lock:
                        snapshots = {k: dict(v) for k, v in states.items()}

                    fractions = []
                    for name, st in snapshots.items():
                        t = int(st.get("total") or 0)
                        c = int(st.get("current") or 0)
                        if t > 0:
                            c = min(max(c, 0), t)
                            fractions.append(float(c) / float(t))
                        else:
                            fractions.append(0.0)

                    overall = sum(fractions) / max(len(fractions), 1)
                    mapped = 50 + int(overall * 35)  # 50% → 85%
                    msg = (
                        f"設備: {snapshots['instruments']['current']}/{snapshots['instruments']['total'] or '?'} | "
                        f"ライセンス: {snapshots['licenses']['current']}/{snapshots['licenses']['total'] or '?'}"
                    )
                    if not _progress_ok(progress_callback, mapped, 100, msg):
                        return "キャンセルされました"

                # 完了 future を処理
                for future in done:
                    name = future_to_name[future]
                    # 例外はここで再送出して stage_error_handler に拾わせる
                    future.result()
                    completed += 1
                    remaining.remove(future)

                    if progress_callback:
                        mapped = 50 + int((completed / max(total, 1)) * 35)
                        if not progress_callback(mapped, 100, f"取得完了: {name} ({completed}/{total})"):
                            return "キャンセルされました"
    
    if progress_callback:
        if not progress_callback(100, 100, "テンプレート・設備・ライセンス情報取得完了"):
            return "キャンセルされました"
    
    return "テンプレート・設備・ライセンス情報取得が完了しました"

@stage_error_handler("invoiceSchema情報取得")
def fetch_invoice_schema_stage(bearer_token, progress_callback=None, max_workers: int = 10):
    """段階8: invoiceSchema情報取得"""
    if progress_callback:
        if not progress_callback(10, 100, "invoiceSchema情報取得中..."):
            return "キャンセルされました"
    
    output_dir = OUTPUT_RDE_DATA_DIR
    result = fetch_invoice_schemas(bearer_token, output_dir, progress_callback, max_workers=max_workers)
    
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
            
            # グループIDの解析（v2.1.16: program_id優先対応）
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

def auto_refresh_subgroup_json(bearer_token, progress_callback=None, force_refresh_subgroup: bool = False):
    """
    サブグループ作成成功後にsubGroup.jsonを自動再取得する
    
    v2.1.17更新:
    - parent_widget=None を渡す（自動更新のためダイアログ表示なし）
    """
    try:
        if progress_callback:
            if not progress_callback(20, 100, "サブグループ情報自動更新中..."):
                return "キャンセルされました"
        
        logger.info("サブグループ作成成功 - subGroup.json自動更新開始")
        result = fetch_group_info_stage(
            bearer_token,
            progress_callback,
            program_id=None,
            parent_widget=None,
            force_program_dialog=False,
            force_download=False,
            force_refresh_subgroup=force_refresh_subgroup,
            skip_dialog=True,
        )
        
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

def execute_individual_stage(
    stage_name,
    bearer_token,
    webview=None,
    onlySelf=False,
    searchWords=None,
    searchWordsBatch: Optional[List[str]] = None,
    progress_callback=None,
    parent_widget=None,
    force_program_dialog: bool = False,
    force_download: bool = False,
    parallel_max_workers: Optional[int] = None,
):
    """指定された段階を個別実行する"""
    if stage_name not in STAGE_FUNCTIONS:
        return f"不正な段階名です: {stage_name}"
    
    # セパレータの場合は実行しない
    if STAGE_FUNCTIONS[stage_name] is None:
        return f"セパレータアイテムは実行できません: {stage_name}"
    
    logger.info(f"個別段階実行開始: {stage_name}")
    
    try:
        func = STAGE_FUNCTIONS[stage_name]
        
        resolved_workers: Optional[int] = None
        try:
            if parallel_max_workers is not None:
                resolved_workers = int(parallel_max_workers)
                if resolved_workers < 1:
                    resolved_workers = None
        except Exception:
            resolved_workers = None

        # 関数のシグネチャに応じて引数を調整
        if stage_name == "データセット情報":
            result = func(
                bearer_token,
                onlySelf=onlySelf,
                searchWords=searchWords,
                 searchWordsBatch=searchWordsBatch,
                progress_callback=progress_callback,
                max_workers=resolved_workers or 10,
            )
        elif stage_name == "統合情報生成":
            result = func(webview=webview, progress_callback=progress_callback)
        elif stage_name == "ユーザー情報":
            result = func(bearer_token, progress_callback=progress_callback, parent_widget=parent_widget)
        elif stage_name == "グループ関連情報":
            result = func(
                bearer_token,
                progress_callback=progress_callback,
                program_id=None,
                parent_widget=parent_widget,
                force_program_dialog=force_program_dialog,
                force_download=force_download,
                max_workers=resolved_workers or 10,
            )
        elif stage_name in ["subGroup.json自動更新", "dataset.json自動更新"]:
            # 自動更新関数は bearer_token と progress_callback のみ
            result = func(bearer_token, progress_callback=progress_callback)
        else:
            if stage_name in {"サンプル情報", "データエントリ情報", "インボイス情報", "invoiceSchema情報", "テンプレート・設備・ライセンス情報"}:
                result = func(
                    bearer_token,
                    progress_callback=progress_callback,
                    max_workers=resolved_workers or 10,
                )
            else:
                result = func(bearer_token, progress_callback=progress_callback)
        
        logger.info(f"個別段階実行完了: {stage_name}")
        return result
    except Exception as e:
        error_msg = f"個別段階実行でエラーが発生しました ({stage_name}): {e}"
        logger.error(error_msg)
        traceback.print_exc()
        return error_msg

def fetch_basic_info_logic(
    bearer_token,
    parent=None,
    webview=None,
    onlySelf=False,
    searchWords=None,
    searchWordsBatch: Optional[List[str]] = None,
    skip_confirmation=False,
    progress_callback=None,
    program_id=None,
    force_download: bool = False,
    parallel_max_workers: Optional[int] = None,
):
    """
    基本情報取得・保存・WebView遷移（開発用）
    
    v2.0.1改善:
    - 事前トークン検証の追加
    - 認証エラー時の再ログイン促進
    - エラーメッセージの明確化
    
    v2.1.16追加:
    - program_id引数を追加（グループ選択機能対応）

    v2.1.20追加:
    - force_download引数を追加。False時は既存JSONを優先利用し、欠損分のみ取得
    """
    import traceback
    import json
    from pathlib import Path
    from core.bearer_token_manager import BearerTokenManager
    from qt_compat.widgets import QMessageBox

    try:
        resolved_workers = int(parallel_max_workers) if parallel_max_workers is not None else None
        if resolved_workers is not None and resolved_workers < 1:
            resolved_workers = None
    except Exception:
        resolved_workers = None

    # 既存のデフォルト値(多くの箇所で10)を維持しつつ、UIから上書き可能にする
    parallel_workers = resolved_workers or 10
    
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
        preview_words = list(searchWordsBatch) if searchWordsBatch else None
        if not show_fetch_confirmation_dialog(parent, onlySelf, searchWords, searchWordsList=preview_words):
            logger.info("基本情報取得処理はユーザーによりキャンセルされました。")
            return "キャンセルされました"
    
    logger.info("基本情報取得処理を開始します")

    def _exists(path: str) -> bool:
        return Path(path).exists()

    def _folder_has_files(folder_path: str, expected_count: Optional[int] = None) -> tuple[bool, int]:
        """フォルダ内のJSONファイル数をチェック。existsは常に確認。
        
        Returns:
            (has_any_files, actual_count): ファイルがあるか、実際のファイル数
        """
        folder = Path(folder_path)
        # フォルダの存在確認はスキップしない（v2.1.21）
        if not folder.exists():
            logger.debug(f"フォルダが存在しません: {folder_path}")
            return False, 0
        
        # *.json ファイルをカウント
        json_files = list(folder.glob("*.json"))
        actual_count = len(json_files)
        
        # expected_countが指定されている場合は欠損判定
        if expected_count is not None and actual_count < expected_count:
            logger.info(f"フォルダ内に欠損ファイルあり: {folder_path} (期待: {expected_count}件, 実際: {actual_count}件)")
            return True, actual_count  # 欠損があってもファイルが1つでもあればTrue
        
        return actual_count > 0, actual_count
    
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
        try:
            if force_download or not _exists(SELF_JSON_PATH):
                fetch_self_info_from_api(bearer_token, parent_widget=parent)
            else:
                logger.info("ユーザー情報: 既存の self.json を利用するため取得をスキップします")
        except Exception as fetch_error:
            logger.error(f"ユーザー情報取得エラー: {fetch_error}")
            return "ユーザー情報取得に失敗しました"
        
        if not update_stage_progress(0, 100, "完了"):
            return "キャンセルされました"

        group_id = None
        project_group_id = None
        sub_group_data = None

        # 2-4. グループ関連情報取得（統合パイプライン）
        if not update_stage_progress(1, 0, "開始"):
            return "キャンセルされました"
        if not update_stage_progress(2, 0, "準備中"):
            return "キャンセルされました"
        if not update_stage_progress(3, 0, "準備中"):
            return "キャンセルされました"

        force_project_dialog = os.environ.get('FORCE_PROJECT_GROUP_DIALOG', '0') == '1'

        def pipeline_progress_adapter(current_percent, total, message):
            percent = max(0, min(100, current_percent))
            if percent <= 34:
                mapped = min(100, int((percent / 34) * 100))
                return update_stage_progress(1, mapped, message)
            if percent <= 67:
                mapped = min(100, int(((percent - 34) / 33) * 100))
                return update_stage_progress(2, mapped, message)
            mapped = min(100, int(((percent - 67) / 33) * 100))
            return update_stage_progress(3, mapped, message)
        group_files_ready = all(
            _exists(path) for path in (GROUP_JSON_PATH, GROUP_DETAIL_JSON_PATH, SUBGROUP_JSON_PATH)
        )
        subgroups_complete = _subgroups_folder_complete() if group_files_ready else False
        if group_files_ready and not subgroups_complete and not force_download:
            logger.info("サブグループ詳細に欠損があるためグループ関連情報を再取得します")
        use_cache = (not force_download) and group_files_ready and subgroups_complete
        group_pipeline = None

        if use_cache:
            try:
                with open(GROUP_DETAIL_JSON_PATH, "r", encoding="utf-8") as f:
                    cached_program_data = json.load(f)
                with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
                    cached_project_data = json.load(f)
                group_id = cached_program_data.get("data", {}).get("id")
                project_group_id = cached_project_data.get("data", {}).get("id")
                sub_group_data = cached_project_data
                if not group_id or not project_group_id:
                    raise ValueError("キャッシュに必要なグループIDが含まれていません")
                logger.info("グループ関連情報: 既存ファイルを再利用しました")
            except Exception as cache_error:
                logger.warning("グループ関連JSONの読み込みに失敗したため再取得を実行します: %s", cache_error)
                use_cache = False

        if not use_cache:
            try:
                group_pipeline = run_group_hierarchy_pipeline(
                    bearer_token=bearer_token,
                    parent_widget=parent,
                    preferred_program_id=program_id,
                    progress_callback=pipeline_progress_adapter,
                    force_project_dialog=force_project_dialog,
                )
            except GroupFetchCancelled:
                return "キャンセルされました"

            group_id = group_pipeline.selected_program_id
            project_group_id = group_pipeline.selected_project_id
            sub_group_data = group_pipeline.selected_project_data

            if not sub_group_data or not project_group_id:
                logger.error("サブグループデータを正常に取得できませんでした")
                return "サブグループ情報を取得できませんでした"

            total_success = sum(item.get("success", 0) for item in group_pipeline.subgroup_summary.values())
            total_fail = sum(item.get("fail", 0) for item in group_pipeline.subgroup_summary.values())
            logger.info(
                "グループ関連情報取得完了（サブグループ: 成功 %s件, 失敗 %s件）",
                total_success,
                total_fail,
            )

        for stage_idx in (1, 2, 3):
            sub_message = "キャッシュ再利用" if use_cache else "完了"
            if not update_stage_progress(stage_idx, 100, sub_message):
                return "キャンセルされました"

        # 5. サンプル情報取得
        if not update_stage_progress(4, 0, "サンプル取得準備中"):
            return "キャンセルされました"
            
        logger.debug("fetch_sample_info_from_api")
        sub_group_included = []
        if sub_group_data and isinstance(sub_group_data, dict):
            sub_group_included = sub_group_data.get("included", [])
            
        sample_dir = os.path.join(OUTPUT_DIR, "rde", "data", "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        total_samples = len(sub_group_included)
        if not update_stage_progress(4, 0, f"サンプル取得準備: 計画 {total_samples}件 (並列閾値: 50件)"):
            return "キャンセルされました"
        
        # サンプル フォルダ内のファイル数をチェック（v2.1.21: 欠損判定）
        sample_has_files, sample_actual_count = _folder_has_files(sample_dir, expected_count=total_samples)
        
        skip_sample_fetch = not force_download and sample_has_files and sample_actual_count == total_samples
        
        if skip_sample_fetch:
            logger.info(f"サンプル情報: 既存フォルダ({sample_actual_count}件)を利用するため取得をスキップします")
            if not update_stage_progress(4, 100, f"キャッシュ完了 (計画: {total_samples}件)"):
                return "キャンセルされました"
        else:
            processed_samples = 0
            skipped_samples = 0
            failed_samples = 0

            if total_samples >= 50:
                from config.common import load_bearer_token
                from net.http_helpers import parallel_download

                material_token = load_bearer_token('rde-material.nims.go.jp')
                tasks = [
                    (material_token, included.get("id", ""), sample_dir, force_download)
                    for included in sub_group_included
                    if included.get("id")
                ]

                def sample_parallel_progress(current, total, message):
                    mapped = 5 + int((current / 100.0) * 90)
                    mapped = min(95, max(5, mapped))
                    text = f"並列サンプル取得中 (計画: {total_samples}件, {message})"
                    return update_stage_progress(4, mapped, text)

                result = parallel_download(
                    tasks=tasks,
                    worker_function=_fetch_single_sample_worker_force,
                    max_workers=parallel_workers,
                    progress_callback=sample_parallel_progress,
                    threshold=1,
                )

                if result.get("cancelled"):
                    logger.warning("サンプル情報取得がユーザーによりキャンセルされました")
                    return "キャンセルされました"

                processed_samples = result.get("success_count", 0)
                skipped_samples = result.get("skipped_count", 0)
                failed_samples = result.get("failed_count", 0)
            else:
                from config.common import load_bearer_token

                material_token = load_bearer_token('rde-material.nims.go.jp')
                for idx, included in enumerate(sub_group_included):
                    current_index = idx + 1
                    sample_progress = int((current_index / total_samples) * 100) if total_samples > 0 else 100
                    group_id_sample = included.get("id", "")
                    sample_json_path = os.path.join(sample_dir, f"{group_id_sample}.json")
                    
                    if not force_download and os.path.exists(sample_json_path):
                        skipped_samples += 1
                        if not update_stage_progress(4, sample_progress, f"サンプル確認 {current_index}/{total_samples} - スキップ済み: {skipped_samples}"):
                            return "キャンセルされました"
                        logger.debug(f"サンプル情報({group_id_sample})は既に存在するためスキップしました: {sample_json_path}")
                        continue
                        
                    if not update_stage_progress(4, sample_progress, f"サンプル取得中 {current_index}/{total_samples} - 完了: {processed_samples}"):
                        return "キャンセルされました"
                    
                    url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id_sample}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
                    try:
                        headers_sample = _make_headers(material_token, host="rde-material-api.nims.go.jp", origin="https://rde-entry-arim.nims.go.jp", referer="https://rde-entry-arim.nims.go.jp/")
                        resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
                        if resp is None:
                            logger.error(f"サンプル情報({group_id_sample})の取得に失敗しました: リクエストエラー")
                            failed_samples += 1
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        with open(sample_json_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        processed_samples += 1
                        logger.info(f"サンプル情報({group_id_sample})の取得・保存に成功しました: {sample_json_path}")
                    except Exception as e:
                        failed_samples += 1
                        logger.error(f"サンプル情報({group_id_sample})の取得・保存に失敗しました: {e}")

            logger.info(
                "サンプル情報取得完了: 処理済み %s件, スキップ済み %s件, 失敗 %s件 (計画 %s件)",
                processed_samples,
                skipped_samples,
                failed_samples,
                total_samples,
            )
            final_message = (
                f"完了 (計画: {total_samples}件, 成功: {processed_samples}, スキップ: {skipped_samples}, 失敗: {failed_samples}, "
                f"並列: {'有効' if total_samples >= 50 else '無効'})"
            )
            if not update_stage_progress(4, 100, final_message):
                return "キャンセルされました"

        # 6. 組織・装置情報取得
        total_org_tasks = 2
        if not update_stage_progress(5, 0, f"組織・装置情報取得準備 (計画: {total_org_tasks}件, 並列: なし)"):
            return "キャンセルされました"
            
        logger.debug("fetch_organization_info_from_api")
        org_json_path = [OUTPUT_DIR, "rde", "data", "organization.json"]
        if force_download or not _exists(ORGANIZATION_JSON_PATH):
            fetch_organization_info_from_api(bearer_token, org_json_path)
            if not update_stage_progress(5, 50, "組織情報取得完了 (1/2)"):
                return "キャンセルされました"
        else:
            logger.info("組織情報: 既存の organization.json を利用するため取得をスキップします")
            if not update_stage_progress(5, 50, "組織情報キャッシュ完了 (1/2)"):
                return "キャンセルされました"
        
        logger.debug("fetch_instrument_type_info_from_api")
        instrument_type_json_path = [OUTPUT_DIR, "rde", "data", "instrumentType.json"]
        if force_download or not _exists(INSTRUMENT_TYPE_JSON_PATH):
            fetch_instrument_type_info_from_api(bearer_token, instrument_type_json_path)
            if not update_stage_progress(5, 100, "装置タイプ情報取得完了 (2/2)"):
                return "キャンセルされました"
        else:
            logger.info("装置タイプ情報: 既存の instrumentType.json を利用するため取得をスキップします")
            if not update_stage_progress(5, 100, "装置タイプ情報キャッシュ完了 (2/2)"):
                return "キャンセルされました"

        # 7. データセット情報取得
        if not update_stage_progress(6, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_all_dataset_info")

        def dataset_progress_adapter(current, total, message):
            return update_stage_progress(6, current, message)

        if force_download or not _exists(DATASET_JSON_PATH):
            dataset_result = fetch_all_dataset_info(
                bearer_token,
                output_dir=os.path.join(OUTPUT_DIR, "rde", "data"),
                onlySelf=onlySelf,
                searchWords=searchWords,
                searchWordsBatch=searchWordsBatch,
                progress_callback=dataset_progress_adapter,
                max_workers=parallel_workers,
            )
            if dataset_result == "キャンセルされました":
                return "キャンセルされました"
        else:
            cache_message = "データセット一覧: 既存の dataset.json を利用するため取得をスキップします"
            logger.info(cache_message)
            if not update_stage_progress(6, 100, f"キャッシュ完了 (計画: 不明件, 並列: なし)"):
                return "キャンセルされました"

        if not update_stage_progress(6, 100, "完了"):
            return "キャンセルされました"

        # 8. データエントリ情報取得
        if not update_stage_progress(7, 0, "データエントリ情報取得準備中"):
            return "キャンセルされました"
            
        logger.debug("fetch_all_data_entrys_info")
        
        # dataEntry フォルダ内のファイル数をチェック（v2.1.21: 欠損判定）
        dataentry_dir = os.path.join(OUTPUT_DIR, "rde", "data", "dataEntry")
        dataentry_has_files, dataentry_count = _folder_has_files(dataentry_dir)
        
        skip_dataentry_fetch = not force_download and dataentry_has_files
        
        if skip_dataentry_fetch:
            logger.info(f"データエントリ情報: 既存フォルダ({dataentry_count}件)を利用するため取得をスキップします")
            if not update_stage_progress(7, 100, "キャッシュ完了"):
                return "キャンセルされました"
        else:
            # プログレスコールバックを作成（ステージ7の0-100%をマッピング）
            def dataentry_progress_callback(current, total, message):
                return update_stage_progress(7, current, message)
            
            result = fetch_all_data_entrys_info(
                bearer_token,
                progress_callback=dataentry_progress_callback,
                max_workers=parallel_workers,
            )
            if result == "キャンセルされました":
                return "キャンセルされました"
        
        if not update_stage_progress(7, 100, "データエントリ情報取得完了"):
            return "キャンセルされました"

        # 9. インボイス情報取得
        if not update_stage_progress(8, 0, "インボイス情報取得準備中"):
            return "キャンセルされました"
            
        logger.debug("fetch_all_invoices_info")
        
        # invoice フォルダ内のファイル数をチェック（v2.1.21: 欠損判定）
        invoice_dir = os.path.join(OUTPUT_DIR, "rde", "data", "invoice")
        invoice_has_files, invoice_count = _folder_has_files(invoice_dir)
        
        skip_invoice_fetch = not force_download and invoice_has_files
        
        if skip_invoice_fetch:
            logger.info(f"インボイス情報: 既存フォルダ({invoice_count}件)を利用するため取得をスキップします")
            if not update_stage_progress(8, 100, "キャッシュ完了"):
                return "キャンセルされました"
        else:
            # プログレスコールバックを作成（ステージ8の0-100%をマッピング）
            def invoice_progress_callback(current, total, message):
                return update_stage_progress(8, current, message)
            
            result = fetch_all_invoices_info(
                bearer_token,
                progress_callback=invoice_progress_callback,
                max_workers=parallel_workers,
            )
            if result == "キャンセルされました":
                return "キャンセルされました"
        
        if not update_stage_progress(8, 100, "インボイス情報取得完了"):
            return "キャンセルされました"

        # 10. invoiceSchema情報取得
        if not update_stage_progress(9, 0, "invoiceSchema情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_invoice_schemas")
        
        # invoiceSchemas フォルダ内のファイル数をチェック（v2.1.21: 欠損判定）
        invoiceschemas_dir = os.path.join(OUTPUT_DIR, "rde", "data", "invoiceSchemas")
        invoiceschemas_has_files, invoiceschemas_count = _folder_has_files(invoiceschemas_dir)
        
        skip_invoiceschema_fetch = not force_download and invoiceschemas_has_files
        
        if skip_invoiceschema_fetch:
            logger.info(f"invoiceSchema情報: 既存フォルダ({invoiceschemas_count}件)を利用するため取得をスキップします")
            if not update_stage_progress(9, 100, f"キャッシュ完了 (既存: {invoiceschemas_count}件)"):
                return "キャンセルされました"
        else:
            try:
                output_dir = os.path.join(OUTPUT_DIR, "rde", "data")

                def invoiceschema_progress_adapter(current, total, message):
                    return update_stage_progress(9, current, message)

                invoice_schema_result = fetch_invoice_schemas(
                    bearer_token,
                    output_dir,
                    progress_callback=invoiceschema_progress_adapter,
                    max_workers=parallel_workers,
                )
                if invoice_schema_result == "キャンセルされました":
                    return "キャンセルされました"
            except Exception as e:
                logger.warning(f"invoiceSchema取得でエラーが発生しましたが処理を続行します: {e}")
        
            if not update_stage_progress(9, 100, "完了"):
                return "キャンセルされました"

        # 11. テンプレート・設備・ライセンス情報取得
        if not update_stage_progress(10, 0, "テンプレート情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_template_info_from_api")
        if force_download or not _exists(TEMPLATE_JSON_PATH):
            fetch_template_info_from_api(bearer_token)
        else:
            logger.info("テンプレート情報: 既存の template.json を利用するため取得をスキップします")
        
        # devices/licenses は独立なので、必要分があれば並列化して短縮
        if not update_stage_progress(10, 33, "設備・利用ライセンス情報取得中"):
            return "キャンセルされました"

        need_instruments = force_download or not _exists(INSTRUMENTS_JSON_PATH)
        need_licenses = force_download or not _exists(LICENSES_JSON_PATH)

        if not need_instruments:
            logger.info("設備情報: 既存の instruments.json を利用するため取得をスキップします")
        if not need_licenses:
            logger.info("利用ライセンス情報: 既存の licenses.json を利用するため取得をスキップします")

        tasks = []
        if need_instruments:
            tasks.append(("instruments", lambda: fetch_instruments_info_from_api(bearer_token)))
        if need_licenses:
            tasks.append(("licenses", lambda: fetch_licenses_info_from_api(bearer_token)))

        if len(tasks) <= 1 or parallel_workers <= 1:
            for name, fn in tasks:
                logger.debug("fetch_%s_info_from_api", name)
                fn()
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=min(int(parallel_workers), len(tasks))) as executor:
                future_to_name = {executor.submit(fn): name for name, fn in tasks}
                completed = 0
                total = len(future_to_name)
                for future in as_completed(future_to_name):
                    name = future_to_name[future]
                    future.result()
                    completed += 1
                    if not update_stage_progress(10, 33 + int((completed / max(total, 1)) * 33), f"完了: {name} ({completed}/{total})"):
                        return "キャンセルされました"

        if not update_stage_progress(10, 66, "完了"):
            return "キャンセルされました"
        
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

def fetch_sample_info_only(bearer_token, output_dir=None, progress_callback=None, max_workers: int = 10):
    """
    サンプル情報のみを強制取得・保存（既存ファイルも上書き）
    v2.1.0: 並列ダウンロード対応（50件以上で自動並列化）
    """
    from net.http_helpers import parallel_download
    
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
        root_dir = output_dir or OUTPUT_RDE_DATA_DIR
        sub_group_path = os.path.join(root_dir, "subGroup.json")
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
        
        sample_dir = os.path.join(root_dir, "samples")
        os.makedirs(sample_dir, exist_ok=True)
        
        total_samples = len(sub_group_included)
        
        # タスクリストを作成（並列実行用）
        tasks = []
        for included in sub_group_included:
            group_id_sample = included.get("id", "")
            if group_id_sample:
                tasks.append((bearer_token, group_id_sample, sample_dir))
        
        # 並列ダウンロード実行（50件以上で自動並列化）
        def worker(token, group_id, samp_dir):
            """ワーカー関数"""
            try:
                url = f"https://rde-material-api.nims.go.jp/samples?groupId={group_id}&page%5Blimit%5D=1000&page%5Boffset%5D=0&fields%5Bsample%5D=names%2Cdescription%2Ccomposition"
                sample_json_path = os.path.join(samp_dir, f"{group_id}.json")
                
                # Material API用のトークンを明示的に取得
                from config.common import load_bearer_token
                material_token = load_bearer_token('rde-material.nims.go.jp')
                headers_sample = _make_headers(material_token, host="rde-material-api.nims.go.jp", origin="https://rde-entry-arim.nims.go.jp", referer="https://rde-entry-arim.nims.go.jp/")
                resp = api_request("GET", url, bearer_token=material_token, headers=headers_sample, timeout=10)
                if resp is None:
                    logger.error(f"サンプル情報({group_id})の取得に失敗しました: リクエストエラー")
                    return "failed: request error"
                
                resp.raise_for_status()
                data = resp.json()
                
                # 強制上書き保存
                with open(sample_json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
                logger.info(f"サンプル情報({group_id})の強制取得・保存に成功しました: {sample_json_path}")
                return "success"
                
            except Exception as e:
                logger.error(f"サンプル情報({group_id})の取得・保存に失敗しました: {e}")
                return f"failed: {e}"
        
        # プログレスコールバックを調整（10-95%の範囲にマッピング）
        def adjusted_progress_callback(current, total, message):
            if progress_callback:
                progress_percent = 10 + int((current / 100) * 85)  # 10-95%
                return progress_callback(progress_percent, 100, message)
            return True
        
        result = parallel_download(
            tasks=tasks,
            worker_function=worker,
            max_workers=max_workers,
            progress_callback=adjusted_progress_callback,
            threshold=50
        )
        
        if progress_callback:
            if not progress_callback(95, 100, "サンプル情報取得完了処理中..."):
                return "キャンセルされました"
                
        result_msg = (f"サンプル情報強制取得が完了しました。"
                     f"成功: {result['success_count']}件, "
                     f"失敗: {result['failed_count']}件, "
                     f"総数: {result['total']}件")
        logger.info(result_msg)
        
        if progress_callback:
            if not progress_callback(100, 100, "完了"):
                return "キャンセルされました"
        
        if result['cancelled']:
            return "キャンセルされました"
        
        return result_msg
        
    except Exception as e:
        error_msg = f"サンプル情報取得でエラーが発生しました: {e}"
        logger.error(error_msg)
        traceback.print_exc()
        return error_msg

def fetch_sample_info_from_subgroup_ids_only(bearer_token, output_dir=None):
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
        root_dir = output_dir or OUTPUT_RDE_DATA_DIR
        sub_group_path = os.path.join(root_dir, "subGroup.json")
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
        
        sample_dir = os.path.join(root_dir, "samples")
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

def fetch_sample_info_for_dataset_only(bearer_token, dataset_id, output_dir=None):
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
        root_dir = output_dir or OUTPUT_RDE_DATA_DIR
        dataset_json_path = os.path.join(root_dir, "datasets", f"{dataset_id}.json")
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
        sample_dir = os.path.join(root_dir, "samples")
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

def fetch_common_info_only_logic(
    bearer_token,
    parent=None,
    webview=None,
    progress_callback=None,
    program_id=None,
    force_download=False,
):
    """
    7種類の共通情報JSONのみを取得・保存（個別データセットJSONは取得しない）
    
    v2.0.1改善:
    - 事前トークン検証の追加
    - 認証エラー時の再ログイン促進
    - エラーメッセージの明確化
    
    v2.1.16追加:
    - program_id引数を追加（グループ選択機能対応）
    """
    import traceback
    from datetime import datetime
    from core.bearer_token_manager import BearerTokenManager
    from qt_compat.widgets import QMessageBox
    
    # ===== API記録初期化（v2.1.16新規追加） =====
    try:
        from net.api_call_recorder import reset_global_recorder
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        reset_global_recorder(session_id=session_id)
        logger.debug(f"APIコール記録を初期化しました: session_id={session_id}")
    except Exception as e:
        logger.debug(f"API記録初期化失敗（非致命的）: {e}")
    
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

    group_id = None
    project_group_id = None
    sub_group_data = None
    group_stage_executed = False

    def _exists(path: str) -> bool:
        return Path(path).exists()

    def _folder_has_files(folder_path: str, expected_count: Optional[int] = None) -> tuple[bool, int]:
        """フォルダ内のJSONファイル数をチェック。existsは常に確認。
        
        Returns:
            (has_any_files, actual_count): ファイルがあるか、実際のファイル数
        """
        folder = Path(folder_path)
        # フォルダの存在確認はスキップしない（v2.1.21）
        if not folder.exists():
            logger.debug(f"フォルダが存在しません: {folder_path}")
            return False, 0
        
        # *.json ファイルをカウント
        json_files = list(folder.glob("*.json"))
        actual_count = len(json_files)
        
        # expected_countが指定されている場合は欠損判定
        if expected_count is not None and actual_count < expected_count:
            logger.info(f"フォルダ内に欠損ファイルあり: {folder_path} (期待: {expected_count}件, 実際: {actual_count}件)")
            return True, actual_count  # 欠損があってもファイルが1つでもあればTrue
        
        return actual_count > 0, actual_count
    
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

        try:
            if force_download or not Path(SELF_JSON_PATH).exists():
                logger.debug("fetch_self_info_from_api")
                fetch_self_info_from_api(bearer_token, parent_widget=parent)
            else:
                logger.info("ユーザー情報: 既存の self.json を利用するため取得をスキップします")
        except Exception as fetch_error:
            logger.error(f"ユーザー情報取得エラー: {fetch_error}")
            return "ユーザー情報取得に失敗しました"
        
        if not update_stage_progress(0, 100, "完了"):
            return "キャンセルされました"

        # 2. グループ関連情報取得（グループ、グループ詳細、サブグループ）
        if not update_stage_progress(1, 0, "グループ情報取得開始"):
            return "キャンセルされました"

        import os
        force_project_dialog = os.environ.get('FORCE_PROJECT_GROUP_DIALOG', '0') == '1'

        def pipeline_progress_callback(current, total, message):
            total = total or 100
            mapped = int((current / total) * 100)
            mapped = max(0, min(100, mapped))
            return update_stage_progress(1, mapped, message)

        group_files_ready = all(
            _exists(path) for path in (GROUP_JSON_PATH, GROUP_DETAIL_JSON_PATH, SUBGROUP_JSON_PATH)
        )
        subgroups_complete = _subgroups_folder_complete() if group_files_ready else False
        if group_files_ready and not subgroups_complete and not force_download:
            logger.info("サブグループ詳細に欠損があるためグループ関連情報を再取得します")
        use_cache = (not force_download) and group_files_ready and subgroups_complete
        group_pipeline = None

        if use_cache:
            try:
                with open(GROUP_DETAIL_JSON_PATH, "r", encoding="utf-8") as f:
                    cached_program_data = json.load(f)
                with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
                    cached_project_data = json.load(f)
                group_id = cached_program_data.get("data", {}).get("id")
                project_group_id = cached_project_data.get("data", {}).get("id")
                sub_group_data = cached_project_data
                if not group_id or not project_group_id:
                    raise ValueError("キャッシュに必要なグループIDが含まれていません")
                logger.info("グループ関連情報: 既存ファイルを再利用しました")
            except Exception as cache_error:
                logger.warning("グループ関連JSONの読み込みに失敗したため再取得を実行します: %s", cache_error)
                use_cache = False

        if not use_cache:
            try:
                group_pipeline = run_group_hierarchy_pipeline(
                    bearer_token=bearer_token,
                    parent_widget=parent,
                    preferred_program_id=program_id,
                    progress_callback=pipeline_progress_callback,
                    force_project_dialog=force_project_dialog,
                    force_download=force_download,
                )
                group_stage_executed = True
            except GroupFetchCancelled:
                logger.info("共通情報取得: グループ階層取得がキャンセルされました")
                return "キャンセルされました"
            except Exception as pipeline_error:
                logger.error("共通情報取得: グループ階層取得に失敗", exc_info=True)
                return f"グループ関連情報取得に失敗しました: {pipeline_error}"

            group_id = group_pipeline.selected_program_id
            project_group_id = group_pipeline.selected_project_id
            sub_group_data = group_pipeline.selected_project_data

        if not update_stage_progress(1, 100, "完了" if not use_cache else "キャッシュ完了"):
            return "キャンセルされました"

        # 3. 組織・装置情報取得
        if not update_stage_progress(2, 0, "組織情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_organization_info_from_api")
        org_json_path = [OUTPUT_DIR, "rde", "data", "organization.json"]
        if force_download or not _exists(ORGANIZATION_JSON_PATH):
            fetch_organization_info_from_api(bearer_token, org_json_path)
        else:
            logger.info("組織情報: 既存の organization.json を利用するため取得をスキップします")
        
        if not update_stage_progress(2, 50, "装置タイプ情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_instrument_type_info_from_api")
        instrument_type_json_path = [OUTPUT_DIR, "rde", "data", "instrumentType.json"]
        if force_download or not _exists(INSTRUMENT_TYPE_JSON_PATH):
            fetch_instrument_type_info_from_api(bearer_token, instrument_type_json_path)
        else:
            logger.info("装置タイプ情報: 既存の instrumentType.json を利用するため取得をスキップします")
        
        if not update_stage_progress(2, 100, "完了"):
            return "キャンセルされました"

        # 4. データセット一覧取得（個別詳細は取得しない）
        if not update_stage_progress(3, 0, "開始"):
            return "キャンセルされました"
            
        logger.debug("fetch_dataset_list_only")
        if force_download or not _exists(DATASET_JSON_PATH):
            fetch_dataset_list_only(bearer_token, output_dir=os.path.join(OUTPUT_DIR, "rde", "data"))
        else:
            logger.info("データセット一覧: 既存の dataset.json を利用するため取得をスキップします")
        
        if not update_stage_progress(3, 100, "完了"):
            return "キャンセルされました"

        # 5. テンプレート・設備・ライセンス情報取得
        if not update_stage_progress(4, 0, "テンプレート情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_template_info_from_api")
        if force_download or not _exists(TEMPLATE_JSON_PATH):
            fetch_template_info_from_api(bearer_token)
        else:
            logger.info("テンプレート情報: 既存の template.json を利用するため取得をスキップします")
        
        if not update_stage_progress(4, 33, "設備情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_instruments_info_from_api")
        if force_download or not _exists(INSTRUMENTS_JSON_PATH):
            fetch_instruments_info_from_api(bearer_token)
        else:
            logger.info("設備情報: 既存の instruments.json を利用するため取得をスキップします")
        
        if not update_stage_progress(4, 66, "利用ライセンス情報取得中"):
            return "キャンセルされました"
            
        logger.debug("fetch_licenses_info_from_api")
        if force_download or not _exists(LICENSES_JSON_PATH):
            fetch_licenses_info_from_api(bearer_token)
        else:
            logger.info("利用ライセンス情報: 既存の licenses.json を利用するため取得をスキップします")
        
        if not update_stage_progress(4, 100, "完了"):
            return "キャンセルされました"

        # 6. 統合情報生成
        if not update_stage_progress(5, 0, "開始"):
            return "キャンセルされました"
            
        # info.json生成
        should_generate_info = sub_group_data and (
            force_download or group_stage_executed or not _exists(INFO_JSON_PATH)
        )
        if should_generate_info:
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
        elif sub_group_data:
            logger.info("info.json: 既存ファイルを利用するため生成をスキップします")
                
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

def fetch_dataset_list_only(bearer_token, output_dir=None):
    """データセット一覧のみを取得し、dataset.jsonとして保存（個別JSONは取得しない）"""
    # パス区切りを統一
    output_dir = os.path.normpath(output_dir or OUTPUT_RDE_DATA_DIR)

    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")

    try:
        dataset_payload = _download_dataset_list_in_chunks(
            bearer_token=bearer_token,
            headers=headers,
            search_words=None,
        )
    except Exception as e:
        logger.error("データセット一覧の取得に失敗しました: %s", e)


    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, "dataset.json")

    # 既存ファイルのバックアップを作成
    if os.path.exists(save_path):
        backup_path = save_path + ".backup"
        try:
            shutil.copy2(save_path, backup_path)
            logger.info("既存ファイルのバックアップを作成: %s", backup_path)
        except Exception as backup_error:
            logger.warning("バックアップ作成に失敗: %s", backup_error)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(dataset_payload, f, ensure_ascii=False, indent=2)
    logger.info("データセット一覧(dataset.json)の取得・保存に成功しました。")
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

    def _dir_has_any_entry(path: str) -> bool:
        try:
            with os.scandir(path) as it:
                for _ in it:
                    return True
            return False
        except Exception:
            return False
    
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
                    if _dir_has_any_entry(item_path):
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

                dataEntry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{ds_info['id']}.json")
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

def fetch_invoice_schema_from_api(
    bearer_token,
    template_id,
    output_dir,
    summary,
    log_path,
    summary_path,
    team_id_candidates=None,
    summary_lock=None,
):
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
    # 既存ファイルがあればスキップ
    if os.path.exists(filepath):
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return "skipped_file"
    # NOTE: teamId が無いと多くのテンプレートで403/404になり、取得件数が激減する。
    # そのため teamId 候補を付けて取得する（候補は subGroup.json の TEAM group から抽出）。
    headers = _make_headers(bearer_token, host="rde-api.nims.go.jp", origin="https://rde.nims.go.jp", referer="https://rde.nims.go.jp/")
    from contextlib import nullcontext

    lock_ctx = summary_lock if summary_lock is not None else nullcontext()
    candidates = team_id_candidates if isinstance(team_id_candidates, list) and team_id_candidates else [DEFAULT_TEAM_ID]
    # NOTE: 2025-12-18: teamId候補のリトライは行わない。
    # 基本情報/InvoiceSchema取得ボタンの動作として、最初の候補のみを使用し、失敗しても他候補は試さない。
    candidates = candidates[:1]

    # summaryの最低限の整合性を保証
    if not isinstance(summary, dict):
        return "failed: invalid summary"
    summary.setdefault("success", [])
    if not isinstance(summary.get("success"), list):
        summary["success"] = []
    summary.setdefault("failed", {})
    if not isinstance(summary.get("failed"), dict):
        summary["failed"] = {}

    try:
        team_id = candidates[0]
        url = f"https://rde-api.nims.go.jp/invoiceSchemas/{template_id}?teamId={team_id}"
        resp = api_request("GET", url, bearer_token=bearer_token, headers=headers, timeout=10)

        if resp is None:
            last_status = 0
            last_error = "Request failed"
        else:
            last_status = getattr(resp, "status_code", None)

            # token無効はteamIdに依らないので即終了
            if last_status == 401:
                last_error = "HTTP 401 Unauthorized"
            elif last_status in (403, 404):
                # teamId違い/権限/存在差分の可能性はあるが、候補のリトライは行わない
                last_error = f"HTTP {last_status}"
            else:
                resp.raise_for_status()
                data = resp.json()
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                with lock_ctx:
                    summary["success"].append(template_id)
                    summary["failed"].pop(template_id, None)
                    with open(log_path, "a", encoding="utf-8") as logf:
                        logf.write(
                            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [SUCCESS] template_id={template_id} teamId={team_id}\n"
                        )
                    with open(summary_path, "w", encoding="utf-8") as f:
                        json.dump(summary, f, ensure_ascii=False, indent=2)

                return "success"

        with lock_ctx:
            summary["failed"][template_id] = last_error or "failed"
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [FAILED] template_id={template_id} "
                    f"status={last_status} error={last_error}\n"
                )
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

        return "failed"

    except Exception as e:
        with lock_ctx:
            summary["failed"][template_id] = str(e)
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [FAILED] template_id={template_id} error={e}\n"
                )
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        return "failed"


# ========================================
# UIController用ラッパー関数
# ========================================

