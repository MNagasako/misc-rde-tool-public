"""設備一覧スクレイパー

facility.php?mode=search のページネーションを解析し、
全件取得時に必要な設備IDリストを提供する。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from net.http_helpers import proxy_get

logger = logging.getLogger(__name__)

BASE_URL = "https://nanonet.go.jp"
DEFAULT_QUERY = {
    "mode": "search",
    "mode2": "",
    "code": "0",
    "display_result": "2",  # 100件表示
}
LISTING_PER_PAGE = 100
PAGINATION_SELECTOR = ".pageNavBox .pageNav a[href*='page=']"

LogCallback = Optional[Callable[[str], None]]
CancelChecker = Optional[Callable[[], bool]]


@dataclass
class FacilityListingSummary:
    """設備一覧のサマリ情報"""

    total_count: int
    final_page: int


class FacilityListingScraper:
    """設備一覧ページを解析するスクレイパー"""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.list_url = f"{self.base_url}/facility.php"
        self.default_query = DEFAULT_QUERY.copy()

    def get_listing_summary(self) -> Optional[FacilityListingSummary]:
        """総件数と最終ページを取得"""
        try:
            html = self._fetch_page_html(1)
            soup = BeautifulSoup(html, "html.parser")
            total = self._extract_total_count(soup)
            final_page = self._extract_final_page(soup)

            if total is None and final_page is None:
                return None

            if final_page is None and total is not None:
                final_page = max(1, math.ceil(total / LISTING_PER_PAGE))
            if total is None and final_page is not None:
                total = final_page * LISTING_PER_PAGE

            summary = FacilityListingSummary(total_count=total, final_page=final_page)
            logger.info(
                "設備一覧サマリ: total=%s, final_page=%s",
                summary.total_count,
                summary.final_page,
            )
            return summary
        except Exception as exc:  # pragma: no cover - ログ用
            logger.error("設備一覧サマリ取得エラー: %s", exc)
            return None

    def collect_facility_ids(
        self,
        start_page: int = 1,
        end_page: Optional[int] = None,
        log_callback: LogCallback = None,
        cancel_checker: CancelChecker = None,
    ) -> list[int]:
        """設備IDをページ単位で収集"""

        if end_page is not None and end_page < start_page:
            end_page = start_page

        current_page = max(1, start_page)
        collected: list[int] = []

        while True:
            if cancel_checker and cancel_checker():
                logger.info("設備ID収集がキャンセルされました (page=%s)", current_page)
                break

            try:
                html = self._fetch_page_html(current_page)
            except Exception as exc:  # pragma: no cover - ログ用
                logger.error("設備一覧の取得に失敗しました (page=%s): %s", current_page, exc)
                break

            page_ids = self._extract_ids_from_page(html)
            collected.extend(page_ids)

            message = f"設備一覧 page {current_page}: {len(page_ids)} 件"
            logger.debug(message)
            if log_callback:
                log_callback(message)

            if end_page is not None and current_page >= end_page:
                break
            if end_page is None and len(page_ids) < LISTING_PER_PAGE:
                break

            current_page += 1

        return self._unique_preserve_order(collected)

    # -------------------------------
    # internal helpers
    # -------------------------------

    def _build_url(self, page: int) -> str:
        query = self.default_query.copy()
        query["page"] = str(max(1, page))
        return f"{self.list_url}?{urlencode(query)}"

    def _fetch_page_html(self, page: int) -> str:
        url = self._build_url(page)
        response = proxy_get(url)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {url}")
        response.encoding = "utf-8"
        return response.text

    def _extract_total_count(self, soup: BeautifulSoup) -> Optional[int]:
        dt_tag = soup.select_one(".pageNavBox dt")
        if not dt_tag:
            return None
        text = dt_tag.get_text(strip=True)
        for part in text.split():
            if part.endswith("件中"):
                number = part[:-2]
                if number.isdigit():
                    return int(number)
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None

    def _extract_final_page(self, soup: BeautifulSoup) -> Optional[int]:
        max_page = 0
        for link in soup.select(PAGINATION_SELECTOR):
            href = str(link.get("href") or "")
            if "page=" not in href:
                continue
            try:
                value = href.split("page=")[1].split("&")[0]
                max_page = max(max_page, int(value))
            except (ValueError, IndexError):
                continue
        return max_page or None

    def _extract_ids_from_page(self, html: str) -> list[int]:
        soup = BeautifulSoup(html, "html.parser")
        ids: list[int] = []
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if "facility.php" not in href or "mode=detail" not in href:
                continue
            if "code=" not in href:
                continue
            try:
                code_part = href.split("code=")[1]
                facility_id = code_part.split("&")[0]
                if facility_id.isdigit():
                    ids.append(int(facility_id))
            except (IndexError, ValueError):
                continue
        return ids

    @staticmethod
    def _unique_preserve_order(values: Sequence[int]) -> list[int]:
        seen = set()
        ordered: list[int] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered
