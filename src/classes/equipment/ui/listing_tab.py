"""Equipment listing tab."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional, Tuple

from classes.equipment.util.output_paths import (
    find_latest_matching_file,
    get_equipment_root_dir,
)
from classes.ui.utilities.listing_support import ListingColumn
from classes.ui.utilities.listing_table import ListingTabBase

LOGGER = logging.getLogger(__name__)


class EquipmentListingTab(ListingTabBase):
    """Tab showing the latest exported facility records."""

    title_text = "📋 最新設備データ一覧"
    empty_state_message = "設備データのJSON出力がまだありません"
    columns = (
        ListingColumn("code", "コード", width=80, preview_limit=32),
        ListingColumn("装置名_日", "装置名 (日)", width=220, preview_limit=120),
        ListingColumn("装置名_英", "装置名 (英)", width=220, preview_limit=120),
        ListingColumn("設置機関", "設置機関", width=220, preview_limit=160),
        ListingColumn("設置場所", "設置場所", width=200, preview_limit=140),
        ListingColumn("メーカー名", "メーカー", width=160, preview_limit=120),
        ListingColumn("キーワード", "キーワード", width=260, preview_limit=180),
        ListingColumn("仕様・特徴", "仕様・特徴", width=320, preview_limit=240),
    )

    def load_records_from_disk(self) -> Tuple[Iterable[dict], Optional[Path]]:
        base_dir = get_equipment_root_dir()
        latest_file = find_latest_matching_file(
            base_dir,
            ("facilities_*.json", "facilities.json", "facilities_full.json"),
        )
        if not latest_file:
            LOGGER.info("equipment listing: JSON file not found under %s", base_dir)
            return [], None

        try:
            with latest_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"JSON解析に失敗しました: {latest_file}") from exc
        except OSError as exc:
            raise RuntimeError(f"JSONを読み込めません: {latest_file}") from exc

        records = self._extract_records(payload)
        return records, latest_file

    @staticmethod
    def _extract_records(payload: object) -> Iterable[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            facilities = payload.get("facilities") or payload.get("data")
            if isinstance(facilities, list):
                return facilities
        return []
