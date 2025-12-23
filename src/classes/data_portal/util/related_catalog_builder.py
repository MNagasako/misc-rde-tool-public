"""Related catalog helpers for Data Portal edit dialog.

This module is intentionally UI-free so it can be unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from typing import Iterable, Optional


def extract_related_dataset_ids(dataset_payload: object) -> list[str]:
    """Extract related dataset ids from a dataset detail JSON.

    Expected shape (JSON:API style):
      payload['data']['relationships']['relatedDatasets']['data'] -> [{'id': '...'}, ...]

    Returns de-duplicated ids preserving order.
    """
    if not isinstance(dataset_payload, dict):
        return []

    data = dataset_payload.get("data")
    if not isinstance(data, dict):
        return []

    relationships = data.get("relationships")
    if not isinstance(relationships, dict):
        return []

    related = relationships.get("relatedDatasets")
    if not isinstance(related, dict):
        return []

    rel_data = related.get("data")
    if not isinstance(rel_data, list):
        return []

    ids: list[str] = []
    seen: set[str] = set()
    for item in rel_data:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            continue
        if raw_id in seen:
            continue
        seen.add(raw_id)
        ids.append(raw_id)

    return ids


def normalize_public_portal_records(payload: object) -> list[dict]:
    """Normalize public portal output JSON into a list of dict records."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]

    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data")
        if isinstance(items, list):
            return [r for r in items if isinstance(r, dict)]

    return []


def _record_dataset_id(record: dict) -> Optional[str]:
    # public output.json では dataset_id が fields/fields_raw 配下に入ることがある
    for key in ("dataset_id", "id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value

    for container_key in ("fields", "fields_raw"):
        container = record.get(container_key)
        if not isinstance(container, dict):
            continue
        value = container.get("dataset_id")
        if isinstance(value, str) and value:
            return value

    # key は data portal のトークンであり dataset_id ではないが、
    # 旧形式の互換のため最後にフォールバックとして扱う
    value = record.get("key")
    if isinstance(value, str) and value:
        return value
    return None


def _record_title(record: dict) -> str:
    value = record.get("title")
    if isinstance(value, str) and value:
        return value
    return _record_dataset_id(record) or ""


def _record_url(record: dict) -> Optional[str]:
    for key in ("detail_url", "url"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def find_related_catalog_candidates(related_dataset_ids: Iterable[str], public_records: Iterable[dict]) -> list[dict]:
    """Find public-portal records for related dataset ids.

    Returns a list of dicts with keys: id, title, detail_url.
    Order follows related_dataset_ids.
    """
    index: dict[str, dict] = {}
    for record in public_records:
        if not isinstance(record, dict):
            continue
        dataset_id = _record_dataset_id(record)
        if not dataset_id:
            continue
        if dataset_id in index:
            continue
        index[dataset_id] = record

    out: list[dict] = []
    seen: set[str] = set()
    for rid in related_dataset_ids:
        if not isinstance(rid, str) or not rid:
            continue
        if rid in seen:
            continue
        seen.add(rid)
        record = index.get(rid)
        if not record:
            continue
        out.append(
            {
                "id": rid,
                "title": _record_title(record),
                "detail_url": _record_url(record),
            }
        )

    return out


def build_related_catalog_html(
    candidates: Iterable[dict],
    *,
    selected_ids: Optional[set[str]] = None,
    header_text: Optional[str] = None,
    header_tag: str = "h2",
) -> str:
    """Build an HTML snippet listing selected candidates.

    The result is intended to be placed into the "装置・プロセス" text cell.
    """
    items: list[str] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        dataset_id = c.get("id")
        if not isinstance(dataset_id, str) or not dataset_id:
            continue
        if selected_ids is not None and dataset_id not in selected_ids:
            continue

        title = c.get("title")
        if not isinstance(title, str) or not title:
            title = dataset_id

        url = c.get("detail_url")
        if isinstance(url, str) and url:
            items.append(f'<li><a href="{escape(url, quote=True)}">{escape(title)}</a>')
        else:
            items.append(f"<li>{escape(title)}")

    if not items:
        return ""

    tag = (header_tag or "").strip().lower()
    # 文字/数字のみのシンプルなタグに限定（安全側）。不正値はh2へフォールバック。
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9]*", tag):
        tag = "h2"

    normalized_header_text = "関連データカタログ"
    if isinstance(header_text, str) and header_text.strip():
        normalized_header_text = header_text.strip()

    # Data Portal 側の表示都合に合わせて、通常は非表示・subSetDetail では表示するHTMLを生成
    style_html = (
        f"<style>ul,{tag}.onlyDetail{{display:none}}"
        f".subSetDetail ul,.subSetDetail {tag}.onlyDetail{{display:block}}"
        f"ul+br,{tag}.onlyDetail+br{{display:none}}</style>"
    )
    header_html = f"<{tag} class=\"onlyDetail\">{escape(normalized_header_text)}</{tag}>"
    return style_html + header_html + "<ul>" + "".join(items) + "</ul>"
