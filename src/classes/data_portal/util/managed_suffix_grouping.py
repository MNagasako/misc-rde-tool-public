from __future__ import annotations

import re
from typing import Any


_SUFFIX_RE = re.compile(r"^(?P<prefix>managed:)(?P<base>.+?)(?P<num>[0-9]+)$")


def add_grouped_suffix_columns(rows: list[dict[str, Any]]) -> set[str]:
    """Collapse managed numeric-suffix columns into grouped multiline columns.

    Examples (keys):
    - managed:装置1..managed:装置5 -> managed_group:装置 with values joined by '\n'
    - managed:プロセス1..managed:プロセス5 -> managed_group:プロセス

    - Empty values are skipped.
    - Rows are mutated in-place.

    Returns:
        A set of member keys that should be suppressed from column definitions.
    """

    all_keys: set[str] = set()
    for r in rows or []:
        if isinstance(r, dict):
            all_keys.update(str(k) for k in r.keys())

    groups: dict[str, list[tuple[int, str]]] = {}
    for k in all_keys:
        m = _SUFFIX_RE.match(str(k))
        if not m:
            continue
        base = str(m.group("base") or "").strip()
        num_s = str(m.group("num") or "").strip()
        if not base or not num_s:
            continue
        try:
            num = int(num_s)
        except Exception:
            continue
        groups.setdefault(base, []).append((num, str(k)))

    suppressed: set[str] = set()
    effective_groups = {base: sorted(items, key=lambda t: t[0]) for base, items in groups.items() if len(items) >= 2}
    if not effective_groups:
        return suppressed

    for base, items in effective_groups.items():
        member_keys = [k for _n, k in items]
        suppressed.update(member_keys)
        grouped_key = f"managed_group:{base}"

        for row in rows or []:
            if not isinstance(row, dict):
                continue
            values: list[str] = []
            for k in member_keys:
                v = row.get(k, "")
                s = str(v or "").strip()
                if s:
                    values.append(s)
            if values:
                row[grouped_key] = "\n".join(values)

    return suppressed
