"""Invoice edit helpers for dataset data-entry tab.

This module provides pure helpers for merging invoice attributes and building
JSON:API payloads. Network operations are implemented in the UI layer via
`net.http_helpers`.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional


def split_comma_list(text: str | None) -> List[str]:
    if not text:
        return []
    items = [item.strip() for item in text.split(",")]
    return [item for item in items if item]


def _ensure_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def merge_invoice_attributes(
    original_attributes: Dict[str, Any] | None,
    *,
    data_name: Optional[str] = None,
    basic_description: Optional[str] = None,
    experiment_id: Optional[str] = None,
    data_owner_id: Optional[str] = None,
    sample_description: Optional[str] = None,
    sample_composition: Optional[str] = None,
    sample_reference_url: Optional[str] = None,
    sample_names: Optional[List[str]] = None,
    sample_tags: Optional[List[str]] = None,
    custom: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return merged invoice attributes.

    Keeps unknown keys from the original payload to avoid accidental loss.
    Only updates provided fields.
    """

    merged: Dict[str, Any] = deepcopy(original_attributes or {})

    basic = _ensure_dict(merged.get("basic"))
    if data_name is not None:
        basic["dataName"] = data_name
    if basic_description is not None:
        basic["description"] = basic_description
    if experiment_id is not None:
        basic["experimentId"] = experiment_id
    if data_owner_id is not None:
        basic["dataOwnerId"] = data_owner_id
    merged["basic"] = basic

    sample = _ensure_dict(merged.get("sample"))
    if sample_description is not None:
        sample["description"] = sample_description
    if sample_composition is not None:
        sample["composition"] = sample_composition
    if sample_reference_url is not None:
        sample["referenceUrl"] = sample_reference_url
    if sample_names is not None:
        sample["names"] = sample_names
    if sample_tags is not None:
        sample["tags"] = sample_tags
    merged["sample"] = sample

    if custom is not None:
        merged["custom"] = custom

    return merged


def merge_custom_from_schema_form(
    original_custom: Dict[str, Any] | None,
    *,
    schema_keys: Iterable[str],
    current_values: Dict[str, Any] | None,
    initial_values: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Merge schema-based custom inputs into the original custom dict.

    - Keeps unknown (non-schema) keys from original.
    - For schema keys:
        - Non-empty input overwrites as string.
        - If user cleared a previously non-empty value, sets to None.
        - If both initial and current are empty, leaves unchanged.
    """

    merged: Dict[str, Any] = deepcopy(original_custom or {})
    current_values = current_values or {}
    initial_values = initial_values or {}

    for key in schema_keys:
        raw_current = current_values.get(key)
        raw_initial = initial_values.get(key)

        current_text = "" if raw_current is None else str(raw_current)
        initial_text = "" if raw_initial is None else str(raw_initial)

        current_text = current_text.strip()
        initial_text = initial_text.strip()

        if current_text:
            merged[key] = current_text
            continue

        if initial_text:
            merged[key] = None

    return merged


def build_invoice_patch_payload(
    entry_id: str,
    attributes: Dict[str, Any],
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "data": {
            "type": "invoice",
            "id": entry_id,
            "attributes": attributes,
        }
    }
    if isinstance(meta, dict) and meta:
        payload["meta"] = meta
    return payload
