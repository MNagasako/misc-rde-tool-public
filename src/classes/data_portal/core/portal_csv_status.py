"""Logged-in portal CSV (theme list) parsing.

This module is UI-agnostic.
- Decodes CSV bytes from the Data Portal "csv_download" endpoint.
- Extracts dataset_id + status and maps them to listing labels.

Rules:
- "公開済" -> "公開（管理）"
- "非公開" -> "UP済" (entry exists but not publicly published)

All HTTP access is handled elsewhere (PortalClient).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from classes.dataset.util.portal_status_resolver import PUBLIC_MANAGED_LABEL


@dataclass(frozen=True)
class PortalCsvRow:
    dataset_id: str
    raw_status: str


_STATUS_PUBLIC_MARKERS = ("公開済",)
_STATUS_PRIVATE_MARKERS = ("非公開",)


def _decode_csv_bytes(payload: bytes) -> str:
    data = payload or b""
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    # last resort
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _normalize_header(h: str) -> str:
    return (h or "").strip().replace("\ufeff", "").lower()


def _pick_header_index(headers: list[str], candidates: Iterable[str]) -> Optional[int]:
    norm = [_normalize_header(h) for h in headers]
    cand_norm = {_normalize_header(c) for c in candidates}
    for i, h in enumerate(norm):
        if h in cand_norm:
            return i
    return None


def parse_portal_theme_csv_rows(csv_text: str) -> list[PortalCsvRow]:
    """Parse CSV text and return (dataset_id, raw_status) rows."""

    text = csv_text or ""
    if not text.strip():
        return []

    # Dialect: allow commas, tabs, etc.
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect=dialect)

    try:
        headers = next(reader)
    except StopIteration:
        return []

    # Common header variants seen in portals
    dataset_id_idx = _pick_header_index(headers, candidates=(
        "データセットid",
        "データセットID",
        "dataset_id",
        "datasetid",
        "dataset id",
    ))
    status_idx = _pick_header_index(headers, candidates=(
        "ステータス",
        "状態",
        "公開ステータス",
        "status",
        "公開/非公開",
        "公開状況",
    ))

    if dataset_id_idx is None or status_idx is None:
        # Best-effort: scan header cells.
        for i, h in enumerate(headers):
            n = _normalize_header(h)
            if dataset_id_idx is None and ("dataset" in n and "id" in n or "データセット" in n and "id" in n):
                dataset_id_idx = i
            if status_idx is None and ("status" in n or "ステータ" in n or "公開" in n):
                status_idx = i

    if dataset_id_idx is None or status_idx is None:
        return []

    rows: list[PortalCsvRow] = []
    for record in reader:
        if not record or max(dataset_id_idx, status_idx) >= len(record):
            continue
        dsid = str(record[dataset_id_idx] or "").strip()
        status = str(record[status_idx] or "").strip()
        if not dsid:
            continue
        rows.append(PortalCsvRow(dataset_id=dsid, raw_status=status))

    return rows


def map_csv_rows_to_listing_labels(rows: Iterable[PortalCsvRow]) -> Dict[str, str]:
    """Map parsed CSV rows to dataset_id -> portal_status label."""

    mapping: Dict[str, str] = {}
    for row in rows:
        dsid = str(row.dataset_id or "").strip()
        if not dsid:
            continue
        status = str(row.raw_status or "").strip()

        label = None
        if any(m in status for m in _STATUS_PUBLIC_MARKERS):
            label = PUBLIC_MANAGED_LABEL
        elif any(m in status for m in _STATUS_PRIVATE_MARKERS):
            label = "UP済"

        if label:
            mapping[dsid] = label

    return mapping


def parse_portal_theme_csv_to_label_map(payload: Any) -> Dict[str, str]:
    """Convenience: bytes/str -> dataset_id -> label."""

    if payload is None:
        return {}
    if isinstance(payload, bytes):
        text = _decode_csv_bytes(payload)
    else:
        text = str(payload)

    rows = parse_portal_theme_csv_rows(text)
    return map_csv_rows_to_listing_labels(rows)
