try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
        QLabel, QLineEdit, QComboBox, QHeaderView, QSizePolicy, QAbstractItemView
    )
    from qt_compat.core import Qt, QTimer, Signal, QThread, Slot
    from qt_compat.gui import QDesktopServices
    from PySide6.QtCore import QUrl
except Exception:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
        QLabel, QLineEdit, QComboBox, QHeaderView, QSizePolicy, QAbstractItemView
    )
    from PySide6.QtCore import Qt, QTimer, Signal, QThread, Slot, QUrl
    from PySide6.QtGui import QDesktopServices
import logging
import os
from datetime import datetime, timezone, timedelta

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

import classes.data_entry.core.registration_status_service as regsvc
from classes.managers.token_manager import TokenManager

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


class _SortableItem(QTableWidgetItem):
    """表示テキストとは別に sort key を持たせるためのItem。"""

    def __init__(self, text: str = "", sort_key=None):
        super().__init__(text)
        if sort_key is not None:
            self.setData(Qt.UserRole, sort_key)

    def __lt__(self, other):
        try:
            a = self.data(Qt.UserRole)
            b = other.data(Qt.UserRole)
            if a is not None and b is not None:
                return a < b
        except Exception:
            pass
        return super().__lt__(other)


class _EntryCacheWorker(QThread):

    def __init__(self, entry_ids: list[str]):
        super().__init__()
        self._entry_ids = entry_ids
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for entry_id in self._entry_ids:
            if self._cancelled:
                break
            try:
                regsvc.ensure_entry_detail_cached(entry_id)
            except Exception as exc:
                logger.debug("[登録状況] 個別JSONキャッシュに失敗: id=%s err=%s", entry_id, exc)


class _EntryPollWorker(QThread):
    fetched = Signal(str, object)  # (entry_id, detail_json)

    def __init__(self, entry_id: str):
        super().__init__()
        self._entry_id = entry_id

    def run(self):
        payload = regsvc.fetch_entry_detail(self._entry_id, overwrite=True)
        self.fetched.emit(self._entry_id, payload)


class _EntriesLoadWorker(QThread):
    loaded = Signal(object)  # entries(list[dict])

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        entries: list[dict] = []
        try:
            # 可能なら全件キャッシュをTTL無視で読み込み（ネットワークアクセス無し）
            if getattr(regsvc, "has_all_cache", None) and regsvc.has_all_cache(ignore_ttl=True):
                entries = regsvc.load_all_cache(ignore_ttl=True)
            elif regsvc.has_valid_cache():
                # TTL内のキャッシュのみ利用（ネットワークアクセス無し）
                entries = regsvc.fetch_latest(limit=100, use_cache=True)
        except Exception as exc:
            logger.debug("[登録状況] キャッシュロードに失敗: %s", exc)
            entries = []
        if self._cancelled:
            return
        self.loaded.emit(entries)

class RegistrationStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # タブ内に埋め込まれるケースでは、親ウィンドウ側のレイアウトに追従させる。
        # （固定サイズ/タイトル設定はトップレベル表示時のみ）
        if parent is None:
            self.setWindowTitle("登録状況")
        self._is_visible = False
        self._cache_worker: _EntryCacheWorker | None = None
        self._load_worker: _EntriesLoadWorker | None = None
        self._poll_timers: dict[str, QTimer] = {}
        self._poll_remaining: dict[str, int] = {}
        self._poll_workers: dict[str, _EntryPollWorker] = {}
        # 実行中のQThread参照を保持してGC/破棄によるクラッシュを防ぐ。
        # （"QThread: Destroyed while thread is still running" 対策）
        self._retired_workers: set[QThread] = set()
        # 注意: テーブルはユーザーソートで行順が変わるため、entry_id→row の固定マップは使わない
        self._row_by_entry_id: dict[str, int] = {}
        if parent is None:
            self.resize(1000, 600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)

        # Controls
        ctrl = QHBoxLayout()
        self.btn_latest = QPushButton("最新100件を取得")
        self.btn_all = QPushButton("全件を取得 (オプション)")
        self.btn_clear = QPushButton("キャッシュ削除")
        self.lbl_summary = QLabel("")
        self.lbl_summary.setAlignment(Qt.AlignLeft)
        ctrl.addWidget(self.btn_latest)
        ctrl.addWidget(self.btn_all)
        ctrl.addWidget(self.btn_clear)
        ctrl.addWidget(self.lbl_summary)
        layout.addLayout(ctrl)

        # Filters row (per column + status)
        filters = QHBoxLayout()
        self.filter_start = QLineEdit(); self.filter_start.setPlaceholderText("開始時刻フィルタ")
        self.filter_data = QLineEdit(); self.filter_data.setPlaceholderText("データ名フィルタ")
        self.filter_dataset = QLineEdit(); self.filter_dataset.setPlaceholderText("データセットフィルタ")
        self.filter_status = QComboBox(); self.filter_status.addItem("(すべて)")
        self.filter_creator = QLineEdit(); self.filter_creator.setPlaceholderText("データ投入者(所属)フィルタ")
        self.filter_inst = QLineEdit(); self.filter_inst.setPlaceholderText("装置フィルタ")
        filters.addWidget(self.filter_start)
        filters.addWidget(self.filter_data)
        filters.addWidget(self.filter_dataset)
        filters.addWidget(self.filter_status)
        filters.addWidget(self.filter_creator)
        filters.addWidget(self.filter_inst)
        layout.addLayout(filters)

        self.cache_info_label = QLabel("キャッシュ情報: なし")
        self.cache_info_label.setAlignment(Qt.AlignLeft)
        self.cache_info_label.setWordWrap(True)
        layout.addWidget(self.cache_info_label)

        # Table
        # 列定義
        self.COL_AUTO = 0
        self.COL_START = 1
        self.COL_DATA_NAME = 2
        self.COL_DATASET_NAME = 3
        self.COL_STATUS = 4
        self.COL_INGESTOR_ORG = 5
        self.COL_OWNER_ORG = 6
        self.COL_ERROR_CODE = 7
        self.COL_ERROR_MESSAGE = 8
        self.COL_INSTRUMENT = 9
        self.COL_ENTRY_ID = 10
        self.COL_LINK = 11

        self.table = QTableWidget(0, 12, self)
        self.table.setHorizontalHeaderLabels([
            "自動確認",
            "開始時刻",
            "データ名",
            "データセット",
            "ステータス",
            "データ投入者(所属)",
            "データ所有者(所属)",
            "エラーコード",
            "エラーメッセージ",
            "装置",
            "ID",
            "リンク",
        ])
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(24)
        header.setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.table)

        # 列幅（リンク列の幅/ボタン幅を小さめに）
        try:
            self.table.setColumnWidth(self.COL_AUTO, 86)
            self.table.setColumnWidth(self.COL_ENTRY_ID, 220)
            self.table.setColumnWidth(self.COL_LINK, 60)
        except Exception:
            pass

        # Signals
        self.btn_latest.clicked.connect(self.load_latest)
        self.btn_all.clicked.connect(self.load_all)
        self.btn_clear.clicked.connect(self.clear_cache)
        self.table.cellClicked.connect(self._on_cell_clicked)
        # Filter signals
        self.filter_start.textChanged.connect(self._apply_filters)
        self.filter_data.textChanged.connect(self._apply_filters)
        self.filter_dataset.textChanged.connect(self._apply_filters)
        self.filter_status.currentIndexChanged.connect(self._apply_filters)
        self.filter_creator.textChanged.connect(self._apply_filters)
        self.filter_inst.textChanged.connect(self._apply_filters)

        # 破棄時にスレッドが残っているとクラッシュするため、念のため停止処理を仕込む。
        try:
            self.destroyed.connect(self._on_destroyed)
        except Exception:
            pass

    def _retire_worker(self, worker: QThread | None) -> None:
        if worker is None:
            return
        self._retired_workers.add(worker)

        def _cleanup():
            try:
                self._retired_workers.discard(worker)
            except Exception:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass

        # QThread.finished は built-in signal。_EntryCacheWorker は同名を上書きしているが
        # いずれも .finished で接続できる想定。
        try:
            worker.finished.connect(_cleanup)
        except Exception:
            pass

    def _on_destroyed(self, *_args):
        # QWidget破棄直前に残スレッドを止めないと、Qtが異常終了する可能性がある。
        try:
            self._finalize_threads(wait_ms=5000)
        except Exception:
            pass

    def _finalize_threads(self, wait_ms: int = 2000) -> None:
        # タイマー/ポーリング停止
        try:
            self._stop_all_polling()
        except Exception:
            pass

        # ワーカー停止要求
        self._cancel_cache_worker(retire=True)
        self._cancel_load_worker(retire=True)

        # まだ走っているスレッドがあれば待機（最後の手段で terminate）
        workers = set(self._retired_workers)
        if self._cache_worker is not None:
            workers.add(self._cache_worker)
        if self._load_worker is not None:
            workers.add(self._load_worker)
        for w in list(workers):
            try:
                if w.isRunning():
                    w.wait(wait_ms)
                if w.isRunning():
                    # キャンセル不能なブロッキングが残る場合の最終手段
                    w.terminate()
                    w.wait(1000)
            except Exception:
                pass

    def _is_terminal_status(self, status: str | None) -> bool:
        s = (status or '').strip().upper()
        return s in {"COMPLETED", "FAILED", "CANCELLED", "CANCELED"}

    def _terminal_label(self, status: str | None) -> str:
        s = (status or '').strip().upper()
        if s == "COMPLETED":
            return "完了"
        if s == "FAILED":
            return "失敗"
        if s in {"CANCELLED", "CANCELED"}:
            return "取消"
        return "確認"

    def showEvent(self, event):
        super().showEvent(event)
        self._is_visible = True
        # pytest中はQtスレッドが不安定になり得るため、自動ロードは行わない。
        # テストは btn_latest / btn_all で明示的にロードする。
        if os.environ.get("PYTEST_CURRENT_TEST"):
            self.update_cache_info_label()
            return
        # キャッシュ読み込みは別スレッドで実行し、タブ選択時にUIを固めない。
        try:
            self._cancel_load_worker(retire=True)
            self.lbl_summary.setText("キャッシュ読込中…")
            self._load_worker = _EntriesLoadWorker()
            self._load_worker.loaded.connect(self._on_entries_loaded)
            self._load_worker.start()
        except Exception as ex:
            logger.warning(f"[登録状況] 自動表示(非同期)起動で例外: {ex}")
        self.update_cache_info_label()

    def hideEvent(self, event):
        try:
            self._is_visible = False
            self._stop_all_polling()
            # 非表示化ではUI操作不能になるだけで破棄ではないため、
            # 実行中スレッドは参照を保持したままキャンセル要求だけ行う。
            self._cancel_cache_worker(retire=True)
            self._cancel_load_worker(retire=True)
        finally:
            super().hideEvent(event)

    def _cancel_load_worker(self, *, retire: bool = False):
        worker = self._load_worker
        self._load_worker = None
        if worker is None:
            return
        try:
            if worker.isRunning() and hasattr(worker, 'cancel'):
                worker.cancel()
        except Exception:
            pass
        if retire and getattr(worker, 'isRunning', lambda: False)():
            self._retire_worker(worker)

    @Slot(object)
    def _on_entries_loaded(self, entries):
        if not self._is_visible:
            return
        try:
            if isinstance(entries, list) and entries:
                self._populate(entries)
            else:
                self.lbl_summary.setText("キャッシュがありません")
        finally:
            self.update_cache_info_label()

    def clear_cache(self):
        try:
            logger.info("[登録状況] キャッシュ削除ボタン押下")
            regsvc.clear_cache()
            self.lbl_summary.setText("キャッシュを削除しました")
            self.table.setRowCount(0)
        except Exception as ex:
            logger.exception(f"キャッシュ削除に失敗: {ex}")
            self.lbl_summary.setText("キャッシュ削除に失敗しました。ログをご確認ください。")
        finally:
            self.update_cache_info_label()

    def _populate(self, entries, *, start_cache_worker: bool = True):
        was_sorting = False
        was_updates = True
        try:
            was_sorting = self.table.isSortingEnabled()
            if was_sorting:
                self.table.setSortingEnabled(False)
        except Exception:
            was_sorting = False

        try:
            was_updates = self.table.updatesEnabled()
            self.table.setUpdatesEnabled(False)
        except Exception:
            was_updates = True

        self._row_by_entry_id = {}
        self.table.setRowCount(len(entries))
        statuses = set()
        status_counts: dict[str, int] = {}

        for row, e in enumerate(entries):
            entry_id = e.get('id') or ''
            self._row_by_entry_id[entry_id] = row

            # 自動確認列（セルクリックで操作。行ごとのQPushButtonは生成しない）
            auto_item = _SortableItem("確認", sort_key=1)
            self.table.setItem(row, self.COL_AUTO, auto_item)
            self._apply_auto_item_style(auto_item, state="idle")

            self.table.setItem(row, self.COL_START, QTableWidgetItem(e.get('startTime') or ''))
            self.table.setItem(row, self.COL_DATA_NAME, QTableWidgetItem(e.get('dataName') or ''))
            self.table.setItem(row, self.COL_DATASET_NAME, QTableWidgetItem(e.get('datasetName') or ''))
            status_text = e.get('status') or ''
            self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(status_text))
            if status_text:
                statuses.add(status_text)
            status_counts[status_text or 'UNKNOWN'] = status_counts.get(status_text or 'UNKNOWN', 0) + 1

            ingestor = self._format_user_org(e.get('createdByName'), e.get('createdByOrg'))
            owner = self._format_user_org(e.get('dataOwnerName'), e.get('dataOwnerOrg'))
            self.table.setItem(row, self.COL_INGESTOR_ORG, QTableWidgetItem(ingestor))
            self.table.setItem(row, self.COL_OWNER_ORG, QTableWidgetItem(owner))
            self.table.setItem(row, self.COL_ERROR_CODE, QTableWidgetItem(e.get('errorCode') or ''))
            self.table.setItem(row, self.COL_ERROR_MESSAGE, QTableWidgetItem(e.get('errorMessage') or ''))
            ins = e.get('instrumentNameJa') or e.get('instrumentNameEn') or ''
            self.table.setItem(row, self.COL_INSTRUMENT, QTableWidgetItem(ins))
            # ID列（リンクボタン対象のIDをそのまま表示）
            self.table.setItem(row, self.COL_ENTRY_ID, QTableWidgetItem(entry_id))

            # リンク列（セルクリックで操作。行ごとのQPushButtonは生成しない）
            link_item = QTableWidgetItem("開く")
            link_item.setData(Qt.UserRole, entry_id)
            self.table.setItem(row, self.COL_LINK, link_item)

            # 終端ステータス(COMPLETED/FAILED/CANCELLED)は確認不可
            if self._is_terminal_status(status_text):
                auto_item.setText(self._terminal_label(status_text))
                self._apply_auto_item_style(auto_item, state="disabled")
                self._set_auto_sort_value(row, enabled=False)
            else:
                self._set_auto_sort_value(row, enabled=True)

        self.lbl_summary.setText(f"件数: {len(entries)} / ステータス: {status_counts}")
        # Update status filter
        current = self.filter_status.currentText()
        self.filter_status.blockSignals(True)
        self.filter_status.clear()
        self.filter_status.addItem("(すべて)")
        for s in sorted(statuses):
            self.filter_status.addItem(s)
        idx = self.filter_status.findText(current)
        if idx >= 0:
            self.filter_status.setCurrentIndex(idx)
        self.filter_status.blockSignals(False)

        try:
            if was_sorting:
                self.table.setSortingEnabled(True)
        except Exception:
            pass

        try:
            if was_updates:
                self.table.setUpdatesEnabled(True)
        except Exception:
            pass

        # 仕様: リスト取得時に個別JSONを output/rde/data/entry に格納（既存は更新しない）
        if start_cache_worker:
            self._start_cache_worker_for_entries(entries)

    def _start_cache_worker_for_entries(self, entries: list[dict]):
        if not self._is_visible:
            return
        try:
            entry_ids = [e.get('id') for e in entries if e.get('id')]
            if not entry_ids:
                return
            self._cancel_cache_worker(retire=True)
            self._cache_worker = _EntryCacheWorker(entry_ids)
            # 完了後に参照を外す
            self._cache_worker.finished.connect(lambda: setattr(self, '_cache_worker', None))
            self._cache_worker.start()
        except Exception as exc:
            logger.debug("[登録状況] 個別JSONキャッシュワーカー起動に失敗: %s", exc)

    def _cancel_cache_worker(self, *, retire: bool = False):
        worker = self._cache_worker
        self._cache_worker = None
        if worker is None:
            return
        try:
            if worker.isRunning() and hasattr(worker, 'cancel'):
                worker.cancel()
        except Exception:
            pass
        if retire and getattr(worker, 'isRunning', lambda: False)():
            self._retire_worker(worker)

    def update_cache_info_label(self):
        try:
            metadata = regsvc.get_cache_metadata()
        except AttributeError:
            self.cache_info_label.setText("キャッシュ情報: 取得できません")
            return
        except Exception as exc:
            logger.warning("[登録状況] キャッシュ情報取得に失敗: %s", exc)
            self.cache_info_label.setText("キャッシュ情報: 取得に失敗しました")
            return

        if not metadata:
            self.cache_info_label.setText("キャッシュ情報: なし")
            return

        parts = []
        for info in metadata:
            label = "最新100件" if info.get("type") == "latest" else "全件"
            updated = info.get("updated_at")
            if isinstance(updated, datetime):
                updated_local = updated.astimezone(JST)
                timestamp = updated_local.strftime("%Y-%m-%d %H:%M:%S JST")
            else:
                timestamp = "時刻不明"
            count = info.get("count", 0)
            parts.append(f"{label}: {count}件 ({timestamp})")

        self.cache_info_label.setText("キャッシュ情報: " + " | ".join(parts))

    def _open_entry(self, entry_id: str):
        if not entry_id:
            return
        url = f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{entry_id}"
        logger.info(f"[登録状況] エントリーをブラウザで開く: {url}")
        QDesktopServices.openUrl(QUrl(url))

    def _apply_filters(self):
        fs = {
            self.COL_START: self.filter_start.text().strip().lower(),
            self.COL_DATA_NAME: self.filter_data.text().strip().lower(),
            self.COL_DATASET_NAME: self.filter_dataset.text().strip().lower(),
            self.COL_STATUS: self.filter_status.currentText(),
            self.COL_INGESTOR_ORG: self.filter_creator.text().strip().lower(),
            self.COL_INSTRUMENT: self.filter_inst.text().strip().lower(),
        }
        rows = self.table.rowCount()
        for r in range(rows):
            visible = True
            for c in (self.COL_START, self.COL_DATA_NAME, self.COL_DATASET_NAME, self.COL_INGESTOR_ORG, self.COL_INSTRUMENT):
                item = self.table.item(r, c)
                val = (item.text() if item else '').lower()
                if fs[c] and fs[c] not in val:
                    visible = False
                    break
            if visible:
                if fs[self.COL_STATUS] and fs[self.COL_STATUS] != "(すべて)":
                    item = self.table.item(r, self.COL_STATUS)
                    val = item.text() if item else ''
                    if val != fs[self.COL_STATUS]:
                        visible = False
            self.table.setRowHidden(r, not visible)

    def _apply_auto_item_style(self, item: QTableWidgetItem, *, state: str):
        """自動確認セルの見た目を状態に応じて更新する。

        state:
            - idle: 押下可能（未完了）
            - countdown: ポーリング待機（次の取得まで）
            - fetching: 取得中
            - disabled: COMPLETED 等で無効
        """
        if state == "disabled":
            bg = get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)
            fg = get_color(ThemeKey.BUTTON_DISABLED_TEXT)
            bd = get_color(ThemeKey.BUTTON_DISABLED_BORDER)
            hover = bg
        elif state == "fetching":
            bg = get_color(ThemeKey.BUTTON_INFO_BACKGROUND)
            fg = get_color(ThemeKey.BUTTON_INFO_TEXT)
            bd = get_color(ThemeKey.BUTTON_INFO_BORDER)
            hover = get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)
        elif state == "countdown":
            bg = get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)
            fg = get_color(ThemeKey.BUTTON_WARNING_TEXT)
            bd = get_color(ThemeKey.BUTTON_WARNING_BORDER)
            hover = get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)
        else:
            bg = get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)
            fg = get_color(ThemeKey.BUTTON_SUCCESS_TEXT)
            bd = get_color(ThemeKey.BUTTON_SUCCESS_BORDER)
            hover = get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)

        try:
            # 規約: QColor() の直接使用は禁止。テーマモジュール経由で取得する。
            from qt_compat.gui import QBrush
            from classes.theme import get_qcolor

            item.setBackground(QBrush(get_qcolor(bg)))
            item.setForeground(QBrush(get_qcolor(fg)))
        except Exception:
            # 互換レイヤや環境差異でBrush適用できない場合は無視
            pass

    def _set_auto_sort_value(self, row: int, *, enabled: bool) -> None:
        """自動確認列のソート値（有効=1, 無効=0）を更新する。"""
        try:
            item = self.table.item(row, self.COL_AUTO)
            if item is None:
                item = _SortableItem("", sort_key=(1 if enabled else 0))
                self.table.setItem(row, self.COL_AUTO, item)
            item.setData(Qt.UserRole, 1 if enabled else 0)
        except Exception:
            pass

    def _get_auto_item(self, row: int) -> QTableWidgetItem | None:
        try:
            return self.table.item(row, self.COL_AUTO)
        except Exception:
            return None

    def _find_row_by_entry_id(self, entry_id: str) -> int | None:
        """現在のテーブル上の行番号を entry_id から探す。

        ソート等で行が移動するため、固定マップではなくID列(7)の値から検索する。
        """
        if not entry_id:
            return None
        try:
            rows = self.table.rowCount()
            for r in range(rows):
                item = self.table.item(r, self.COL_ENTRY_ID)
                if item and item.text() == entry_id:
                    return r
        except Exception:
            return None
        return None

    def _format_user_org(self, user_name: str | None, org_name: str | None) -> str:
        user_name = (user_name or '').strip()
        org_name = (org_name or '').strip()
        if user_name and org_name:
            return f"{user_name} ({org_name})"
        if user_name:
            return user_name
        if org_name:
            return org_name
        return ""

    def _on_cell_clicked(self, row: int, col: int):
        try:
            entry_item = self.table.item(row, self.COL_ENTRY_ID)
            entry_id = entry_item.text() if entry_item else ''
        except Exception:
            entry_id = ''
        if not entry_id:
            return

        if col == self.COL_AUTO:
            try:
                status_item = self.table.item(row, self.COL_STATUS)
                status_text = status_item.text() if status_item else ''
            except Exception:
                status_text = ''
            if self._is_terminal_status(status_text):
                return
            self._toggle_polling(entry_id)
            return
        if col == self.COL_LINK:
            self._open_entry(entry_id)
            return

    def _toggle_polling(self, entry_id: str):
        if not entry_id:
            return
        if entry_id in self._poll_timers:
            self._stop_polling(entry_id, reset_button=True)
            return
        self._start_polling(entry_id)

    def _start_polling(self, entry_id: str):
        if not entry_id:
            return
        if not self._is_visible:
            return
        row = self._find_row_by_entry_id(entry_id)
        if row is None:
            return

        # 終端ステータスは開始不可
        status_item = self.table.item(row, self.COL_STATUS)
        status_text = status_item.text() if status_item else ''
        if self._is_terminal_status(status_text):
            item = self._get_auto_item(row)
            if item:
                item.setText(self._terminal_label(status_text))
                self._apply_auto_item_style(item, state="disabled")
                self._set_auto_sort_value(row, enabled=False)
            return

        item = self._get_auto_item(row)
        if item:
            self._apply_auto_item_style(item, state="countdown")

        self._poll_remaining[entry_id] = 10
        self._update_poll_button_text(entry_id)

        timer = QTimer(self)
        timer.setInterval(1000)
        timer.timeout.connect(lambda eid=entry_id: self._on_poll_tick(eid))
        self._poll_timers[entry_id] = timer
        timer.start()

    def _update_poll_button_text(self, entry_id: str):
        row = self._find_row_by_entry_id(entry_id)
        if row is None:
            return
        item = self._get_auto_item(row)
        if not item:
            return
        remaining = self._poll_remaining.get(entry_id, 0)
        if remaining <= 0:
            item.setText("受信中…")
        else:
            item.setText(f"{remaining}s")

    def _on_poll_tick(self, entry_id: str):
        if not self._is_visible:
            self._stop_polling(entry_id)
            return

        remaining = self._poll_remaining.get(entry_id, 0) - 1
        self._poll_remaining[entry_id] = remaining
        if remaining > 0:
            self._update_poll_button_text(entry_id)
            return

        # 取得開始
        self._update_poll_button_text(entry_id)
        row = self._find_row_by_entry_id(entry_id)
        if row is not None:
            item = self._get_auto_item(row)
            if item:
                self._apply_auto_item_style(item, state="fetching")
        if entry_id in self._poll_workers and self._poll_workers[entry_id].isRunning():
            return
        worker = _EntryPollWorker(entry_id)
        self._poll_workers[entry_id] = worker
        worker.fetched.connect(self._on_entry_polled)
        worker.start()

    @Slot(str, object)
    def _on_entry_polled(self, entry_id: str, detail_json):
        # 次回までリセット
        if entry_id not in self._poll_timers:
            return
        self._poll_remaining[entry_id] = 10

        row = self._find_row_by_entry_id(entry_id)
        if row is None:
            self._stop_polling(entry_id)
            return

        # 受信完了→次回カウントダウン表示へ
        item = self._get_auto_item(row)
        if item:
            self._apply_auto_item_style(item, state="countdown")

        summary = None
        try:
            if isinstance(detail_json, dict):
                summary = regsvc.entry_detail_to_summary(detail_json)
        except Exception as exc:
            logger.debug("[登録状況] detail→summary変換失敗: id=%s err=%s", entry_id, exc)

        if summary:
            self._update_row_from_summary(row, summary)

        # 終端ステータスなら終了
        status_item = self.table.item(row, self.COL_STATUS)
        status_text = status_item.text() if status_item else ''
        if self._is_terminal_status(status_text):
            item = self._get_auto_item(row)
            if item:
                item.setText(self._terminal_label(status_text))
                self._apply_auto_item_style(item, state="disabled")
            self._set_auto_sort_value(row, enabled=False)
            self._stop_polling(entry_id)
            return

        # 未完了ならソート上は有効のまま
        self._set_auto_sort_value(row, enabled=True)

        self._update_poll_button_text(entry_id)

    def _update_row_from_summary(self, row: int, summary: dict):
        try:
            self.table.setItem(row, self.COL_START, QTableWidgetItem(summary.get('startTime') or ''))
            self.table.setItem(row, self.COL_DATA_NAME, QTableWidgetItem(summary.get('dataName') or ''))
            self.table.setItem(row, self.COL_DATASET_NAME, QTableWidgetItem(summary.get('datasetName') or ''))
            self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(summary.get('status') or ''))
            ingestor = self._format_user_org(summary.get('createdByName'), summary.get('createdByOrg'))
            owner = self._format_user_org(summary.get('dataOwnerName'), summary.get('dataOwnerOrg'))
            self.table.setItem(row, self.COL_INGESTOR_ORG, QTableWidgetItem(ingestor))
            self.table.setItem(row, self.COL_OWNER_ORG, QTableWidgetItem(owner))
            self.table.setItem(row, self.COL_ERROR_CODE, QTableWidgetItem(summary.get('errorCode') or ''))
            self.table.setItem(row, self.COL_ERROR_MESSAGE, QTableWidgetItem(summary.get('errorMessage') or ''))
            ins = summary.get('instrumentNameJa') or summary.get('instrumentNameEn') or ''
            self.table.setItem(row, self.COL_INSTRUMENT, QTableWidgetItem(ins))
            # ID列は維持
        except Exception as exc:
            logger.debug("[登録状況] 行更新に失敗: row=%s err=%s", row, exc)

    def _stop_polling(self, entry_id: str, *, reset_button: bool = False):
        timer = self._poll_timers.pop(entry_id, None)
        if timer:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
        self._poll_remaining.pop(entry_id, None)
        worker = self._poll_workers.pop(entry_id, None)
        if worker and worker.isRunning():
            # 強制停止はしない（完了通知だけ捨てる）が、参照を維持しないとGCでクラッシュする。
            self._retire_worker(worker)

        if reset_button:
            row = self._find_row_by_entry_id(entry_id)
            if row is not None:
                item = self._get_auto_item(row)
                if item:
                    item.setText("確認")
                    self._apply_auto_item_style(item, state="idle")
                self._set_auto_sort_value(row, enabled=True)

    def _stop_all_polling(self):
        for entry_id in list(self._poll_timers.keys()):
            self._stop_polling(entry_id)

    def load_latest(self):
        try:
            logger.info("[登録状況] 最新100件取得ボタン押下")
            self.lbl_summary.setText("取得中… 最新100件を問い合わせています")
            logger.info("[登録状況] API呼び出し開始: fetch_latest(limit=100)")
            tm = TokenManager.get_instance()
            if not tm.get_access_token('rde.nims.go.jp'):
                # テストやキャッシュ利用のケースでも進めるため、早期returnはしない
                self.lbl_summary.setText("トークン未設定の可能性があります（必要に応じて左の『ログイン』をご利用ください）。続行して取得を試みます…")
                logger.warning("[登録状況] アクセストークン未検出: rde.nims.go.jp。続行して取得を試行します。")
            self.btn_latest.setEnabled(False)
            self.btn_all.setEnabled(False)
            entries = regsvc.fetch_latest(limit=100, use_cache=False)
            logger.debug(f"[登録状況] 取得件数: {len(entries)}")
            self._populate(entries)
            if len(entries) == 0:
                self.lbl_summary.setText("0件でした。認証エラーや権限不足の可能性があります。ログを確認してください。")
        except Exception as ex:
            logger.exception(f"最新取得に失敗: {ex}")
            self.lbl_summary.setText("最新取得に失敗しました。ログをご確認ください。")
        finally:
            self.btn_latest.setEnabled(True)
            self.btn_all.setEnabled(True)
            self.update_cache_info_label()

    def load_all(self):
        try:
            logger.info("[登録状況] 全件取得ボタン押下")
            self.lbl_summary.setText("取得中… 全件を問い合わせています")
            logger.info("[登録状況] API呼び出し開始: fetch_all(chunk=5000)")
            tm = TokenManager.get_instance()
            if not tm.get_access_token('rde.nims.go.jp'):
                # テストやキャッシュ利用のケースでも進めるため、早期returnはしない
                self.lbl_summary.setText("トークン未設定の可能性があります（必要に応じて左の『ログイン』をご利用ください）。続行して取得を試みます…")
                logger.warning("[登録状況] アクセストークン未検出: rde.nims.go.jp。続行して取得を試行します。")
            self.btn_latest.setEnabled(False)
            self.btn_all.setEnabled(False)
            entries = regsvc.fetch_all(default_chunk=5000, use_cache=False)
            logger.debug(f"[登録状況] 全件取得完了: {len(entries)}")
            self._populate(entries)
            if len(entries) == 0:
                self.lbl_summary.setText("0件でした。認証エラーや権限不足の可能性があります。ログを確認してください。")
        except Exception as ex:
            logger.exception(f"全件取得に失敗: {ex}")
            self.lbl_summary.setText("全件取得に失敗しました。ログをご確認ください。")
        finally:
            self.btn_latest.setEnabled(True)
            self.btn_all.setEnabled(True)
            self.update_cache_info_label()
