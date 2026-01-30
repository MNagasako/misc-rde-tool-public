from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .base import PathLike


class PosixPlatformServices:
    def is_windows(self) -> bool:
        return False

    def open_path(self, path: PathLike) -> bool:
        target = _normalize_path(path)
        if not target:
            return False
        if sys.platform == "darwin":
            return _run(["open", target])
        return _run(["xdg-open", target])

    def reveal_in_file_manager(self, path: PathLike) -> bool:
        target = _normalize_path(path)
        if not target:
            return False
        if sys.platform == "darwin":
            return _run(["open", "-R", target])
        parent = os.path.dirname(target)
        return self.open_path(parent)

    def write_to_parent_console(self, text: str) -> bool:
        if not text:
            return False
        try:
            print(text)
            return True
        except Exception:
            return False

    def show_version_messagebox(self, text: str, title: str = "ARIM RDE Tool") -> None:
        return

    def get_system_proxy_info(self) -> str:
        try:
            http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
            https_proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            if https_proxy or http_proxy:
                return f"{https_proxy or http_proxy}"
            return "プロキシなし（直接接続）"
        except Exception as exc:
            return f"検出失敗: {exc}"

    def is_fiddler_ca_installed(self) -> bool:
        return False

    def get_windows_cert_store_counts(self) -> tuple[int, int] | None:
        return None

    def get_windows_certificates_pem(self) -> list[str]:
        return []

    def get_windows_registry_proxy(self) -> dict[str, object]:
        return {}

    def get_windows_process_list(self, process_name: str) -> list[str]:
        return []

    def get_netsh_winhttp_proxy_output(self) -> str | None:
        return None

    def launch_update_runner_cmd(self, runner_cmd: str, runner_log: str) -> tuple[list[str], int]:
        raise RuntimeError("Windows update runner is not supported on this platform")

    def launch_update_runner_ps(self, runner_ps1: str, runner_log: str) -> tuple[list[str], int]:
        raise RuntimeError("Windows update runner is not supported on this platform")

    def apply_native_titlebar_theme(self, widget, mode, theme_manager) -> None:
        return


def _normalize_path(path: PathLike) -> str:
    try:
        if isinstance(path, Path):
            return str(path)
        return str(path)
    except Exception:
        return ""


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.Popen(cmd)
        return True
    except Exception:
        return False
