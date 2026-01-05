"""AIサジェスト結果ログ

- データセット/報告書ごと
- ボタンIDごと
- 取得日時ごと

の結果を保存し、同一対象+同一ボタンの既存結果を参照できるようにする。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.common import get_dynamic_file_path


def _safe_filename(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return "unknown"
    # Windows safe-ish
    for ch in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        s = s.replace(ch, '_')
    s = s.replace(' ', '_')
    s = s.strip('._')
    return s[:180] if len(s) > 180 else s


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def _extract_report_arimno(target_key: str) -> str:
    """報告書ログのファイル名はARIMNOのみとする。

    旧実装では target_key が 'ARIMNO|年度|機関コード' など複合だったため、
    先頭要素（ARIMNO）を抽出して返す。
    """
    text = (target_key or '').strip()
    if not text:
        return "unknown"

    # 新/旧両方を想定: 'ARIM|2024|A01' / 'ARIM_2024_A01'
    if '|' in text:
        head = (text.split('|', 1)[0] or '').strip()
        return head or "unknown"
    if '_' in text:
        head = (text.split('_', 1)[0] or '').strip()
        return head or "unknown"
    return text


def _iter_candidate_report_log_paths(button_id: str, target_key: str) -> List[str]:
    """報告書ログの候補パス（新形式 + 旧形式）を返す。"""
    bid = _safe_filename(button_id)
    arimno = _safe_filename(_extract_report_arimno(target_key))

    base_rel = f"output/ai_suggest_logs/report/{bid}"
    base_dir = get_dynamic_file_path(base_rel)

    candidates: List[str] = []

    # 新形式（ARIMNO.jsonl）
    candidates.append(os.path.join(base_dir, f"{arimno}.jsonl"))

    # 旧形式（ARIMNO_*.jsonl）も拾う
    try:
        if os.path.exists(base_dir):
            for fn in os.listdir(base_dir):
                if not fn.lower().endswith('.jsonl'):
                    continue
                if fn == f"{arimno}.jsonl":
                    continue
                if fn.startswith(f"{arimno}_"):
                    candidates.append(os.path.join(base_dir, fn))
    except Exception:
        pass

    # 実在するものを優先（重複除去）
    seen = set()
    existing: List[str] = []
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        if os.path.exists(p):
            existing.append(p)

    return existing


def build_log_path(target_kind: str, button_id: str, target_key: str) -> str:
    kind = 'report' if (target_kind or '').strip().lower() == 'report' else 'dataset'
    bid = _safe_filename(button_id)
    if kind == 'report':
        tkey = _safe_filename(_extract_report_arimno(target_key))
    else:
        tkey = _safe_filename(target_key)
    rel = f"output/ai_suggest_logs/{kind}/{bid}/{tkey}.jsonl"
    return get_dynamic_file_path(rel)


def resolve_log_path(target_kind: str, button_id: str, target_key: str) -> str:
    """ログファイルのパスを解決して返す。

    - dataset: build_log_path() のみ
    - report: 新形式（ARIMNO.jsonl）を優先し、存在しない場合は旧形式（ARIMNO_*.jsonl）も探索

    存在するファイルが見つからない場合でも、想定されるパス（build_log_path）を返す。
    """
    kind = 'report' if (target_kind or '').strip().lower() == 'report' else 'dataset'
    direct = build_log_path(kind, button_id, target_key)
    if kind != 'report':
        return direct

    try:
        if os.path.exists(direct):
            return direct
    except Exception:
        pass

    try:
        for p in _iter_candidate_report_log_paths(button_id, target_key):
            return p
    except Exception:
        pass

    return direct


def append_result(
    *,
    target_kind: str,
    target_key: str,
    button_id: str,
    button_label: str,
    prompt: str,
    display_format: str,
    display_content: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    request_params: Optional[Dict[str, Any]] = None,
    response_params: Optional[Dict[str, Any]] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> str:
    """Append a result to per-target+button log (jsonl). Returns log file path."""
    path = build_log_path(target_kind, button_id, target_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    record: Dict[str, Any] = {
        'timestamp': _now_iso(),
        'target_kind': 'report' if (target_kind or '').strip().lower() == 'report' else 'dataset',
        'target_key': target_key,
        'button_id': button_id,
        'button_label': button_label,
        'prompt': prompt,
        'display_format': display_format,  # 'html' or 'text'
        'display_content': display_content,
        'provider': provider,
        'model': model,
        'request_params': request_params,
        'response_params': response_params,
        'started_at': started_at,
        'finished_at': finished_at,
        'elapsed_seconds': elapsed_seconds,
    }

    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return path


def read_latest_result(target_kind: str, target_key: str, button_id: str) -> Optional[Dict[str, Any]]:
    """Return the latest logged result record for target+button, if exists."""
    kind = 'report' if (target_kind or '').strip().lower() == 'report' else 'dataset'
    if kind != 'report':
        path = build_log_path(target_kind, button_id, target_key)
        return _read_latest_record_from_jsonl(path)

    # report: 新形式 + 旧形式を横断して最新を返す
    direct_path = build_log_path(target_kind, button_id, target_key)
    direct = _read_latest_record_from_jsonl(direct_path)
    if isinstance(direct, dict):
        return direct

    best: Optional[Dict[str, Any]] = None
    best_ts = ''
    for path in _iter_candidate_report_log_paths(button_id, target_key):
        rec = _read_latest_record_from_jsonl(path)
        if not isinstance(rec, dict):
            continue
        ts = (rec.get('timestamp') or '').strip()
        ts = re.sub(r'\.\d+(?=[+-][0-9]{2}:[0-9]{2}$)', '', ts)
        if ts and ts > best_ts:
            best_ts = ts
            best = rec
        elif not best and rec:
            best = rec
    return best


def _read_latest_record_from_jsonl(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    last_line = None
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return None
            read_size = min(size, 65536)
            f.seek(-read_size, os.SEEK_END)
            chunk = f.read(read_size)
        lines = chunk.splitlines()
        if not lines:
            return None
        last_line = lines[-1].decode('utf-8', errors='replace')
        return json.loads(last_line)
    except Exception:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        last_line = line
            if not last_line:
                return None
            return json.loads(last_line)
        except Exception:
            return None


def list_latest_results(target_kind: str, button_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return latest result records under output/ai_suggest_logs.

    - target_kind: 'report' or 'dataset'
    - button_id: optional filter

    Each log file stores results for (target_kind, button_id, target_key).
    This function returns the latest record for each log file.
    """
    kind = 'report' if (target_kind or '').strip().lower() == 'report' else 'dataset'
    base_rel = f"output/ai_suggest_logs/{kind}"
    base_dir = get_dynamic_file_path(base_rel)
    if not os.path.exists(base_dir):
        return []

    results: List[Dict[str, Any]] = []
    bid_filter = (button_id or '').strip()
    if bid_filter:
        # folder name is safe_filename(button_id)
        base_dir = os.path.join(base_dir, _safe_filename(bid_filter))
        if not os.path.exists(base_dir):
            return []

    for root, _dirs, files in os.walk(base_dir):
        for fn in files:
            if not fn.lower().endswith('.jsonl'):
                continue
            path = os.path.join(root, fn)
            rec = _read_latest_record_from_jsonl(path)
            if not isinstance(rec, dict):
                continue
            if rec.get('target_kind') != kind:
                continue
            if bid_filter and rec.get('button_id') != bid_filter:
                continue
            results.append(rec)

    # ISO timestamp sort (desc). Missing timestamps go last.
    def _ts_key(r: Dict[str, Any]) -> str:
        s = (r.get('timestamp') or '').strip()
        # normalize to improve ordering if fractional seconds vary
        s = re.sub(r'\.\d+(?=[+-][0-9]{2}:[0-9]{2}$)', '', s)
        return s

    results.sort(key=_ts_key, reverse=True)
    return results
