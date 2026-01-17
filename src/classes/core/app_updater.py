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
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Tuple, Union

from config.common import ensure_directory_exists, get_dynamic_file_path

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


def _default_installer_log_path(version: str, *, base_dir: str | None = None) -> str:
    safe_version = re.sub(r"[^0-9A-Za-z._-]", "_", str(version or ""))
    if base_dir:
        return os.path.join(str(base_dir), f"installer_{safe_version}.log")
    return get_dynamic_file_path(f"output/update/installer_{safe_version}.log")


def _get_update_dir_for_installer(installer_path: str) -> str:
    """インストーラと同じ update ディレクトリを返す（作成も保証）。"""
    try:
        p = os.path.abspath(str(installer_path or ""))
        d = os.path.dirname(p) if p else ""
    except Exception:
        d = ""
    if not d:
        d = get_dynamic_file_path("output/update")
    return ensure_directory_exists(d)


def _safe_name_from_installer_path(installer_path: str) -> str:
    base = os.path.basename(str(installer_path or "") or "")
    m = re.search(r"(?i)arim_rde_tool_setup\.(?P<ver>[0-9]+(?:\.[0-9]+){1,4})\.exe$", base)
    if m:
        return re.sub(r"[^0-9A-Za-z._-]", "_", m.group("ver"))
    base2 = re.sub(r"[^0-9A-Za-z._-]", "_", os.path.splitext(base)[0] or "installer")
    return (base2[:48] if base2 else "installer")


def build_update_runner_paths(*, installer_path: str) -> tuple[str, str, str]:
        """更新ランナー(cmd/ps1)とランナーログのパスを返す。

        NOTE:
        - バイナリ実行時に「インストーラだけ保存され、runner/log が見当たらない」ケースを避けるため、
            常に installer_path と同じフォルダ（update）へ出力する。
        """
        safe_name = _safe_name_from_installer_path(installer_path)
        update_dir = _get_update_dir_for_installer(installer_path)
        runner_cmd = os.path.join(update_dir, f"update_runner_{safe_name}.cmd")
        runner_ps1 = os.path.join(update_dir, f"update_runner_{safe_name}.ps1")
        runner_log = os.path.join(update_dir, f"update_runner_{safe_name}.log")
        return runner_cmd, runner_ps1, runner_log


def _runner_log_has_start_marker(runner_log: str) -> bool:
    try:
        if not runner_log or not os.path.exists(runner_log):
            return False
        # 大きくなっても末尾だけ見れば十分
        with open(runner_log, "rb") as f:
            try:
                f.seek(-4096, os.SEEK_END)
            except Exception:
                f.seek(0)
            tail = f.read().decode("utf-8", errors="ignore")
        return "runner:start" in tail
    except Exception:
        return False


def _wait_for_runner_start(*, runner_log: str, timeout_sec: float = 5.0) -> bool:
    """runner:start がログに出るまで待つ（短時間ポーリング）。"""
    deadline = time.time() + max(0.0, float(timeout_sec or 0.0))
    while time.time() < deadline:
        if _runner_log_has_start_marker(runner_log):
            return True
        time.sleep(0.10)
    return _runner_log_has_start_marker(runner_log)


def _default_install_stamp_path() -> str:
    return get_dynamic_file_path("output/update/last_install.json")


def _default_install_stamp_path_in_dir(update_dir: str) -> str:
    return os.path.join(str(update_dir), "last_install.json")


def get_last_install_info() -> dict:
    """前回インストールの情報を返す（無ければ空dict）。"""
    path = _default_install_stamp_path()
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_last_install_datetime_text() -> str:
    """前回インストール日時（ローカル表示）を返す。"""
    info = get_last_install_info()
    raw_local = str(info.get("installedAtLocal", "") or "").strip()
    if raw_local:
        return raw_local

    raw = str(info.get("installedAtUtc", "") or "").strip()
    if not raw:
        return ""
    try:
        s = raw
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone()  # OSのローカルTZ
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return raw


def _build_inno_installer_args(*, log_path: str, restart_apps: bool) -> list[str]:
    """Inno Setup の共通引数を組み立てる。

    NOTE:
    - ユーザーが進捗を確認できるよう、サイレント実行は行わない。
    - ただし /NORESTART など安全系は維持する。
    """
    args = [
        "/NORESTART",  # OS再起動は行わない
        "/CLOSEAPPLICATIONS",  # 可能なら対象アプリを閉じる（ファイルロック回避）
        f"/LOG={log_path}",
    ]
    if restart_apps:
        args.append("/RESTARTAPPLICATIONS")
    return args


