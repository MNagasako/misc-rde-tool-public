from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional


_UTC = timezone.utc


def parse_entry_start_time(start_time: str | None) -> Optional[datetime]:
    if not start_time:
        return None
    # APIはISO8601想定
    try:
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_UTC)
        return dt.astimezone(_UTC)
    except Exception:
        return None


def select_failed_entries_within_window(
    *,
    entries: Iterable[Dict],
    reference_time: datetime,
    window: timedelta = timedelta(days=1),
) -> List[Dict]:
    """FAILED かつ startTime が [reference_time, reference_time+window] に入るものを抽出。"""
    ref = reference_time.astimezone(_UTC)
    end = ref + window

    selected: List[Dict] = []
    for e in entries:
        status = str(e.get("status") or "").strip().upper()
        if status != "FAILED":
            continue
        start_dt = parse_entry_start_time(e.get("startTime"))
        if start_dt is None:
            continue
        if ref <= start_dt <= end:
            selected.append(e)
    return selected
