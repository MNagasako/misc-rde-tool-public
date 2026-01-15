"""
報告書機能 - 並列取得モジュール

報告書データを並列ダウンロードし、高速に取得します。

"""

import logging
from typing import List, Dict, Tuple, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .report_scraper import ReportScraper
from .report_cache_manager import ReportCacheManager, ReportCacheMode


logger = logging.getLogger(__name__)


class ParallelReportFetcher:
    """
    報告書並列取得クラス
    
    複数の報告書を並列ダウンロードして高速化します。
    設備タブのParallelFacilityFetcherパターンを踏襲しています。
    """
    
    def __init__(
        self,
        max_workers: int = 5,
        cache_manager: Optional[ReportCacheManager] = None,
        cache_mode: ReportCacheMode = ReportCacheMode.SKIP,
    ):
        """
        初期化
        
        Args:
            max_workers: 並列実行するワーカー数（デフォルト: 5）
        """
        self.max_workers = max_workers
        self.scraper = ReportScraper()
        self.cache_manager = cache_manager or ReportCacheManager()
        self.cache_mode = cache_mode
        logger.info(
            "ParallelReportFetcher初期化: max_workers=%s, cache_mode=%s",
            max_workers,
            self.cache_mode.value,
        )
    
    def fetch_reports(
        self,
        report_links: List[Dict[str, str]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        報告書リストを並列取得
        
        Args:
            report_links: 報告書リンク情報のリスト
                [{"url": "...", "code": "...", "key": "..."}, ...]
            progress_callback: 進捗コールバック関数
                callback(current, total, message)
        
        Returns:
            (success_data, error_data) のタプル
            - success_data: 取得成功した報告書データ
            - error_data: 取得失敗した報告書情報（エラー情報付き）
        
        Examples:
            >>> fetcher = ParallelReportFetcher(max_workers=5)
            >>> links = [{"url": "...", "code": "001", "key": "KEY001"}, ...]
            >>> success, errors = fetcher.fetch_reports(links, progress_callback)
            >>> print(f"成功: {len(success)}, 失敗: {len(errors)}")
        """
        logger.info(f"並列取得開始: {len(report_links)} 件")

        success_data: List[Dict] = []
        error_data: List[Dict] = []
        total = len(report_links)

        self._safe_progress(progress_callback, 0, total, "並列取得を開始します...")

        pending_links, cache_hits = self._apply_cache_hits(
            report_links,
            success_data,
            total,
            progress_callback,
        )
        completed = len(success_data)

        if pending_links:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._fetch_single, link): link
                    for link in pending_links
                }

                for future in as_completed(futures):
                    link = futures[future]
                    completed += 1

                    try:
                        result = future.result()

                        if result:
                            success_data.append(result)
                            self._save_to_cache(result)
                            code = link.get('code', 'unknown')
                            self._safe_progress(
                                progress_callback,
                                completed,
                                total,
                                f"✓ 取得成功: code={code} ({completed}/{total})",
                            )
                        else:
                            error_data.append({
                                "link": link,
                                "error": "Failed to fetch report",
                            })
                            code = link.get('code', 'unknown')
                            self._safe_progress(
                                progress_callback,
                                completed,
                                total,
                                f"✗ 取得失敗: code={code} ({completed}/{total})",
                            )

                    except Exception as e:
                        logger.error(f"タスク実行エラー ({link}): {e}")
                        error_data.append({
                            "link": link,
                            "error": str(e),
                        })
                        code = link.get('code', 'unknown')
                        self._safe_progress(
                            progress_callback,
                            completed,
                            total,
                            f"⚠ エラー: code={code} - {str(e)[:50]}",
                        )
        else:
            logger.info("取得対象は全件キャッシュ再利用されました")

        logger.info(
            "並列取得完了: 成功=%s, 失敗=%s, キャッシュ再利用=%s",
            len(success_data),
            len(error_data),
            cache_hits,
        )

        self._safe_progress(
            progress_callback,
            total,
            total,
            f"完了: 成功={len(success_data)}, 失敗={len(error_data)}",
        )

        return success_data, error_data
    
    def fetch_range(
        self,
        start_page: int = 1,
        max_pages: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        指定範囲のページから報告書を並列取得
        
        Args:
            start_page: 開始ページ番号
            max_pages: 取得する最大ページ数（Noneの場合は全ページ）
            progress_callback: 進捗コールバック関数
        
        Returns:
            (success_data, error_data) のタプル
        
        Note:
            1. 報告書一覧を取得
            2. 並列ダウンロード実行
        """
        logger.info(f"範囲指定取得開始: start_page={start_page}, max_pages={max_pages}")
        
        # プログレス通知（一覧取得開始）
        if progress_callback:
            progress_callback(0, 0, "報告書一覧を取得中...")
        
        # 報告書一覧取得
        try:
            report_links = self.scraper.get_report_list(
                max_pages=max_pages,
                start_page=start_page
            )
            
            logger.info(f"報告書一覧取得完了: {len(report_links)} 件")
            
            # プログレス通知（一覧取得完了）
            if progress_callback:
                progress_callback(0, len(report_links), f"報告書一覧取得完了: {len(report_links)} 件")
            
        except Exception as e:
            logger.error(f"報告書一覧取得エラー: {e}")
            if progress_callback:
                progress_callback(0, 0, f"エラー: 報告書一覧取得失敗 - {str(e)}")
            return [], []
        
        # 並列取得実行
        return self.fetch_reports(report_links, progress_callback)
    
    # ========================================
    # プライベートメソッド
    # ========================================

    def _apply_cache_hits(
        self,
        report_links: List[Dict[str, str]],
        success_data: List[Dict],
        total: int,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> Tuple[List[Dict[str, str]], int]:
        if not self.cache_manager or self.cache_mode != ReportCacheMode.SKIP:
            return list(report_links), 0

        pending_links: List[Dict[str, str]] = []
        cache_hits = 0

        for link in report_links:
            cached = self._load_from_cache(link)
            if cached:
                success_data.append(cached)
                cache_hits += 1
                code = link.get('code', 'unknown')
                self._safe_progress(
                    progress_callback,
                    len(success_data),
                    total,
                    f"↺ キャッシュ再利用: code={code} ({len(success_data)}/{total})",
                )
            else:
                pending_links.append(link)

        if cache_hits:
            logger.info("キャッシュ再利用件数: %s/%s", cache_hits, total or cache_hits)

        return pending_links, cache_hits

    def _load_from_cache(self, link: Dict[str, str]) -> Optional[Dict]:
        if not self.cache_manager:
            return None
        code = link.get('code') if link else None
        if not code:
            return None
        return self.cache_manager.load_entry(code)

    def _save_to_cache(self, report: Optional[Dict]) -> None:
        if not report or not self.cache_manager:
            return
        # SKIP/OVERWRITE いずれの場合も最新データを保存しておく
        self.cache_manager.save_entry(report)

    def _safe_progress(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]],
        current: int,
        total: int,
        message: str,
    ) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(current, total, message)
        except Exception as exc:  # pragma: no cover - コールバック例外は通知のみ
            logger.debug("progress_callback実行中に例外が発生: %s", exc)
    
    def _fetch_single(self, link: Dict[str, str]) -> Optional[Dict]:
        """
        単一報告書を取得（内部用）
        
        Args:
            link: 報告書リンク情報
        
        Returns:
            報告書データ、エラー時はNone
        """
        url = link.get('url')
        if not url:
            logger.warning("URL欠如のため取得スキップ")
            return None
        
        try:
            # 少し待機（サーバー負荷軽減）
            time.sleep(0.1)
            
            # 報告書取得
            report_data = self.scraper.fetch_report(url)
            return report_data
            
        except Exception as e:
            logger.error(f"報告書取得エラー ({url}): {e}")
            return None
