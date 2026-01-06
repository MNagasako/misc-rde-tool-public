from __future__ import annotations

import argparse

from datetime import datetime, timezone

from classes.core.latest_json_generator import (
    build_latest_json,
    compute_sha256,
    default_installer_path,
    default_public_url,
    read_version_from_version_txt,
    write_latest_json,
)
from config.common import get_dynamic_file_path


def main() -> int:
    parser = argparse.ArgumentParser(description="latest.json を生成する")
    parser.add_argument(
        "--version",
        default=None,
        help="バージョン（省略時は VERSION.txt から取得）",
    )
    parser.add_argument(
        "--installer",
        default=None,
        help="インストーラexeのパス（省略時は setup/Output/arim_rde_tool_setup.<version>.exe）",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="公開先URL（省略時は GitHub Releases のデフォルトURLを生成）",
    )
    parser.add_argument(
        "--updated-at",
        default=None,
        help="更新日時ISO8601（省略時はUTC現在時刻）",
    )
    parser.add_argument(
        "--out",
        default=get_dynamic_file_path("latest.json"),
        help="出力先latest.json（既定: リポジトリ直下 latest.json）",
    )

    args = parser.parse_args()

    version = (args.version or "").strip() or read_version_from_version_txt()
    installer_path = (args.installer or "").strip() or default_installer_path(version)
    url = (args.url or "").strip() or default_public_url(version)
    updated_at = (args.updated_at or "").strip() or datetime.now(timezone.utc).isoformat()

    sha256 = compute_sha256(installer_path)
    payload = build_latest_json(version=version, url=url, sha256=sha256, updated_at=updated_at)
    write_latest_json(args.out, payload)

    print(args.out)
    print(payload["version"])
    print(payload["sha256"])
    print(payload["url"])
    print(payload["updatedAt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
