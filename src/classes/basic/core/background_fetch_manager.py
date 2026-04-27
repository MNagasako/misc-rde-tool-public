"""バックグラウンド取得マネージャー

個別データ（サンプル / データセット個別 / dataEntry / invoice / invoiceSchema）を
バックグラウンドで非同期取得する。UIスレッドをブロックせず、任意のタイミングで中止できる。

v2.5.46: Basic Info 個別データ取得のバックグラウンド実行経路として導入
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from qt_compat.core import QObject, Signal

logger = logging.getLogger(__name__)


class BackgroundFetchManager(QObject):
    """個別データのバックグラウンド取得を管理するシングルトン風マネージャー。

    Signals:
        stage_started(str)  -- 段階名
        stage_progress(str, int, int, str)  -- (段階名, current, total, message)
        stage_completed(str, bool, str)  -- (段階名, 成功, メッセージ)
        all_completed(bool, str)  -- (成功, サマリ)
        fetch_cancelled()  -- キャンセルされた
    """

    stage_started = Signal(str)
    stage_progress = Signal(str, int, int, str)
    stage_completed = Signal(str, bool, str)
    all_completed = Signal(bool, str)
    fetch_cancelled = Signal()

    _instance: Optional["BackgroundFetchManager"] = None

    @classmethod
    def instance(cls) -> "BackgroundFetchManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self._running = False
        self._lock = threading.Lock()
        # 現在実行中の段階名
        self._current_stage: str = ""
        self._stages_results: list[dict[str, Any]] = []

    # ---- public API ----

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_stage(self) -> str:
        return self._current_stage

    def start(
        self,
        bearer_token: str,
        *,
        force_download: bool = False,
        parallel_workers: int = 10,
        on_self: bool = False,
        search_words: Any = None,
        search_words_batch: Any = None,
        stages_filter: list[str] | None = None,
    ) -> bool:
        """バックグラウンド取得を開始する。既に実行中の場合は False を返す。

        Args:
            stages_filter: 実行する段階名のリスト。None の場合は全段階を実行。
                例: ["サンプル情報"] とすると、サンプル情報のみ取得。
        """
        with self._lock:
            if self._running:
                logger.warning("バックグラウンド取得は既に実行中です")
                return False
            self._running = True
            self._cancelled = False
            self._stages_results.clear()

        self._thread = threading.Thread(
            target=self._run,
            kwargs={
                "bearer_token": bearer_token,
                "force_download": force_download,
                "parallel_workers": parallel_workers,
                "on_self": on_self,
                "search_words": search_words,
                "search_words_batch": search_words_batch,
                "stages_filter": stages_filter,
            },
            daemon=True,
        )
        self._thread.start()
        return True

    def cancel(self) -> None:
        """取得を中止する。実行中でなければ何もしない。"""
        self._cancelled = True
        logger.info("バックグラウンド取得: キャンセル要求")

    # ---- internal ----

    def _is_cancelled(self) -> bool:
        return self._cancelled

    def _progress_callback_for(self, stage_name: str) -> Callable[..., bool]:
        """段階ごとのプログレスコールバックを生成する。"""

        def _cb(current: int, total: int, message: str = "") -> bool:
            if self._cancelled:
                return False
            try:
                self.stage_progress.emit(stage_name, int(current), int(total), str(message))
            except Exception:
                pass
            return True

        return _cb

    def _run(
        self,
        bearer_token: str,
        force_download: bool,
        parallel_workers: int,
        on_self: bool,
        search_words: Any,
        search_words_batch: Any,
        stages_filter: list[str] | None = None,
    ) -> None:
        """ワーカースレッド本体。"""
        import os
        from classes.basic.core.basic_info_logic import (
            fetch_all_data_entrys_info,
            fetch_all_dataset_info,
            fetch_all_invoices_info,
            fetch_invoice_schemas,
            fetch_sample_info_only,
            fetch_sample_info_only_direct,
            fetch_sample_info_stage,
            fetch_sample_info_stage_direct,
        )
        from config.common import get_dynamic_file_path

        OUTPUT_DIR = get_dynamic_file_path("output")
        output_rde_data = os.path.join(OUTPUT_DIR, "rde", "data")

        t_start = time.perf_counter()
        success_all = True
        summary_parts: list[str] = []

        # ---- 段階定義（依存関係順） ----
        # dataset は一覧取得を含むためまず先にやる
        # dataEntry / invoice は dataset.json に依存
        # invoiceSchema は template.json に依存（Phase1 で取得済み前提）
        stages: list[tuple[str, Callable[[], str | None]]] = []

        # 1) サンプル情報（旧ルート）
        def _fetch_samples_legacy() -> str | None:
            cb = self._progress_callback_for("サンプル情報（旧ルート）")
            if force_download:
                return fetch_sample_info_only(
                    bearer_token,
                    output_dir=output_rde_data,
                    progress_callback=cb,
                    max_workers=parallel_workers,
                )
            return fetch_sample_info_stage(
                bearer_token,
                progress_callback=cb,
                max_workers=parallel_workers,
            )

        stages.append(("サンプル情報（旧ルート）", _fetch_samples_legacy))

        # 2) サンプル情報（新ルート）— 明示的に stages_filter に含まれた場合のみ実行
        # 基本情報取得(ALL/検索)では実行しない。ボタン「サンプル情報取得(選択)」から直接呼ぶ際のみ使用。
        if stages_filter is not None and "サンプル情報（新ルート）" in stages_filter:
            def _fetch_samples_direct() -> str | None:
                cb = self._progress_callback_for("サンプル情報（新ルート）")
                if force_download:
                    return fetch_sample_info_only_direct(
                        bearer_token,
                        output_dir=output_rde_data,
                        progress_callback=cb,
                        max_workers=parallel_workers,
                    )
                return fetch_sample_info_stage_direct(
                    bearer_token,
                    progress_callback=cb,
                    max_workers=parallel_workers,
                )

            stages.append(("サンプル情報（新ルート）", _fetch_samples_direct))

        # 3) データセット情報（一覧 + 個別 — dataEntry/invoiceが依存）
        def _fetch_datasets() -> str | None:
            return fetch_all_dataset_info(
                bearer_token,
                output_dir=output_rde_data,
                onlySelf=on_self,
                searchWords=search_words,
                searchWordsBatch=search_words_batch,
                progress_callback=self._progress_callback_for("データセット情報"),
                max_workers=parallel_workers,
            )

        stages.append(("データセット情報", _fetch_datasets))

        # 4) データエントリ情報（dataset.jsonに依存）
        def _fetch_data_entries() -> str | None:
            return fetch_all_data_entrys_info(
                bearer_token,
                progress_callback=self._progress_callback_for("データエントリ情報"),
                max_workers=parallel_workers,
            )

        stages.append(("データエントリ情報", _fetch_data_entries))

        # 5) インボイス情報（dataset.jsonに依存）
        def _fetch_invoices() -> str | None:
            return fetch_all_invoices_info(
                bearer_token,
                progress_callback=self._progress_callback_for("インボイス情報"),
                max_workers=parallel_workers,
            )

        stages.append(("インボイス情報", _fetch_invoices))

        # 6) invoiceSchema情報（template.jsonに依存 — Phase1で取得済み）
        def _fetch_invoice_schemas() -> str | None:
            return fetch_invoice_schemas(
                bearer_token,
                output_rde_data,
                progress_callback=self._progress_callback_for("invoiceSchema情報"),
                max_workers=parallel_workers,
            )

        stages.append(("invoiceSchema情報", _fetch_invoice_schemas))

        # フィルタ適用
        if stages_filter is not None:
            filter_set = set(stages_filter)
            stages = [(name, func) for name, func in stages if name in filter_set]
            if not stages:
                logger.warning("stages_filter に一致する段階がありません: %s", stages_filter)
                with self._lock:
                    self._running = False
                try:
                    self.all_completed.emit(True, "対象段階なし")
                except Exception:
                    pass
                return

        # ---- 段階の順次実行 ----
        for stage_name, stage_func in stages:
            if self._cancelled:
                break

            self._current_stage = stage_name
            try:
                self.stage_started.emit(stage_name)
            except Exception:
                pass

            try:
                result = stage_func()
                cancelled = result == "キャンセルされました"
                if cancelled:
                    self._cancelled = True
                    try:
                        self.stage_completed.emit(stage_name, False, "キャンセル")
                    except Exception:
                        pass
                    break
                msg = result if isinstance(result, str) else "完了"
                try:
                    self.stage_completed.emit(stage_name, True, msg)
                except Exception:
                    pass
                summary_parts.append(f"  {stage_name}: {msg}")
                self._stages_results.append({"name": stage_name, "ok": True, "msg": msg})
            except Exception as e:
                logger.error("バックグラウンド取得失敗: %s: %s", stage_name, e)
                try:
                    self.stage_completed.emit(stage_name, False, str(e))
                except Exception:
                    pass
                summary_parts.append(f"  {stage_name}: エラー ({e})")
                self._stages_results.append({"name": stage_name, "ok": False, "msg": str(e)})
                success_all = False

        elapsed = time.perf_counter() - t_start
        self._current_stage = ""

        with self._lock:
            self._running = False

        if self._cancelled:
            try:
                self.fetch_cancelled.emit()
            except Exception:
                pass
            logger.info("バックグラウンド取得: キャンセルされました (%.1f秒)", elapsed)
        else:
            summary = "\n".join(summary_parts) if summary_parts else "完了"
            full_msg = f"バックグラウンド取得完了 ({elapsed:.1f}秒)\n{summary}"
            try:
                self.all_completed.emit(success_all, full_msg)
            except Exception:
                pass
            logger.info(full_msg)
