from __future__ import annotations

import csv
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from openpyxl import Workbook


_EXPORT_SCALAR_TYPES = (str, int, float, bool, datetime, date, time, Decimal)


def _coerce_export_value(value: object) -> Any:
    if value is None or isinstance(value, _EXPORT_SCALAR_TYPES):
        return value
    return str(value)


def write_table_export(
    path: str,
    fmt: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    sheet_name: str = "Sheet1",
) -> None:
    normalized = str(fmt or "").strip().lower()
    resolved_headers = [str(header or "") for header in headers]
    resolved_rows = [list(row) for row in rows]

    if normalized == "csv":
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            if resolved_headers:
                writer.writerow(resolved_headers)
            for row in resolved_rows:
                writer.writerow([_coerce_export_value(value) for value in row])
        return

    if normalized == "xlsx":
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = str(sheet_name or "Sheet1")[:31] or "Sheet1"
        if resolved_headers:
            worksheet.append(resolved_headers)
        for row in resolved_rows:
            worksheet.append([_coerce_export_value(value) for value in row])
        workbook.save(path)
        return

    raise ValueError(f"Unsupported export format: {fmt}")


def write_record_export(
    path: str,
    fmt: str,
    records: Iterable[Mapping[str, object]],
    *,
    headers: Sequence[str] | None = None,
    sheet_name: str = "Sheet1",
) -> None:
    resolved_records = [dict(record) for record in records]
    resolved_headers = list(headers) if headers is not None else []
    if not resolved_headers and resolved_records:
        resolved_headers = [str(header or "") for header in resolved_records[0].keys()]

    rows = []
    for record in resolved_records:
        rows.append([record.get(header, "") for header in resolved_headers])

    write_table_export(path, fmt, resolved_headers, rows, sheet_name=sheet_name)