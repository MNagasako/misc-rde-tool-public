"""
外部アクセスモニター - SQLiteサービス層

HTTPリクエストの記録・照会を行うSQLiteベースの永続化サービス。
http_helpers._log_and_execute() からフック呼び出しされる。
スレッドセーフ設計。
"""

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class AccessRecord:
    """1件のHTTPアクセス記録"""
    id: int = 0
    created_at: str = ""
    url: str = ""
    host: str = ""
    method: str = ""
    source_kind: str = "network"  # "network" or "cache"
    status_code: int = 0
    duration_ms: float = 0.0
    cache_key: str = ""
    error_text: str = ""


# ---------------------------------------------------------------------------
# SQLiteストア (シングルトン)
# ---------------------------------------------------------------------------


class ExternalAccessMonitorStore:
    """SQLiteベースのアクセスログ永続化ストア (シングルトン)"""

    _instance: Optional["ExternalAccessMonitorStore"] = None
    _lock = threading.Lock()

    # -- シングルトン -----------------------------------------------------------

    @classmethod
    def instance(cls) -> "ExternalAccessMonitorStore":
        """スレッドセーフなシングルトン取得"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """テスト用: シングルトンをリセット"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    # -- 初期化 ---------------------------------------------------------------

    def __init__(self) -> None:
        self._db_path: Optional[str] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.Lock()
        self._latest: Optional[AccessRecord] = None
        self._listeners: List = []  # callable[[AccessRecord], None]

    def init_db(self, db_path: Optional[str] = None) -> None:
        """DB初期化。db_path=None のときデフォルトパスを使用"""
        if db_path is None:
            from config.common import get_dynamic_file_path
            db_path = get_dynamic_file_path("output/log/external_access_log.sqlite3")
        self._db_path = db_path

        # 親ディレクトリ作成
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                host        TEXT    NOT NULL DEFAULT '',
                method      TEXT    NOT NULL DEFAULT 'GET',
                source_kind TEXT    NOT NULL DEFAULT 'network',
                status_code INTEGER NOT NULL DEFAULT 0,
                duration_ms REAL    NOT NULL DEFAULT 0,
                cache_key   TEXT    NOT NULL DEFAULT '',
                error_text  TEXT    NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_created_at ON access_log(created_at)"
        )
        self._conn.commit()
        logger.debug("ExternalAccessMonitorStore initialized: %s", db_path)

    # -- 書き込み -------------------------------------------------------------

    def record_access(
        self,
        url: str,
        method: str,
        status_code: int,
        duration_ms: float,
        source_kind: str = "network",
        cache_key: str = "",
        error_text: str = "",
    ) -> Optional[AccessRecord]:
        """アクセスを1件記録し、リスナーへ通知する。DB未初期化時は何もしない。"""
        if self._conn is None:
            return None

        host = ""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
        except Exception:
            pass

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rec = AccessRecord(
            created_at=now,
            url=url,
            host=host,
            method=method.upper(),
            source_kind=source_kind,
            status_code=status_code,
            duration_ms=round(duration_ms, 1),
            cache_key=cache_key,
            error_text=error_text[:500],
        )

        try:
            with self._write_lock:
                cur = self._conn.execute(
                    """
                    INSERT INTO access_log
                        (created_at, url, host, method, source_kind,
                         status_code, duration_ms, cache_key, error_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.created_at,
                        rec.url,
                        rec.host,
                        rec.method,
                        rec.source_kind,
                        rec.status_code,
                        rec.duration_ms,
                        rec.cache_key,
                        rec.error_text,
                    ),
                )
                self._conn.commit()
                rec.id = cur.lastrowid or 0
        except Exception:
            logger.debug("access_log insert failed", exc_info=True)
            return None

        self._latest = rec
        self._notify_listeners(rec)
        return rec

    # -- 読み取り -------------------------------------------------------------

    def get_recent(self, n: int = 10) -> List[AccessRecord]:
        """直近 n 件のレコードを新しい順で返す"""
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT id, created_at, url, host, method, source_kind, "
                "status_code, duration_ms, cache_key, error_text "
                "FROM access_log ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        except Exception:
            logger.debug("get_recent failed", exc_info=True)
            return []

    def get_all(
        self,
        method_filter: str = "",
        host_filter: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> List[AccessRecord]:
        """全件取得 (フィルタ・ページング対応)"""
        if self._conn is None:
            return []
        clauses: List[str] = []
        params: list = []
        if method_filter:
            clauses.append("method = ?")
            params.append(method_filter.upper())
        if host_filter:
            clauses.append("host LIKE ?")
            params.append(f"%{host_filter}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])
        try:
            rows = self._conn.execute(
                f"SELECT id, created_at, url, host, method, source_kind, "
                f"status_code, duration_ms, cache_key, error_text "
                f"FROM access_log{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        except Exception:
            logger.debug("get_all failed", exc_info=True)
            return []

    def get_total_count(self) -> int:
        """全レコード件数を返す"""
        if self._conn is None:
            return 0
        try:
            row = self._conn.execute("SELECT COUNT(*) FROM access_log").fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    @property
    def latest(self) -> Optional[AccessRecord]:
        """インメモリの最新レコード"""
        return self._latest

    # -- リスナー管理 ---------------------------------------------------------

    def add_listener(self, callback) -> None:
        """新規レコード追加時のコールバックを登録"""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        """コールバック登録解除"""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify_listeners(self, record: AccessRecord) -> None:
        for cb in self._listeners:
            try:
                cb(record)
            except Exception:
                logger.debug("listener callback error", exc_info=True)

    # -- ユーティリティ -------------------------------------------------------

    def close(self) -> None:
        """DBコネクションをクローズ"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    @staticmethod
    def _row_to_record(row: tuple) -> AccessRecord:
        return AccessRecord(
            id=row[0],
            created_at=row[1],
            url=row[2],
            host=row[3],
            method=row[4],
            source_kind=row[5],
            status_code=row[6],
            duration_ms=row[7],
            cache_key=row[8],
            error_text=row[9],
        )
