"""Sample dedup listing records.

Loads subgroup/dataset/dataEntry/sample JSON files and builds rows for the
sample dedup listing tab.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from config.common import get_dynamic_file_path
from config.site_rde import URLS
from net.http_helpers import proxy_get

logger = logging.getLogger(__name__)


_CACHE_REL_PATH = "output/rde/cache/sample_listing_cache.json"
_CACHE_VERSION = 2


def _cache_path() -> str:
    return get_dynamic_file_path(_CACHE_REL_PATH)


def _ensure_cache_dir_exists() -> None:
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
    except Exception:
        return


def compute_sample_listing_sources_signature() -> Dict[str, Any]:
    """Compute a stable signature of local source files for cache validation.

    This acts like an ETag: if signature matches, derived table rows are assumed valid.
    """

    def _mtime(path: str) -> float:
        try:
            return float(os.path.getmtime(path)) if path and os.path.exists(path) else 0.0
        except Exception:
            return 0.0

    def _dir_signature(path: str) -> Dict[str, Any]:
        sig = {"path": str(path), "count": 0, "latest_mtime": 0.0}
        try:
            if not path or not os.path.isdir(path):
                return sig
            latest = 0.0
            count = 0
            with os.scandir(path) as it:
                for entry in it:
                    if not entry.is_file():
                        continue
                    count += 1
                    try:
                        mt = float(entry.stat().st_mtime)
                    except Exception:
                        mt = 0.0
                    if mt > latest:
                        latest = mt
            sig["count"] = count
            sig["latest_mtime"] = latest
        except Exception:
            return sig
        return sig

    subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
    dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
    data_entry_dir = get_dynamic_file_path("output/rde/data/dataEntry")
    samples_dir = get_dynamic_file_path("output/rde/data/samples")

    return {
        "subGroup.json_mtime": _mtime(subgroup_path),
        "dataset.json_mtime": _mtime(dataset_path),
        "dataEntry_dir": _dir_signature(data_entry_dir),
        "samples_dir": _dir_signature(samples_dir),
    }


def _cache_updated_at_epoch(cache_payload: Dict[str, Any]) -> float:
    try:
        return float(cache_payload.get("updated_at_epoch") or 0.0)
    except Exception:
        return 0.0


def is_sample_listing_cache_fresh(
    cache_payload: Dict[str, Any],
    *,
    sources_signature: Dict[str, Any],
    ttl_seconds: int,
) -> bool:
    """Return True if cache is usable without refresh.

    Priority: signature (ETag-like) match, then TTL.
    """

    if not isinstance(cache_payload, dict):
        return False
    if int(cache_payload.get("version") or 0) != _CACHE_VERSION:
        return False

    cached_sig = cache_payload.get("sources_signature")
    if isinstance(cached_sig, dict) and cached_sig == sources_signature:
        return True

    # Fallback: TTL
    updated_at = _cache_updated_at_epoch(cache_payload)
    if updated_at <= 0:
        return False
    age = time.time() - updated_at
    return age <= float(max(0, int(ttl_seconds)))


def load_sample_listing_cache() -> Dict[str, Any]:
    """Load persisted cache. Returns {} when missing/invalid."""
    path = _cache_path()
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def save_sample_listing_cache(cache_payload: Dict[str, Any]) -> None:
    if not isinstance(cache_payload, dict):
        return
    _ensure_cache_dir_exists()
    path = _cache_path()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cache_payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        logger.debug("Failed to save sample listing cache", exc_info=True)


def update_sample_listing_cache_for_subgroups(subgroup_ids: Iterable[str]) -> bool:
    """Rebuild and merge sample listing (一覧) rows into the persisted cache.

    This is intended to be called after an operation that changes local JSON sources
    (e.g., relinking a tile to a different sample) so the cache does not keep showing
    stale content.

    Args:
        subgroup_ids: Target subgroup ids to refresh in the cache.

    Returns:
        True if an update was attempted, False if inputs were empty/invalid.
    """

    ids = [str(x).strip() for x in (subgroup_ids or []) if str(x).strip()]
    if not ids:
        return False

    try:
        signature = compute_sample_listing_sources_signature()
        _columns, rows, _missing = build_sample_dedup_rows_from_files(ids)
        new_rows = [r for r in (rows or []) if isinstance(r, dict)]

        cache_payload = load_sample_listing_cache()
        merged = merge_rows_into_cache(
            cache_payload,
            subgroup_ids=ids,
            subgroup_order=ids,
            rows=new_rows,
            sources_signature=signature,
        )
        save_sample_listing_cache(merged)
        return True
    except Exception:
        logger.debug("Failed to update sample listing cache for subgroups", exc_info=True)
        return False


def _ensure_cache_shape(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    if int(payload.get("version") or 0) != _CACHE_VERSION:
        payload = {}

    rows_by_subgroup = payload.get("rows_by_subgroup")
    if not isinstance(rows_by_subgroup, dict):
        rows_by_subgroup = {}

    subgroup_order = payload.get("subgroup_order")
    if not isinstance(subgroup_order, list):
        subgroup_order = []

    payload.setdefault("version", _CACHE_VERSION)
    payload["rows_by_subgroup"] = rows_by_subgroup
    payload["subgroup_order"] = subgroup_order
    return payload


def extract_cached_rows(
    cache_payload: Dict[str, Any],
    *,
    subgroup_ids: List[str],
    subgroup_order: List[str],
) -> List[Dict[str, Any]]:
    payload = _ensure_cache_shape(cache_payload)
    rows_by_subgroup = payload.get("rows_by_subgroup") or {}
    if not isinstance(rows_by_subgroup, dict):
        return []

    wanted = {str(x).strip() for x in (subgroup_ids or []) if str(x).strip()}
    # Prefer caller-provided order; fall back to cache order; finally fall back to stable key order.
    ordered = [str(x).strip() for x in (subgroup_order or []) if str(x).strip()]
    if not ordered:
        ordered = [str(x).strip() for x in (payload.get("subgroup_order") or []) if str(x).strip()]
    if not ordered:
        ordered = [str(x).strip() for x in rows_by_subgroup.keys() if str(x).strip()]
    if wanted:
        ordered = [sid for sid in ordered if sid in wanted]
        # add any missing subgroup ids in stable order
        for sid in subgroup_ids:
            ss = str(sid).strip()
            if ss and ss not in ordered:
                ordered.append(ss)

    out: List[Dict[str, Any]] = []
    for sid in ordered:
        rows = rows_by_subgroup.get(sid)
        if isinstance(rows, list):
            out.extend([r for r in rows if isinstance(r, dict)])
    return out


def merge_rows_into_cache(
    cache_payload: Dict[str, Any],
    *,
    subgroup_ids: List[str],
    subgroup_order: List[str],
    rows: List[Dict[str, Any]],
    sources_signature: Dict[str, Any],
) -> Dict[str, Any]:
    payload = _ensure_cache_shape(cache_payload)
    rows_by_subgroup = payload.get("rows_by_subgroup")
    if not isinstance(rows_by_subgroup, dict):
        rows_by_subgroup = {}

    wanted = {str(x).strip() for x in (subgroup_ids or []) if str(x).strip()}
    # Group new rows by subgroup_id
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sid = _safe_str(row.get("subgroup_id")).strip()
        if wanted and sid not in wanted:
            continue
        grouped.setdefault(sid, []).append(row)

    # Update cache for affected subgroups.
    for sid in (wanted or set(grouped.keys())):
        rows_by_subgroup[sid] = grouped.get(sid, [])

    payload["rows_by_subgroup"] = rows_by_subgroup

    # Do not overwrite existing order with an empty order (can happen when subgroup metadata is unavailable).
    normalized_order = [str(x).strip() for x in (subgroup_order or []) if str(x).strip()]
    if not normalized_order:
        normalized_order = [str(x).strip() for x in (payload.get("subgroup_order") or []) if str(x).strip()]
    seen: set[str] = set()
    ordered: list[str] = []
    for sid in normalized_order:
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    # Ensure any updated subgroup ids are present (stable append).
    for sid in (wanted or set(grouped.keys())):
        ss = str(sid).strip()
        if ss and ss not in seen:
            seen.add(ss)
            ordered.append(ss)
    for sid in rows_by_subgroup.keys():
        ss = str(sid).strip()
        if ss and ss not in seen:
            seen.add(ss)
            ordered.append(ss)

    payload["subgroup_order"] = ordered
    payload["sources_signature"] = sources_signature if isinstance(sources_signature, dict) else {}
    payload["updated_at_epoch"] = float(time.time())
    return payload


@dataclass(frozen=True)
class SampleDedupColumn:
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


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _load_json(path: str) -> Any:
    try:
        if not path or not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        logger.debug("Failed to load json: %s", path, exc_info=True)
        return None


def _extract_group_id_from_dataset_item(item: Dict[str, Any]) -> str:
    rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
    group = rels.get("group") if isinstance(rels.get("group"), dict) else {}
    data = group.get("data") if isinstance(group.get("data"), dict) else {}
    return _safe_str(data.get("id")).strip()


def _extract_group_id_from_dataset_detail(dataset_id: str) -> str:
    dsid = _safe_str(dataset_id).strip()
    if not dsid:
        return ""
    detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dsid}.json")
    payload = _load_json(detail_path)
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rels = data.get("relationships") if isinstance(data.get("relationships"), dict) else {}
    group = rels.get("group") if isinstance(rels.get("group"), dict) else {}
    data_rel = group.get("data") if isinstance(group.get("data"), dict) else {}
    return _safe_str(data_rel.get("id")).strip()


def _extract_grants_from_dataset_detail(dataset_id: str) -> List[str]:
    dsid = _safe_str(dataset_id).strip()
    if not dsid:
        return []
    detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dsid}.json")
    payload = _load_json(detail_path)
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    if not attrs:
        return []

    grants = _extract_grants_from_subjects(attrs.get("subjects"))
    if not grants:
        grants = _extract_grants_from_subjects(attrs.get("subject"))
    if not grants:
        single = _safe_str(attrs.get("grantNumber")).strip()
        if single:
            grants = [single]
    return grants


def _normalize_sample_name(name: str) -> str:
    text = _safe_str(name).strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[\-_/\\.]+", "", text)
    return text


def get_default_columns() -> List[SampleDedupColumn]:
    return [
        SampleDedupColumn("subgroup_name", "サブグループ名", True),
        SampleDedupColumn("subgroup_id", "サブグループUUID", False),
        SampleDedupColumn("subgroup_description", "サブグループ説明", True),
        SampleDedupColumn("grant_numbers", "課題番号", True),
        SampleDedupColumn("dataset_names", "データセット名", True),
        SampleDedupColumn("dataset_ids", "データセットUUID", False),
        SampleDedupColumn("data_entry_names", "タイル名", True),
        SampleDedupColumn("data_entry_ids", "タイルUUID", False),
        SampleDedupColumn("sample_name", "試料名", True),
        SampleDedupColumn("sample_id", "試料UUID", True),
        SampleDedupColumn("sample_edit", "編集", True),
        SampleDedupColumn("data_entry_count", "タイル数", True),
        SampleDedupColumn("dataset_count", "データセット数", True),
        SampleDedupColumn("subgroup_dataset_count", "サブグループ内データセット数", False),
        SampleDedupColumn("sample_names", "別名", False),
        SampleDedupColumn("composition", "組成", False),
        SampleDedupColumn("description", "説明", False),
        SampleDedupColumn("tags", "TAG", False),
        SampleDedupColumn("reference_url", "参照URL", False),
        SampleDedupColumn("name_key", "名寄せキー", False),
    ]


def get_default_columns_list2() -> List[SampleDedupColumn]:
    """Default columns for the alternative listing mode (一覧2).

    Join order: subgroup -> samples -> data entries (tiles) -> datasets.
    """

    return [
        SampleDedupColumn("subgroup_name", "サブグループ名", True),
        SampleDedupColumn("sample_name", "試料名", True),
        SampleDedupColumn("tile_dataset_grant", "タイル－データセット－課題番号", True),
        SampleDedupColumn("data_entry_count", "タイル数", True),
        SampleDedupColumn("dataset_count", "データセット数", True),
        SampleDedupColumn("grant_count", "課題番号数", True),
        SampleDedupColumn("grant_numbers", "課題番号", False),
        # UUID columns (default visible in 一覧2)
        SampleDedupColumn("subgroup_id", "サブグループUUID", True),
        SampleDedupColumn("sample_id", "試料UUID", True),
        SampleDedupColumn("sample_edit", "編集", True),
        SampleDedupColumn("dataset_ids", "データセットUUID", True),
        SampleDedupColumn("data_entry_ids", "タイルUUID", True),
    ]


def _build_subgroup_maps() -> tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    subgroup_json_path = get_dynamic_file_path("output/rde/data/subGroup.json")
    payload = _load_json(subgroup_json_path)
    if not isinstance(payload, dict):
        return {}, {}
    included = payload.get("included")
    if not isinstance(included, list):
        return {}, {}
    subgroup_name_by_id: Dict[str, str] = {}
    subgroup_grants_by_id: Dict[str, str] = {}
    subgroup_desc_by_id: Dict[str, str] = {}
    for item in included:
        if not isinstance(item, dict):
            continue
        subgroup_id = _safe_str(item.get("id")).strip()
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        name = _safe_str(attrs.get("name") or attrs.get("title")).strip() if attrs else ""
        desc = _safe_str(attrs.get("description")).strip() if attrs else ""
        subjects = attrs.get("subjects") if isinstance(attrs.get("subjects"), list) else []
        grants: list[str] = []
        seen: set[str] = set()
        for s in subjects:
            if not isinstance(s, dict):
                continue
            gn = _safe_str(s.get("grantNumber")).strip()
            if not gn or gn in seen:
                continue
            seen.add(gn)
            grants.append(gn)
        if subgroup_id:
            subgroup_name_by_id[subgroup_id] = name
            subgroup_grants_by_id[subgroup_id] = "\n".join(grants)
            subgroup_desc_by_id[subgroup_id] = desc
    return subgroup_name_by_id, subgroup_grants_by_id, subgroup_desc_by_id


def _build_dataset_maps() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
    payload = _load_json(dataset_json_path)
    dataset_items = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(dataset_items, list):
        dataset_items = []

    dataset_name_by_id: Dict[str, str] = {}
    dataset_ids_by_group: Dict[str, List[str]] = {}

    for item in dataset_items:
        if not isinstance(item, dict):
            continue
        dataset_id = _safe_str(item.get("id")).strip()
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        dataset_name = _safe_str(attrs.get("name")).strip() if attrs else ""
        if dataset_id:
            if dataset_name:
                dataset_name_by_id[dataset_id] = dataset_name
            group_id = _extract_group_id_from_dataset_item(item)
            if not group_id:
                group_id = _extract_group_id_from_dataset_detail(dataset_id)
            if group_id:
                dataset_ids_by_group.setdefault(group_id, []).append(dataset_id)

    return dataset_name_by_id, dataset_ids_by_group


def _extract_grants_from_subjects(subjects: Any) -> List[str]:
    if not isinstance(subjects, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for s in subjects:
        if not isinstance(s, dict):
            continue
        gn = _safe_str(s.get("grantNumber")).strip()
        if not gn or gn in seen:
            continue
        seen.add(gn)
        out.append(gn)
    return out


def _pick_single_join_grant_number(*, subgroup_grants_text: str, dataset_ids: Iterable[str], dataset_grants_by_id: Dict[str, List[str]]) -> str:
    """Pick a single grant number (join key) for subgroup <-> dataset.

    Rationale:
    - subgroup subjects may contain multiple grant numbers, but the table column is used as a JOIN key and must be a single value.
    - Prefer dataset-level grant numbers (more specific). If multiple exist, pick a deterministic one.
    """

    ds_grants: list[str] = []
    seen: set[str] = set()
    for dataset_id in dataset_ids:
        dsid = _safe_str(dataset_id).strip()
        if not dsid:
            continue
        grants = dataset_grants_by_id.get(dsid, [])
        if not isinstance(grants, list):
            continue
        for g in grants:
            gn = _safe_str(g).strip()
            if not gn or gn in seen:
                continue
            seen.add(gn)
            ds_grants.append(gn)

    if ds_grants:
        # If multiple grants exist, pick stable smallest (deterministic) to satisfy "single value" constraint.
        try:
            return sorted(ds_grants)[0]
        except Exception:
            return ds_grants[0]

    # Fallback: subgroup-level grant list
    subgroup_list = [x.strip() for x in _safe_str(subgroup_grants_text).splitlines() if x.strip()]
    if subgroup_list:
        return subgroup_list[0]
    return ""


def remove_sample_from_local_samples_json(*, subgroup_id: str, sample_id: str) -> bool:
    """Remove a sample entry from output/rde/data/samples/{subgroup_id}.json.

    Returns True if the file was modified.
    """

    gid = _safe_str(subgroup_id).strip()
    sid = _safe_str(sample_id).strip()
    if not gid or not sid:
        return False

    path = get_dynamic_file_path(f"output/rde/data/samples/{gid}.json")
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return False
    data_items = payload.get("data") if isinstance(payload.get("data"), list) else []
    if not isinstance(data_items, list) or not data_items:
        return False

    before = len(data_items)
    filtered = [item for item in data_items if not (isinstance(item, dict) and _safe_str(item.get("id")).strip() == sid)]
    if len(filtered) == before:
        return False

    payload["data"] = filtered
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("[SAMPLE-PURGE] Failed to write samples json: %s", str(e))
        return False


def purge_sample_from_listing_cache(*, subgroup_id: str, sample_id: str) -> bool:
    """Remove cached listing rows for the given sample.

    Returns True if the cache payload was modified.
    """

    gid = _safe_str(subgroup_id).strip()
    sid = _safe_str(sample_id).strip()
    if not gid or not sid:
        return False

    cache_payload = load_sample_listing_cache()
    if not isinstance(cache_payload, dict):
        return False
    rows_by = cache_payload.get("rows_by_subgroup")
    if not isinstance(rows_by, dict):
        return False
    rows = rows_by.get(gid)
    if not isinstance(rows, list) or not rows:
        return False

    before = len(rows)
    rows2 = [r for r in rows if not (isinstance(r, dict) and _safe_str(r.get("sample_id")).strip() == sid)]
    if len(rows2) == before:
        return False

    rows_by[gid] = rows2
    cache_payload["rows_by_subgroup"] = rows_by
    try:
        save_sample_listing_cache(cache_payload)
        return True
    except Exception:
        return False


def purge_invalid_sample_entry(*, subgroup_id: str, sample_id: str) -> Dict[str, bool]:
    """Purge a non-existent sample from local sources (JSON + table cache)."""

    removed_json = remove_sample_from_local_samples_json(subgroup_id=subgroup_id, sample_id=sample_id)
    removed_cache = purge_sample_from_listing_cache(subgroup_id=subgroup_id, sample_id=sample_id)
    return {"removed_json": bool(removed_json), "removed_cache": bool(removed_cache)}


def _build_dataset_grants_map() -> Dict[str, List[str]]:
    """Build dataset_id -> list[grantNumber].

    Prefer dataset-level grant numbers. When unavailable, caller may fall back to subgroup grants.
    """

    dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
    payload = _load_json(dataset_json_path)
    dataset_items = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(dataset_items, list):
        dataset_items = []

    grants_by_id: Dict[str, List[str]] = {}
    for item in dataset_items:
        if not isinstance(item, dict):
            continue
        dataset_id = _safe_str(item.get("id")).strip()
        if not dataset_id:
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}

        # Common shapes observed in RDE exports.
        grants: list[str] = []
        if attrs:
            grants = _extract_grants_from_subjects(attrs.get("subjects"))
            if not grants:
                grants = _extract_grants_from_subjects(attrs.get("subject"))
            if not grants:
                single = _safe_str(attrs.get("grantNumber")).strip()
                if single:
                    grants = [single]

        if not grants:
            # Fallback: dataset.json may omit subjects; check per-dataset detail JSON.
            grants = _extract_grants_from_dataset_detail(dataset_id)

        if grants:
            grants_by_id[dataset_id] = grants

    return grants_by_id


def _build_sample_usage_details(
    dataset_ids: Iterable[str],
    *,
    dataset_name_by_id: Dict[str, str],
) -> Dict[str, List[Dict[str, str]]]:
    """Build a sample-centric list of (tile/dataset) references."""

    usage: Dict[str, List[Dict[str, str]]] = {}
    for dataset_id in dataset_ids:
        dsid = _safe_str(dataset_id).strip()
        if not dsid:
            continue
        data_entry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dsid}.json")
        payload = _load_json(data_entry_path)
        if not isinstance(payload, dict):
            continue
        entries = payload.get("data") if isinstance(payload.get("data"), list) else []
        if not isinstance(entries, list):
            entries = []

        dataset_name = dataset_name_by_id.get(dsid, dsid)

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = _safe_str(entry.get("id")).strip()
            entry_attrs = entry.get("attributes") if isinstance(entry.get("attributes"), dict) else {}
            entry_name = _safe_str(entry_attrs.get("name")).strip() if entry_attrs else ""
            sample_ids = _extract_sample_ids_from_entry(entry)
            if not sample_ids:
                continue
            for sample_id in sample_ids:
                sid = _safe_str(sample_id).strip()
                if not sid:
                    continue
                usage.setdefault(sid, []).append(
                    {
                        "data_entry_id": entry_id,
                        "data_entry_name": entry_name,
                        "dataset_id": dsid,
                        "dataset_name": dataset_name,
                    }
                )
    return usage


def _extract_sample_ids_from_entry(entry: Dict[str, Any]) -> List[str]:
    rels = entry.get("relationships") if isinstance(entry.get("relationships"), dict) else {}
    sample_rel = rels.get("sample") if isinstance(rels.get("sample"), dict) else {}
    data = sample_rel.get("data")
    if isinstance(data, dict):
        sid = _safe_str(data.get("id")).strip()
        return [sid] if sid else []
    if isinstance(data, list):
        return [_safe_str(item.get("id")).strip() for item in data if isinstance(item, dict) and _safe_str(item.get("id")).strip()]
    return []


def _build_sample_usage(dataset_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    usage: Dict[str, Dict[str, Any]] = {}
    for dataset_id in dataset_ids:
        dsid = _safe_str(dataset_id).strip()
        if not dsid:
            continue
        data_entry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dsid}.json")
        payload = _load_json(data_entry_path)
        if not isinstance(payload, dict):
            continue
        entries = payload.get("data") if isinstance(payload.get("data"), list) else []
        if not isinstance(entries, list):
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = _safe_str(entry.get("id")).strip()
            entry_attrs = entry.get("attributes") if isinstance(entry.get("attributes"), dict) else {}
            entry_name = _safe_str(entry_attrs.get("name")).strip() if entry_attrs else ""
            sample_ids = _extract_sample_ids_from_entry(entry)
            if not sample_ids:
                continue
            for sample_id in sample_ids:
                row = usage.setdefault(
                    sample_id,
                    {
                        "dataset_ids": set(),
                        "entry_count": 0,
                        "entry_ids": set(),
                        "entry_names": set(),
                    },
                )
                row["dataset_ids"].add(dsid)
                row["entry_count"] += 1
                if entry_id:
                    row["entry_ids"].add(entry_id)
                if entry_name:
                    row["entry_names"].add(entry_name)
    return usage


def _load_sample_payload(subgroup_id: str) -> Optional[Dict[str, Any]]:
    path = get_dynamic_file_path(f"output/rde/data/samples/{subgroup_id}.json")
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def build_sample_dedup_rows_from_files(
    subgroup_ids: Optional[Iterable[str]] = None,
) -> Tuple[List[SampleDedupColumn], List[Dict[str, Any]], List[str]]:
    subgroup_name_by_id, subgroup_grants_by_id, subgroup_desc_by_id = _build_subgroup_maps()
    dataset_name_by_id, dataset_ids_by_group = _build_dataset_maps()
    dataset_grants_by_id = _build_dataset_grants_map()
    usage = _build_sample_usage(dataset_name_by_id.keys())

    wanted_subgroup_ids: Optional[Set[str]] = None
    if subgroup_ids is not None:
        wanted_subgroup_ids = {str(x).strip() for x in subgroup_ids if str(x).strip()}

    columns = get_default_columns()
    rows: List[Dict[str, Any]] = []
    missing_sample_files: List[str] = []

    for subgroup_id, subgroup_name in subgroup_name_by_id.items():
        if wanted_subgroup_ids is not None and subgroup_id not in wanted_subgroup_ids:
            continue
        # grant_numbers is a JOIN key and must be a single value.
        grant_numbers = _pick_single_join_grant_number(
            subgroup_grants_text=subgroup_grants_by_id.get(subgroup_id, ""),
            dataset_ids=dataset_ids_by_group.get(subgroup_id, []),
            dataset_grants_by_id=dataset_grants_by_id,
        )
        subgroup_desc = subgroup_desc_by_id.get(subgroup_id, "")
        payload = _load_sample_payload(subgroup_id)
        if payload is None:
            missing_sample_files.append(subgroup_id)
            rows.append(
                {
                    "sample_id": "",
                    "sample_name": "",
                    "sample_names": "",
                    "composition": "",
                    "description": "",
                    "tags": "",
                    "reference_url": "",
                    "name_key": "",
                    "data_entry_count": 0,
                    "dataset_count": 0,
                    "dataset_names": "",
                    "dataset_ids": "",
                    "data_entry_names": "",
                    "data_entry_ids": "",
                    "subgroup_dataset_count": len(dataset_ids_by_group.get(subgroup_id, [])),
                    "subgroup_name": subgroup_name,
                    "subgroup_id": subgroup_id,
                    "subgroup_description": subgroup_desc,
                    "grant_numbers": grant_numbers,
                    "missing_sample": True,
                }
            )
            continue

        data_items = payload.get("data") if isinstance(payload.get("data"), list) else []
        if not data_items:
            rows.append(
                {
                    "sample_id": "",
                    "sample_name": "",
                    "sample_names": "",
                    "composition": "",
                    "description": "",
                    "tags": "",
                    "reference_url": "",
                    "name_key": "",
                    "data_entry_count": 0,
                    "dataset_count": 0,
                    "dataset_names": "",
                    "dataset_ids": "",
                    "data_entry_names": "",
                    "data_entry_ids": "",
                    "subgroup_dataset_count": len(dataset_ids_by_group.get(subgroup_id, [])),
                    "subgroup_name": subgroup_name,
                    "subgroup_id": subgroup_id,
                    "subgroup_description": subgroup_desc,
                    "grant_numbers": grant_numbers,
                    "missing_sample": False,
                }
            )
            continue

        for item in data_items:
            if not isinstance(item, dict):
                continue
            sample_id = _safe_str(item.get("id")).strip()
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            names = _safe_list(attrs.get("names")) if attrs else []
            names = [str(x) for x in names if _safe_str(x).strip()]
            sample_name = names[0] if names else ""
            composition = _safe_str(attrs.get("composition")).strip() if attrs else ""
            description = _safe_str(attrs.get("description")).strip() if attrs else ""
            tags = _safe_list(attrs.get("tags")) if attrs else []
            tags = [str(x) for x in tags if _safe_str(x).strip()]
            reference_url = _safe_str(attrs.get("referenceUrl")).strip() if attrs else ""

            usage_row = usage.get(
                sample_id,
                {"dataset_ids": set(), "entry_count": 0, "entry_ids": set(), "entry_names": set()},
            )
            dataset_ids: Set[str] = set(usage_row.get("dataset_ids", set()))
            dataset_names = [dataset_name_by_id.get(dsid, dsid) for dsid in sorted(dataset_ids)]
            entry_ids: Set[str] = set(usage_row.get("entry_ids", set()))
            entry_names: Set[str] = set(usage_row.get("entry_names", set()))

            # grant_numbers is a JOIN key and must be a single value.
            grant_numbers_for_row = _pick_single_join_grant_number(
                subgroup_grants_text=subgroup_grants_by_id.get(subgroup_id, ""),
                dataset_ids=sorted(dataset_ids),
                dataset_grants_by_id=dataset_grants_by_id,
            )

            rows.append(
                {
                    "sample_id": sample_id,
                    "sample_name": sample_name,
                    "sample_names": "\n".join(names),
                    "composition": composition,
                    "description": description,
                    "tags": "\n".join(tags),
                    "reference_url": reference_url,
                    "name_key": _normalize_sample_name(sample_name),
                    "data_entry_count": int(usage_row.get("entry_count", 0) or 0),
                    "dataset_count": len(dataset_ids),
                    "dataset_names": "\n".join([n for n in dataset_names if n]),
                    "dataset_ids": "\n".join(sorted(dataset_ids)),
                    "data_entry_names": "\n".join(sorted([n for n in entry_names if n])),
                    "data_entry_ids": "\n".join(sorted(entry_ids)),
                    "subgroup_dataset_count": len(dataset_ids_by_group.get(subgroup_id, [])),
                    "subgroup_name": subgroup_name,
                    "subgroup_id": subgroup_id,
                    "subgroup_description": subgroup_desc,
                    "grant_numbers": grant_numbers_for_row,
                    "missing_sample": False,
                }
            )

    return columns, rows, missing_sample_files


def build_sample_listing2_rows_from_files(
    subgroup_ids: Optional[Iterable[str]] = None,
) -> Tuple[List[SampleDedupColumn], List[Dict[str, Any]], List[str]]:
    """Build rows for the alternative listing mode (一覧2).

    Rows are sample-centric and include the list of referencing tiles/datasets.
    """

    subgroup_name_by_id, subgroup_grants_by_id, _subgroup_desc_by_id = _build_subgroup_maps()
    dataset_name_by_id, _dataset_ids_by_group = _build_dataset_maps()
    dataset_grants_by_id = _build_dataset_grants_map()
    usage_details = _build_sample_usage_details(dataset_name_by_id.keys(), dataset_name_by_id=dataset_name_by_id)

    wanted_subgroup_ids: Optional[Set[str]] = None
    if subgroup_ids is not None:
        wanted_subgroup_ids = {str(x).strip() for x in subgroup_ids if str(x).strip()}

    columns = get_default_columns_list2()
    rows: List[Dict[str, Any]] = []
    missing_sample_files: List[str] = []

    for subgroup_id, subgroup_name in subgroup_name_by_id.items():
        if wanted_subgroup_ids is not None and subgroup_id not in wanted_subgroup_ids:
            continue

        subgroup_grant_numbers = subgroup_grants_by_id.get(subgroup_id, "")
        subgroup_grant_list = [x.strip() for x in str(subgroup_grant_numbers).splitlines() if x.strip()]

        payload = _load_sample_payload(subgroup_id)
        if payload is None:
            missing_sample_files.append(subgroup_id)
            rows.append(
                {
                    "subgroup_name": subgroup_name,
                    "subgroup_id": subgroup_id,
                    "sample_name": "",
                    "sample_id": "",
                    "tile_dataset_grant": "",
                    "tile_dataset_grant_links": [],
                    "data_entry_count": 0,
                    "dataset_count": 0,
                    "grant_numbers": subgroup_grant_numbers,
                    "grant_count": len({x for x in subgroup_grant_list if x}),
                    "dataset_ids": "",
                    "data_entry_ids": "",
                    "missing_sample": True,
                }
            )
            continue

        data_items = payload.get("data") if isinstance(payload.get("data"), list) else []
        if not data_items:
            continue

        for item in data_items:
            if not isinstance(item, dict):
                continue
            sample_id = _safe_str(item.get("id")).strip()
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            names = _safe_list(attrs.get("names")) if attrs else []
            names = [str(x) for x in names if _safe_str(x).strip()]
            sample_name = names[0] if names else ""

            details = usage_details.get(sample_id, []) if sample_id else []
            if not isinstance(details, list):
                details = []

            # Build per-tile lines; keep a set for counts.
            seen_entry_ids: set[str] = set()
            norm_details: List[Dict[str, str]] = []
            dataset_ids_set: set[str] = set()
            entry_ids_set: set[str] = set()
            grant_set: set[str] = set()

            for d in details:
                if not isinstance(d, dict):
                    continue
                entry_id = _safe_str(d.get("data_entry_id")).strip()
                dataset_id = _safe_str(d.get("dataset_id")).strip()
                if entry_id and entry_id in seen_entry_ids:
                    continue
                if entry_id:
                    seen_entry_ids.add(entry_id)
                    entry_ids_set.add(entry_id)
                if dataset_id:
                    dataset_ids_set.add(dataset_id)
                norm_details.append(
                    {
                        "data_entry_id": entry_id,
                        "data_entry_name": _safe_str(d.get("data_entry_name")).strip(),
                        "dataset_id": dataset_id,
                        "dataset_name": _safe_str(d.get("dataset_name")).strip(),
                    }
                )

            lines: List[str] = []
            links: List[Dict[str, str]] = []
            tile_ids_lines: List[str] = []
            dataset_ids_lines: List[str] = []
            for d in norm_details:
                tile_name = d.get("data_entry_name", "")
                dataset_name = d.get("dataset_name", "")
                tile_id = d.get("data_entry_id", "")
                dataset_id = d.get("dataset_id", "")

                tile_url = ""
                if tile_id:
                    tile_url = URLS["web"].get("data_detail_page", "https://rde.nims.go.jp/rde/datasets/data/{id}").format(id=tile_id)
                dataset_url = ""
                if dataset_id:
                    dataset_url = URLS["web"].get("dataset_page", "https://rde.nims.go.jp/rde/datasets/{id}").format(id=dataset_id)

                # Grants belong to dataset (tile -> dataset -> grant). Fall back to subgroup grants if dataset grants are missing.
                grants = dataset_grants_by_id.get(dataset_id, []) if dataset_id else []
                if not grants:
                    grants = subgroup_grant_list
                grants = [x for x in grants if _safe_str(x).strip()]
                for g in grants:
                    grant_set.add(str(g).strip())
                grant_display = " / ".join([str(x).strip() for x in grants if str(x).strip()])

                if grant_display:
                    lines.append(f"{tile_name} - {dataset_name} - {grant_display}")
                else:
                    lines.append(f"{tile_name} - {dataset_name}")
                links.append(
                    {
                        "tile_url": tile_url,
                        "dataset_url": dataset_url,
                        "data_entry_id": tile_id,
                        "dataset_id": dataset_id,
                    }
                )
                tile_ids_lines.append(tile_id)
                dataset_ids_lines.append(dataset_id)

            grant_numbers = "\n".join(sorted({x for x in grant_set if x}))
            grant_count = len({x for x in grant_set if x})

            rows.append(
                {
                    "subgroup_name": subgroup_name,
                    "subgroup_id": subgroup_id,
                    "sample_name": sample_name,
                    "sample_id": sample_id,
                    "tile_dataset_grant": "\n".join([x for x in lines if x]),
                    "tile_dataset_grant_links": links,
                    "data_entry_count": len(entry_ids_set),
                    "dataset_count": len(dataset_ids_set),
                    "grant_numbers": grant_numbers,
                    "grant_count": grant_count,
                    "dataset_ids": "\n".join([x for x in dataset_ids_lines if x]),
                    "data_entry_ids": "\n".join([x for x in tile_ids_lines if x]),
                    "missing_sample": False,
                }
            )

    return columns, rows, missing_sample_files


def fetch_samples_for_subgroups(subgroup_ids: Iterable[str], timeout: int = 10) -> str:
    ids = [str(x).strip() for x in subgroup_ids if str(x).strip()]
    if not ids:
        return "対象の試料IDがありません"

    samples_dir = get_dynamic_file_path("output/rde/data/samples")
    try:
        os.makedirs(samples_dir, exist_ok=True)
    except Exception as e:
        msg = f"samplesディレクトリ作成に失敗しました: {e}"
        logger.error(msg)
        return msg

    succeeded = 0
    failed = 0

    for subgroup_id in ids:
        url = (
            "https://rde-material-api.nims.go.jp/samples"
            f"?groupId={subgroup_id}"
            "&page%5Blimit%5D=1000&page%5Boffset%5D=0"
            "&fields%5Bsample%5D=names%2Cdescription%2Ccomposition%2Ctags%2CreferenceUrl"
        )
        headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Host": "rde-material-api.nims.go.jp",
            "Origin": "https://rde-entry-arim.nims.go.jp",
            "Referer": "https://rde-entry-arim.nims.go.jp/",
        }

        try:
            resp = proxy_get(url, headers=headers, timeout=timeout)
            if resp is None:
                failed += 1
                logger.error("試料情報(%s)の取得に失敗: リクエストエラー", subgroup_id)
                continue
            resp.raise_for_status()
            data = resp.json()
            out_path = os.path.join(samples_dir, f"{subgroup_id}.json")
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            succeeded += 1
        except Exception as e:
            failed += 1
            logger.error("試料情報(%s)の取得失敗: %s", subgroup_id, e)

    return f"試料情報取得完了: 成功={succeeded}件, 失敗={failed}件, 総数={len(ids)}件"
