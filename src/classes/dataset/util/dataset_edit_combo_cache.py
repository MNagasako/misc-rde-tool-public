from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config.common import ensure_directory_exists, get_dynamic_file_path


_CACHE_REL_PATH = "output/rde/cache/dataset_edit_combo_cache.json"
_CACHE_VERSION = 1


def _cache_path() -> str:
    return get_dynamic_file_path(_CACHE_REL_PATH)


def _file_signature(relative_path: str) -> Dict[str, Any]:
    path = get_dynamic_file_path(relative_path)
    mtime = None
    size = 0
    try:
        if path and os.path.exists(path):
            stat = os.stat(path)
            mtime = float(stat.st_mtime)
            size = int(stat.st_size)
    except Exception:
        mtime = None
        size = 0
    return {
        "path": relative_path,
        "mtime": mtime,
        "size": size,
    }


def build_default_dataset_edit_combo_signature() -> Dict[str, Any]:
    return {
        "version": _CACHE_VERSION,
        "dataset": _file_signature("output/rde/data/dataset.json"),
        "self": _file_signature("output/rde/data/self.json"),
        "subgroup": _file_signature("output/rde/data/subGroup.json"),
    }


def load_default_dataset_edit_combo_cache(signature: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    path = _cache_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    expected_signature = signature if signature is not None else build_default_dataset_edit_combo_signature()
    if payload.get("signature") != expected_signature:
        return None

    combo_payload = payload.get("default_combo")
    if not isinstance(combo_payload, dict):
        return None

    datasets = combo_payload.get("datasets")
    display_names = combo_payload.get("display_names")
    if not isinstance(datasets, list) or not isinstance(display_names, list):
        return None
    if len(datasets) != len(display_names):
        return None

    return combo_payload


def save_default_dataset_edit_combo_cache(
    datasets: list[dict],
    display_names: list[str],
    *,
    signature: Optional[Dict[str, Any]] = None,
) -> None:
    path = _cache_path()
    if not path:
        return

    tmp_path = f"{path}.tmp"
    try:
        ensure_directory_exists(os.path.dirname(path))
        payload = {
            "version": _CACHE_VERSION,
            "created_at": time.time(),
            "signature": signature if signature is not None else build_default_dataset_edit_combo_signature(),
            "default_combo": {
                "datasets": datasets or [],
                "display_names": display_names or [],
            },
        }
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def clear_dataset_edit_combo_cache_storage() -> None:
    path = _cache_path()
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        return


def get_dataset_edit_combo_cache_metadata() -> Dict[str, Any]:
    path = _cache_path()
    meta: Dict[str, Any] = {
        "paths": [path] if path else [],
        "created_at": None,
        "updated_at": None,
        "size_bytes": 0,
        "item_count": 0,
        "active": False,
    }
    if not path or not os.path.exists(path):
        return meta

    try:
        stat = os.stat(path)
        meta["size_bytes"] = int(stat.st_size)
        meta["updated_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        meta["active"] = True
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            created_at = payload.get("created_at")
            try:
                if created_at is not None:
                    meta["created_at"] = datetime.fromtimestamp(float(created_at), tz=timezone.utc)
            except Exception:
                pass
            combo_payload = payload.get("default_combo")
            if isinstance(combo_payload, dict):
                display_names = combo_payload.get("display_names")
                datasets = combo_payload.get("datasets")
                if isinstance(display_names, list):
                    meta["item_count"] = len(display_names)
                elif isinstance(datasets, list):
                    meta["item_count"] = len(datasets)
    except Exception:
        return meta

    return meta