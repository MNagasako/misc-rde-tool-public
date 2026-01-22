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
import re
from typing import Any, Iterable, Optional
import unicodedata


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


def extract_public_code(record: dict) -> str:
    return _to_str(record.get("code") or "").strip()


def extract_public_dataset_id(record: dict) -> str:
    fields_raw = record.get("fields_raw") if isinstance(record.get("fields_raw"), dict) else {}
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    dsid = _to_str(fields_raw.get("dataset_id") or fields.get("dataset_id") or record.get("dataset_id") or "").strip()
    return dsid


def normalize_public_record(record: dict) -> dict[str, Any]:
    """Flatten public cache record into a row dict for listing."""

    fields_raw = record.get("fields_raw") if isinstance(record.get("fields_raw"), dict) else {}
    metrics_raw = record.get("data_metrics_raw") if isinstance(record.get("data_metrics_raw"), dict) else {}

    row: dict[str, Any] = {
        "source": "public",
        "code": extract_public_code(record),
        "key": _to_str(record.get("key") or "").strip(),
        "dataset_id": extract_public_dataset_id(record),
        "title": _to_str(record.get("title") or "").strip(),
        "summary": _to_str(record.get("summary") or "").strip(),
        "url": _to_str(record.get("url") or record.get("detail_url") or "").strip(),
    }

    for k in (
        "project_title",
        "project_number",
        "dataset_registrant",
        "organization",
        "registered_date",
        "embargo_release_date",
        "license",
        "key_technology_area_primary",
        "key_technology_area_secondary",
        "crosscutting_technology_area",
        "keyword_tags",
        "outcomes_publications_and_use",
        "material_index",
    ):
        if k in fields_raw and fields_raw.get(k) not in (None, ""):
            row[k] = fields_raw.get(k)

    for k in (
        "page_views",
        "download_count",
        "file_count",
        "total_file_size",
        "data_tile_count",
    ):
        if k in metrics_raw and metrics_raw.get(k) not in (None, ""):
            row[k] = metrics_raw.get(k)

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
        "タイトル": "title",
        "課題名": "title",
        "要約": "summary",
        "URL": "url",
        "リンク": "url",
        "機関": "organization",
        "実施機関": "organization",
        "登録日": "registered_date",
        "エンバーゴ解除日": "embargo_release_date",
        "エンバーゴ期間終了日": "embargo_release_date",
        "ライセンス": "license",
        "ライセンスレベル": "license_level",
        "キーワードタグ": "keyword_tags",
        "タグ": "keyword_tags",
        "ステータス": "managed_status",
        "状態": "managed_status",
        "公開状況": "managed_status",
    }

    for header, key in header_to_key.items():
        value = str(record.get(header, "") or "").strip()
        if value:
            row[key] = value

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

    for pub in public_rows:
        code = _to_str(pub.get("code") or "").strip()
        dataset_id = _to_str(pub.get("dataset_id") or "").strip()

        if code:
            managed = _pick_best_managed(code, dataset_id)
        else:
            managed = None

        if managed is None:
            merged_rows.append(pub)
            public_only += 1
            continue

        used_managed_ids.add(id(managed))
        merged_count += 1

        unified_keys = (
            "dataset_id",
            "title",
            "summary",
            "url",
            "organization",
            "registered_date",
            "embargo_release_date",
            "license",
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
        merged_rows.append(merged_row)

    managed_only_rows: list[dict[str, Any]] = []
    for code, candidates in managed_by_code.items():
        for m in candidates:
            if id(m) in used_managed_ids:
                continue
            managed_only_rows.append(m)

    managed_only_rows.extend(managed_without_code)

    all_rows = merged_rows + managed_only_rows
    return MergeResult(
        rows=all_rows,
        managed_only=len(managed_only_rows),
        public_only=public_only,
        merged=merged_count,
    )
