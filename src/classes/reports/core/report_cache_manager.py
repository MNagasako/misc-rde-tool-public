"""報告書データのJSONキャッシュ管理モジュール"""

from __future__ import annotations

import json
import logging
import os
import re
from enum import Enum
from typing import Dict, Iterable, Optional, List

from config.common import OUTPUT_DIR, ensure_directory_exists

logger = logging.getLogger(__name__)


class ReportCacheMode(str, Enum):
    """報告書キャッシュの振る舞い"""

    SKIP = "skip"
    OVERWRITE = "overwrite"

    @classmethod
    def from_value(cls, value: Optional[str]) -> "ReportCacheMode":
        """文字列表現からキャッシュモードを取得"""
        if value == cls.OVERWRITE.value:
            return cls.OVERWRITE
        return cls.SKIP


class ReportCacheManager:
    """報告書JSONのキャッシュ管理クラス"""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = ensure_directory_exists(
            cache_dir or os.path.join(OUTPUT_DIR, "arim-site", "reports", "cache")
        )
        logger.info("ReportCacheManager初期化: cache_dir=%s", self.cache_dir)

    def _sanitize_code(self, code: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]", "_", code)

    def _entry_path(self, code: str) -> str:
        return os.path.join(self.cache_dir, f"{self._sanitize_code(code)}.json")

    def load_entry(self, code: Optional[str]) -> Optional[Dict]:
        if not code:
            return None
        path = self._entry_path(code)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("キャッシュ読込失敗: code=%s, error=%s", code, exc)
            return None

    def save_entry(self, report: Dict) -> Optional[str]:
        code = report.get("code")
        if not code:
            logger.debug("キャッシュ保存スキップ: codeフィールドが存在しません")
            return None
        path = self._entry_path(code)
        tmp_path = f"{path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(report, fp, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
            return path
        except OSError as exc:
            logger.error("キャッシュ保存失敗: code=%s, error=%s", code, exc)
            return None

    def save_entries(self, reports: Iterable[Dict]) -> int:
        saved = 0
        for report in reports:
            if self.save_entry(report):
                saved += 1
        if saved:
            logger.info("キャッシュ更新: %d件", saved)
        return saved

    def has_entry(self, code: Optional[str]) -> bool:
        if not code:
            return False
        return os.path.exists(self._entry_path(code))

    def delete_entry(self, code: Optional[str]) -> bool:
        if not code:
            return False
        path = self._entry_path(code)
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
            return True
        except OSError as exc:
            logger.warning("キャッシュ削除失敗: code=%s, error=%s", code, exc)
            return False

    def list_cached_codes(self) -> List[str]:
        codes: List[str] = []
        try:
            for filename in os.listdir(self.cache_dir):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(self.cache_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    code = data.get("code") or filename[:-5]
                except (OSError, json.JSONDecodeError):
                    code = filename[:-5]
                codes.append(code)
        except OSError:
            return []
        return codes
