from typing import Optional, Tuple
import re
import json
from pathlib import Path

# NOTE: Follow path management rules via config.common
try:
    # Correct workspace import
    from config.common import get_output_dir
except Exception:
    # Fallback to local path resolution if config.common is unavailable in tests
    def get_output_dir() -> Path:
        return Path("output")

EQUIPMENT_SUBDIR = Path("arim-site") / "equipment"
RDE_DATA_SUBDIR = Path("rde") / "data"
FACILITIES_PATTERN = re.compile(r"^facilities_\d{8}_\d{6}\.json$")


def find_latest_facilities_json() -> Optional[Path]:
    """Find the latest facilities_********_******.json under output/arim-site/equipment.
    Returns absolute Path or None.
    """
    base = Path(get_output_dir()) / EQUIPMENT_SUBDIR
    if not base.exists():
        return None
    candidates = []
    for p in base.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if FACILITIES_PATTERN.match(name):
            candidates.append(p)
    if not candidates:
        # Optional: fallback to non-dated filename
        fallback = base / "facilities.json"
        return fallback if fallback.exists() else None
    # Sort by filename (timestamp embedded) to pick latest by name
    candidates.sort(key=lambda x: x.name, reverse=True)
    return candidates[0]


def load_equipment_name_map_from_merged_data2() -> dict[str, dict[str, str]]:
    """Load equipment name map from merged_data2.json.

    Returns mapping: equipment_id -> {"ja": ..., "en": ..., "raw": ...}
    When file is missing or invalid, returns empty dict.
    """

    try:
        # Follow path management via config.common
        from config.common import get_dynamic_file_path

        merged_path = Path(get_dynamic_file_path("output/arim-site/equipment/merged_data2.json"))
    except Exception:
        merged_path = Path(get_output_dir()) / EQUIPMENT_SUBDIR / "merged_data2.json"

    if not merged_path.exists() or not merged_path.is_file():
        return {}

    try:
        with merged_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    if not isinstance(payload, list):
        return {}

    result: dict[str, dict[str, str]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        equip_id = str(item.get("設備ID") or item.get("equipment_id") or item.get("id") or "").strip()
        if not equip_id:
            continue
        name_ja = str(item.get("装置名_日") or item.get("装置名") or "").strip()
        name_en = str(item.get("装置名_英") or "").strip()
        raw = str(item.get("設備名称") or "").strip()
        result[equip_id] = {"ja": name_ja, "en": name_en, "raw": raw}

    return result


def lookup_device_name_ja(equipment_id: str, *, name_map: Optional[dict[str, dict[str, str]]] = None) -> Optional[str]:
    """Lookup Japanese device name for an equipment ID from merged_data2.json."""

    eid = (equipment_id or "").strip()
    if not eid:
        return None

    mapping = name_map if isinstance(name_map, dict) else load_equipment_name_map_from_merged_data2()
    item = mapping.get(eid) if isinstance(mapping, dict) else None
    if not isinstance(item, dict):
        return None

    return (item.get("ja") or item.get("raw") or item.get("en") or "").strip() or None


def lookup_equipment_id_by_device_name(
    device_name_ja: str,
    device_name_en: str = "",
    *,
    name_map: Optional[dict[str, dict[str, str]]] = None,
) -> Optional[str]:
    """装置名から merged_data2 の「設備ID」を逆引きする。

    - 完全一致（trim後）で探索
    - ja→en→raw の順で探索
    """

    ja = (device_name_ja or "").strip()
    en = (device_name_en or "").strip()
    if not ja and not en:
        return None

    mapping = name_map if isinstance(name_map, dict) else load_equipment_name_map_from_merged_data2()
    if not isinstance(mapping, dict) or not mapping:
        return None

    # 1) ja一致
    if ja:
        for eid, item in mapping.items():
            if not isinstance(item, dict):
                continue
            if str(item.get("ja") or "").strip() == ja:
                return str(eid)

    # 2) en一致
    if en:
        for eid, item in mapping.items():
            if not isinstance(item, dict):
                continue
            if str(item.get("en") or "").strip() == en:
                return str(eid)

    # 3) raw一致
    if ja:
        for eid, item in mapping.items():
            if not isinstance(item, dict):
                continue
            if str(item.get("raw") or "").strip() == ja:
                return str(eid)

    return None


def lookup_facility_code_by_equipment_id(json_path: Path, equipment_id: str) -> Optional[str]:
    """Lookup facility code by '設備ID' within the JSON at json_path.
    Returns code string or None.
    """
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    facilities = data.get("facilities") if isinstance(data, dict) else None
    if not isinstance(facilities, list):
        return None
    for item in facilities:
        if not isinstance(item, dict):
            continue
        if str(item.get("設備ID")) == str(equipment_id):
            code = item.get("code")
            return str(code) if code is not None else None
    return None


_ID_PATTERNS = [
    # 長い/具体的な形式を先に置いて部分一致の誤抽出を避ける
    re.compile(r"[A-Za-z]{2}-[A-Za-z]{3}-\d{3,4}"),  # e.g., KT-FDL-060
    re.compile(r"[A-Za-z]{2}-\d{4}"),  # e.g., XX-1234
    re.compile(r"[A-Za-z]{2}-\d{3}"),  # e.g., NM-005
]


def extract_equipment_id(text: str) -> Optional[str]:
    """Extract equipment ID like 'NM-005' from mixed text.
    Returns ID or None if not found.
    """
    if not text:
        return None
    for pat in _ID_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0).upper()
    # Sometimes the text itself is the ID
    t = text.strip()
    if any(re.fullmatch(pat, t) for pat in _ID_PATTERNS):
        return t.upper()
    return None


