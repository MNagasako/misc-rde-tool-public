"""
設備データ並列取得モジュール

複数の設備データを並列で高速取得します。
"""

import logging
from typing import List, Dict, Callable, Optional, Tuple
from net.http_helpers import parallel_download
from classes.equipment.core.facility_scraper import FacilityScraper


logger = logging.getLogger(__name__)


class ParallelFacilityFetcher:
    """設備データ並列取得クラス
    
    FacilityScraperを使用して複数の設備データを並列で取得します。
    """
    
    def __init__(self, max_workers: int = 5):
        """初期化
        
        Args:
            max_workers: 並列実行スレッド数（デフォルト: 5）
        """
        self.scraper = FacilityScraper()
        self.max_workers = max_workers
        logger.info(f"ParallelFacilityFetcher初期化: max_workers={max_workers}")
    
    def fetch_facilities(self, 
                        facility_ids: List[int],
                        progress_callback: Optional[Callable[[int, int, str], bool]] = None) -> Tuple[List[Dict], List[Dict]]:
        """複数の設備データを並列取得
        
        Args:
            facility_ids: 取得する設備IDのリスト
            progress_callback: プログレスコールバック関数
                              (current, total, message) -> bool (Falseでキャンセル)
        
        Returns:
            Tuple[List[Dict], List[Dict]]: (成功データリスト, エラー情報リスト)
        """
        logger.info(f"並列取得開始: {len(facility_ids)}件, max_workers={self.max_workers}")
        
        # ワーカー関数定義
        def worker(facility_id: int) -> Dict:
            """個別設備データ取得ワーカー
            
            Args:
                facility_id: 設備ID
            
            Returns:
                Dict: 結果辞書 {status, data, error}
            """
            try:
                data = self.scraper.fetch_facility(facility_id)
                
                if data:
                    return {
                        "status": "success",
                        "facility_id": facility_id,
                        "data": data
                    }
                else:
                    return {
                        "status": "failed",
                        "facility_id": facility_id,
                        "error": "データ取得失敗"
                    }
            except Exception as e:
                logger.error(f"設備ID {facility_id} 取得エラー: {e}")
                return {
                    "status": "failed",
                    "facility_id": facility_id,
                    "error": str(e)
                }
        
        # タスクリスト作成（各IDをタプルでラップ）
        tasks = [(facility_id,) for facility_id in facility_ids]
        
        # 並列ダウンロード実行
        result = parallel_download(
            tasks=tasks,
            worker_function=worker,
            max_workers=self.max_workers,
            progress_callback=progress_callback,
            threshold=3  # 3件未満は同期実行
        )
        
        # 結果の集計
        success_data = []
        error_info = []
        
        logger.info(f"並列取得完了: 成功={result['success_count']}, "
                   f"失敗={result['failed_count']}, "
                   f"スキップ={result['skipped_count']}")
        
        # エラー情報を整形
        for error_item in result.get('errors', []):
            task = error_item.get('task', [])
            facility_id = task[0] if task else 'unknown'
            error_info.append({
                'facility_id': facility_id,
                'error': error_item.get('error', 'Unknown error')
            })
        
        # 注意: parallel_download は結果データを直接返さないため、
        # 個別に再取得が必要。ここでは統計情報のみ返す。
        # 実際のデータ取得は fetch_facilities_with_retry で行う。
        
        return success_data, error_info
    
    def fetch_facilities_with_results(self,
                                      facility_ids: List[int],
                                      progress_callback: Optional[Callable[[int, int, str], bool]] = None) -> Tuple[List[Dict], List[Dict]]:
        """複数の設備データを並列取得（結果データ付き）
        
        parallel_downloadの制約により、結果データを収集する別実装。
        
        Args:
            facility_ids: 取得する設備IDのリスト
            progress_callback: プログレスコールバック関数
        
        Returns:
            Tuple[List[Dict], List[Dict]]: (成功データリスト, エラー情報リスト)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        logger.info(f"並列取得開始（データ収集モード）: {len(facility_ids)}件")
        
        success_data = []
        error_info = []
        completed_count = 0
        lock = threading.Lock()
        
        # 3件未満は同期実行
        if len(facility_ids) < 3:
            logger.info("少数データのため同期実行")
            for facility_id in facility_ids:
                try:
                    data = self.scraper.fetch_facility(facility_id)
                    if data:
                        success_data.append(data)
                    else:
                        error_info.append({
                            'facility_id': facility_id,
                            'error': 'データ取得失敗'
                        })
                except Exception as e:
                    error_info.append({
                        'facility_id': facility_id,
                        'error': str(e)
                    })
                
                # プログレス更新
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, len(facility_ids), 
                                    f"取得中... ({completed_count}/{len(facility_ids)})")
            
            return success_data, error_info
        
        # 並列実行
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_id = {
                executor.submit(self.scraper.fetch_facility, fid): fid 
                for fid in facility_ids
            }
            
            for future in as_completed(future_to_id):
                facility_id = future_to_id[future]
                
                try:
                    data = future.result()
                    
                    with lock:
                        if data:
                            success_data.append(data)
                            logger.debug(f"取得成功: ID={facility_id}, 設備ID={data.get('設備ID')}")
                        else:
                            error_info.append({
                                'facility_id': facility_id,
                                'error': 'データ取得失敗（空データ）'
                            })
                            logger.warning(f"取得失敗: ID={facility_id}")
                        
                        completed_count += 1
                        
                        # プログレス更新
                        if progress_callback:
                            if not progress_callback(completed_count, len(facility_ids),
                                                    f"取得中... ({completed_count}/{len(facility_ids)})"):
                                logger.info("ユーザーによるキャンセル")
                                # 残りをキャンセル
                                for f in future_to_id:
                                    f.cancel()
                                break
                
                except Exception as e:
                    with lock:
                        error_info.append({
                            'facility_id': facility_id,
                            'error': str(e)
                        })
                        logger.error(f"取得エラー: ID={facility_id}, error={e}")
        
        logger.info(f"並列取得完了: 成功={len(success_data)}件, エラー={len(error_info)}件")
        return success_data, error_info
    
    def fetch_range(self,
                    start_id: int,
                    end_id: int,
                    progress_callback: Optional[Callable[[int, int, str], bool]] = None) -> Tuple[List[Dict], List[Dict]]:
        """指定範囲の設備データを並列取得
        
        Args:
            start_id: 開始ID（含む）
            end_id: 終了ID（含む）
            progress_callback: プログレスコールバック関数
        
        Returns:
            Tuple[List[Dict], List[Dict]]: (成功データリスト, エラー情報リスト)
        """
        facility_ids = list(range(start_id, end_id + 1))
        logger.info(f"範囲取得: {start_id}～{end_id} ({len(facility_ids)}件)")
        
        return self.fetch_facilities_with_results(facility_ids, progress_callback)
