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


def build_log_path(target_kind: str, button_id: str, target_key: str) -> str:
    kind = 'report' if (target_kind or '').strip().lower() == 'report' else 'dataset'
    bid = _safe_filename(button_id)
    tkey = _safe_filename(target_key)
    rel = f"output/ai_suggest_logs/{kind}/{bid}/{tkey}.jsonl"
    return get_dynamic_file_path(rel)


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
    }

    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return path


def read_latest_result(target_kind: str, target_key: str, button_id: str) -> Optional[Dict[str, Any]]:
    """Return the latest logged result record for target+button, if exists."""
    path = build_log_path(target_kind, button_id, target_key)
    return _read_latest_record_from_jsonl(path)


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
        s = re.sub(r'\.\d+(?=[+-]\\d\d:\\d\d$)', '', s)
        return s

    results.sort(key=_ts_key, reverse=True)
    return results
