"""データ取得2: 一括取得（DP）タブ"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from typing import Any

from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QCompleter,
    QMenu,
    QProgressBar,
)
from qt_compat.core import Qt, QUrl, QThread, Signal
from qt_compat.gui import QDesktopServices

from config.common import get_dynamic_file_path
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color
from classes.utils.button_styles import get_button_style
from classes.utils.data_portal_public import search_public_arim_data, fetch_public_arim_data_details
from classes.core.rde_search_index import ensure_rde_search_index, search_dataset_ids
from classes.data_portal.util.public_output_paths import get_public_data_portal_root_dir
from classes.data_fetch2.util.parallel_search import resolve_parallel_workers, suggest_parallel_workers, parallel_filter


logger = logging.getLogger(__name__)


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _contains(value: str, needle: str) -> bool:
    if not needle:
        return True
    return needle.casefold() in (value or "").casefold()


def _load_json(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_data_items(path: str) -> list[dict]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def _first_non_empty(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            text = _first_non_empty(item)
            if text:
                return text
    if isinstance(value, dict):
        for item in value.values():
            text = _first_non_empty(item)
            if text:
                return text
    return ""


def _join_non_empty(parts: list[str], sep: str = ", ") -> str:
    return sep.join([x for x in [str(p).strip() for p in parts] if x])


def _looks_like_uuid(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    value = value.lower()
    if len(value) == 36 and value.count("-") == 4:
        parts = value.split("-")
        if [len(p) for p in parts] == [8, 4, 4, 4, 12]:
            hex_chars = set("0123456789abcdef")
            return all(all(ch in hex_chars for ch in p) for p in parts)
    return False


def _collect_tags(dataset_obj: dict) -> str:
    attrs = dataset_obj.get("attributes", {}) if isinstance(dataset_obj, dict) else {}
    tags = attrs.get("tags") or attrs.get("tag") or []
    if isinstance(tags, str):
        return tags.strip()
    if not isinstance(tags, list):
        return ""
    out: list[str] = []
    for t in tags:
        if isinstance(t, dict):
            out.append(str(t.get("name") or t.get("label") or "").strip())
        else:
            out.append(str(t).strip())
    return _join_non_empty(out)


def _collect_related_dataset_ids(dataset_obj: dict) -> str:
    relationships = dataset_obj.get("relationships", {}) if isinstance(dataset_obj, dict) else {}
    rel = relationships.get("relatedDatasets", {}) if isinstance(relationships, dict) else {}
    data = rel.get("data", []) if isinstance(rel, dict) else []
    if isinstance(data, dict):
        data = [data]
    out: list[str] = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict):
            rid = str(item.get("id") or "").strip()
            if rid:
                out.append(rid)
    return _join_non_empty(sorted(set(out)))


def _load_public_output_registrant_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for env in ("production", "test"):
        try:
            output_path = get_public_data_portal_root_dir(env) / "output.json"
        except Exception:
            continue
        if not output_path.exists():
            continue
        payload = _load_json(str(output_path))
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            fields_raw = item.get("fields_raw") if isinstance(item.get("fields_raw"), dict) else {}
            dataset_id = _to_text(fields.get("dataset_id") or fields_raw.get("dataset_id") or item.get("dataset_id")).strip()
            registrant = _to_text(
                fields.get("dataset_registrant")
                or fields.get("registrant")
                or fields_raw.get("dataset_registrant")
                or fields_raw.get("registrant")
            ).strip()
            if dataset_id and registrant and dataset_id not in result:
                result[dataset_id] = registrant
    return result


def _normalize_public_payload_to_records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("items") or payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _record_dataset_id(record: dict) -> str:
    if not isinstance(record, dict):
        return ""
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    fields_raw = record.get("fields_raw") if isinstance(record.get("fields_raw"), dict) else {}
    dataset_id = _to_text(fields_raw.get("dataset_id") or fields.get("dataset_id") or record.get("dataset_id")).strip()
    if dataset_id:
        return dataset_id
    return _to_text(record.get("id") or "").strip()


def _public_field(record: dict, *keys: str) -> str:
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    fields_raw = record.get("fields_raw") if isinstance(record.get("fields_raw"), dict) else {}
    for key in keys:
        value = _to_text(fields_raw.get(key) or fields.get(key) or record.get(key)).strip()
        if value:
            return value
    return ""


def _public_content_url(record: dict) -> str:
    links = record.get("download_links")
    if isinstance(links, list):
        for link in links:
            text = _to_text(link).strip()
            if text and "mode=free" in text:
                return text
        for link in links:
            text = _to_text(link).strip()
            if text:
                return text
    return ""


def _record_matches_keyword(record: dict, keyword: str) -> bool:
    needle = _to_text(keyword).strip()
    if not needle:
        return True
    haystacks = [
        _to_text(record.get("title")),
        _record_dataset_id(record),
        _public_field(record, "project_number"),
        _public_field(record, "dataset_registrant"),
        _public_field(record, "organization"),
        _public_field(record, "dataset_template"),
        _public_field(record, "keyword_tags"),
    ]
    return any(_contains(h, needle) for h in haystacks)


def _build_record_from_public_record(record: dict) -> dict:
    dataset_id = _record_dataset_id(record)
    detail_url = _to_text(record.get("detail_url") or record.get("url")).strip()
    return {
        "title": _to_text(record.get("title")).strip(),
        "project_number": _public_field(record, "project_number"),
        "subgroup": _public_field(record, "subgroup", "sub_group"),
        "subgroup_id": _public_field(record, "subgroup_id", "group_id"),
        "registrant": _public_field(record, "dataset_registrant", "registrant"),
        "organization": _public_field(record, "organization"),
        "dataset_id": dataset_id,
        "template": _public_field(record, "dataset_template", "template", "template_id"),
        "sample_name": _public_field(record, "sample_name"),
        "sample_uuid": _public_field(record, "sample_uuid"),
        "equipment_name": _public_field(record, "equipment_name"),
        "equipment_local_id": _public_field(record, "equipment_local_id"),
        "tags": _public_field(record, "keyword_tags", "tags"),
        "related_datasets": _public_field(record, "related_datasets"),
        "related_datasets_display": "",
        "detail_url": detail_url,
        "content_url": _public_content_url(record),
    }


def _load_public_output_records(environment: str) -> tuple[list[dict], bool]:
    try:
        output_path = get_public_data_portal_root_dir(environment) / "output.json"
    except Exception:
        return [], False
    if not output_path.exists():
        return [], False
    payload = _load_json(str(output_path))
    return _normalize_public_payload_to_records(payload), True


class _BulkDpSearchThread(QThread):
    finished_fetch = Signal(object, str)

    def __init__(
        self,
        keyword: str,
        environment: str,
        candidate_dataset_ids: set[str] | None,
        use_details: bool,
        detail_workers: int,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._keyword = str(keyword or "")
        self._environment = str(environment or "production")
        self._candidate_dataset_ids = set(candidate_dataset_ids) if isinstance(candidate_dataset_ids, set) else None
        self._use_details = bool(use_details)
        self._detail_workers = max(1, int(detail_workers or 1))
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def _is_cancelled(self) -> bool:
        return bool(self._cancel_requested)

    def run(self):
        try:
            started = time.perf_counter()
            if self._is_cancelled():
                self.finished_fetch.emit([], "__CANCELLED__")
                return

            # まずローカルのpublic output.jsonを利用（不要なDPアクセスを避ける）
            local_records_raw, local_source_exists = _load_public_output_records(self._environment)
            local_filter_started = time.perf_counter()
            if local_records_raw:
                if self._candidate_dataset_ids is not None:
                    local_records_raw = [
                        rec for rec in local_records_raw
                        if _record_dataset_id(rec) in self._candidate_dataset_ids
                    ]
                if self._keyword:
                    local_records_raw = [rec for rec in local_records_raw if _record_matches_keyword(rec, self._keyword)]

            if local_source_exists:
                local_filter_sec = max(0.0, time.perf_counter() - local_filter_started)
                records = [_build_record_from_public_record(rec) for rec in local_records_raw]
                self.finished_fetch.emit(
                    {
                        "records": records,
                        "_meta": {
                            "link_fetch_sec": 0.0,
                            "detail_fetch_sec": 0.0,
                            "local_filter_sec": local_filter_sec,
                            "workers": self._detail_workers,
                            "source": "local_output",
                        },
                    },
                    "",
                )
                return

            try:
                links = search_public_arim_data(
                    keyword=self._keyword,
                    environment=self._environment,
                    page_max_workers=self._detail_workers,
                )
            except TypeError:
                links = search_public_arim_data(keyword=self._keyword, environment=self._environment)
            link_fetch_sec = max(0.0, time.perf_counter() - started)
            if self._is_cancelled():
                self.finished_fetch.emit([], "__CANCELLED__")
                return
            if self._candidate_dataset_ids is not None:
                filtered_links = [
                    link
                    for link in links
                    if str(getattr(link, "code", "") or "").strip() in self._candidate_dataset_ids
                ]
                if filtered_links:
                    links = filtered_links

            can_build_from_links = True
            for link in links:
                code = str(getattr(link, "code", "") or "").strip()
                url = str(getattr(link, "url", "") or "").strip()
                if not code or not url:
                    can_build_from_links = False
                    break

            if self._use_details or not can_build_from_links:
                details_started = time.perf_counter()
                details = fetch_public_arim_data_details(
                    links,
                    environment=self._environment,
                    max_workers=self._detail_workers,
                    cache_enabled=True,
                )
                detail_fetch_sec = max(0.0, time.perf_counter() - details_started)
                if self._is_cancelled():
                    self.finished_fetch.emit([], "__CANCELLED__")
                    return
                self.finished_fetch.emit(
                    {
                        "details": details,
                        "_meta": {
                            "link_fetch_sec": link_fetch_sec,
                            "detail_fetch_sec": detail_fetch_sec,
                            "local_filter_sec": 0.0,
                            "workers": self._detail_workers,
                            "source": "remote_detail",
                        },
                    },
                    "",
                )
            else:
                self.finished_fetch.emit(
                    {
                        "links": links,
                        "_meta": {
                            "link_fetch_sec": link_fetch_sec,
                            "detail_fetch_sec": 0.0,
                            "local_filter_sec": 0.0,
                            "workers": self._detail_workers,
                            "source": "remote_links",
                        },
                    },
                    "",
                )
        except Exception as exc:
            self.finished_fetch.emit([], str(exc))


class DataFetch2BulkDpTab(QWidget):
    PAGE_SIZE_OPTIONS = [50, 100, 200, 500, 1000, 2000, 5000, 10000]

    COLUMNS = [
        "タイトル",
        "課題番号",
        "サブグループ",
        "登録者",
        "データセットID",
        "データセットテンプレート",
        "試料(表示名)",
        "試料(UUID)",
        "装置名",
        "装置(ローカルID)",
        "タグ",
        "関連データセット",
        "詳細ページURL",
        "コンテンツURL(mode=free)",
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._all_records: list[dict] = []
        self._records: list[dict] = []
        self._current_page = 1
        self._record_exact_indexes: dict[str, dict[str, set[int]]] = {}
        self._rde_index_payload: dict[str, Any] | None = None
        self._dataset_inference_map: dict[str, dict[str, str]] = {}
        self._dataset_inference_by_title: dict[str, dict[str, str]] = {}
        self._dataset_name_by_id: dict[str, str] = {}
        self._dataset_grant_by_id: dict[str, str] = {}
        self._dataset_uuid_by_title: dict[str, str] = {}
        self._subgroup_name_by_id: dict[str, str] = {}
        self._sample_name_by_id: dict[str, str] = {}
        self._entry_enrichment_cache: dict[str, dict[str, str]] = {}
        self._search_thread: _BulkDpSearchThread | None = None
        self._compact_rows_mode = False
        self._search_started_at: float | None = None
        self._cancel_requested = False
        self._build_ui()
        self._bootstrap_filter_candidates()

    def _elapsed_search_seconds(self) -> float:
        if self._search_started_at is None:
            return 0.0
        return max(0.0, time.perf_counter() - self._search_started_at)

    def _format_elapsed(self) -> str:
        return f"{self._elapsed_search_seconds():.2f}秒"

    def _default_search_workers(self) -> int:
        return suggest_parallel_workers()

    def _effective_search_workers(self) -> int:
        value = self.search_workers_combo.currentData()
        return resolve_parallel_workers(int(value or 0))

    def _effective_page_size(self) -> int | None:
        value = self.page_size_combo.currentData()
        if value is None:
            return None
        try:
            parsed = int(value)
        except Exception:
            return 500
        if parsed <= 0:
            return None
        return parsed

    def _total_pages(self) -> int:
        if not self._records:
            return 1
        page_size = self._effective_page_size()
        if page_size is None:
            return 1
        return max(1, (len(self._records) + page_size - 1) // page_size)

    def _current_page_records(self) -> list[dict]:
        if not self._records:
            return []
        page_size = self._effective_page_size()
        if page_size is None:
            return self._records
        total_pages = self._total_pages()
        self._current_page = max(1, min(self._current_page, total_pages))
        start = (self._current_page - 1) * page_size
        end = start + page_size
        return self._records[start:end]

    def _create_filter_combo(self, placeholder: str, object_name: str) -> QComboBox:
        combo = QComboBox(self)
        combo.setObjectName(object_name)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        combo.addItem("")
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)
        return combo

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("一括取得（DP）")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        root.addWidget(title)

        desc = QLabel(
            "データポータルの検索結果を一覧化し、詳細ページリンクとコンテンツリンク(mode=free)を表示します。"
            "\nDPは直接ダウンロード不可のため、リンク先を開いて取得してください。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        root.addWidget(desc)

        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("環境:"))
        self.env_combo = QComboBox(self)
        self.env_combo.addItem("production", "production")
        self.env_combo.addItem("test", "test")
        env_row.addWidget(self.env_combo)
        env_row.addStretch()
        root.addLayout(env_row)

        filters_layout = QVBoxLayout()
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(6)

        self.f_keyword = QLineEdit(self)
        self.f_project_number = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpGrantCombo")
        self.f_subgroup = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpSubgroupCombo")
        self.f_registrant = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpRegistrantCombo")
        self.f_org = QLineEdit(self)
        self.f_template = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpTemplateCombo")
        self.f_sample_name = QLineEdit(self)
        self.f_sample_uuid = QLineEdit(self)
        self.f_equip_name = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpEquipmentNameCombo")
        self.f_equip_local = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpEquipmentLocalCombo")
        self.f_tags = QLineEdit(self)
        self.f_related = self._create_filter_combo("候補から選択（部分一致可）", "bulkDpRelatedCombo")

        fields = [
            ("キーワード", self.f_keyword),
            ("課題番号", self.f_project_number),
            ("サブグループ", self.f_subgroup),
            ("登録者", self.f_registrant),
            ("登録者所属", self.f_org),
            ("データセットテンプレート", self.f_template),
            ("試料（表示名）", self.f_sample_name),
            ("試料（UUID）", self.f_sample_uuid),
            ("装置名", self.f_equip_name),
            ("装置（ローカルID）", self.f_equip_local),
            ("タグ", self.f_tags),
            ("関連データセット", self.f_related),
        ]
        for label, editor in fields:
            row = QHBoxLayout()
            row_label = QLabel(label)
            row_label.setMinimumWidth(140)
            row.addWidget(row_label)
            if isinstance(editor, QLineEdit):
                editor.setPlaceholderText("部分一致")
            row.addWidget(editor, 1)
            filters_layout.addLayout(row)
        root.addLayout(filters_layout)

        op_row = QHBoxLayout()
        self.search_btn = QPushButton("検索して一覧化")
        self.open_detail_btn = QPushButton("選択行の詳細ページを開く")
        self.open_content_btn = QPushButton("選択行のコンテンツリンクを開く")
        export_menu = QMenu(self)
        export_csv = export_menu.addAction("CSV出力")
        export_csv.triggered.connect(lambda: self._export("csv"))
        self.export_btn = QPushButton("エクスポート")
        self.export_btn.setMenu(export_menu)
        self.compact_rows_btn = QPushButton("1行表示")
        self.cancel_btn = QPushButton("検索キャンセル")
        self.cancel_btn.setEnabled(False)
        self.search_workers_combo = QComboBox(self)
        self.search_workers_combo.setObjectName("bulkDpSearchWorkersCombo")
        self.search_workers_combo.addItem("検索並列数: 自動", 0)
        for value in [1, 2, 4, 8, 12, 16]:
            self.search_workers_combo.addItem(f"検索並列数: {value}", value)
        default_workers = self._default_search_workers()
        worker_index = self.search_workers_combo.findData(default_workers)
        self.search_workers_combo.setCurrentIndex(worker_index if worker_index >= 0 else 0)
        op_row.addWidget(self.search_btn)
        op_row.addWidget(self.open_detail_btn)
        op_row.addWidget(self.open_content_btn)
        op_row.addWidget(self.export_btn)
        op_row.addWidget(self.compact_rows_btn)
        op_row.addWidget(self.cancel_btn)
        op_row.addWidget(self.search_workers_combo)
        op_row.addStretch()
        root.addLayout(op_row)

        self.search_btn.setStyleSheet(get_button_style("primary"))
        self.open_detail_btn.setStyleSheet(get_button_style("info"))
        self.open_content_btn.setStyleSheet(get_button_style("info"))
        self.export_btn.setStyleSheet(get_button_style("success"))
        self.compact_rows_btn.setStyleSheet(get_button_style("info"))
        self.cancel_btn.setStyleSheet(get_button_style("warning"))

        self.status = QLabel("待機中")
        root.addWidget(self.status)

        self.search_spinner = QProgressBar(self)
        self.search_spinner.setRange(0, 0)
        self.search_spinner.setVisible(False)
        root.addWidget(self.search_spinner)

        paging_row = QHBoxLayout()
        paging_row.addWidget(QLabel("表示件数:"))
        self.page_size_combo = QComboBox(self)
        self.page_size_combo.setObjectName("bulkDpPageSizeCombo")
        for size in self.PAGE_SIZE_OPTIONS:
            self.page_size_combo.addItem(str(size), size)
        self.page_size_combo.addItem("全件", None)
        self.page_size_combo.setCurrentText("500")
        paging_row.addWidget(self.page_size_combo)
        self.page_prev_btn = QPushButton("前へ")
        self.page_next_btn = QPushButton("次へ")
        self.page_info_label = QLabel("ページ 1/1")
        paging_row.addWidget(self.page_prev_btn)
        paging_row.addWidget(self.page_next_btn)
        paging_row.addWidget(self.page_info_label)
        paging_row.addStretch()
        root.addLayout(paging_row)

        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(int(self.table.fontMetrics().height() * 1.8))
        root.addWidget(self.table, 1)

        self.search_btn.clicked.connect(self._on_search_button_clicked)
        self.open_detail_btn.clicked.connect(lambda: self._open_selected_url("detail_url"))
        self.open_content_btn.clicked.connect(lambda: self._open_selected_url("content_url"))
        self.compact_rows_btn.clicked.connect(self._toggle_row_height_mode)
        self.cancel_btn.clicked.connect(self._cancel_search)
        self.page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        self.page_prev_btn.clicked.connect(lambda: self._move_page(-1))
        self.page_next_btn.clicked.connect(lambda: self._move_page(1))
        self._update_pagination_controls()

    def _on_page_size_changed(self):
        self._current_page = 1
        self._render_page()

    def _move_page(self, delta: int):
        total_pages = self._total_pages()
        self._current_page = max(1, min(self._current_page + int(delta), total_pages))
        self._render_page()

    def _update_pagination_controls(self):
        total_pages = self._total_pages()
        self._current_page = max(1, min(self._current_page, total_pages))
        page_size = self._effective_page_size()
        if page_size is None:
            self.page_info_label.setText(f"ページ 1/1 ({len(self._records)}件)")
        else:
            self.page_info_label.setText(f"ページ {self._current_page}/{total_pages} ({len(self._records)}件)")
        self.page_prev_btn.setEnabled(total_pages > 1 and self._current_page > 1)
        self.page_next_btn.setEnabled(total_pages > 1 and self._current_page < total_pages)

    def _on_search_button_clicked(self):
        logger.debug("bulk_dp: search button clicked")
        self.search_and_build()

    def _set_search_busy(self, busy: bool):
        logger.debug("bulk_dp: set search busy=%s", busy)
        self.search_spinner.setVisible(busy)
        self.search_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.open_detail_btn.setEnabled(not busy)
        self.open_content_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy)
        self.compact_rows_btn.setEnabled(not busy)
        self.search_workers_combo.setEnabled(not busy)
        self.page_size_combo.setEnabled(not busy)
        if busy:
            self.page_prev_btn.setEnabled(False)
            self.page_next_btn.setEnabled(False)
        else:
            self._update_pagination_controls()

    def _cancel_search(self):
        if self._search_thread is None or not self._search_thread.isRunning():
            return
        self._cancel_requested = True
        self._search_thread.request_cancel()
        self.status.setText(f"キャンセル要求を送信中... ({self._format_elapsed()})")

    def _log_record_quality(self, records: list[dict]):
        if not records:
            logger.debug("bulk_dp: record quality no records")
            return
        subgroup_empty = sum(1 for r in records if not _to_text(r.get("subgroup")).strip())
        registrant_empty = sum(1 for r in records if not _to_text(r.get("registrant")).strip())
        sample_name_empty = sum(1 for r in records if not _to_text(r.get("sample_name")).strip())
        logger.debug(
            "bulk_dp: record quality total=%s subgroup_empty=%s registrant_empty=%s sample_name_empty=%s",
            len(records),
            subgroup_empty,
            registrant_empty,
            sample_name_empty,
        )

    def _build_records_from_links(self, links: list[Any]) -> list[dict]:
        records: list[dict] = []
        for link in links:
            dataset_id = _to_text(getattr(link, "code", "")).strip()
            detail_url = _to_text(getattr(link, "url", "")).strip()
            record = {
                "title": _to_text(getattr(link, "title", "")).strip(),
                "project_number": "",
                "subgroup": "",
                "subgroup_id": "",
                "registrant": "",
                "organization": "",
                "dataset_id": dataset_id,
                "template": "",
                "sample_name": "",
                "sample_uuid": "",
                "equipment_name": "",
                "equipment_local_id": "",
                "tags": "",
                "related_datasets": "",
                "related_datasets_display": "",
                "detail_url": detail_url,
                "content_url": "",
            }
            records.append(self._enrich_record(record))
        return records

    def _bootstrap_filter_candidates(self):
        try:
            self._rde_index_payload = ensure_rde_search_index(force_rebuild=False)
        except Exception:
            self._rde_index_payload = None

        try:
            self._dataset_inference_map, self._dataset_inference_by_title = self._load_dataset_inference_map()
        except Exception:
            self._dataset_inference_map = {}
            self._dataset_inference_by_title = {}

        self._dataset_name_by_id = {
            str(dataset_id): _to_text(info.get("dataset_name")).strip()
            for dataset_id, info in self._dataset_inference_map.items()
            if isinstance(info, dict)
        }
        self._dataset_grant_by_id = {
            str(dataset_id): _to_text(info.get("project_number")).strip()
            for dataset_id, info in self._dataset_inference_map.items()
            if isinstance(info, dict)
        }
        self._dataset_uuid_by_title = {
            _to_text(info.get("dataset_name")).strip().casefold(): str(dataset_id)
            for dataset_id, info in self._dataset_inference_map.items()
            if isinstance(info, dict) and _to_text(info.get("dataset_name")).strip()
        }
        self._subgroup_name_by_id = {
            _to_text(info.get("subgroup_id")).strip(): _to_text(info.get("subgroup")).strip()
            for info in self._dataset_inference_map.values()
            if isinstance(info, dict)
            and _to_text(info.get("subgroup_id")).strip()
            and _to_text(info.get("subgroup")).strip()
        }
        self._sample_name_by_id = {
            _to_text(info.get("sample_uuid")).strip(): _to_text(info.get("sample_name")).strip()
            for info in self._dataset_inference_map.values()
            if isinstance(info, dict)
            and _to_text(info.get("sample_uuid")).strip()
            and _to_text(info.get("sample_name")).strip()
        }

        self._update_filter_options([])

    def _resolve_subgroup_label(self, subgroup: str, subgroup_id: str) -> str:
        text = _to_text(subgroup).strip()
        sid = _to_text(subgroup_id).strip()
        if not text and sid:
            text = _to_text(self._subgroup_name_by_id.get(sid)).strip()
        if text and sid and sid not in text:
            return _join_non_empty([text, sid], sep=" | ")
        return text or sid

    def _resolve_related_label(self, dataset_id: str) -> str:
        rid = _to_text(dataset_id).strip()
        if not rid:
            return ""
        grant = _to_text(self._dataset_grant_by_id.get(rid)).strip()
        dataset_name = _to_text(self._dataset_name_by_id.get(rid)).strip()
        label = _join_non_empty([grant, dataset_name], sep=" | ")
        return label or rid

    def _combo_match_value(self, combo: QComboBox) -> str:
        text = combo.currentText().strip()
        if not text:
            return ""
        idx = combo.currentIndex()
        if idx >= 0 and combo.itemText(idx).strip() == text:
            user_value = combo.itemData(idx, Qt.UserRole)
            if isinstance(user_value, str) and user_value.strip():
                return user_value.strip()
        return text

    def _combo_selected_user_value(self, combo: QComboBox) -> str:
        text = combo.currentText().strip()
        if not text:
            return ""
        idx = combo.currentIndex()
        if idx < 0:
            return ""
        if combo.itemText(idx).strip() != text:
            return ""
        user_value = combo.itemData(idx, Qt.UserRole)
        if isinstance(user_value, str):
            return user_value.strip()
        return ""

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]], selected_text: str):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("", "")
        seen: set[tuple[str, str]] = set()
        for label, value in items:
            l = str(label or "").strip()
            v = str(value or "").strip()
            if not l:
                continue
            key = (l.casefold(), v.casefold())
            if key in seen:
                continue
            seen.add(key)
            combo.addItem(l, v)
        combo.setCurrentText(selected_text)
        combo.blockSignals(False)

    def _update_filter_options(self, records: list[dict]):
        grant_items: set[tuple[str, str]] = set()
        subgroup_items: set[tuple[str, str]] = set()
        registrant_items: set[tuple[str, str]] = set()
        template_items: set[tuple[str, str]] = set()
        equip_items: set[tuple[str, str]] = set()
        equip_local_items: set[tuple[str, str]] = set()
        related_items: set[tuple[str, str]] = set()

        subgroup_label_to_id: dict[str, str] = {}
        for info in self._dataset_inference_map.values():
            if not isinstance(info, dict):
                continue
            label = self._resolve_subgroup_label(info.get("subgroup", ""), info.get("subgroup_id", ""))
            sid = _to_text(info.get("subgroup_id")).strip()
            if label and sid:
                subgroup_label_to_id.setdefault(label, sid)

        subgroup_id_to_label: dict[str, str] = {}
        for label, sid in subgroup_label_to_id.items():
            if sid and label:
                subgroup_id_to_label.setdefault(sid, label)

        for rec in records:
            grant = _to_text(rec.get("project_number")).strip()
            subgroup = _to_text(rec.get("subgroup")).strip()
            subgroup_id = _to_text(rec.get("subgroup_id")).strip()
            registrant = _to_text(rec.get("registrant")).strip()
            template = _to_text(rec.get("template")).strip()
            equip = _to_text(rec.get("equipment_name")).strip()
            equip_local = _to_text(rec.get("equipment_local_id")).strip()
            related = _to_text(rec.get("related_datasets")).strip()

            if grant:
                grant_items.add((grant, grant))
            subgroup_label = self._resolve_subgroup_label(subgroup, subgroup_id)
            if subgroup_label:
                subgroup_items.add((subgroup_label, subgroup_id or subgroup_label))
            if registrant:
                if not _looks_like_uuid(registrant):
                    registrant_items.add((registrant, registrant))
            if template:
                template_items.add((template, template))
            if equip:
                equip_items.add((equip, equip))
            if equip_local:
                if equip:
                    equip_local_label = _join_non_empty([equip_local, equip], sep=" | ")
                    if equip_local_label:
                        equip_local_items.add((equip_local_label, equip_local))
            if related:
                for rid in [x.strip() for x in related.split(",") if x.strip()]:
                    related_items.add((self._resolve_related_label(rid), rid))

        for info in self._dataset_inference_map.values():
            if not isinstance(info, dict):
                continue
            grant = _to_text(info.get("project_number")).strip()
            subgroup = _to_text(info.get("subgroup")).strip()
            subgroup_id = _to_text(info.get("subgroup_id")).strip()
            registrant = _to_text(info.get("registrant")).strip()
            template = _to_text(info.get("template")).strip()
            equip = _to_text(info.get("equipment_name")).strip()
            equip_local = _to_text(info.get("equipment_local_id")).strip()
            related = _to_text(info.get("related_datasets")).strip()

            if grant:
                grant_items.add((grant, grant))
            subgroup_label = self._resolve_subgroup_label(subgroup, subgroup_id)
            if subgroup_label:
                subgroup_items.add((subgroup_label, subgroup_id or subgroup_label))
            if registrant:
                if not _looks_like_uuid(registrant):
                    registrant_items.add((registrant, registrant))
            if template:
                template_items.add((template, template))
            if equip:
                equip_items.add((equip, equip))
            if equip_local:
                if equip:
                    equip_local_label = _join_non_empty([equip_local, equip], sep=" | ")
                    if equip_local_label:
                        equip_local_items.add((equip_local_label, equip_local))
            if related:
                for rid in [x.strip() for x in related.split(",") if x.strip()]:
                    related_items.add((self._resolve_related_label(rid), rid))

        reverse = self._rde_index_payload.get("reverse") if isinstance(self._rde_index_payload, dict) else {}
        if isinstance(reverse, dict):
            for key in reverse.get("grant_number", {}).keys() if isinstance(reverse.get("grant_number"), dict) else []:
                text = str(key).strip()
                if text:
                    grant_items.add((text, text))
            subgroup_name_map = reverse.get("subgroup_name") if isinstance(reverse.get("subgroup_name"), dict) else {}
            subgroup_id_map = reverse.get("subgroup_id") if isinstance(reverse.get("subgroup_id"), dict) else {}
            for key in subgroup_name_map.keys() if isinstance(subgroup_name_map, dict) else []:
                text = str(key).strip()
                if text:
                    subgroup_items.add((text, subgroup_label_to_id.get(text, text)))
            for key in subgroup_id_map.keys() if isinstance(subgroup_id_map, dict) else []:
                text = str(key).strip()
                if text:
                    subgroup_items.add((subgroup_id_to_label.get(text, self._resolve_subgroup_label("", text)), text))
            for key in reverse.get("template_id", {}).keys() if isinstance(reverse.get("template_id"), dict) else []:
                text = str(key).strip()
                if text:
                    template_items.add((text, text))
            for key in reverse.get("equipment_name", {}).keys() if isinstance(reverse.get("equipment_name"), dict) else []:
                text = str(key).strip()
                if text:
                    equip_items.add((text, text))
            for key in reverse.get("equipment_local_id", {}).keys() if isinstance(reverse.get("equipment_local_id"), dict) else []:
                local_text = str(key).strip()
                if local_text:
                    inferred_name = ""
                    for info in self._dataset_inference_map.values():
                        if not isinstance(info, dict):
                            continue
                        if _to_text(info.get("equipment_local_id")).strip() == local_text:
                            inferred_name = _to_text(info.get("equipment_name")).strip()
                            if inferred_name:
                                break
                    if inferred_name:
                        equip_local_items.add((_join_non_empty([local_text, inferred_name], sep=" | "), local_text))
            for key in reverse.get("related_dataset_id", {}).keys() if isinstance(reverse.get("related_dataset_id"), dict) else []:
                text = str(key).strip()
                if text:
                    related_items.add((self._resolve_related_label(text), text))

        self._set_combo_items(self.f_project_number, sorted(grant_items), self.f_project_number.currentText().strip())
        self._set_combo_items(self.f_subgroup, sorted(subgroup_items), self.f_subgroup.currentText().strip())
        self._set_combo_items(self.f_registrant, sorted(registrant_items), self.f_registrant.currentText().strip())
        self._set_combo_items(self.f_template, sorted(template_items), self.f_template.currentText().strip())
        self._set_combo_items(self.f_equip_name, sorted(equip_items), self.f_equip_name.currentText().strip())
        self._set_combo_items(self.f_equip_local, sorted(equip_local_items), self.f_equip_local.currentText().strip())
        self._set_combo_items(self.f_related, sorted(related_items), self.f_related.currentText().strip())

    def _toggle_row_height_mode(self):
        self._compact_rows_mode = not self._compact_rows_mode
        if self._compact_rows_mode:
            self.table.verticalHeader().setDefaultSectionSize(int(self.table.fontMetrics().height() * 1.15))
            self.compact_rows_btn.setText("通常表示")
        else:
            self.table.verticalHeader().setDefaultSectionSize(int(self.table.fontMetrics().height() * 1.8))
            self.compact_rows_btn.setText("1行表示")

    def _current_filter_criteria(self) -> dict[str, str]:
        return {
            "project_number": self._combo_match_value(self.f_project_number),
            "subgroup": self._combo_match_value(self.f_subgroup),
            "registrant": self._combo_match_value(self.f_registrant),
            "organization": self.f_org.text().strip(),
            "template": self._combo_match_value(self.f_template),
            "sample_name": self.f_sample_name.text().strip(),
            "sample_uuid": self.f_sample_uuid.text().strip(),
            "equipment_name": self._combo_match_value(self.f_equip_name),
            "equipment_local": self._combo_match_value(self.f_equip_local),
            "tags": self.f_tags.text().strip(),
            "related": self._combo_match_value(self.f_related),
        }

    @staticmethod
    def _matches_criteria(rec: dict, criteria: dict[str, str]) -> bool:
        subgroup_text = _join_non_empty([
            _to_text(rec.get("subgroup", "")),
            _to_text(rec.get("subgroup_id", "")),
        ], sep=" | ")
        return (
            _contains(rec.get("project_number", ""), criteria.get("project_number", ""))
            and _contains(subgroup_text, criteria.get("subgroup", ""))
            and _contains(rec.get("registrant", ""), criteria.get("registrant", ""))
            and _contains(rec.get("organization", ""), criteria.get("organization", ""))
            and _contains(rec.get("template", ""), criteria.get("template", ""))
            and _contains(rec.get("sample_name", ""), criteria.get("sample_name", ""))
            and _contains(rec.get("sample_uuid", ""), criteria.get("sample_uuid", ""))
            and _contains(rec.get("equipment_name", ""), criteria.get("equipment_name", ""))
            and _contains(
                _join_non_empty([
                    rec.get("equipment_local_id", ""),
                    rec.get("equipment_name", ""),
                ], sep=" | "),
                criteria.get("equipment_local", ""),
            )
            and _contains(rec.get("tags", ""), criteria.get("tags", ""))
            and _contains(rec.get("related_datasets", ""), criteria.get("related", ""))
        )

    def _matches(self, rec: dict) -> bool:
        return self._matches_criteria(rec, self._current_filter_criteria())

    def _parallel_filter_records(self, candidates: list[dict]) -> list[dict]:
        criteria = self._current_filter_criteria()
        workers = self._effective_search_workers()
        return parallel_filter(
            candidates,
            lambda rec: self._matches_criteria(rec, criteria),
            max_workers=workers,
            cancel_checker=lambda: self._cancel_requested,
        )

    def _build_record_exact_indexes(self, records: list[dict]):
        indexes: dict[str, dict[str, set[int]]] = {
            "dataset_id": {},
            "project_number": {},
            "subgroup": {},
            "registrant": {},
            "template": {},
            "equipment_name": {},
            "equipment_local": {},
            "related": {},
        }

        def add(field: str, value: str, row_idx: int):
            key = str(value or "").strip().casefold()
            if not key:
                return
            bucket = indexes[field].setdefault(key, set())
            bucket.add(row_idx)

        for i, rec in enumerate(records):
            add("dataset_id", _to_text(rec.get("dataset_id")), i)
            add("project_number", _to_text(rec.get("project_number")), i)
            add("subgroup", _to_text(rec.get("subgroup")), i)
            add("subgroup", _to_text(rec.get("subgroup_id")), i)
            add("registrant", _to_text(rec.get("registrant")), i)
            add("template", _to_text(rec.get("template")), i)
            add("equipment_name", _to_text(rec.get("equipment_name")), i)
            add("equipment_local", _to_text(rec.get("equipment_local_id")), i)
            for rel in [x.strip() for x in _to_text(rec.get("related_datasets")).split(",") if x.strip()]:
                add("related", rel, i)

        self._record_exact_indexes = indexes

    def _candidate_dataset_ids_from_rde_index(self) -> set[str] | None:
        if not isinstance(self._rde_index_payload, dict):
            return None
        criteria = {
            "grant_number": self._combo_match_value(self.f_project_number),
            "subgroup_id": self._combo_selected_user_value(self.f_subgroup),
            "subgroup_name": self.f_subgroup.currentText().strip(),
            "template_id": self._combo_match_value(self.f_template),
            "equipment_name": self._combo_match_value(self.f_equip_name),
            "equipment_local_id": self._combo_match_value(self.f_equip_local),
            "related_dataset_id": self._combo_match_value(self.f_related),
        }
        try:
            return search_dataset_ids(self._rde_index_payload, criteria)
        except Exception:
            return None

    def _candidate_records_from_indexes(self) -> list[dict]:
        if not self._all_records:
            return []

        candidate_rows: set[int] | None = None
        selected_keys: list[tuple[str, str]] = [
            ("project_number", self._combo_selected_user_value(self.f_project_number)),
            ("subgroup", self._combo_selected_user_value(self.f_subgroup)),
            ("registrant", self._combo_selected_user_value(self.f_registrant)),
            ("template", self._combo_selected_user_value(self.f_template)),
            ("equipment_name", self._combo_selected_user_value(self.f_equip_name)),
            ("equipment_local", self._combo_selected_user_value(self.f_equip_local)),
            ("related", self._combo_selected_user_value(self.f_related)),
        ]

        for field, value in selected_keys:
            if not value:
                continue
            rows = self._record_exact_indexes.get(field, {}).get(value.casefold(), set())
            if candidate_rows is None:
                candidate_rows = set(rows)
            else:
                candidate_rows &= rows
            if not candidate_rows:
                return []

        dataset_candidates = self._candidate_dataset_ids_from_rde_index()
        if dataset_candidates is not None:
            dataset_rows: set[int] = set()
            for i, rec in enumerate(self._all_records):
                dataset_id = _to_text(rec.get("dataset_id")).strip()
                if dataset_id and dataset_id in dataset_candidates:
                    dataset_rows.add(i)
            if dataset_rows:
                if candidate_rows is None:
                    candidate_rows = dataset_rows
                else:
                    candidate_rows &= dataset_rows

        if candidate_rows is None:
            return self._all_records
        return [self._all_records[i] for i in sorted(candidate_rows)]

    def _load_dataset_inference_map(self) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
        bootstrap_started_at = time.perf_counter()
        entry_read_limit = 200
        entry_read_count = 0
        entry_read_time_budget_sec = 3.0

        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        subgroup_path = get_dynamic_file_path("output/rde/data/subGroup.json")
        template_path = get_dynamic_file_path("output/rde/data/template.json")
        instrument_path = get_dynamic_file_path("output/rde/data/instruments.json")
        entry_dir = get_dynamic_file_path("output/rde/data/dataEntry")

        dataset_items = _load_data_items(dataset_path)
        template_items = _load_data_items(template_path)
        instrument_items = _load_data_items(instrument_path)

        subgroup_payload = _load_json(subgroup_path)
        subgroup_name_by_id: dict[str, str] = {}
        subgroup_by_grant: dict[str, tuple[str, str]] = {}
        user_name_by_id: dict[str, str] = {}
        user_org_by_id: dict[str, str] = {}
        subgroup_items: list[dict] = []
        if isinstance(subgroup_payload, dict):
            included = subgroup_payload.get("included")
            data = subgroup_payload.get("data")
            if isinstance(included, list):
                subgroup_items.extend([x for x in included if isinstance(x, dict)])
            if isinstance(data, list):
                subgroup_items.extend([x for x in data if isinstance(x, dict)])
            elif isinstance(data, dict):
                subgroup_items.append(data)
        elif isinstance(subgroup_payload, list):
            subgroup_items.extend([x for x in subgroup_payload if isinstance(x, dict)])

        for item in subgroup_items:
            item_type = str(item.get("type") or "").strip()
            if item_type == "user":
                uid = str(item.get("id") or "").strip()
                attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
                name = _to_text(attrs.get("userName") or attrs.get("name")).strip()
                org = _to_text(attrs.get("organizationName") or attrs.get("organization")).strip()
                if uid and name:
                    user_name_by_id[uid] = name
                if uid and org:
                    user_org_by_id[uid] = org
                continue
            if item_type != "group":
                continue
            gid = str(item.get("id") or "").strip()
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            group_type = str(attrs.get("groupType") or "").strip()
            if group_type and group_type != "TEAM":
                continue
            name = str(attrs.get("name") or "").strip()
            desc = str(attrs.get("description") or "").strip()
            if gid:
                subgroup_name_by_id[gid] = _join_non_empty([name, desc], sep=" | ") or gid

            raw_subjects = attrs.get("subjects")
            subjects: list[Any] = raw_subjects if isinstance(raw_subjects, list) else []
            for subject in subjects:
                if not isinstance(subject, dict):
                    continue
                grant = str(subject.get("grantNumber") or "").strip()
                if grant and gid:
                    subgroup_by_grant[grant] = (gid, subgroup_name_by_id.get(gid, gid))

        template_name_by_id: dict[str, str] = {}
        for item in template_items:
            tid = str(item.get("id") or "").strip()
            if not tid:
                continue
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            template_name = _first_non_empty(
                [
                    attrs.get("name"),
                    attrs.get("nameJa"),
                    attrs.get("title"),
                    attrs.get("displayName"),
                    attrs.get("templateName"),
                ]
            )
            template_name_by_id[tid] = template_name or tid

        instrument_name_by_id: dict[str, str] = {}
        instrument_local_by_id: dict[str, str] = {}
        for item in instrument_items:
            iid = str(item.get("id") or "").strip()
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            name = str(attrs.get("nameJa") or attrs.get("nameEn") or attrs.get("name") or "").strip()
            local_id = ""
            programs = attrs.get("programs")
            for program in programs if isinstance(programs, list) else []:
                if isinstance(program, dict):
                    local_id = str(program.get("localId") or "").strip()
                    if local_id:
                        break
            if iid:
                if name:
                    instrument_name_by_id[iid] = name
                if local_id:
                    instrument_local_by_id[iid] = local_id

        sample_name_by_id: dict[str, str] = {}
        samples_dir = get_dynamic_file_path("output/rde/data/samples")
        if samples_dir and os.path.isdir(samples_dir):
            for file_name in os.listdir(samples_dir):
                if not str(file_name).lower().endswith(".json"):
                    continue
                payload = _load_json(os.path.join(samples_dir, file_name))
                items: list[dict] = []
                if isinstance(payload, dict):
                    data = payload.get("data")
                    if isinstance(data, list):
                        items.extend([x for x in data if isinstance(x, dict)])
                    elif isinstance(data, dict):
                        items.append(data)
                elif isinstance(payload, list):
                    items.extend([x for x in payload if isinstance(x, dict)])

                for item in items:
                    sample_id = str(item.get("id") or "").strip()
                    attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
                    names = attrs.get("names")
                    name = ""
                    if isinstance(names, list):
                        name = ", ".join([str(x).strip() for x in names if str(x).strip()])
                    elif isinstance(names, str):
                        name = names.strip()
                    if not name:
                        name = _first_non_empty([attrs.get("name"), attrs.get("description"), attrs.get("displayName")])
                    if sample_id and name:
                        sample_name_by_id[sample_id] = name

        template_to_instrument_ids: dict[str, list[str]] = {}
        for item in template_items:
            template_id = str(item.get("id") or "").strip()
            if not template_id:
                continue
            rels = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
            instruments_data = (rels.get("instruments") or {}).get("data") if isinstance(rels, dict) else []
            ids: list[str] = []
            if isinstance(instruments_data, dict):
                instruments_data = [instruments_data]
            for inst in instruments_data if isinstance(instruments_data, list) else []:
                if not isinstance(inst, dict):
                    continue
                inst_id = str(inst.get("id") or "").strip()
                if inst_id:
                    ids.append(inst_id)
            template_to_instrument_ids[template_id] = ids

        result: dict[str, dict[str, str]] = {}
        by_title: dict[str, dict[str, str]] = {}
        public_registrant_map = _load_public_output_registrant_map()
        for dataset in dataset_items:
            dataset_id = str(dataset.get("id") or "").strip()
            if not dataset_id:
                continue
            attrs = dataset.get("attributes") if isinstance(dataset.get("attributes"), dict) else {}
            rels = dataset.get("relationships") if isinstance(dataset.get("relationships"), dict) else {}

            group_data = (rels.get("group") or {}).get("data") if isinstance(rels, dict) else None
            subgroup_id = ""
            if isinstance(group_data, dict):
                subgroup_id = str(group_data.get("id") or "").strip()
            subgroup_id = subgroup_id or str(attrs.get("groupId") or "").strip()
            grant_number = str(attrs.get("grantNumber") or "").strip()
            if not subgroup_id and grant_number and grant_number in subgroup_by_grant:
                subgroup_id = subgroup_by_grant[grant_number][0]
            subgroup = subgroup_name_by_id.get(subgroup_id, subgroup_by_grant.get(grant_number, ("", ""))[1] or subgroup_id)

            template_data = (rels.get("template") or {}).get("data") if isinstance(rels, dict) else None
            template_id = ""
            if isinstance(template_data, dict):
                template_id = str(template_data.get("id") or "").strip()
            template_id = template_id or str(attrs.get("templateId") or "").strip()
            template = template_name_by_id.get(template_id, template_id)

            registrant = _first_non_empty(
                [
                    attrs.get("datasetRegistrant"),
                    attrs.get("dataset_registrant"),
                    attrs.get("registrant"),
                    attrs.get("registrants"),
                    attrs.get("datasetRegistrants"),
                    attrs.get("registrationUserName"),
                    attrs.get("registeredBy"),
                    attrs.get("registered_by"),
                    attrs.get("createdBy"),
                    attrs.get("creatorName"),
                    attrs.get("ownerName"),
                ]
            )
            if not registrant:
                registrant = _to_text(public_registrant_map.get(dataset_id)).strip()
            if not registrant:
                data_owners = (rels.get("dataOwners") or {}).get("data") if isinstance(rels, dict) else []
                if isinstance(data_owners, dict):
                    data_owners = [data_owners]
                for owner in (data_owners if isinstance(data_owners, list) else []):
                    if not isinstance(owner, dict):
                        continue
                    owner_id = str(owner.get("id") or "").strip()
                    if not owner_id:
                        continue
                    owner_name = _to_text(user_name_by_id.get(owner_id)).strip()
                    owner_org = _to_text(user_org_by_id.get(owner_id)).strip()
                    if owner_name and owner_org:
                        registrant = f"{owner_name}（{owner_org}）"
                        break
                    if owner_name:
                        registrant = owner_name
                        break
                    owner_org_only = _to_text(user_org_by_id.get(owner_id)).strip()
                    if owner_org_only:
                        registrant = f"所属:{owner_org_only}"
                        break

            info = {
                "dataset_uuid": dataset_id,
                "project_number": str(attrs.get("grantNumber") or "").strip(),
                "subgroup": subgroup,
                "subgroup_id": subgroup_id,
                "registrant": registrant,
                "template": template,
                "dataset_name": str(attrs.get("name") or "").strip(),
                "sample_name": "",
                "sample_uuid": "",
                "equipment_name": "",
                "equipment_local_id": "",
                "tags": _collect_tags(dataset),
                "related_datasets": _collect_related_dataset_ids(dataset),
                "related_datasets_display": "",
            }

            needs_entry_lookup = not (
                info["registrant"]
                and info["sample_name"]
                and info["sample_uuid"]
                and info["equipment_name"]
                and info["equipment_local_id"]
            )
            entry_items: list[dict] = []
            if needs_entry_lookup and os.path.isdir(entry_dir):
                within_time_budget = (time.perf_counter() - bootstrap_started_at) < entry_read_time_budget_sec
                within_read_limit = entry_read_count < entry_read_limit
                if within_time_budget and within_read_limit:
                    entry_path = os.path.join(entry_dir, f"{dataset_id}.json")
                    entry_items = _load_data_items(entry_path)
                    entry_read_count += 1
            for entry in entry_items:
                eattrs = entry.get("attributes") if isinstance(entry.get("attributes"), dict) else {}
                erels = entry.get("relationships") if isinstance(entry.get("relationships"), dict) else {}
                if not info["registrant"]:
                    info["registrant"] = _first_non_empty(
                        [
                            eattrs.get("registrant"),
                            eattrs.get("registeredBy"),
                            eattrs.get("registrationUserName"),
                            eattrs.get("creatorName"),
                            eattrs.get("createdBy"),
                        ]
                    )
                if not info["sample_name"]:
                    info["sample_name"] = _first_non_empty(
                        [
                            eattrs.get("sampleNames"),
                            eattrs.get("sampleName"),
                            eattrs.get("displayName"),
                        ]
                    )
                if not info["sample_uuid"]:
                    info["sample_uuid"] = _first_non_empty(
                        [
                            eattrs.get("sampleUuid"),
                            eattrs.get("sampleUUID"),
                            eattrs.get("sampleId"),
                            eattrs.get("sample_id"),
                        ]
                    )
                if not info["equipment_name"]:
                    info["equipment_name"] = _first_non_empty(
                        [
                            eattrs.get("instrumentName"),
                            eattrs.get("equipmentName"),
                            eattrs.get("instrument"),
                        ]
                    )
                if not info["equipment_local_id"]:
                    info["equipment_local_id"] = _first_non_empty(
                        [
                            eattrs.get("instrumentLocalId"),
                            eattrs.get("equipmentLocalId"),
                            eattrs.get("localId"),
                        ]
                    )

                instrument_rel = (erels.get("instrument") or {}).get("data") if isinstance(erels, dict) else None
                instrument_id = str(instrument_rel.get("id") or "").strip() if isinstance(instrument_rel, dict) else ""
                if instrument_id:
                    if not info["equipment_name"]:
                        info["equipment_name"] = instrument_name_by_id.get(instrument_id, "")
                    if not info["equipment_local_id"]:
                        info["equipment_local_id"] = instrument_local_by_id.get(instrument_id, "")

                sample_rel = (erels.get("sample") or {}).get("data") if isinstance(erels, dict) else None
                if not info["sample_uuid"] and isinstance(sample_rel, dict):
                    info["sample_uuid"] = str(sample_rel.get("id") or "").strip()
                if not info["sample_name"] and isinstance(sample_rel, dict):
                    sid = str(sample_rel.get("id") or "").strip()
                    if sid:
                        info["sample_name"] = _to_text(sample_name_by_id.get(sid)).strip()

                if info["sample_name"] and info["sample_uuid"] and info["equipment_name"] and info["equipment_local_id"]:
                    break

            if (not info["equipment_name"] or not info["equipment_local_id"]) and template_id:
                for inst_id in template_to_instrument_ids.get(template_id, []):
                    if not info["equipment_name"]:
                        info["equipment_name"] = _to_text(instrument_name_by_id.get(inst_id)).strip()
                    if not info["equipment_local_id"]:
                        info["equipment_local_id"] = _to_text(instrument_local_by_id.get(inst_id)).strip()
                    if info["equipment_name"] and info["equipment_local_id"]:
                        break

            result[dataset_id] = info
            title_key = str(info.get("dataset_name") or "").strip().casefold()
            if title_key:
                by_title[title_key] = info

        if entry_read_count >= entry_read_limit or (time.perf_counter() - bootstrap_started_at) >= entry_read_time_budget_sec:
            logger.debug(
                "bulk_dp: dataset inference bootstrap limited entry reads count=%s elapsed=%.3fs",
                entry_read_count,
                max(0.0, time.perf_counter() - bootstrap_started_at),
            )

        for dataset_id, info in result.items():
            related_ids = [x.strip() for x in _to_text(info.get("related_datasets")).split(",") if x.strip()]
            display_parts: list[str] = []
            for rid in related_ids:
                rel = result.get(rid, {})
                rel_grant = _to_text(rel.get("project_number")).strip()
                rel_name = _to_text(rel.get("dataset_name")).strip()
                display_parts.append(_join_non_empty([rel_grant, rel_name], sep=" | ") or rid)
            info["related_datasets_display"] = _join_non_empty(display_parts)

        return result, by_title

    def _enrich_record(self, rec: dict) -> dict:
        dataset_id = _to_text(rec.get("dataset_id")).strip()
        inferred = self._dataset_inference_map.get(dataset_id, {})
        if not inferred:
            title_key = _to_text(rec.get("title")).strip().casefold()
            if title_key:
                inferred = self._dataset_inference_by_title.get(title_key, {})
        if inferred:
            for key in [
                "project_number",
                "subgroup",
                "subgroup_id",
                "registrant",
                "template",
                "sample_name",
                "sample_uuid",
                "equipment_name",
                "equipment_local_id",
                "tags",
                "related_datasets",
                "related_datasets_display",
            ]:
                if not _to_text(rec.get(key)).strip():
                    rec[key] = _to_text(inferred.get(key)).strip()

            current_dataset_id = _to_text(rec.get("dataset_id")).strip()
            inferred_dataset_uuid = _to_text(inferred.get("dataset_uuid")).strip()
            if not inferred_dataset_uuid:
                title_key = _to_text(rec.get("title")).strip().casefold()
                inferred_dataset_uuid = _to_text(self._dataset_uuid_by_title.get(title_key)).strip()
            if inferred_dataset_uuid and (not current_dataset_id or not _looks_like_uuid(current_dataset_id)):
                rec["dataset_id"] = inferred_dataset_uuid

        if not _to_text(rec.get("sample_name")).strip():
            sample_uuid = _to_text(rec.get("sample_uuid")).strip()
            if sample_uuid:
                rec["sample_name"] = _to_text(self._sample_name_by_id.get(sample_uuid)).strip()

        dataset_id_for_entry = _to_text(rec.get("dataset_id")).strip()
        if dataset_id_for_entry:
            needs_entry_enrichment = not (
                _to_text(rec.get("subgroup")).strip()
                and _to_text(rec.get("registrant")).strip()
                and _to_text(rec.get("sample_name")).strip()
                and _to_text(rec.get("sample_uuid")).strip()
            )
            if needs_entry_enrichment:
                extra = self._load_entry_derived_info_for_dataset(dataset_id_for_entry)
                if isinstance(extra, dict):
                    if not _to_text(rec.get("subgroup")).strip() and _to_text(extra.get("subgroup")).strip():
                        rec["subgroup"] = _to_text(extra.get("subgroup")).strip()
                    if not _to_text(rec.get("subgroup_id")).strip() and _to_text(extra.get("subgroup_id")).strip():
                        rec["subgroup_id"] = _to_text(extra.get("subgroup_id")).strip()
                    if not _to_text(rec.get("registrant")).strip() and _to_text(extra.get("registrant")).strip():
                        rec["registrant"] = _to_text(extra.get("registrant")).strip()
                    if not _to_text(rec.get("sample_uuid")).strip() and _to_text(extra.get("sample_uuid")).strip():
                        rec["sample_uuid"] = _to_text(extra.get("sample_uuid")).strip()
                    if not _to_text(rec.get("sample_name")).strip() and _to_text(extra.get("sample_name")).strip():
                        rec["sample_name"] = _to_text(extra.get("sample_name")).strip()

        if not _to_text(rec.get("sample_name")).strip():
            sample_uuid = _to_text(rec.get("sample_uuid")).strip()
            if sample_uuid:
                rec["sample_name"] = _to_text(self._sample_name_by_id.get(sample_uuid)).strip()
        return rec

    def _load_entry_derived_info_for_dataset(self, dataset_id: str) -> dict[str, str]:
        dsid = _to_text(dataset_id).strip()
        if not dsid:
            return {}
        cached = self._entry_enrichment_cache.get(dsid)
        if isinstance(cached, dict):
            return cached

        info: dict[str, str] = {
            "subgroup": "",
            "subgroup_id": "",
            "registrant": "",
            "sample_name": "",
            "sample_uuid": "",
        }

        try:
            dataset_items = _load_data_items(get_dynamic_file_path("output/rde/data/dataset.json"))
            for ds in dataset_items:
                if not isinstance(ds, dict):
                    continue
                if _to_text(ds.get("id")).strip() != dsid:
                    continue
                attrs = ds.get("attributes") if isinstance(ds.get("attributes"), dict) else {}
                rels = ds.get("relationships") if isinstance(ds.get("relationships"), dict) else {}
                group_data = (rels.get("group") or {}).get("data") if isinstance(rels, dict) else None
                subgroup_id = ""
                if isinstance(group_data, dict):
                    subgroup_id = _to_text(group_data.get("id")).strip()
                subgroup_id = subgroup_id or _to_text(attrs.get("groupId")).strip()
                info["subgroup_id"] = subgroup_id
                info["subgroup"] = _to_text(self._subgroup_name_by_id.get(subgroup_id) or subgroup_id).strip()
                break
        except Exception:
            pass

        try:
            entry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dsid}.json")
            entry_payload = _load_json(entry_path)
        except Exception:
            entry_payload = None

        entries: list[dict] = []
        included_items: list[dict] = []
        if isinstance(entry_payload, dict):
            raw_data = entry_payload.get("data")
            if isinstance(raw_data, list):
                entries.extend([x for x in raw_data if isinstance(x, dict)])
            elif isinstance(raw_data, dict):
                entries.append(raw_data)
            raw_included = entry_payload.get("included")
            if isinstance(raw_included, list):
                included_items.extend([x for x in raw_included if isinstance(x, dict)])

        user_label_by_id: dict[str, str] = {}
        sample_name_by_id_from_included: dict[str, str] = {}
        for item in included_items:
            item_type = _to_text(item.get("type")).strip()
            item_id = _to_text(item.get("id")).strip()
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            if item_type == "user" and item_id:
                user_name = _to_text(attrs.get("userName") or attrs.get("name")).strip()
                org_name = _to_text(attrs.get("organizationName") or attrs.get("organization")).strip()
                if user_name and org_name:
                    user_label_by_id[item_id] = f"{user_name}（{org_name}）"
                elif user_name:
                    user_label_by_id[item_id] = user_name
                elif org_name:
                    user_label_by_id[item_id] = f"所属:{org_name}"
            elif item_type == "sample" and item_id:
                names = attrs.get("names")
                sample_name = ""
                if isinstance(names, list):
                    sample_name = ", ".join([_to_text(x).strip() for x in names if _to_text(x).strip()])
                if not sample_name:
                    sample_name = _to_text(attrs.get("primaryName") or attrs.get("name") or attrs.get("displayName")).strip()
                if sample_name:
                    sample_name_by_id_from_included[item_id] = sample_name

        def _metadata_value(metadata: dict[str, Any], key: str) -> str:
            node = metadata.get(key)
            if isinstance(node, dict):
                value = node.get("value")
                if isinstance(value, list):
                    return _first_non_empty(value)
                return _to_text(value).strip()
            return ""

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            eattrs = entry.get("attributes") if isinstance(entry.get("attributes"), dict) else {}
            erels = entry.get("relationships") if isinstance(entry.get("relationships"), dict) else {}
            metadata = eattrs.get("metadata") if isinstance(eattrs.get("metadata"), dict) else {}

            if not info["registrant"]:
                info["registrant"] = _first_non_empty(
                    [
                        eattrs.get("registrant"),
                        eattrs.get("registeredBy"),
                        eattrs.get("registrationUserName"),
                        eattrs.get("creatorName"),
                        eattrs.get("createdBy"),
                        _metadata_value(metadata, "invoice.basic.data_owner"),
                    ]
                )

            if not info["registrant"]:
                owner_rel = (erels.get("owner") or {}).get("data") if isinstance(erels, dict) else None
                if isinstance(owner_rel, dict):
                    owner_id = _to_text(owner_rel.get("id")).strip()
                    if owner_id:
                        info["registrant"] = _to_text(user_label_by_id.get(owner_id)).strip()

            if not info["sample_name"]:
                info["sample_name"] = _first_non_empty(
                    [
                        eattrs.get("sampleNames"),
                        eattrs.get("sampleName"),
                        eattrs.get("displayName"),
                        _metadata_value(metadata, "sample.name"),
                    ]
                )

            if not info["sample_uuid"]:
                info["sample_uuid"] = _first_non_empty(
                    [
                        eattrs.get("sampleUuid"),
                        eattrs.get("sampleUUID"),
                        eattrs.get("sampleId"),
                        eattrs.get("sample_id"),
                    ]
                )

            if not info["sample_uuid"]:
                sample_rel = (erels.get("sample") or {}).get("data") if isinstance(erels, dict) else None
                if isinstance(sample_rel, dict):
                    info["sample_uuid"] = _to_text(sample_rel.get("id")).strip()

            if info["sample_uuid"] and not info["sample_name"]:
                info["sample_name"] = _to_text(self._sample_name_by_id.get(info["sample_uuid"]) or "").strip()
            if info["sample_uuid"] and not info["sample_name"]:
                info["sample_name"] = _to_text(sample_name_by_id_from_included.get(info["sample_uuid"]) or "").strip()

            if info["registrant"] and info["sample_name"] and info["sample_uuid"]:
                break

        self._entry_enrichment_cache[dsid] = dict(info)
        return self._entry_enrichment_cache[dsid]

    def search_and_build(self):
        if self._search_thread is not None and self._search_thread.isRunning():
            logger.debug("bulk_dp: search request ignored because worker is running")
            return

        env = self.env_combo.currentData() or "production"
        keyword = self.f_keyword.text().strip()

        logger.debug("bulk_dp: start async search env=%s keyword_len=%s", env, len(keyword))
        self._search_started_at = time.perf_counter()
        self._cancel_requested = False
        workers = self._effective_search_workers()
        self.status.setText(f"検索中... (並列: {workers})")
        self._set_search_busy(True)
        candidate_dataset_ids = self._candidate_dataset_ids_from_rde_index()
        use_details = not bool(self._dataset_inference_map)
        logger.debug(
            "bulk_dp: async params candidate_ids=%s use_details=%s",
            "none" if candidate_dataset_ids is None else len(candidate_dataset_ids),
            use_details,
        )

        self._search_thread = _BulkDpSearchThread(keyword, env, candidate_dataset_ids, use_details, workers, self)
        self._search_thread.finished_fetch.connect(self._on_search_fetch_finished)
        self._search_thread.finished.connect(self._on_search_thread_stopped)
        self._search_thread.start()

    def _on_search_thread_stopped(self):
        logger.debug("bulk_dp: search thread stopped")
        if self._search_thread is not None:
            self._search_thread.deleteLater()
            self._search_thread = None

    def _on_search_fetch_finished(self, details: Any, error_text: str):
        logger.debug("bulk_dp: search thread finished error=%s details_type=%s", bool(error_text), type(details).__name__)
        elapsed = self._format_elapsed()
        meta: dict[str, Any] = details.get("_meta", {}) if isinstance(details, dict) else {}
        phase_suffix = ""
        if isinstance(meta, dict):
            link_fetch_sec = float(meta.get("link_fetch_sec") or 0.0)
            detail_fetch_sec = float(meta.get("detail_fetch_sec") or 0.0)
            local_filter_sec = float(meta.get("local_filter_sec") or 0.0)
            workers = int(meta.get("workers") or 0)
            source = _to_text(meta.get("source")).strip()
            if local_filter_sec > 0.0:
                phase_suffix = f" / ローカル抽出:{local_filter_sec:.2f}秒 / 並列:{workers}"
            elif link_fetch_sec > 0.0 or detail_fetch_sec > 0.0:
                phase_suffix = (
                    f" / page取得:{link_fetch_sec:.2f}秒"
                    f" / detail取得:{detail_fetch_sec:.2f}秒"
                    f" / 並列:{workers}"
                )
            if source:
                phase_suffix += f" / source:{source}"
        if error_text == "__CANCELLED__" or self._cancel_requested:
            self.status.setText(f"検索をキャンセルしました。({elapsed}{phase_suffix})")
            self._set_search_busy(False)
            return
        if error_text:
            self._all_records = []
            self._records = []
            self._record_exact_indexes = {}
            self._populate([])
            self.status.setText(f"検索失敗: {error_text} ({elapsed}{phase_suffix})")
            self._set_search_busy(False)
            return

        if isinstance(details, dict) and isinstance(details.get("links"), list):
            links = details.get("links") or []
            records = self._build_records_from_links(links)
            self._all_records = records
            self._build_record_exact_indexes(self._all_records)
            self._update_filter_options(self._all_records)

            candidates = self._candidate_records_from_indexes()
            self._records = self._parallel_filter_records(candidates)
            self._current_page = 1
            self._populate(self._records)
            self._log_record_quality(self._records)
            self.status.setText(f"検索結果: {len(self._records)}件 ({elapsed}{phase_suffix})")
            self._set_search_busy(False)
            return

        if isinstance(details, dict) and isinstance(details.get("records"), list):
            raw_records = details.get("records") or []
            records = [self._enrich_record(dict(rec)) for rec in raw_records if isinstance(rec, dict)]
            self._all_records = records
            self._build_record_exact_indexes(self._all_records)
            self._update_filter_options(self._all_records)

            candidates = self._candidate_records_from_indexes()
            self._records = self._parallel_filter_records(candidates)
            self._current_page = 1
            self._populate(self._records)
            self._log_record_quality(self._records)
            self.status.setText(f"検索結果: {len(self._records)}件 ({elapsed}{phase_suffix})")
            self._set_search_busy(False)
            return

        if isinstance(details, dict) and isinstance(details.get("details"), list):
            details_list = details.get("details") or []
        else:
            details_list = details if isinstance(details, list) else []
        if not details_list:
            self._all_records = []
            self._records = []
            self._record_exact_indexes = {}
            self._populate([])
            self.status.setText(f"検索結果: 0件 ({elapsed}{phase_suffix})")
            self._set_search_busy(False)
            return
        records: list[dict] = []
        for d in details_list:
            fields = d.fields if isinstance(d.fields, dict) else {}
            record = {
                    "title": d.title,
                    "project_number": _to_text(fields.get("project_number")),
                    "subgroup": _to_text(fields.get("subgroup") or fields.get("sub_group") or ""),
                    "subgroup_id": "",
                    "registrant": _to_text(fields.get("dataset_registrant")),
                    "organization": _to_text(fields.get("organization")),
                    "dataset_id": _to_text(fields.get("dataset_id") or d.code),
                    "template": _to_text(fields.get("dataset_template") or ""),
                    "sample_name": _to_text(fields.get("sample_name") or ""),
                    "sample_uuid": _to_text(fields.get("sample_uuid") or ""),
                    "equipment_name": _to_text(fields.get("equipment_name") or ""),
                    "equipment_local_id": _to_text(fields.get("equipment_local_id") or ""),
                    "tags": _to_text(fields.get("keyword_tags") or ""),
                    "related_datasets": _to_text(fields.get("related_datasets") or ""),
                    "related_datasets_display": "",
                    "detail_url": d.detail_url,
                    "content_url": (d.download_links[0] if d.download_links else ""),
                }
            records.append(self._enrich_record(record))

        self._all_records = records
        self._build_record_exact_indexes(self._all_records)
        self._update_filter_options(self._all_records)

        candidates = self._candidate_records_from_indexes()
        self._records = self._parallel_filter_records(candidates)
        self._current_page = 1
        self._populate(self._records)
        self._log_record_quality(self._records)
        self.status.setText(f"検索結果: {len(self._records)}件 ({elapsed}{phase_suffix})")
        self._set_search_busy(False)

    def _populate(self, records: list[dict]):
        self._records = list(records)
        self._render_page()

    def _render_page(self):
        records = self._current_page_records()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for rec in records:
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                rec.get("title", ""),
                rec.get("project_number", ""),
                rec.get("subgroup", ""),
                "" if _looks_like_uuid(_to_text(rec.get("registrant", ""))) else rec.get("registrant", ""),
                rec.get("dataset_id", ""),
                rec.get("template", ""),
                rec.get("sample_name", ""),
                rec.get("sample_uuid", ""),
                rec.get("equipment_name", ""),
                rec.get("equipment_local_id", ""),
                rec.get("tags", ""),
                rec.get("related_datasets_display") or rec.get("related_datasets", ""),
                rec.get("detail_url", ""),
                rec.get("content_url", ""),
            ]
            for c, v in enumerate(values):
                it = QTableWidgetItem(_to_text(v))
                it.setData(Qt.UserRole, rec)
                it.setFlags(it.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self._update_pagination_controls()

    def _selected_record(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        rec = item.data(Qt.UserRole)
        return rec if isinstance(rec, dict) else None

    def _open_selected_url(self, key: str):
        rec = self._selected_record()
        if rec is None:
            QMessageBox.information(self, "情報", "行を選択してください。")
            return
        url = str(rec.get(key) or "").strip()
        if not url:
            QMessageBox.information(self, "情報", "対象URLがありません。")
            return
        QDesktopServices.openUrl(QUrl(url))

    def export_csv(self):
        if not self._records:
            QMessageBox.information(self, "情報", "出力対象がありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV出力", "dp_bulk_links.csv", "CSV (*.csv)")
        if not path:
            return
        headers = [
            "title",
            "project_number",
            "subgroup",
            "registrant",
            "dataset_id",
            "template",
            "sample_name",
            "sample_uuid",
            "equipment_name",
            "equipment_local_id",
            "tags",
            "related_datasets",
            "detail_url",
            "content_url",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for rec in self._records:
                writer.writerow({k: _to_text(rec.get(k, "")) for k in headers})
        QMessageBox.information(self, "完了", f"CSVを出力しました。\n{path}")

    def _export(self, fmt: str):
        if fmt != "csv":
            return
        self.export_csv()


def create_bulk_dp_tab(parent: QWidget | None = None) -> DataFetch2BulkDpTab:
    return DataFetch2BulkDpTab(parent)
