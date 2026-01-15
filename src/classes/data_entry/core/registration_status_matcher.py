from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional


_UTC = timezone.utc


def _parse_iso8601(dt_str: str) -> Optional[datetime]:
    """Parse ISO-8601 datetime commonly used by RDE APIs.

    Accepts strings like:
    - 2026-01-14T12:34:56Z
    - 2026-01-14T12:34:56+09:00
    """

    if not dt_str:
        return None

    value = str(dt_str).strip()
    if not value:
        return None

    # datetime.fromisoformat() doesn't accept trailing 'Z' in some versions
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None

    if parsed.tzinfo is None:
        # Treat as UTC if timezone is missing
        parsed = parsed.replace(tzinfo=_UTC)

    return parsed.astimezone(_UTC)


@dataclass(frozen=True)
class RegistrationStatusMatch:
    state: str
    reason: str
    entry: Optional[Dict[str, Any]] = None


def find_registration_status_match(
    entries: Iterable[Dict[str, Any]],
    *,
    data_name: str,
    dataset_name: Optional[str],
    near_time_utc: datetime,
    window: timedelta = timedelta(minutes=20),
) -> RegistrationStatusMatch:
    """Find a likely matching registration status entry from the latest list.

    Criteria (per requirement):
    - startTime is close to near_time_utc
    - dataName matches
    - datasetName matches (when provided)
    - status is not failed => treat as "likely_success"
    """

    target_data_name = (data_name or "").strip()
    target_dataset_name = (dataset_name or "").strip() if dataset_name else ""

    if near_time_utc.tzinfo is None:
        near_time_utc = near_time_utc.replace(tzinfo=_UTC)
    near_time_utc = near_time_utc.astimezone(_UTC)

    best: Optional[Dict[str, Any]] = None
    best_diff: Optional[timedelta] = None

    for e in entries or []:
        if not isinstance(e, dict):
            continue
        if (str(e.get("dataName") or "").strip() != target_data_name) or not target_data_name:
            continue
        if target_dataset_name:
            if str(e.get("datasetName") or "").strip() != target_dataset_name:
                continue

        start_time = _parse_iso8601(str(e.get("startTime") or ""))
        if not start_time:
            continue

        diff = abs(start_time - near_time_utc)
        if diff > window:
            continue

        if best_diff is None or diff < best_diff:
            best = e
            best_diff = diff

    if not best:
        return RegistrationStatusMatch(
            state="unknown",
            reason="no_match_in_latest",
            entry=None,
        )

    status = str(best.get("status") or "").strip().lower()
    if status == "failed":
        return RegistrationStatusMatch(
            state="failed",
            reason="matched_but_failed",
            entry=best,
        )

    # Requirement says "status が failed でない場合、登録は成功".
    return RegistrationStatusMatch(
        state="likely_success",
        reason="matched_and_not_failed",
        entry=best,
    )
