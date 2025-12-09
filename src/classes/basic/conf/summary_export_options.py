from __future__ import annotations

"""Export options for the summary.xlsx generator."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class SummaryExportMode(str, Enum):
    """Available output strategies for the summary workbook."""

    MERGED = "merged"
    PER_FILE = "per_file"
    CUSTOM_SELECTION = "custom_selection"


@dataclass
class SummaryExportOptions:
    """Carries the user-selected summary export configuration."""

    mode: SummaryExportMode = SummaryExportMode.MERGED
    selected_group_ids: List[str] = field(default_factory=list)
    custom_suffix: Optional[str] = None
    project_files: List[str] = field(default_factory=list)
    extra_project_files: List[str] = field(default_factory=list)

    def requires_group_selection(self) -> bool:
        return self.mode == SummaryExportMode.CUSTOM_SELECTION

    def to_payload(self) -> Dict[str, Any]:
        """Serialize to a plain dict so ProgressWorker can pass it across threads."""

        return {
            "mode": self.mode.value,
            "selected_group_ids": list(self.selected_group_ids),
            "custom_suffix": self.custom_suffix,
            "project_files": list(self.project_files),
            "extra_project_files": list(self.extra_project_files),
        }

    @classmethod
    def from_payload(cls, payload: Optional[Dict[str, Any]]) -> "SummaryExportOptions":
        if not payload:
            return cls()
        mode_value = payload.get("mode", SummaryExportMode.MERGED.value)
        try:
            mode = SummaryExportMode(mode_value)
        except ValueError:
            mode = SummaryExportMode.MERGED
        selected_ids = payload.get("selected_group_ids") or []
        if isinstance(selected_ids, str):
            selected_ids = [selected_ids]
        project_files = payload.get("project_files") or []
        extra_files = payload.get("extra_project_files") or []
        if isinstance(extra_files, str):
            extra_files = [extra_files]
        if isinstance(project_files, str):
            project_files = [project_files]
        return cls(
            mode=mode,
            selected_group_ids=list(selected_ids),
            custom_suffix=payload.get("custom_suffix"),
            project_files=list(project_files),
            extra_project_files=list(extra_files),
        )

    @staticmethod
    def sanitize_suffix(value: Optional[str]) -> Optional[str]:
        """Return a filesystem-friendly suffix or ``None``."""

        if not value:
            return None
        # Allow ASCII letters, numbers, hyphen and underscore only
        import re

        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", value).strip("_")
        return cleaned or None

    def with_sanitized_suffix(self) -> "SummaryExportOptions":
        return SummaryExportOptions(
            mode=self.mode,
            selected_group_ids=list(self.selected_group_ids),
            custom_suffix=self.sanitize_suffix(self.custom_suffix),
            project_files=list(self.project_files),
            extra_project_files=list(self.extra_project_files),
        )

    def ensure_valid_selection(self, available_ids: Iterable[str]) -> "SummaryExportOptions":
        """Filter the stored selection so it only contains known group IDs."""

        if not self.requires_group_selection():
            return self
        available_set = set(available_ids)
        filtered = [gid for gid in self.selected_group_ids if gid in available_set]
        return SummaryExportOptions(
            mode=self.mode,
            selected_group_ids=filtered,
            custom_suffix=self.custom_suffix,
            project_files=list(self.project_files),
            extra_project_files=list(self.extra_project_files),
        )
