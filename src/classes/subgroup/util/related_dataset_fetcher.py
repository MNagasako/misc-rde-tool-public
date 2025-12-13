"""Helpers for resolving datasets linked to a subgroup.

This module keeps the dataset.json parsing logic in one place so UI layers
can focus on presentation only.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, Iterable, List, Optional

from config.common import DATASET_JSON_PATH

logger = logging.getLogger(__name__)

RelatedDataset = Dict[str, str]


class RelatedDatasetFetcher:
    """Loads cached dataset metadata and filters by grant numbers."""

    def __init__(self, dataset_json_path: Optional[str] = None) -> None:
        self.dataset_json_path = dataset_json_path or DATASET_JSON_PATH
        self._cached_entries: List[Dict] = []
        self._cached_mtime: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_related_datasets(self, grant_numbers: Iterable[str]) -> List[RelatedDataset]:
        """Return datasets whose grantNumber is included in *grant_numbers*."""

        normalized = {
            grant.strip()
            for grant in grant_numbers
            if isinstance(grant, str) and grant.strip()
        }
        if not normalized:
            return []

        entries = self._load_entries()
        related: List[RelatedDataset] = []
        for dataset in entries:
            if not isinstance(dataset, dict):
                continue
            attrs = dataset.get("attributes", {})
            if not isinstance(attrs, dict):
                continue
            grant_number = attrs.get("grantNumber", "")
            if grant_number in normalized:
                related.append(
                    {
                        "id": dataset.get("id", ""),
                        "name": attrs.get("name", ""),
                        "grant_number": grant_number,
                        "subject_title": attrs.get("subjectTitle", ""),
                        "dataset_type": attrs.get("datasetType", ""),
                    }
                )

        related.sort(key=lambda item: (item["grant_number"], item["name"]))
        return related

    def clear_cache(self) -> None:
        """Drop the cached dataset list (used by tests)."""

        self._cached_entries = []
        self._cached_mtime = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_entries(self) -> List[Dict]:
        path = self.dataset_json_path
        if not path:
            logger.debug("dataset_json_path is not configured")
            return []

        if not os.path.exists(path):
            logger.debug("dataset.json が見つかりません: %s", path)
            self._cached_entries = []
            self._cached_mtime = None
            return []

        try:
            current_mtime = os.path.getmtime(path)
        except OSError as exc:
            logger.debug("dataset.json の更新時刻取得に失敗: %s", exc)
            current_mtime = None

        if self._cached_mtime is not None and current_mtime == self._cached_mtime:
            return self._cached_entries

        try:
            with open(path, "r", encoding="utf-8") as fp:
                raw_data = json.load(fp)
        except Exception as exc:
            logger.error("dataset.json の読み込みに失敗: %s", exc)
            self._cached_entries = []
            self._cached_mtime = current_mtime
            return []

        if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), list):
            entries = raw_data["data"]
        elif isinstance(raw_data, list):
            entries = raw_data
        else:
            entries = []

        if not isinstance(entries, list):
            entries = []

        self._cached_entries = entries
        self._cached_mtime = current_mtime
        logger.debug("dataset.json を再読込: %s件", len(entries))
        return entries
