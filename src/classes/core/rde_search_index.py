from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from config.common import get_dynamic_file_path, ensure_directory_exists


INDEX_VERSION = 1
QUERY_CACHE_MAX_ENTRIES = 3000

_INDEX_MEMORY_CACHE: dict[str, Any] | None = None
_INDEX_MEMORY_PATH: str = ""
_INDEX_MEMORY_MTIME: float = -1.0
_QUERY_CACHE_LOADED = False
_QUERY_CACHE_PAYLOAD: dict[str, Any] = {"signature": "", "entries": {}}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_data_items(path: str) -> list[dict]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def _get_sources() -> dict[str, str]:
    return {
        "dataset": get_dynamic_file_path("output/rde/data/dataset.json"),
        "template": get_dynamic_file_path("output/rde/data/template.json"),
        "instrument": get_dynamic_file_path("output/rde/data/instruments.json"),
        "subgroup": get_dynamic_file_path("output/rde/data/subGroup.json"),
    }


def get_index_path() -> str:
    return get_dynamic_file_path("output/rde/data/search_index/rde_search_index.json")


def get_query_cache_path() -> str:
    return get_dynamic_file_path("output/rde/data/search_index/rde_search_query_cache.json")


def _source_signature_from_meta(meta: dict[str, Any]) -> str:
    source_mtimes = meta.get("source_mtimes") if isinstance(meta.get("source_mtimes"), dict) else {}
    return json.dumps(
        {
            "version": int(meta.get("version") or 0),
            "dataset_count": int(meta.get("dataset_count") or 0),
            "source_mtimes": {k: float(v or 0.0) for k, v in sorted(source_mtimes.items())},
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _index_signature(index_payload: dict[str, Any]) -> str:
    meta = index_payload.get("meta") if isinstance(index_payload.get("meta"), dict) else {}
    return _source_signature_from_meta(meta)


def _criteria_cache_key(criteria: dict[str, str]) -> str:
    normalized: list[tuple[str, str]] = []
    for field, value in sorted(criteria.items(), key=lambda x: str(x[0])):
        key = _safe_str(field)
        token = _safe_str(value)
        if not key or not token:
            continue
        normalized.append((key, token.casefold()))
    if not normalized:
        return ""
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _load_query_cache_payload() -> dict[str, Any]:
    global _QUERY_CACHE_LOADED, _QUERY_CACHE_PAYLOAD
    if _QUERY_CACHE_LOADED:
        return _QUERY_CACHE_PAYLOAD

    payload = _load_json(get_query_cache_path())
    if isinstance(payload, dict):
        signature = _safe_str(payload.get("signature"))
        entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else {}
        normalized_entries: dict[str, list[str]] = {}
        for key, ids in entries.items():
            if not isinstance(ids, list):
                continue
            normalized_ids = sorted(set([_safe_str(x) for x in ids if _safe_str(x)]))
            normalized_entries[_safe_str(key)] = normalized_ids
        _QUERY_CACHE_PAYLOAD = {"signature": signature, "entries": normalized_entries}
    else:
        _QUERY_CACHE_PAYLOAD = {"signature": "", "entries": {}}

    _QUERY_CACHE_LOADED = True
    return _QUERY_CACHE_PAYLOAD


def _save_query_cache_payload(payload: dict[str, Any]) -> None:
    global _QUERY_CACHE_LOADED, _QUERY_CACHE_PAYLOAD
    path = get_query_cache_path()
    ensure_directory_exists(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    _QUERY_CACHE_PAYLOAD = payload
    _QUERY_CACHE_LOADED = True


def _clear_query_cache_for_index(index_payload: dict[str, Any]) -> None:
    signature = _index_signature(index_payload)
    _save_query_cache_payload({"signature": signature, "entries": {}})


def _query_cache_lookup(index_payload: dict[str, Any], criteria: dict[str, str]) -> set[str] | None:
    cache_key = _criteria_cache_key(criteria)
    if not cache_key:
        return None

    payload = _load_query_cache_payload()
    if _safe_str(payload.get("signature")) != _index_signature(index_payload):
        return None

    raw_entries = payload.get("entries")
    entries: dict[str, list[str]] = raw_entries if isinstance(raw_entries, dict) else {}
    ids = entries.get(cache_key)
    if isinstance(ids, list):
        return set([_safe_str(x) for x in ids if _safe_str(x)])
    return None


def _query_cache_store(index_payload: dict[str, Any], criteria: dict[str, str], result: set[str]) -> None:
    cache_key = _criteria_cache_key(criteria)
    if not cache_key:
        return

    payload = _load_query_cache_payload()
    signature = _index_signature(index_payload)
    if _safe_str(payload.get("signature")) != signature:
        payload = {"signature": signature, "entries": {}}

    raw_entries = payload.get("entries")
    entries: dict[str, list[str]] = raw_entries if isinstance(raw_entries, dict) else {}
    result_ids = sorted(set([_safe_str(x) for x in result if _safe_str(x)]))
    if entries.get(cache_key) == result_ids:
        return

    entries[cache_key] = result_ids
    while len(entries) > QUERY_CACHE_MAX_ENTRIES:
        oldest_key = next(iter(entries.keys()), None)
        if not oldest_key:
            break
        entries.pop(oldest_key, None)

    payload = {"signature": signature, "entries": entries}
    _save_query_cache_payload(payload)


def _source_mtimes(sources: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, path in sources.items():
        try:
            out[key] = os.path.getmtime(path) if path and os.path.exists(path) else 0.0
        except Exception:
            out[key] = 0.0
    return out


def _build_template_to_instrument_ids(template_items: list[dict]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in template_items:
        template_id = _safe_str(item.get("id"))
        if not template_id:
            continue
        rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
        instruments_data = (rels.get("instruments") or {}).get("data") if isinstance(rels, dict) else []
        inst_ids: list[str] = []
        for inst in _safe_list(instruments_data):
            if not isinstance(inst, dict):
                continue
            inst_id = _safe_str(inst.get("id"))
            if inst_id:
                inst_ids.append(inst_id)
        result[template_id] = sorted(set(inst_ids))
    return result


def _build_instrument_maps(instrument_items: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    instrument_name_by_id: dict[str, str] = {}
    local_id_to_name: dict[str, str] = {}

    for item in instrument_items:
        instrument_id = _safe_str(item.get("id"))
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        name = _safe_str(attrs.get("nameJa") or attrs.get("nameEn"))
        if instrument_id and name:
            instrument_name_by_id[instrument_id] = name

        raw_programs = attrs.get("programs")
        programs: list[Any] = raw_programs if isinstance(raw_programs, list) else []
        for program in programs:
            if not isinstance(program, dict):
                continue
            local_id = _safe_str(program.get("localId"))
            if not local_id:
                continue
            if local_id not in local_id_to_name or not local_id_to_name[local_id]:
                local_id_to_name[local_id] = name

    return instrument_name_by_id, local_id_to_name


def _build_subgroup_name_by_id(subgroup_payload: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    items: list[dict] = []
    if isinstance(subgroup_payload, dict):
        included = subgroup_payload.get("included")
        data = subgroup_payload.get("data")
        if isinstance(included, list):
            items.extend([x for x in included if isinstance(x, dict)])
        if isinstance(data, list):
            items.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict):
            items.append(data)
    elif isinstance(subgroup_payload, list):
        items.extend([x for x in subgroup_payload if isinstance(x, dict)])

    for item in items:
        if item.get("type") != "group":
            continue
        group_id = _safe_str(item.get("id"))
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        if attrs.get("groupType") != "TEAM":
            continue
        if not group_id:
            continue
        name = _safe_str(attrs.get("name"))
        desc = _safe_str(attrs.get("description"))
        result[group_id] = " | ".join([x for x in [name, desc] if x]) or group_id
    return result


def _add_reverse(reverse_map: dict[str, dict[str, list[str]]], field: str, key: str, dataset_id: str):
    normalized = _safe_str(key)
    if not normalized:
        return
    bucket = reverse_map.setdefault(field, {}).setdefault(normalized, [])
    if dataset_id not in bucket:
        bucket.append(dataset_id)


def rebuild_rde_search_index() -> dict[str, Any]:
    sources = _get_sources()
    mtimes = _source_mtimes(sources)

    dataset_items = _load_data_items(sources["dataset"])
    template_items = _load_data_items(sources["template"])
    instrument_items = _load_data_items(sources["instrument"])
    subgroup_payload = _load_json(sources["subgroup"])

    template_to_instrument_ids = _build_template_to_instrument_ids(template_items)
    instrument_name_by_id, local_id_to_name = _build_instrument_maps(instrument_items)
    subgroup_name_by_id = _build_subgroup_name_by_id(subgroup_payload)

    datasets: dict[str, dict[str, Any]] = {}
    reverse: dict[str, dict[str, list[str]]] = {}

    for dataset in dataset_items:
        dataset_id = _safe_str(dataset.get("id"))
        if not dataset_id:
            continue

        attrs = dataset.get("attributes") if isinstance(dataset.get("attributes"), dict) else {}
        rels = dataset.get("relationships") if isinstance(dataset.get("relationships"), dict) else {}

        grant = _safe_str(attrs.get("grantNumber"))
        dataset_name = _safe_str(attrs.get("name"))

        group_data = (rels.get("group") or {}).get("data") if isinstance(rels, dict) else {}
        subgroup_id = _safe_str((group_data or {}).get("id") if isinstance(group_data, dict) else "") or _safe_str(attrs.get("groupId"))
        subgroup_name = subgroup_name_by_id.get(subgroup_id, "")

        template_data = (rels.get("template") or {}).get("data") if isinstance(rels, dict) else {}
        template_id = _safe_str((template_data or {}).get("id") if isinstance(template_data, dict) else "") or _safe_str(attrs.get("templateId"))

        related_data = (rels.get("relatedDatasets") or {}).get("data") if isinstance(rels, dict) else []
        related_ids: list[str] = []
        for item in _safe_list(related_data):
            if isinstance(item, dict):
                rid = _safe_str(item.get("id"))
                if rid:
                    related_ids.append(rid)

        instrument_ids = template_to_instrument_ids.get(template_id, [])
        equipment_names: list[str] = []
        equipment_local_ids: list[str] = []

        for instrument_id in instrument_ids:
            name = instrument_name_by_id.get(instrument_id, "")
            if name:
                equipment_names.append(name)

        for local_id, local_name in local_id_to_name.items():
            if local_name and local_name in equipment_names:
                equipment_local_ids.append(local_id)

        equipment_names = sorted(set([_safe_str(x) for x in equipment_names if _safe_str(x)]))
        equipment_local_ids = sorted(set([_safe_str(x) for x in equipment_local_ids if _safe_str(x)]))
        related_ids = sorted(set([_safe_str(x) for x in related_ids if _safe_str(x)]))

        datasets[dataset_id] = {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "grant_number": grant,
            "subgroup_id": subgroup_id,
            "subgroup_name": subgroup_name,
            "template_id": template_id,
            "related_dataset_ids": related_ids,
            "instrument_ids": instrument_ids,
            "equipment_names": equipment_names,
            "equipment_local_ids": equipment_local_ids,
        }

        _add_reverse(reverse, "dataset_id", dataset_id, dataset_id)
        _add_reverse(reverse, "dataset_name", dataset_name, dataset_id)
        _add_reverse(reverse, "grant_number", grant, dataset_id)
        _add_reverse(reverse, "subgroup_id", subgroup_id, dataset_id)
        _add_reverse(reverse, "subgroup_name", subgroup_name, dataset_id)
        _add_reverse(reverse, "template_id", template_id, dataset_id)
        for rid in related_ids:
            _add_reverse(reverse, "related_dataset_id", rid, dataset_id)
        for ename in equipment_names:
            _add_reverse(reverse, "equipment_name", ename, dataset_id)
        for local_id in equipment_local_ids:
            _add_reverse(reverse, "equipment_local_id", local_id, dataset_id)

    for field_map in reverse.values():
        for key, ids in list(field_map.items()):
            field_map[key] = sorted(set(ids))

    index_payload: dict[str, Any] = {
        "meta": {
            "version": INDEX_VERSION,
            "generated_at": _now_iso(),
            "source_mtimes": mtimes,
            "dataset_count": len(datasets),
        },
        "datasets": datasets,
        "reverse": reverse,
    }

    index_path = get_index_path()
    ensure_directory_exists(os.path.dirname(index_path))
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_payload, f, ensure_ascii=False, indent=2)

    global _INDEX_MEMORY_CACHE, _INDEX_MEMORY_PATH, _INDEX_MEMORY_MTIME
    _INDEX_MEMORY_CACHE = index_payload
    _INDEX_MEMORY_PATH = index_path
    try:
        _INDEX_MEMORY_MTIME = os.path.getmtime(index_path)
    except Exception:
        _INDEX_MEMORY_MTIME = -1.0

    _clear_query_cache_for_index(index_payload)

    return index_payload


def load_rde_search_index() -> dict[str, Any] | None:
    global _INDEX_MEMORY_CACHE, _INDEX_MEMORY_PATH, _INDEX_MEMORY_MTIME
    index_path = get_index_path()
    try:
        current_mtime = os.path.getmtime(index_path) if index_path and os.path.exists(index_path) else -1.0
    except Exception:
        current_mtime = -1.0

    if (
        _INDEX_MEMORY_CACHE is not None
        and _INDEX_MEMORY_PATH == index_path
        and abs(_INDEX_MEMORY_MTIME - current_mtime) <= 0.0001
    ):
        return _INDEX_MEMORY_CACHE

    payload = _load_json(index_path)
    if isinstance(payload, dict):
        _INDEX_MEMORY_CACHE = payload
        _INDEX_MEMORY_PATH = index_path
        _INDEX_MEMORY_MTIME = current_mtime
        return payload
    return None


def _is_index_stale(index_payload: dict[str, Any]) -> bool:
    meta = index_payload.get("meta") if isinstance(index_payload.get("meta"), dict) else {}
    saved_mtimes = meta.get("source_mtimes") if isinstance(meta.get("source_mtimes"), dict) else {}
    current_mtimes = _source_mtimes(_get_sources())

    for key, current in current_mtimes.items():
        saved = float(saved_mtimes.get(key) or 0.0)
        if abs(saved - current) > 0.0001:
            return True
    return False


def ensure_rde_search_index(force_rebuild: bool = False) -> dict[str, Any]:
    current = load_rde_search_index()
    if force_rebuild or current is None or _is_index_stale(current):
        return rebuild_rde_search_index()
    return current


def search_dataset_ids(index_payload: dict[str, Any], criteria: dict[str, str]) -> set[str] | None:
    cached = _query_cache_lookup(index_payload, criteria)
    if cached is not None:
        return cached

    reverse = index_payload.get("reverse") if isinstance(index_payload.get("reverse"), dict) else {}
    if not isinstance(reverse, dict):
        return None

    result: set[str] | None = None
    for field, value in criteria.items():
        token = _safe_str(value)
        if not token:
            continue

        field_map = reverse.get(field)
        if not isinstance(field_map, dict):
            continue

        token_cf = token.casefold()
        matched_ids: set[str] = set()
        for key, ids in field_map.items():
            key_cf = _safe_str(key).casefold()
            if token_cf and token_cf in key_cf:
                if isinstance(ids, list):
                    matched_ids.update([_safe_str(x) for x in ids if _safe_str(x)])

        if result is None:
            result = matched_ids
        else:
            result &= matched_ids

        if result is not None and not result:
            result = set()
            _query_cache_store(index_payload, criteria, result)
            return result

    if result is not None:
        _query_cache_store(index_payload, criteria, result)
    return result


def get_index_overview(index_payload: dict[str, Any]) -> dict[str, Any]:
    meta = index_payload.get("meta") if isinstance(index_payload.get("meta"), dict) else {}
    reverse = index_payload.get("reverse") if isinstance(index_payload.get("reverse"), dict) else {}

    reverse_counts: dict[str, int] = {}
    for key, value in reverse.items():
        if isinstance(value, dict):
            reverse_counts[key] = len(value)

    return {
        "version": int(meta.get("version") or 0),
        "generated_at": _safe_str(meta.get("generated_at")),
        "dataset_count": int(meta.get("dataset_count") or 0),
        "reverse_counts": reverse_counts,
    }
