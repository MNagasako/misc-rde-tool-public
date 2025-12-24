"""
診断ツール統合実行クラス - ARIM RDE Tool v2.2.8

プロキシ・SSL診断をGUI環境から実行するためのバックグラウンドワーカー

機能:
- 統合診断の非同期実行
- プログレス通知
- 結果のパース・整形
- エラーハンドリング
"""

import sys
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from qt_compat import QtCore, Signal
from config.common import get_dynamic_file_path

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
        process = None
        try:
            logger.info("診断ツール実行開始")
            self.progress_updated.emit("診断準備中...", 0)
            
            # バイナリ環境の場合は直接実行モードを使用
            if is_frozen():
                logger.info("バイナリ環境を検出: 診断を直接実行モードで実行")
                results = self._run_diagnostics_direct()
            else:
                logger.info("開発環境を検出: 診断をサブプロセスモードで実行")
                results = self._run_diagnostics_subprocess()
            
            self.progress_updated.emit("診断完了", 100)
            self.diagnostic_completed.emit(results)
            
        except subprocess.TimeoutExpired:
            logger.error(f"診断がタイムアウトしました（{self.timeout}秒）")
            if process:
                process.kill()
            self.diagnostic_failed.emit(f"診断がタイムアウトしました（{self.timeout}秒）")
        except Exception as e:
            logger.exception("診断実行中にエラーが発生")
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    pass
            self.diagnostic_failed.emit(f"エラー: {str(e)}")
    
    def _run_diagnostics_direct(self) -> Dict[str, Any]:
        """診断を直接実行（バイナリ環境用）"""
        try:
            import importlib.util

            # 診断スクリプトのパス確認（testsは静的リソース）
            from config.common import get_static_resource_path
            tests_proxy_dir = get_static_resource_path("tests/proxy")
            if not Path(tests_proxy_dir).exists():
                raise FileNotFoundError(f"診断ディレクトリが見つかりません: {tests_proxy_dir}")
            
            # 診断実行
            self.progress_updated.emit("診断スクリプトをロード中...", 20)
            
            # run_all_diagnostics をインポートして実行
            def _load_module_from_path(module_name: str, file_path: Path):
                spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                if spec is None or spec.loader is None:
                    raise ImportError(f"モジュールロードに失敗: {module_name} ({file_path})")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                return module

            try:
                proxy_dir = Path(tests_proxy_dir)
                diag_utils = _load_module_from_path("diagnostic_utils", proxy_dir / "diagnostic_utils.py")
                run_all = _load_module_from_path("run_all_diagnostics", proxy_dir / "run_all_diagnostics.py")

                IntegratedDiagnostics = getattr(run_all, "IntegratedDiagnostics")
                DiagnosticConfig = getattr(diag_utils, "DiagnosticConfig")
            except Exception as e:
                raise ImportError(f"診断スクリプトのインポートに失敗: {e}")
            
            self.progress_updated.emit("診断を実行中...", 30)
            
            # 診断設定を構築
            config = DiagnosticConfig()
            cli_args = {
                'allow_mitm': self.allow_mitm,
                'verbose': self.verbose,
                'timeout': self.timeout
            }
            
            # 進捗コールバック機能を追加（モンキーパッチ）
            diagnostics = IntegratedDiagnostics(config=config, cli_args=cli_args)
            
            # 元のlog関数を保存
            original_log = diagnostics.log
            completed_tests = [0]  # リスト参照で更新可能に
            total_tests = 5
            
            def progress_log(message: str, level: str = "INFO"):
                """進捗をGUIに伝播するlog関数"""
                # 元のlog関数を呼び出す
                original_log(message, level)
                
                # 進捗パターンを検出
                if '✅' in message and '完了' in message:
                    completed_tests[0] += 1
                    progress = 30 + int(60 * completed_tests[0] / total_tests)
                    self.progress_updated.emit(
                        f"完了: テスト {completed_tests[0]}/{total_tests}",
                        progress
                    )
                elif '[' in message and ']' in message and '/' in message:
                    # "[1/5]" パターンを検出
                    try:
                        import re
                        match = re.search(r'\[(\d+)/(\d+)\]', message)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            progress = 30 + int(60 * (current - 1) / total)
                            self.progress_updated.emit(
                                f"実行中: テスト {current}/{total}",
                                progress
                            )
                    except:
                        pass
                elif '❌' in message:
                    self.progress_updated.emit(f"エラー発生", 50)
            
            # log関数を置き換え
            diagnostics.log = progress_log
            
            # 診断実行
            diagnostics.run_all_diagnostics()
            
            self.progress_updated.emit("結果を解析中...", 90)
            
            # 結果をレポートファイルから取得
            report_file = self._find_latest_report()
            if report_file:
                return self._parse_report(report_file)
            else:
                # レポートがない場合はエラー
                raise FileNotFoundError("診断レポートファイルが生成されませんでした")
                
        except Exception as e:
            logger.exception("直接実行モードでエラーが発生")
            raise
    
    def _run_diagnostics_subprocess(self) -> Dict[str, Any]:
        """診断をサブプロセスで実行（開発環境用）"""
        process = None
        try:
            logger.info("診断ツール実行開始")
            self.progress_updated.emit("診断準備中...", 0)
            
            # 診断スクリプトのパス（testsは静的リソース）
            from config.common import get_static_resource_path
            diagnostic_script = get_static_resource_path("tests/proxy/run_all_diagnostics.py")
            
            if not Path(diagnostic_script).exists():
                raise FileNotFoundError(f"診断スクリプトが見つかりません: {diagnostic_script}")
            
            # Python実行環境を取得
            python_exe = sys.executable
            
            # コマンド構築
            cmd = [python_exe, str(diagnostic_script)]
            if self.allow_mitm:
                cmd.append("--allow-mitm")
            if self.verbose:
                cmd.append("--verbose")
            cmd.extend(["--timeout", str(self.timeout)])
            
            logger.info(f"診断コマンド: {' '.join(cmd)}")
            self.progress_updated.emit("診断実行中...", 10)
            
            # 作業ディレクトリ（診断スクリプトの親ディレクトリ）
            working_dir = Path(diagnostic_script).parent
            
            # サブプロセス実行
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(working_dir)
            )
            
            # リアルタイム出力を監視してプログレスを更新
            import time
            start_time = time.time()
            progress = 10
            completed_tests = 0
            total_tests = 5  # 診断テストの総数
            
            stdout_buffer = []
            
            # プロセスが完了するまでポーリング
            while process.poll() is None:
                # キャンセルチェック
                if self._cancelled:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    logger.info("診断がキャンセルされました")
                    self.diagnostic_failed.emit("ユーザーによりキャンセルされました")
                    return
                
                # 標準出力から進捗を読み取る
                try:
                    # 非ブロッキングで1行読み取り
                    line = process.stdout.readline()
                    if line:
                        stdout_buffer.append(line)
                        
                        # 進捗パターンを検出
                        if '[' in line and ']' in line and '/' in line:
                            # "[1/5]" のようなパターンから進捗を計算
                            try:
                                import re
                                match = re.search(r'\[(\d+)/(\d+)\]', line)
                                if match:
                                    current = int(match.group(1))
                                    total = int(match.group(2))
                                    completed_tests = current - 1  # 開始時点での完了数
                                    total_tests = total
                                    # 10%〜90%の範囲で進捗を計算
                                    progress = 10 + int(80 * completed_tests / total_tests)
                            except:
                                pass
                        
                        # 完了メッセージを検出
                        if '✅' in line and '完了' in line:
                            completed_tests += 1
                            progress = 10 + int(80 * completed_tests / total_tests)
                            # テスト名を抽出して表示
                            test_name = line.strip()
                            if ':' in test_name:
                                test_name = test_name.split(':', 1)[0].replace('[INFO]', '').replace('✅', '').strip()
                            self.progress_updated.emit(f"完了: {test_name} ({completed_tests}/{total_tests})", progress)
                        
                        # エラーメッセージを検出
                        elif '❌' in line:
                            test_name = line.strip()
                            if ':' in test_name:
                                test_name = test_name.split(':', 1)[0].replace('[ERROR]', '').replace('❌', '').strip()
                            self.progress_updated.emit(f"エラー: {test_name}", progress)
                
                except:
                    pass
                
                # タイムアウトチェック
                elapsed = time.time() - start_time
                if elapsed > self.timeout:
                    process.kill()
                    logger.error(f"診断がタイムアウトしました（{self.timeout}秒）")
                    self.diagnostic_failed.emit(f"診断がタイムアウトしました（{self.timeout}秒）")
                    return
                
                # 進捗が更新されない場合は時間ベースで更新
                if progress < 80:
                    time_based_progress = min(80, 10 + int(70 * elapsed / self.timeout))
                    if time_based_progress > progress:
                        progress = time_based_progress
                        self.progress_updated.emit(f"診断実行中... ({int(elapsed)}秒経過)", progress)
                
                # 0.1秒待機（よりレスポンシブに）
                time.sleep(0.1)
            
            # プロセス完了後、出力を取得
            stdout, stderr = process.communicate()
            
            self.progress_updated.emit("結果を解析中...", 90)
            
            # 常にSTDOUT/STDERRをログに出力（デバッグ用）
            if stdout:
                logger.debug(f"診断スクリプトSTDOUT（最初の500文字）:\n{stdout[:500]}")
            if stderr:
                logger.debug(f"診断スクリプトSTDERR:\n{stderr}")
            
            # 戻り値チェック（ただし、レポートが生成されていれば部分的成功とみなす）
            if process.returncode != 0:
                logger.warning(f"診断が警告付きで完了（終了コード: {process.returncode}）")
                if stdout:
                    logger.debug(f"STDOUT（最初の1000文字）:\n{stdout[:1000]}")
                if stderr:
                    logger.warning(f"STDERR:\n{stderr}")
                
                # レポートファイルを探す
                report_file = self._find_latest_report()
                if report_file:
                    # レポートがあれば部分的成功として扱う
                    logger.info(f"レポートファイルが見つかりました。部分的成功として処理します: {report_file}")
                    return self._parse_report(report_file)
                else:
                    # レポートもない場合は失敗
                    error_detail = stderr if stderr.strip() else stdout
                    raise RuntimeError(f"診断失敗（終了コード: {process.returncode}）\n\n{error_detail[:1000]}")
            else:
                # 成功時
                # 診断レポートファイルを探す
                report_file = self._find_latest_report()
                if report_file:
                    logger.info(f"診断レポート発見: {report_file}")
                    return self._parse_report(report_file)
                else:
                    # レポートが見つからない場合は標準出力からパース
                    logger.warning("診断レポートファイルが見つかりません。標準出力から解析します")
                    return self._parse_stdout(stdout)
                    
        except Exception as e:
            logger.exception("サブプロセス実行中にエラーが発生")
            raise
            
    def _find_latest_report(self) -> Optional[Path]:
        """最新の診断レポートファイルを検索"""
        try:
            # バイナリ環境と開発環境で異なるディレクトリを検索
            if is_frozen():
                # バイナリ環境: カレントディレクトリ/tests/proxy
                report_dir = Path.cwd() / "tests" / "proxy"
            else:
                # 開発環境: プロジェクトルート/tests/proxy
                report_dir = Path(get_dynamic_file_path("tests/proxy"))
            
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
