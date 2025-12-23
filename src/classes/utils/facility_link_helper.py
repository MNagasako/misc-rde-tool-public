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
    re.compile(r"[A-Za-z]{2}-\d{3}"),  # e.g., NM-005 (case-insensitive)
    re.compile(r"[A-Za-z]{2}-\d{4}"),  # e.g., XX-1234 (future proof)
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
    if re.fullmatch(_ID_PATTERNS[0], t) or re.fullmatch(_ID_PATTERNS[1], t):
        return t.upper()
    return None


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
