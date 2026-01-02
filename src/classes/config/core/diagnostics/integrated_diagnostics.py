"""統合プロキシ診断（本体同梱版）

- tests フォルダに依存しない。
- 進捗表示のため、ログメッセージは従来のパターン（[1/5] 等）を維持する。
- レポートは get_dynamic_file_path("output/log/diagnostics") 配下に JSON で出力する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Callable, List
import sys
import time
import json
from pathlib import Path

from config.common import get_dynamic_file_path

from .diagnostic_utils import DiagnosticConfig


@dataclass(frozen=True)
class DiagnosticTask:
    module_name: str
    description: str


class IntegratedDiagnostics:
    """統合診断クラス"""

    def __init__(self, config: Optional[DiagnosticConfig] = None, cli_args: Optional[dict] = None):
        self.config = config or DiagnosticConfig()
        self._cli_args = cli_args or {}
        self.start_time = datetime.now()
        self.results: Dict[str, Any] = {}

        self._tasks: List[DiagnosticTask] = [
            DiagnosticTask('test_system_proxy_detection', 'システムプロキシ検出'),
            DiagnosticTask('test_config_flow', '設定保存/読み込みフロー'),
            DiagnosticTask('test_basic_proxy', '基本プロキシ疎通'),
            DiagnosticTask('test_ssl_certificate', 'SSL/証明書診断'),
            DiagnosticTask('test_connection_stability', '連続接続安定性'),
        ]

    def log(self, message: str, level: str = 'INFO'):
        icons = {
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'ERROR': '❌',
            'WARNING': '⚠️',
            'DEBUG': '🔍',
        }
        icon = icons.get(level, '📝')
        print(f"[{level:7}] {icon} {message}")

    def _report_dir(self) -> Path:
        report_dir = Path(get_dynamic_file_path('output/log/diagnostics'))
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir

    def _write_report(self) -> Path:
        report_dir = self._report_dir()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = report_dir / f'diagnostic_report_{ts}.json'

        total = len(self._tasks)
        passed = sum(1 for r in self.results.values() if r.get('success'))
        failed = total - passed

        payload = {
            'start_time': self.start_time.isoformat(timespec='seconds'),
            'end_time': datetime.now().isoformat(timespec='seconds'),
            'total_tests': total,
            'passed_tests': passed,
            'failed_tests': failed,
            'duration_seconds': (datetime.now() - self.start_time).total_seconds(),
            'results': self.results,
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return report_path

    def _run_module_main(self, module_name: str) -> bool:
        # 動的 import（PyInstaller で確実に取り込ませるため、このモジュールは diagnostic_runner が import する）
        module = __import__(f'{__package__}.{module_name}', fromlist=['main'])

        if not hasattr(module, 'main'):
            raise AttributeError(f'main() が見つかりません: {module_name}')

        old_argv = sys.argv
        sys.argv = [module_name + '.py']
        try:
            if self._cli_args.get('verbose'):
                sys.argv.append('--verbose')

            # --allow-mitm / --no-mitm
            if self._cli_args.get('allow_mitm'):
                sys.argv.append('--allow-mitm')
            if self._cli_args.get('no_mitm'):
                sys.argv.append('--no-mitm')

            if self._cli_args.get('timeout'):
                sys.argv.extend(['--timeout', str(self._cli_args['timeout'])])

            if self._cli_args.get('config'):
                sys.argv.extend(['--config', str(self._cli_args['config'])])

            try:
                module.main()
                return True
            except SystemExit as e:
                return (e.code == 0) if isinstance(e.code, int) else True
        finally:
            sys.argv = old_argv

    def run_all_diagnostics(self):
        total = len(self._tasks)
        for idx, task in enumerate(self._tasks, start=1):
            self.log(f"[{idx}/{total}] ▶ 開始: {task.description}")
            started = time.time()
            try:
                success = self._run_module_main(task.module_name)
                duration = time.time() - started
                self.results[task.module_name + '.py'] = {
                    'description': task.description,
                    'success': bool(success),
                    'return_code': 0 if success else 1,
                    'duration': duration,
                }
                if success:
                    self.log(f"✅ {task.description} 完了", 'SUCCESS')
                else:
                    self.log(f"❌ {task.description} 失敗", 'ERROR')
            except Exception as e:
                duration = time.time() - started
                self.results[task.module_name + '.py'] = {
                    'description': task.description,
                    'success': False,
                    'return_code': 1,
                    'duration': duration,
                    'error': str(e),
                }
                self.log(f"❌ 実行エラー: {task.module_name}: {e}", 'ERROR')

        report_path = self._write_report()
        self.log(f"レポート出力: {report_path}", 'INFO')
