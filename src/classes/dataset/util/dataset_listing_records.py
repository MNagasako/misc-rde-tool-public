"""Dataset listing helpers for AISuggestionDialog dataset tab.

This module provides:
- dataset.json loading
- optional info.json user map loading
- ARIM grant number parsing (year / institute code)
- derived fields needed for the dataset tab table

UI code should keep raw dataset items attached so that existing context update
logic can consume dataset.json-shaped dicts.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_GRANT_NUMBER_RE = re.compile(r"^JPMXP12(?P<yy>\d{2})(?P<inst>[A-Z0-9]{2})(?P<num>\d{4})$")


def parse_grant_number_year_and_inst_code(grant_number: str) -> Tuple[str, str]:
    """Parse ARIM grant number to derive (year, institute_code).

    Expected format: JPMXP12yyZZnnnn
      - yy: 2-digit western year (e.g., 24 -> 2024)
      - ZZ: institute code (2 chars)
      - nnnn: 4-digit zero-padded serial

    Returns empty strings when the input does not match the expected pattern.
    """

    text = (grant_number or "").strip()
    if not text:
        return "", ""
    match = _GRANT_NUMBER_RE.match(text)
    if not match:
        return "", ""

    yy = match.group("yy")
    inst = match.group("inst")

    try:
        year = 2000 + int(yy)
        year_text = str(year)
    except Exception:
        year_text = ""

    return year_text, inst


def _load_json_file(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def load_dataset_items(dataset_json_path: str) -> List[Dict[str, Any]]:
    """Load dataset.json and return its item list (dataset dicts)."""

    payload = _load_json_file(dataset_json_path)
    if payload is None:
        return []

    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload.get("data") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    return [it for it in items if isinstance(it, dict)]


def build_user_name_map(info_json_path: Optional[str]) -> Dict[str, str]:
    """Build a {user_id: user_name} map from info.json when possible.

    info.json format varies across environments; this function is defensive.
    Supported shapes (best-effort):
      - {"data": [{"id": "...", "attributes": {"userName": "..."}}]}
      - [{"id": "...", "attributes": {"userName": "..."}}]
      - {"<id>": {"userName": "..."}}  (legacy-ish)
    """

    if not info_json_path:
        return {}

    payload = _load_json_file(info_json_path)
    if payload is None:
        return {}

    records: List[Dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        data_list = payload.get("data") or []
        records = [r for r in data_list if isinstance(r, dict)]
    elif isinstance(payload, list):
        records = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        # dict keyed by id
        result: Dict[str, str] = {}
        for k, v in payload.items():
            if not isinstance(k, str):
                continue
            if not isinstance(v, dict):
                continue
            name = (v.get("userName") or v.get("name") or "").strip() if isinstance(v, dict) else ""
            if name:
                result[k] = name
        return result

    result: Dict[str, str] = {}
    for rec in records:
        user_id = (rec.get("id") or "").strip()
        attrs = rec.get("attributes") if isinstance(rec.get("attributes"), dict) else {}
        user_name = (attrs.get("userName") or attrs.get("name") or "").strip() if isinstance(attrs, dict) else ""
        if user_id and user_name:
            result[user_id] = user_name

    return result


def extract_dataset_template_id(dataset_item: Dict[str, Any]) -> str:
    """Extract dataset template id from dataset.json item."""

    try:
        rel = dataset_item.get("relationships") if isinstance(dataset_item.get("relationships"), dict) else {}
        tmpl = rel.get("template") if isinstance(rel.get("template"), dict) else {}
        data = tmpl.get("data") if isinstance(tmpl.get("data"), dict) else {}
        template_id = (data.get("id") or "").strip()
        return template_id
    except Exception:
        return ""


def derive_dataset_listing_rows(
    dataset_items: List[Dict[str, Any]],
    user_name_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Convert dataset.json items into listing rows for the dataset tab table.

    Returned rows include a `_raw` entry containing the original dataset item.
    """

    user_name_map = user_name_map or {}

    rows: List[Dict[str, Any]] = []
    for item in dataset_items:
        dataset_id = (item.get("id") or "").strip()
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}

        grant_number = (attrs.get("grantNumber") or "").strip()
        year, inst_code = parse_grant_number_year_and_inst_code(grant_number)

        applicant_name = ""
        try:
            rel = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
            applicant = rel.get("applicant") if isinstance(rel.get("applicant"), dict) else {}
            applicant_data = applicant.get("data") if isinstance(applicant.get("data"), dict) else {}
            applicant_id = (applicant_data.get("id") or "").strip()
            if applicant_id:
                applicant_name = (user_name_map.get(applicant_id) or "").strip()
        except Exception:
            applicant_name = ""

        subject_title = (attrs.get("subjectTitle") or "").strip()
        dataset_name = (attrs.get("name") or "").strip()
        dataset_template = extract_dataset_template_id(item)

        rows.append(
            {
                "dataset_id": dataset_id,
                "grant_number": grant_number,
                "year": year,
                "inst_code": inst_code,
                "applicant": applicant_name,
                "subject_title": subject_title,
                "dataset_name": dataset_name,
                "dataset_template": dataset_template,
                "_raw": item,
            }
        )

    return rows


def load_dataset_listing_rows(dataset_json_path: str, info_json_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Convenience loader for dataset tab."""

    items = load_dataset_items(dataset_json_path)
    user_map = build_user_name_map(info_json_path)
    return derive_dataset_listing_rows(items, user_map)
