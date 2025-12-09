"""Report listing tab implementation."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional, Tuple

from classes.reports.util.output_paths import (
    find_latest_matching_file,
    get_reports_root_dir,
)
from classes.ui.utilities.listing_support import ListingColumn
from classes.ui.utilities.listing_table import ListingTabBase

LOGGER = logging.getLogger(__name__)


class ReportListingTab(ListingTabBase):
    """Tab that renders the latest exported report records."""

    title_text = "📋 報告書データ一覧"
    empty_state_message = "報告書データのJSON出力が見つかりません"
    columns = (
        ListingColumn("課題番号 / Project Issue Number", "課題番号", width=160, preview_limit=64),
        ListingColumn("利用課題名 / Title", "利用課題名", width=260, preview_limit=160),
        ListingColumn("利用した実施機関 / Support Institute", "実施機関", width=200, preview_limit=140),
        ListingColumn("利用者名（課題申請者）/ User Name (Project Applicant)", "利用者", width=180, preview_limit=120),
        ListingColumn("所属名 / Affiliation", "所属", width=220, preview_limit=140),
        ListingColumn("利用した主な設備 / Equipment Used in This Project", "利用設備", width=260, preview_limit=200),
        ListingColumn("概要（目的・用途・実施内容）/ Abstract (Aim, Use Applications and Contents)", "概要", width=320, preview_limit=220),
        ListingColumn("結果と考察 / Results and Discussion", "結果と考察", width=320, preview_limit=220),
    )

    def load_records_from_disk(self) -> Tuple[Iterable[dict], Optional[Path]]:
        base_dir = get_reports_root_dir()
        latest_file = find_latest_matching_file(
            base_dir,
            (
                "output.json",
                "output_*.json",
                "reports_*.json",
                "ARIM-extracted2_*.json",
            ),
        )
        if not latest_file:
            LOGGER.info("report listing: JSON file not found under %s", base_dir)
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
            return payload
        if isinstance(payload, dict):
            reports = payload.get("reports") or payload.get("data")
            if isinstance(reports, list):
                return reports
        return []
