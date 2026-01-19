#!/usr/bin/env python3

"""ARIM RDE Tool CLI helper.

GUI版（PyInstaller: console=False/runw）の `--version` は、
環境（ConPTY/企業端末制御など）によってはコンソールへ出力できない場合がある。

その場合でも利用者が確実にバージョンを確認できるよう、
最小依存のコンソール用エントリポイントを提供する。
"""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--version", "-v", action="store_true", help="バージョン情報を表示して終了")
    args = parser.parse_args()

    if args.version:
        # config.common は VERSION.txt を SoT として REVISION を公開する。
        from config.common import REVISION

        print(str(REVISION))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