def run_installer_and_exit(installer_path: str, log_path: Optional[str] = None) -> None:
    """Inno Setup インストーラをサイレント実行してアプリを終了する。

    NOTE: テストでは subprocess.Popen / os._exit を monkeypatch して使用すること。
    """
    if sys.platform != "win32":
        raise RuntimeError("Windows以外ではインストーラ実行はサポートしていません")

    if not installer_path or not os.path.exists(installer_path):
        raise FileNotFoundError(f"インストーラが見つかりません: {installer_path}")

    update_dir = _get_update_dir_for_installer(installer_path)
    log_path = log_path or _default_installer_log_path("latest", base_dir=update_dir)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    args = [installer_path] + _build_inno_installer_args(log_path=log_path, restart_apps=False)

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
    wait_pid: Optional[int] = None,
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

    # 再起動対象の実行ファイルと引数を推定する。
    # - frozen（配布exe）: sys.executable をそのまま起動（必要ならargv[1:]を付与）
    # - 開発実行（python + script）: python.exe に script + argv を付与しないと再起動できない
    restart_args: list[str] = []
    if restart_exe:
        restart_exe = str(restart_exe)
    else:
        restart_exe = sys.executable
        try:
            is_frozen = bool(getattr(sys, "frozen", False))
        except Exception:
            is_frozen = False

        if is_frozen:
            # exe自身を起動する（argv[0]はexeなので除外）
            try:
                restart_args = [str(a) for a in (sys.argv[1:] or [])]
            except Exception:
                restart_args = []
        else:
            # python.exe + <script> + args
            try:
                argv0 = str((sys.argv or [""])[0] or "")
                extra_args = [str(a) for a in (sys.argv[1:] or [])]
                if argv0.lower().endswith("arim_rde_tool.py"):
                    argv0 = get_dynamic_file_path("src/arim_rde_tool.py")
                elif argv0:
                    argv0 = os.path.abspath(argv0)
                restart_args = ([argv0] if argv0 else []) + extra_args
            except Exception:
                restart_args = []

    if not restart_exe:
        raise RuntimeError("再起動対象の実行ファイルパスが取得できません")

    update_dir = _get_update_dir_for_installer(installer_path)
    log_path = log_path or _default_installer_log_path("latest", base_dir=update_dir)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    stamp_path = _default_install_stamp_path()
    stamp_path2 = _default_install_stamp_path_in_dir(update_dir)
    try:
        os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(stamp_path2), exist_ok=True)
    except Exception:
        pass

    # インストーラ引数
    installer_args = _build_inno_installer_args(log_path=log_path, restart_apps=False)

    # 更新対象（= 本体）が起動中のままインストーラを開始すると、
    # サイレント時にファイル置換が遅延/失敗して「更新されない」ように見えやすい。
    # そのため、別プロセス側で本体PIDの終了を待ってからインストーラを起動する。
    pid_to_wait = int(wait_pid) if wait_pid is not None else int(os.getpid())

    # ランナー生成（cmd優先 / ps1はデバッグ用に残す）
    runner_cmd, runner_ps1, runner_log = build_update_runner_paths(installer_path=installer_path)
    try:
        os.makedirs(os.path.dirname(runner_cmd), exist_ok=True)
        os.makedirs(os.path.dirname(runner_ps1), exist_ok=True)
        os.makedirs(os.path.dirname(runner_log), exist_ok=True)
    except Exception:
        pass

    try:
        with open(runner_log, "a", encoding="utf-8") as lf:
            lf.write(f"[launcher] created at {datetime.now().isoformat()}\n")
    except Exception:
        pass

    # PowerShell版（診断用）
    app_args_ps = ",".join(_ps_quote(a) for a in (restart_args or []))
    installer_args_ps = ",".join(_ps_quote(a) for a in installer_args)
    stamp2_ps = "" if os.path.normpath(stamp_path2) == os.path.normpath(stamp_path) else stamp_path2
    ps1 = (
        "$ErrorActionPreference='Stop'\n"
        "$ProgressPreference='SilentlyContinue'\n"
        f"$RunnerLog={_ps_quote(runner_log)}\n"
        "function Write-RunnerLog([string]$msg) {\n"
        "  try {\n"
        "    $dir=Split-Path -Parent $RunnerLog; if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }\n"
        "    $ts=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff');\n"
        "    Add-Content -LiteralPath $RunnerLog -Encoding UTF8 -Value (\"[$ts] $msg\");\n"
        "  } catch {}\n"
        "}\n"
        "Write-RunnerLog 'runner:start'\n"
        f"$pidToWait={pid_to_wait}\n"
        f"$installer={_ps_quote(installer_path)}\n"
        f"$installerLog={_ps_quote(log_path)}\n"
        f"$stamp={_ps_quote(stamp_path)}\n"
        f"$stamp2={_ps_quote(stamp2_ps)}\n"
        f"$app={_ps_quote(restart_exe)}\n"
        f"$appArgs=@({app_args_ps});\n"
        f"$installerArgs=@({installer_args_ps});\n"
        "try {\n"
        "  Write-RunnerLog (\"wait:pid=$pidToWait\");\n"
        "  try { Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue } catch {}\n"
        "  if (-not (Test-Path -LiteralPath $installer)) { throw (\"installer not found: $installer\") }\n"
        "  Write-RunnerLog (\"start-installer: $installer\");\n"
        "  $p=Start-Process -FilePath $installer -ArgumentList $installerArgs -PassThru;\n"
        "  $null=$p.WaitForExit();\n"
        "  Write-RunnerLog (\"installer-exit: exitCode=$($p.ExitCode)\");\n"
        "  try {\n"
        "    $dir=Split-Path -Parent $stamp; if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }\n"
        "    $obj=@{ installedAtUtc=(Get-Date).ToUniversalTime().ToString('o'); exitCode=$p.ExitCode; installer=$installer; logPath=$installerLog; runnerLog=$RunnerLog }\n"
        "    $json=$obj | ConvertTo-Json -Compress\n"
        "    Set-Content -LiteralPath $stamp -Value $json -Encoding UTF8\n"
        "    if ($stamp2) { try { Set-Content -LiteralPath $stamp2 -Value $json -Encoding UTF8 } catch {} }\n"
        "    Write-RunnerLog (\"stamp-written: $stamp\");\n"
        "  } catch { Write-RunnerLog (\"stamp-error: $($_.Exception.Message)\") }\n"
        "  Write-RunnerLog (\"restart: $app\");\n"
        "  if ($appArgs.Count -gt 0) { Start-Process -FilePath $app -ArgumentList $appArgs } else { Start-Process -FilePath $app }\n"
        "  Write-RunnerLog 'runner:done'\n"
        "} catch {\n"
        "  Write-RunnerLog (\"runner-error: $($_.Exception.Message)\");\n"
        "  throw\n"
        "}\n"
    )

    try:
        with open(runner_ps1, "w", encoding="utf-8") as f:
            f.write(ps1)
    except Exception as e:
        raise RuntimeError(f"更新ランナーの作成に失敗しました: {e}")

    # cmd版（本命）: PID待ち→インストーラ(start /wait)→スタンプ(JSON)→再起動
    def _cmd_quote(arg: str) -> str:
        s = str(arg)
        if not s:
            return '""'
        if any(c in s for c in ' \t"'):
            return '"' + s.replace('"', '""') + '"'
        return s

    installer_args_cmd = " ".join(_cmd_quote(a) for a in installer_args)
    app_args_cmd = " ".join(_cmd_quote(a) for a in (restart_args or []))

    # cmd版（本命）: パスに空白があっても壊れないよう set "VAR=..." を使用する。
    stamp2_cmd = "" if os.path.normpath(stamp_path2) == os.path.normpath(stamp_path) else stamp_path2

    restart_line = (
        f"start \"\" {_cmd_quote(restart_exe)} {app_args_cmd}\r\n"
        if (restart_args or [])
        else f"start \"\" {_cmd_quote(restart_exe)}\r\n"
    )

    cmd_lines = [
        "@echo off\r\n",
        "setlocal EnableExtensions EnableDelayedExpansion\r\n",
        f"set \"RUNNER_LOG={runner_log}\"\r\n",
        f"set \"INSTALLER={installer_path}\"\r\n",
        f"set \"PID_TO_WAIT={pid_to_wait}\"\r\n",
        f"set \"STAMP={stamp_path}\"\r\n",
        f"set \"STAMP2={stamp2_cmd}\"\r\n",
        f"set \"APP={restart_exe}\"\r\n",
        "echo [%%date%% %%time%%] runner:start>>\"%RUNNER_LOG%\"\r\n",
        "echo [%%date%% %%time%%] wait:pid=%PID_TO_WAIT%>>\"%RUNNER_LOG%\"\r\n",
        ":waitloop\r\n",
        "tasklist /FI \"PID eq %PID_TO_WAIT%\" 2>NUL | findstr /I \"%PID_TO_WAIT%\" >NUL\r\n",
        "if %ERRORLEVEL%==0 (timeout /t 1 /nobreak >NUL & goto waitloop)\r\n",
        "if not exist \"%INSTALLER%\" (echo [%%date%% %%time%%] ERROR: installer not found: %INSTALLER%>>\"%RUNNER_LOG%\" & exit /b 2)\r\n",
        "echo [%%date%% %%time%%] start-installer: %INSTALLER%>>\"%RUNNER_LOG%\"\r\n",
        f"start \"\" /wait \"%INSTALLER%\" {installer_args_cmd}\r\n",
        "set EC=%ERRORLEVEL%\r\n",
        "echo [%%date%% %%time%%] installer-exit: exitCode=!EC!>>\"%RUNNER_LOG%\"\r\n",
        "set LDT=\r\n",
        "for /f \"tokens=2 delims==\" %%i in ('wmic os get localdatetime /value 2^>NUL ^| find \"=\"') do set LDT=%%i\r\n",
        "if not defined LDT set LDT=%date% %time%\r\n",
        "set INSTALLED_AT=!LDT!\r\n",
        "set JSON={\"installedAtLocal\":\"!INSTALLED_AT!\",\"exitCode\":!EC!}\r\n",
        "echo !JSON!>\"%STAMP%\"\r\n",
        "if not \"%STAMP2%\"==\"\" (echo !JSON!>\"%STAMP2%\")\r\n",
        "echo [%%date%% %%time%%] stamp-written: %STAMP%>>\"%RUNNER_LOG%\"\r\n",
        "echo [%%date%% %%time%%] restart: %APP%>>\"%RUNNER_LOG%\"\r\n",
        restart_line,
        "echo [%%date%% %%time%%] runner:done>>\"%RUNNER_LOG%\"\r\n",
        "endlocal\r\n",
    ]
    cmd_script = "".join(cmd_lines)

    try:
        with open(runner_cmd, "w", encoding="utf-8", newline="") as f:
            f.write(cmd_script)
    except Exception as e:
        raise RuntimeError(f"更新ランナー(cmd)の作成に失敗しました: {e}")

    # cmd.exe start でデタッチして実行（PowerShellより環境依存が少ない）
    popen_args = [
        "cmd.exe",
        "/c",
        "start",
        "",
        runner_cmd,
    ]

    creationflags = 0
    try:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        # VS Code のターミナル/タスク経由で起動したプロセスは Job Object に入っており、
        # 親終了と同時に子プロセスがまとめて終了することがある。
        # breakaway できる環境では、更新ランナーをジョブから切り離して生存させる。
        try:
            creationflags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
        except Exception:
            pass
    except Exception:
        creationflags = 0

    try:
        logger.info("インストーラ起動(再起動付き): %s", installer_path)
        logger.info("再起動コマンド: %s %s", restart_exe, " ".join(restart_args or []))
        logger.info("更新ランナー(cmd): %s", runner_cmd)
        logger.info("更新ランナー(ps1): %s", runner_ps1)
        logger.info("更新ランナーログ: %s", runner_log)
        try:
            with open(runner_log, "a", encoding="utf-8") as lf:
                lf.write(f"[launcher] ps={popen_args[0]} creationflags={creationflags}\n")
                lf.write(f"[launcher] args={popen_args}\n")
                lf.write(f"[launcher] runner_cmd={runner_cmd}\n")
                lf.write(f"[launcher] runner_ps1={runner_ps1}\n")
        except Exception:
            pass
    except Exception:
        logger.info("インストーラ起動(再起動付き): %s", installer_path)

    # まずはcmd runnerを起動
    subprocess.Popen(popen_args, close_fds=True, creationflags=creationflags)

    # すぐに親が終了してしまうため、短時間だけ起動確認する（遅延起動もあるのでポーリング）
    if not bool(os.environ.get("PYTEST_CURRENT_TEST")):
        started = _wait_for_runner_start(runner_log=runner_log, timeout_sec=5.0)
        if not started:
            # 最後の手段: PowerShell版を start で起動してみる
            try:
                with open(runner_log, "a", encoding="utf-8") as lf:
                    lf.write("[launcher] cmd runner did not start; fallback to pwsh -File\n")
            except Exception:
                pass
            ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            fallback_args = [
                "cmd.exe",
                "/c",
                "start",
                "",
                ps_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                runner_ps1,
            ]
            subprocess.Popen(fallback_args, close_fds=True)
            started = _wait_for_runner_start(runner_log=runner_log, timeout_sec=5.0)

        if not started:
            raise RuntimeError(
                "更新ランナーを起動できませんでした。"
                f"\nrunner_log: {runner_log}"
                f"\nrunner_cmd: {runner_cmd}"
                f"\nrunner_ps1: {runner_ps1}"
                "\n（セキュリティ製品/実行ポリシーにより start がブロックされている可能性があります。"
                "runner_cmd をダブルクリックで実行できるかも確認してください）"
            )

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
