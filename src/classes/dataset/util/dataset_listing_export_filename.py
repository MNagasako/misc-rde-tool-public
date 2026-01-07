from __future__ import annotations

import datetime
from typing import Optional


def build_dataset_listing_export_default_filename(fmt: str, now: Optional[datetime.datetime] = None) -> str:
    """Build default export filename for Dataset listing.

    This helper is intentionally UI/Qt-free so it can be unit-tested without
    importing `DatasetListingWidget` (which pulls in PySide6/theme init).
    """
    if fmt not in {"csv", "xlsx"}:
        return ""

    dt = now or datetime.datetime.now()
    ts = dt.strftime("%Y%m%d_%H%M%S")
    ext = "csv" if fmt == "csv" else "xlsx"
    return f"dataset_list_{ts}.{ext}"
