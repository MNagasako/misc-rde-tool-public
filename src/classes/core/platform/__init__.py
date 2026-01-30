"""Platform boundary services for OS-specific behavior."""

from __future__ import annotations

from .services import (
    get_platform_services,
    is_windows,
    get_system_proxy_info,
    get_windows_certificates_pem,
    get_windows_cert_store_counts,
    get_windows_process_list,
    get_windows_registry_proxy,
    get_netsh_winhttp_proxy_output,
    is_fiddler_ca_installed,
    launch_update_runner_cmd,
    launch_update_runner_ps,
    apply_native_titlebar_theme,
    open_path,
    reveal_in_file_manager,
    show_version_messagebox,
    write_to_parent_console,
)

__all__ = [
    "get_platform_services",
    "is_windows",
    "get_system_proxy_info",
    "get_windows_certificates_pem",
    "get_windows_cert_store_counts",
    "get_windows_process_list",
    "get_windows_registry_proxy",
    "get_netsh_winhttp_proxy_output",
    "is_fiddler_ca_installed",
    "launch_update_runner_cmd",
    "launch_update_runner_ps",
    "apply_native_titlebar_theme",
    "open_path",
    "reveal_in_file_manager",
    "show_version_messagebox",
    "write_to_parent_console",
]
