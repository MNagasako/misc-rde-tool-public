#!/usr/bin/env python3
"""基本プロキシ診断ツール v2.1.6（本体同梱版）

requests を直接叩かず、net.session_manager / net.http_helpers 経由で疎通確認する。
"""

from __future__ import annotations

import sys
import os
import io
import argparse
import json
from datetime import datetime
from typing import Dict, Optional

from net.session_manager import get_proxy_session, configure_proxy_session, create_new_proxy_session
from net.http_helpers import proxy_get

from .diagnostic_utils import DiagnosticConfig, add_common_arguments, load_config_with_args


# 標準出力をUTF-8に設定（Windows cp932対策）
if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class ProxyDiagnostics:
    def __init__(self, config: Optional[DiagnosticConfig] = None, test_url: Optional[str] = None, verbose: bool = False):
        self.config = config or DiagnosticConfig()
        self.test_url = test_url or self.config.get('test_urls.primary', 'https://httpbin.org/get')
        self.verbose = verbose or self.config.get('logging.verbose', False)
        self.timeout = self.config.get('timeout.request', 30)
        self.results = []

    def log(self, message: str, level: str = 'INFO'):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        prefix = {
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'ERROR': '❌',
            'WARNING': '⚠️',
            'DEBUG': '🔍',
        }.get(level, '📝')

        full_message = f"[{timestamp}] {prefix} {message}"
        print(full_message)

        if self.verbose or level != 'DEBUG':
            self.results.append({'timestamp': timestamp, 'level': level, 'message': message})

    def check_environment_variables(self) -> Dict[str, Optional[str]]:
        self.log('=== 環境変数の確認 ===', 'INFO')

        env_vars = {
            'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
            'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
            'NO_PROXY': os.environ.get('NO_PROXY'),
            'http_proxy': os.environ.get('http_proxy'),
            'https_proxy': os.environ.get('https_proxy'),
            'no_proxy': os.environ.get('no_proxy'),
        }

        for key, value in env_vars.items():
            if value:
                self.log(f"{key}: {value}", 'SUCCESS')
            else:
                self.log(f"{key}: 未設定", 'DEBUG')

        return env_vars

    def test_proxy_session_request(self) -> bool:
        self.log('\n=== プロキシセッション（アプリ設定）での疎通 ===', 'INFO')

        try:
            response = proxy_get(self.test_url, timeout=self.timeout)
            self.log(f"ステータス: {response.status_code}", 'SUCCESS')
            return response.status_code == 200
        except Exception as e:
            self.log(f"疎通失敗: {e}", 'ERROR')
            return False

    def test_direct_session_request(self) -> bool:
        self.log('\n=== DIRECTセッション（プロキシなし）での疎通 ===', 'INFO')

        try:
            direct_session = create_new_proxy_session({'mode': 'DIRECT'})
            response = direct_session.get(self.test_url, timeout=self.timeout)
            self.log(f"ステータス: {response.status_code}", 'SUCCESS')
            return response.status_code == 200
        except Exception as e:
            self.log(f"疎通失敗: {e}", 'ERROR')
            return False

    def run(self) -> bool:
        self.check_environment_variables()

        # 既定のセッション設定（必要なら診断側で一時上書き可能）
        # ここでは現行設定のまま実行

        ok_proxy = self.test_proxy_session_request()
        ok_direct = self.test_direct_session_request()

        return bool(ok_proxy or ok_direct)


def main():
    parser = argparse.ArgumentParser(description='基本プロキシ診断ツール')
    add_common_arguments(parser)
    parser.add_argument('--test-url', help='テストURL')

    args = parser.parse_args()

    config = load_config_with_args(args)

    diagnostics = ProxyDiagnostics(config=config, test_url=args.test_url, verbose=bool(getattr(args, 'verbose', False)))
    success = diagnostics.run()

    if success:
        print('\n✅ 基本プロキシ診断: 成功')
        raise SystemExit(0)

    print('\n❌ 基本プロキシ診断: 失敗')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
