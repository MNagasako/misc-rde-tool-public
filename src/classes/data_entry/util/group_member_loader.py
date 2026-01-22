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
