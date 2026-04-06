"""更新履歴タブ向けのリリースノート生成ユーティリティ。"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from config.common import get_base_dir, get_static_resource_path, is_binary_execution

logger = logging.getLogger(__name__)

_RELEASE_HEADER_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+v(?P<version>\d+\.\d+\.\d+)\s*-\s*(?P<summary>.+?)\s*$"
)
_VERSION_MARKER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class ReleaseNoteEntry:
    """VERSION.txt から抽出した 1 リリース分の情報。"""

    release_date: str
    version: str
    summary: str
    details: list[str] = field(default_factory=list)


def _get_version_file_path() -> str:
    if is_binary_execution():
        return get_static_resource_path("VERSION.txt")
    return os.path.join(get_base_dir(), "VERSION.txt")


def _normalize_detail_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("-"):
        return stripped[1:].strip()
    return stripped


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except Exception:
        return (0, 0, 0)


def _parse_release_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return datetime.min


def _sort_entries(entries: list[ReleaseNoteEntry]) -> list[ReleaseNoteEntry]:
    return sorted(
        entries,
        key=lambda entry: (_parse_release_date(entry.release_date), _parse_version_tuple(entry.version)),
        reverse=True,
    )


def parse_version_history(version_text: str) -> list[ReleaseNoteEntry]:
    """VERSION.txt の本文からリリース履歴を抽出する。"""

    entries: list[ReleaseNoteEntry] = []
    current: ReleaseNoteEntry | None = None

    for raw_line in version_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        header_match = _RELEASE_HEADER_RE.match(stripped)
        if header_match:
            if current is not None:
                entries.append(current)
            current = ReleaseNoteEntry(
                release_date=header_match.group("date"),
                version=header_match.group("version"),
                summary=header_match.group("summary"),
            )
            continue

        if _VERSION_MARKER_RE.match(stripped):
            continue

        if current is None:
            continue

        if re.match(r"^\s*[-・]\s+", raw_line):
            detail = _normalize_detail_line(stripped)
            if detail:
                current.details.append(detail)

    if current is not None:
        entries.append(current)

    return _sort_entries(entries)


def load_release_note_entries() -> list[ReleaseNoteEntry]:
    """VERSION.txt を読み込んでリリース履歴を返す。"""

    version_file = _get_version_file_path()
    with open(version_file, "r", encoding="utf-8") as handle:
        return parse_version_history(handle.read())


def build_release_notes_markdown(max_entries: int | None = None) -> str:
    """VERSION.txt 正本から更新履歴タブ用 Markdown を生成する。"""

    entries = load_release_note_entries()
    if max_entries is not None:
        entries = entries[:max_entries]

    if not entries:
        return "# 更新履歴\n\nVERSION.txt から更新履歴を生成できませんでした。"

    lines = ["# 更新履歴", ""]
    for entry in entries:
        lines.extend(_format_entry_lines(entry))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_entry_lines(entry: ReleaseNoteEntry) -> list[str]:
    lines = [
        f"## v{entry.version}",
        "",
        f"- 日付: {entry.release_date}",
        f"- 概要: {entry.summary}",
    ]
    return lines