"""Shared data-entry summary helper.

Provides reusable aggregation logic for dataset data-entry JSON files so that
multiple widgets (dataset data-entry tab, data-portal edit dialog, etc.) can
obtain consistent file count/size statistics.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from config.common import get_dynamic_file_path
from classes.data_fetch2.conf.file_filter_config import FILE_TYPES
from classes.managers.log_manager import get_logger

logger = get_logger("Dataset.DataEntrySummary")

DISPLAY_FILE_TYPES = list(FILE_TYPES)
if "OTHER" not in DISPLAY_FILE_TYPES:
    DISPLAY_FILE_TYPES.append("OTHER")
DISPLAY_FILE_TYPES = tuple(DISPLAY_FILE_TYPES)
IMAGE_FILE_TYPES = {"MAIN_IMAGE", "THUMBNAIL"}


@dataclass(frozen=True)
class Aggregate:
    """Simple container for aggregated counts/bytes."""

    count: int = 0
    bytes: int = 0


def format_size_with_bytes(num_bytes: int) -> str:
    """Return a short human-readable size with byte suffix."""

    if not num_bytes:
        return "0 B"
    size = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]} ({num_bytes:,} B)"


def compute_summary_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compute aggregated summary from a RDE dataEntry payload."""

    if not isinstance(payload, dict):
        return None

    entries = payload.get("data", [])
    included = payload.get("included", [])
    file_lookup = {
        item.get("id"): item
        for item in included
        if isinstance(item, dict) and item.get("type") == "file" and item.get("id")
    }

    summary = _create_empty_summary()

    if not entries:
        return _finalize_summary(summary)

    for entry in entries:
        entry_summary = _analyze_entry(entry, file_lookup)
        _merge_entry_summary(summary, entry, entry_summary)

    return _finalize_summary(summary)


def get_data_entry_summary(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Load dataEntry JSON for dataset_id and compute summary."""

    try:
        path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
        if not os.path.exists(path):
            logger.info("dataEntry file not found: %s", path)
            return None
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return compute_summary_from_payload(payload)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to compute dataEntry summary for %s: %s", dataset_id, exc, exc_info=True)
        return None


def get_shared2_stats(dataset_id: str) -> Optional[Aggregate]:
    """Return the shared2 aggregate (count/bytes) for a dataset."""

    summary = get_data_entry_summary(dataset_id)
    if not summary:
        return None
    shared = summary.get("shared2")
    if not shared:
        return None
    return Aggregate(count=shared.get("count", 0), bytes=shared.get("bytes", 0))


def _create_empty_summary() -> Dict[str, Any]:
    def _empty() -> Dict[str, int]:
        return {"count": 0, "bytes": 0}

    return {
        "files": _empty(),
        "images": _empty(),
        "filetypes": {ft: _empty() for ft in DISPLAY_FILE_TYPES},
        "total": _empty(),
        "shared1": _empty(),
        "shared2": _empty(),
        "shared3": _empty(),
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _classify_file_type(raw_type: str) -> str:
    if raw_type in DISPLAY_FILE_TYPES:
        return raw_type
    return "OTHER"


def _analyze_entry(entry: Dict[str, Any], file_lookup: Dict[str, Any]) -> Dict[str, Any]:
    counts = {ft: 0 for ft in DISPLAY_FILE_TYPES}
    sizes = {ft: 0 for ft in DISPLAY_FILE_TYPES}
    image_bytes = 0

    rel_files = (
        entry.get("relationships", {})
        .get("files", {})
        .get("data", [])
    )
    for rel in rel_files:
        file_id = rel.get("id")
        if not file_id or file_id not in file_lookup:
            continue
        attributes = file_lookup[file_id].get("attributes", {})
        raw_type = attributes.get("fileType", "OTHER")
        classified = _classify_file_type(raw_type)
        size = _safe_int(attributes.get("fileSize", 0))
        counts[classified] += 1
        sizes[classified] += size
        is_image = attributes.get("isImageFile")
        if is_image is None:
            is_image = raw_type in IMAGE_FILE_TYPES
        if is_image:
            image_bytes += size

    return {
        "counts": counts,
        "sizes": sizes,
        "image_bytes": image_bytes,
    }


def _merge_entry_summary(summary: Dict[str, Any], entry: Dict[str, Any], entry_summary: Dict[str, Dict[str, int]]):
    attributes = entry.get("attributes", {})
    summary["files"]["count"] += _safe_int(attributes.get("numberOfFiles"))
    summary["files"]["bytes"] += sum(entry_summary["sizes"].values())
    summary["images"]["count"] += _safe_int(attributes.get("numberOfImageFiles"))
    summary["images"]["bytes"] += entry_summary["image_bytes"]

    for ft in DISPLAY_FILE_TYPES:
        summary["filetypes"][ft]["count"] += entry_summary["counts"][ft]
        summary["filetypes"][ft]["bytes"] += entry_summary["sizes"][ft]


def _finalize_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    total_count = sum(item["count"] for item in summary["filetypes"].values())
    total_bytes = sum(item["bytes"] for item in summary["filetypes"].values())
    summary["total"]["count"] = total_count
    summary["total"]["bytes"] = total_bytes

    shared_sets = {
        "shared1": {"exclude": {"NONSHARED_RAW"}},
        "shared2": {"exclude": {"NONSHARED_RAW", "THUMBNAIL"}},
        "shared3": {"exclude": {"NONSHARED_RAW", "THUMBNAIL", "OTHER"}},
    }

    for key, config in shared_sets.items():
        include = [ft for ft in DISPLAY_FILE_TYPES if ft not in config["exclude"]]
        summary[key]["count"] = sum(summary["filetypes"][ft]["count"] for ft in include)
        summary[key]["bytes"] = sum(summary["filetypes"][ft]["bytes"] for ft in include)

    summary["files"]["bytes"] = total_bytes
    return summary
