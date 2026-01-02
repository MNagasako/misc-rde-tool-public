import logging
import os
import json
from typing import List, Dict, Any
from net.http_helpers import proxy_get
from config.common import SUBGROUP_DETAILS_DIR, SUBGROUP_REL_DETAILS_DIR
from classes.subgroup.core.subgroup_data_manager import SubgroupDataManager

logger = logging.getLogger(__name__)

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
    # NOTE: include=members は環境によって 404 になる事例があるため、まずは基本のgroupsエンドポイントを使用する。
    url = f"https://rde-api.nims.go.jp/groups/{group_id}"
    
    try:
        response = proxy_get(url)
        
        if response.status_code == 200:
            data = response.json()
            members = []
            if 'included' in data:
                for item in data['included']:
                    if item.get('type') == 'user':
                        members.append(item)
            
            if not members and 'members' in data:
                 members = data['members']

            return members
        else:
            logger.error(f"Failed to load group members from API. Status: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"Error loading group members from API for group {group_id}: {e}")
        return []
