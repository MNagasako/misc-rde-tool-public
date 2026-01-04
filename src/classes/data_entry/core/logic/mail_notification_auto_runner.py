from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from classes.data_entry.core.logic.notification_selection import PlannedNotificationRow

_JST = timezone(timedelta(hours=9))
_UTC = timezone.utc


@dataclass(frozen=True)
class AutoRunMailBatch:
    to_addr: str
    subject: str
    body: str
    entry_ids: Tuple[str, ...]


@dataclass(frozen=True)
class AutoRunSummary:
    checked_at_utc: datetime
    selected_count: int
    excluded_logged_count: int
    unresolved_count: int
    batches: Tuple[AutoRunMailBatch, ...]


def interval_options() -> List[Tuple[str, int]]:
    """UI表示ラベルと秒数の候補。"""

    seconds = [10, 20, 30, 60]
    minutes = [2, 3, 5, 10, 15, 20, 30, 60]
    opts: List[Tuple[str, int]] = [(f"{s}秒", s) for s in seconds]
    opts.extend([(f"{m}分", m * 60) for m in minutes])
    return opts


def _now_jst_str(now_utc: datetime) -> str:
    dt = now_utc.astimezone(_JST) if now_utc.tzinfo else now_utc.replace(tzinfo=_UTC).astimezone(_JST)
    return dt.strftime("%Y-%m-%d %H:%M")


def _aggregate_subject(*, subjects: Sequence[str], template_name: str, count: int) -> str:
    uniq = [s for s in {str(x or "").strip() for x in subjects} if s]
    if len(uniq) == 1:
        return uniq[0]
    # 件名が分岐する場合は、バッチ送信用に共通件名へフォールバック
    tn = (template_name or "").strip()
    base = tn if tn else "データ登録 FAILED 通知"
    return f"{base} ({count}件)"


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover
        return "{" + key + "}"


def _format_batch_template(*, template: str, now_utc: datetime, count: int, production_mode: bool) -> str:
    if not template:
        return ""
    values = _SafeFormatDict(
        {
            "nowJst": _now_jst_str(now_utc),
            "count": str(int(count)),
            "testNotice": "" if production_mode else "本メールはテスト送信です",
        }
    )
    try:
        return (template or "").format_map(values)
    except Exception:
        return template or ""


def build_batches(
    *,
    planned_rows: Iterable[PlannedNotificationRow],
    production_mode: bool,
    include_creator: bool,
    include_owner: bool,
    include_equipment_manager: bool = False,
    test_to_address: str,
    template_name: str,
    batch_subject_template: str = "",
    batch_header_template: str = "",
    batch_footer_template: str = "",
    logged_entry_ids: Optional[Iterable[str]] = None,
) -> AutoRunSummary:
    """通知対象（planned_rows）から、送信先ごとのバッチメールを構築する。

    - production_mode:
        - include_creator/include_owner に基づき、投入者/所有者の各宛先へバッチを作る
    - test_mode:
        - 全通知を 1通として test_to_address に送る
    - logged_entry_ids に含まれる entryId は除外

    Returns:
        AutoRunSummary（送信しない場合でも batches は空）
    """

    now_utc = datetime.now(_UTC)
    logged = {str(x or "").strip() for x in (logged_entry_ids or []) if str(x or "").strip()}

    all_rows = [r for r in (planned_rows or []) if r and getattr(r, "entry_id", "")]
    rows: List[PlannedNotificationRow] = [r for r in all_rows if r.entry_id not in logged]
    excluded = max(0, len(all_rows) - len(rows))

    # 対象0件の場合は送信バッチを作らない（テスト運用でも空メールを送らない）
    if not rows:
        return AutoRunSummary(
            checked_at_utc=now_utc,
            selected_count=0,
            excluded_logged_count=excluded,
            unresolved_count=0,
            batches=(),
        )

    unresolved = 0
    buckets: Dict[str, List[PlannedNotificationRow]] = {}

    if production_mode:
        if not (include_creator or include_owner or include_equipment_manager):
            # 宛先指定不正：送信はしない（UI側でブロックする想定）
            return AutoRunSummary(
                checked_at_utc=now_utc,
                selected_count=len(rows),
                excluded_logged_count=excluded,
                unresolved_count=len(rows),
                batches=(),
            )

        for r in rows:
            recipients: List[str] = []
            if include_creator and r.created_mail and r.created_mail not in ("(不明)", "(未解決)"):
                recipients.append(r.created_mail)
            if include_owner and r.owner_mail and r.owner_mail not in ("(不明)", "(未解決)"):
                recipients.append(r.owner_mail)
            if include_equipment_manager:
                try:
                    recipients.extend(list(getattr(r, "equipment_manager_emails", ()) or ()))
                except Exception:
                    pass

            uniq: List[str] = []
            seen = set()
            for addr in recipients:
                a = str(addr or "").strip()
                if not a or a in seen:
                    continue
                seen.add(a)
                uniq.append(a)

            if not uniq:
                unresolved += 1
                continue

            for to in uniq:
                buckets.setdefault(to, []).append(r)
    else:
        to = str(test_to_address or "").strip()
        if not to:
            return AutoRunSummary(
                checked_at_utc=now_utc,
                selected_count=len(rows),
                excluded_logged_count=excluded,
                unresolved_count=len(rows),
                batches=(),
            )
        buckets[to] = list(rows)

    batches: List[AutoRunMailBatch] = []
    for to, rs in buckets.items():
        # 本文は entry 単位にテンプレ適用済みの body を連結
        subject = _format_batch_template(
            template=(batch_subject_template or ""),
            now_utc=now_utc,
            count=len(rs),
            production_mode=production_mode,
        ).strip()
        if not subject:
            subjects = [r.subject for r in rs]
            subject = _aggregate_subject(subjects=subjects, template_name=template_name, count=len(rs))

        parts: List[str] = []

        header = _format_batch_template(
            template=batch_header_template,
            now_utc=now_utc,
            count=len(rs),
            production_mode=production_mode,
        ).strip("\n")
        if header:
            parts.append(header)

        for idx, r in enumerate(rs, start=1):
            entry_body = (getattr(r, "entry_body", "") or getattr(r, "body", "") or "").strip("\n")
            if not entry_body:
                continue
            if idx > 1:
                parts.append("------------------------------------------------------------")
            parts.append(entry_body)

        footer = _format_batch_template(
            template=batch_footer_template,
            now_utc=now_utc,
            count=len(rs),
            production_mode=production_mode,
        ).strip("\n")
        if footer:
            parts.append(footer)

        body = "\n\n".join([p for p in parts if p]).strip() + ("\n" if parts else "")
        batches.append(
            AutoRunMailBatch(
                to_addr=to,
                subject=subject,
                body=body,
                entry_ids=tuple([r.entry_id for r in rs]),
            )
        )

    # 宛先の安定化のため sort
    batches.sort(key=lambda b: b.to_addr.lower())

    return AutoRunSummary(
        checked_at_utc=now_utc,
        selected_count=len(rows),
        excluded_logged_count=excluded,
        unresolved_count=unresolved,
        batches=tuple(batches),
    )
