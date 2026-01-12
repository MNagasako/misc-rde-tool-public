"""Dataset date display helpers.

Provides:
- ISO8601(UTC) -> JST formatting
- Loading dataset.json for missing attributes
- QLabel updater bound to QComboBox selection

This module is UI-focused and uses ThemeManager for dynamic theme updates.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
import weakref

from config.common import get_dynamic_file_path

try:
    from qt_compat.core import Qt
    from qt_compat.widgets import QComboBox, QLabel
except Exception:  # pragma: no cover
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QComboBox, QLabel

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color

_JST = timezone(timedelta(hours=9))
_UTC = timezone.utc


@dataclass(frozen=True)
class DatasetDateInfo:
    created: str
    modified: str
    open_at: str


_DATASET_JSON_CACHE: dict[str, Any] = {
    "path": None,
    "mtime": None,
    "by_id": {},
}


def _parse_iso_datetime_utc(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_UTC)
        return dt.astimezone(_UTC)
    except Exception:
        return None


def format_iso_to_jst(value: str, *, with_seconds: bool = True) -> str:
    dt = _parse_iso_datetime_utc(value)
    if not dt:
        return ""
    jst = dt.astimezone(_JST)
    fmt = "%Y-%m-%d %H:%M:%S JST" if with_seconds else "%Y-%m-%d %H:%M JST"
    return jst.strftime(fmt)


def _load_dataset_json_index() -> dict[str, dict]:
    path = get_dynamic_file_path("output/rde/data/dataset.json")
    try:
        mtime = os.path.getmtime(path) if os.path.exists(path) else None
    except Exception:
        mtime = None

    if _DATASET_JSON_CACHE.get("path") == path and _DATASET_JSON_CACHE.get("mtime") == mtime:
        by_id = _DATASET_JSON_CACHE.get("by_id")
        if isinstance(by_id, dict):
            return by_id

    by_id: dict[str, dict] = {}
    if not path or not os.path.exists(path):
        _DATASET_JSON_CACHE["path"] = path
        _DATASET_JSON_CACHE["mtime"] = mtime
        _DATASET_JSON_CACHE["by_id"] = by_id
        return by_id

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        items = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(items, list):
            for ds in items:
                if isinstance(ds, dict) and ds.get("id"):
                    by_id[str(ds.get("id"))] = ds
    except Exception:
        by_id = {}

    _DATASET_JSON_CACHE["path"] = path
    _DATASET_JSON_CACHE["mtime"] = mtime
    _DATASET_JSON_CACHE["by_id"] = by_id
    return by_id


def _extract_attrs(dataset_like: Any) -> dict[str, Any]:
    if not isinstance(dataset_like, dict):
        return {}
    if "attributes" in dataset_like and isinstance(dataset_like.get("attributes"), dict):
        return dataset_like.get("attributes") or {}

    # dataset detail payload (JSON:API): {"data": {"attributes": ...}}
    data = dataset_like.get("data")
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        return data.get("attributes") or {}

    return {}


def resolve_dataset_date_info(combo_data: Any) -> DatasetDateInfo:
    dataset_like = combo_data

    dataset_id: Optional[str] = None
    if isinstance(combo_data, dict):
        dataset_id = str(combo_data.get("id") or "") or None
    elif isinstance(combo_data, str):
        dataset_id = combo_data.strip() or None

    attrs = _extract_attrs(dataset_like)

    created = str(attrs.get("created") or attrs.get("createdAt") or "")
    modified = str(attrs.get("modified") or attrs.get("modifiedAt") or "")
    open_at = str(attrs.get("openAt") or "")

    if dataset_id and (not created or not modified or not open_at):
        by_id = _load_dataset_json_index()
        ds = by_id.get(dataset_id)
        if isinstance(ds, dict):
            attrs2 = _extract_attrs(ds)
            created = created or str(attrs2.get("created") or attrs2.get("createdAt") or "")
            modified = modified or str(attrs2.get("modified") or attrs2.get("modifiedAt") or "")
            open_at = open_at or str(attrs2.get("openAt") or "")

    return DatasetDateInfo(created=created, modified=modified, open_at=open_at)


def apply_dataset_dates_label_theme(label: QLabel) -> None:
    label.setStyleSheet(
        " ".join(
            [
                f"color: {get_color(ThemeKey.TEXT_SECONDARY)};",
                "font-size: 9pt;",
                "margin-left: 2px;",
            ]
        )
    )


def bind_dataset_dates_label_to_theme(label: QLabel) -> None:
    label_ref = weakref.ref(label)

    try:
        tm = ThemeManager.instance()
    except Exception:
        return

    def _on_theme_changed(*_args) -> None:
        lbl = label_ref()
        if lbl is None:
            return
        try:
            from shiboken6 import isValid  # type: ignore

            if not isValid(lbl):
                return
        except Exception:
            # shiboken6 が利用できない場合は best-effort
            pass

        try:
            apply_dataset_dates_label_theme(lbl)
        except Exception:
            return

    try:
        tm.theme_changed.connect(_on_theme_changed)
    except Exception:
        return

    # 破棄後に theme_changed が飛ぶと Internal C++ object already deleted になるため切断する
    def _disconnect_theme_changed(*_args) -> None:
        try:
            tm.theme_changed.disconnect(_on_theme_changed)
        except Exception:
            # ThemeManager が先に破棄されるなど、Qtオブジェクト破棄順序の差で
            # "Signal source has been deleted" が出ることがあるため best-effort で握りつぶす
            pass

    try:
        label.destroyed.connect(_disconnect_theme_changed)
    except Exception:
        return


def create_dataset_dates_label(parent=None) -> QLabel:
    label = QLabel(parent)
    label.setObjectName("datasetDatesLabel")
    label.setWordWrap(True)
    apply_dataset_dates_label_theme(label)
    bind_dataset_dates_label_to_theme(label)
    return label


def update_dataset_dates_label(label: QLabel, combo_data: Any) -> None:
    info = resolve_dataset_date_info(combo_data)

    created = format_iso_to_jst(info.created) or "--"
    modified = format_iso_to_jst(info.modified) or "--"
    open_at = format_iso_to_jst(info.open_at) or "--"

    label.setText(f"開設日: {created}    更新日: {modified}    公開日: {open_at}")


def attach_dataset_dates_label(
    *,
    combo: QComboBox,
    label: QLabel,
    data_role: Optional[int] = None,
) -> None:
    def _current_data() -> Any:
        idx = combo.currentIndex()
        if idx < 0:
            return None
        try:
            if data_role is None:
                return combo.itemData(idx)
            return combo.itemData(idx, data_role)
        except Exception:
            return None

    def _refresh(*_args) -> None:
        update_dataset_dates_label(label, _current_data())

    combo.currentIndexChanged.connect(_refresh)
    _refresh()
