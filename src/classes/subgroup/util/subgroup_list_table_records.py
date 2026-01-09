"""Build table records for subgroup listing tab.

This module loads output/rde/data/subGroup.json and converts it into
(columns, rows) suitable for the subgroup listing UI.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from config.common import get_dynamic_file_path, get_samples_dir_path
from classes.subgroup.util.related_dataset_fetcher import RelatedDatasetFetcher

LOGGER = logging.getLogger(__name__)


_SUBGROUP_LIST_CACHE: Dict[str, Any] = {
    "signature": None,
    "columns": None,
    "rows": None,
    "created_at": 0.0,
}


_DETAIL_USER_ATTR_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


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


def _persisted_cache_path() -> str:
    # NOTE: Must be CWD-independent. Use get_dynamic_file_path.
    return get_dynamic_file_path("output/rde/cache/subgroup_listing_cache.json")


def _safe_stat_signature(path: str) -> Tuple[float, int]:
    try:
        if not path or not os.path.exists(path):
            return 0.0, 0
        return float(os.path.getmtime(path)), int(os.path.getsize(path))
    except Exception:
        return 0.0, 0


def _safe_dir_mtime(path: str) -> float:
    try:
        if not path or not os.path.exists(path):
            return 0.0
        return float(os.path.getmtime(path))
    except Exception:
        return 0.0


def _compute_signature(
    *,
    subgroup_json_path: str,
    dataset_json_path: str,
    samples_dir: str,
    subgroup_details_dir: str,
    subgroup_rel_details_dir: str,
) -> Dict[str, Any]:
    # Keep JSON-stable primitives only.
    subgroup_sig = _safe_stat_signature(subgroup_json_path)
    dataset_sig = _safe_stat_signature(dataset_json_path)
    samples_mtime = _safe_dir_mtime(samples_dir)
    details_mtime = _safe_dir_mtime(subgroup_details_dir)
    rel_details_mtime = _safe_dir_mtime(subgroup_rel_details_dir)
    return {
        "subGroup.json": [subgroup_sig[0], subgroup_sig[1]],
        "dataset.json": [dataset_sig[0], dataset_sig[1]],
        "samples_dir_mtime": samples_mtime,
        "subgroup_details_dir_mtime": details_mtime,
        "subgroup_rel_details_dir_mtime": rel_details_mtime,
        "schema": 2,
    }


def _load_detail_user_attributes_for_subgroup(subgroup_id: str) -> Dict[str, Dict[str, Any]]:
    """サブグループ詳細ファイルから user_id -> attributes を読む（キャッシュ付き）。

    一覧タブのメンバー表示は、修正タブ同様「ユーザー名」を最優先で表示する。
    subGroup.json だけでは userName が欠落するケースがあり、ここを参照しないと
    メンバーIDが直接表示される不具合が再発しやすい。
    """

    sgid = _safe_str(subgroup_id).strip()
    if not sgid:
        return {}

    cached = _DETAIL_USER_ATTR_CACHE.get(sgid)
    if isinstance(cached, dict):
        return cached

    attr_map: Dict[str, Dict[str, Any]] = {}
    try:
        # NOTE: Must be CWD-independent. Use get_dynamic_file_path.
        candidate_paths = [
            get_dynamic_file_path(f"output/rde/data/subGroups/{sgid}.json"),
            get_dynamic_file_path(f"output/rde/data/subGroupsAncestors/{sgid}.json"),
            # legacy dir (互換)
            get_dynamic_file_path(f"output/rde/data/subgroups/{sgid}.json"),
        ]
        for path in candidate_paths:
            if not path or not os.path.exists(path):
                continue
            data = _load_json_file(path)
            included = data.get("included", []) if isinstance(data, dict) else []
            if not isinstance(included, list):
                continue
            for item in included:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "user":
                    continue
                uid = _safe_str(item.get("id")).strip()
                attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
                if uid:
                    attr_map[uid] = attrs or {}
            if attr_map:
                break
    except Exception:
        attr_map = {}

    _DETAIL_USER_ATTR_CACHE[sgid] = attr_map
    return attr_map


def _serialize_columns(columns: List["SubgroupListColumn"]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for col in columns or []:
        try:
            out.append({"key": col.key, "label": col.label, "default_visible": bool(col.default_visible)})
        except Exception:
            continue
    return out


def _deserialize_columns(payload: Any) -> List["SubgroupListColumn"]:
    if not isinstance(payload, list):
        return []
    cols: List[SubgroupListColumn] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = _safe_str(item.get("key")).strip()
        label = _safe_str(item.get("label")).strip()
        if not key or not label:
            continue
        cols.append(SubgroupListColumn(key=key, label=label, default_visible=bool(item.get("default_visible", True))))
    return cols


def _load_persisted_cache(signature: Dict[str, Any]) -> Tuple[List["SubgroupListColumn"], List[Dict[str, Any]]] | None:
    path = _persisted_cache_path()
    if not path:
        return None
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return None
        if payload.get("signature") != signature:
            return None
        cols = _deserialize_columns(payload.get("columns"))
        rows = payload.get("rows")
        if not cols or not isinstance(rows, list):
            return None
        cleaned_rows: List[Dict[str, Any]] = [r for r in rows if isinstance(r, dict)]
        return cols, cleaned_rows
    except Exception:
        return None


def _save_persisted_cache(signature: Dict[str, Any], columns: List["SubgroupListColumn"], rows: List[Dict[str, Any]]) -> None:
    path = _persisted_cache_path()
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "signature": signature,
            "created_at": time.time(),
            "columns": _serialize_columns(columns),
            "rows": rows,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    except Exception:
        return


def clear_subgroup_list_cache() -> None:
    """Clear the in-memory cache used by build_subgroup_list_rows_from_files()."""

    _SUBGROUP_LIST_CACHE["signature"] = None
    _SUBGROUP_LIST_CACHE["columns"] = None
    _SUBGROUP_LIST_CACHE["rows"] = None
    _SUBGROUP_LIST_CACHE["created_at"] = 0.0


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
    dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
    try:
        samples_dir = get_samples_dir_path()
    except Exception:
        samples_dir = ""

    subgroup_details_dir = get_dynamic_file_path("output/rde/data/subGroups")
    subgroup_rel_details_dir = get_dynamic_file_path("output/rde/data/subGroupsAncestors")

    signature = _compute_signature(
        subgroup_json_path=subgroup_json_path,
        dataset_json_path=dataset_json_path,
        samples_dir=samples_dir,
        subgroup_details_dir=subgroup_details_dir,
        subgroup_rel_details_dir=subgroup_rel_details_dir,
    )

    if (
        _SUBGROUP_LIST_CACHE.get("signature") == signature
        and _SUBGROUP_LIST_CACHE.get("columns") is not None
        and _SUBGROUP_LIST_CACHE.get("rows") is not None
    ):
        return _SUBGROUP_LIST_CACHE["columns"], _SUBGROUP_LIST_CACHE["rows"]

    persisted = _load_persisted_cache(signature)
    if persisted is not None:
        cols, rows = persisted
        _SUBGROUP_LIST_CACHE["signature"] = signature
        _SUBGROUP_LIST_CACHE["columns"] = cols
        _SUBGROUP_LIST_CACHE["rows"] = rows
        _SUBGROUP_LIST_CACHE["created_at"] = time.time()
        return cols, rows

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

    # NOTE: 一覧タブでは修正タブ向けの重い統合メンバー解決（load_unified_member_list）を使わない。
    # subGroup.jsonのincludedユーザー＋ユーザーキャッシュでの軽量解決に留め、
    # 初回表示の体感（スピナーが消えない）を防ぐ。

    # Related datasets via dataset.json (same logic as edit tab)
    related_dataset_fetcher = RelatedDatasetFetcher(dataset_json_path=dataset_json_path)

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

        # Resolve member names:
        # - 修正タブのメンバーテーブルは「詳細ファイル included.user.userName」を優先する。
        # - 一覧タブも同様にしないと、subGroup.json 側に userName が無いケースで
        #   メンバーIDが直接表示される不具合が再発する。
        # - そのため、ここでは「詳細ファイル -> subGroup.json included -> ユーザーキャッシュ」の順で解決する。
        #   （※ resolved できない場合でも、IDをUIに表示しない）
        member_names: List[str] = []
        detail_attr_map = _load_detail_user_attributes_for_subgroup(subgroup_id)
        for mid in member_ids:
            if not mid:
                continue
            resolved = ""
            try:
                detail = detail_attr_map.get(mid) if isinstance(detail_attr_map, dict) else {}
                if isinstance(detail, dict):
                    resolved = _safe_str(detail.get("userName") or "").strip()
            except Exception:
                resolved = ""
            try:
                info = user_map.get(mid) or {}
                if not resolved:
                    resolved = _safe_str(info.get("userName") if isinstance(info, dict) else "").strip()
            except Exception:
                resolved = ""
            if (not resolved or resolved in {"Unknown", "Unknown User"}) and get_cached_user is not None:
                try:
                    cached = get_cached_user(mid)
                    if isinstance(cached, dict):
                        resolved = _safe_str(cached.get("userName") or "").strip() or resolved
                except Exception:
                    pass

            # 再発防止: UIに member_id を直接出さない。
            # どうしても解決できない場合は "Unknown" とする（IDの露出は不可）。
            member_names.append(resolved or "Unknown")

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

    try:
        _save_persisted_cache(signature, columns, rows)
    except Exception:
        pass
    _SUBGROUP_LIST_CACHE["signature"] = signature
    _SUBGROUP_LIST_CACHE["columns"] = columns
    _SUBGROUP_LIST_CACHE["rows"] = rows
    _SUBGROUP_LIST_CACHE["created_at"] = time.time()

    return columns, rows
