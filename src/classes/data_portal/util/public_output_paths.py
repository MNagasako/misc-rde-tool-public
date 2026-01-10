"""Output path helpers for public (no-login) ARIM Data Portal scraping."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from config.common import get_dynamic_file_path


def get_public_data_portal_root_dir() -> Path:
    """Return output root for public data portal exports."""
    root = Path(get_dynamic_file_path("output/data_portal_public"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_public_data_portal_cache_dir() -> Path:
    """Return cache directory for public data portal scraping."""
    cache_dir = get_public_data_portal_root_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def find_latest_matching_file(base_dir: Path, patterns: Iterable[str]) -> Optional[Path]:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(base_dir.glob(pattern))

    if not candidates:
        return None

    def safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return max(candidates, key=safe_mtime)
