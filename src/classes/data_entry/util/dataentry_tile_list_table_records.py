"""Build table records for aggregated data entry (tile) listing.

This module is UI-agnostic:
- Reads dataset.json / subGroup.json / self.json / dataEntry/*.json
- Produces (columns, rows) for a listing table.

All file paths must be obtained via config.common.get_dynamic_file_path.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from config.common import get_dynamic_file_path


@dataclass(frozen=True)
class DataEntryTileListColumn:
    key: str
    label: str
    default_visible: bool = True


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _extract_rel_id(dataset_item: Dict[str, Any], rel_key: str) -> str:
    rels = dataset_item.get("relationships")
    if not isinstance(rels, dict):
        return ""
    rel = rels.get(rel_key)
    if not isinstance(rel, dict):
        return ""
    data = rel.get("data")
    if isinstance(data, dict):
        return _safe_str(data.get("id")).strip()
    return ""


def _get_user_grant_numbers() -> set[str]:
    """Return grant numbers for TEAM groups where current user is a member."""

    self_path = get_dynamic_file_path("output/rde/data/self.json")
    subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")

    user_id = ""
    self_payload = _load_json(self_path)
    if isinstance(self_payload, dict):
        user_id = _safe_str(self_payload.get("data", {}).get("id")).strip()
    if not user_id:
        return set()

    payload = _load_json(subgroup_path)
    included = payload.get("included", []) if isinstance(payload, dict) else []
    if not isinstance(included, list):
        return set()

    out: set[str] = set()
    for item in included:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "group":
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        if attrs.get("groupType") != "TEAM":
            continue
        roles = attrs.get("roles")
        if not isinstance(roles, list):
            continue
        if not any(isinstance(r, dict) and _safe_str(r.get("userId")).strip() == user_id for r in roles):
            continue
        subjects = attrs.get("subjects")
        if not isinstance(subjects, list):
            continue
        for s in subjects:
            if not isinstance(s, dict):
                continue
            gn = _safe_str(s.get("grantNumber")).strip()
            if gn:
                out.add(gn)
    return out


def get_default_columns() -> List[DataEntryTileListColumn]:
    return [
        DataEntryTileListColumn("subgroup_name", "サブグループ"),
        DataEntryTileListColumn("grant_number", "課題番号"),
        DataEntryTileListColumn("dataset_name", "データセット"),
        DataEntryTileListColumn("data_number", "タイルNo"),
        DataEntryTileListColumn("tile_name", "タイル名"),
        DataEntryTileListColumn("tile_id", "タイルUUID"),
        DataEntryTileListColumn("dataset_id", "データセットUUID"),
        DataEntryTileListColumn("subgroup_id", "サブグループUUID"),
        DataEntryTileListColumn("number_of_files", "ファイル"),
        DataEntryTileListColumn("number_of_image_files", "画像"),
        DataEntryTileListColumn("created_date", "作成日"),
        DataEntryTileListColumn("description", "説明", default_visible=False),
    ]


def build_dataentry_tile_list_rows_from_files(
    *,
    filter_mode: str = "user_only",
    grant_number_filter: str = "",
) -> Tuple[List[DataEntryTileListColumn], List[Dict[str, Any]]]:
    """Build rows for tile listing.

    Args:
        filter_mode: one of {"user_only", "others_only", "all"}
        grant_number_filter: substring match for grantNumber
    """

    dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
    subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
    dataentry_dir = get_dynamic_file_path("output/rde/data/dataEntry")

    datasets_payload = _load_json(dataset_path)
    datasets = datasets_payload.get("data", []) if isinstance(datasets_payload, dict) else []
    if not isinstance(datasets, list):
        datasets = []

    subgroup_payload = _load_json(subgroup_path)
    subgroup_name_by_id: Dict[str, str] = {}
    subgroup_id_by_grant_number: Dict[str, str] = {}
    included = subgroup_payload.get("included", []) if isinstance(subgroup_payload, dict) else []
    if isinstance(included, list):
        for item in included:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "group":
                continue
            sid = _safe_str(item.get("id")).strip()
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            group_type = _safe_str(attrs.get("groupType")).strip().upper()
            name = _safe_str(attrs.get("name") or attrs.get("nameJa") or "").strip()
            if sid and name:
                subgroup_name_by_id[sid] = name

            # Best-effort: grantNumber -> subgroup_id (TEAM only)
            if sid and group_type == "TEAM":
                subjects = attrs.get("subjects")
                if isinstance(subjects, list):
                    for s in subjects:
                        if not isinstance(s, dict):
                            continue
                        gn = _safe_str(s.get("grantNumber")).strip()
                        if gn and gn not in subgroup_id_by_grant_number:
                            subgroup_id_by_grant_number[gn] = sid

    user_grants = _get_user_grant_numbers() if filter_mode in {"user_only", "others_only"} else set()
    grant_filter = (grant_number_filter or "").strip().lower()

    dataset_infos: List[Dict[str, Any]] = []
    for ds in datasets:
        if not isinstance(ds, dict):
            continue
        dsid = _safe_str(ds.get("id")).strip()
        attrs = ds.get("attributes") if isinstance(ds.get("attributes"), dict) else {}
        grant = _safe_str(attrs.get("grantNumber")).strip()
        if grant_filter and grant_filter not in grant.lower():
            continue

        if filter_mode == "user_only" and user_grants and grant not in user_grants:
            continue
        if filter_mode == "others_only" and user_grants and grant in user_grants:
            continue

        subgroup_id = _extract_rel_id(ds, "subGroup")
        if not subgroup_id:
            subgroup_id = _extract_rel_id(ds, "subgroup")
        if not subgroup_id and grant:
            subgroup_id = subgroup_id_by_grant_number.get(grant, "")
        name = _safe_str(attrs.get("name") or "").strip()
        dataset_infos.append(
            {
                "dataset_id": dsid,
                "dataset_name": name,
                "grant_number": grant,
                "subgroup_id": subgroup_id,
                "subgroup_name": subgroup_name_by_id.get(subgroup_id, ""),
            }
        )

    columns = get_default_columns()
    rows: List[Dict[str, Any]] = []

    for info in dataset_infos:
        dataset_id = _safe_str(info.get("dataset_id")).strip()
        if not dataset_id:
            continue

        dataentry_file = os.path.join(dataentry_dir, f"{dataset_id}.json") if dataentry_dir else ""
        payload = _load_json(dataentry_file) if dataentry_file and os.path.exists(dataentry_file) else None
        if not isinstance(payload, dict):
            continue
        entries = payload.get("data", [])
        if not isinstance(entries, list):
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            attrs = entry.get("attributes") if isinstance(entry.get("attributes"), dict) else {}
            entry_id = _safe_str(entry.get("id")).strip()
            created_at = _safe_str(attrs.get("createdAt") or attrs.get("created") or "").strip()
            created_date = created_at.split("T")[0] if created_at else ""
            subgroup_id = _safe_str(info.get("subgroup_id")).strip()
            rows.append(
                {
                    "subgroup_name": info.get("subgroup_name") or "",
                    "grant_number": info.get("grant_number") or "",
                    "dataset_name": info.get("dataset_name") or "",
                    "data_number": _safe_str(attrs.get("dataNumber")).strip(),
                    "tile_name": _safe_str(attrs.get("name")).strip(),
                    "tile_id": entry_id,
                    "dataset_id": dataset_id,
                    "subgroup_id": subgroup_id,
                    "number_of_files": attrs.get("numberOfFiles"),
                    "number_of_image_files": attrs.get("numberOfImageFiles"),
                    "created_date": created_date,
                    "description": _safe_str(attrs.get("description")).strip(),
                    "_tile_url": f"https://rde.nims.go.jp/rde/datasets/data/{entry_id}" if entry_id else "",
                    "_dataset_url": f"https://rde.nims.go.jp/rde/datasets/{dataset_id}" if dataset_id else "",
                    "_subgroup_url": f"https://rde.nims.go.jp/rde/datasets/groups/{subgroup_id}" if subgroup_id else "",
                }
            )

    rows.sort(
        key=lambda r: (
            str(r.get("subgroup_name") or ""),
            str(r.get("grant_number") or ""),
            str(r.get("dataset_name") or ""),
            str(r.get("data_number") or ""),
        )
    )
    return columns, rows
