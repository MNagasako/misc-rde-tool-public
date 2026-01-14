from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import os
import zipfile


@dataclass(frozen=True)
class SelectedFile:
    file_id: str
    file_name: str
    file_type: str
    file_size: int
    local_path: str


def filter_file_entries_excluding_nonshared_raw(file_entries: Iterable[dict]) -> List[dict]:
    """RDE /data/{id}/files の data 配列を想定し、NONSHARED_RAW を除外する。"""
    filtered: List[dict] = []
    for entry in file_entries or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "file":
            continue
        attrs = entry.get("attributes") or {}
        if (attrs.get("fileType") or "") == "NONSHARED_RAW":
            continue
        filtered.append(entry)
    return filtered


def compute_filetype_summary(files: Iterable[SelectedFile]) -> Dict[str, Tuple[int, int]]:
    """file_type -> (count, total_size_bytes)"""
    summary: Dict[str, Tuple[int, int]] = {}
    for f in files or []:
        count, total = summary.get(f.file_type, (0, 0))
        summary[f.file_type] = (count + 1, total + int(f.file_size or 0))
    return summary


def format_bytes(num_bytes: int) -> str:
    size = float(max(0, int(num_bytes or 0)))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(num_bytes)} B"


def build_zip(
    zip_path: str,
    base_dir: str,
    files: Iterable[SelectedFile],
) -> str:
    """指定ファイルを zip にまとめる。

    - zip 内のパスは base_dir からの相対パスにする（ディレクトリ構造保持）。
    """

    zip_path_p = Path(zip_path)
    zip_path_p.parent.mkdir(parents=True, exist_ok=True)

    base_dir_p = Path(base_dir)

    with zipfile.ZipFile(zip_path_p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files or []:
            src = Path(f.local_path)
            if not src.exists() or not src.is_file():
                continue
            try:
                arcname = os.path.relpath(str(src), str(base_dir_p))
            except Exception:
                arcname = src.name
            zf.write(str(src), arcname=arcname)

    return str(zip_path_p)
