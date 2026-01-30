from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .base import PathLike


class WindowsPlatformServices:
    def is_windows(self) -> bool:
        return True

    def open_path(self, path: PathLike) -> bool:
        try:
            os.startfile(str(path))
            return True
        except Exception:
            return False

    def reveal_in_file_manager(self, path: PathLike) -> bool:
        try:
            target = os.path.normpath(str(path))
            subprocess.Popen(["explorer", "/select,", target], close_fds=True)
            return True
        except Exception:
            return False

    def write_to_parent_console(self, text: str) -> bool:
        if not text:
            return False

        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            try:
                print(text)
                return True
            except Exception:
                return False

        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            ATTACH_PARENT_PROCESS = -1
            ERROR_ACCESS_DENIED = 5

            attached = bool(kernel32.AttachConsole(ATTACH_PARENT_PROCESS))
            if not attached:
                err = ctypes.get_last_error()
                if err == ERROR_ACCESS_DENIED:
                    attached = True
                else:
                    attached = bool(kernel32.AllocConsole())

            if not attached:
                return False

            GENERIC_WRITE = 0x40000000
            FILE_SHARE_READ = 0x00000001
            FILE_SHARE_WRITE = 0x00000002
            OPEN_EXISTING = 3
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

            handle = kernel32.CreateFileW(
                "CONOUT$",
                GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )

            if not handle or handle == INVALID_HANDLE_VALUE:
                STD_OUTPUT_HANDLE = -11
                handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
                if not handle or handle == INVALID_HANDLE_VALUE:
                    return False

            text_to_write = f"{text}\r\n"
            written_chars = ctypes.c_ulong(0)

            ok = kernel32.WriteConsoleW(
                handle,
                ctypes.c_wchar_p(text_to_write),
                len(text_to_write),
                ctypes.byref(written_chars),
                None,
            )

            if not ok:
                data = text_to_write.encode("utf-8", errors="replace")
                written_bytes = ctypes.c_ulong(0)
                ok = kernel32.WriteFile(handle, data, len(data), ctypes.byref(written_bytes), None)

            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass

            return bool(ok)
        except Exception:
            return False

    def show_version_messagebox(self, text: str, title: str = "ARIM RDE Tool") -> None:
        if not text:
            return
        if sys.platform != "win32":
            return
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0)
        except Exception:
            pass

    def get_system_proxy_info(self) -> str:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            proxy_enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
            if proxy_enable:
                proxy_server = winreg.QueryValueEx(key, "ProxyServer")[0]
                winreg.CloseKey(key)
                return f"{proxy_server}"
            winreg.CloseKey(key)
            return "プロキシなし（直接接続）"
        except Exception:
            return "不明（レジストリアクセスエラー）"

    def is_fiddler_ca_installed(self) -> bool:
        try:
            result = subprocess.run(
                ["certutil", "-store", "Root"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "FiddlerRoot" in result.stdout or "Fiddler" in result.stdout
        except Exception:
            return False

    def get_windows_cert_store_counts(self) -> tuple[int, int] | None:
        try:
            import wincertstore

            ca_store = wincertstore.CertSystemStore("CA")
            root_store = wincertstore.CertSystemStore("ROOT")

            ca_count = len(list(ca_store.itercerts()))
            root_count = len(list(root_store.itercerts()))
            return ca_count, root_count
        except Exception:
            return None

    def get_windows_certificates_pem(self) -> list[str]:
        certificates: list[str] = []
        try:
            import ssl
            import wincertstore

            stores = ["ROOT", "CA"]
            for store_name in stores:
                store = wincertstore.CertSystemStore(store_name)
                for cert_der in store.itercerts(usage=wincertstore.SERVER_AUTH):
                    try:
                        cert_pem = ssl.DER_cert_to_PEM_cert(cert_der)
                        certificates.append(cert_pem)
                    except (ssl.SSLError, ValueError):
                        continue
        except Exception:
            return []
        return certificates

    def get_windows_registry_proxy(self) -> dict[str, object]:
        registry_info: dict[str, object] = {}
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            proxy_enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
            proxy_server = winreg.QueryValueEx(key, "ProxyServer")[0] if proxy_enable else None
            auto_config_url = None
            proxy_override = None
            try:
                auto_config_url = winreg.QueryValueEx(key, "AutoConfigURL")[0]
            except Exception:
                auto_config_url = None
            try:
                proxy_override = winreg.QueryValueEx(key, "ProxyOverride")[0]
            except Exception:
                proxy_override = None
            winreg.CloseKey(key)
            registry_info["ProxyEnable"] = proxy_enable
            registry_info["ProxyServer"] = proxy_server
            registry_info["AutoConfigURL"] = auto_config_url
            registry_info["ProxyOverride"] = proxy_override
        except Exception as exc:
            registry_info["error"] = str(exc)
        return registry_info

    def get_windows_process_list(self, process_name: str) -> list[str]:
        if not process_name:
            return []
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return [line.strip() for line in (result.stdout or "").split("\n") if process_name in line]
        except Exception:
            return []

    def get_netsh_winhttp_proxy_output(self) -> str | None:
        try:
            result = subprocess.run(
                ["netsh", "winhttp", "show", "proxy"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout or ""
        except Exception:
            return None

    def launch_update_runner_cmd(self, runner_cmd: str, runner_log: str) -> tuple[list[str], int]:
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
            try:
                creationflags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
            except Exception:
                pass
        except Exception:
            creationflags = 0

        subprocess.Popen(popen_args, close_fds=True, creationflags=creationflags)
        return popen_args, creationflags

    def launch_update_runner_ps(self, runner_ps1: str, runner_log: str) -> tuple[list[str], int]:
        ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        popen_args = [
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
        subprocess.Popen(popen_args, close_fds=True)
        return popen_args, 0

    def apply_native_titlebar_theme(self, widget, mode, theme_manager) -> None:
        try:
            import ctypes
        except ImportError:
            return

        hwnd = _get_hwnd(widget)
        if not hwnd:
            return

        dark_enabled = ctypes.c_int(1 if mode.name == "DARK" else 0)
        size = ctypes.sizeof(dark_enabled)

        try:
            dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
        except AttributeError:
            return

        immersive_attrs = (20, 19)
        for attr in immersive_attrs:
            result = dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark_enabled), size)
            if result == 0:
                break

        _apply_caption_palette(dwmapi, hwnd, mode, theme_manager)


def _get_hwnd(widget) -> int:
    try:
        from PySide6.QtCore import Qt
    except Exception:
        return 0

    try:
        if not widget.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            return 0
    except Exception:
        return 0

    try:
        win_id = widget.winId()
    except Exception:
        return 0
    try:
        return int(win_id)
    except Exception:
        return 0


def _apply_caption_palette(dwmapi, hwnd: int, mode, theme_manager) -> None:
    try:
        import ctypes
    except Exception:
        return

    from classes.theme import ThemeKey

    if mode.name == "DARK":
        caption_color = _colorref_from_theme(theme_manager.get_color(ThemeKey.WINDOW_BACKGROUND))
        text_color = _colorref_from_theme(theme_manager.get_color(ThemeKey.TEXT_PRIMARY))
        border_color = _colorref_from_theme(theme_manager.get_color(ThemeKey.BORDER_DARK))
    else:
        caption_color = None
        text_color = None
        border_color = None

    _set_dwm_color(dwmapi, hwnd, 35, caption_color)
    _set_dwm_color(dwmapi, hwnd, 36, text_color)
    _set_dwm_color(dwmapi, hwnd, 34, border_color)


def _colorref_from_theme(color) -> int:
    try:
        rgb = color
        if hasattr(color, "rgb"):
            rgb = color.rgb()
        value = int(rgb) & 0x00FFFFFF
        r = value & 0xFF
        g = (value >> 8) & 0xFF
        b = (value >> 16) & 0xFF
        return (b << 16) | (g << 8) | r
    except Exception:
        return 0


def _set_dwm_color(dwmapi, hwnd: int, attr: int, colorref: int | None) -> None:
    try:
        import ctypes
    except Exception:
        return

    COLOR_UNSET = 0xFFFFFFFF
    value = COLOR_UNSET if colorref is None else colorref
    color_value = ctypes.c_int(value)
    try:
        dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(color_value), ctypes.sizeof(color_value))
    except Exception:
        return
