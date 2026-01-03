"""
診断ツール統合実行クラス - ARIM RDE Tool v2.4.3

プロキシ・SSL診断をGUI環境から実行するためのバックグラウンドワーカー

機能:
- 統合診断の非同期実行
- プログレス通知
- 結果のパース・整形
- エラーハンドリング
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from qt_compat import QtCore, Signal
from config.common import get_dynamic_file_path

from classes.config.core.diagnostics.diagnostic_utils import DiagnosticConfig
from classes.config.core.diagnostics.integrated_diagnostics import IntegratedDiagnostics

logger = logging.getLogger(__name__)


def is_frozen():
    """バイナリ環境（PyInstaller等でフリーズされた環境）かどうかを判定"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


class DiagnosticWorker(QtCore.QThread):
    """診断実行ワーカースレッド"""
    
    # シグナル定義
    progress_updated = Signal(str, int)  # (メッセージ, 進捗%)
    diagnostic_completed = Signal(dict)   # 診断完了（結果辞書）
    diagnostic_failed = Signal(str)       # 診断失敗（エラーメッセージ）
    
    def __init__(self, 
                 allow_mitm: bool = True,
                 verbose: bool = False,
                 timeout: int = 90,  # 300→90秒に短縮
                 parent=None):
        """
        Args:
            allow_mitm: MitM環境でのSSL検証スキップを許可
            verbose: 詳細ログ出力
            timeout: 診断全体のタイムアウト（秒）
            parent: 親ウィジェット（QThreadでは未使用だが互換性のため保持）
        """
        super().__init__()  # QThreadはparentを受け取らない
        self.allow_mitm = allow_mitm
        self.verbose = verbose
        self.timeout = timeout
        self._cancelled = False
        
    def cancel(self):
        """診断をキャンセル"""
        self._cancelled = True
        
    def __del__(self):
        """デストラクタ - スレッドのクリーンアップ"""
        try:
            if self.isRunning():
                self.cancel()
                self.wait(1000)  # 1秒待機
                if self.isRunning():
                    self.terminate()  # 強制終了
        except:
            pass
        
    def run(self):
        """診断実行（バックグラウンドスレッド）"""
        try:
            logger.info("診断ツール実行開始")
            self.progress_updated.emit("診断準備中...", 0)

            # 本体同梱の診断モジュールを直接実行（tests 非依存）
            results = self._run_diagnostics_direct()
            
            self.progress_updated.emit("診断完了", 100)
            self.diagnostic_completed.emit(results)
            
        except TimeoutError:
            logger.error(f"診断がタイムアウトしました（{self.timeout}秒）")
            self.diagnostic_failed.emit(f"診断がタイムアウトしました（{self.timeout}秒）")
        except Exception as e:
            logger.exception("診断実行中にエラーが発生")
            self.diagnostic_failed.emit(f"エラー: {str(e)}")
    
    def _run_diagnostics_direct(self) -> Dict[str, Any]:
        """診断を直接実行（バイナリ環境用）"""
        try:
            self.progress_updated.emit("診断モジュールをロード中...", 20)

            config = DiagnosticConfig()
            cli_args = {
                'allow_mitm': self.allow_mitm,
                'verbose': self.verbose,
                'timeout': self.timeout,
            }

            diagnostics = IntegratedDiagnostics(config=config, cli_args=cli_args)

            original_log = diagnostics.log
            completed_tests = [0]
            total_tests = 5

            def progress_log(message: str, level: str = "INFO"):
                original_log(message, level)
                if '✅' in message and '完了' in message:
                    completed_tests[0] += 1
                    progress = 30 + int(60 * completed_tests[0] / total_tests)
                    self.progress_updated.emit(
                        f"完了: テスト {completed_tests[0]}/{total_tests}",
                        progress,
                    )
                elif '[' in message and ']' in message and '/' in message:
                    try:
                        import re

                        match = re.search(r'\[(\d+)/(\d+)\]', message)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            progress = 30 + int(60 * (current - 1) / total)
                            self.progress_updated.emit(
                                f"実行中: テスト {current}/{total}",
                                progress,
                            )
                    except Exception:
                        pass
                elif '❌' in message:
                    self.progress_updated.emit("エラー発生", 50)

            diagnostics.log = progress_log

            self.progress_updated.emit("診断を実行中...", 30)
            diagnostics.run_all_diagnostics()
            self.progress_updated.emit("結果を解析中...", 90)

            report_file = self._find_latest_report()
            if report_file:
                return self._parse_report(report_file)
            raise FileNotFoundError("診断レポートファイルが生成されませんでした")

        except Exception:
            logger.exception("直接実行モードでエラーが発生")
            raise
    
    def _run_diagnostics_subprocess(self) -> Dict[str, Any]:
        """診断をサブプロセスで実行（開発環境用）"""
        # tests 非依存化によりサブプロセス実行は廃止し、直接実行に統一
        return self._run_diagnostics_direct()
            
    def _find_latest_report(self) -> Optional[Path]:
        """最新の診断レポートファイルを検索"""
        try:
            report_dir = Path(get_dynamic_file_path("output/log/diagnostics"))
            
            if not report_dir.exists():
                logger.warning(f"レポートディレクトリが存在しません: {report_dir}")
                return None
            
            # diagnostic_report_*.json パターンで検索
            report_files = list(report_dir.glob("diagnostic_report_*.json"))
            
            if not report_files:
                logger.debug(f"レポートファイルが見つかりません: {report_dir}")
                return None
            
            # 最新のファイルを返す（タイムスタンプ降順）
            latest = max(report_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"レポートファイルを発見: {latest}")
            return latest
            
        except Exception as e:
            logger.warning(f"レポートファイル検索エラー: {e}")
            return None
            
    def _parse_report(self, report_file: Path) -> Dict[str, Any]:
        """診断レポートJSONをパース"""
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # レポート形式を判定（v2.1.6形式とlegacy形式の両方に対応）
            if 'summary' in data:
                # legacy形式
                summary = {
                    'success': True,
                    'total_tests': data['summary'].get('total', 0),
                    'passed': data['summary'].get('passed', 0),
                    'failed': data['summary'].get('failed', 0),
                    'duration': data['summary'].get('total_duration', 0),
                    'tests': data.get('results', []),
                    'timestamp': data.get('timestamp', ''),
                    'report_file': str(report_file)
                }
            else:
                # v2.1.6形式（直接キー）
                results_dict = data.get('results', {})
                tests = []
                for script_name, result in results_dict.items():
                    # 所要時間を取得（秒→適切な単位に変換）
                    duration = result.get('duration', 0)
                    if duration >= 60:
                        duration_str = f"{duration / 60:.1f}分"
                    else:
                        duration_str = f"{duration:.2f}秒"
                    
                    tests.append({
                        'name': result.get('description', script_name),
                        'status': 'passed' if result.get('success') else 'failed',
                        'message': f"終了コード: {result.get('return_code', 'N/A')}",
                        'duration': duration,
                        'duration_str': duration_str
                    })
                
                summary = {
                    'success': True,
                    'total_tests': data.get('total_tests', 0),
                    'passed': data.get('passed_tests', 0),
                    'failed': data.get('failed_tests', 0),
                    'duration': data.get('duration_seconds', 0),
                    'tests': tests,
                    'timestamp': data.get('start_time', ''),
                    'report_file': str(report_file)
                }
            
            return summary
            
        except Exception as e:
            logger.error(f"レポート解析エラー: {e}")
            return {
                'success': False,
                'error': f'レポート解析失敗: {e}',
                'report_file': str(report_file)
            }
            
    def _parse_stdout(self, stdout: str) -> Dict[str, Any]:
        """標準出力から診断結果をパース（フォールバック）"""
        try:
            # 簡易パース（合格/不合格のカウント）
            lines = stdout.split('\n')
            passed = sum(1 for line in lines if '✅' in line or '合格' in line)
            failed = sum(1 for line in lines if '❌' in line or '失敗' in line)
            
            return {
                'success': True,
                'total_tests': passed + failed,
                'passed': passed,
                'failed': failed,
                'duration': 0,
                'tests': [],
                'timestamp': datetime.now().isoformat(),
                'report_file': None,
                'stdout': stdout
            }
            
        except Exception as e:
            logger.error(f"標準出力解析エラー: {e}")
            return {
                'success': False,
                'error': f'出力解析失敗: {e}',
                'stdout': stdout
            }


class DiagnosticRunner:
    """診断実行管理クラス"""
    
    def __init__(self, parent_widget=None):
        """
        Args:
            parent_widget: 親ウィジェット（プログレスダイアログ表示用）
        """
        self.parent = parent_widget
        self.worker = None
    
    def __del__(self):
        """デストラクタ - ワーカーのクリーンアップ"""
        self.cleanup()
    
    def cleanup(self):
        """ワーカースレッドを安全に終了"""
        if self.worker:
            try:
                if self.worker.isRunning():
                    self.worker.cancel()
                    self.worker.wait(2000)  # 2秒待機
                    if self.worker.isRunning():
                        self.worker.terminate()
                        self.worker.wait(1000)
                self.worker.deleteLater()
            except:
                pass
            finally:
                self.worker = None
        
    def run_async(self, 
                  callback: Callable[[Dict[str, Any]], None],
                  error_callback: Optional[Callable[[str], None]] = None,
                  progress_callback: Optional[Callable[[str, int], None]] = None,
                  allow_mitm: bool = True,
                  verbose: bool = False,
                  timeout: int = 90):  # 300→90秒に短縮
        """
        診断を非同期実行
        
        Args:
            callback: 診断完了時のコールバック関数（結果辞書を引数に取る）
            error_callback: エラー発生時のコールバック関数（エラーメッセージを引数に取る）
            progress_callback: プログレス更新時のコールバック関数（メッセージ, 進捗%を引数に取る）
            allow_mitm: MitM環境でのSSL検証スキップを許可
            verbose: 詳細ログ出力
            timeout: 診断全体のタイムアウト（秒）
        """
        if self.worker and self.worker.isRunning():
            logger.warning("既に診断が実行中です")
            return
        
        # 古いワーカーをクリーンアップ
        if self.worker:
            try:
                self.worker.deleteLater()
            except:
                pass
        
        # ワーカースレッド作成
        self.worker = DiagnosticWorker(
            allow_mitm=allow_mitm,
            verbose=verbose,
            timeout=timeout,
            parent=self.parent
        )
        
        # シグナル接続
        self.worker.diagnostic_completed.connect(callback)
        if error_callback:
            self.worker.diagnostic_failed.connect(error_callback)
        if progress_callback:
            self.worker.progress_updated.connect(progress_callback)
        
        # 実行開始
        logger.info("診断ワーカースレッド開始")
        self.worker.start()
        
    def cancel(self):
        """実行中の診断をキャンセル"""
        if self.worker and self.worker.isRunning():
            logger.info("診断キャンセル要求")
            self.worker.cancel()
            self.worker.wait(5000)  # 5秒待機
            
    def is_running(self) -> bool:
        """診断実行中かどうか"""
        return self.worker is not None and self.worker.isRunning()
