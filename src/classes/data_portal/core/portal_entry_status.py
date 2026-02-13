"""Portal entry status parsing + caching.

This module is intentionally UI-agnostic.
- Parses the HTML returned by Data Portal search (main.php mode=theme)
- Derives flags aligned with DatasetUploadTab button enable/disable logic
- Provides a small persisted cache to avoid excessive site access

All file paths must be obtained via config.common.get_dynamic_file_path.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from classes.managers.log_manager import get_logger
from config.common import get_dynamic_file_path

logger = get_logger("DataPortal.PortalEntryStatus")


DEFAULT_ENVIRONMENT = "production"
# Dataset listing portal column should avoid excessive portal access.
# Keep confirmed values for 1 day.
CACHE_TTL_SECONDS = 60 * 60 * 24  # 1 day
_CACHE_VERSION = 1


@dataclass(frozen=True)
class PortalEntryCheckResult:
    dataset_id: str
    dataset_id_found: bool
    can_edit: bool
    can_toggle_status: bool
    can_public_view: bool
    current_status: Optional[str]
    public_code: Optional[str]
    public_key: Optional[str]
    public_url: Optional[str]

    def listing_label(self) -> str:
        """Derive listing label aligned with dataset listing rules.

        - 公開済 -> 公開済 (later normalized to "公開（管理）")
        - 非公開 -> UP済
        - それ以外/不明 -> 未UP
        """

        # If the portal does not allow editing/toggling (no edit link), treat as not-uploaded.
        # This matches the existing button-equivalent parsing expectations.
        if not bool(self.can_edit):
            return "未UP"

        status = str(self.current_status or "").strip()
        if status == "公開済":
            return "公開済"
        if status == "非公開":
            return "UP済"
        return "未UP"


def _persisted_cache_path() -> str:
    return get_dynamic_file_path("output/rde/cache/portal_entry_status_cache.json")


def _durable_cache_path() -> str:
    # output 配下がクリアされても残るように、設定配下にも保存する。
    return get_dynamic_file_path("config/cache/portal_entry_status_cache.json")


def _all_persisted_cache_paths() -> list[str]:
    primary = _persisted_cache_path()
    durable = _durable_cache_path()
    paths: list[str] = []
    for p in (primary, durable):
        ps = str(p or "").strip()
        if not ps:
            continue
        if ps in paths:
            continue
        paths.append(ps)
    return paths


def parse_portal_entry_search_html(
    html: str,
    dataset_id: str,
    environment: Optional[str] = None,
) -> PortalEntryCheckResult:
    """Parse portal search HTML and extract flags/status.

    This mirrors DatasetUploadTab._check_portal_entry_exists parsing logic.

    Args:
        html: HTML text returned by portal main.php search.
        dataset_id: dataset id searched.
        environment: production/test. Used only to build public URL when possible.

    Returns:
        PortalEntryCheckResult
    """

    dsid = str(dataset_id or "").strip()
    text = html or ""

    dataset_id_found = bool(dsid) and (dsid in text)

    can_edit = False
    current_status: Optional[str] = None
    public_code: Optional[str] = None
    public_key: Optional[str] = None
    public_url: Optional[str] = None

    if dataset_id_found:
        try:
            import re

            can_edit = re.search(r"form_change\d+", text) is not None
        except Exception:
            can_edit = False

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")

            status_cell = None
            for td in soup.find_all("td", {"rowspan": "2"}):
                td_text = td.get_text() if td is not None else ""
                if "公開" in td_text or "非公開" in td_text:
                    status_cell = td
                    break

            if status_cell is not None:
                status_text = status_cell.get_text(strip=True)
                if "公開済" in status_text:
                    current_status = "公開済"
                elif "非公開" in status_text:
                    current_status = "非公開"
                else:
                    current_status = None

            # Extract public detail URL params if available.
            try:
                for a in soup.find_all("a", href=True):
                    href = (a.get("href") or "").strip()
                    if "arim_data.php" not in href:
                        continue
                    if "mode=detail" not in href:
                        continue
                    if "code=" not in href or "key=" not in href:
                        continue

                    try:
                        from urllib.parse import parse_qs, urlparse

                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        code = (params.get("code", [""])[0] or "").strip()
                        key = (params.get("key", [""])[0] or "").strip()
                        if not code or not key:
                            continue

                        env = (environment or DEFAULT_ENVIRONMENT) or DEFAULT_ENVIRONMENT
                        try:
                            from classes.utils.data_portal_public import build_public_detail_url

                            public_url = build_public_detail_url(env, code, key)
                        except Exception:
                            public_url = None

                        public_code = code
                        public_key = key
                        break
                    except Exception:
                        continue
            except Exception:
                pass

        except Exception:
            current_status = None

    # DatasetUploadTab only enables the public view button when edit link is available.
    can_public_view = bool(can_edit and public_code and public_key)
    can_toggle_status = bool(can_edit and current_status)

    return PortalEntryCheckResult(
        dataset_id=dsid,
        dataset_id_found=dataset_id_found,
        can_edit=can_edit,
        can_toggle_status=can_toggle_status,
        can_public_view=can_public_view,
        current_status=current_status,
        public_code=public_code,
        public_key=public_key,
        public_url=public_url,
    )


def parse_portal_contents_link_search_html(html: str, dataset_id: str) -> bool:
    """Parse portal search HTML and detect whether contents link exists.

    The data portal (main.php mode=theme) listing includes a "コンテンツ" link when
    content files are present. Operationally, we treat this as "コンテンツZIPアップ済み".

    Args:
        html: HTML text returned by portal main.php search.
        dataset_id: dataset id to locate.

    Returns:
        True if a contents link (arim_data_file.php?mode=free) is found for the dataset.
    """

    dsid = str(dataset_id or "").strip()
    if not dsid:
        return False
    text = html or ""
    if dsid not in text:
        return False

    # Prefer structured parsing.
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "html.parser")
        for td in soup.find_all("td", {"class": "l"}):
            if td is None:
                continue
            if td.get_text(strip=True) != dsid:
                continue

            tr = td.find_parent("tr")
            rows = [tr]
            try:
                if tr is not None:
                    rows.append(tr.find_next_sibling("tr"))
            except Exception:
                pass

            for row in rows:
                if row is None:
                    continue
                for a in row.find_all("a", href=True):
                    href = (a.get("href") or "").strip()
                    if "arim_data_file.php" in href and "mode=free" in href:
                        return True
            return False
    except Exception:
        pass

    # Fallback: local window search around dataset id.
    try:
        idx = text.find(dsid)
        if idx < 0:
            return False
        window = text[idx : idx + 4000]
        return ("arim_data_file.php" in window) and ("mode=free" in window)
    except Exception:
        return False


class PortalEntryStatusCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._items: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _key(environment: str, dataset_id: str) -> str:
        env = str(environment or DEFAULT_ENVIRONMENT).strip() or DEFAULT_ENVIRONMENT
        dsid = str(dataset_id or "").strip()
        return f"{env}:{dsid}"

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            latest_items: Dict[str, Any] = {}
            latest_saved_at = -1.0
            try:
                for path in _all_persisted_cache_paths():
                    if not path or not os.path.exists(path):
                        continue
                    try:
                        with open(path, "r", encoding="utf-8") as fh:
                            payload = json.load(fh)
                    except Exception:
                        continue
                    if not isinstance(payload, dict) or int(payload.get("version", 0) or 0) != _CACHE_VERSION:
                        continue
                    items = payload.get("items")
                    if not isinstance(items, dict):
                        continue
                    try:
                        saved_at = float(payload.get("saved_at") or 0.0)
                    except Exception:
                        saved_at = 0.0
                    if saved_at >= latest_saved_at:
                        latest_saved_at = saved_at
                        latest_items = items
                self._items = latest_items if isinstance(latest_items, dict) else {}
            except Exception:
                self._items = {}
            self._loaded = True

    def get_label(self, dataset_id: str, environment: str = DEFAULT_ENVIRONMENT) -> Optional[str]:
        self._ensure_loaded()
        k = self._key(environment, dataset_id)
        now = time.time()
        with self._lock:
            item = self._items.get(k)
            if not isinstance(item, dict):
                return None
            checked_at = item.get("checked_at")
            try:
                checked_at_f = float(checked_at)
            except Exception:
                checked_at_f = 0.0
            if checked_at_f <= 0.0 or (now - checked_at_f) > CACHE_TTL_SECONDS:
                return None
            label = item.get("label")
            return str(label) if isinstance(label, str) and label.strip() else None

    def get_label_any_age(self, dataset_id: str, environment: str = DEFAULT_ENVIRONMENT) -> Optional[str]:
        """Return cached label regardless of TTL.

        Dataset listing should keep using the last known value until overwritten,
        while TTL is used only for deciding whether to re-check.
        """

        self._ensure_loaded()
        k = self._key(environment, dataset_id)
        with self._lock:
            item = self._items.get(k)
            if not isinstance(item, dict):
                return None
            label = item.get("label")
            return str(label) if isinstance(label, str) and label.strip() else None

    def get_checked_at_any_age(self, dataset_id: str, environment: str = DEFAULT_ENVIRONMENT) -> Optional[float]:
        """Return cached checked_at (epoch seconds) regardless of TTL."""

        self._ensure_loaded()
        k = self._key(environment, dataset_id)
        with self._lock:
            item = self._items.get(k)
            if not isinstance(item, dict):
                return None
            try:
                checked_at_f = float(item.get("checked_at") or 0.0)
            except Exception:
                checked_at_f = 0.0
            return checked_at_f if checked_at_f > 0.0 else None

    def clear(self, environment: Optional[str] = None) -> None:
        """Clear cached items (optionally only for one environment) and persist."""

        self._ensure_loaded()
        env = str(environment or "").strip()
        with self._lock:
            if not env:
                self._items = {}
            else:
                prefix = f"{env}:"
                self._items = {k: v for k, v in self._items.items() if not str(k).startswith(prefix)}
        self._save_best_effort()

    def clear_dataset_ids(self, dataset_ids: set[str] | list[str] | tuple[str, ...], environment: Optional[str] = None) -> None:
        """Remove cached items for specific dataset IDs and persist.

        This is used for partial force refresh scenarios (e.g. "非公開のみ更新").

        Args:
            dataset_ids: dataset IDs to remove.
            environment: when provided, remove only from that environment; otherwise remove across all environments.
        """

        self._ensure_loaded()
        ids = {str(d or "").strip() for d in (dataset_ids or [])}
        ids.discard("")
        if not ids:
            return

        env = str(environment or "").strip()

        with self._lock:
            if env:
                prefix = f"{env}:"
                for dsid in ids:
                    self._items.pop(f"{env}:{dsid}", None)
            else:
                # Remove from any env.
                suffixes = {f":{dsid}" for dsid in ids}
                self._items = {k: v for k, v in self._items.items() if not any(str(k).endswith(sfx) for sfx in suffixes)}

        self._save_best_effort()

    def set_label(self, dataset_id: str, label: str, environment: str = DEFAULT_ENVIRONMENT) -> None:
        self._ensure_loaded()
        k = self._key(environment, dataset_id)
        now = time.time()
        with self._lock:
            self._items[k] = {"label": str(label), "checked_at": now}
        self._save_best_effort()

    def set_labels_bulk(self, labels_by_dataset_id: Dict[str, str], environment: str = DEFAULT_ENVIRONMENT) -> None:
        """Set many labels at once and persist only once.

        This is intended for bulk imports (e.g., CSV download) to keep UI responsive.
        """

        self._ensure_loaded()
        env = str(environment or DEFAULT_ENVIRONMENT).strip() or DEFAULT_ENVIRONMENT
        now = time.time()
        if not isinstance(labels_by_dataset_id, dict) or not labels_by_dataset_id:
            return

        with self._lock:
            for dataset_id, label in labels_by_dataset_id.items():
                dsid = str(dataset_id or "").strip()
                if not dsid:
                    continue
                text = str(label).strip()
                if not text:
                    continue
                k = self._key(env, dsid)
                self._items[k] = {"label": text, "checked_at": now}

        self._save_best_effort()

    def _save_best_effort(self) -> None:
        paths = _all_persisted_cache_paths()
        if not paths:
            return
        try:
            # Snapshot under lock so concurrent writers do not corrupt the persisted file.
            with self._lock:
                items_snapshot = dict(self._items)

            payload = {
                "version": _CACHE_VERSION,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "saved_at": time.time(),
                "items": items_snapshot,
            }

            for path in paths:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)

                    # Atomic write (best-effort) to avoid truncation/corruption on crash.
                    tmp_path = f"{path}.tmp"
                    with open(tmp_path, "w", encoding="utf-8") as fh:
                        json.dump(payload, fh, ensure_ascii=False)
                    try:
                        os.replace(tmp_path, path)
                    except Exception:
                        # Fallback to direct write if atomic replace fails.
                        with open(path, "w", encoding="utf-8") as fh:
                            json.dump(payload, fh, ensure_ascii=False)
                        try:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception as exc:
            logger.debug(f"portal entry status cache save skipped: {exc}")


_CACHE_SINGLETON: Optional[PortalEntryStatusCache] = None


def get_portal_entry_status_cache() -> PortalEntryStatusCache:
    global _CACHE_SINGLETON
    if _CACHE_SINGLETON is None:
        _CACHE_SINGLETON = PortalEntryStatusCache()
    return _CACHE_SINGLETON
