"""
報告書機能 - 並列取得モジュール

報告書データを並列ダウンロードし、高速に取得します。

Version: 2.1.0
"""

import logging
from typing import List, Dict, Tuple, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .report_scraper import ReportScraper


logger = logging.getLogger(__name__)


class ParallelReportFetcher:
    """
    報告書並列取得クラス
    
    複数の報告書を並列ダウンロードして高速化します。
    設備タブのParallelFacilityFetcherパターンを踏襲しています。
    """
    
    def __init__(self, max_workers: int = 5):
        """
        初期化
        
        Args:
            max_workers: 並列実行するワーカー数（デフォルト: 5）
        """
        self.max_workers = max_workers
        self.scraper = ReportScraper()
        logger.info(f"ParallelReportFetcher初期化: max_workers={max_workers}")
    
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
        
        success_data = []
        error_data = []
        total = len(report_links)
        
        # プログレス初期化
        if progress_callback:
            progress_callback(0, total, "並列取得を開始します...")
        
        # 並列実行
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 全タスクを投入
            futures = {
                executor.submit(self._fetch_single, link): link
                for link in report_links
            }
            
            # 完了したタスクから順次処理
            completed = 0
            for future in as_completed(futures):
                link = futures[future]
                completed += 1
                
                try:
                    result = future.result()
                    
                    if result:
                        success_data.append(result)
                        
                        # プログレス通知（成功）
                        if progress_callback:
                            code = link.get('code', 'unknown')
                            progress_callback(
                                completed,
                                total,
                                f"✓ 取得成功: code={code} ({completed}/{total})"
                            )
                    else:
                        # 取得失敗
                        error_data.append({
                            "link": link,
                            "error": "Failed to fetch report"
                        })
                        
                        # プログレス通知（失敗）
                        if progress_callback:
                            code = link.get('code', 'unknown')
                            progress_callback(
                                completed,
                                total,
                                f"✗ 取得失敗: code={code} ({completed}/{total})"
                            )
                
                except Exception as e:
                    logger.error(f"タスク実行エラー ({link}): {e}")
                    error_data.append({
                        "link": link,
                        "error": str(e)
                    })
                    
                    # プログレス通知（エラー）
                    if progress_callback:
                        code = link.get('code', 'unknown')
                        progress_callback(
                            completed,
                            total,
                            f"⚠ エラー: code={code} - {str(e)[:50]}"
                        )
        
        logger.info(f"並列取得完了: 成功={len(success_data)}, 失敗={len(error_data)}")
        
        # 最終プログレス通知
        if progress_callback:
            progress_callback(
                total,
                total,
                f"完了: 成功={len(success_data)}, 失敗={len(error_data)}"
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
