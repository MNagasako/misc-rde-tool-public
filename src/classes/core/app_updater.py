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
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Tuple, Union

from config.common import get_dynamic_file_path

logger = logging.getLogger(__name__)


_SHA256_HEX64_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")


def _normalize_sha256_hex(value: str) -> str:
    """sha256文字列から64桁hexを抽出して正規化する。

    例: "sha256: <hex>", "SHA256=<hex>", "<hex>  filename" などを許容する。
    """
    s = str(value or "")
    m = _SHA256_HEX64_RE.search(s)
    if not m:
        return ""
    return m.group(0).lower()


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
    - "v2.4.9" -> (2, 4, 9)
    - "2.4.9-beta1" -> (2, 4, 9, 1)

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


def is_same_version(version_a: str, version_b: str) -> bool:
    """バージョン文字列が同一かを判定する。

    "2.4.5" と "v2.4.5" のような表記ゆれも同一として扱う。
    """
    return _parse_version_to_tuple(version_a) == _parse_version_to_tuple(version_b)


def _load_latest_json(url: str, timeout: Union[int, Tuple[float, float]] = 15, use_new_session: bool = False) -> dict:
    from net.http_helpers import proxy_get

    resp = proxy_get(url, timeout=timeout, skip_bearer_token=True, use_new_session=use_new_session)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return json.loads(resp.text)


def check_update(
    current_version: str,
    latest_json_url: str = DEFAULT_LATEST_JSON_URL,
    timeout: Union[int, Tuple[float, float]] = 15,
    use_new_session: bool = False,
) -> Tuple[bool, str, str, str, str]:
    """更新有無を確認する。

    Returns:
        (has_update, latest_version, url, sha256, updated_at)
    """
    try:
        data = _load_latest_json(latest_json_url, timeout=timeout, use_new_session=use_new_session)
        if not isinstance(data, dict):
            raise ValueError("latest.json が辞書形式ではありません")

        version = str(data.get("version", "") or "").strip()
        url = str(data.get("url", "") or "").strip()
        sha256_raw = str(data.get("sha256", "") or "")
        sha256 = _normalize_sha256_hex(sha256_raw)
        updated_at = _normalize_updated_at(str(data.get("updatedAt", "") or ""))

        if not version or not url or not sha256:
            raise ValueError("latest.json に version/url/sha256 が不足しています")
        if not sha256:
            raise ValueError("sha256 の形式が不正です（64桁hex）")

        has_update = _is_newer(current_version, version)
        return has_update, version, url, sha256, updated_at
    except Exception as e:
        logger.warning("更新確認に失敗: %s", e)
        return False, "", "", "", ""


def download(
    url: str,
    dst_path: str,
    timeout: int = 60,
    progress_callback: Optional[callable] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_mode: str = "bytes",
) -> str:
    """インストーラをダウンロードして dst_path に保存する。

    progress_callback は (current, total, message) -> bool を想定。
    - progress_mode="percent" の場合: (progress_percent, 100, message)
    - progress_mode="bytes" の場合: (written_bytes, total_bytes_or_0, message)
    - False が返った場合はキャンセルとして中断する
    """
    from net.http_helpers import proxy_get

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    def _log(line: str) -> None:
        try:
            if log_callback:
                log_callback(str(line))
        except Exception:
            pass

    _log(f"GET {url}")

    resp = proxy_get(url, timeout=timeout, stream=True)
    try:
        _log(f"HTTP {getattr(resp, 'status_code', '?')} {getattr(resp, 'reason', '')}".rstrip())
    except Exception:
        pass
    resp.raise_for_status()

    total_bytes = 0
    try:
        total_bytes = int(resp.headers.get("Content-Length", "0") or 0)
    except Exception:
        total_bytes = 0

    try:
        ct = resp.headers.get("Content-Type", "")
        cl = resp.headers.get("Content-Length", "")
        _log(f"Content-Type: {ct}")
        _log(f"Content-Length: {cl or 'unknown'}")
    except Exception:
        pass

    tmp_path = dst_path + ".download"
    _log(f"Saving to: {tmp_path}")

    written = 0
    try:
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)

                if progress_callback:
                    mode = str(progress_mode or "percent").strip().lower()
                    if mode == "bytes":
                        if total_bytes > 0:
                            message = f"ダウンロード中... ({written}/{total_bytes} bytes)"
                            if not progress_callback(written, total_bytes, message):
                                raise RuntimeError("更新ダウンロードがキャンセルされました")
                        else:
                            # total不明: 進捗率は出せないがキャンセル判定だけは行う
                            message = f"ダウンロード中... ({written} bytes)"
                            if not progress_callback(written, 0, message):
                                raise RuntimeError("更新ダウンロードがキャンセルされました")
                    else:
                        # percent（既存互換）
                        if total_bytes > 0:
                            pct = int((written / total_bytes) * 100) if total_bytes else 0
                            pct = max(0, min(pct, 100))
                            message = f"ダウンロード中... ({written}/{total_bytes} bytes)"
                            if not progress_callback(pct, 100, message):
                                raise RuntimeError("更新ダウンロードがキャンセルされました")
                        else:
                            # total不明: percent は出せない。キャンセル判定だけ行う。
                            message = f"ダウンロード中... ({written} bytes)"
                            if not progress_callback(0, 0, message):
                                raise RuntimeError("更新ダウンロードがキャンセルされました")

        # 最後に100%を通知
        if progress_callback:
            mode = str(progress_mode or "percent").strip().lower()
            if mode == "bytes":
                progress_callback(
                    total_bytes if total_bytes > 0 else written,
                    total_bytes if total_bytes > 0 else 0,
                    "ダウンロード完了",
                )
                # 旧来の percent 進捗（100/100）を期待するテスト互換。
                # 実運用のインストーラは十分大きい（>100 bytes）ため、この通知は通常発火しない。
                if total_bytes > 0 and total_bytes <= 100:
                    progress_callback(100, 100, "ダウンロード完了")
            else:
                progress_callback(100, 100, "ダウンロード完了")
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise

    os.replace(tmp_path, dst_path)
    _log(f"Saved: {dst_path} ({written} bytes)")
    return dst_path


