from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config.common import ensure_directory_exists, get_dynamic_file_path

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _log_path() -> str:
    return get_dynamic_file_path("output/.private/mail_notification_log.json")


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_json(path: str, obj: Dict[str, Any]) -> None:
    try:
        # output/.private の作成
        ensure_directory_exists(get_dynamic_file_path("output/.private"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.debug("mail_send_log save failed: %s", exc)


def _key(to_addr: str, subject: str) -> str:
    return f"{to_addr.strip().lower()}|{subject.strip()}"


def should_send(*, to_addr: str, subject: str) -> bool:
    """同一(送信先+件名)は二重送信しない。"""
    if not to_addr.strip() or not subject.strip():
        return False
    path = _log_path()
    data = _load_json(path)
    last = (data.get("last_sent") or {})
    if not isinstance(last, dict):
        last = {}
    return _key(to_addr, subject) not in last


def record_sent(*, to_addr: str, subject: str, sent_at: Optional[datetime] = None) -> None:
    """送信日時/送信先/件名を永続ログに追記し、last_sent を更新する。"""
    if not to_addr.strip() or not subject.strip():
        return

    sent_at = sent_at or _utc_now()
    path = _log_path()
    data = _load_json(path)

    history = data.get("history")
    if not isinstance(history, list):
        history = []

    history.append(
        {
            "sentAt": sent_at.isoformat(),
            "to": to_addr,
            "subject": subject,
        }
    )

    last = data.get("last_sent")
    if not isinstance(last, dict):
        last = {}
    last[_key(to_addr, subject)] = sent_at.isoformat()

    data["history"] = history
    data["last_sent"] = last

    _save_json(path, data)


def load_history(*, limit: int = 200) -> List[Dict[str, Any]]:
    """送信履歴（新しい順）を返す。"""
    try:
        data = _load_json(_log_path())
        history = data.get("history")
        if not isinstance(history, list):
            return []
        items = [h for h in history if isinstance(h, dict)]

        def _key_time(item: Dict[str, Any]) -> str:
            return str(item.get("sentAt") or "")

        items.sort(key=_key_time, reverse=True)
        if limit and limit > 0:
            return items[: int(limit)]
        return items
    except Exception:
        return []
