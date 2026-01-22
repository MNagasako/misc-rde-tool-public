from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.common import ensure_directory_exists, get_dynamic_file_path


@dataclass(frozen=True)
class ManagedCsvInfo:
    path: Path
    mtime: float
    size_bytes: int


def get_managed_csv_dir() -> Path:
    path = Path(get_dynamic_file_path("output/data_portal_managed_csv"))
    ensure_directory_exists(str(path))
    return path


def build_managed_csv_path(environment: str, *, now: datetime | None = None) -> Path:
    env = (environment or "production").strip() or "production"
    ts = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return get_managed_csv_dir() / f"theme_list_{env}_{ts}.csv"


def find_latest_managed_csv(environment: str) -> ManagedCsvInfo | None:
    env = (environment or "production").strip() or "production"
    base = get_managed_csv_dir()

    candidates = list(base.glob(f"theme_list_{env}_*.csv"))
    if not candidates:
        return None

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    stat = latest.stat()
    return ManagedCsvInfo(path=latest, mtime=stat.st_mtime, size_bytes=stat.st_size)


def format_size(size_bytes: int) -> str:
    size = float(max(0, int(size_bytes)))
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(size_bytes)} B"


def format_mtime_jst(mtime: float) -> str:
    dt = datetime.fromtimestamp(mtime, tz=ZoneInfo("Asia/Tokyo"))
    return dt.strftime("%Y-%m-%d %H:%M:%S JST")
