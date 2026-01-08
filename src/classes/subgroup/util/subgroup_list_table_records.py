"""Build table records for subgroup listing tab.

This module loads output/rde/data/subGroup.json and converts it into
(columns, rows) suitable for the subgroup listing UI.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from config.common import get_dynamic_file_path, get_samples_dir_path
from classes.subgroup.util.related_dataset_fetcher import RelatedDatasetFetcher

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubgroupListColumn:
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


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        # Common JSON:API pattern
        data = value.get("data")
        if isinstance(data, list):
            return data
    return []


def _load_json_file(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        LOGGER.debug("Failed to load json: %s", path, exc_info=True)
        return None


def _coerce_items(payload: Any) -> List[dict]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        included = payload.get("included")
        if isinstance(included, list):
            return [it for it in included if isinstance(it, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [it for it in data if isinstance(it, dict)]
        if isinstance(data, dict):
            return [data]
    if isinstance(payload, list):
        return [it for it in payload if isinstance(it, dict)]
    return []


def _join_display(
    values: List[Any],
    *,
    prefer_keys: Tuple[str, ...] = ("name", "nameJa", "title", "grantNumber", "id"),
    separator: str = ", ",
) -> str:
    parts: List[str] = []
    for it in values:
        if isinstance(it, dict):
            # JSON:API: {id,type,attributes}
            attrs = it.get("attributes") if isinstance(it.get("attributes"), dict) else {}
            for k in prefer_keys:
                v = attrs.get(k)
                if v is None:
                    v = it.get(k)
                s = _safe_str(v).strip()
                if s:
                    parts.append(s)
                    break
            else:
                s = _safe_str(it.get("id")).strip()
                if s:
                    parts.append(s)
        else:
            s = _safe_str(it).strip()
            if s:
                parts.append(s)

    # De-dup while preserving order
    seen = set()
    uniq: List[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return separator.join(uniq)


def build_subgroup_list_rows_from_files() -> Tuple[List[SubgroupListColumn], List[Dict[str, Any]]]:
    """Load output/rde/data/subGroup.json and return (columns, rows)."""

    subgroup_json_path = get_dynamic_file_path("output/rde/data/subGroup.json")
    payload = _load_json_file(subgroup_json_path)

    # Resolve user ids -> names (same source as edit tab: subGroup.json included users)
    user_map: Dict[str, Dict[str, str]] = {}
    try:
        included = payload.get("included", []) if isinstance(payload, dict) else []
        if isinstance(included, list):
            for item in included:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "user":
                    continue
                user_id = _safe_str(item.get("id")).strip()
                attrs_u = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
                if user_id:
                    user_map[user_id] = {
                        "userName": _safe_str(attrs_u.get("userName") or user_id),
                        "emailAddress": _safe_str(attrs_u.get("emailAddress") or ""),
                    }
    except Exception:
        user_map = {}

    # Fallback: try SubgroupDataManager if payload has no users
    if not user_map:
        try:
            from classes.subgroup.core.subgroup_data_manager import SubgroupDataManager

            user_entries = SubgroupDataManager.load_user_entries()
            if isinstance(user_entries, list):
                user_map = SubgroupDataManager.create_user_map(user_entries)
        except Exception:
            user_map = {}

    # User cache (edit tab complements missing userName/email via cache/API)
    try:
        from classes.subgroup.core.user_cache_manager import get_cached_user  # type: ignore
    except Exception:
        get_cached_user = None  # type: ignore

    # Edit/repair tab helper (unified member resolution). We avoid API by not passing bearer_token.
    try:
        from classes.subgroup.core.subgroup_api_helper import load_unified_member_list  # type: ignore
    except Exception:
        load_unified_member_list = None  # type: ignore

    unified_member_info_cache: Dict[str, Dict[str, Any]] = {}

    # Related datasets via dataset.json (same logic as edit tab)
    related_dataset_fetcher = RelatedDatasetFetcher(
        dataset_json_path=get_dynamic_file_path("output/rde/data/dataset.json")
    )

    # subGroup.json often uses JSON:API: groups in `data`, related resources in `included`.
    # We need both: list groups from `data` while using `included` for enrichment.
    items: List[dict] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        included = payload.get("included")
        if isinstance(data, list):
            items.extend([it for it in data if isinstance(it, dict)])
        elif isinstance(data, dict):
            items.append(data)
        if isinstance(included, list):
            items.extend([it for it in included if isinstance(it, dict)])
    else:
        items = _coerce_items(payload)

    columns: List[SubgroupListColumn] = [
        SubgroupListColumn("subgroup_id", "グループID"),
        SubgroupListColumn("subgroup_name", "グループ名"),
        SubgroupListColumn("description", "説明"),
        SubgroupListColumn("subjects", "課題"),
        SubgroupListColumn("subject_count", "課題数"),
        SubgroupListColumn("funds", "研究資金"),
        SubgroupListColumn("fund_count", "研究資金数"),
        SubgroupListColumn("members", "メンバー"),
        SubgroupListColumn("member_count", "メンバー数"),
        SubgroupListColumn("related_datasets", "関連データセット"),
        SubgroupListColumn("related_datasets_count", "関連データセット数"),
        SubgroupListColumn("related_samples", "関連試料"),
        SubgroupListColumn("related_samples_count", "関連試料数"),
    ]

    rows: List[Dict[str, Any]] = []
    for it in items:
        # subGroup.json usually mixes different JSON:API resources.
        # We only display subgroup (group) items.
        it_type = _safe_str(it.get("type")).strip()
        if it_type and it_type != "group":
            continue

        attrs = it.get("attributes") if isinstance(it.get("attributes"), dict) else {}
        rels = it.get("relationships") if isinstance(it.get("relationships"), dict) else {}

        subgroup_id = _safe_str(it.get("id")).strip()
        subgroup_name = _safe_str(attrs.get("name") or attrs.get("nameJa") or attrs.get("title") or it.get("name")).strip()
        description = _safe_str(attrs.get("description") or attrs.get("descriptionJa") or attrs.get("detail") or "").strip()

        subjects_list = _coerce_list(attrs.get("subjects"))
        funds_list = _coerce_list(attrs.get("funds"))

        # members: prefer roles.userId (edit tab behavior), then relationships.members.data
        member_ids: List[str] = []
        roles = attrs.get("roles")
        if isinstance(roles, list) and roles:
            for role in roles:
                if not isinstance(role, dict):
                    continue
                mid = _safe_str(role.get("userId")).strip()
                if mid:
                    member_ids.append(mid)

        if not member_ids:
            members_rels = rels.get("members") if isinstance(rels.get("members"), dict) else {}
            members_data = _coerce_list(members_rels)
            if not members_data:
                members_data = _coerce_list(attrs.get("members"))
            for m in members_data:
                if isinstance(m, dict):
                    mid = _safe_str(m.get("id")).strip()
                    if mid:
                        member_ids.append(mid)
                else:
                    s = _safe_str(m).strip()
                    if s:
                        member_ids.append(s)

        # Resolve member names as reliably as possible (view/edit tab approach).
        member_info_for_group: Dict[str, Any] = {}
        if subgroup_id and subgroup_id not in unified_member_info_cache and load_unified_member_list is not None:
            try:
                _users, info = load_unified_member_list(subgroup_id=subgroup_id, bearer_token=None)
                unified_member_info_cache[subgroup_id] = info if isinstance(info, dict) else {}
            except Exception:
                unified_member_info_cache[subgroup_id] = {}
        if subgroup_id:
            member_info_for_group = unified_member_info_cache.get(subgroup_id, {})

        member_names: List[str] = []
        for mid in member_ids:
            if not mid:
                continue
            resolved = ""
            try:
                info = user_map.get(mid) or {}
                resolved = _safe_str(info.get("userName") if isinstance(info, dict) else "").strip()
            except Exception:
                resolved = ""
            if not resolved:
                try:
                    info2 = member_info_for_group.get(mid) if isinstance(member_info_for_group, dict) else None
                    if isinstance(info2, dict):
                        resolved = _safe_str(info2.get("userName") or "").strip()
                except Exception:
                    resolved = ""
            if (not resolved or resolved in {"Unknown", "Unknown User"}) and get_cached_user is not None:
                try:
                    cached = get_cached_user(mid)
                    if isinstance(cached, dict):
                        resolved = _safe_str(cached.get("userName") or "").strip() or resolved
                except Exception:
                    pass
            member_names.append(resolved or mid)

        # De-dup while preserving order
        member_names = list(dict.fromkeys([n for n in member_names if n]))

        # related datasets: use dataset.json + grantNumbers from subjects (edit tab behavior)
        grant_numbers: List[str] = []
        if isinstance(subjects_list, list):
            for subject in subjects_list:
                if isinstance(subject, dict):
                    grant = subject.get("grantNumber")
                    if isinstance(grant, str) and grant.strip():
                        grant_numbers.append(grant.strip())
        related_datasets = related_dataset_fetcher.get_related_datasets(grant_numbers)
        related_dataset_pairs: List[tuple[str, str]] = []
        for d in related_datasets:
            if not isinstance(d, dict):
                continue
            did = _safe_str(d.get("id")).strip()
            dname = _safe_str(d.get("name") or d.get("id") or "").strip()
            if did and dname:
                related_dataset_pairs.append((did, dname))

        # De-dup by dataset id while preserving order
        seen_ds: set[str] = set()
        related_dataset_ids: List[str] = []
        related_dataset_names: List[str] = []
        for did, dname in related_dataset_pairs:
            if did in seen_ds:
                continue
            seen_ds.add(did)
            related_dataset_ids.append(did)
            related_dataset_names.append(dname)

        # related samples: load samples/<subgroup_id>.json (RelatedSamplesDialog behavior)
        related_sample_pairs: List[tuple[str, str]] = []
        try:
            samples_dir = get_samples_dir_path()
            sample_file = os.path.join(samples_dir, f"{subgroup_id}.json")
            sample_payload = _load_json_file(sample_file) if os.path.exists(sample_file) else None
            sample_items = []
            if isinstance(sample_payload, dict):
                sample_items = sample_payload.get("data", [])
            if isinstance(sample_items, list):
                for sample in sample_items:
                    if not isinstance(sample, dict):
                        continue
                    sid = _safe_str(sample.get("id")).strip()
                    attrs_s = sample.get("attributes") if isinstance(sample.get("attributes"), dict) else {}
                    names = attrs_s.get("names")
                    display_name = ""
                    if isinstance(names, list) and names:
                        display_name = _safe_str(names[0]).strip()
                    if not display_name:
                        display_name = sid
                    if sid and display_name:
                        related_sample_pairs.append((sid, display_name))
        except Exception:
            pass

        # De-dup by sample id while preserving order
        seen_samples: set[str] = set()
        related_sample_ids_unique: List[str] = []
        related_sample_names_unique: List[str] = []
        for sid, sname in related_sample_pairs:
            if not sid or sid in seen_samples:
                continue
            seen_samples.add(sid)
            related_sample_ids_unique.append(sid)
            related_sample_names_unique.append(sname)

        row: Dict[str, Any] = {
            "subgroup_id": subgroup_id,
            "subgroup_name": subgroup_name,
            "description": description,
            "subjects": _join_display(subjects_list, prefer_keys=("grantNumber", "title", "name", "id"), separator="\n"),
            "subject_count": len(subjects_list),
            "funds": _join_display(funds_list, prefer_keys=("fundNumber", "title", "name", "id")),
            "fund_count": len(funds_list),
            "members": "\n".join(member_names),
            "member_count": len(member_names),
            "related_datasets": "\n".join(dict.fromkeys(related_dataset_names)),
            "related_datasets_count": len(related_dataset_names),
            "related_samples": "\n".join(related_sample_names_unique),
            "related_samples_count": len(related_sample_names_unique),
            "related_dataset_ids": related_dataset_ids,
            "related_sample_ids": related_sample_ids_unique,
        }

        rows.append(row)

    # Stable ordering by name then id
    rows.sort(key=lambda r: ((r.get("subgroup_name") or ""), (r.get("subgroup_id") or "")))

    return columns, rows
