"""Public data portal listing tab."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional, Tuple

from classes.data_portal.util.public_output_paths import (
    find_latest_matching_file,
    get_public_data_portal_root_dir,
)
from classes.ui.utilities.listing_support import ListingColumn
from classes.ui.utilities.listing_table import ListingTabBase

LOGGER = logging.getLogger(__name__)


class PublicDataPortalListingTab(ListingTabBase):
    title_text = "📋 公開データポータル 検索結果一覧"
    empty_state_message = "公開データポータルの検索結果JSONが見つかりません"
    columns = (
        ListingColumn("code", "code", width=90, preview_limit=64),
        ListingColumn("title", "タイトル", width=320, preview_limit=180),
        ListingColumn("url", "URL", width=520, preview_limit=220),
        ListingColumn("key", "key", width=180, preview_limit=120),
    )

    def __init__(self, parent=None, *, environment: str = "production"):
        self.environment = str(environment or "production").strip() or "production"
        super().__init__(parent)

    def set_environment(self, environment: str) -> None:
        env = str(environment or "production").strip() or "production"
        if env == getattr(self, "environment", "production"):
            return
        self.environment = env
        self.refresh_from_disk()

    def load_records_from_disk(self) -> Tuple[Iterable[dict], Optional[Path]]:
        base_dir = get_public_data_portal_root_dir(getattr(self, "environment", "production"))
        latest_file = find_latest_matching_file(
            base_dir,
            (
                "output.json",
                "public_arim_data_details_*.json",
                "public_arim_data_*.json",
                "public_arim_data*.json",
            ),
        )
        if not latest_file:
            LOGGER.info("public portal listing: JSON file not found under %s", base_dir)
            return [], None

        try:
            with latest_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"JSON解析に失敗しました: {latest_file}") from exc
        except OSError as exc:
            raise RuntimeError(f"JSONを読み込めません: {latest_file}") from exc

        records = self._normalize_records(payload)
        return records, latest_file

    @staticmethod
    def _normalize_records(payload: object) -> Iterable[dict]:
        if isinstance(payload, list):
            return [PublicDataPortalListingTab._normalize_record(r) for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("data")
            if isinstance(items, list):
                return [PublicDataPortalListingTab._normalize_record(r) for r in items if isinstance(r, dict)]
        return []

    @staticmethod
    def _normalize_record(record: dict) -> dict:
        # detail取得データは detail_url を持つため、Listing互換の url キーへ補完
        if "url" not in record and "detail_url" in record:
            record = dict(record)
            record["url"] = record.get("detail_url")
        return record
