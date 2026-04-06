"""
グローバルスレッドレジストリ

アプリケーション全体で実行中のQThreadを追跡し、
終了時に一括停止・待機するための仕組みを提供する。
"""
import logging
import threading
from weakref import WeakSet

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_threads: WeakSet = WeakSet()
_shutdown_guard_lock = threading.Lock()
_guarded_apps: set[int] = set()
_shutdown_in_progress = False


def register_thread(thread) -> None:
    """実行中のQThreadをレジストリに登録する。"""
    with _lock:
        _threads.add(thread)
    try:
        thread.finished.connect(lambda: _try_unregister(thread))
    except Exception:
        pass


def _try_unregister(thread) -> None:
    with _lock:
        _threads.discard(thread)


def unregister_thread(thread) -> None:
    """スレッドをレジストリから明示的に除去する。"""
    with _lock:
        _threads.discard(thread)


def active_threads() -> list:
    """現在登録されている生存スレッドのリストを返す。"""
    with _lock:
        result = []
        for t in list(_threads):
            try:
                if hasattr(t, "isRunning") and t.isRunning():
                    result.append(t)
            except RuntimeError:
                pass
        return result


def stop_all(timeout_ms: int = 3000) -> int:
    """全登録スレッドを停止する。

    各スレッドの ``stop()`` メソッドを呼び出し、*timeout_ms* ミリ秒待機する。
    まだ動いているスレッドには ``terminate()`` を実行する。

    Returns:
        強制終了されたスレッドの数。
    """
    threads = active_threads()
    if not threads:
        return 0

    logger.info("ThreadRegistry: %d 個のスレッドを停止します", len(threads))

    for t in threads:
        try:
            if hasattr(t, "requestInterruption") and callable(getattr(t, "requestInterruption")):
                t.requestInterruption()
        except Exception:
            logger.debug("ThreadRegistry: requestInterruption() 呼び出し失敗", exc_info=True)
        try:
            if hasattr(t, "quit") and callable(getattr(t, "quit")):
                t.quit()
        except Exception:
            logger.debug("ThreadRegistry: quit() 呼び出し失敗", exc_info=True)
        try:
            if hasattr(t, "stop") and callable(getattr(t, "stop")):
                t.stop()
        except Exception:
            logger.debug("ThreadRegistry: stop() 呼び出し失敗", exc_info=True)

    forced = 0
    for t in threads:
        try:
            if hasattr(t, "isRunning") and t.isRunning():
                t.wait(timeout_ms)
        except Exception:
            pass
        try:
            if hasattr(t, "isRunning") and t.isRunning():
                if hasattr(t, "terminate"):
                    t.terminate()
                    try:
                        t.wait(min(timeout_ms, 500))
                    except Exception:
                        pass
                    forced += 1
                    logger.warning("ThreadRegistry: スレッドを強制終了しました: %s", t)
        except Exception:
            pass
        try:
            if not (hasattr(t, "isRunning") and t.isRunning()):
                unregister_thread(t)
        except Exception:
            pass

    if forced:
        logger.warning("ThreadRegistry: %d 個のスレッドを強制終了しました", forced)
    else:
        logger.info("ThreadRegistry: すべてのスレッドが正常に停止しました")

    return forced


def wait_all(timeout_ms: int = 30000) -> bool:
    """全登録スレッドの完了を待つ。

    Returns:
        全スレッドが時間内に停止した場合 True。
    """
    threads = active_threads()
    if not threads:
        return True

    logger.info("ThreadRegistry: %d 個のスレッドの完了を待機します", len(threads))

    all_done = True
    for t in threads:
        try:
            if hasattr(t, "isRunning") and t.isRunning():
                t.wait(timeout_ms)
                if hasattr(t, "isRunning") and t.isRunning():
                    all_done = False
        except Exception:
            all_done = False

    return all_done


def has_active_threads() -> bool:
    """実行中のスレッドがあるか判定する。"""
    return len(active_threads()) > 0


def active_thread_count() -> int:
    """実行中のスレッド数を返す。"""
    return len(active_threads())


def stop_all_for_app_exit(stop_timeout_ms: int = 1500, wait_timeout_ms: int = 2000) -> None:
    """アプリ終了時の最終停止処理を一度だけ実行する。"""
    global _shutdown_in_progress
    with _shutdown_guard_lock:
        if _shutdown_in_progress:
            return
        _shutdown_in_progress = True
    try:
        stop_all(timeout_ms=stop_timeout_ms)
        wait_all(timeout_ms=wait_timeout_ms)
    finally:
        with _shutdown_guard_lock:
            _shutdown_in_progress = False


def install_app_shutdown_guard(app) -> bool:
    """QApplication の aboutToQuit に最終停止処理を接続する。"""
    if app is None:
        return False

    app_id = id(app)
    with _shutdown_guard_lock:
        if app_id in _guarded_apps:
            return False
        _guarded_apps.add(app_id)

    try:
        app.aboutToQuit.connect(lambda: stop_all_for_app_exit())
        return True
    except Exception:
        with _shutdown_guard_lock:
            _guarded_apps.discard(app_id)
        logger.debug("ThreadRegistry: aboutToQuit ガード接続失敗", exc_info=True)
        return False
