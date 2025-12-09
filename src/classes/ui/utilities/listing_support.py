"""Listing table support utilities.

Provide column metadata definitions and helpers to format
values for display inside filterable listing tables.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Tuple

DEFAULT_PREVIEW_LIMIT = 120


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return value.decode(errors="ignore")
    return str(value)


def _flatten_sequence(sequence: Sequence[Any]) -> str:
    parts = []
    for item in sequence:
        text = format_raw_value(item)
        if text:
            parts.append(text)
    return ", ".join(parts)


def format_raw_value(value: Any) -> str:
    """Convert arbitrary value into a normalized string."""
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        if stripped[0] in "[{" and stripped[-1] in "]}" :
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, (list, dict)):
                    return format_raw_value(parsed)
            except json.JSONDecodeError:
                pass
        return stripped
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return _flatten_sequence(value)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = format_raw_value(item)
            if text:
                parts.append(f"{key}: {text}")
        return ", ".join(parts)
    return _stringify(value)


def truncate_value(value: str, limit: int) -> Tuple[str, str]:
    """Return (display_text, full_text) applying ellipsis when necessary."""
    if limit <= 0 or len(value) <= limit:
        return value, value
    trimmed = value[: max(limit - 3, 0)] + "..."
    return trimmed, value


@dataclass(frozen=True)
class ListingColumn:
    """Column definition for listing tables."""

    key: str
    label: str
    width: int | None = None
    preview_limit: int = DEFAULT_PREVIEW_LIMIT


def prepare_display_value(value: Any, limit: int | None = None) -> Tuple[str, str]:
    """Format arbitrary value for table display."""
    raw_text = format_raw_value(value)
    if not raw_text:
        return "", ""
    preview_limit = DEFAULT_PREVIEW_LIMIT if limit is None else limit
    return truncate_value(raw_text, preview_limit)
