"""
期限付き永続キャッシュ (TTL Persistent Cache)

JSON ファイルベースのキャッシュストア。各エントリに有効期限 (TTL) が付き、
期限切れのエントリは自動的に無視される。部分更新にも対応。

用途:
  - データセットエントリ一覧のキャッシュ
  - レジストレーションステータスの完了済みキャッシュ
  - データポータル検索結果キャッシュ  等
"""

import json
import logging
import os
import time
from datetime import timedelta
from typing import Any

from config.common import get_dynamic_file_path

logger = logging.getLogger(__name__)


class TTLCache:
    """JSON ファイルベースの期限付き永続キャッシュ。

    Parameters
    ----------
    namespace : str
        キャッシュの名前空間。ファイルパスの一部に使用される。
        例: ``"dataset_entries"`` → ``output/cache/dataset_entries.json``
    default_ttl : timedelta
        デフォルトの有効期限。
    """

    _BASE_DIR = "output/cache"

    def __init__(self, namespace: str, default_ttl: timedelta = timedelta(hours=1)) -> None:
        self._namespace = namespace
        self._default_ttl = default_ttl.total_seconds()
        self._path = get_dynamic_file_path(f"{self._BASE_DIR}/{namespace}.json")
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """キーに対応する値を返す。期限切れまたは未登録なら ``None``."""
        entry = self._data.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            return None
        return entry.get("v")

    def put(self, key: str, value: Any, ttl: timedelta | None = None) -> None:
        """値をキャッシュに保存する。"""
        ttl_sec = ttl.total_seconds() if ttl else self._default_ttl
        self._data[key] = {
            "v": value,
            "ts": time.time(),
            "ttl": ttl_sec,
        }
        self._save()

    def put_many(self, items: dict[str, Any], ttl: timedelta | None = None) -> None:
        """複数の値を一括保存する。"""
        ttl_sec = ttl.total_seconds() if ttl else self._default_ttl
        now = time.time()
        for k, v in items.items():
            self._data[k] = {"v": v, "ts": now, "ttl": ttl_sec}
        self._save()

    def put_permanent(self, key: str, value: Any) -> None:
        """恒久キャッシュとして保存する (TTL なし)。"""
        self._data[key] = {
            "v": value,
            "ts": time.time(),
            "ttl": 0,  # 0 = 永久
        }
        self._save()

    def invalidate(self, key: str) -> None:
        """特定キーのキャッシュを無効化する。"""
        if key in self._data:
            del self._data[key]
            self._save()

    def invalidate_prefix(self, prefix: str) -> int:
        """プレフィックスに一致するキーをすべて無効化して件数を返す。"""
        to_del = [k for k in self._data if k.startswith(prefix)]
        for k in to_del:
            del self._data[k]
        if to_del:
            self._save()
        return len(to_del)

    def clear(self) -> None:
        """全キャッシュをクリアする。"""
        self._data.clear()
        self._save()

    def has(self, key: str) -> bool:
        """有効なキャッシュエントリが存在するか。"""
        return self.get(key) is not None

    def keys(self) -> list[str]:
        """有効なキーの一覧を返す。"""
        return [k for k in self._data if not self._is_expired(self._data[k])]

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_expired(entry: dict) -> bool:
        ttl = entry.get("ttl", 0)
        if ttl <= 0:
            return False  # permanent
        return (time.time() - entry.get("ts", 0)) > ttl

    def _load(self) -> None:
        if not os.path.exists(self._path):
            self._data = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
            else:
                self._data = {}
        except Exception:
            logger.debug("TTLCache load failed: %s", self._path, exc_info=True)
            self._data = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self._path)
        except Exception:
            logger.warning("TTLCache save failed: %s", self._path, exc_info=True)
