from __future__ import annotations

from pathlib import Path
from typing import Protocol, Union

PathLike = Union[str, Path]


class PlatformServices(Protocol):
    def is_windows(self) -> bool:
        """Return True when running on Windows."""

    def open_path(self, path: PathLike) -> bool:
        """Open a file or folder with the OS default handler."""

    def reveal_in_file_manager(self, path: PathLike) -> bool:
        """Reveal a file or folder in the OS file manager."""

    def write_to_parent_console(self, text: str) -> bool:
        """Write text to a parent console, if supported."""

    def show_version_messagebox(self, text: str, title: str = "ARIM RDE Tool") -> None:
        """Show a version dialog for windowed builds, if supported."""

    def get_system_proxy_info(self) -> str:
        """Return a human-readable system proxy description."""

    def is_fiddler_ca_installed(self) -> bool:
        """Return True if the Fiddler root CA is installed."""

    def get_windows_cert_store_counts(self) -> tuple[int, int] | None:
        """Return (CA_count, ROOT_count) when available, else None."""

    def get_windows_certificates_pem(self) -> list[str]:
        """Return PEM certificates from Windows trust stores when available."""

    def get_windows_registry_proxy(self) -> dict[str, object]:
        """Return Windows registry proxy settings when available."""

    def get_windows_process_list(self, process_name: str) -> list[str]:
        """Return matching Windows process list lines for the given image name."""

    def get_netsh_winhttp_proxy_output(self) -> str | None:
        """Return raw output from netsh winhttp show proxy when available."""

    def launch_update_runner_cmd(self, runner_cmd: str, runner_log: str) -> tuple[list[str], int]:
        """Launch cmd-based update runner and return (args, creationflags)."""

    def launch_update_runner_ps(self, runner_ps1: str, runner_log: str) -> tuple[list[str], int]:
        """Launch PowerShell-based update runner and return (args, creationflags)."""

    def apply_native_titlebar_theme(self, widget, mode, theme_manager) -> None:
        """Apply native titlebar theming when supported."""
