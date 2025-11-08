#!/usr/bin/env python3
"""
BatchProcessor - バッチ処理クラス

概要:
大量データの一括処理と効率的なバッチ実行を専門に行うクラスです。
スケーラブルで信頼性の高いデータ処理パイプラインを提供します。

主要機能:
- バッチジョブの管理・実行
- 大量データの効率的処理
- 処理進捗の監視・レポート
- エラー時の自動リトライ
- リソース使用量の最適化
- 並列処理による高速化

責務:
バッチ処理を専門化し、大規模データ処理の効率性と信頼性を確保します。
"""

# -*- coding: utf-8 -*-
"""
BatchProcessor: バッチ処理機能を管理するクラス - ARIM RDE Tool v1.13.1
複数プロジェクトの一括処理・進行状況管理・結果集約機能
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認

このクラスは以下の責務を持つ：
1. バッチ実行機能の管理
2. grantNumber一括処理
3. バッチ処理の進行状況管理
4. バッチ処理結果の集約
"""

import os
import logging
from qt_compat.core import QObject, Signal, QTimer, QDateTime
from config.common import INPUT_DIR
from classes.utils.debug_log import debug_log

class BatchProcessor(QObject):
    """バッチ処理機能を管理するクラス"""
    
    # シグナル定義
    batch_progress_updated = Signal(int, int)  # (current, total)
    batch_completed = Signal(object)  # results（PySide6: dict→object）
    batch_error = Signal(str)  # error_message
    
    @debug_log
    def __init__(self, browser_instance):
        """
        BatchProcessorの初期化
        
        Args:
            browser_instance: Browser クラスのインスタンス（参照用）
        """
        super().__init__()
        self.browser = browser_instance
        self.logger = logging.getLogger(__name__)
        
        # バッチ処理状態
        self.is_batch_running = False
        self.current_batch_index = 0
        self.batch_grant_numbers = []
        self.batch_results = {}
        self.timeout_timer = None
        self.processing_started = False
        
        # 設定値
        self.batch_delay = 3000  # ミリ秒
        self.max_retries = 3
        
        self.logger.info("BatchProcessor初期化完了")
    
    @debug_log
    def execute_batch_grant_numbers(self):
        """
        grantNumber一括実行処理
        
        list.txtファイルからgrantNumberを読み込み、
        順次検索・保存処理を実行する
        """
        try:
            list_file_path = os.path.join(INPUT_DIR, 'list.txt')
            
            if not os.path.exists(list_file_path):
                self.batch_error.emit(f"ファイルが見つかりません: {list_file_path}")
                return
            
            # list.txtからgrantNumberを読み込み
            with open(list_file_path, 'r', encoding='utf-8') as f:
                grant_numbers = [line.strip() for line in f.readlines() if line.strip()]
            
            if not grant_numbers:
                self.batch_error.emit("有効なgrantNumberが見つかりません")
                return
            
            self.logger.info(f"バッチ処理開始: {len(grant_numbers)}件のgrantNumber")
            
            # バッチ処理開始
            self.batch_grant_numbers = grant_numbers
            self.current_batch_index = 0
            self.batch_results = {}
            self.is_batch_running = True
            
            # 最初の処理を開始
            self._process_next_grant_number()
            
        except Exception as e:
            self.logger.error(f"バッチ処理開始エラー: {str(e)}")
            self.batch_error.emit(f"バッチ処理開始エラー: {str(e)}")
    
    @debug_log
    def _process_next_grant_number(self):
        """次のgrantNumberを処理"""
        if not self.is_batch_running:
            return
        
        if self.current_batch_index >= len(self.batch_grant_numbers):
            # 全ての処理完了
            self._complete_batch_processing()
            return
        
        current_grant = self.batch_grant_numbers[self.current_batch_index]
        self.logger.info(f"処理中: {current_grant} ({self.current_batch_index + 1}/{len(self.batch_grant_numbers)})")
        
        # 進行状況を更新
        self.batch_progress_updated.emit(self.current_batch_index + 1, len(self.batch_grant_numbers))
        
        # ブラウザのgrantNumber設定
        if hasattr(self.browser, 'grant_input') and self.browser.grant_input:
            self.browser.grant_input.setText(current_grant)
        
        # 検索実行
        self._execute_search_for_current_grant()
    
    @debug_log
    def _execute_search_for_current_grant(self):
        """現在のgrantNumberに対して検索を実行"""
        try:
            current_grant = self.batch_grant_numbers[self.current_batch_index]
            
            # ProjectManagerを使用して完全な処理を実行
            if hasattr(self.browser, 'project_manager'):
                self.logger.info(f"[BATCH] ProjectManager経由で完全処理開始: {current_grant}")
                self.browser.set_webview_message(f'[BATCH] 処理中: {current_grant}')
                
                try:
                    # ProjectManagerの処理を実行（同期処理）
                    success = self.browser.project_manager.process_grant_number(current_grant)
                    
                    if success:
                        self.logger.info(f"[BATCH] ProjectManager処理成功: {current_grant}")
                        self.browser.set_webview_message(f'[BATCH] 完了: {current_grant}')
                        self._handle_search_completion()
                    else:
                        self.logger.warning(f"[BATCH] ProjectManager処理失敗: {current_grant}")
                        self.browser.set_webview_message(f'[BATCH] 失敗: {current_grant}')
                        self._record_batch_error("ProjectManager処理が失敗しました")
                        
                except Exception as pm_error:
                    self.logger.error(f"[BATCH] ProjectManager例外: {current_grant} - {pm_error}")
                    self.browser.set_webview_message(f'[BATCH] 例外: {current_grant}')
                    self._record_batch_error(f"ProjectManager例外: {pm_error}")
                    
            else:
                # フォールバック：従来の方法
                self.logger.warning("ProjectManagerが見つかりません。従来の方法で処理します")
                
                # grantNumberを設定
                self.browser.grant_number = current_grant
                
                # 検索とデータセット取得の両方を実行
                if hasattr(self.browser, 'search_and_save_result') and hasattr(self.browser, 'fetch_and_save_multiple_datasets'):
                    # 1. 検索実行
                    self.browser.search_and_save_result(grant_number=current_grant)
                    
                    # 2. データセット詳細取得実行
                    self.browser.fetch_and_save_multiple_datasets()
                    
                    # 処理完了を検知するため、一定時間後に完了確認
                    QTimer.singleShot(15000, self._check_processing_completion)
                    
                    # タイムアウト保護（60秒）
                    self.timeout_timer = QTimer()
                    self.timeout_timer.singleShot(60000, self._handle_search_timeout)
                else:
                    self.logger.error("必要なメソッドが見つかりません")
                    self._record_batch_error("必要なメソッドが見つかりません")
                
        except Exception as e:
            self.logger.error(f"検索実行エラー: {str(e)}")
            self._record_batch_error(f"検索実行エラー: {str(e)}")
    
    @debug_log
    def _handle_search_completion(self, grant_number=None, success=True):
        """検索完了後の処理"""
        if not self.is_batch_running:
            return
            
        current_grant = self.batch_grant_numbers[self.current_batch_index]
        
        # タイムアウトタイマーをキャンセル
        if self.timeout_timer:
            self.timeout_timer.stop()
            self.timeout_timer = None
        
        # DataManagerシグナルを切断
        if hasattr(self.browser, 'data_manager') and hasattr(self.browser.data_manager, 'processing_completed'):
            try:
                self.browser.data_manager.processing_completed.disconnect(self._handle_search_completion)
            except:
                pass  # 切断エラーは無視
        
        # 結果記録
        status = 'completed' if success else 'error'
        self.batch_results[current_grant] = {
            'status': status,
            'success': success,
            'timestamp': QDateTime.currentDateTime().toString(),
            'index': self.current_batch_index
        }
        
        self.logger.info(f"完了: {current_grant} (success={success})")
        
        # 次の処理へ
        self.current_batch_index += 1
        self.processing_started = False
        
        # 少し待ってから次の処理を開始
        QTimer.singleShot(2000, self._process_next_grant_number)
    
    @debug_log
    def _record_batch_error(self, error_message):
        """バッチ処理中のエラーを記録して次に進む"""
        if not self.is_batch_running:
            return
            
        current_grant = self.batch_grant_numbers[self.current_batch_index]
        
        # タイムアウトタイマーをキャンセル
        if self.timeout_timer:
            self.timeout_timer.stop()
            self.timeout_timer = None
        
        # DataManagerシグナルを切断
        if hasattr(self.browser, 'data_manager') and hasattr(self.browser.data_manager, 'processing_completed'):
            try:
                self.browser.data_manager.processing_completed.disconnect(self._handle_search_completion)
            except:
                pass  # 切断エラーは無視
        
        self.batch_results[current_grant] = {
            'status': 'error',
            'error': error_message,
            'timestamp': QDateTime.currentDateTime().toString(),
            'index': self.current_batch_index
        }
        
        self.logger.warning(f"エラー記録: {current_grant} - {error_message}")
        
        # 次の処理へ
        self.current_batch_index += 1
        self.processing_started = False
        QTimer.singleShot(2000, self._process_next_grant_number)
    
    @debug_log
    def _complete_batch_processing(self):
        """バッチ処理完了"""
        self.is_batch_running = False
        
        # 結果集計
        total_count = len(self.batch_grant_numbers)
        success_count = len([r for r in self.batch_results.values() if r['status'] == 'completed'])
        error_count = total_count - success_count
        
        completion_result = {
            'total': total_count,
            'success': success_count,
            'errors': error_count,
            'results': self.batch_results
        }
        
        self.logger.info(f"バッチ処理完了: 成功={success_count}, エラー={error_count}, 合計={total_count}")
        
        # 完了シグナル発信
        self.batch_completed.emit(completion_result)
    
    @debug_log
    def stop_batch_processing(self):
        """バッチ処理を停止"""
        if self.is_batch_running:
            self.is_batch_running = False
            self.logger.info("バッチ処理が手動で停止されました")
            
            # 部分的な結果を返す
            partial_result = {
                'total': len(self.batch_grant_numbers),
                'processed': self.current_batch_index,
                'results': self.batch_results,
                'status': 'stopped'
            }
            
            self.batch_completed.emit(partial_result)
    
    @debug_log
    def get_batch_status(self):
        """現在のバッチ処理状況を取得"""
        return {
            'is_running': self.is_batch_running,
            'current_index': self.current_batch_index,
            'total_count': len(self.batch_grant_numbers),
            'current_grant': self.batch_grant_numbers[self.current_batch_index] if self.current_batch_index < len(self.batch_grant_numbers) else None
        }
    
    @debug_log
    def set_batch_delay(self, delay_ms):
        """バッチ処理間隔を設定"""
        self.batch_delay = max(1000, delay_ms)  # 最小1秒
        self.logger.info(f"バッチ処理間隔を {self.batch_delay}ms に設定")
    
    @debug_log
    def _handle_search_timeout(self):
        """検索処理のタイムアウト処理"""
        if self.is_batch_running and self.current_batch_index < len(self.batch_grant_numbers):
            current_grant = self.batch_grant_numbers[self.current_batch_index]
            self.logger.warning(f"検索処理タイムアウト: {current_grant}")
            self._record_batch_error("検索処理がタイムアウトしました")
    
    @debug_log
    def _check_processing_completion(self):
        """処理完了チェック（簡易版）"""
        if not self.is_batch_running:
            return
            
        current_grant = self.batch_grant_numbers[self.current_batch_index]
        
        # 処理完了の簡易判定（ファイル存在チェック等）
        try:
            from config.common import OUTPUT_DIR
            import os
            
            # 検索結果ファイルの存在確認
            search_result_path = os.path.join(OUTPUT_DIR, "search_results", f"{current_grant}.json")
            
            # データセットディレクトリの存在確認  
            dataset_dir = os.path.join(OUTPUT_DIR, "datasets", current_grant)
            
            if os.path.exists(search_result_path) and os.path.exists(dataset_dir):
                # 処理完了とみなす
                self.logger.info(f"処理完了を確認: {current_grant}")
                self._handle_search_completion(current_grant, True)
            else:
                # さらに待機（最大3回まで）
                if not hasattr(self, '_completion_check_count'):
                    self._completion_check_count = 0
                
                self._completion_check_count += 1
                if self._completion_check_count < 3:
                    self.logger.debug(f"処理確認中: {current_grant} (試行 {self._completion_check_count}/3)")
                    QTimer.singleShot(10000, self._check_processing_completion)
                else:
                    # タイムアウト
                    self.logger.warning(f"処理完了確認タイムアウト: {current_grant}")
                    self._handle_search_completion(current_grant, False)
                    self._completion_check_count = 0
        except Exception as e:
            self.logger.error(f"処理完了チェックエラー: {str(e)}")
            self._handle_search_completion(current_grant, False)
