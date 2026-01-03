from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from config.common import get_dynamic_file_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EquipmentManager:
    name: str
    email: str
    note: str = ""


def _split_multi(text: str) -> List[str]:
    # ';' または改行区切りを許可
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts: List[str] = []
    for chunk in raw.split(";"):
        for line in chunk.split("\n"):
            v = (line or "").strip()
            if v:
                parts.append(v)
    return parts


def managers_to_placeholder_fields(managers: List[EquipmentManager]) -> Tuple[str, str, str]:
    """テンプレ向けの表示/プレースホルダ値を生成する。"""

    names = [m.name.strip() for m in (managers or []) if isinstance(m, EquipmentManager) and m.name.strip()]
    emails = [m.email.strip() for m in (managers or []) if isinstance(m, EquipmentManager) and m.email.strip()]
    notes = [m.note.strip() for m in (managers or []) if isinstance(m, EquipmentManager) and m.note.strip()]
    return ("; ".join(names), "; ".join(emails), "; ".join(notes))


def parse_managers_from_fields(names_text: str, emails_text: str, notes_text: str) -> List[EquipmentManager]:
    """UI入力（複数値）から EquipmentManager の配列を作る。"""

    names = _split_multi(names_text)
    emails = _split_multi(emails_text)
    notes = _split_multi(notes_text)
    n = max(len(names), len(emails), len(notes), 1)
    result: List[EquipmentManager] = []
    for i in range(n):
        name = names[i] if i < len(names) else ""
        email = emails[i] if i < len(emails) else ""
        note = notes[i] if i < len(notes) else ""
        m = EquipmentManager(name=name, email=email, note=note)
        if m.name or m.email or m.note:
            result.append(m)
    return result


def get_equipment_manager_store_path() -> str:
    """Return the user data path for the equipment manager store JSON."""

    return get_dynamic_file_path("input/equipment_managers.json")


def _normalize_manager_dict(item: Dict[str, Any]) -> EquipmentManager:
    name = str(item.get("name") or "").strip()
    email = str(item.get("email") or "").strip()
    note = str(item.get("note") or "").strip()
    return EquipmentManager(name=name, email=email, note=note)


def load_equipment_managers() -> Dict[str, List[EquipmentManager]]:
    """Load equipment managers mapping from JSON.

    JSON schema (minimal):
      {"AE-003": [{"name": "...", "email": "...", "note": "..."}, ...], ...}
    """

    path = get_equipment_manager_store_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.debug("Failed to load equipment managers: %s", exc)
        return {}

    if not isinstance(payload, dict):
        return {}

    result: Dict[str, List[EquipmentManager]] = {}
    for k, v in payload.items():
        equip_id = str(k or "").strip()
        if not equip_id:
            continue
        if not isinstance(v, list):
            continue
        managers: List[EquipmentManager] = []
        for item in v:
            if not isinstance(item, dict):
                continue
            m = _normalize_manager_dict(item)
            if not (m.name or m.email or m.note):
                continue
            managers.append(m)
        if managers:
            result[equip_id] = managers
    return result


def save_equipment_managers(mapping: Dict[str, List[EquipmentManager]]) -> None:
    path = get_equipment_manager_store_path()

    payload: Dict[str, Any] = {}
    for equip_id, managers in (mapping or {}).items():
        eid = str(equip_id or "").strip()
        if not eid:
            continue
        arr: List[Dict[str, str]] = []
        for m in managers or []:
            if not isinstance(m, EquipmentManager):
                continue
            if not (m.name or m.email or m.note):
                continue
            arr.append({"name": m.name, "email": m.email, "note": m.note})
        if arr:
            payload[eid] = arr

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
