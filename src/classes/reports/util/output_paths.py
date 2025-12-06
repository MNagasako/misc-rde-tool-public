"""報告書機能向けの出力パスヘルパー"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from config import common as common_config

_logger = logging.getLogger(__name__)


def get_reports_root_dir() -> Path:
    """`output/arim-site/reports` を作成・返却"""
    reports_dir = Path(common_config.OUTPUT_DIR) / "arim-site" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def get_reports_backups_root() -> Path:
    """報告書バックアップディレクトリを作成・返却"""
    backups_dir = get_reports_root_dir() / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    return backups_dir


def find_latest_matching_file(base_dir: Path, patterns: Iterable[str]) -> Optional[Path]:
    """パターンに一致する最新ファイルを返す"""
    candidates = []
    for pattern in patterns:
        candidates.extend(base_dir.glob(pattern))
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    except OSError as exc:  # pragma: no cover - OS errors are loggedのみ
        _logger.debug("最新ファイル探索に失敗: %s", exc)
        return None


def find_latest_child_directory(base_dir: Path) -> Optional[Path]:
    """指定ディレクトリ直下の最新サブディレクトリを返す"""
    if not base_dir.exists():
        return None
    directories = [child for child in base_dir.iterdir() if child.is_dir()]
    if not directories:
        return None
    try:
        return max(directories, key=lambda path: path.stat().st_mtime)
    except OSError as exc:  # pragma: no cover
        _logger.debug("最新ディレクトリ探索に失敗: %s", exc)
        return None
