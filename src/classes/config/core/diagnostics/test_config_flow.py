"""プロキシ設定の保存・読み込みフロー診断ツール v2.1.6（本体同梱版）

network.yaml の読み書きと設定値の追跡を検証します。
UI → YAML → SessionManager → Session の変換フローを追跡。

注意:
- tests 配下に依存しない。
- パスは config.common.get_dynamic_file_path() を使用する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional
import io
import sys
import json

import yaml

from config.common import get_dynamic_file_path
from net.session_manager import configure_proxy_session, get_proxy_session


# 標準出力をUTF-8に設定（Windows cp932対策）
if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class ProxyConfigDiagnostics:
    def __init__(self):
        self.config_path = Path(get_dynamic_file_path('config/network.yaml'))
        self.original_config: Optional[Dict[str, Any]] = None

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

    def backup_current_config(self) -> bool:
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.original_config = yaml.safe_load(f)
                self.log(f"現在の設定をバックアップ: {self.config_path}", 'SUCCESS')
                return True

            self.log('network.yaml が存在しません', 'WARNING')
            self.original_config = None
            return False
        except Exception as e:
            self.log(f"バックアップエラー: {e}", 'ERROR')
            return False

    def restore_config(self) -> bool:
        try:
            if self.original_config is not None:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.original_config, f, allow_unicode=True, default_flow_style=False)
                self.log('設定を復元しました', 'SUCCESS')
                return True
            return False
        except Exception as e:
            self.log(f"復元エラー: {e}", 'ERROR')
            return False

    def save_test_config(self, config: Dict[str, Any], description: str) -> bool:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            self.log(f"テスト設定を書き込み: {description}", 'INFO')
            return True
        except Exception as e:
            self.log(f"書き込みエラー: {e}", 'ERROR')
            return False

    def verify_session_state(self, expected_mode: str) -> bool:
        try:
            session = get_proxy_session()
            proxies = getattr(session, 'proxies', {})
            mode_ok = True

            if expected_mode.upper() == 'DIRECT':
                mode_ok = not bool(proxies)

            self.log(f"セッション proxies={proxies}", 'DEBUG')
            return bool(mode_ok)
        except Exception as e:
            self.log(f"セッション検証エラー: {e}", 'ERROR')
            return False

    def run(self) -> bool:
        self.log('=== プロキシ設定フロー診断 ===', 'INFO')

        self.backup_current_config()
        try:
            # DIRECT
            direct_config = {'network': {'mode': 'DIRECT'}}
            if self.save_test_config(direct_config, 'DIRECT モード'):
                configure_proxy_session(None)
                if not self.verify_session_state('DIRECT'):
                    self.log('DIRECT モード検証失敗', 'ERROR')
                    return False

            # STATIC の最低限
            static_config = {
                'network': {
                    'mode': 'STATIC',
                    'proxies': {'http': 'http://127.0.0.1:8888', 'https': 'http://127.0.0.1:8888'},
                    'cert': {'verify': False, 'use_os_store': True},
                }
            }
            if self.save_test_config(static_config, 'STATIC(ローカル) モード'):
                configure_proxy_session(None)
                # プロキシが設定されることだけ確認
                session = get_proxy_session()
                proxies = getattr(session, 'proxies', {})
                if not proxies:
                    self.log('STATIC モードで proxies が空です', 'ERROR')
                    return False

            self.log('✅ 設定フロー診断 完了', 'SUCCESS')
            return True
        finally:
            self.restore_config()


def main():
    diagnostics = ProxyConfigDiagnostics()
    ok = diagnostics.run()
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
