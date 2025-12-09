"""
設備データ取得 - フェッチ範囲ビルダー

全件取得モード用のIDスキャンロジックを提供します。
"""

from __future__ import annotations

import logging
import math
from typing import Callable, Optional

from classes.equipment.core.facility_listing import (
    FacilityListingScraper,
    LISTING_PER_PAGE,
)

logger = logging.getLogger(__name__)

LogCallback = Optional[Callable[[str], None]]
CancelChecker = Optional[Callable[[], bool]]


def collect_valid_facility_ids(
    start_id: int,
    end_id: int,
    chunk_size: int,
    stop_threshold: int,
    log_callback: LogCallback = None,
    cancel_checker: CancelChecker = None,
    listing_scraper: Optional[FacilityListingScraper] = None,
) -> list[int]:
    """設備一覧のページネーションを使って有効な設備IDを収集する

    Args:
        start_id: 取得対象の開始設備ID
        end_id: 取得対象の終了設備ID
        chunk_size: ページ単位換算用のID件数（通常は100件）
        stop_threshold: 互換性維持用パラメータ（現行実装ではページスキャン停止条件に利用）
        log_callback: ログ出力用コールバック
        cancel_checker: キャンセル状態を返すコールバック
        listing_scraper: FacilityListingScraper インスタンス（未指定の場合は自動生成）

    Returns:
        list[int]: 設備一覧ページから収集した設備IDのリスト
    """

    if start_id > end_id:
        logger.warning("start_id が end_id より大きいため、空のリストを返します")
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if stop_threshold <= 0:
        raise ValueError("stop_threshold must be positive")

    log = log_callback or (lambda _msg: None)
    is_cancelled = cancel_checker or (lambda: False)
    scraper = listing_scraper or FacilityListingScraper()

    start_page = max(1, math.ceil(start_id / chunk_size))
    requested_end_page = max(start_page, math.ceil(end_id / chunk_size))

    log(
        f"🔍 設備一覧モード: display_result=2 / 1ページ {LISTING_PER_PAGE}件"
    )

    summary = scraper.get_listing_summary()
    if summary:
        end_page = min(requested_end_page, summary.final_page)
        log(
            f"📋 設備一覧サマリ: 総件数 {summary.total_count} 件 / 最終ページ {summary.final_page}"
        )
    else:
        end_page = requested_end_page
        log("⚠ 設備一覧サマリの取得に失敗したため、指定ページ範囲のみスキャンします")

    if end_page < start_page:
        log("⚠ 指定範囲に該当するページがありません")
        return []

    max_empty_pages = max(1, math.ceil(stop_threshold / chunk_size))
    current_empty_pages = 0
    collected_ids: list[int] = []

    for page in range(start_page, end_page + 1):
        if is_cancelled():
            log("⚠ キャンセルされました")
            break

        page_ids = scraper.collect_facility_ids(
            start_page=page,
            end_page=page,
            log_callback=log,
            cancel_checker=is_cancelled,
        )

        if page_ids:
            current_empty_pages = 0
            collected_ids.extend(page_ids)
        else:
            current_empty_pages += 1
            if current_empty_pages >= max_empty_pages:
                log(
                    f"✋ {LISTING_PER_PAGE * current_empty_pages}件分の設備が連続で見つからなかったため停止"
                )
                break

        if len(page_ids) < LISTING_PER_PAGE:
            # 最終ページに到達したと判断
            break

    unique_ids = list(dict.fromkeys(collected_ids))
    log(f"✅ 有効な設備ID: {len(unique_ids)}件")
    return unique_ids
