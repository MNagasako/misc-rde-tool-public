#!/usr/bin/env python3
"""システムプロキシ検出ツール v2.1.6（本体同梱版）

Windows環境のプロキシ設定を複数の方法で検出し、
Fiddlerの起動状態も確認します。

注意:
- tests フォルダに依存しない
"""

from __future__ import annotations

import sys
import os
import io
import argparse
import socket
import subprocess
from datetime import datetime
from typing import Dict, Optional, List


# 標準出力をUTF-8に設定（Windows cp932対策）
if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class SystemProxyDetector:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: Dict[str, object] = {}

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

    def detect_environment_variables(self) -> Dict[str, Optional[str]]:
        self.log('=== 1. 環境変数からの検出 ===', 'INFO')

        env_proxies: Dict[str, Optional[str]] = {}
        proxy_vars = [
            'HTTP_PROXY',
            'HTTPS_PROXY',
            'NO_PROXY',
            'http_proxy',
            'https_proxy',
            'no_proxy',
        ]

        for var in proxy_vars:
            value = os.environ.get(var)
            if value:
                env_proxies[var] = value
                self.log(f"{var}: {value}", 'SUCCESS')
            else:
                self.log(f"{var}: 未設定", 'DEBUG')

        if not env_proxies:
            self.log('環境変数にプロキシ設定なし', 'WARNING')

        self.results['environment_variables'] = env_proxies
        return env_proxies

    def detect_windows_registry(self) -> Dict[str, object]:
        self.log('\n=== 2. Windowsレジストリからの検出 ===', 'INFO')

        registry_info: Dict[str, object] = {}
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            proxy_enable = winreg.QueryValueEx(key, 'ProxyEnable')[0]
            proxy_server = winreg.QueryValueEx(key, 'ProxyServer')[0] if proxy_enable else None
            winreg.CloseKey(key)

            registry_info['ProxyEnable'] = proxy_enable
            registry_info['ProxyServer'] = proxy_server

            if proxy_enable and proxy_server:
                self.log(f"ProxyEnable=1 ProxyServer={proxy_server}", 'SUCCESS')
            else:
                self.log('ProxyEnable=0', 'WARNING')
        except Exception as e:
            registry_info['error'] = str(e)
            self.log(f"レジストリ検出失敗: {e}", 'WARNING')

        self.results['windows_registry'] = registry_info
        return registry_info

    def detect_urllib_proxies(self) -> Dict[str, object]:
        self.log('\n=== 3. urllib からの検出 ===', 'INFO')
        import urllib.request

        proxies = urllib.request.getproxies() or {}
        if proxies:
            for k, v in proxies.items():
                self.log(f"{k}: {v}", 'SUCCESS')
        else:
            self.log('urllib.getproxies() は空です', 'WARNING')

        self.results['urllib'] = proxies
        return proxies

    def check_fiddler_port(self, host: str = '127.0.0.1', port: int = 8888) -> bool:
        self.log('\n=== 4. Fiddler ポート確認 ===', 'INFO')
        try:
            with socket.create_connection((host, port), timeout=1):
                self.log(f"{host}:{port} に接続可能（Fiddler等が起動中の可能性）", 'SUCCESS')
                return True
        except Exception:
            self.log(f"{host}:{port} に接続不可", 'DEBUG')
            return False

    def run(self) -> bool:
        self.detect_environment_variables()
        self.detect_windows_registry()
        self.detect_urllib_proxies()
        _ = self.check_fiddler_port()
        return True


def main():
    parser = argparse.ArgumentParser(description='システムプロキシ検出ツール')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    detector = SystemProxyDetector(verbose=args.verbose)
    ok = detector.run()
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
