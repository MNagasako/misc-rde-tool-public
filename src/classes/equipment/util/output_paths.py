"""設備機能の出力パスヘルパー"""

import logging
import shutil
from pathlib import Path
from typing import Iterable, Optional

from config import common as common_config

_logger = logging.getLogger(__name__)


def _equipment_root_path() -> Path:
    """`output/arim-site/equipment` を指すPathを返す"""
    return Path(common_config.OUTPUT_DIR) / "arim-site" / "equipment"


def _legacy_facilities_path() -> Path:
    """旧`output/arim-site/facilities`ディレクトリのPath"""
    return Path(common_config.OUTPUT_DIR) / "arim-site" / "facilities"


def ensure_equipment_output_dirs(logger: Optional[logging.Logger] = None) -> Path:
    """設備出力ディレクトリと標準サブディレクトリを作成し、旧構造を移行"""
    log = logger or _logger
    equipment_dir = _equipment_root_path()
    legacy_dir = _legacy_facilities_path()

    if legacy_dir.exists():
        _migrate_legacy_directory(legacy_dir, equipment_dir, log)

    for sub_dir in (equipment_dir, equipment_dir / "json_entries", equipment_dir / "backups"):
        sub_dir.mkdir(parents=True, exist_ok=True)

    return equipment_dir


def _migrate_legacy_directory(legacy_dir: Path, equipment_dir: Path, log: logging.Logger) -> None:
    """旧facilitiesディレクトリをequipment配下へ移行"""
    try:
        if not equipment_dir.exists():
            legacy_dir.rename(equipment_dir)
            log.info("既存のfacilitiesディレクトリをequipmentへリネームしました: %s", equipment_dir)
            return

        for item in legacy_dir.iterdir():
            dest = equipment_dir / item.name
            if dest.exists():
                log.debug("移行先が既に存在するためスキップ: %s", dest)
                continue
            shutil.move(str(item), str(dest))
            log.info("facilities配下のファイルをequipmentへ移動: %s -> %s", item, dest)

        try:
            legacy_dir.rmdir()
            log.info("空になったfacilitiesディレクトリを削除しました: %s", legacy_dir)
        except OSError:
            log.debug("facilitiesディレクトリは空でないため削除しませんでした: %s", legacy_dir)
    except Exception as exc:
        log.warning("facilitiesディレクトリの移行に失敗: %s", exc)


def get_equipment_root_dir() -> Path:
    """設備出力ディレクトリのPathを返す"""
    return ensure_equipment_output_dirs()


def get_equipment_backups_root() -> Path:
    """バックアップディレクトリのPathを返す"""
    equipment_dir = ensure_equipment_output_dirs()
    backups = equipment_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    return backups


def get_equipment_entries_dir() -> Path:
    """json_entriesディレクトリのPathを返す"""
    equipment_dir = ensure_equipment_output_dirs()
    entries = equipment_dir / "json_entries"
    entries.mkdir(parents=True, exist_ok=True)
    return entries


def find_latest_matching_file(base_dir: Path, patterns: Iterable[str]) -> Optional[Path]:
    """指定パターンに一致するファイルのうち最新のものを返す"""
    candidates = []
    for pattern in patterns:
        candidates.extend(base_dir.glob(pattern))
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def find_latest_child_directory(base_dir: Path) -> Optional[Path]:
    """指定ディレクトリ配下の最新サブディレクトリを返す"""
    if not base_dir.exists():
        return None
    directories = [child for child in base_dir.iterdir() if child.is_dir()]
    if not directories:
        return None
    try:
        return max(directories, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
