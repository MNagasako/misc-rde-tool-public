"""Remote existence checks and local pruning helpers.

Purpose:
- Prevent stale local JSON entries (dataset/subgroup) from being offered in combo boxes
  when the resource was deleted on the RDE side.
- Only prune when the remote side definitively reports missing (404/410).
- Never fall back to black/unintended UI colors (handled elsewhere); this module is
  data-layer validation.

Notes:
- All HTTP requests must go through net.http_helpers.
- All file paths must be resolved via config.common.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from config.common import get_dynamic_file_path
from config.common import ensure_directory_exists
from net.http_helpers import proxy_get

logger = logging.getLogger(__name__)


ResourceType = Literal["dataset", "group"]


_CACHE_REL_PATH = "output/rde/cache/remote_missing_ids.json"


def _cache_path() -> str:
    return get_dynamic_file_path(_CACHE_REL_PATH)


def _load_cache() -> dict:
    path = _cache_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    path = _cache_path()
    try:
        import os

        ensure_directory_exists(os.path.dirname(path))
    except Exception:
        pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_set(data: dict, key: str) -> set[str]:
    raw = data.get(key, [])
    if isinstance(raw, list):
        return {str(x) for x in raw if x}
    if isinstance(raw, set):
        return {str(x) for x in raw if x}
    return set()


def is_marked_missing(resource_type: ResourceType, resource_id: str) -> bool:
    if not resource_id:
        return False
    data = _load_cache()
    key = "datasets" if resource_type == "dataset" else "groups"
    return resource_id in _get_set(data, key)


def mark_missing(resource_type: ResourceType, resource_id: str) -> None:
    if not resource_id:
        return
    data = _load_cache()
    key = "datasets" if resource_type == "dataset" else "groups"
    ids = _get_set(data, key)
    if resource_id in ids:
        return
    ids.add(resource_id)
    data[key] = sorted(ids)
    data["updated_at"] = int(time.time())
    try:
        _save_cache(data)
    except Exception:
        # Fail-safe: do not block UI/data loading.
        return


def clear_marked_missing(
    resource_type: Optional[ResourceType] = None,
    *,
    include_existence_cache: bool = True,
) -> None:
    """Clear persisted missing-id cache and optional existence TTL cache."""

    if resource_type is None:
        try:
            path = _cache_path()
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    else:
        data = _load_cache()
        key = "datasets" if resource_type == "dataset" else "groups"
        data.pop(key, None)
        data["updated_at"] = int(time.time())
        try:
            _save_cache(data)
        except Exception:
            pass

    if include_existence_cache:
        _existence_cache.clear()


def get_missing_cache_metadata() -> dict[str, object]:
    """Return metadata for persisted missing-id cache and TTL existence cache."""

    data = _load_cache()
    datasets = _get_set(data, "datasets")
    groups = _get_set(data, "groups")
    path = _cache_path()
    size_bytes = 0
    updated_at = None
    try:
        if path and os.path.exists(path):
            stat = os.stat(path)
            size_bytes = int(stat.st_size)
            updated_at = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc)
    except Exception:
        pass
    return {
        "path": path,
        "item_count": len(datasets) + len(groups),
        "dataset_count": len(datasets),
        "group_count": len(groups),
        "ttl_memory_count": len(_existence_cache),
        "size_bytes": size_bytes,
        "updated_at": updated_at,
        "active": bool(datasets or groups or _existence_cache),
    }


@dataclass(frozen=True)
class RemoteCheckResult:
    exists: Optional[bool]
    status_code: int | None = None


# ---------------------------------------------------------------------------
# TTL existence cache (shared across check_group_exists / check_dataset_exists)
# ---------------------------------------------------------------------------
_EXISTENCE_TTL_SEC: float = 30 * 60  # 30 min
_existence_cache: dict[str, tuple[float, bool]] = {}
# key: resource_id, value: (timestamp, exists)


def record_existence(resource_id: str, exists: bool) -> None:
    """外部 (Basic Info 等) から存在確認結果をキャッシュに登録する。"""
    _existence_cache[resource_id] = (time.time(), exists)


def invalidate_existence(resource_id: str) -> None:
    """特定リソースの存在キャッシュを破棄する。"""
    _existence_cache.pop(resource_id, None)


def _get_cached_existence(resource_id: str) -> Optional[bool]:
    """TTL 内であればキャッシュ済みの存在結果を返す。期限切れなら None。"""
    entry = _existence_cache.get(resource_id)
    if entry is None:
        return None
    ts, exists = entry
    if (time.time() - ts) > _EXISTENCE_TTL_SEC:
        del _existence_cache[resource_id]
        return None
    return exists


def check_dataset_exists(dataset_id: str, *, timeout: float = 3.0) -> RemoteCheckResult:
    """Return whether dataset exists on RDE API.

    - exists=True  : confirmed 2xx
    - exists=False : confirmed missing (404/410)
    - exists=None  : unknown (network/auth/other)
    """

    if not dataset_id:
        return RemoteCheckResult(exists=None, status_code=None)

    cached = _get_cached_existence(dataset_id)
    if cached is not None:
        logger.debug("dataset存在チェック: キャッシュヒット id=%s exists=%s", dataset_id[:20], cached)
        return RemoteCheckResult(exists=cached, status_code=200 if cached else 404)

    url = f"https://rde-api.nims.go.jp/datasets/{dataset_id}"
    try:
        resp = proxy_get(url, headers={"Accept": "application/vnd.api+json"}, timeout=timeout)
        status = int(getattr(resp, "status_code", 0) or 0)
        if status in (404, 410):
            mark_missing("dataset", dataset_id)
            record_existence(dataset_id, False)
            return RemoteCheckResult(exists=False, status_code=status)
        if 200 <= status < 300:
            record_existence(dataset_id, True)
            return RemoteCheckResult(exists=True, status_code=status)
        if status in (401, 403):
            return RemoteCheckResult(exists=None, status_code=status)
        return RemoteCheckResult(exists=None, status_code=status)
    except Exception:
        return RemoteCheckResult(exists=None, status_code=None)


def check_group_exists(group_id: str, *, timeout: float = 3.0) -> RemoteCheckResult:
    if not group_id:
        return RemoteCheckResult(exists=None, status_code=None)

    cached = _get_cached_existence(group_id)
    if cached is not None:
        logger.debug("group存在チェック: キャッシュヒット id=%s exists=%s", group_id[:20], cached)
        return RemoteCheckResult(exists=cached, status_code=200 if cached else 404)

    url = f"https://rde-api.nims.go.jp/groups/{group_id}"
    try:
        resp = proxy_get(url, headers={"Accept": "application/vnd.api+json"}, timeout=timeout)
        status = int(getattr(resp, "status_code", 0) or 0)
        if status in (404, 410):
            mark_missing("group", group_id)
            record_existence(group_id, False)
            return RemoteCheckResult(exists=False, status_code=status)
        if 200 <= status < 300:
            record_existence(group_id, True)
            return RemoteCheckResult(exists=True, status_code=status)
        if status in (401, 403):
            return RemoteCheckResult(exists=None, status_code=status)
        return RemoteCheckResult(exists=None, status_code=status)
    except Exception:
        return RemoteCheckResult(exists=None, status_code=None)


def filter_out_marked_missing_ids(
    items: Iterable[dict],
    *,
    resource_type: ResourceType,
    id_key: str = "id",
) -> list[dict]:
    """Filter dict items by id_key using the local missing-id registry."""

    key = "datasets" if resource_type == "dataset" else "groups"
    data = _load_cache()
    missing = _get_set(data, key)
    if not missing:
        return [x for x in items if isinstance(x, dict)]

    filtered: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = item.get(id_key)
        if rid and str(rid) in missing:
            continue
        filtered.append(item)
    return filtered
