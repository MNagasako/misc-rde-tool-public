from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from classes.reports.util.output_paths import find_latest_matching_file, get_reports_root_dir


def extract_task_number_from_report_target_key(target_key: str) -> str:
    """AIログの対象キーからARIM課題番号部分を取り出す。

    対象キーは通常 "<課題番号>|<年度>|<機関コード>" の形式。
    """

    if not target_key:
        return ""
    head = str(target_key).split("|", 1)[0]
    return head.strip()


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join([_stringify(v) for v in value if _stringify(v)])
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value).strip()


def _first_non_empty(record: dict, keys: Iterable[str]) -> str:
    for k in keys:
        v = record.get(k)
        s = _stringify(v)
        if s:
            return s
    return ""


def build_task_number_to_key_technology_areas_index(
    report_records: Iterable[dict],
) -> Dict[str, Tuple[str, str]]:
    """報告書レコード群から、課題番号→(重要技術領域 主, 副) の索引を作る。"""

    rich = build_task_number_to_tech_areas_index(report_records)
    index: Dict[str, Tuple[str, str]] = {}
    for task_number, areas in (rich or {}).items():
        if task_number in index:
            continue
        main_area = _stringify((areas or {}).get("important_main"))
        sub_area = _stringify((areas or {}).get("important_sub"))
        index[task_number] = (main_area, sub_area)
    return index


def build_task_number_to_tech_areas_index(report_records: Iterable[dict]) -> Dict[str, Dict[str, str]]:
    """報告書レコード群から、課題番号→技術領域（重要/横断）の索引を作る。

    Returns:
        {
            <task_number>: {
                'important_main': ...,
                'important_sub': ...,
                'cross_main': ...,
                'cross_sub': ...,
            }
        }
    """

    index: Dict[str, Dict[str, str]] = {}
    for rec in report_records or []:
        if not isinstance(rec, dict):
            continue

        task_number = _first_non_empty(rec, ("課題番号", "ARIMNO", "課題番号 / Project Issue Number"))
        if not task_number:
            continue

        cross_main = _first_non_empty(
            rec,
            (
                "横断技術領域（主）",
                "横断技術領域・主",
                "キーワード【横断技術領域】（主）",
                "キーワード【横断技術領域】(主)",
            ),
        )
        cross_sub = _first_non_empty(
            rec,
            (
                "横断技術領域（副）",
                "横断技術領域・副",
                "キーワード【横断技術領域】（副）",
                "キーワード【横断技術領域】(副)",
            ),
        )

        important_main = _first_non_empty(
            rec,
            (
                "重要技術領域（主）",
                "重要技術領域・主",
                "キーワード【重要技術領域】（主）",
                "キーワード【重要技術領域】(主)",
            ),
        )
        important_sub = _first_non_empty(
            rec,
            (
                "重要技術領域（副）",
                "重要技術領域・副",
                "キーワード【重要技術領域】（副）",
                "キーワード【重要技術領域】(副)",
            ),
        )

        if task_number not in index:
            index[task_number] = {
                "important_main": important_main,
                "important_sub": important_sub,
                "cross_main": cross_main,
                "cross_sub": cross_sub,
            }

    return index


def load_latest_report_records() -> List[dict]:
    """報告書JSON出力（最新）をディスクから読み込み、レコード配列を返す。"""

    base_dir = get_reports_root_dir()
    latest_file = find_latest_matching_file(
        base_dir,
        (
            "output.json",
            "output_*.json",
            "reports_*.json",
            "ARIM-extracted2_*.json",
        ),
    )
    if not latest_file:
        return []

    path = Path(latest_file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        reports = payload.get("reports") or payload.get("data")
        if isinstance(reports, list):
            return [r for r in reports if isinstance(r, dict)]

    return []
