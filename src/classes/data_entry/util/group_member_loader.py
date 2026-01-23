import logging
import os
import json
from typing import List, Dict, Any
from net.http_helpers import proxy_get
from config.common import SUBGROUP_DETAILS_DIR, SUBGROUP_REL_DETAILS_DIR
from classes.subgroup.core.subgroup_data_manager import SubgroupDataManager

logger = logging.getLogger(__name__)


def load_group_name(group_id: str) -> str:
    """指定されたグループ(サブグループ)IDの名称を取得する。

    後方互換のため本モジュールに残すが、実装は共通ヘルパへ委譲する。
    """

    try:
        from classes.utils.group_name_resolver import load_group_name as _impl

        return _impl(group_id)
    except Exception:
        return ""

def load_group_members(group_id: str) -> List[Dict[str, Any]]:
    """
    指定されたグループIDのメンバー情報を取得します。
    まずはローカルのキャッシュファイルを確認し、なければAPIから取得を試みます。

    Args:
        group_id (str): グループID

    Returns:
        List[Dict[str, Any]]: メンバー情報のリスト。エラー時は空リストを返します。
    """
    if not group_id:
        return []

    # 0. subGroup.json(included) を使えるのは「その subGroup.json の groupId と一致する場合のみ」
    #    そうでない場合に使うと、別グループの問い合わせでも誤ったメンバー一覧を返してしまう。
    try:
        subgroup_data = SubgroupDataManager.load_subgroups_data()
        if isinstance(subgroup_data, dict):
            current_group_id = str(((subgroup_data.get("data") or {}) if subgroup_data else {}).get("id") or "")
            if current_group_id and current_group_id == str(group_id):
                users = SubgroupDataManager.load_user_entries()
                if users and not isinstance(users, str):
                    return list(users)
    except Exception:
        pass

    # 1. ローカルファイルから取得を試みる
    users = _load_from_local_file(group_id)
    if users:
        logger.debug(f"Loaded {len(users)} members from local file for group {group_id}")
        return users

    # 2. APIから取得を試みる (フォールバック)
    logger.debug(f"Local file not found or empty, fetching from API for group {group_id}")
    return _load_from_api(group_id)


