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


def _load_cached_files_payload(entry_id: str) -> Optional[Dict[str, Any]]:
    """Load cached /data/{id}/files JSON when available.

    Some environments do not expose NONSHARED_RAW in /data?include=files response.
    When present, prefer the cached dataFiles payload to compute accurate stats.
    """

    if not entry_id:
        return None

    candidates = (
        f"output/rde/data/dataFiles/{entry_id}.json",
        f"output/rde/data/dataFiles/sub/{entry_id}.json",
    )
    for rel_path in candidates:
        try:
            path = get_dynamic_file_path(rel_path)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                return payload
        except Exception:
            continue

    return None


def _is_file_like_resource(item: Any) -> bool:
    if not isinstance(item, dict):
        return False

    resource_type = item.get("type")
    if resource_type in {"file", "dataFile"}:
        return True

    attributes = item.get("attributes")
    if not isinstance(attributes, dict):
        return False

    # Some API responses may use a different `type` for file resources.
    # Treat resources as files when they carry file attributes.
    return any(key in attributes for key in ("fileType", "fileSize", "fileName", "mediaType"))


def build_file_lookup(included: Any) -> Dict[str, Dict[str, Any]]:
    """Build {file_id: file_resource} mapping from a JSON:API included list."""

    if not isinstance(included, list):
        return {}

    lookup: Dict[str, Dict[str, Any]] = {}
    for item in included:
        if not _is_file_like_resource(item):
            continue
        file_id = item.get("id")
        if not file_id:
            continue
        lookup[str(file_id)] = item
    return lookup


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
    file_lookup = build_file_lookup(payload.get("included", []))

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


def compute_entry_file_stats(entry: Dict[str, Any], file_lookup: Dict[str, Any]) -> Dict[str, Any]:
    """Compute fileType counts/sizes for a single entry.

    Prefer cached /data/{id}/files payload when available because the
    /data?include=files response may omit some file types from relationships.
    """

    counts = {ft: 0 for ft in DISPLAY_FILE_TYPES}
    sizes = {ft: 0 for ft in DISPLAY_FILE_TYPES}
    image_bytes = 0

    cached_files_payload = _load_cached_files_payload(str(entry.get("id", "")))
    if cached_files_payload:
        for item in cached_files_payload.get("data", []):
            if not _is_file_like_resource(item):
                continue
            attributes = item.get("attributes", {})
            if not isinstance(attributes, dict):
                continue
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

    rel_files = entry.get("relationships", {}).get("files", {}).get("data", [])
    if isinstance(rel_files, list):
        for rel in rel_files:
            if not isinstance(rel, dict):
                continue
            file_id = rel.get("id")
            if not file_id:
                continue
            file_id = str(file_id)
            if file_id not in file_lookup:
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


def _analyze_entry(entry: Dict[str, Any], file_lookup: Dict[str, Any]) -> Dict[str, Any]:
    return compute_entry_file_stats(entry, file_lookup)


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