def load_instrument_local_id_map_from_instruments_json(json_path: Optional[Path | str] = None) -> dict[str, str]:
    """Load instrument localId map from output/rde/data/instruments.json.

    Returns mapping: instrument_uuid -> localId
    """

    if json_path is not None:
        json_path = Path(str(json_path))
    else:
        try:
            from config.common import INSTRUMENTS_JSON_PATH

            json_path = Path(INSTRUMENTS_JSON_PATH)
        except Exception:
            json_path = Path(get_output_dir()) / RDE_DATA_SUBDIR / "instruments.json"

    if not json_path.exists() or not json_path.is_file():
        return {}

    try:
        with json_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return {}

    result: dict[str, str] = {}
    for inst in data:
        if not isinstance(inst, dict):
            continue
        inst_id = str(inst.get("id") or "").strip()
        if not inst_id:
            continue
        attr = inst.get("attributes") or {}
        programs = attr.get("programs") or []
        local_id = ""
        if isinstance(programs, list):
            for prog in programs:
                if not isinstance(prog, dict):
                    continue
                lid = str(prog.get("localId") or "").strip()
                if lid:
                    local_id = lid
                    break
        if local_id:
            result[inst_id] = local_id

    return result


def lookup_instrument_local_id(
    instrument_uuid: str,
    *,
    local_id_map: Optional[dict[str, str]] = None,
) -> Optional[str]:
    iid = str(instrument_uuid or "").strip()
    if not iid:
        return None
    mapping = local_id_map if isinstance(local_id_map, dict) else load_instrument_local_id_map_from_instruments_json()
    v = mapping.get(iid) if isinstance(mapping, dict) else None
    return str(v).strip() if v else None


def lookup_facility_name_by_equipment_id(json_path: Path, equipment_id: str) -> Optional[str]:
    """Lookup facility name by '設備ID' within the JSON at json_path.
    Returns name string or None.
    """
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    facilities = data.get("facilities") if isinstance(data, dict) else None
    if not isinstance(facilities, list):
        return None
    for item in facilities:
        if not isinstance(item, dict):
            continue
        if str(item.get("設備ID")) == str(equipment_id):
            name = item.get("設備名称")
            return str(name) if name is not None else None
    return None


def build_equipment_anchor(code: str, equipment_id: str) -> str:
    """Build anchor tag for equipment code and id."""
    href = f"https://nanonet.go.jp/facility.php?mode=detail&code={code}"
    return f"<a href=\"{href}\">{equipment_id}</a>"


def build_equipment_anchor_with_name(code: str, equipment_id: str, equipment_name: str) -> str:
    """Build anchor tag for equipment code, id and name.
    Format: <a href='...'>ID：Name</a>
    """
    href = f"https://nanonet.go.jp/facility.php?mode=detail&code={code}"
    return f"<a href=\"{href}\">{equipment_id}:{equipment_name}</a>"