def load_group_members_with_debug(group_id: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """指定グループIDのメンバー取得（デバッグ情報付き）。

    UI側で「どのJSON/どのキーを参照したか」を表示するための補助。
    既存の load_group_members() 互換のため、戻り値に debug を付与する。
    """

    debug: Dict[str, Any] = {
        "group_id": str(group_id or ""),
        "steps": [],
        "result": {
            "source": "none",
            "used_path": None,
            "api_attempts": [],
        },
    }

    if not group_id:
        debug["steps"].append({"step": "input", "ok": False, "note": "group_id is empty"})
        return [], debug

    # 0. subGroup.json(included)
    try:
        subgroup_data = SubgroupDataManager.load_subgroups_data()
        current_group_id = ""
        if isinstance(subgroup_data, dict):
            current_group_id = str(((subgroup_data.get("data") or {}) if subgroup_data else {}).get("id") or "")

        debug["steps"].append(
            {
                "step": "subGroup.json(included)",
                "checked": True,
                "current_group_id": current_group_id,
                "match": bool(current_group_id and current_group_id == str(group_id)),
                "reads": [
                    "subGroup.json:data.id",
                    "subGroup.json:included[type=user]",
                ],
            }
        )

        if current_group_id and current_group_id == str(group_id):
            users = SubgroupDataManager.load_user_entries()
            if users and not isinstance(users, str):
                result_users = list(users)
                debug["result"].update({"source": "subGroup.json(included)", "used_path": "output/rde/data/subGroup.json"})
                return result_users, debug
    except Exception as exc:
        debug["steps"].append({"step": "subGroup.json(included)", "checked": False, "error": str(exc)})

    # 1. local cache
    local_users, local_path = _load_from_local_file_with_path(group_id)
    debug["steps"].append(
        {
            "step": "local_file",
            "candidates": [
                os.path.join(SUBGROUP_DETAILS_DIR, f"{group_id}.json"),
                os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{group_id}.json"),
            ],
            "used_path": local_path,
            "reads": ["<group>.json:included[type=user]"],
            "count": len(local_users or []),
        }
    )
    if local_users:
        debug["result"].update({"source": "local_file", "used_path": local_path})
        return local_users, debug

    # 2. API fallback
    api_users, api_debug = _load_from_api_with_debug(group_id)
    debug["steps"].append({"step": "api", **api_debug})
    if api_users:
        debug["result"].update({"source": "api", "used_path": None, "api_attempts": api_debug.get("attempts", [])})
    else:
        debug["result"].update({"source": "none", "used_path": None, "api_attempts": api_debug.get("attempts", [])})
    return api_users, debug

def _load_from_local_file(group_id: str) -> List[Dict[str, Any]]:
    users = []
    candidate_paths = [
        os.path.join(SUBGROUP_DETAILS_DIR, f"{group_id}.json"),
        os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{group_id}.json"),
    ]
    
    for path in candidate_paths:
        if not os.path.exists(path):
            continue
            
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            
            # included配列からtype="user"の項目を抽出
            for item in (data or {}).get("included", []) or []:
                if item.get("type") == "user":
                    users.append(item)
            
            if users:
                return users
                
        except Exception as e:
            logger.warning(f"Failed to load group members from local file {path}: {e}")
            
    return users


def _load_from_local_file_with_path(group_id: str) -> tuple[List[Dict[str, Any]], str | None]:
    users: List[Dict[str, Any]] = []
    candidate_paths = [
        os.path.join(SUBGROUP_DETAILS_DIR, f"{group_id}.json"),
        os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{group_id}.json"),
    ]

    for path in candidate_paths:
        if not os.path.exists(path):
            continue

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            for item in (data or {}).get("included", []) or []:
                if item.get("type") == "user":
                    users.append(item)

            if users:
                return users, path
        except Exception as e:
            logger.warning(f"Failed to load group members from local file {path}: {e}")

    return users, None

def _load_from_api(group_id: str) -> List[Dict[str, Any]]:
    def _dedupe_by_id(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for u in users or []:
            uid = str((u or {}).get("id") or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            deduped.append(u)
        return deduped

    def _extract_users(payload: Any) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return []

        users: List[Dict[str, Any]] = []

        included = payload.get("included")
        if isinstance(included, list):
            for item in included:
                if isinstance(item, dict) and item.get("type") == "user":
                    users.append(item)
        if users:
            return _dedupe_by_id(users)

        # include が無い/権限等で included が落ちる場合に備え、members のIDだけでも返す。
        relationships = (payload.get("data") or {}).get("relationships")
        if isinstance(relationships, dict):
            members_rel = (relationships.get("members") or {}).get("data")
            if isinstance(members_rel, list):
                for m in members_rel:
                    if not isinstance(m, dict):
                        continue
                    if m.get("type") != "user":
                        continue
                    mid = str(m.get("id") or "").strip()
                    if not mid:
                        continue
                    users.append({"id": mid, "type": "user", "attributes": {}})

        # 旧形式/独自形式（念のため）
        if not users and isinstance(payload.get("members"), list):
            for m in payload.get("members"):
                if isinstance(m, dict):
                    users.append(m)

        return _dedupe_by_id(users)

    # NOTE: include=members は環境によって 404 になる事例があるため、まずは include=members を試し、失敗時に素のgroupsへフォールバック。
    base_url = f"https://rde-api.nims.go.jp/groups/{group_id}"
    urls_to_try = [
        # なるべくユーザー表示に必要な最小限のフィールドだけに絞る
        base_url + "?include=members&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted",
        base_url,
    ]

    last_status: int | None = None
    for url in urls_to_try:
        try:
            response = proxy_get(url)
            last_status = getattr(response, "status_code", None)
            if response.status_code != 200:
                continue
            payload = response.json()
            users = _extract_users(payload)
            if users:
                return users
        except Exception as e:
            logger.error(f"Error loading group members from API for group {group_id}: {e}")
            continue

    if last_status is not None:
        logger.error(f"Failed to load group members from API. Status: {last_status}")
    return []


def _load_from_api_with_debug(group_id: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """APIフォールバック（デバッグ情報付き）。"""

    debug: Dict[str, Any] = {"attempts": []}

    def _dedupe_by_id(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for u in users or []:
            uid = str((u or {}).get("id") or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            deduped.append(u)
        return deduped

    def _extract_users(payload: Any) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return []

        users: List[Dict[str, Any]] = []

        included = payload.get("included")
        if isinstance(included, list):
            for item in included:
                if isinstance(item, dict) and item.get("type") == "user":
                    users.append(item)
        if users:
            return _dedupe_by_id(users)

        relationships = (payload.get("data") or {}).get("relationships")
        if isinstance(relationships, dict):
            members_rel = (relationships.get("members") or {}).get("data")
            if isinstance(members_rel, list):
                for m in members_rel:
                    if not isinstance(m, dict):
                        continue
                    if m.get("type") != "user":
                        continue
                    mid = str(m.get("id") or "").strip()
                    if not mid:
                        continue
                    users.append({"id": mid, "type": "user", "attributes": {}})

        if not users and isinstance(payload.get("members"), list):
            for m in payload.get("members"):
                if isinstance(m, dict):
                    users.append(m)

        return _dedupe_by_id(users)

    base_url = f"https://rde-api.nims.go.jp/groups/{group_id}"
    urls_to_try = [
        base_url + "?include=members&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted",
        base_url,
    ]

    last_status: int | None = None
    for url in urls_to_try:
        attempt: Dict[str, Any] = {"url": url, "status": None, "error": None, "user_count": 0}
        try:
            response = proxy_get(url)
            last_status = getattr(response, "status_code", None)
            attempt["status"] = last_status
            if response.status_code != 200:
                debug["attempts"].append(attempt)
                continue
            payload = response.json()
            users = _extract_users(payload)
            attempt["user_count"] = len(users)
            debug["attempts"].append(attempt)
            if users:
                return users, debug
        except Exception as e:
            attempt["error"] = str(e)
            debug["attempts"].append(attempt)
            logger.error(f"Error loading group members from API for group {group_id}: {e}")
            continue

    if last_status is not None:
        logger.error(f"Failed to load group members from API. Status: {last_status}")
    return [], debug
