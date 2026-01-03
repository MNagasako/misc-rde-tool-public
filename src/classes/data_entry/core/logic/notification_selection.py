from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

_JST = timezone(timedelta(hours=9))
_UTC = timezone.utc


def parse_entry_start_time(value: str) -> Optional[datetime]:
    """登録状況エントリの startTime をUTC datetimeへ。

    入力は ISO8601 を想定（例: 2026-01-01T01:00:00+00:00 / 2026-01-01T01:00:00Z）。
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        # Pythonのfromisoformatは 'Z' を受け付けないため置換
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            # tz無しはUTC扱い（登録状況のstartTimeは原則UTC）
            dt = dt.replace(tzinfo=_UTC)
        return dt.astimezone(_UTC)
    except Exception:
        return None


def format_start_time_jst(value: str) -> str:
    dt = parse_entry_start_time(value)
    if not dt:
        return ""
    jst = dt.astimezone(_JST)
    return jst.strftime("%Y-%m-%d %H:%M")


def select_failed_entries_in_range(
    *,
    entries: Iterable[Dict[str, Any]],
    start_utc: datetime,
    end_utc: datetime,
) -> List[Dict[str, Any]]:
    """FAILED かつ startTime が [start_utc, end_utc] の範囲内のものを返す。"""
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=_UTC)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=_UTC)

    start_utc = start_utc.astimezone(_UTC)
    end_utc = end_utc.astimezone(_UTC)

    selected: List[Dict[str, Any]] = []
    for e in entries or []:
        if str(e.get("status") or "").upper() != "FAILED":
            continue
        dt = parse_entry_start_time(str(e.get("startTime") or ""))
        if not dt:
            continue
        if start_utc <= dt <= end_utc:
            selected.append(e)

    # 表示・安定性のため、開始時刻で昇順
    selected.sort(key=lambda x: parse_entry_start_time(str(x.get("startTime") or "")) or datetime.min.replace(tzinfo=_UTC))
    return selected


def select_failed_entries_by_reference(
    *,
    entries: Iterable[Dict[str, Any]],
    reference_utc: datetime,
    range_days: int,
) -> List[Dict[str, Any]]:
    """基準日時(reference_utc)から過去 range_days 日の範囲内で FAILED を抽出する。"""
    if range_days <= 0:
        range_days = 1
    ref = reference_utc.astimezone(_UTC) if reference_utc.tzinfo else reference_utc.replace(tzinfo=_UTC)
    start = ref - timedelta(days=int(range_days))
    end = ref
    return select_failed_entries_in_range(entries=entries, start_utc=start, end_utc=end)


@dataclass(frozen=True)
class PlannedNotificationRow:
    entry_id: str
    start_time_jst: str
    equipment_id: str
    device_name_ja: str
    dataset_template_name: str
    dataset_name: str
    data_name: str
    created_name: str
    created_org: str
    created_mail: str
    owner_name: str
    owner_org: str
    owner_mail: str
    test_to: str
    production_to: str
    production_sent_at: str
    effective_to: str
    error_code: str
    error_message: str
    subject: str
    body: str


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover
        return "{" + key + "}"


def _format_template(template: str, entry: Dict[str, Any]) -> str:
    values = _SafeFormatDict(
        {
            "entryId": entry.get("id") or "",
            "startTime": format_start_time_jst(str(entry.get("startTime") or "")) or (entry.get("startTime") or ""),
            "dataName": entry.get("dataName") or "",
            "datasetName": entry.get("datasetName") or "",
            "datasetTemplateName": entry.get("datasetTemplateName") or "",
            "equipmentId": entry.get("equipmentId") or "",
            "deviceNameJa": entry.get("deviceNameJa") or "",
            "errorCode": entry.get("errorCode") or "",
            "errorMessage": entry.get("errorMessage") or "",
            "createdByUserId": entry.get("createdByUserId") or "",
            "createdByName": entry.get("createdByName") or "",
            "createdByOrg": entry.get("createdByOrg") or "",
            "createdByMail": entry.get("createdByMail") or "",
            "dataOwnerUserId": entry.get("dataOwnerUserId") or "",
            "dataOwnerName": entry.get("dataOwnerName") or "",
            "dataOwnerOrg": entry.get("dataOwnerOrg") or "",
            "dataOwnerMail": entry.get("dataOwnerMail") or "",
            "testToAddress": entry.get("testToAddress") or "",
            "productionToAddress": entry.get("productionToAddress") or "",
            "equipmentManagerNames": entry.get("equipmentManagerNames") or "",
            "equipmentManagerEmails": entry.get("equipmentManagerEmails") or "",
            "equipmentManagerNotes": entry.get("equipmentManagerNotes") or "",
        }
    )
    try:
        return (template or "").format_map(values)
    except Exception:
        return template or ""


def build_planned_notification_rows(
    *,
    entries: Iterable[Dict[str, Any]],
    email_map: Dict[str, str],
    production_mode: bool,
    include_creator: bool,
    include_owner: bool,
    test_to_address: str,
    subject_template: str,
    body_template: str,
    production_sent_at_by_entry_id: Optional[Dict[str, str]] = None,
) -> List[PlannedNotificationRow]:
    """通知対象リスト（テーブル表示用）を生成する。

    - JST表示を基本とする
    - 実送信先は、本番運用なら投入者/所有者の実アドレス、テスト運用なら test_to_address を表示
      (ただし投入者/所有者の実アドレスは別カラムで表示する)
    """
    rows: List[PlannedNotificationRow] = []

    for e in entries or []:
        entry_id = str(e.get("id") or "")
        start_time_jst = format_start_time_jst(str(e.get("startTime") or ""))
        dataset_name = str(e.get("datasetName") or "")
        data_name = str(e.get("dataName") or "")

        created_name = str(e.get("createdByName") or "")
        created_org = str(e.get("createdByOrg") or "")
        owner_name = str(e.get("dataOwnerName") or "")
        owner_org = str(e.get("dataOwnerOrg") or "")

        created_id = str(e.get("createdByUserId") or "")
        owner_id = str(e.get("dataOwnerUserId") or "")
        created_mail = (email_map.get(created_id) or "").strip()
        owner_mail = (email_map.get(owner_id) or "").strip()

        production_targets: List[str] = []
        if include_creator:
            production_targets.append(created_mail)
        if include_owner:
            production_targets.append(owner_mail)
        # Preserve order / unique
        seen: set[str] = set()
        production_targets = [m for m in production_targets if m and not (m in seen or seen.add(m))]
        production_to = "; ".join(production_targets) if production_targets else "(未解決)"
        test_to = (test_to_address or "").strip() or "(未設定)"

        prod_sent_at = ""
        try:
            prod_sent_at = str((production_sent_at_by_entry_id or {}).get(entry_id) or "")
        except Exception:
            prod_sent_at = ""

        # テンプレ置換用にも載せておく（フォーマット側で拾えるように）
        try:
            e["createdByMail"] = created_mail
            e["dataOwnerMail"] = owner_mail
            e["testToAddress"] = test_to
            e["productionToAddress"] = production_to
        except Exception:
            pass

        subject = _format_template(subject_template, e)
        body = _format_template(body_template, e)

        # テーブルの「実送信先」表示は現運用モードの送信先を表示
        if production_mode:
            effective_to = production_to
        else:
            effective_to = test_to

        rows.append(
            PlannedNotificationRow(
                entry_id=entry_id,
                start_time_jst=start_time_jst,
                equipment_id=str(e.get("equipmentId") or ""),
                device_name_ja=str(e.get("deviceNameJa") or ""),
                dataset_template_name=str(e.get("datasetTemplateName") or ""),
                dataset_name=dataset_name,
                data_name=data_name,
                created_name=created_name,
                created_org=created_org,
                created_mail=created_mail or "(不明)",
                owner_name=owner_name,
                owner_org=owner_org,
                owner_mail=owner_mail or "(不明)",
                test_to=test_to,
                production_to=production_to,
                production_sent_at=prod_sent_at,
                effective_to=effective_to or "(未設定)",
                error_code=str(e.get("errorCode") or ""),
                error_message=str(e.get("errorMessage") or ""),
                subject=subject,
                body=body,
            )
        )

    return rows
