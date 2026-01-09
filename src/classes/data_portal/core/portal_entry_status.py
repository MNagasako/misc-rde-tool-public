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
            path = _persisted_cache_path()
            try:
                if not path or not os.path.exists(path):
                    self._loaded = True
                    return
                with open(path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                if not isinstance(payload, dict) or int(payload.get("version", 0) or 0) != _CACHE_VERSION:
                    self._loaded = True
                    return
                items = payload.get("items")
                if isinstance(items, dict):
                    self._items = items
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
        path = _persisted_cache_path()
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {
                "version": _CACHE_VERSION,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "saved_at": time.time(),
                "items": self._items,
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
        except Exception as exc:
            logger.debug(f"portal entry status cache save skipped: {exc}")


_CACHE_SINGLETON: Optional[PortalEntryStatusCache] = None


def get_portal_entry_status_cache() -> PortalEntryStatusCache:
    global _CACHE_SINGLETON
    if _CACHE_SINGLETON is None:
        _CACHE_SINGLETON = PortalEntryStatusCache()
    return _CACHE_SINGLETON
