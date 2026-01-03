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


def record_sent_ex(
    *,
    to_addr: str,
    subject: str,
    sent_at: Optional[datetime] = None,
    mode: Optional[str] = None,
    entry_id: Optional[str] = None,
    template_name: Optional[str] = None,
) -> None:
    """拡張版: mode/entryId/templateName 等を含めて永続ログに追記する。

    - 既存の record_sent() と同じログファイルを使用
    - 既存ログと共存できるように、追加フィールドは任意
    """

    if not to_addr.strip() or not subject.strip():
        return

    sent_at = sent_at or _utc_now()
    path = _log_path()
    data = _load_json(path)

    history = data.get("history")
    if not isinstance(history, list):
        history = []

    item: Dict[str, Any] = {
        "sentAt": sent_at.isoformat(),
        "to": to_addr,
        "subject": subject,
    }
    m = (mode or "").strip().lower()
    if m:
        item["mode"] = m
    eid = (entry_id or "").strip()
    if eid:
        item["entryId"] = eid
    tn = (template_name or "").strip()
    if tn:
        item["templateName"] = tn

    history.append(item)

    last = data.get("last_sent")
    if not isinstance(last, dict):
        last = {}
    last[_key(to_addr, subject)] = sent_at.isoformat()

    data["history"] = history
    data["last_sent"] = last

    _save_json(path, data)


def load_last_sent_at_by_entry_id(*, mode: Optional[str] = None) -> Dict[str, str]:
    """entryIdごとの最新送信日時(ISO文字列)を返す。

    Args:
        mode: "production" / "test" など。指定時は一致するもののみ。
    """

    items = load_history(limit=0)
    m = (mode or "").strip().lower()
    result: Dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        eid = str(it.get("entryId") or "").strip()
        if not eid:
            continue
        if m:
            if str(it.get("mode") or "").strip().lower() != m:
                continue
        ts = str(it.get("sentAt") or "").strip()
        if not ts:
            continue
        # historyは新しい順だが、limit=0で全取得時はソート済みのはず
        result.setdefault(eid, ts)
    return result


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


def clear_history_by_mode(*, mode: str) -> int:
    """指定モードの送信履歴を削除する。

    - history から mode が一致する要素のみ除去
    - last_sent は残った history から再構築する（mode を保持していないため）

    Returns:
        削除した履歴件数
    """

    m = (mode or "").strip().lower()
    if not m:
        return 0

    path = _log_path()
    data = _load_json(path)
    history = data.get("history")
    if not isinstance(history, list):
        history = []

    kept: List[Dict[str, Any]] = []
    removed = 0
    for it in history:
        if not isinstance(it, dict):
            continue
        if str(it.get("mode") or "").strip().lower() == m:
            removed += 1
            continue
        kept.append(it)

    # last_sent を再構築（新しい方が勝つ）
    kept_sorted = [h for h in kept if isinstance(h, dict)]

    def _key_time(item: Dict[str, Any]) -> str:
        return str(item.get("sentAt") or "")

    kept_sorted.sort(key=_key_time, reverse=True)

    last: Dict[str, str] = {}
    for it in kept_sorted:
        to_addr = str(it.get("to") or "").strip()
        subject = str(it.get("subject") or "").strip()
        sent_at = str(it.get("sentAt") or "").strip()
        if not to_addr or not subject or not sent_at:
            continue
        k = _key(to_addr, subject)
        # sorted済みなので最初が最新
        if k not in last:
            last[k] = sent_at

    data["history"] = kept
    data["last_sent"] = last
    _save_json(path, data)
    return removed
