from __future__ import annotations

import atexit
import ctypes
import json
import logging
import msvcrt
import os
import sys
import threading
from datetime import datetime
from typing import Callable, Optional

from classes.core.platform import is_windows
from config.common import DEBUG_LOG_ENABLED, DEBUG_LOG_PATH, LOCKS_DIR, ensure_directory_exists, get_dynamic_file_path


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if is_windows():
        try:
            import subprocess

            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = result.stdout or ""
            return str(pid) in out
        except Exception:
            # Fail closed to avoid deleting a valid lock on Windows.
            return True
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    return True
_DEBUG_TRACE_LOCK = threading.Lock()
_FILE_LOCK_HANDLE = None
_MUTEX_HANDLE = None


def _write_debug_trace(event: str, **payload: object) -> None:
    if not DEBUG_LOG_ENABLED:
        return
    try:
        ensure_directory_exists(os.path.dirname(DEBUG_LOG_PATH))
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        record = {"event": event, **payload}
        argstr = json.dumps(record, ensure_ascii=False, default=str)
        logline = f"{now}\tSingleInstanceGuard\t{argstr}\n"
        with _DEBUG_TRACE_LOCK:
            with open(DEBUG_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(logline)
    except Exception:
        pass


def _create_single_instance_mutex(name: str) -> tuple[bool, int]:
    """
    Create or open a Windows named mutex. Returns (created, handle).
    created=False indicates the mutex already existed.
    handle=0 indicates failure to create/open.
    """
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        create_mutex.restype = ctypes.c_void_p
        handle = create_mutex(None, False, name)
        if not handle:
            return False, 0
        last_error = ctypes.get_last_error()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            return False, int(handle)
        return True, int(handle)
    except Exception:
        return False, 0


def _show_block_message(message_box: Optional[object], title: str, message: str) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        if message_box is not None:
            try:
                message_box.information(None, title, message)
            except Exception:
                pass
        return

    try:
        from qt_compat.widgets import QApplication  # type: ignore

        app = QApplication.instance()
    except Exception:
        app = None

    if app is not None and message_box is not None:
        try:
            _write_debug_trace("dialog_attempt", source="qmessagebox", title=title)
            message_box.information(None, title, message)
            _write_debug_trace("dialog_shown", source="qmessagebox", title=title)
            return
        except Exception as e:
            _write_debug_trace("dialog_failed", source="qmessagebox", error=str(e))
    else:
        _write_debug_trace("dialog_skipped", source="qmessagebox", reason="no_app")

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        _write_debug_trace("dialog_attempt", source="win32", title=title)
        flags = 0x00000040 | 0x00001000 | 0x00040000 | 0x00000010
        user32.MessageBoxW(None, message, title, flags)
        _write_debug_trace("dialog_shown", source="win32", title=title)
    except Exception:
        _write_debug_trace("dialog_failed", source="win32")


def _count_running_processes(exe_name: str) -> int:
    try:
        import subprocess

        creationflags = 0
        startupinfo = None
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            if hasattr(subprocess, "STARTF_USESHOWWINDOW"):
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        out = result.stdout or ""
        lines = [line for line in out.splitlines() if line.strip()]
        if len(lines) <= 1:
            return 0
        # First line is header in CSV output.
        return max(0, len(lines) - 1)
    except Exception:
        return 0


def _resolve_exe_name() -> str:
    exe_name = os.path.basename(sys.executable or "").strip()
    if exe_name:
        return exe_name
    argv0 = os.path.basename((sys.argv[0] or "").strip())
    return argv0


class SingleInstanceResult:
    def __init__(self, allowed: bool, created_guard: bool) -> None:
        self.allowed = bool(allowed)
        self.created_guard = bool(created_guard)


def ensure_single_instance_guard(
    app,
    *,
    allow_multi_instance: bool,
    prompt_on_conflict: bool,
    shared_key: str = "ARIM_RDE_TOOL_SINGLE_INSTANCE",
    lock_path: Optional[str] = None,
    register_atexit: bool = True,
    logger: Optional[logging.Logger] = None,
    shared_memory_factory: Optional[Callable[[str], object]] = None,
    message_box: Optional[object] = None,
) -> SingleInstanceResult:
    if not is_windows():
        _write_debug_trace("skip", reason="not_windows")
        return SingleInstanceResult(True, False)

    if allow_multi_instance:
        if logger is not None:
            logger.info("[SingleInstance] allow_multi_instance_windows is enabled; guard skipped")
        _write_debug_trace("skip", reason="allow_multi_instance")
        return SingleInstanceResult(True, False)

    if lock_path is None:
        lock_path = os.path.join(LOCKS_DIR, "single_instance.lock")

    if logger is not None:
        logger.info("[SingleInstance] guard start: lock_path=%s", lock_path)
    _write_debug_trace(
        "start",
        lock_path=lock_path,
        pid=os.getpid(),
        allow_multi_instance=bool(allow_multi_instance),
        prompt_on_conflict=bool(prompt_on_conflict),
        shared_key=shared_key,
    )

    if shared_memory_factory is None or message_box is None:
        try:
            from qt_compat.core import QSharedMemory  # type: ignore
            from qt_compat.widgets import QMessageBox  # type: ignore

            shared_memory_factory = shared_memory_factory or QSharedMemory
            message_box = message_box or QMessageBox
            _write_debug_trace("guard_checkpoint", step="message_box_ready")
        except Exception as e:
            class _NullSharedMemory:
                def __init__(self, _key):
                    pass

                def create(self, _size):
                    return False

                def attach(self):
                    return False

                def detach(self):
                    return False

            if shared_memory_factory is None:
                shared_memory_factory = _NullSharedMemory
            _write_debug_trace("guard_checkpoint", step="message_box_failed", error=str(e))

    if not os.environ.get("PYTEST_CURRENT_TEST"):
        exe_name = _resolve_exe_name()
        if exe_name:
            try:
                _write_debug_trace("guard_checkpoint", step="process_count_start", exe_name=exe_name)
                count = _count_running_processes(exe_name)
                _write_debug_trace("process_count", exe_name=exe_name, count=count)
                if logger is not None:
                    logger.info("[SingleInstance] process count: %s=%s", exe_name, count)
                if count >= 2:
                    if prompt_on_conflict:
                        try:
                            result = message_box.question(
                                None,
                                "起動済み",
                                "既に起動されています。二重起動しますか？",
                                message_box.StandardButton.Yes | message_box.StandardButton.No,
                                message_box.StandardButton.No,
                            )
                            if result == message_box.StandardButton.Yes:
                                _write_debug_trace("bypass", source="process", exe_name=exe_name)
                                return SingleInstanceResult(True, False)
                        except Exception:
                            pass

                    _show_block_message(
                        message_box,
                        "多重起動不可",
                        "多重起動はできません。\n"
                        "起動済みのアプリを終了してから再度お試しください。",
                    )
                    _write_debug_trace("blocked", source="process", exe_name=exe_name)
                    return SingleInstanceResult(False, False)
            except Exception as e:
                _write_debug_trace("process_count_error", exe_name=exe_name, error=str(e))
        else:
            _write_debug_trace(
                "process_count_skipped",
                reason="empty_exe_name",
                sys_executable=str(sys.executable or ""),
                argv0=str(sys.argv[0] or ""),
            )

    try:
        ensure_directory_exists(os.path.dirname(lock_path))
        if logger is not None:
            logger.info("[SingleInstance] lock dir ready: %s", os.path.dirname(lock_path))
        _write_debug_trace("lock_dir_ready", lock_dir=os.path.dirname(lock_path))
    except Exception as e:
        if logger is not None:
            logger.info("[SingleInstance] lock dir create failed: %s", e)
        _write_debug_trace("lock_dir_error", lock_dir=os.path.dirname(lock_path), error=str(e))

    try:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            _write_debug_trace("mutex_skipped", reason="pytest")
        else:
            mutex_name = f"Local\\{shared_key}"
            if logger is not None:
                logger.info("[SingleInstance] mutex attempt: %s", mutex_name)
            _write_debug_trace("mutex_attempt", mutex_name=mutex_name)
            created, mutex_handle = _create_single_instance_mutex(mutex_name)
            if not mutex_handle:
                if logger is not None:
                    logger.info("[SingleInstance] mutex create failed")
                _write_debug_trace("mutex_create_failed", mutex_name=mutex_name)
            elif not created:
                if logger is not None:
                    logger.info("[SingleInstance] mutex already exists")
                _write_debug_trace("mutex_exists", mutex_name=mutex_name)
                if prompt_on_conflict:
                    try:
                        result = message_box.question(
                            None,
                            "起動済み",
                            "既に起動されています。二重起動しますか？",
                            message_box.StandardButton.Yes | message_box.StandardButton.No,
                            message_box.StandardButton.No,
                        )
                        if result == message_box.StandardButton.Yes:
                            _write_debug_trace("bypass", source="mutex", mutex_name=mutex_name)
                            return SingleInstanceResult(True, False)
                    except Exception:
                        pass

                _show_block_message(
                    message_box,
                    "多重起動不可",
                    "多重起動はできません。\n"
                    "起動済みのアプリを終了してから再度お試しください。",
                )
                _write_debug_trace("blocked", source="mutex", mutex_name=mutex_name)
                return SingleInstanceResult(False, False)
            else:
                if logger is not None:
                    logger.info("[SingleInstance] mutex created")
                _write_debug_trace("mutex_created", mutex_name=mutex_name)
                global _MUTEX_HANDLE
                _MUTEX_HANDLE = mutex_handle
                try:
                    app._single_instance_mutex_handle = mutex_handle
                except Exception:
                    pass
                if register_atexit and mutex_handle:
                    try:
                        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                        close_handle = kernel32.CloseHandle
                        close_handle.argtypes = [ctypes.c_void_p]
                        close_handle.restype = ctypes.c_bool

                        def _release_mutex() -> None:
                            try:
                                close_handle(ctypes.c_void_p(mutex_handle))
                            except Exception:
                                pass

                        atexit.register(_release_mutex)
                    except Exception:
                        pass
    except Exception as e:
        if logger is not None:
            logger.info("[SingleInstance] mutex guard error: %s", e)
        _write_debug_trace("mutex_error", error=str(e))

    def _acquire_lock(path: str) -> bool:
        try:
            ensure_directory_exists(os.path.dirname(path))
        except Exception:
            pass

        try:
            lock_file = open(path, "a+", encoding="utf-8")
        except Exception as e:
            _write_debug_trace("lock_open_error", lock_path=path, error=str(e))
            return False

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except Exception as e:
            try:
                lock_file.seek(0)
                raw = (lock_file.read() or "").strip()
            except Exception:
                raw = ""
            try:
                pid = int(raw) if raw else 0
            except Exception:
                pid = 0
            if logger is not None:
                logger.info("[SingleInstance] lock busy (pid=%s)", pid or "unknown")
            _write_debug_trace("lock_busy", lock_path=path, pid=pid or None, error=str(e))
            try:
                lock_file.close()
            except Exception:
                pass
            return False

        try:
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(f"{os.getpid()}")
            lock_file.flush()
        except Exception:
            pass

        global _FILE_LOCK_HANDLE
        _FILE_LOCK_HANDLE = lock_file
        try:
            app._single_instance_lock_handle = lock_file
        except Exception:
            pass

        if register_atexit:
            def _release_file_lock() -> None:
                try:
                    lock_file.close()
                except Exception:
                    pass
                try:
                    os.remove(path)
                except Exception:
                    pass

            atexit.register(_release_file_lock)

        if logger is not None:
            logger.info("[SingleInstance] lock acquired")
        _write_debug_trace("lock_acquired", lock_path=path)
        return True

    def _log(msg: str) -> None:
        if logger is not None:
            logger.debug(msg)

    lock_ok = _acquire_lock(lock_path)
    if not lock_ok:
        if logger is not None:
            logger.info("[SingleInstance] lock acquisition failed")
        _write_debug_trace("lock_failed", lock_path=lock_path)
        if prompt_on_conflict:
            try:
                result = message_box.question(
                    None,
                    "起動済み",
                    "既に起動されています。二重起動しますか？",
                    message_box.StandardButton.Yes | message_box.StandardButton.No,
                    message_box.StandardButton.No,
                )
                if result == message_box.StandardButton.Yes:
                    _log("single instance lock bypassed by user")
                    _write_debug_trace("bypass", lock_path=lock_path)
                    return SingleInstanceResult(True, False)
            except Exception:
                pass

        _show_block_message(
            message_box,
            "多重起動不可",
            "多重起動はできません。\n"
            "起動済みのアプリを終了してから再度お試しください。",
        )
        _write_debug_trace("blocked", lock_path=lock_path)
        return SingleInstanceResult(False, False)

    def _release_lock() -> None:
        try:
            handle = getattr(app, "_single_instance_lock_handle", None)
            if handle is not None:
                handle.close()
        except Exception:
            pass
        try:
            global _FILE_LOCK_HANDLE
            if _FILE_LOCK_HANDLE is not None:
                _FILE_LOCK_HANDLE.close()
                _FILE_LOCK_HANDLE = None
        except Exception:
            pass
        try:
            if lock_path:
                os.remove(lock_path)
        except Exception:
            pass

    try:
        app._single_instance_lock_path = lock_path
    except Exception:
        pass
    if register_atexit:
        atexit.register(_release_lock)

    shared = shared_memory_factory(shared_key)

    def _try_create() -> bool:
        try:
            if shared.create(1):
                return True
        except Exception:
            return False
        try:
            if shared.attach():
                try:
                    shared.detach()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            return bool(shared.create(1))
        except Exception:
            return False

    if _try_create():
        if logger is not None:
            logger.info("[SingleInstance] shared memory created")
        _write_debug_trace("shared_memory_created", shared_key=shared_key)
        try:
            app._single_instance_guard = shared
        except Exception:
            pass
        return SingleInstanceResult(True, True)

    if logger is not None:
        logger.info("[SingleInstance] shared memory create failed; proceeding without shared memory")
    _write_debug_trace("shared_memory_failed", shared_key=shared_key)
    return SingleInstanceResult(True, True)
