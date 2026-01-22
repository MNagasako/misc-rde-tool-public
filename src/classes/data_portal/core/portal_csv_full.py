"""Logged-in portal CSV parsing (full table).

This module keeps *all columns* from the portal CSV for the listing tab.

- UI-agnostic
- Accepts bytes/str payloads (from PortalClient.download_theme_csv)

NOTE:
- There is an existing parser in `portal_csv_status.py` that extracts only
  dataset_id + status for the dataset listing.
- This module is intentionally separate to avoid impacting existing behaviour.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Iterable, Optional


def decode_portal_csv_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload

    data = payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode("utf-8", errors="ignore")
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp", "latin-1"):
        try:
            return bytes(data).decode(enc)
        except Exception:
            continue
    try:
        return bytes(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _normalize_header(header: str) -> str:
    text = (header or "").strip().replace("\ufeff", "")
    text = re.sub(r"\s+", " ", text)
    return text


def parse_portal_csv_to_records(csv_text: str) -> list[dict[str, str]]:
    """Parse portal CSV text into a list of {header: value} dicts.

    - Keeps all columns.
    - Values are normalized to strings.
    - Empty rows are skipped.
    """

    text = csv_text or ""
    if not text.strip():
        return []

    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return []

    # Some portal CSV exports contain duplicate column headers (e.g. "タグ" appears twice).
    # If we keep them as-is, later dict assignment overwrites earlier values.
    # To preserve all values, we uniquify headers by appending " (2)", " (3)", ...
    seen: dict[str, int] = {}
    headers: list[str] = []
    for raw in raw_headers:
        base = _normalize_header(raw)
        if not base:
            headers.append("")
            continue
        n = int(seen.get(base, 0)) + 1
        seen[base] = n
        if n == 1:
            headers.append(base)
        else:
            headers.append(f"{base} ({n})")

    records: list[dict[str, str]] = []
    for row in reader:
        if not row:
            continue
        record: dict[str, str] = {}
        non_empty = False
        for idx, header in enumerate(headers):
            if not header:
                continue
            value = row[idx] if idx < len(row) else ""
            value = str(value or "").strip()
            if value:
                non_empty = True
            record[header] = value
        if non_empty and record:
            records.append(record)
    return records


def parse_portal_csv_payload_to_records(payload: Any) -> list[dict[str, str]]:
    return parse_portal_csv_to_records(decode_portal_csv_payload(payload))


def pick_first_value(record: dict[str, str], candidates: Iterable[str]) -> Optional[str]:
    for key in candidates:
        value = str(record.get(key, "") or "").strip()
        if value:
            return value
    return None


def extract_code(record: dict[str, str]) -> str:
    """Best-effort extract portal entry code from a CSV record."""

    candidates = (
        "code",
        "CODE",
        "Code",
        "管理コード",
        "管理code",
        "管理Code",
        "管理番号",
        "テーマコード",
        "テーマID",
        "theme_code",
        "theme id",
        "theme_id",
    )
    value = pick_first_value(record, candidates)
    if value is None:
        return ""
    m = re.search(r"\d+", value)
    return m.group(0) if m else value


def extract_dataset_id(record: dict[str, str]) -> str:
    candidates = (
        "データセットID",
        "データセットid",
        "dataset_id",
        "dataset id",
        "Dataset ID",
    )
    value = pick_first_value(record, candidates)
    return value or ""
