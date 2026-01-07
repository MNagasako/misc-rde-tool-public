"""Dataset list table records for DatasetTabWidget '一覧' tab.

This module is intentionally UI-agnostic:
- Loads dataset.json and related reference JSON files (best-effort)
- Flattens dataset items into rows with Japanese column labels aligned to the
  dataset edit form labels where practical.
- Resolves related IDs to human-readable names when possible.

All file paths should be obtained via config.common.get_dynamic_file_path.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import os

from classes.dataset.util.data_entry_summary import compute_summary_from_payload, format_size_with_bytes

from config.common import get_dynamic_file_path


@dataclass(frozen=True)
class DatasetListColumn:
    key: str
    label: str
    default_visible: bool = True


def _load_json_file(path: str) -> Any:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _coerce_data_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        data = payload.get("data") or []
        return [d for d in data if isinstance(d, dict)]
    if isinstance(payload, list):
        return [d for d in payload if isinstance(d, dict)]
    return []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _extract_rel_id(dataset_item: Dict[str, Any], rel_key: str) -> str:
    rels = dataset_item.get("relationships") if isinstance(dataset_item.get("relationships"), dict) else {}
    rel = rels.get(rel_key) if isinstance(rels.get(rel_key), dict) else {}
    data = rel.get("data")
    if isinstance(data, dict):
        return _safe_str(data.get("id")).strip()
    return ""


def _extract_rel_ids(dataset_item: Dict[str, Any], rel_key: str) -> List[str]:
    rels = dataset_item.get("relationships") if isinstance(dataset_item.get("relationships"), dict) else {}
    rel = rels.get(rel_key) if isinstance(rels.get(rel_key), dict) else {}
    data = rel.get("data")
    if isinstance(data, list):
        ids: List[str] = []
        for d in data:
            if isinstance(d, dict) and d.get("id"):
                ids.append(_safe_str(d.get("id")).strip())
        return [i for i in ids if i]
    if isinstance(data, dict) and data.get("id"):
        return [_safe_str(data.get("id")).strip()]
    return []


def _parse_iso_date(date_text: str) -> Optional[datetime.date]:
    text = (date_text or "").strip()
    if not text:
        return None

    # dataset_edit_widget expects strings like "2026-03-31T03:00:00.000Z".
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text:
        text = text.split(" ", 1)[0]

    try:
        y, m, d = map(int, text.split("-"))
        return datetime.date(y, m, d)
    except Exception:
        return None


def _format_related_links(links: Any) -> str:
    if not isinstance(links, list):
        return ""
    parts: List[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        title = _safe_str(link.get("title")).strip()
        url = _safe_str(link.get("url")).strip()
        if title and url:
            parts.append(f"{title}:{url}")
    return ",".join(parts)


def _format_user_label(user_name: str, organization_name: str) -> str:
    name = (user_name or "").strip()
    org = (organization_name or "").strip()
    if name and org:
        return f"{name} ({org})"
    return name or org


def _build_user_name_map_from_info_json(info_payload: Any) -> Dict[str, str]:
    # Re-implement a tiny subset of classes.dataset.util.dataset_listing_records
    # to keep this module self-contained.
    records: List[Dict[str, Any]] = []
    if isinstance(info_payload, dict) and isinstance(info_payload.get("data"), list):
        records = [r for r in (info_payload.get("data") or []) if isinstance(r, dict)]
    elif isinstance(info_payload, list):
        records = [r for r in info_payload if isinstance(r, dict)]
    elif isinstance(info_payload, dict):
        # dict keyed by id
        result: Dict[str, str] = {}
        for k, v in info_payload.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            name = _safe_str(v.get("userName") or v.get("name")).strip()
            if name:
                result[k] = name
        return result

    result: Dict[str, str] = {}
    for rec in records:
        user_id = _safe_str(rec.get("id")).strip()
        attrs = rec.get("attributes") if isinstance(rec.get("attributes"), dict) else {}
        user_name = _safe_str(attrs.get("userName") or attrs.get("name")).strip() if isinstance(attrs, dict) else ""
        org_name = _safe_str(attrs.get("organizationName") or "").strip() if isinstance(attrs, dict) else ""
        label = _format_user_label(user_name, org_name)
        if user_id and label:
            result[user_id] = label
    return result


def _iter_included_users(payload: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    included = payload.get("included")
    if not isinstance(included, list):
        return []
    users: List[Dict[str, Any]] = []
    for inc in included:
        if not isinstance(inc, dict):
            continue
        if _safe_str(inc.get("type")).strip() != "user":
            continue
        users.append(inc)
    return users


def _build_user_label_map_from_included_users(payload: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for user in _iter_included_users(payload):
        user_id = _safe_str(user.get("id")).strip()
        attrs = user.get("attributes") if isinstance(user.get("attributes"), dict) else {}
        if not user_id or not isinstance(attrs, dict):
            continue
        user_name = _safe_str(attrs.get("userName") or attrs.get("name") or "").strip()
        org_name = _safe_str(attrs.get("organizationName") or "").strip()
        label = _format_user_label(user_name, org_name)
        if label:
            result[user_id] = label
    return result


def _build_user_label_map_best_effort(info_payload: Any, subgroup_payload: Any, subgroups_dir: str) -> Dict[str, str]:
    # Priority: included user objects (have org) > info.json > fallback empty
    label_by_id: Dict[str, str] = {}

    try:
        label_by_id.update(_build_user_name_map_from_info_json(info_payload))
    except Exception:
        pass

    try:
        label_by_id.update(_build_user_label_map_from_included_users(subgroup_payload))
    except Exception:
        pass

    # subGroups/*.json often contain included users with org/name.
    try:
        if subgroups_dir and os.path.isdir(subgroups_dir):
            for name in os.listdir(subgroups_dir):
                if not name.lower().endswith(".json"):
                    continue
                p = os.path.join(subgroups_dir, name)
                payload = _load_json_file(p)
                if payload is None:
                    continue
                label_by_id.update(_build_user_label_map_from_included_users(payload))
    except Exception:
        pass

    return label_by_id


def _load_dataset_detail_user_label_map(dataset_id: str) -> Dict[str, str]:
    dsid = _safe_str(dataset_id).strip()
    if not dsid:
        return {}
    # dataset.json はダイジェストのため、詳細ファイルがあれば included の user から復元できる。
    detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dsid}.json")
    payload = _load_json_file(detail_path)
    if payload is None:
        return {}
    try:
        return _build_user_label_map_from_included_users(payload)
    except Exception:
        return {}


def _build_name_map_by_id(payload: Any, preferred_attr_keys: Tuple[str, ...]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in _coerce_data_list(payload):
        item_id = _safe_str(item.get("id")).strip()
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        name = ""
        if isinstance(attrs, dict):
            for k in preferred_attr_keys:
                candidate = _safe_str(attrs.get(k)).strip()
                if candidate:
                    name = candidate
                    break
        if item_id and name:
            result[item_id] = name
    return result


def _build_grant_number_to_subgroup_info(subgroup_payload: Any) -> Dict[str, Dict[str, str]]:
    # subGroup.json often contains included groups of type TEAM.
    # We extract grantNumber -> {"name": team_name, "id": group_id}
    if not isinstance(subgroup_payload, dict):
        return {}

    included = subgroup_payload.get("included")
    if not isinstance(included, list):
        return {}

    mapping: Dict[str, Dict[str, str]] = {}
    for inc in included:
        if not isinstance(inc, dict):
            continue
        attrs = inc.get("attributes") if isinstance(inc.get("attributes"), dict) else {}
        if not isinstance(attrs, dict):
            continue
        if _safe_str(attrs.get("groupType")).strip().upper() != "TEAM":
            continue
        team_name = _safe_str(attrs.get("name")).strip()
        group_id = _safe_str(inc.get("id")).strip()
        subjects = attrs.get("subjects")
        if not isinstance(subjects, list):
            continue
        for subj in subjects:
            if not isinstance(subj, dict):
                continue
            grant = _safe_str(subj.get("grantNumber")).strip()
            if grant and (team_name or group_id):
                mapping.setdefault(grant, {"name": team_name, "id": group_id})
    return mapping


def _build_grant_number_to_subgroup_name(subgroup_payload: Any) -> Dict[str, str]:
    # Backward-compatible helper
    info = _build_grant_number_to_subgroup_info(subgroup_payload)
    return {k: (v.get("name") or "") for k, v in info.items()}


def get_default_columns() -> List[DatasetListColumn]:
    # Labels are aligned to dataset_edit_widget.py where possible (without trailing colon).
    return [
        DatasetListColumn("subgroup_name", "サブグループ名", True),
        DatasetListColumn("grant_number", "課題番号", True),
        DatasetListColumn("dataset_name", "データセット名", True),
        DatasetListColumn("tool_open", "ツール内リンク", True),
        DatasetListColumn("tile_count", "タイル数", True),
        DatasetListColumn("file_count", "ファイル数", True),
        DatasetListColumn("file_size", "ファイルサイズ", True),
        DatasetListColumn("embargo_date", "エンバーゴ期間終了日", True),
        DatasetListColumn("template_name", "データセットテンプレート", True),
        DatasetListColumn("instrument_names", "設備", True),
        DatasetListColumn("manager_name", "管理者", True),
        DatasetListColumn("applicant_name", "申請者", True),
        DatasetListColumn("data_owner_names", "データ所有者", False),
        DatasetListColumn("license_name", "利用ライセンス", False),
        DatasetListColumn("tags", "TAG", False),
        DatasetListColumn("tag_count", "TAG数", True),
        DatasetListColumn("description_len", "説明文字数", True),
        DatasetListColumn("related_datasets_count", "関連データセット", True),
        # Default-hidden (still available via column selector)
        DatasetListColumn("dataset_id", "データセットID", False),
        DatasetListColumn("description", "説明", False),
        DatasetListColumn("contact", "問い合わせ先", False),
        DatasetListColumn("taxonomy_keys", "タクソノミーキー", False),
        DatasetListColumn("related_links", "関連情報", False),
        DatasetListColumn("related_datasets_names", "関連データセット名", False),
        DatasetListColumn("citation_format", "引用書式", False),
        DatasetListColumn("is_anonymized", "匿名化", False),
        DatasetListColumn("is_data_entry_prohibited", "データ登録禁止", False),
        DatasetListColumn("data_listing_type", "データ一覧表示タイプ", False),
    ]


def build_dataset_list_rows_from_files() -> Tuple[List[DatasetListColumn], List[Dict[str, Any]]]:
    """Load JSON files and return (columns, rows).

    Rows are dicts keyed by DatasetListColumn.key.
    Each row also contains:
      - _raw: original dataset item
      - _embargo_date_obj: datetime.date | None (for UI filtering/sorting)
    """

    dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
    subgroup_json_path = get_dynamic_file_path("output/rde/data/subGroup.json")
    info_json_path = get_dynamic_file_path("output/rde/data/info.json")
    template_json_path = get_dynamic_file_path("output/rde/data/template.json")
    instruments_json_path = get_dynamic_file_path("output/rde/data/instruments.json")
    licenses_json_path = get_dynamic_file_path("output/rde/data/licenses.json")
    subgroups_dir = get_dynamic_file_path("output/rde/data/subGroups")

    dataset_payload = _load_json_file(dataset_json_path)
    subgroup_payload = _load_json_file(subgroup_json_path)
    info_payload = _load_json_file(info_json_path)
    template_payload = _load_json_file(template_json_path)
    instruments_payload = _load_json_file(instruments_json_path)
    licenses_payload = _load_json_file(licenses_json_path)

    dataset_items = _coerce_data_list(dataset_payload)
    grant_to_subgroup_info = _build_grant_number_to_subgroup_info(subgroup_payload)
    user_label_map = _build_user_label_map_best_effort(info_payload, subgroup_payload, subgroups_dir)

    # template.json/instruments.json/licenses.json name resolution (best-effort)
    template_name_by_id = _build_name_map_by_id(template_payload, ("nameJa", "name", "title"))
    instrument_name_by_id = _build_name_map_by_id(instruments_payload, ("nameJa", "name", "title"))
    license_name_by_id = _build_name_map_by_id(licenses_payload, ("nameJa", "name", "title"))

    dataset_name_by_id: Dict[str, str] = {}
    for it in dataset_items:
        did = _safe_str(it.get("id")).strip()
        attrs = it.get("attributes") if isinstance(it.get("attributes"), dict) else {}
        name = _safe_str(attrs.get("name")).strip() if isinstance(attrs, dict) else ""
        if did and name:
            dataset_name_by_id[did] = name

    columns = get_default_columns()

    # Cache dataEntry computations to avoid repeated disk IO.
    data_entry_payload_cache: Dict[str, Any] = {}
    data_entry_stats_cache: Dict[str, Tuple[Optional[int], Optional[int], Optional[int]]] = {}

    def _load_data_entry_payload(dsid: str) -> Any:
        dsid = _safe_str(dsid).strip()
        if not dsid:
            return None
        if dsid in data_entry_payload_cache:
            return data_entry_payload_cache[dsid]
        try:
            path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dsid}.json")
            if not path or not os.path.exists(path):
                data_entry_payload_cache[dsid] = None
                return None
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            data_entry_payload_cache[dsid] = payload
            return payload
        except Exception:
            data_entry_payload_cache[dsid] = None
            return None

    def _compute_tile_file_stats(dsid: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Return (tile_count, shared2_file_count, shared2_bytes) best-effort."""

        dsid = _safe_str(dsid).strip()
        if not dsid:
            return None, None, None
        if dsid in data_entry_stats_cache:
            return data_entry_stats_cache[dsid]

        payload = _load_data_entry_payload(dsid)
        if not isinstance(payload, dict):
            data_entry_stats_cache[dsid] = (None, None, None)
            return None, None, None

        tiles = payload.get("data")
        tile_count = len(tiles) if isinstance(tiles, list) else 0

        summary = None
        try:
            # Listing tab should stay responsive; skip expensive per-entry cached dataFiles payloads.
            summary = compute_summary_from_payload(payload, prefer_cached_files=False)
        except Exception:
            summary = None

        shared2 = summary.get("shared2") if isinstance(summary, dict) else None
        if not isinstance(shared2, dict):
            data_entry_stats_cache[dsid] = (tile_count, None, None)
            return tile_count, None, None

        shared2_count = int(shared2.get("count", 0) or 0)
        shared2_bytes = int(shared2.get("bytes", 0) or 0)
        data_entry_stats_cache[dsid] = (tile_count, shared2_count, shared2_bytes)
        return tile_count, shared2_count, shared2_bytes

    rows: List[Dict[str, Any]] = []
    for item in dataset_items:
        dataset_id = _safe_str(item.get("id")).strip()
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        attrs = attrs if isinstance(attrs, dict) else {}

        grant_number = _safe_str(attrs.get("grantNumber")).strip()
        subgroup_info = grant_to_subgroup_info.get(grant_number, {}) if grant_number else {}
        subgroup_name = _safe_str(subgroup_info.get("name")).strip() if isinstance(subgroup_info, dict) else ""
        subgroup_id = _safe_str(subgroup_info.get("id")).strip() if isinstance(subgroup_info, dict) else ""

        dataset_name = _safe_str(attrs.get("name")).strip()
        description = _safe_str(attrs.get("description"))
        embargo_text = _safe_str(attrs.get("embargoDate")).strip()
        embargo_date_obj = _parse_iso_date(embargo_text)
        embargo_display = embargo_date_obj.isoformat() if embargo_date_obj else (embargo_text.split("T")[0] if embargo_text else "")

        contact = _safe_str(attrs.get("contact"))
        taxonomy_keys = attrs.get("taxonomyKeys") if isinstance(attrs.get("taxonomyKeys"), list) else []
        taxonomy_keys_text = " ".join([_safe_str(x).strip() for x in taxonomy_keys if _safe_str(x).strip()])

        related_links = _format_related_links(attrs.get("relatedLinks"))
        tags = attrs.get("tags") if isinstance(attrs.get("tags"), list) else []
        tag_items = [_safe_str(t).strip() for t in tags if _safe_str(t).strip()]
        tags_text = ", ".join(tag_items)
        tag_count = len(tag_items)

        citation_format = _safe_str(attrs.get("citationFormat"))
        is_anonymized = bool(attrs.get("isAnonymized", False))
        is_data_entry_prohibited = bool(attrs.get("isDataEntryProhibited", False))
        data_listing_type = _safe_str(attrs.get("dataListingType") or "")

        template_id = _extract_rel_id(item, "template")
        template_name = template_name_by_id.get(template_id, template_id)

        manager_id = _extract_rel_id(item, "manager")
        manager_label = user_label_map.get(manager_id, "") if manager_id else ""

        applicant_id = _extract_rel_id(item, "applicant")
        applicant_label = user_label_map.get(applicant_id, "") if applicant_id else ""

        # Fallback: per-dataset detail JSON may contain included users with org/name.
        if dataset_id and ((manager_id and not manager_label) or (applicant_id and not applicant_label)):
            detail_user_map = _load_dataset_detail_user_label_map(dataset_id)
            if manager_id and not manager_label:
                manager_label = detail_user_map.get(manager_id, "")
            if applicant_id and not applicant_label:
                applicant_label = detail_user_map.get(applicant_id, "")

        manager_resolved = bool(manager_id and manager_label and manager_label != manager_id)
        manager_name = manager_label or manager_id

        applicant_resolved = bool(applicant_id and applicant_label and applicant_label != applicant_id)
        applicant_name = applicant_label or applicant_id

        license_id = _extract_rel_id(item, "license")
        license_name = license_name_by_id.get(license_id, license_id)

        instrument_ids = _extract_rel_ids(item, "instruments")
        if not instrument_ids:
            instrument_ids = _extract_rel_ids(item, "instrument")
        instrument_names = [instrument_name_by_id.get(i, i) for i in instrument_ids]

        data_owner_ids = _extract_rel_ids(item, "dataOwners")
        data_owner_names = [user_label_map.get(i, i) for i in data_owner_ids]

        related_dataset_ids = _extract_rel_ids(item, "relatedDatasets")
        related_dataset_names = [dataset_name_by_id.get(i, i) for i in related_dataset_ids]

        tile_count, shared2_file_count, shared2_bytes = _compute_tile_file_stats(dataset_id)
        file_size_display = ""
        if shared2_bytes is not None:
            try:
                file_size_display = format_size_with_bytes(shared2_bytes)
            except Exception:
                file_size_display = _safe_str(shared2_bytes)

        row: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "subgroup_name": subgroup_name,
            "subgroup_id": subgroup_id,
            "grant_number": grant_number,
            "dataset_name": dataset_name,
            "tool_open": "ツール内" if dataset_id else "",
            "tile_count": tile_count,
            "file_count": shared2_file_count,
            "file_size": file_size_display,
            "description": description,
            "description_len": len(description) if isinstance(description, str) else 0,
            "embargo_date": embargo_display,
            "template_name": template_name,
            "instrument_names": ", ".join([n for n in instrument_names if n]),
            "manager_name": manager_name,
            "applicant_name": applicant_name,
            "data_owner_names": ", ".join([n for n in data_owner_names if n]),
            "contact": contact,
            "taxonomy_keys": taxonomy_keys_text,
            "related_links": related_links,
            "tags": tags_text,
            "tag_count": tag_count,
            "license_name": license_name,
            "related_datasets_count": len(related_dataset_ids),
            "related_datasets_names": "\n".join([n for n in related_dataset_names if n]),
            "citation_format": citation_format,
            "is_anonymized": is_anonymized,
            "is_data_entry_prohibited": is_data_entry_prohibited,
            "data_listing_type": data_listing_type,
            # extras
            "_raw": item,
            "_embargo_date_obj": embargo_date_obj,
            "_template_id": template_id,
            "_license_id": license_id,
            "_instrument_ids": instrument_ids,
            "_instrument_names": instrument_names,
            "_manager_id": manager_id,
            "_applicant_id": applicant_id,
            "_manager_resolved": manager_resolved,
            "_applicant_resolved": applicant_resolved,
            "_related_dataset_ids": related_dataset_ids,
        }

        rows.append(row)

    return columns, rows
