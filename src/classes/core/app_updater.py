"""アプリ更新（GitHub Releases 配布用）

方式: latest.json で更新検知 → インストーラexeをDL → sha256検証 → Inno Setup をサイレント実行 → アプリ終了。

- HTTPアクセスは net.http_helpers 経由
- パスは config.common の動的パスを使用
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from config.common import get_dynamic_file_path

logger = logging.getLogger(__name__)


DEFAULT_LATEST_JSON_URL = (
    "https://raw.githubusercontent.com/MNagasako/misc-rde-tool-public/main/latest.json"
)


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str
    sha256: str
    updated_at: str


def _normalize_updated_at(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        # 形式不正でも更新チェック自体は継続する
        return ""


def _parse_version_to_tuple(version: str) -> Tuple[int, ...]:
    """バージョン文字列を比較可能なタプルへ変換する。

    例:
    - "2.4.10" -> (2, 4, 10)
    - "v2.4.6" -> (2, 4, 6)
    - "2.4.6-beta1" -> (2, 4, 6, 1)

    文字列比較は禁止（2.4.10 > 2.4.4 を正しく扱う）。
    """
    parts = re.findall(r"\d+", str(version or ""))
    if not parts:
        return (0,)
    try:
        return tuple(int(p) for p in parts)
    except Exception:
        return (0,)


def _is_newer(current_version: str, latest_version: str) -> bool:
    return _parse_version_to_tuple(latest_version) > _parse_version_to_tuple(current_version)


def _load_latest_json(url: str, timeout: int = 15) -> dict:
    from net.http_helpers import proxy_get

    resp = proxy_get(url, timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return json.loads(resp.text)


def check_update(
    current_version: str,
    latest_json_url: str = DEFAULT_LATEST_JSON_URL,
    timeout: int = 15,
) -> Tuple[bool, str, str, str, str]:
    """更新有無を確認する。

    Returns:
        (has_update, latest_version, url, sha256, updated_at)
    """
    try:
        data = _load_latest_json(latest_json_url, timeout=timeout)
        if not isinstance(data, dict):
            raise ValueError("latest.json が辞書形式ではありません")

        version = str(data.get("version", "") or "").strip()
        url = str(data.get("url", "") or "").strip()
        sha256 = str(data.get("sha256", "") or "").strip().lower()
        updated_at = _normalize_updated_at(str(data.get("updatedAt", "") or ""))

        if not version or not url or not sha256:
            raise ValueError("latest.json に version/url/sha256 が不足しています")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("sha256 の形式が不正です（64桁hex）")

        has_update = _is_newer(current_version, version)
        return has_update, version, url, sha256, updated_at
    except Exception as e:
        logger.warning("更新確認に失敗: %s", e)
        return False, "", "", "", ""


def download(url: str, dst_path: str, timeout: int = 60) -> str:
    """インストーラをダウンロードして dst_path に保存する。"""
    from net.http_helpers import proxy_get

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    resp = proxy_get(url, timeout=timeout, stream=True)
    resp.raise_for_status()

    tmp_path = dst_path + ".download"
    with open(tmp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            f.write(chunk)

    os.replace(tmp_path, dst_path)
    return dst_path


def verify_sha256(path: str, expected: str) -> bool:
    """sha256を検証する（不一致なら False）。"""
    expected = str(expected or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("expected sha256 の形式が不正です（64桁hex）")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    return actual == expected


def _default_installer_log_path(version: str) -> str:
    safe_version = re.sub(r"[^0-9A-Za-z._-]", "_", str(version or ""))
    return get_dynamic_file_path(f"output/.private/update/installer_{safe_version}.log")


def run_installer_and_exit(installer_path: str, log_path: Optional[str] = None) -> None:
    """Inno Setup インストーラをサイレント実行してアプリを終了する。

    NOTE: テストでは subprocess.Popen / os._exit を monkeypatch して使用すること。
    """
    if sys.platform != "win32":
        raise RuntimeError("Windows以外ではインストーラ実行はサポートしていません")

    if not installer_path or not os.path.exists(installer_path):
        raise FileNotFoundError(f"インストーラが見つかりません: {installer_path}")

    log_path = log_path or _default_installer_log_path("latest")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    args = [
        installer_path,
        "/SP-",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/LOG={log_path}",
    ]

    logger.info("インストーラ起動: %s", " ".join(args))
    subprocess.Popen(args, close_fds=True)

    # できるだけ穏当な終了を試みる
    try:
        from qt_compat.widgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()
    except Exception:
        pass

    os._exit(0)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def should_check_once_per_day(last_checked_iso: Optional[str], now: Optional[datetime] = None) -> bool:
    """最後のチェックから1日以上経過しているか判定。"""
    now = now or _now_utc()
    if not last_checked_iso:
        return True
    try:
        last = datetime.fromisoformat(last_checked_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception:
        return True

    return now - last >= timedelta(days=1)


def get_default_download_path(version: str) -> str:
    filename = f"arim_rde_tool_setup.{version}.exe" if version else "arim_rde_tool_setup.latest.exe"
    return get_dynamic_file_path(f"output/.private/update/{filename}")
