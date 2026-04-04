"""基本情報: 統合ステータス表示（段階別完了状況 + 取得状況）

- 表示は QTableWidget で統合
- 項目名/ファイル名/一覧・個別/取得割合/タイムスタンプ(JSON日時・fetch_meta・mtime)/サイズ 等を表示
- テーマは classes.theme (ThemeKey) を使用
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from dateutil.parser import parse as parse_datetime

from classes.theme import ThemeKey, get_color
from config.common import get_dynamic_file_path
from qt_compat.core import Qt, QTimer, Signal
from qt_compat.widgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QComboBox,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _StageDef:
    name: str
    required_items: tuple[str, ...]
    # common_info2 の fetch_meta に寄せる（存在しない場合は空表示）
    fetch_meta_target_ids: tuple[str, ...] = ()


def _read_json(path: Path) -> Optional[Any]:
    try:
        if not path.exists() or not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _extract_json_datetime(path: Path) -> Optional[datetime]:
    """JSON内の日時っぽいフィールドを抽出してUTC datetimeにする（見つからなければNone）"""
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None

    candidates: list[str] = []

    meta = payload.get("meta")
    if isinstance(meta, dict):
        for k in ("updatedAt", "generatedAt", "createdAt", "fetchedAt"):
            v = meta.get(k)
            if isinstance(v, str) and v:
                candidates.append(v)

    data = payload.get("data")
    if isinstance(data, dict):
        attr = data.get("attributes")
        if isinstance(attr, dict):
            for k in ("modified", "updated", "created"):
                v = attr.get(k)
                if isinstance(v, str) and v:
                    candidates.append(v)
    elif isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            attr = first.get("attributes")
            if isinstance(attr, dict):
                for k in ("modified", "updated", "created"):
                    v = attr.get(k)
                    if isinstance(v, str) and v:
                        candidates.append(v)

    for raw in candidates:
        try:
            dt = parse_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue

    return None


def _format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        jst = timezone(timedelta(hours=9))
        return dt.astimezone(jst).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _mtime_utc(path: Path) -> Optional[datetime]:
    try:
        if not path.exists():
            return None
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _iter_json_files(dir_path: Path) -> Iterable[Path]:
    try:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        return [p for p in dir_path.glob("*.json") if p.is_file()]
    except Exception:
        return []


def _latest_json_file(dir_path: Path) -> Optional[Path]:
    files = list(_iter_json_files(dir_path))
    if not files:
        return None
    try:
        return max(files, key=lambda p: p.stat().st_mtime)
    except Exception:
        return None


def _sum_size_bytes(paths: Iterable[Path]) -> int:
    total = 0
    for p in paths:
        try:
            if p.is_file():
                total += p.stat().st_size
        except Exception:
            continue
    return total


def _dir_size_and_count(dir_path: Path) -> tuple[int, int]:
    files = list(_iter_json_files(dir_path))
    return _sum_size_bytes(files), len(files)


def _meta_path_for_target(target_id: str) -> Path:
    return Path(get_dynamic_file_path(f"output/rde/data/.fetch_meta/{target_id}.json"))


def _read_fetch_meta_datetime(target_id: str) -> Optional[datetime]:
    meta_path = _meta_path_for_target(target_id)
    payload = _read_json(meta_path)
    if not isinstance(payload, dict):
        return None

    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, str) or not fetched_at:
        return None

    try:
        dt = parse_datetime(fetched_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _read_fetch_meta_elapsed_seconds(target_id: str) -> Optional[float]:
    meta_path = _meta_path_for_target(target_id)
    payload = _read_json(meta_path)
    if not isinstance(payload, dict):
        return None
    raw = payload.get("elapsed_seconds")
    try:
        if raw is None:
            return None
        value = float(raw)
        if value < 0:
            return None
        return value
    except Exception:
        return None


def _sum_fetch_meta_elapsed_seconds(target_ids: Iterable[str]) -> Optional[float]:
    total = 0.0
    found = False
    for tid in target_ids:
        v = _read_fetch_meta_elapsed_seconds(tid)
        if v is None:
            continue
        total += v
        found = True
    return total if found else None


def _format_elapsed_short(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    try:
        total = int(round(float(seconds)))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return ""


def _latest_fetch_meta_datetime(target_ids: Iterable[str]) -> Optional[datetime]:
    latest: Optional[datetime] = None
    for tid in target_ids:
        dt = _read_fetch_meta_datetime(tid)
        if not dt:
            continue
        latest = dt if latest is None else max(latest, dt)
    return latest


class BasicUnifiedStatusWidget(QWidget):
    """基本情報: 統合ステータス表示ウィジェット"""

    # ワーカースレッド→UIスレッドへ結果を渡す
    _status_rows_ready = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auth_border_color_key: Optional[ThemeKey] = None

        self._refetch_button_style: str = ""
        self._columns_sized_once: bool = False

        self._controller = None

        self._timer: Optional[QTimer] = None

        self._perf_logger = logging.getLogger("RDE_WebView")
        self._PerfMonitor = None

        # update_status() が重い場合でもUIスレッドを塞がないための制御
        self._status_update_seq: int = 0
        self._status_update_inflight: bool = False
        self._status_update_pending: bool = False
        self._status_loading_seq: int = 0

        self._auth_label = QLabel("")
        self._auth_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._loading_label = QLabel("")
        self._loading_label.setObjectName('basicInfoStatusLoadingLabel')
        self._loading_label.setVisible(False)

        # 旧UI互換のため部品は保持（表示はしない）
        self._stage_label = QLabel("個別取得")
        self._stage_combo = QComboBox()
        self._stage_execute_button = QPushButton("実行")

        self.refresh_button = QPushButton("状況更新")
        self.refresh_button.setMaximumWidth(100)
        self.refresh_button.clicked.connect(self.update_status)

        self.debug_button = QPushButton("🔍 API Debug")
        self.debug_button.setMaximumWidth(120)
        self.debug_button.clicked.connect(self._show_api_debug)

        self._stage_execute_button.clicked.connect(self._on_stage_execute_clicked)

        self.table = QTableWidget()
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            [
                "項目",
                "対象",
                "再取得",
                "種別",
                "取得割合",
                "JSON日時",
                "fetch_meta",
                "mtime",
                "サイズ",
                "取得時間",
                "件数",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_table_cell_clicked)

        # バックグラウンド取得プログレスバー領域
        self._bg_fetch_frame = QWidget()
        self._bg_fetch_frame.setVisible(False)
        bg_layout = QHBoxLayout(self._bg_fetch_frame)
        bg_layout.setContentsMargins(0, 4, 0, 4)
        self._bg_fetch_label = QLabel("個別データ取得中...")
        self._bg_fetch_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._bg_fetch_progress = QProgressBar()
        self._bg_fetch_progress.setRange(0, 100)
        self._bg_fetch_progress.setValue(0)
        self._bg_fetch_progress.setFixedWidth(200)
        self._bg_fetch_progress.setFixedHeight(18)
        self._bg_fetch_cancel_btn = QPushButton("中止")
        self._bg_fetch_cancel_btn.setMaximumWidth(60)
        self._bg_fetch_cancel_btn.clicked.connect(self._on_bg_fetch_cancel)
        bg_layout.addWidget(self._bg_fetch_label)
        bg_layout.addWidget(self._bg_fetch_progress)
        bg_layout.addWidget(self._bg_fetch_cancel_btn)

        # 接続済みマネージャーの参照
        self._bg_fetch_manager = None

        # ProgressWorker 埋め込み実行用
        self._embedded_worker = None
        self._embedded_thread: Optional[threading.Thread] = None
        self._embedded_task_name: str = ""
        self._embedded_on_finished = None

        root = QVBoxLayout(self)
        root.addWidget(self._auth_label)
        root.addWidget(self._loading_label)
        root.addWidget(self._bg_fetch_frame)
        root.addWidget(self.table, 1)

        self.refresh_theme()
        # 初回の状況更新は遅延実行にして、タブ切替や初回描画をブロックしにくくする
        QTimer.singleShot(0, self.update_status)

        QTimer.singleShot(0, self._connect_theme_signal)

        # 自動更新（重い場合があるため、間隔は設定で制御）
        # - 0 以下: 無効
        # - 既定: 30秒
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_status)
        self._apply_auto_refresh_policy()

        # 非同期計算結果をUIスレッドで反映
        try:
            self._status_rows_ready.connect(self._on_status_rows_ready)
        except Exception:
            pass

    def _on_status_rows_ready(self, seq: int, rows_obj: object) -> None:
        try:
            rows = rows_obj if isinstance(rows_obj, list) else []
            self._apply_status_rows(int(seq), rows, perf_logger=self._perf_logger, PerfMonitor=self._PerfMonitor)
        except Exception:
            logger.debug("BasicUnifiedStatusWidget apply (signal) failed", exc_info=True)
            try:
                self._status_update_inflight = False
            except Exception:
                pass

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._apply_auto_refresh_policy()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().hideEvent(event)
        try:
            if self._timer is not None:
                self._timer.stop()
        except Exception:
            pass

    def _apply_auto_refresh_policy(self) -> None:
        try:
            if self._timer is None:
                return
            if not self.isVisible():
                self._timer.stop()
                return

            from classes.managers.app_config_manager import get_config_manager

            cfg = get_config_manager()
            interval_ms = int(cfg.get("basic_info.status_auto_refresh_ms", 30000) or 0)
            if interval_ms <= 0:
                self._timer.stop()
                return

            self._timer.start(interval_ms)
        except Exception:
            # 失敗しても手動更新は使える
            try:
                if self._timer is not None:
                    self._timer.stop()
            except Exception:
                pass

    def set_controller(self, controller) -> None:
        self._controller = controller
        self._populate_stage_combo()

    def _populate_stage_combo(self) -> None:
        self._stage_combo.clear()
        try:
            from classes.basic.core.basic_info_logic import STAGE_FUNCTIONS

            for name, func in STAGE_FUNCTIONS.items():
                if func is None:
                    continue
                # セパレータは除外
                if isinstance(name, str) and name.startswith("---"):
                    continue
                self._stage_combo.addItem(str(name))
        except Exception:
            # 失敗時は空でも動作する
            pass

    def _on_stage_execute_clicked(self) -> None:
        if self._controller is None:
            QMessageBox.warning(self, "エラー", "コントローラーが設定されていません")
            return
        stage_name = (self._stage_combo.currentText() or "").strip()
        if not stage_name:
            return
        try:
            from classes.basic.ui.ui_basic_info import execute_individual_stage_ui

            execute_individual_stage_ui(self._controller, stage_name)
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"個別実行に失敗しました:\n{e}")

    def set_auth_status(self, status_text: str, border_color_key: Optional[ThemeKey] = None) -> None:
        """認証状況の表示を更新（validatorから呼ぶ）"""
        self._auth_border_color_key = border_color_key
        self._auth_label.setText(f"認証状況: {status_text}")
        self.refresh_theme()

    def refresh_theme(self, *_args, **_kwargs) -> None:
        try:
            from classes.utils.button_styles import get_button_style

            # テーブル内「再取得」ボタン（update_statusで生成される）
            self._refetch_button_style = get_button_style("basicinfo_refetch")

            self.refresh_button.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
                    border-radius: 4px;
                    padding: 5px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
                }}
                QPushButton:pressed {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
                }}
                """
            )

            self.debug_button.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                    border-radius: 4px;
                    padding: 5px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
                }}
                """
            )

            border_style = f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};"
            if isinstance(self._auth_border_color_key, ThemeKey):
                border_style = f"border: 1px solid {get_color(self._auth_border_color_key)};"

            self.table.setStyleSheet(
                f"""
                QTableWidget {{
                    background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                    {border_style}
                    border-radius: 4px;
                }}
                QHeaderView::section {{
                    background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
                    color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};
                    border: 1px solid {get_color(ThemeKey.TABLE_HEADER_BORDER)};
                    padding: 4px;
                }}
                """
            )

            self._auth_label.setStyleSheet(
                f"color: {get_color(ThemeKey.TEXT_SECONDARY)};"
            )
        except Exception as e:
            logger.debug("BasicUnifiedStatusWidget refresh_theme failed: %s", e)

    def _connect_theme_signal(self) -> None:
        try:
            from classes.theme.theme_manager import ThemeManager

            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
            self.refresh_theme()
        except Exception as e:
            logger.debug("BasicUnifiedStatusWidget theme signal connect failed: %s", e)

    def _build_stage_defs(self) -> list[_StageDef]:
        # basic_info_logic.get_stage_completion_status() と揃える
        return [
            _StageDef("ユーザー情報", ("self.json",), fetch_meta_target_ids=("self",)),
            _StageDef(
                "グループ関連情報",
                ("group.json", "groupDetail.json", "subGroup.json", "subGroups", "subGroupsAncestors"),
                fetch_meta_target_ids=("group_pipeline",),
            ),
            _StageDef(
                "組織・装置情報",
                ("organization.json", "instrumentType.json"),
                fetch_meta_target_ids=("organization", "instrument_type"),
            ),
            _StageDef("サンプル情報", ("samples",), fetch_meta_target_ids=("samples",)),
            _StageDef(
                "データセット情報",
                ("dataset.json", "datasets"),
                fetch_meta_target_ids=("dataset_list", "dataset_details"),
            ),
            _StageDef("データエントリ情報", ("dataEntry",), fetch_meta_target_ids=()),
            _StageDef("インボイス情報", ("invoice",), fetch_meta_target_ids=()),
            _StageDef("invoiceSchema情報", ("invoiceSchemas",), fetch_meta_target_ids=("invoiceSchemas",)),
            _StageDef(
                "テンプレート・設備情報",
                ("template.json", "instruments.json"),
                fetch_meta_target_ids=("template", "instruments"),
            ),
            _StageDef("統合情報生成", ("info.json",), fetch_meta_target_ids=("info_generate",)),
        ]

    def update_status(self) -> None:
        """ステータスを更新する。

        - ファイル/ディレクトリ走査が重くなる場合があるため、計算はバックグラウンドで行う
        - UI反映のみメインスレッドで実行する
        """

        # 多重実行抑止（タイマーや手動更新が重なると固まりやすい）
        if self._status_update_inflight:
            self._status_update_pending = True
            return

        self._status_update_inflight = True
        self._status_update_pending = False
        self._status_update_seq += 1
        seq = int(self._status_update_seq)
        self._status_loading_seq = seq
        try:
            self.refresh_button.setEnabled(False)
            self._loading_label.setVisible(False)
        except Exception:
            pass
        try:
            QTimer.singleShot(1000, lambda current_seq=seq: self._show_loading_hint(current_seq))
        except Exception:
            pass

        try:
            from classes.utils.perf_monitor import PerfMonitor
        except Exception:
            PerfMonitor = None

        perf_logger = logging.getLogger("RDE_WebView")
        self._perf_logger = perf_logger
        self._PerfMonitor = PerfMonitor

        def _worker():
            rows: list[dict[str, Any]]
            try:
                if PerfMonitor is not None:
                    with PerfMonitor.span("basic_info:status:compute", logger=perf_logger):
                        rows = self._compute_status_rows(perf_logger=perf_logger, PerfMonitor=PerfMonitor)
                else:
                    rows = self._compute_status_rows(perf_logger=None, PerfMonitor=None)
            except Exception:
                logger.debug("BasicUnifiedStatusWidget status compute failed", exc_info=True)
                rows = []

            # UI反映はSignal経由でメインスレッドへ配送する
            try:
                self._status_rows_ready.emit(seq, rows)
            except Exception:
                # ウィジェットが破棄された等
                pass

        try:
            threading.Thread(target=_worker, daemon=True, name=f"basic_info_status_{seq}").start()
        except Exception:
            # スレッド起動に失敗した場合は同期実行にフォールバック
            try:
                rows = self._compute_status_rows(perf_logger=perf_logger, PerfMonitor=PerfMonitor)
            except Exception:
                rows = []
            self._apply_status_rows(seq, rows, perf_logger=perf_logger, PerfMonitor=PerfMonitor)

    def _show_loading_hint(self, seq: int) -> None:
        if seq != self._status_loading_seq:
            return
        if not self._status_update_inflight:
            return
        try:
            self._loading_label.setText('状況を更新中です。読み込みに時間がかかっています...')
            self._loading_label.setVisible(True)
        except Exception:
            pass

    def _compute_status_rows(self, *, perf_logger, PerfMonitor) -> list[dict[str, Any]]:
        base_dir = Path(get_dynamic_file_path("output/rde/data"))

        try:
            from classes.basic.core.basic_info_logic import get_stage_completion_status

            if PerfMonitor is not None and perf_logger is not None:
                with PerfMonitor.span("basic_info:status:get_stage_completion_status", logger=perf_logger):
                    completion = get_stage_completion_status()
            else:
                completion = get_stage_completion_status()
        except Exception:
            completion = {}

        rows: list[dict[str, Any]] = []

        # 1回の更新内で同じディレクトリを何度も走査しない
        _dir_scan_cache: dict[Path, tuple[int, int, Optional[Path]]] = {}

        def _scan_json_dir(dir_path: Path) -> tuple[int, int, Optional[Path]]:
            cached = _dir_scan_cache.get(dir_path)
            if cached is not None:
                return cached

            total_bytes = 0
            count = 0
            latest_path: Optional[Path] = None
            latest_mtime: Optional[float] = None

            try:
                if not dir_path.exists() or not dir_path.is_dir():
                    result = (0, 0, None)
                    _dir_scan_cache[dir_path] = result
                    return result

                with os.scandir(dir_path) as it:
                    for entry in it:
                        try:
                            if not entry.is_file():
                                continue
                            name = entry.name
                            if not name.lower().endswith(".json"):
                                continue
                            st = entry.stat()
                            total_bytes += int(getattr(st, "st_size", 0) or 0)
                            count += 1
                            mt = float(getattr(st, "st_mtime", 0.0) or 0.0)
                            if latest_mtime is None or mt > latest_mtime:
                                latest_mtime = mt
                                latest_path = Path(entry.path)
                        except Exception:
                            continue
            except Exception:
                result = (0, 0, None)
                _dir_scan_cache[dir_path] = result
                return result

            result = (total_bytes, count, latest_path)
            _dir_scan_cache[dir_path] = result
            return result

        def _meta_ids_for_item(stage: _StageDef, item_name: str) -> tuple[str, ...]:
            # 代表的な item → fetch_meta target_id の対応
            mapping = {
                "self.json": ("self",),
                "group.json": ("group_pipeline",),
                "groupDetail.json": ("group_pipeline",),
                "subGroup.json": ("group_pipeline",),
                "subGroups": ("group_pipeline",),
                "subGroupsAncestors": ("group_pipeline",),
                "organization.json": ("organization",),
                "instrumentType.json": ("instrument_type",),
                "samples": ("samples",),
                "dataset.json": ("dataset_list",),
                "datasets": ("dataset_details",),
                "dataEntry": ("data_entry",),
                "invoice": ("invoice",),
                "invoiceSchemas": ("invoiceSchemas",),
                "template.json": ("template",),
                "instruments.json": ("instruments",),
                "licenses.json": ("licenses",),
                "info.json": ("info_generate",),
            }
            return mapping.get(item_name, stage.fetch_meta_target_ids)

        for stage in self._build_stage_defs():
            stage_info = completion.get(stage.name, {}) if isinstance(completion, dict) else {}

            completed = int(stage_info.get("completed", 0) or 0)
            total = int(stage_info.get("total", len(stage.required_items)) or 0)
            rate = float(stage_info.get("rate", 0.0) or 0.0)

            stage_ratio = f"{completed}/{total} ({rate:.1f}%)" if total > 0 else "-"

            # アンカーパス（表示用の代表）
            anchor: Optional[Path] = None
            for item in stage.required_items:
                p = base_dir / item
                if p.exists() and p.is_file():
                    anchor = p
                    break
            if anchor is None:
                # ディレクトリから最新JSON
                for item in stage.required_items:
                    p = base_dir / item
                    if p.exists() and p.is_dir():
                        _size_b, _n, latest = _scan_json_dir(p)
                        if latest is not None:
                            anchor = latest
                            break

            json_dt = _extract_json_datetime(anchor) if anchor and anchor.suffix.lower() == ".json" else None
            fetch_dt = _latest_fetch_meta_datetime(stage.fetch_meta_target_ids)
            elapsed_stage = _sum_fetch_meta_elapsed_seconds(stage.fetch_meta_target_ids)

            # stage の mtime はアンカーの mtime を採用
            mtime_dt = _mtime_utc(anchor) if anchor else None

            # size/count: stage の required_items 合算
            total_bytes = 0
            count_text_parts: list[str] = []
            kind = "段階"
            targets_display = "\n".join(stage.required_items)

            for item in stage.required_items:
                p = base_dir / item
                if p.exists() and p.is_file():
                    try:
                        total_bytes += p.stat().st_size
                    except Exception:
                        pass
                elif p.exists() and p.is_dir():
                    size_b, n, _latest = _scan_json_dir(p)
                    total_bytes += size_b
                    count_text_parts.append(f"{item}:{n}")
                else:
                    # missing
                    if item.endswith(".json"):
                        count_text_parts.append(f"{item}:0")

            size_text = f"{total_bytes / 1024:.1f}KB" if total_bytes else "0KB"
            count_text = " ".join(count_text_parts)

            rows.append(
                {
                    "item": stage.name,
                    "target": targets_display,
                    "kind": kind,
                    "ratio": stage_ratio,
                    "json_dt": _format_dt(json_dt),
                    "fetch_dt": _format_dt(fetch_dt),
                    "mtime": _format_dt(mtime_dt),
                    "size": size_text,
                    "elapsed": _format_elapsed_short(elapsed_stage),
                    "count": count_text,
                    "_target_path": None,
                    "_refetch_kind": "stage",
                    "_stage_name": stage.name,
                    "_item_name": None,
                }
            )

            # 子行（ファイル/dirの明細）
            for item in stage.required_items:
                p = base_dir / item
                item_meta_ids = _meta_ids_for_item(stage, item)
                elapsed_item = _sum_fetch_meta_elapsed_seconds(item_meta_ids)
                if p.exists() and p.is_file():
                    exists = "✓" if p.stat().st_size > 0 else "△"
                    json_dt_i = _extract_json_datetime(p) if p.suffix.lower() == ".json" else None
                    mtime_i = _mtime_utc(p)
                    size_i = f"{p.stat().st_size / 1024:.1f}KB" if p.exists() else ""
                    rows.append(
                        {
                            "item": f"  - {item}",
                            "target": item,
                            "kind": "一覧" if item.endswith(".json") else "ファイル",
                            "ratio": exists,
                            "json_dt": _format_dt(json_dt_i),
                            "fetch_dt": "",
                            "mtime": _format_dt(mtime_i),
                            "size": size_i,
                            "elapsed": _format_elapsed_short(elapsed_item),
                            "count": "",
                            "_target_path": str(p),
                            "_refetch_kind": "file",
                            "_stage_name": stage.name,
                            "_item_name": item,
                        }
                    )
                else:
                    # dir
                    _size_b, _n, latest = _scan_json_dir(p) if p.exists() and p.is_dir() else (0, 0, None)
                    mtime_i = _mtime_utc(latest) if latest else _mtime_utc(p)
                    json_dt_i = _extract_json_datetime(latest) if latest else None
                    size_b, n = (_size_b, _n) if p.exists() and p.is_dir() else (0, 0)
                    exists = "✓" if n > 0 else "✗"
                    rows.append(
                        {
                            "item": f"  - {item}",
                            "target": item,
                            "kind": "個別"
                            if item
                            in {"datasets", "dataEntry", "samples", "invoiceSchemas", "invoice", "subGroups", "subGroupsAncestors"}
                            else "dir",
                            "ratio": exists,
                            "json_dt": _format_dt(json_dt_i),
                            "fetch_dt": "",
                            "mtime": _format_dt(mtime_i),
                            "size": f"{size_b / 1024:.1f}KB" if size_b else "0KB",
                            "elapsed": _format_elapsed_short(elapsed_item),
                            "count": str(n) if n else "0",
                            "_target_path": str(p),
                            "_refetch_kind": "dir",
                            "_stage_name": stage.name,
                            "_item_name": item,
                        }
                    )

        return rows

    def _apply_status_rows(self, seq: int, rows: list[dict[str, Any]], *, perf_logger, PerfMonitor) -> None:
        # 破棄済み/古い結果は捨てる
        if seq != self._status_update_seq:
            self._status_update_inflight = False
            return

        def _do_apply():
            # UI反映を高速化（大量のsetItem/setCellWidgetの間は更新停止）
            try:
                self.table.setUpdatesEnabled(False)
            except Exception:
                pass
            try:
                self.table.blockSignals(True)
            except Exception:
                pass
            try:
                self.table.setSortingEnabled(False)
            except Exception:
                pass

            try:
                self.table.setRowCount(len(rows))
                for r, row in enumerate(rows):
                    self.table.setRowHeight(r, 24)
                    values = [
                        row.get("item", ""),
                        row.get("target", ""),
                        "",  # 再取得ボタン
                        row.get("kind", ""),
                        row.get("ratio", ""),
                        row.get("json_dt", ""),
                        row.get("fetch_dt", ""),
                        row.get("mtime", ""),
                        row.get("size", ""),
                        row.get("elapsed", ""),
                        row.get("count", ""),
                    ]
                    for c, v in enumerate(values):
                        item = QTableWidgetItem(str(v))
                        if c == 1:
                            target_path = row.get("_target_path")
                            if isinstance(target_path, str) and target_path:
                                item.setData(Qt.UserRole, target_path)
                                font = item.font()
                                font.setUnderline(True)
                                item.setFont(font)
                                item.setToolTip("クリックでファイル/フォルダを開きます")
                        if c in (4, 8, 9, 10):
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        else:
                            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        self.table.setItem(r, c, item)

                    # 再取得ボタン（列=2）
                    try:
                        btn = QPushButton("再取得")
                        btn.setObjectName("basic_info_refetch_button")
                        btn.setMaximumWidth(70)
                        if self._refetch_button_style:
                            btn.setStyleSheet(self._refetch_button_style)
                        btn.clicked.connect(lambda _checked=False, rr=r, meta=row: self._on_refetch_clicked(rr, meta))
                        self.table.setCellWidget(r, 2, btn)
                    except Exception:
                        pass

                # 列幅の自動調整はコストがかかるため初回/手動更新を中心に抑制する
                if not self._columns_sized_once:
                    try:
                        self.table.resizeColumnsToContents()
                    except Exception:
                        pass
                    self._columns_sized_once = True
                try:
                    self.table.horizontalHeader().setStretchLastSection(True)
                except Exception:
                    pass
            finally:
                try:
                    self.table.blockSignals(False)
                except Exception:
                    pass
                try:
                    self.table.setUpdatesEnabled(True)
                except Exception:
                    pass
                try:
                    self.table.viewport().update()
                except Exception:
                    pass

        try:
            if PerfMonitor is not None:
                with PerfMonitor.span("basic_info:status:apply", logger=perf_logger):
                    _do_apply()
            else:
                _do_apply()
        finally:
            self._status_update_inflight = False
            try:
                self.refresh_button.setEnabled(True)
                self._loading_label.clear()
                self._loading_label.setVisible(False)
            except Exception:
                pass
            if self._status_update_pending:
                self._status_update_pending = False
                # 直近の更新要求をもう一度実行
                try:
                    QTimer.singleShot(0, self.update_status)
                except Exception:
                    pass

    # ---- バックグラウンド取得 UI ----

    def connect_background_fetch(self, manager) -> None:
        """BackgroundFetchManager のシグナルを接続し、プログレス表示を開始する。"""
        # 既存接続を切断
        if self._bg_fetch_manager is not None:
            try:
                self._bg_fetch_manager.stage_started.disconnect(self._on_bg_stage_started)
                self._bg_fetch_manager.stage_progress.disconnect(self._on_bg_stage_progress)
                self._bg_fetch_manager.stage_completed.disconnect(self._on_bg_stage_completed)
                self._bg_fetch_manager.all_completed.disconnect(self._on_bg_all_completed)
                self._bg_fetch_manager.fetch_cancelled.disconnect(self._on_bg_cancelled)
            except Exception:
                pass

        self._bg_fetch_manager = manager
        manager.stage_started.connect(self._on_bg_stage_started)
        manager.stage_progress.connect(self._on_bg_stage_progress)
        manager.stage_completed.connect(self._on_bg_stage_completed)
        manager.all_completed.connect(self._on_bg_all_completed)
        manager.fetch_cancelled.connect(self._on_bg_cancelled)

        self._bg_fetch_frame.setVisible(True)
        self._bg_fetch_label.setText("個別データ取得を開始しています...")
        self._bg_fetch_progress.setRange(0, 0)  # indeterminate
        self._bg_fetch_progress.setValue(0)

    def _on_bg_fetch_cancel(self) -> None:
        if self._embedded_worker is not None:
            self._on_embedded_cancel_clicked()
            return
        if self._bg_fetch_manager is not None:
            self._bg_fetch_manager.cancel()
            self._bg_fetch_label.setText("中止しています...")
            self._bg_fetch_cancel_btn.setEnabled(False)

    def _on_bg_stage_started(self, stage_name: str) -> None:
        def _update():
            self._bg_fetch_label.setText(f"取得中: {stage_name}")
            self._bg_fetch_progress.setRange(0, 100)
            self._bg_fetch_progress.setValue(0)
        QTimer.singleShot(0, _update)

    def _on_bg_stage_progress(self, stage_name: str, current: int, total: int, message: str) -> None:
        def _update():
            text = f"{stage_name}: {message}" if message else stage_name
            self._bg_fetch_label.setText(text)
            if total > 0 and not (total == 100 and current <= 100):
                self._bg_fetch_progress.setRange(0, total)
                self._bg_fetch_progress.setValue(min(current, total))
            elif total == 100:
                self._bg_fetch_progress.setRange(0, 100)
                self._bg_fetch_progress.setValue(min(current, 100))
        QTimer.singleShot(0, _update)

    def _on_bg_stage_completed(self, stage_name: str, success: bool, message: str) -> None:
        def _update():
            prefix = "✔" if success else "✖"
            self._bg_fetch_label.setText(f"{prefix} {stage_name}: {message}")
            # 段階完了ごとにステータステーブルも更新
            QTimer.singleShot(500, self.update_status)
        QTimer.singleShot(0, _update)

    def _on_bg_all_completed(self, success: bool, message: str) -> None:
        def _update():
            self._bg_fetch_frame.setVisible(False)
            self._bg_fetch_cancel_btn.setEnabled(True)
            self._bg_fetch_manager = None
            # 最終ステータス更新
            self.update_status()
        QTimer.singleShot(0, _update)

    def _on_bg_cancelled(self) -> None:
        def _update():
            self._bg_fetch_label.setText("個別データ取得: 中止しました")
            self._bg_fetch_cancel_btn.setEnabled(True)
            self._bg_fetch_manager = None
            # 2秒後にバーを隠す
            QTimer.singleShot(2000, lambda: self._bg_fetch_frame.setVisible(False))
            self.update_status()
        QTimer.singleShot(0, _update)

    # ---- 汎用 ProgressWorker 埋め込み実行 ----

    @property
    def is_task_running(self) -> bool:
        """何らかのタスク（BackgroundFetchManager or 埋め込みWorker）が実行中か"""
        if self._bg_fetch_manager is not None:
            return True
        if self._embedded_worker is not None:
            return True
        return False

    def run_worker_embedded(self, worker, task_name: str = "処理中",
                            *, on_finished=None) -> bool:
        """ProgressWorker / SimpleProgressWorker をタブ内プログレスバーで実行する。

        実行中の場合は False を返す（呼び出し側でアラートを出す想定）。

        Args:
            worker: ProgressWorker or SimpleProgressWorker
            task_name: 表示用タスク名
            on_finished: 完了時コールバック (success: bool, message: str) -> None
        Returns:
            True: 正常に開始した / False: 既に実行中のため開始できない
        """
        if self.is_task_running:
            return False

        self._embedded_worker = worker
        self._embedded_task_name = task_name
        self._embedded_on_finished = on_finished

        # UI表示
        self._bg_fetch_frame.setVisible(True)
        self._bg_fetch_label.setText(f"{task_name}を開始しています...")
        self._bg_fetch_progress.setRange(0, 0)  # indeterminate
        self._bg_fetch_progress.setValue(0)
        self._bg_fetch_cancel_btn.setEnabled(True)

        # シグナル接続
        if hasattr(worker, 'progress_detail'):
            try:
                worker.progress_detail.connect(self._on_embedded_progress_detail)
            except Exception:
                worker.progress.connect(self._on_embedded_progress)
        else:
            worker.progress.connect(self._on_embedded_progress)
        worker.finished.connect(self._on_embedded_finished)

        # スレッドで実行
        self._embedded_thread = threading.Thread(target=worker.run, daemon=True)
        self._embedded_thread.start()
        return True

    def _on_embedded_cancel_clicked(self) -> None:
        """埋め込みワーカーのキャンセル処理"""
        if self._embedded_worker is not None:
            self._embedded_worker.cancel()
            self._bg_fetch_label.setText(f"{self._embedded_task_name}: 中止しています...")
            self._bg_fetch_cancel_btn.setEnabled(False)

    def _on_embedded_progress(self, percent: int, message: str) -> None:
        def _update():
            text = f"{self._embedded_task_name}: {message}" if message else self._embedded_task_name
            self._bg_fetch_label.setText(text)
            self._bg_fetch_progress.setRange(0, 100)
            self._bg_fetch_progress.setValue(min(max(int(percent), 0), 100))
        QTimer.singleShot(0, _update)

    def _on_embedded_progress_detail(self, current: int, total: int, message: str) -> None:
        def _update():
            text = f"{self._embedded_task_name}: {message}" if message else self._embedded_task_name
            self._bg_fetch_label.setText(text)
            if total > 0 and not (total == 100 and current <= 100):
                self._bg_fetch_progress.setRange(0, total)
                self._bg_fetch_progress.setValue(min(max(current, 0), total))
            elif total == 100:
                self._bg_fetch_progress.setRange(0, 100)
                self._bg_fetch_progress.setValue(min(max(current, 0), 100))
            else:
                self._bg_fetch_progress.setRange(0, 0)  # indeterminate
        QTimer.singleShot(0, _update)

    def _on_embedded_finished(self, success: bool, message: str) -> None:
        def _update():
            prefix = "✅" if success else "❌"
            self._bg_fetch_label.setText(f"{prefix} {self._embedded_task_name}: {message}")
            self._bg_fetch_progress.setRange(0, 100)
            self._bg_fetch_progress.setValue(100)
            self._bg_fetch_cancel_btn.setEnabled(True)

            # コールバック呼び出し
            cb = self._embedded_on_finished
            self._embedded_worker = None
            self._embedded_thread = None
            self._embedded_on_finished = None

            # 3秒後にバーを隠す
            QTimer.singleShot(3000, lambda: self._hide_frame_if_idle())
            # ステータステーブル更新
            self.update_status()

            if cb is not None:
                try:
                    cb(success, message)
                except Exception:
                    logger.debug("embedded on_finished callback failed", exc_info=True)
        QTimer.singleShot(0, _update)

    def _hide_frame_if_idle(self) -> None:
        """タスクが実行中でなければプログレスフレームを隠す"""
        if not self.is_task_running:
            self._bg_fetch_frame.setVisible(False)

    def _on_refetch_clicked(self, row_index: int, row_meta: dict[str, Any]) -> None:
        if self._controller is None:
            QMessageBox.warning(self, "エラー", "コントローラーが設定されていません")
            return

        stage_name = str(row_meta.get("_stage_name") or "").strip()
        item_name = row_meta.get("_item_name")
        refetch_kind = str(row_meta.get("_refetch_kind") or "").strip()

        # 個別データ段階はバックグラウンドで実行
        _INDIVIDUAL_STAGES = {
            "サンプル情報", "データセット情報", "データエントリ情報",
            "インボイス情報", "invoiceSchema情報",
        }
        if stage_name in _INDIVIDUAL_STAGES:
            self._on_refetch_individual_background(stage_name, refetch_kind)
            return

        # JSON群(dir/stage)は「上書き/欠損のみ」を選べる
        overwrite = True
        chosen_parallel_workers: Optional[int] = None
        if refetch_kind in {"dir", "stage"}:
            from qt_compat.widgets import QInputDialog

            choice, ok = QInputDialog.getItem(
                self,
                "再取得方法",
                "再取得方法を選択してください",
                ["上書き再取得", "欠損のみ取得"],
                0,
                False,
            )
            if not ok:
                return
            overwrite = choice == "上書き再取得"

            # 併せて並列数も指定（この段階の実行にのみ反映）
            default_workers = 10
            try:
                spin = getattr(self._controller, 'basic_parallel_download_spinbox', None)
                if spin is not None and hasattr(spin, 'value'):
                    default_workers = int(spin.value())
            except Exception:
                default_workers = 10

            # NOTE: PySide6 の getInt は min/max をキーワードで受けないため位置引数で渡す
            workers, ok_workers = QInputDialog.getInt(
                self,
                "並列数",
                "並列処理数を指定してください（再取得のこの実行にのみ反映）",
                max(1, int(default_workers)),
                1,
                50,
                1,
            )
            if not ok_workers:
                return
            chosen_parallel_workers = int(workers)

        try:
            from classes.utils.progress_worker import ProgressWorker
            from core.bearer_token_manager import BearerTokenManager

            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self._controller.parent)
            if not bearer_token:
                QMessageBox.warning(self, "認証エラー", "認証トークンが取得できません。ログインしてください。")
                return

            webview = getattr(self._controller.parent, 'webview', self._controller.parent)
            parallel_workers = chosen_parallel_workers
            if parallel_workers is None:
                try:
                    spin = getattr(self._controller, 'basic_parallel_download_spinbox', None)
                    if spin is not None and hasattr(spin, 'value'):
                        parallel_workers = int(spin.value())
                except Exception:
                    parallel_workers = None

            worker = ProgressWorker(
                task_func=self._refetch_task,
                task_kwargs={
                    'bearer_token': bearer_token,
                    'webview': webview,
                    'stage_name': stage_name,
                    'item_name': item_name,
                    'refetch_kind': refetch_kind,
                    'overwrite': overwrite,
                    'parallel_max_workers': parallel_workers,
                },
                task_name="再取得",
            )

            if not self.run_worker_embedded(worker, f"再取得: {stage_name}"):
                QMessageBox.information(
                    self, "処理中",
                    "現在別の取得処理が実行中です。\n完了または中止してから再度お試しください。",
                )
                return
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"再取得開始に失敗しました:\n{e}")

    def _on_refetch_individual_background(self, stage_name: str, refetch_kind: str) -> None:
        """個別データ段階の再取得をバックグラウンドで実行する。"""
        from qt_compat.widgets import QInputDialog
        from core.bearer_token_manager import BearerTokenManager
        from classes.basic.core.background_fetch_manager import BackgroundFetchManager

        # 上書き/欠損のみ選択
        overwrite = True
        if refetch_kind in {"dir", "stage"}:
            choice, ok = QInputDialog.getItem(
                self,
                "再取得方法",
                "再取得方法を選択してください",
                ["上書き再取得", "欠損のみ取得"],
                0,
                False,
            )
            if not ok:
                return
            overwrite = choice == "上書き再取得"

        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(
            self._controller.parent if self._controller else None
        )
        if not bearer_token:
            QMessageBox.warning(self, "認証エラー", "認証トークンが取得できません。ログインしてください。")
            return

        # 並列数
        parallel_workers = 10
        try:
            spin = getattr(self._controller, 'basic_parallel_download_spinbox', None)
            if spin is not None and hasattr(spin, 'value'):
                parallel_workers = int(spin.value())
        except Exception:
            pass

        mgr = BackgroundFetchManager.instance()
        if self.is_task_running or mgr.is_running:
            QMessageBox.information(self, "処理中", "現在別の取得処理が実行中です。\n完了または中止してから再度お試しください。")
            return

        # 単一段階のみ実行するために BackgroundFetchManager を使う
        # 検索条件は controller から取得（あれば）
        search_state = getattr(self._controller, '_basic_info_search_state', None) if self._controller else None
        on_self = False
        search_words = None
        search_words_batch = None
        if search_state is not None:
            on_self = True
            search_words = getattr(search_state, 'manual_keyword', None) or None
            search_words_batch = getattr(search_state, 'keyword_batch', None) or None

        self.connect_background_fetch(mgr)
        mgr.start(
            bearer_token,
            force_download=overwrite,
            parallel_workers=parallel_workers,
            on_self=on_self,
            search_words=search_words,
            search_words_batch=search_words_batch,
            stages_filter=[stage_name],
        )

    def _refetch_task(
        self,
        bearer_token: str,
        webview,
        stage_name: str,
        item_name: Optional[str],
        refetch_kind: str,
        overwrite: bool,
        parallel_max_workers: Optional[int] = None,
        progress_callback=None,
    ) -> str:
        import shutil
        import time

        from classes.basic.core.common_info_selection_logic import save_fetch_meta

        def _rm_path(p: str) -> None:
            try:
                if os.path.isfile(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass

        # fetch_meta target_id の決定
        meta_id = None
        if item_name:
            # item単位
            mapping = {
                "self.json": "self",
                "group.json": "group_pipeline",
                "groupDetail.json": "group_pipeline",
                "subGroup.json": "group_pipeline",
                "organization.json": "organization",
                "instrumentType.json": "instrument_type",
                "samples": "samples",
                "dataset.json": "dataset_list",
                "datasets": "dataset_details",
                "dataEntry": "data_entry",
                "invoice": "invoice",
                "invoiceSchemas": "invoiceSchemas",
                "template.json": "template",
                "instruments.json": "instruments",
                "licenses.json": "licenses",
                "info.json": "info_generate",
            }
            meta_id = mapping.get(str(item_name))
        else:
            # stage単位
            stage_map = {
                "ユーザー情報": "self",
                "グループ関連情報": "group_pipeline",
                "組織・装置情報": "organization",
                "サンプル情報": "samples",
                "データセット情報": "dataset_details",
                "データエントリ情報": "data_entry",
                "インボイス情報": "invoice",
                "invoiceSchema情報": "invoiceSchemas",
                "テンプレート・設備情報": "template",
                "テンプレート・設備・ライセンス情報": "template",
                "統合情報生成": "info_generate",
            }
            meta_id = stage_map.get(stage_name)

        base_dir = get_dynamic_file_path("output/rde/data")
        item_path = None
        if item_name:
            item_path = os.path.join(base_dir, str(item_name))

        if overwrite and item_path:
            _rm_path(item_path)
        elif overwrite and stage_name:
            # stageの代表ファイル/dirを削除（ざっくり）
            stage_delete_map = {
                "ユーザー情報": ["self.json"],
                "グループ関連情報": ["group.json", "groupDetail.json", "subGroup.json"],
                "組織・装置情報": ["organization.json", "instrumentType.json"],
                "サンプル情報": ["samples"],
                "データセット情報": ["dataset.json", "datasets"],
                "データエントリ情報": ["dataEntry"],
                "インボイス情報": ["invoice"],
                "invoiceSchema情報": ["invoiceSchemas"],
                "テンプレート・設備情報": ["template.json", "instruments.json"],
                "テンプレート・設備・ライセンス情報": ["template.json", "instruments.json", "licenses.json"],
                "統合情報生成": ["info.json"],
            }
            for rel in stage_delete_map.get(stage_name, []):
                _rm_path(os.path.join(base_dir, rel))

        if progress_callback:
            if not progress_callback(1, 100, f"再取得開始: {stage_name} {item_name or ''}"):
                return "キャンセルされました"

        from classes.basic.core import basic_info_logic

        t0 = time.perf_counter()

        # item指定がある場合はその item を含む段階を実行（簡易実装）
        # 基本は stage を使う
        if not stage_name:
            raise ValueError("stage_name が空です")

        # データセット情報だけは検索条件をcontroller側で保持しているが、ここでは全取得相当
        if stage_name == "データセット情報":
            result = basic_info_logic.fetch_dataset_info_stage(
                bearer_token,
                onlySelf=False,
                searchWords=None,
                searchWordsBatch=None,
                progress_callback=progress_callback,
                max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
            )
        elif stage_name == "統合情報生成":
            result = basic_info_logic.finalize_basic_info_stage(webview=webview, progress_callback=progress_callback)
        elif stage_name == "グループ関連情報":
            result = basic_info_logic.fetch_group_info_stage(
                bearer_token,
                progress_callback=progress_callback,
                program_id=None,
                parent_widget=self._controller.parent if self._controller is not None else None,
                force_program_dialog=False,
                force_download=overwrite,
                max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
            )
        elif stage_name == "ユーザー情報":
            result = basic_info_logic.fetch_user_info_stage(
                bearer_token,
                progress_callback=progress_callback,
                parent_widget=self._controller.parent if self._controller is not None else None,
            )
        elif stage_name == "組織・装置情報":
            result = basic_info_logic.fetch_organization_stage(bearer_token, progress_callback=progress_callback)
        elif stage_name == "サンプル情報":
            if overwrite:
                result = basic_info_logic.fetch_sample_info_only(
                    bearer_token,
                    output_dir=base_dir,
                    progress_callback=progress_callback,
                    max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
                )
            else:
                result = basic_info_logic.fetch_sample_info_stage(
                    bearer_token,
                    progress_callback=progress_callback,
                    max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
                )
        elif stage_name == "データエントリ情報":
            result = basic_info_logic.fetch_data_entry_stage(
                bearer_token,
                progress_callback=progress_callback,
                max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
            )
        elif stage_name == "インボイス情報":
            result = basic_info_logic.fetch_invoice_stage(
                bearer_token,
                progress_callback=progress_callback,
                max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
            )
        elif stage_name == "invoiceSchema情報":
            result = basic_info_logic.fetch_invoice_schema_stage(
                bearer_token,
                progress_callback=progress_callback,
                max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
            )
        elif stage_name in {"テンプレート・設備情報", "テンプレート・設備・ライセンス情報"}:
            result = basic_info_logic.fetch_template_instrument_stage(
                bearer_token,
                progress_callback=progress_callback,
                max_workers=int(parallel_max_workers) if parallel_max_workers else 10,
            )
        else:
            # 未対応は execute_individual_stage にフォールバック
            result = basic_info_logic.execute_individual_stage(
                stage_name,
                bearer_token,
                webview=webview,
                progress_callback=progress_callback,
                parallel_max_workers=int(parallel_max_workers) if parallel_max_workers else None,
            )

        elapsed = time.perf_counter() - t0
        if meta_id:
            try:
                save_fetch_meta(meta_id, elapsed_seconds=elapsed)
            except Exception:
                pass

        return result

    def _on_table_cell_clicked(self, row: int, column: int) -> None:
        # 「対象」列のみクリックで開く
        if column != 1:
            return

        try:
            cell = self.table.item(row, column)
            if cell is None:
                return
            target_path = cell.data(Qt.UserRole)
            if not isinstance(target_path, str) or not target_path:
                return

            if not os.path.exists(target_path):
                QMessageBox.warning(self, "ファイルがありません", f"対象が存在しません:\n{target_path}")
                return

            from classes.core.platform import open_path

            if not open_path(target_path):
                raise RuntimeError("open_path failed")
        except Exception as e:
            QMessageBox.warning(self, "開けません", f"対象を開けませんでした:\n{e}")

    def _show_api_debug(self) -> None:
        try:
            from .api_history_dialog import APIAccessHistoryDialog
            from net.api_call_recorder import get_global_recorder

            recorder = get_global_recorder()
            if not recorder.get_records():
                from qt_compat.widgets import QMessageBox

                QMessageBox.information(
                    self,
                    "APIアクセス履歴",
                    "まだAPIアクセス記録がありません。\n\n基本情報取得などを実行すると、\nAPIアクセス履歴が記録されます。",
                )
                return

            dialog = APIAccessHistoryDialog(recorder=recorder, parent=self)
            dialog.exec()
        except Exception as e:
            logger.error("show_api_debug error: %s", e)
            try:
                from qt_compat.widgets import QMessageBox

                QMessageBox.critical(self, "エラー", f"APIデバッグ機能でエラーが発生しました:\n{e}")
            except Exception:
                pass
