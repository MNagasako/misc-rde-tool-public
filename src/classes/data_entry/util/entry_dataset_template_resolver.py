import json
import logging
import os
from typing import Any, Dict, Iterable, Optional

from config.common import get_dynamic_file_path

logger = logging.getLogger(__name__)


def _read_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.debug("Failed to read json: path=%s err=%s", path, exc)
        return None


def _extract_dataset_id_from_entry_json(entry_json: Dict[str, Any]) -> str:
    data = (entry_json or {}).get("data") or {}
    rel = data.get("relationships") or {}
    dataset = (rel.get("dataset") or {}).get("data") or {}
    return str(dataset.get("id") or "")


def _extract_dataset_template_id_from_dataset_json(dataset_json: Dict[str, Any]) -> str:
    data = (dataset_json or {}).get("data") or {}
    rel = data.get("relationships") or {}
    tmpl = rel.get("template") or {}
    tmpl_data = (tmpl.get("data") or {}) if isinstance(tmpl, dict) else {}
    return str((tmpl_data or {}).get("id") or "")


def _extract_dataset_template_name_from_included(dataset_json: Dict[str, Any], template_id: str) -> str:
    if not template_id:
        return ""

    included = dataset_json.get("included")
    if not isinstance(included, list):
        return ""

    for inc in included:
        if not isinstance(inc, dict):
            continue
        if str(inc.get("id") or "") != str(template_id):
            continue
        # APIによって type の揺れがあり得る
        inc_type = str(inc.get("type") or "")
        if inc_type and inc_type not in ("datasetTemplate", "template"):
            continue
        attrs = inc.get("attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {}
        name = str(attrs.get("nameJa") or "").strip() or str(attrs.get("nameEn") or "").strip()
        if name:
            return name
    return ""


def build_dataset_template_name_map_for_entry_ids(
    entry_ids: Iterable[str],
    *,
    entry_dir: Optional[str] = None,
    dataset_dir: Optional[str] = None,
) -> Dict[str, str]:
    """entryId 群から entry→dataset→template を辿り、datasetTemplate の表示名を解決する。

    - entry: output/rde/data/entry/<entryId>.json
    - dataset: output/rde/data/datasets/<datasetId>.json
    - datasetTemplate name: dataset.json の included から nameJa/nameEn を探索
      (見つからない場合は templateId を返す)
    """

    entry_dir = entry_dir or get_dynamic_file_path("output/rde/data/entry")
    dataset_dir = dataset_dir or get_dynamic_file_path("output/rde/data/datasets")

    result: Dict[str, str] = {}

    for entry_id in entry_ids:
        eid = str(entry_id or "").strip()
        if not eid:
            continue

        entry_path = os.path.join(entry_dir, f"{eid}.json")
        entry_json = _read_json_if_exists(entry_path)
        if not entry_json:
            continue

        dataset_id = _extract_dataset_id_from_entry_json(entry_json)
        if not dataset_id:
            continue

        dataset_path = os.path.join(dataset_dir, f"{dataset_id}.json")
        dataset_json = _read_json_if_exists(dataset_path)
        if not dataset_json:
            continue

        template_id = _extract_dataset_template_id_from_dataset_json(dataset_json)
        if not template_id:
            continue

        name = _extract_dataset_template_name_from_included(dataset_json, template_id)
        result[eid] = name or template_id

    return result
