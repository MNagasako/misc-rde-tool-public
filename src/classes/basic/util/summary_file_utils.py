from __future__ import annotations

"""Utilities for locating generated summary.xlsx files."""

from pathlib import Path
from typing import List, Optional


def list_summary_workbooks(output_dir: str, default_file: Optional[str] = None) -> List[Path]:
    """Return all summary.xlsx variants inside ``output_dir``.

    Args:
        output_dir: Directory that contains generated XLSX files.
        default_file: Optional explicit summary file to include even if it
            resides outside ``output_dir``.
    """

    candidates: List[Path] = []
    base_dir = Path(output_dir) if output_dir else None
    if base_dir and base_dir.exists():
        candidates.extend(path for path in base_dir.glob("summary*.xlsx") if path.is_file())

    if default_file:
        default_path = Path(default_file)
        if default_path.exists():
            candidates.append(default_path)

    unique_paths = {path.resolve(): path for path in candidates}
    return sorted(unique_paths.values(), key=lambda path: path.name.lower())
