from __future__ import annotations

import sys
from pathlib import Path

from .base import PathLike, PlatformServices

_services: PlatformServices | None = None


def _load_services() -> PlatformServices:
    if sys.platform.startswith("win"):
        from .windows import WindowsPlatformServices

        return WindowsPlatformServices()
    from .posix import PosixPlatformServices

    return PosixPlatformServices()


def get_platform_services() -> PlatformServices:
    global _services
    if _services is None:
        _services = _load_services()
    return _services


def is_windows() -> bool:
    return get_platform_services().is_windows()


def open_path(path: PathLike) -> bool:
    return get_platform_services().open_path(path)


def reveal_in_file_manager(path: PathLike) -> bool:
    return get_platform_services().reveal_in_file_manager(path)


def write_to_parent_console(text: str) -> bool:
    return get_platform_services().write_to_parent_console(text)


def show_version_messagebox(text: str, title: str = "ARIM RDE Tool") -> None:
    get_platform_services().show_version_messagebox(text, title=title)


def get_system_proxy_info() -> str:
    return get_platform_services().get_system_proxy_info()


def is_fiddler_ca_installed() -> bool:
    return get_platform_services().is_fiddler_ca_installed()


def get_windows_cert_store_counts() -> tuple[int, int] | None:
    return get_platform_services().get_windows_cert_store_counts()


def get_windows_certificates_pem() -> list[str]:
    return get_platform_services().get_windows_certificates_pem()


def get_windows_registry_proxy() -> dict[str, object]:
    return get_platform_services().get_windows_registry_proxy()


def get_windows_process_list(process_name: str) -> list[str]:
    return get_platform_services().get_windows_process_list(process_name)


def get_netsh_winhttp_proxy_output() -> str | None:
    return get_platform_services().get_netsh_winhttp_proxy_output()


def launch_update_runner_cmd(runner_cmd: str, runner_log: str) -> tuple[list[str], int]:
    return get_platform_services().launch_update_runner_cmd(runner_cmd, runner_log)


def launch_update_runner_ps(runner_ps1: str, runner_log: str) -> tuple[list[str], int]:
    return get_platform_services().launch_update_runner_ps(runner_ps1, runner_log)


def apply_native_titlebar_theme(widget, mode, theme_manager) -> None:
    return get_platform_services().apply_native_titlebar_theme(widget, mode, theme_manager)
