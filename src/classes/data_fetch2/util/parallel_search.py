"""データ取得2の検索高速化ユーティリティ。"""

from __future__ import annotations

import os
from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")


def suggest_parallel_workers() -> int:
    """CPUコア数に応じた推奨並列数を返す。"""
    cpu_count = os.cpu_count() or 4
    return max(2, min(8, int(cpu_count)))


def resolve_parallel_workers(value: int | None) -> int:
    """UI入力値から実効並列数を解決する（0/Noneは自動）。"""
    parsed = int(value or 0)
    if parsed <= 0:
        return suggest_parallel_workers()
    return max(1, parsed)


def parallel_filter(
    records: list[T],
    predicate: Callable[[T], bool],
    *,
    max_workers: int,
    min_parallel_size: int = 200,
    cancel_checker: Callable[[], bool] | None = None,
) -> list[T]:
    """条件に一致するレコードを並列で抽出する。"""
    workers = max(1, int(max_workers))
    total = len(records)
    if workers <= 1 or total < int(min_parallel_size):
        filtered: list[T] = []
        for rec in records:
            if callable(cancel_checker) and cancel_checker():
                break
            if predicate(rec):
                filtered.append(rec)
        return filtered

    chunk_size = max(200, total // (workers * 4))
    if chunk_size <= 0:
        chunk_size = total

    def _filter_chunk(chunk: list[T]) -> list[T]:
        return [rec for rec in chunk if predicate(rec)]

    chunks: list[list[T]] = [records[i : i + chunk_size] for i in range(0, total, chunk_size)]
    filtered: list[T] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_filter_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            if callable(cancel_checker) and cancel_checker():
                for pending in futures:
                    pending.cancel()
                break
            filtered.extend(future.result())

    return filtered
