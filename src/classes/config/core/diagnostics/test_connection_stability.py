"""連続接続安定性テストツール v2.1.6（本体同梱版）

複数回連続でHTTPリクエストを実行し、接続の安定性を検証します。
セッションキャッシュ、プロキシ設定の永続性、SSL設定の一貫性を確認。

HTTP通信は net.http_helpers / net.session_manager 経由。
"""

from __future__ import annotations

import io
import sys
import time
from datetime import datetime
from typing import Dict, List, Any
import argparse

from net.session_manager import configure_proxy_session, get_proxy_session, create_new_proxy_session
from net.http_helpers import proxy_get

from .diagnostic_utils import DiagnosticConfig, add_common_arguments, load_config_with_args


# 標準出力をUTF-8に設定（Windows cp932対策）
if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class ConnectionStabilityTest:
    def __init__(self, config: DiagnosticConfig = None, test_url: str = None, default_config: Dict[str, Any] = None):
        self.config = config or DiagnosticConfig()
        self.test_url = test_url or self.config.get('test_urls.primary', 'https://httpbin.org/get')
        self.timeout = self.config.get('timeout.request', 30)
        self.results: List[Dict[str, Any]] = []

        self.default_config = default_config or {
            'mode': 'DIRECT',
        }

        configure_proxy_session(self.default_config)

    def log(self, message: str, level: str = 'INFO'):
        icons = {
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'ERROR': '❌',
            'WARNING': '⚠️',
            'DEBUG': '🔍',
        }
        icon = icons.get(level, '📝')
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] {icon} {message}")

    def single_request(self, iteration: int, session_reuse: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'iteration': iteration,
            'success': False,
            'status_code': None,
            'response_time': None,
            'error': None,
            'session_id': None,
            'verify': None,
            'proxies': None,
        }

        try:
            start = time.time()

            if session_reuse:
                session = get_proxy_session()
            else:
                session = create_new_proxy_session(self.default_config)

            result['session_id'] = id(session)
            result['verify'] = getattr(session, 'verify', None)
            result['proxies'] = getattr(session, 'proxies', None)

            resp = session.get(self.test_url, timeout=self.timeout)
            result['status_code'] = resp.status_code
            result['success'] = resp.status_code == 200
            result['response_time'] = time.time() - start

            return result
        except Exception as e:
            result['error'] = str(e)
            result['response_time'] = time.time() - start
            return result

    def run_consecutive_requests(self) -> bool:
        count = int(self.config.get('connection_stability.consecutive_count', 3))
        delay = float(self.config.get('connection_stability.delay', 0.1))

        self.log(f"=== 連続リクエスト（同一セッション） {count} 回 ===", 'INFO')
        ok = True
        for i in range(1, count + 1):
            r = self.single_request(i, session_reuse=True)
            self.results.append(r)
            if r['success']:
                self.log(f"[{i}/{count}] ✅ {r['status_code']} {r['response_time']:.2f}s", 'SUCCESS')
            else:
                ok = False
                self.log(f"[{i}/{count}] ❌ {r.get('error')}", 'ERROR')
            time.sleep(delay)
        return ok

    def run(self) -> bool:
        return self.run_consecutive_requests()


def main():
    parser = argparse.ArgumentParser(description='連続接続安定性テスト')
    add_common_arguments(parser)
    parser.add_argument('--test-url', help='テストURL')
    args = parser.parse_args()

    config = load_config_with_args(args)
    test = ConnectionStabilityTest(config=config, test_url=args.test_url)
    ok = test.run()
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
