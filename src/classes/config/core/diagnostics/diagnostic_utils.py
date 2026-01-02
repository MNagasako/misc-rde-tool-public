"""
プロキシ診断ツール共通ユーティリティ v2.1.6

設定ファイルの読み込み、CLI引数の解析、共通関数を提供します。

注意:
- 本体同梱前提のため tests フォルダには依存しない。
- パスは config.common 経由で解決する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional
import argparse


class DiagnosticConfig:
    """診断ツール設定クラス"""

    DEFAULT_CONFIG = {
        'timeout': {
            'request': 10,
            'subprocess': 90,
            'socket': 1,
        },
        'mitm': {
            'allow': True,
            'on_detect': 'warn',
        },
        'connection_stability': {
            'consecutive_count': 3,
            'new_session_count': 2,
            'reconfiguration_count': 2,
            'delay': 0.1,
        },
        'retry': {
            'max_attempts': 2,
            'delay': 0.5,
            'on_errors': ['Timeout', 'ConnectionError'],
        },
        'logging': {
            'level': 'INFO',
            'verbose': False,
        },
        'test_urls': {
            'primary': 'https://httpbin.org/get',
            'ssl': 'https://httpbin.org/get',
            'fallback': 'https://www.google.com',
        },
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.config = self.DEFAULT_CONFIG.copy()

        if config_path is None:
            # 設定ファイルは src/resources 配下に置く（tests非依存）
            try:
                from config.common import get_static_resource_path

                config_path = Path(get_static_resource_path('resources/diagnostic_config.yaml'))
            except Exception:
                config_path = None

        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path):
        try:
            import yaml

            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)

            if file_config:
                self._merge_config(self.config, file_config)
        except Exception as e:
            print(f"⚠️  設定ファイル読み込みエラー: {e}")
            print("デフォルト設定を使用します")

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def override_from_args(self, args: argparse.Namespace):
        if hasattr(args, 'timeout') and args.timeout is not None:
            self.config['timeout']['request'] = args.timeout

        if hasattr(args, 'allow_mitm') and args.allow_mitm is not None:
            self.config['mitm']['allow'] = args.allow_mitm

        if hasattr(args, 'no_mitm') and args.no_mitm:
            self.config['mitm']['allow'] = False

        if hasattr(args, 'verbose') and args.verbose:
            self.config['logging']['verbose'] = True
            self.config['logging']['level'] = 'DEBUG'

        if hasattr(args, 'test_url') and args.test_url:
            self.config['test_urls']['primary'] = args.test_url

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split('.')
        value: Any = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any):
        keys = key_path.split('.')
        target = self.config

        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value


def add_common_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument('--timeout', type=int, help='HTTPリクエストのタイムアウト（秒）')

    parser.add_argument('--allow-mitm', action='store_true', help='ローカルMitMプロキシ（Fiddler等）を許容する')

    parser.add_argument('--no-mitm', action='store_true', help='MitMプロキシを許容しない（SSL検証エラーを失敗扱い）')

    parser.add_argument('--verbose', '-v', action='store_true', help='詳細ログを表示')

    parser.add_argument('--test-url', help='テストするURL')

    parser.add_argument('--config', type=Path, help='設定ファイルのパス')

    return parser


def load_config_with_args(args: Optional[argparse.Namespace] = None) -> DiagnosticConfig:
    config_path = None
    if args and hasattr(args, 'config') and args.config:
        config_path = args.config

    config = DiagnosticConfig(config_path)

    if args:
        config.override_from_args(args)

    return config


def is_local_mitm_detected() -> bool:
    import urllib.request

    proxies = urllib.request.getproxies() or {}
    local_patterns = ['localhost', '127.0.0.1', '::1']

    for proxy_url in proxies.values():
        if proxy_url and any(pattern in str(proxy_url).lower() for pattern in local_patterns):
            return True

    return False


def should_ignore_ssl_error(config: DiagnosticConfig, error: Exception) -> bool:
    # MitM許容設定がFalseなら常に失敗扱い
    if not config.get('mitm.allow', True):
        return False

    try:
        import requests

        is_ssl_error = isinstance(error, requests.exceptions.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(error)
    except Exception:
        is_ssl_error = "CERTIFICATE_VERIFY_FAILED" in str(error)

    if not is_ssl_error:
        return False

    if is_local_mitm_detected():
        return True

    return False
