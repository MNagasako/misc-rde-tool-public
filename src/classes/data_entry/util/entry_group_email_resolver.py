import json
import logging
import os
from typing import Any, Dict, Iterable, Optional

from config.common import get_dynamic_file_path

from .group_member_loader import load_group_members

logger = logging.getLogger(__name__)


def _read_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.debug("Failed to read json: path=%s err=%s", path, exc)
        return None


def _extract_dataset_id_from_entry_json(entry_json: Dict[str, Any]) -> str:
    data = (entry_json or {}).get("data") or {}
    rel = data.get("relationships") or {}
    dataset = (rel.get("dataset") or {}).get("data") or {}
    return str(dataset.get("id") or "")


def _extract_group_id_from_dataset_json(dataset_json: Dict[str, Any]) -> str:
    data = (dataset_json or {}).get("data") or {}
    rel = data.get("relationships") or {}
    group = (rel.get("group") or {}).get("data") or {}
    return str(group.get("id") or "")


def build_email_map_for_entry_ids(
    entry_ids: Iterable[str],
    *,
    entry_dir: Optional[str] = None,
    dataset_dir: Optional[str] = None,
) -> Dict[str, str]:
    """entryId 群から、entry→dataset→groupId を辿って userId→email を合成する。

    - entry: output/rde/data/entry/<entryId>.json
    - dataset: output/rde/data/datasets/<datasetId>.json
    - group members: load_group_members(groupId) (subGroups/<groupId>.json など)

    Args:
        entry_ids: entryId のイテラブル
        entry_dir: entry詳細JSONディレクトリ（省略時は動的パス）
        dataset_dir: dataset詳細JSONディレクトリ（省略時は動的パス）

    Returns:
        dict: userId -> emailAddress
    """

    entry_dir = entry_dir or get_dynamic_file_path("output/rde/data/entry")
    dataset_dir = dataset_dir or get_dynamic_file_path("output/rde/data/datasets")

    dataset_ids: set[str] = set()
    for entry_id in entry_ids:
        eid = str(entry_id or "").strip()
        if not eid:
            continue
        entry_path = os.path.join(entry_dir, f"{eid}.json")
        entry_json = _read_json_if_exists(entry_path)
        if not entry_json:
            continue
        dataset_id = _extract_dataset_id_from_entry_json(entry_json)
        if dataset_id:
            dataset_ids.add(dataset_id)

    group_ids: set[str] = set()
    for dataset_id in dataset_ids:
        dsid = str(dataset_id or "").strip()
        if not dsid:
            continue
        dataset_path = os.path.join(dataset_dir, f"{dsid}.json")
        dataset_json = _read_json_if_exists(dataset_path)
        if not dataset_json:
            continue
        group_id = _extract_group_id_from_dataset_json(dataset_json)
        if group_id:
            group_ids.add(group_id)

    result: Dict[str, str] = {}
    for group_id in group_ids:
        try:
            members = load_group_members(group_id)
        except Exception:
            members = []
        for member in members or []:
            uid = str(member.get("id") or "").strip()
            attr = member.get("attributes") or {}
            email = (
                str(attr.get("emailAddress") or "")
                or str(attr.get("email") or "")
                or str(attr.get("mailAddress") or "")
            ).strip()
            if uid and email:
                result.setdefault(uid, email)

    return result