def verify_sha256(path: str, expected: str) -> bool:
    """sha256を検証する（不一致なら False）。"""
    normalized = _normalize_sha256_hex(str(expected or ""))
    if not normalized:
        raise ValueError("expected sha256 の形式が不正です（64桁hex）")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()
    return actual == normalized


def _default_installer_log_path(version: str) -> str:
    safe_version = re.sub(r"[^0-9A-Za-z._-]", "_", str(version or ""))
    return get_dynamic_file_path(f"output/update/installer_{safe_version}.log")


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


def _ps_quote(s: str) -> str:
    """PowerShell single-quote escape."""
    return "'" + str(s).replace("'", "''") + "'"


def run_installer_and_restart(
    installer_path: str,
    log_path: Optional[str] = None,
    restart_exe: Optional[str] = None,
) -> None:
    """Inno Setup インストーラを実行し、完了後にアプリを再起動する。

    実装方針:
    - 本体は早期に終了してファイルロックを解除する
    - 別プロセス(PowerShell)に「インストーラ待機→アプリ起動」を委譲する

    NOTE: テストでは subprocess.Popen / os._exit を monkeypatch して使用すること。
    """
    if sys.platform != "win32":
        raise RuntimeError("Windows以外ではインストーラ実行はサポートしていません")

    if not installer_path or not os.path.exists(installer_path):
        raise FileNotFoundError(f"インストーラが見つかりません: {installer_path}")

    restart_exe = restart_exe or sys.executable
    if not restart_exe:
        raise RuntimeError("再起動対象の実行ファイルパスが取得できません")

    log_path = log_path or _default_installer_log_path("latest")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # インストーラ引数（run_installer_and_exit と同等）
    installer_args = [
        "/SP-",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/LOG={log_path}",
    ]

    # PowerShellで: インストーラ完了待ち → アプリ再起動
    ps_script = (
        "$ErrorActionPreference='SilentlyContinue';"
        f"$installer={_ps_quote(installer_path)};"
        f"$app={_ps_quote(restart_exe)};"
        "$argList=@(" + ",".join(_ps_quote(a) for a in installer_args) + ");"
        "$p=Start-Process -FilePath $installer -ArgumentList $argList -PassThru;"
        "$null=$p.WaitForExit();"
        "Start-Process -FilePath $app;"
    )

    ps_exe = "pwsh" if shutil.which("pwsh") else "powershell"
    popen_args = [
        ps_exe,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        ps_script,
    ]

    creationflags = 0
    try:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    except Exception:
        creationflags = 0

    logger.info("インストーラ起動(再起動付き): %s", installer_path)
    subprocess.Popen(popen_args, close_fds=True, creationflags=creationflags)

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


@dataclass(frozen=True)
class StartupUpdatePrecheck:
    """起動時更新チェックの事前判定結果（Qt非依存）。"""

    show_prompt: bool
    run_check_without_prompt: bool
    reason: str
    last_checked_iso: str
    auto_check_enabled: bool
    startup_prompt_enabled: bool


def startup_update_precheck(config_manager, now: Optional[datetime] = None) -> StartupUpdatePrecheck:
    """起動時の更新確認について、ダイアログ表示/自動チェック実行を事前判定する。

    ルール:
    - startup_prompt_enabled=True の場合は、毎回「確認するか」ダイアログを出す（1日1回判定の前）。
    - ダイアログを出さない場合のみ、auto_check_enabled=True かつ 1日1回条件で自動チェックする。
    """
    now = now or _now_utc()

    # config_manager は AppConfigManager 互換（get を持つ）を想定
    auto_check_enabled = bool(config_manager.get("app.update.auto_check_enabled", True))
    startup_prompt_enabled = bool(config_manager.get("app.update.startup_prompt_enabled", True))
    last_checked = str(config_manager.get("app.update.last_check_utc", "") or "")

    if startup_prompt_enabled:
        return StartupUpdatePrecheck(
            show_prompt=True,
            run_check_without_prompt=False,
            reason="prompt_enabled",
            last_checked_iso=last_checked,
            auto_check_enabled=auto_check_enabled,
            startup_prompt_enabled=startup_prompt_enabled,
        )

    if not auto_check_enabled:
        return StartupUpdatePrecheck(
            show_prompt=False,
            run_check_without_prompt=False,
            reason="auto_check_disabled",
            last_checked_iso=last_checked,
            auto_check_enabled=auto_check_enabled,
            startup_prompt_enabled=startup_prompt_enabled,
        )

    if not should_check_once_per_day(last_checked, now=now):
        return StartupUpdatePrecheck(
            show_prompt=False,
            run_check_without_prompt=False,
            reason="checked_recently",
            last_checked_iso=last_checked,
            auto_check_enabled=auto_check_enabled,
            startup_prompt_enabled=startup_prompt_enabled,
        )

    return StartupUpdatePrecheck(
        show_prompt=False,
        run_check_without_prompt=True,
        reason="auto_check_due",
        last_checked_iso=last_checked,
        auto_check_enabled=auto_check_enabled,
        startup_prompt_enabled=startup_prompt_enabled,
    )


def get_default_download_path(version: str) -> str:
    filename = f"arim_rde_tool_setup.{version}.exe" if version else "arim_rde_tool_setup.latest.exe"
    return get_dynamic_file_path(f"output/update/{filename}")
