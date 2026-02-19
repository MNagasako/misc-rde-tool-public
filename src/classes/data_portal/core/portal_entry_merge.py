"""Merge public cache records and managed (logged-in) CSV records.

Rules (per user request):
- Merge primary key is `code`.
- Highest priority match: both sides have (code and dataset_id) and they match.
- Otherwise: match by code when possible.

NOTE:
- Public cache data comes from output/data_portal_public/cache (JSON dicts).
- Managed CSV rows can contain a different set of columns depending on access.

This module is UI-agnostic; it outputs merged row dicts suitable for tables.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Iterable, Optional
import unicodedata

from config.common import get_dynamic_file_path


_DATASET_DETAIL_CACHE: dict[str, Optional[dict[str, Any]]] = {}


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_cmp_text(text: str) -> str:
    """Normalize text for best-effort equality checks.

    Public cache values can differ from managed CSV due to formatting conversions
    (e.g. HTML -> plain text, whitespace changes, full/half width). This function
    makes comparisons more resilient while staying conservative.
    """

    t = text.strip()
    if not t:
        return ""
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _format_user_label(user_name: str, organization_name: str) -> str:
    name = (user_name or "").strip()
    org = (organization_name or "").strip()
    if name and org:
        return f"{name} ({org})"
    return name or org


def _build_user_label_map_from_included_users(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    included = payload.get("included")
    if not isinstance(included, list):
        return {}
    result: dict[str, str] = {}
    for inc in included:
        if not isinstance(inc, dict):
            continue
        if _to_str(inc.get("type") or "").strip() != "user":
            continue
        user_id = _to_str(inc.get("id") or "").strip()
        attrs = inc.get("attributes") if isinstance(inc.get("attributes"), dict) else {}
        if not user_id or not isinstance(attrs, dict):
            continue
        user_name = _to_str(attrs.get("userName") or attrs.get("name") or "").strip()
        org_name = _to_str(attrs.get("organizationName") or "").strip()
        label = _format_user_label(user_name, org_name)
        if label:
            result[user_id] = label
    return result


def _load_dataset_detail_payload(dataset_id: str) -> Optional[dict[str, Any]]:
    dsid = _to_str(dataset_id or "").strip()
    if not dsid:
        return None
    if dsid in _DATASET_DETAIL_CACHE:
        return _DATASET_DETAIL_CACHE.get(dsid)

    detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dsid}.json")
    if not detail_path or not os.path.exists(detail_path):
        _DATASET_DETAIL_CACHE[dsid] = None
        return None
    try:
        with open(detail_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            payload = None
    except Exception:
        payload = None

    _DATASET_DETAIL_CACHE[dsid] = payload
    return payload


def _compact_date_text(value: Any) -> str:
    text = _to_str(value).strip()
    if not text:
        return ""
    normalized = text.replace("T", " ")
    normalized = normalized.replace(".", "-").replace("/", "-")
    match = re.match(r"^(\d{4}-\d{1,2}-\d{1,2})", normalized)
    if match:
        parts = match.group(1).split("-")
        if len(parts) == 3:
            y, m, d = parts
            try:
                return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            except Exception:
                return match.group(1)
    return text


def _normalize_date_columns(row: dict[str, Any]) -> None:
    for key in ("opened_date", "registered_date", "embargo_release_date", "updated_date"):
        value = _to_str(row.get(key) or "").strip()
        if not value:
            continue
        normalized = _compact_date_text(value)
        if normalized:
            row[key] = normalized


def _set_if_missing(row: dict[str, Any], key: str, value: Any) -> None:
    current = _to_str(row.get(key) or "").strip()
    if current:
        return
    incoming = _to_str(value).strip()
    if incoming:
        row[key] = incoming


def _resolve_dataset_manager_label(dataset_id: str) -> str:
    dsid = _to_str(dataset_id or "").strip()
    if not dsid:
        return ""
    payload = _load_dataset_detail_payload(dsid)
    if not isinstance(payload, dict):
        return ""

    relationships = ((payload.get("data") or {}).get("relationships") or {})
    manager_data = ((relationships.get("manager") or {}).get("data") or {})
    manager_id = _to_str(manager_data.get("id") or "").strip()
    if not manager_id:
        return ""

    label_map = _build_user_label_map_from_included_users(payload)
    return label_map.get(manager_id, "")


def extract_public_code(record: dict) -> str:
    return _to_str(record.get("code") or "").strip()


def extract_public_dataset_id(record: dict) -> str:
    fields_raw = record.get("fields_raw") if isinstance(record.get("fields_raw"), dict) else {}
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    dsid = _to_str(fields_raw.get("dataset_id") or fields.get("dataset_id") or record.get("dataset_id") or "").strip()
    return dsid


def normalize_public_record(record: dict) -> dict[str, Any]:
    """Flatten public cache record into a row dict for listing."""

    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    fields_raw = record.get("fields_raw") if isinstance(record.get("fields_raw"), dict) else {}
    metrics_raw = record.get("data_metrics_raw") if isinstance(record.get("data_metrics_raw"), dict) else {}

    row: dict[str, Any] = {
        "source": "public",
        "code": extract_public_code(record),
        "key": _to_str(record.get("key") or "").strip(),
        "dataset_id": extract_public_dataset_id(record),
        "title": _to_str(record.get("title") or "").strip(),
        "dataset_name": _to_str(record.get("title") or "").strip(),
        "summary": _to_str(record.get("summary") or "").strip(),
        "url": _to_str(record.get("url") or record.get("detail_url") or "").strip(),
        "outcomes_publications_and_use": "",
        "equipment_links": [],
        "thumbnails": [],
    }

    try:
        equip = record.get("equipment_links")
        if isinstance(equip, list):
            row["equipment_links"] = [e for e in equip if isinstance(e, dict)]
    except Exception:
        pass
    try:
        thumbs = record.get("thumbnails")
        if isinstance(thumbs, list):
            row["thumbnails"] = [str(v) for v in thumbs if str(v or "").strip()]
    except Exception:
        pass

    for k in (
        "project_title",
        "project_number",
        "dataset_registrant",
        "organization",
        "updated_date",
        "registered_date",
        "embargo_release_date",
        "license",
        "doi",
        "key_technology_area_primary",
        "key_technology_area_secondary",
        "crosscutting_technology_area",
        "keyword_tags",
        "outcomes_publications_and_use",
        "material_index",
    ):
        value = fields_raw.get(k) if isinstance(fields_raw, dict) else None
        if value in (None, ""):
            value = fields.get(k) if isinstance(fields, dict) else None
        if value not in (None, ""):
            row[k] = value

    for k in (
        "page_views",
        "download_count",
        "file_count",
        "total_file_size",
        "data_tile_count",
    ):
        value = metrics_raw.get(k) if isinstance(metrics_raw, dict) else None
        if value in (None, ""):
            value = fields_raw.get(k) if isinstance(fields_raw, dict) else None
        if value in (None, ""):
            value = fields.get(k) if isinstance(fields, dict) else None
        if value not in (None, ""):
            row[k] = value

    return row


def normalize_managed_record(record: dict[str, str], *, code: str, dataset_id: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source": "managed",
        "code": code,
        "dataset_id": dataset_id,
    }

    # Best-effort mapping of common CSV headers to standard listing keys.
    # This allows managed values to override public values during merge.
    header_to_key = {
        "タイトル": "project_title",
        "課題名": "project_title",
        "課題番号": "project_number",
        "サブタイトル": "dataset_name",
        "データセット名": "dataset_name",
        "要約": "summary",
        "URL": "url",
        "リンク": "url",
        "機関": "organization",
        "実施機関": "organization",
        "登録日": "registered_date",
        "エンバーゴ解除日": "embargo_release_date",
        "エンバーゴ期間終了日": "embargo_release_date",
        "開設日時": "opened_date",
        "ライセンス": "license",
        "ライセンスレベル": "license_level",
        "キーワードタグ": "keyword_tags",
        "タグ": "keyword_tags",
        "タグ (2)": "keyword_tags",
        "タグ(2)": "keyword_tags",
        "データ数": "data_tile_count",
        "データタイル数": "data_tile_count",
        "管理者": "dataset_manager",
        "管理者名": "dataset_manager",
        "管理者(所属)": "dataset_manager",
        "管理者（所属）": "dataset_manager",
        "ステータス": "managed_status",
        "状態": "managed_status",
        "公開状況": "managed_status",
    }

    def _merge_tag_values(current: str, incoming: str) -> str:
        existing = [p.strip() for p in (current or "").split(",") if p.strip()]
        extras = [p.strip() for p in (incoming or "").split(",") if p.strip()]
        seen: list[str] = []
        for part in existing + extras:
            if part and part not in seen:
                seen.append(part)
        return ", ".join(seen)

    for header, key in header_to_key.items():
        value = str(record.get(header, "") or "").strip()
        if not value:
            continue
        if key == "keyword_tags":
            current = str(row.get(key, "") or "").strip()
            row[key] = _merge_tag_values(current, value) if current else value
            continue
        if str(row.get(key, "") or "").strip():
            continue
        row[key] = value

    title_value = str(record.get("タイトル") or "").strip()
    if title_value and not str(row.get("title") or "").strip():
        row["title"] = title_value
        if not str(row.get("dataset_name") or "").strip():
            row["dataset_name"] = title_value

    # Some exports provide a placeholder for license (e.g. "（）") while the actual
    # license info is available via "ライセンスレベル". Prefer explicit "ライセンス"
    # when meaningful; otherwise, fall back to "ライセンスレベル".
    try:
        lic = str(row.get("license") or "").strip()
        if lic in ("()", "（ ）", "（）", "-", "―"):
            row.pop("license", None)
            lic = ""
        if not lic:
            level = str(row.get("license_level") or record.get("ライセンスレベル") or "").strip()
            if level:
                row["license"] = level
    except Exception:
        pass
    # Keep all columns (fixed set is selected by UI).
    for k, v in record.items():
        if k in ("", None):
            continue
        row[f"managed:{k}"] = v

    return row


@dataclass(frozen=True)
class MergeResult:
    rows: list[dict[str, Any]]
    managed_only: int
    public_only: int
    merged: int


def merge_public_and_managed(
    public_records: Iterable[dict],
    managed_records: Iterable[dict[str, str]],
    *,
    managed_code_getter,
    managed_dataset_id_getter,
) -> MergeResult:
    """Merge public cache + managed CSV rows.

    managed_*_getter are callables to extract code/dataset_id from a managed record.
    """

    public_rows = [normalize_public_record(r) for r in public_records if isinstance(r, dict)]

    managed_rows: list[dict[str, Any]] = []
    for rec in managed_records:
        if not isinstance(rec, dict):
            continue
        code = _to_str(managed_code_getter(rec) or "").strip()
        dataset_id = _to_str(managed_dataset_id_getter(rec) or "").strip()
        managed_rows.append(normalize_managed_record(rec, code=code, dataset_id=dataset_id))

    # Index managed by code.
    managed_by_code: dict[str, list[dict[str, Any]]] = {}
    managed_without_code: list[dict[str, Any]] = []
    for row in managed_rows:
        code = _to_str(row.get("code") or "").strip()
        if not code:
            managed_without_code.append(row)
            continue
        managed_by_code.setdefault(code, []).append(row)

    merged_rows: list[dict[str, Any]] = []
    merged_count = 0
    public_only = 0

    used_managed_ids: set[int] = set()

    def _pick_best_managed(code: str, dataset_id: str) -> Optional[dict[str, Any]]:
        candidates = managed_by_code.get(code) or []
        if not candidates:
            return None
        # Best: exact dataset_id match when both sides have it.
        if dataset_id:
            for c in candidates:
                if id(c) in used_managed_ids:
                    continue
                if _to_str(c.get("dataset_id") or "").strip() == dataset_id:
                    return c
        # Fallback: first unused by code.
        for c in candidates:
            if id(c) not in used_managed_ids:
                return c
        return None

    def _apply_dataset_manager(row: dict[str, Any]) -> None:
        dataset_id = _to_str(row.get("dataset_id") or "").strip()
        payload = _load_dataset_detail_payload(dataset_id)
        row["_has_rde_detail"] = bool(isinstance(payload, dict))

        attrs = ((payload.get("data") or {}).get("attributes") or {}) if isinstance(payload, dict) else {}
        meta = ((payload.get("data") or {}).get("meta") or {}) if isinstance(payload, dict) else {}
        relationships = ((payload.get("data") or {}).get("relationships") or {}) if isinstance(payload, dict) else {}
        user_labels = _build_user_label_map_from_included_users(payload) if isinstance(payload, dict) else {}

        _set_if_missing(row, "project_number", attrs.get("grantNumber"))
        _set_if_missing(row, "project_title", attrs.get("subjectTitle"))
        _set_if_missing(row, "dataset_name", attrs.get("name"))
        _set_if_missing(row, "summary", attrs.get("description"))
        _set_if_missing(row, "opened_date", _compact_date_text(attrs.get("openAt") or attrs.get("created")))
        _set_if_missing(row, "embargo_release_date", _compact_date_text(attrs.get("embargoDate")))
        _set_if_missing(row, "data_tile_count", meta.get("dataCount"))

        manager_id = _to_str((((relationships.get("manager") or {}).get("data") or {}).get("id") or "")).strip()
        applicant_id = _to_str((((relationships.get("applicant") or {}).get("data") or {}).get("id") or "")).strip()
        manager_label = _to_str(user_labels.get(manager_id) or "").strip() if manager_id else ""
        applicant_label = _to_str(user_labels.get(applicant_id) or "").strip() if applicant_id else ""
        applicant_org = ""
        manager_org = ""
        if applicant_label:
            m = re.search(r"\(([^()]+)\)\s*$", applicant_label)
            if m:
                applicant_org = _to_str(m.group(1) or "").strip()
        if manager_label:
            m = re.search(r"\(([^()]+)\)\s*$", manager_label)
            if m:
                manager_org = _to_str(m.group(1) or "").strip()

        # 優先順位: RDE > CSV > スクレイピング
        # RDE側で取得できた値は既存値を上書きする。
        rde_priority_values = {
            "project_number": _to_str(attrs.get("grantNumber") or "").strip(),
            "project_title": _to_str(attrs.get("subjectTitle") or "").strip(),
            "dataset_name": _to_str(attrs.get("name") or "").strip(),
            "summary": _to_str(attrs.get("description") or "").strip(),
            "opened_date": _compact_date_text(attrs.get("openAt") or attrs.get("created")),
            "updated_date": _compact_date_text(attrs.get("modified")),
            "embargo_release_date": _compact_date_text(attrs.get("embargoDate")),
            "data_tile_count": _to_str(meta.get("dataCount") or "").strip(),
            "dataset_manager": manager_label or applicant_label,
            "dataset_registrant": applicant_label or manager_label,
            "organization": applicant_org or manager_org,
        }
        for key, value in rde_priority_values.items():
            if _to_str(value).strip():
                row[key] = value

        if not _to_str(row.get("organization") or "").strip():
            org = ""
            for uid in (applicant_id, manager_id):
                if not uid:
                    continue
                label = _to_str(user_labels.get(uid) or "").strip()
                if not label:
                    continue
                m = re.search(r"\(([^()]+)\)\s*$", label)
                if m:
                    org = _to_str(m.group(1) or "").strip()
                    if org:
                        break
            if org:
                row["organization"] = org

        if not _to_str(row.get("dataset_manager") or "").strip():
            label = _resolve_dataset_manager_label(_to_str(row.get("dataset_id") or ""))
            if label:
                row["dataset_manager"] = label
        if not _to_str(row.get("dataset_registrant") or "").strip():
            manager = _to_str(row.get("dataset_manager") or "").strip()
            if manager:
                row["dataset_registrant"] = manager

        _normalize_date_columns(row)

    for pub in public_rows:
        code = _to_str(pub.get("code") or "").strip()
        dataset_id = _to_str(pub.get("dataset_id") or "").strip()

        if code:
            managed = _pick_best_managed(code, dataset_id)
        else:
            managed = None

        if managed is None:
            _apply_dataset_manager(pub)
            merged_rows.append(pub)
            public_only += 1
            continue

        used_managed_ids.add(id(managed))
        merged_count += 1

        unified_keys = (
            "title",
            "dataset_id",
            "dataset_name",
            "project_number",
            "project_title",
            "dataset_registrant",
            "summary",
            "url",
            "organization",
            "dataset_manager",
            "opened_date",
            "updated_date",
            "registered_date",
            "embargo_release_date",
            "data_tile_count",
            "license",
            "doi",
            "keyword_tags",
        )

        cell_origin: dict[str, str] = {}
        cell_diff: dict[str, dict[str, str]] = {}
        for key in unified_keys:
            pub_value = _to_str(pub.get(key) or "").strip()
            managed_value = _to_str(managed.get(key) or "").strip()

            if managed_value:
                cell_origin[key] = "managed"
                if pub_value and _normalize_cmp_text(pub_value) != _normalize_cmp_text(managed_value):
                    cell_diff[key] = {"public": pub_value, "managed": managed_value}
            elif pub_value:
                cell_origin[key] = "public"

        # Combine: managed wins when keys overlap.
        merged_row = dict(pub)
        merged_row.update(managed)
        merged_row["source"] = "both"
        merged_row["_cell_origin"] = cell_origin
        merged_row["_cell_diff"] = cell_diff
        _apply_dataset_manager(merged_row)
        merged_rows.append(merged_row)

    managed_only_rows: list[dict[str, Any]] = []
    for code, candidates in managed_by_code.items():
        for m in candidates:
            if id(m) in used_managed_ids:
                continue
            m = dict(m)
            _apply_dataset_manager(m)
            managed_only_rows.append(m)

    managed_only_rows.extend(managed_without_code)

    all_rows = merged_rows + managed_only_rows
    return MergeResult(
        rows=all_rows,
        managed_only=len(managed_only_rows),
        public_only=public_only,
        merged=merged_count,
    )
