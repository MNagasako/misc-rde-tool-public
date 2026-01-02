#!/usr/bin/env python3
"""SSL/CA証明書診断ツール v2.1.6（本体同梱版）

- HTTP通信は net.http_helpers / net.session_manager 経由で実施
- 例外型判定等で requests を使う場合があるが、requests.get などの直接呼び出しは行わない
"""

from __future__ import annotations

import sys
import io
import argparse
import ssl
import socket
from datetime import datetime
from typing import Dict, Optional, Tuple
import urllib.request

from net.session_manager import get_proxy_session, configure_proxy_session, create_new_proxy_session
from net.http_helpers import proxy_get


# 標準出力をUTF-8に設定（Windows cp932対策）
if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class SSLCertificateDiagnostics:
    def __init__(self, test_url: str = 'https://httpbin.org/get', verbose: bool = False):
        self.test_url = test_url
        self.verbose = verbose
        self.results: Dict[str, object] = {}

        from urllib.parse import urlparse

        parsed = urlparse(test_url)
        self.hostname = parsed.hostname or 'httpbin.org'
        self.port = parsed.port or 443

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

        if self.verbose or level != 'DEBUG':
            print(full_message)

    def check_truststore_availability(self) -> Dict[str, object]:
        self.log('=== 1. truststore利用可能性チェック ===', 'INFO')

        info: Dict[str, object] = {
            'available': False,
            'version': None,
            'can_create_context': False,
            'error': None,
        }

        try:
            import truststore

            info['available'] = True
            info['version'] = getattr(truststore, '__version__', None)

            try:
                ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                _ = ctx  # keep
                info['can_create_context'] = True
            except Exception as e:
                info['error'] = str(e)

            self.log(f"truststore available={info['available']} version={info['version']}", 'SUCCESS')
        except Exception as e:
            info['error'] = str(e)
            self.log(f"truststore import failed: {e}", 'WARNING')

        self.results['truststore'] = info
        return info

    def test_https_with_verify_true(self) -> bool:
        self.log('\n=== 2. verify=True での HTTPS 疎通 ===', 'INFO')
        try:
            # 現行プロキシ/SSL設定のセッションで verify=True 指定
            resp = proxy_get(self.test_url, verify=True, timeout=10)
            self.log(f"status={resp.status_code}", 'SUCCESS')
            return resp.status_code == 200
        except Exception as e:
            self.log(f"verify=True failed: {e}", 'ERROR')
            return False

    def test_https_with_verify_false(self) -> bool:
        self.log('\n=== 3. verify=False での HTTPS 疎通 ===', 'INFO')
        try:
            resp = proxy_get(self.test_url, verify=False, timeout=10)
            self.log(f"status={resp.status_code}", 'SUCCESS')
            return resp.status_code == 200
        except Exception as e:
            self.log(f"verify=False failed: {e}", 'ERROR')
            return False

    def test_socket_tls_handshake(self) -> bool:
        self.log('\n=== 4. ソケットTLSハンドシェイク（参考） ===', 'INFO')
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((self.hostname, self.port), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=self.hostname) as ssock:
                    _ = ssock.version()
            self.log('TLS handshake OK', 'SUCCESS')
            return True
        except Exception as e:
            self.log(f"TLS handshake failed: {e}", 'WARNING')
            return False

    def run(self) -> bool:
        self.check_truststore_availability()
        ok1 = self.test_https_with_verify_true()
        ok2 = self.test_https_with_verify_false()
        ok3 = self.test_socket_tls_handshake()
        return bool(ok1 or ok2 or ok3)


def main():
    parser = argparse.ArgumentParser(description='SSL/CA証明書診断ツール')
    parser.add_argument('--test-url', default='https://httpbin.org/get')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    diag = SSLCertificateDiagnostics(test_url=args.test_url, verbose=args.verbose)
    ok = diag.run()
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
