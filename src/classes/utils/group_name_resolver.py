from __future__ import annotations

import json
import logging
import os
from typing import Any

from config.common import SUBGROUP_DETAILS_DIR, SUBGROUP_REL_DETAILS_DIR
from net.http_helpers import proxy_get

logger = logging.getLogger(__name__)


def load_group_name(group_id: str) -> str:
    """指定されたグループ(サブグループ)IDの名称を取得する。

    - ローカルキャッシュ(subGroups/{id}.json 等)を優先
    - 無ければAPI(`/groups/{id}`)へフォールバック

    Returns:
        str: グループ名。取得できない場合は空文字。
    """

    group_id = str(group_id or "").strip()
    if not group_id:
        return ""

    # 0. subGroup.json(included) は、当該 subGroup.json の groupId と一致する場合のみ信用する
    try:
        from classes.subgroup.core.subgroup_data_manager import SubgroupDataManager

        subgroup_data = SubgroupDataManager.load_subgroups_data()
        if isinstance(subgroup_data, dict):
            current_group_id = str(((subgroup_data.get("data") or {}) if subgroup_data else {}).get("id") or "")
            if current_group_id and current_group_id == group_id:
                attrs = ((subgroup_data.get("data") or {}).get("attributes") or {})
                if isinstance(attrs, dict):
                    name = str(attrs.get("name") or "").strip()
                    if name:
                        return name
    except Exception:
        pass

    # 1. ローカルファイルから取得
    name = _load_group_name_from_local_file(group_id)
    if name:
        return name

    # 2. APIから取得 (フォールバック)
    return _load_group_name_from_api(group_id)


def _load_group_name_from_local_file(group_id: str) -> str:
    candidate_paths = [
        os.path.join(SUBGROUP_DETAILS_DIR, f"{group_id}.json"),
        os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{group_id}.json"),
    ]

    for path in candidate_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data: Any = json.load(f)
            attrs = ((data or {}).get("data") or {}).get("attributes") or {}
            if isinstance(attrs, dict):
                name = str(attrs.get("name") or "").strip()
                if name:
                    return name
        except Exception as e:
            logger.warning("Failed to load group name from local file %s: %s", path, e)

    return ""


def _load_group_name_from_api(group_id: str) -> str:
    url = f"https://rde-api.nims.go.jp/groups/{group_id}"
    try:
        response = proxy_get(url)
        if getattr(response, "status_code", None) != 200:
            return ""
        payload: Any = response.json()
        attrs = ((payload or {}).get("data") or {}).get("attributes") or {}
        if isinstance(attrs, dict):
            return str(attrs.get("name") or "").strip()
    except Exception as e:
        logger.error("Error loading group name from API for group %s: %s", group_id, e)

    return ""
