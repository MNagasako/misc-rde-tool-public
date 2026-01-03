from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from qt_compat.widgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QLineEdit,
        QCheckBox,
        QTextEdit,
        QGroupBox,
        QSpinBox,
        QRadioButton,
        QButtonGroup,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QAbstractItemView,
        QDateTimeEdit,
        QComboBox,
        QScrollArea,
        QMessageBox,
        QInputDialog,
        QDialog,
    )
    from qt_compat.core import Qt, QThread, Signal, QTimer
except Exception:
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QLineEdit,
        QCheckBox,
        QTextEdit,
        QGroupBox,
        QSpinBox,
        QRadioButton,
        QButtonGroup,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QAbstractItemView,
        QDateTimeEdit,
        QComboBox,
        QScrollArea,
        QMessageBox,
        QInputDialog,
        QDialog,
    )
    from PySide6.QtCore import Qt, QThread, Signal, QTimer

from config.common import SUBGROUP_JSON_PATH
from classes.core.mail_dispatcher import send_using_app_mail_settings
from classes.core.mail_send_log import (
    clear_history_by_mode,
    load_history,
    load_last_sent_at_by_entry_id,
    record_sent_ex,
    should_send,
)
from classes.data_entry.core import registration_status_service as regsvc
from classes.data_entry.core.logic.mail_notification_auto_runner import build_batches, interval_options
from classes.data_entry.core.logic.notification_selection import (
    PlannedNotificationRow,
    build_planned_notification_rows,
    select_failed_entries_by_reference,
    select_failed_entries_in_range,
)
from classes.data_entry.util.entry_dataset_template_resolver import build_dataset_template_name_map_for_entry_ids
from classes.data_entry.util.group_member_loader import load_group_members
from classes.data_entry.util.entry_group_email_resolver import build_email_map_for_entry_ids
from classes.subgroup.core.subgroup_data_manager import SubgroupDataManager
from classes.managers.app_config_manager import get_config_manager
from classes.theme import ThemeKey, get_color
from classes.equipment.util import equipment_manager_store
from classes.equipment.ui.equipment_manager_dialog import EquipmentManagerListDialog
from classes.utils.facility_link_helper import (
    extract_equipment_id,
    load_equipment_name_map_from_merged_data2,
    load_instrument_local_id_map_from_instruments_json,
    lookup_device_name_ja,
    lookup_equipment_id_by_device_name,
    lookup_instrument_local_id,
)

logger = logging.getLogger(__name__)

_JST = timezone(timedelta(hours=9))
_UTC = timezone.utc

_RECIPIENT_BOTH = "both"
_RECIPIENT_CREATOR = "creator"
_RECIPIENT_OWNER = "owner"


class _TemplateEditDialog(QDialog):
    def __init__(self, parent: QWidget, *, template_name: str, subject: str, body: str):
        super().__init__(parent)
        self.setWindowTitle(f"テンプレ編集: {template_name}")
        layout = QVBoxLayout(self)

        row_subj = QHBoxLayout()
        row_subj.addWidget(QLabel("件名テンプレ:"))
        self.subject_edit = QLineEdit()
        self.subject_edit.setText(subject or "")
        row_subj.addWidget(self.subject_edit)
        layout.addLayout(row_subj)

        layout.addWidget(QLabel("本文テンプレ:"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlainText(body or "")
        layout.addWidget(self.body_edit)

        placeholders = (
            "利用可能プレースホルダ（例: {entryId}）\n"
            "- {entryId}\n"
            "- {startTime}\n"
            "- {dataName}\n"
            "- {datasetName}\n"
            "- {datasetTemplateName}\n"
            "- {equipmentId}\n"
            "- {deviceNameJa}\n"
            "- {errorCode}\n"
            "- {errorMessage}\n"
            "- {createdByUserId} / {createdByName} / {createdByOrg} / {createdByMail}\n"
            "- {dataOwnerUserId} / {dataOwnerName} / {dataOwnerOrg} / {dataOwnerMail}\n"
            "- {testToAddress} / {productionToAddress}\n"
            "- {equipmentManagerNames} / {equipmentManagerEmails} / {equipmentManagerNotes}\n"
        )
        ph = QLabel(placeholders)
        ph.setWordWrap(True)
        layout.addWidget(ph)

        btn_row = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def values(self) -> tuple[str, str]:
        return (self.subject_edit.text() or ""), (self.body_edit.toPlainText() or "")


class _NotificationConfirmDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        template_name: str,
        row: PlannedNotificationRow,
    ):
        super().__init__(parent)
        self.setWindowTitle("メール通知確認")
        try:
            if parent is not None:
                self.resize(int(parent.width() * 0.5), max(400, int(parent.height() * 0.7)))
        except Exception:
            pass
        layout = QVBoxLayout(self)

        info = (
            f"テンプレ: {template_name}\n"
            f"設備ID: {row.equipment_id}\n"
            f"装置名_日: {row.device_name_ja}\n"
            f"データセットテンプレ: {row.dataset_template_name}\n"
            f"データ名: {row.data_name}\n"
            f"投入者メール: {row.created_mail}\n"
            f"所有者メール: {row.owner_mail}\n"
            f"テスト送信先: {row.test_to}\n"
            f"本番送信先: {row.production_to}\n"
        )
        lbl = QLabel(info)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        layout.addWidget(QLabel("件名（適用後）:"))
        self.subject_view = QLineEdit()
        self.subject_view.setReadOnly(True)
        self.subject_view.setText(row.subject)
        layout.addWidget(self.subject_view)

        layout.addWidget(QLabel("本文（適用後）:"))
        self.body_view = QTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setPlainText(row.body)
        layout.addWidget(self.body_view)

        btn_row = QHBoxLayout()
        self.send_test_btn = QPushButton("テスト送信")
        self.send_prod_btn = QPushButton("本番送信")
        self.close_btn = QPushButton("閉じる")
        btn_row.addStretch()
        btn_row.addWidget(self.send_test_btn)
        btn_row.addWidget(self.send_prod_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

        self.close_btn.clicked.connect(self.reject)


def _format_iso_to_jst(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_UTC)
        jst = dt.astimezone(_JST)
        return jst.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


class _SendLogDialog(QDialog):
    def __init__(self, parent: QWidget, *, items: List[Dict[str, Any]]):
        super().__init__(parent)
        self.setWindowTitle("送信ログ")
        layout = QVBoxLayout(self)

        self._headers = ["送信日時(JST)", "mode", "to", "subject", "entryId", "templateName"]

        filter_area = QScrollArea(self)
        filter_area.setWidgetResizable(True)
        filter_widget = QWidget(filter_area)
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filters: List[QLineEdit] = []
        for h in self._headers:
            e = QLineEdit()
            e.setPlaceholderText(h)
            e.setClearButtonEnabled(True)
            e.textChanged.connect(self._apply_filters)
            e.setMinimumWidth(140)
            self._filters.append(e)
            filter_layout.addWidget(e)
        filter_layout.addStretch()
        filter_area.setWidget(filter_widget)
        layout.addWidget(filter_area)

        self.table = QTableWidget(0, len(self._headers), self)
        self.table.setHorizontalHeaderLabels(self._headers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setTextElideMode(Qt.ElideRight)
        layout.addWidget(self.table)

        self._populate(items)

        btn_row = QHBoxLayout()
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        try:
            if parent is not None:
                self.resize(int(parent.width() * 0.8), max(400, int(parent.height() * 0.8)))
        except Exception:
            pass

    def _populate(self, items: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        for it in items or []:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(_format_iso_to_jst(str(it.get("sentAt") or ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(it.get("mode") or "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(it.get("to") or "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(it.get("subject") or "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(it.get("entryId") or "")))
            self.table.setItem(row, 5, QTableWidgetItem(str(it.get("templateName") or "")))
        self._apply_filters()

    def _apply_filters(self):
        texts = [(f.text() or "").strip().lower() for f in self._filters]
        for r in range(self.table.rowCount()):
            hide = False
            for c, t in enumerate(texts):
                if not t:
                    continue
                item = self.table.item(r, c)
                cell = (item.text() if item else "").lower()
                if t not in cell:
                    hide = True
                    break
            self.table.setRowHidden(r, hide)



def _load_selected_subgroup_id() -> str:
    try:
        with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        data = (payload or {}).get("data") or {}
        return str(data.get("id") or "")
    except Exception:
        return ""


def _member_email_map(group_id: str) -> Dict[str, str]:
    users = load_group_members(group_id)
    result: Dict[str, str] = {}
    for u in users or []:
        uid = str(u.get("id") or "")
        attr = u.get("attributes") or {}
        email = (
            str(attr.get("emailAddress") or "")
            or str(attr.get("email") or "")
            or str(attr.get("mailAddress") or "")
        ).strip()
        if uid and email:
            result[uid] = email
    return result


def _dtedit_to_jst(edit: QDateTimeEdit) -> datetime:
    # PySide6はPython datetime(naive)を返すことが多いので、JSTとして解釈する
    dt = edit.dateTime().toPython()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=_JST)
        return dt.astimezone(_JST)
    # フォールバック
    return datetime.now(_JST)


class _ExtractWorker(QThread):
    finished = Signal(object)  # list[dict]

    def __init__(
        self,
        *,
        mode: str,
        reference_utc: Optional[datetime],
        range_days: int,
        start_utc: Optional[datetime],
        end_utc: Optional[datetime],
    ):
        super().__init__()
        self._mode = mode
        self._reference_utc = reference_utc
        self._range_days = range_days
        self._start_utc = start_utc
        self._end_utc = end_utc

    def run(self):
        try:
            entries: List[Dict[str, Any]] = []
            if getattr(regsvc, "has_all_cache", None) and regsvc.has_all_cache(ignore_ttl=True):
                entries = regsvc.load_all_cache(ignore_ttl=True)
            else:
                entries = regsvc.fetch_latest(limit=200, use_cache=True)

            if self._mode == "reference" and self._reference_utc is not None:
                selected = select_failed_entries_by_reference(
                    entries=entries,
                    reference_utc=self._reference_utc,
                    range_days=self._range_days,
                )
            elif self._mode == "range" and self._start_utc is not None and self._end_utc is not None:
                selected = select_failed_entries_in_range(entries=entries, start_utc=self._start_utc, end_utc=self._end_utc)
            else:
                selected = []

            self.finished.emit(selected)
        except Exception as exc:
            logger.debug("extract worker failed: %s", exc)
            self.finished.emit([])


class _AutoRunWorker(QThread):
    finished = Signal(object)  # dict

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        run_token: int,
        range_days: int,
        production_mode: bool,
        include_creator: bool,
        include_owner: bool,
        include_equipment_manager: bool,
        test_to_address: str,
        subject_template: str,
        body_template: str,
        template_name: str,
        build_email_map: Callable[[List[Dict[str, Any]]], Dict[str, str]],
        augment_entries_for_display: Callable[[List[Dict[str, Any]]], None],
    ):
        super().__init__(parent)
        self._run_token = int(run_token)
        self._range_days = int(range_days)
        self._production_mode = bool(production_mode)
        self._include_creator = bool(include_creator)
        self._include_owner = bool(include_owner)
        self._include_equipment_manager = bool(include_equipment_manager)
        self._test_to_address = str(test_to_address or "").strip()
        self._subject_template = subject_template or ""
        self._body_template = body_template or ""
        self._template_name = template_name or ""
        self._build_email_map = build_email_map
        self._augment_entries_for_display = augment_entries_for_display

    def run(self):
        mode = "production" if self._production_mode else "test"
        checked_at_utc = datetime.now(_UTC)
        try:
            if self.isInterruptionRequested():
                self.finished.emit(
                    {
                        "run_token": self._run_token,
                        "mode": mode,
                        "checked_at_utc": checked_at_utc,
                        "entries": [],
                        "email_map": {},
                        "planned": [],
                        "excluded_logged": 0,
                        "unresolved": 0,
                        "sent_batches": 0,
                        "skipped_batches": 0,
                        "sent_to_count": 0,
                        "last_sent_at_utc": None,
                        "errors": [],
                    }
                )
                return

            # 1) 登録状況更新（最新100件を取得→キャッシュ保存→全件キャッシュへマージ）
            regsvc.fetch_latest(limit=100, use_cache=False)

            if self.isInterruptionRequested():
                self.finished.emit(
                    {
                        "run_token": self._run_token,
                        "mode": mode,
                        "checked_at_utc": checked_at_utc,
                        "entries": [],
                        "email_map": {},
                        "planned": [],
                        "excluded_logged": 0,
                        "unresolved": 0,
                        "sent_batches": 0,
                        "skipped_batches": 0,
                        "sent_to_count": 0,
                        "last_sent_at_utc": None,
                        "errors": [],
                    }
                )
                return

            # 2) 全件/最新から FAILED + 直近range_days日
            if getattr(regsvc, "has_all_cache", None) and regsvc.has_all_cache(ignore_ttl=True):
                entries = regsvc.load_all_cache(ignore_ttl=True)
            else:
                entries = regsvc.fetch_latest(limit=200, use_cache=True)

            selected = select_failed_entries_by_reference(entries=entries, reference_utc=checked_at_utc, range_days=self._range_days)

            if self.isInterruptionRequested():
                self.finished.emit(
                    {
                        "run_token": self._run_token,
                        "mode": mode,
                        "checked_at_utc": checked_at_utc,
                        "entries": [],
                        "email_map": {},
                        "planned": [],
                        "excluded_logged": 0,
                        "unresolved": 0,
                        "sent_batches": 0,
                        "skipped_batches": 0,
                        "sent_to_count": 0,
                        "last_sent_at_utc": None,
                        "errors": [],
                    }
                )
                return

            # 3) ログがある entry は除外（mode別）
            try:
                logged = load_last_sent_at_by_entry_id(mode=mode)
                logged_entry_ids = set(logged.keys())
            except Exception:
                logged_entry_ids = set()
            filtered = [e for e in selected if str((e or {}).get("id") or "").strip() not in logged_entry_ids]
            excluded_logged = max(0, len(selected) - len(filtered))

            # 4) 表示用の拡張/テンプレ適用
            email_map = self._build_email_map(filtered)
            try:
                self._augment_entries_for_display(filtered)
            except Exception:
                pass

            production_sent_at_by_entry_id: Dict[str, str] = {}
            try:
                production_sent_at_by_entry_id = load_last_sent_at_by_entry_id(mode="production")
            except Exception:
                production_sent_at_by_entry_id = {}

            planned = build_planned_notification_rows(
                entries=filtered,
                email_map=email_map,
                production_mode=self._production_mode,
                include_creator=self._include_creator,
                include_owner=self._include_owner,
                include_equipment_manager=self._include_equipment_manager,
                test_to_address=self._test_to_address,
                subject_template=self._subject_template,
                body_template=self._body_template,
                production_sent_at_by_entry_id=production_sent_at_by_entry_id,
            )

            if self.isInterruptionRequested():
                self.finished.emit(
                    {
                        "run_token": self._run_token,
                        "mode": mode,
                        "checked_at_utc": checked_at_utc,
                        "entries": [],
                        "email_map": {},
                        "planned": [],
                        "excluded_logged": excluded_logged,
                        "unresolved": 0,
                        "sent_batches": 0,
                        "skipped_batches": 0,
                        "sent_to_count": 0,
                        "last_sent_at_utc": None,
                        "errors": [],
                    }
                )
                return

            # 5) 宛先ごとに1通へ集約（テストは全件1通）
            summary = build_batches(
                planned_rows=planned,
                production_mode=self._production_mode,
                include_creator=self._include_creator,
                include_owner=self._include_owner,
                include_equipment_manager=self._include_equipment_manager,
                test_to_address=self._test_to_address,
                template_name=self._template_name,
                logged_entry_ids=logged_entry_ids,
            )

            sent_batches = 0
            skipped_batches = 0
            sent_to_count = 0
            last_sent_at_utc: Optional[datetime] = None
            errors: List[str] = []

            for batch in summary.batches:
                if self.isInterruptionRequested():
                    break
                to_addr = (batch.to_addr or "").strip()
                subject = (batch.subject or "").strip()
                if not to_addr or not subject:
                    skipped_batches += 1
                    continue
                if not should_send(to_addr=to_addr, subject=subject):
                    skipped_batches += 1
                    continue
                try:
                    send_using_app_mail_settings(to_addr=to_addr, subject=subject, body=batch.body)
                    sent_at = datetime.now(_UTC)
                    for entry_id in batch.entry_ids:
                        record_sent_ex(
                            to_addr=to_addr,
                            subject=subject,
                            mode=mode,
                            entry_id=str(entry_id or ""),
                            template_name=self._template_name,
                            sent_at=sent_at,
                        )
                    sent_batches += 1
                    sent_to_count += 1
                    last_sent_at_utc = sent_at
                except Exception as exc:
                    errors.append(str(exc))
                    break

            self.finished.emit(
                {
                    "run_token": self._run_token,
                    "mode": mode,
                    "checked_at_utc": checked_at_utc,
                    "entries": filtered,
                    "email_map": email_map,
                    "planned": planned,
                    "excluded_logged": excluded_logged,
                    "unresolved": summary.unresolved_count,
                    "sent_batches": sent_batches,
                    "skipped_batches": skipped_batches,
                    "sent_to_count": sent_to_count,
                    "last_sent_at_utc": last_sent_at_utc,
                    "errors": errors,
                }
            )
        except Exception as exc:
            self.finished.emit(
                {
                    "run_token": self._run_token,
                    "mode": mode,
                    "checked_at_utc": checked_at_utc,
                    "entries": [],
                    "email_map": {},
                    "planned": [],
                    "excluded_logged": 0,
                    "unresolved": 0,
                    "sent_batches": 0,
                    "skipped_batches": 0,
                    "sent_to_count": 0,
                    "last_sent_at_utc": None,
                    "errors": [str(exc)],
                }
            )


class MailNotificationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker: _ExtractWorker | None = None
        self._auto_worker: _AutoRunWorker | None = None
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._on_auto_tick)
        self._auto_run_token: int = 0
        self._auto_mode: Optional[str] = None  # "test" / "production"
        self._targets: List[Dict[str, Any]] = []
        self._email_map: Dict[str, str] = {}
        self._planned_rows: List[PlannedNotificationRow] = []
        self._templates: List[Dict[str, str]] = []
        self._current_template_index: int = 0

        layout = QVBoxLayout(self)

        title = QLabel("メール通知")
        layout.addWidget(title)

        mode_group = QGroupBox("運用モード")
        mode_layout = QHBoxLayout(mode_group)
        self.test_mode_radio = QRadioButton("テスト")
        self.production_mode_radio = QRadioButton("本番")
        self.test_mode_radio.setChecked(True)
        mode_bg = QButtonGroup(self)
        mode_bg.addButton(self.test_mode_radio)
        mode_bg.addButton(self.production_mode_radio)
        mode_layout.addWidget(self.test_mode_radio)
        mode_layout.addWidget(self.production_mode_radio)

        mode_layout.addWidget(QLabel("本番送信先:"))
        self.production_send_creator_checkbox = QCheckBox("投入者")
        self.production_send_owner_checkbox = QCheckBox("所有者")
        self.production_send_equipment_manager_checkbox = QCheckBox("設備管理者")
        self.production_send_creator_checkbox.setChecked(True)
        self.production_send_owner_checkbox.setChecked(True)
        mode_layout.addWidget(self.production_send_creator_checkbox)
        mode_layout.addWidget(self.production_send_owner_checkbox)
        self.production_send_equipment_manager_checkbox.setChecked(False)
        mode_layout.addWidget(self.production_send_equipment_manager_checkbox)

        self.view_log_btn = QPushButton("送信ログ表示")
        self.view_log_btn.clicked.connect(self._show_send_log)
        mode_layout.addWidget(self.view_log_btn)

        self.equipment_manager_btn = QPushButton("設備管理者リスト")
        self.equipment_manager_btn.clicked.connect(self._open_equipment_manager_dialog)
        mode_layout.addWidget(self.equipment_manager_btn)
        mode_layout.addStretch()
        layout.addWidget(mode_group)

        cond_group = QGroupBox("抽出条件（日本時間/JST）")
        cond_layout = QVBoxLayout(cond_group)

        self.mode_reference_radio = QRadioButton("基準日時 + 範囲（日数）")
        self.mode_range_radio = QRadioButton("期間範囲指定（開始〜終了）")
        self.mode_reference_radio.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self.mode_reference_radio)
        bg.addButton(self.mode_range_radio)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_reference_radio)
        mode_row.addWidget(self.mode_range_radio)
        mode_row.addStretch()
        cond_layout.addLayout(mode_row)

        now_jst = datetime.now(_JST).replace(microsecond=0)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("基準日時（JST）:"))
        self.reference_dt = QDateTimeEdit()
        self.reference_dt.setCalendarPopup(True)
        self.reference_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.reference_dt.setDateTime(now_jst)
        ref_row.addWidget(self.reference_dt)

        ref_row.addWidget(QLabel("範囲（日）:"))
        self.range_days_spin = QSpinBox()
        self.range_days_spin.setMinimum(1)
        self.range_days_spin.setMaximum(999)
        self.range_days_spin.setValue(7)
        ref_row.addWidget(self.range_days_spin)
        ref_row.addStretch()
        cond_layout.addLayout(ref_row)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("プリセット:"))
        self._preset_buttons: List[QPushButton] = []
        for days in (1, 3, 7, 30, 180, 365):
            b = QPushButton(f"{days}日")
            b.clicked.connect(lambda _checked=False, d=days: self.range_days_spin.setValue(int(d)))
            preset_row.addWidget(b)
            self._preset_buttons.append(b)
        preset_row.addStretch()
        cond_layout.addLayout(preset_row)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("開始（JST）:"))
        self.start_dt = QDateTimeEdit()
        self.start_dt.setCalendarPopup(True)
        self.start_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.start_dt.setDateTime((now_jst - timedelta(days=1)))
        range_row.addWidget(self.start_dt)

        range_row.addWidget(QLabel("終了（JST）:"))
        self.end_dt = QDateTimeEdit()
        self.end_dt.setCalendarPopup(True)
        self.end_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.end_dt.setDateTime(now_jst)
        range_row.addWidget(self.end_dt)
        range_row.addStretch()
        cond_layout.addLayout(range_row)

        btn_row = QHBoxLayout()
        self.extract_once_btn = QPushButton("通知対象抽出")
        self.extract_once_btn.clicked.connect(self.extract_once)
        btn_row.addWidget(self.extract_once_btn)

        btn_row.addWidget(QLabel("自動インターバル:"))
        self.auto_interval_combo = QComboBox()
        for label, sec in interval_options():
            self.auto_interval_combo.addItem(label, int(sec))
        # 初期値: 60秒
        try:
            idx = self.auto_interval_combo.findData(60)
            if idx >= 0:
                self.auto_interval_combo.setCurrentIndex(idx)
        except Exception:
            pass
        btn_row.addWidget(self.auto_interval_combo)

        self.auto_run_btn = QPushButton("自動実行")
        self.auto_run_btn.setCheckable(True)
        self.auto_run_btn.toggled.connect(self._on_auto_run_toggled)
        btn_row.addWidget(self.auto_run_btn)

        btn_row.addStretch()
        cond_layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        cond_layout.addWidget(self.status_label)

        auto_info_row = QHBoxLayout()
        self.last_check_label = QLabel("最終登録状況確認: -")
        self.last_send_label = QLabel("最終送信: -")
        auto_info_row.addWidget(self.last_check_label)
        auto_info_row.addWidget(self.last_send_label)
        auto_info_row.addStretch()
        cond_layout.addLayout(auto_info_row)

        layout.addWidget(cond_group)

        tmpl_group = QGroupBox("テンプレート")
        tmpl = QVBoxLayout(tmpl_group)

        tmpl_top = QHBoxLayout()
        tmpl_top.addWidget(QLabel("テンプレート:"))
        self.template_combo = QComboBox()
        tmpl_top.addWidget(self.template_combo)
        self.template_edit_btn = QPushButton("編集")
        self.template_edit_btn.clicked.connect(self._edit_template_dialog)
        tmpl_top.addWidget(self.template_edit_btn)
        self.template_new_btn = QPushButton("新規")
        self.template_new_btn.clicked.connect(self._new_template)
        tmpl_top.addWidget(self.template_new_btn)
        self.template_delete_btn = QPushButton("削除")
        self.template_delete_btn.clicked.connect(self._delete_template)
        tmpl_top.addWidget(self.template_delete_btn)
        self.template_save_btn = QPushButton("保存")
        self.template_save_btn.clicked.connect(self._save_templates)
        tmpl_top.addWidget(self.template_save_btn)
        tmpl_top.addStretch()
        tmpl.addLayout(tmpl_top)

        hint = QLabel("件名・本文の編集は『編集』から行ってください。（プレースホルダ一覧も表示されます）")
        hint.setWordWrap(True)
        tmpl.addWidget(hint)
        layout.addWidget(tmpl_group)

        list_group = QGroupBox("通知対象リスト")
        list_layout = QVBoxLayout(list_group)

        # 列定義（要件: 開始時刻, エラーコード, 設備ID, 装置名_日, データセット, データ名, データセットテンプレ, ...）
        self._table_headers = [
            "開始時刻(JST)",
            "エラーコード",
            "設備ID",
            "装置名_日",
            "データセット",
            "データ名",
            "データセットテンプレ",
            "本番通知済み(JST)",
            "投入者（所属）",
            "投入者メール",
            "所有者（所属）",
            "所有者メール",
            "テスト送信先",
            "本番送信先",
            "実送信先",
            "エラーメッセージ",
            "件名",
            "entryId",
        ]
        self._col_entry_id = len(self._table_headers) - 1

        filter_area = QScrollArea(self)
        filter_area.setWidgetResizable(True)
        filter_widget = QWidget(filter_area)
        filter_row = QHBoxLayout(filter_widget)
        filter_row.setContentsMargins(0, 0, 0, 0)
        self._table_filters: List[QLineEdit] = []
        for h in self._table_headers:
            e = QLineEdit()
            e.setPlaceholderText(h)
            e.setClearButtonEnabled(True)
            e.textChanged.connect(self._apply_table_filters)
            e.setMinimumWidth(120)
            self._table_filters.append(e)
            filter_row.addWidget(e)
        filter_row.addStretch()
        filter_area.setWidget(filter_widget)
        list_layout.addWidget(filter_area)

        self.table = QTableWidget(0, len(self._table_headers), self)
        self.table.setHorizontalHeaderLabels(self._table_headers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setTextElideMode(Qt.ElideRight)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            for i in range(len(self._table_headers)):
                header.setSectionResizeMode(i, QHeaderView.Interactive)
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.Stretch)
            header.setSectionResizeMode(4, QHeaderView.Stretch)
            header.setSectionResizeMode(5, QHeaderView.Stretch)
            header.setSectionResizeMode(6, QHeaderView.Stretch)
            header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(9, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(10, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(11, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(12, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(13, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(14, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(15, QHeaderView.Stretch)
            header.setSectionResizeMode(16, QHeaderView.Stretch)
            header.setSectionResizeMode(17, QHeaderView.ResizeToContents)
        except Exception:
            header.setSectionResizeMode(QHeaderView.Interactive)
        list_layout.addWidget(self.table)

        send_row = QHBoxLayout()
        self.send_all_btn = QPushButton("通知実行（全件）")
        self.send_all_btn.clicked.connect(self.send_all)
        send_row.addWidget(self.send_all_btn)
        self.send_selected_btn = QPushButton("通知実行（選択）")
        self.send_selected_btn.clicked.connect(self.send_selected)
        send_row.addWidget(self.send_selected_btn)
        send_row.addStretch()
        list_layout.addLayout(send_row)

        self.table.cellClicked.connect(self._on_row_clicked)

        layout.addWidget(list_group)
        layout.addStretch()

        self.mode_reference_radio.toggled.connect(self._sync_mode_controls)
        self.mode_range_radio.toggled.connect(self._sync_mode_controls)
        self._sync_mode_controls()

        self._load_templates()
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        self.production_send_creator_checkbox.toggled.connect(self._on_production_recipient_toggled)
        self.production_send_owner_checkbox.toggled.connect(self._on_production_recipient_toggled)
        self.production_send_equipment_manager_checkbox.toggled.connect(self._on_production_recipient_toggled)

        self._set_status("条件を設定して『通知対象抽出』を実行してください。", ThemeKey.TEXT_MUTED)

        # モードUI
        self.test_mode_radio.toggled.connect(self._sync_mode_controls)
        self.production_mode_radio.toggled.connect(self._sync_mode_controls)
        self._sync_mode_controls()

        # 自動実行ボタンのラベルを運用モードに追従
        self.test_mode_radio.toggled.connect(self._refresh_auto_run_button_text)
        self.production_mode_radio.toggled.connect(self._refresh_auto_run_button_text)
        self._refresh_auto_run_button_text()

    def closeEvent(self, event):
        # 破棄タイミングで QThread が生存していると
        # "Destroyed while thread is still running" が出るため、明示的に停止要求する。
        try:
            self._stop_auto_run()
        except Exception:
            pass
        try:
            return super().closeEvent(event)
        except Exception:
            # qt_compat 経由で super の解決が崩れるケースに備える
            event.accept()

    def _auto_is_running(self) -> bool:
        return self._auto_mode in ("test", "production")

    def _auto_worker_is_running(self) -> bool:
        w = self._auto_worker
        if w is None:
            return False
        try:
            return bool(w.isRunning())
        except RuntimeError:
            # Qt側で deleteLater 済みなど
            self._auto_worker = None
            return False

    def _refresh_auto_run_button_text(self):
        try:
            if not getattr(self, "auto_run_btn", None):
                return
            mode = "本番" if self._is_production_mode() else "テスト"
            if self._auto_is_running():
                running_mode = "本番" if self._auto_mode == "production" else "テスト"
                self.auto_run_btn.setText(f"停止（{running_mode}）")
            else:
                self.auto_run_btn.setText(f"自動実行（{mode}）")
        except Exception:
            pass

    def _confirm_auto_run(self, *, action: str, mode: str) -> bool:
        # action: "start" | "stop"
        title = "自動実行" if action == "start" else "自動実行停止"
        mode_label = "本番" if mode == "production" else "テスト"
        if action == "start":
            msg = f"自動実行（{mode_label}）を開始します。よろしいですか？"
        else:
            msg = f"自動実行（{mode_label}）を停止します。よろしいですか？"
        ret = QMessageBox.question(self, title, msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return ret == QMessageBox.Yes

    def _current_template_subject(self) -> str:
        idx = int(self._current_template_index)
        if 0 <= idx < len(self._templates):
            return str(self._templates[idx].get("subject") or "")
        return ""

    def _current_template_body(self) -> str:
        idx = int(self._current_template_index)
        if 0 <= idx < len(self._templates):
            return str(self._templates[idx].get("body") or "")
        return ""

    def _on_production_recipient_toggled(self):
        # 本番送信先は最低1つ必要（最後の1つは外せない）
        if (
            not self.production_send_creator_checkbox.isChecked()
            and not self.production_send_owner_checkbox.isChecked()
            and not self.production_send_equipment_manager_checkbox.isChecked()
        ):
            # 直前の操作で全て外れたケースは、投入者を復帰させる
            self.production_send_creator_checkbox.blockSignals(True)
            self.production_send_creator_checkbox.setChecked(True)
            self.production_send_creator_checkbox.blockSignals(False)

    def _include_creator_in_production(self) -> bool:
        return bool(getattr(self, "production_send_creator_checkbox", None) and self.production_send_creator_checkbox.isChecked())

    def _include_owner_in_production(self) -> bool:
        return bool(getattr(self, "production_send_owner_checkbox", None) and self.production_send_owner_checkbox.isChecked())

    def _include_equipment_manager_in_production(self) -> bool:
        return bool(
            getattr(self, "production_send_equipment_manager_checkbox", None)
            and self.production_send_equipment_manager_checkbox.isChecked()
        )

    def _load_templates(self):
        mgr = get_config_manager()
        templates = None
        try:
            templates = mgr.get("mail.notification.templates", None)
        except Exception:
            templates = None

        if not isinstance(templates, list) or not templates:
            templates = [
                {
                    "name": "デフォルト",
                    "subject": "[RDE] 登録失敗: {dataName} ({entryId})",
                    "body": (
                        "登録状況: FAILED\n"
                        "開始時刻(JST): {startTime}\n"
                        "データ名: {dataName}\n"
                        "データセット: {datasetName}\n"
                        "データセットテンプレ: {datasetTemplateName}\n"
                        "設備ID: {equipmentId}\n"
                        "装置名_日: {deviceNameJa}\n"
                        "エラーコード: {errorCode}\n"
                        "エラーメッセージ: {errorMessage}\n"
                        "投入者: {createdByName} <{createdByMail}>\n"
                        "所有者: {dataOwnerName} <{dataOwnerMail}>\n"
                        "エントリID: {entryId}\n"
                    ),
                }
            ]

        self._templates = [
            {
                "name": str(t.get("name") or "").strip() or f"テンプレ{i+1}",
                "subject": str(t.get("subject") or ""),
                "body": str(t.get("body") or ""),
            }
            for i, t in enumerate(templates)
            if isinstance(t, dict)
        ]
        if not self._templates:
            self._templates = [{"name": "デフォルト", "subject": "", "body": ""}]

        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for t in self._templates:
            self.template_combo.addItem(t["name"])
        self.template_combo.blockSignals(False)

        self._current_template_index = 0
        self.template_combo.setCurrentIndex(0)
        # 旧UI互換: エディタは廃止したため、ここではindexのみ合わせる

    def _save_templates(self):
        try:
            mgr = get_config_manager()
            mgr.set("mail.notification.templates", list(self._templates))
            mgr.save()
            self._set_status("テンプレートを保存しました。", ThemeKey.TEXT_SUCCESS)
        except Exception as exc:
            self._set_status(f"テンプレート保存に失敗: {exc}", ThemeKey.TEXT_ERROR)

    def _new_template(self):
        name, ok = QInputDialog.getText(self, "テンプレート新規作成", "テンプレート名:")
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        existing = {t["name"] for t in self._templates}
        if name in existing:
            self._set_status("同名テンプレートが既に存在します。", ThemeKey.TEXT_WARNING)
            return

        self._templates.append(
            {
                "name": name,
                "subject": self._current_template_subject() or "[RDE] 登録失敗: {dataName} ({entryId})",
                "body": self._current_template_body()
                or (
                    "登録状況: FAILED\n"
                    "開始時刻(JST): {startTime}\n"
                    "データ名: {dataName}\n"
                    "データセット: {datasetName}\n"
                    "データセットテンプレ: {datasetTemplateName}\n"
                    "設備ID: {equipmentId}\n"
                    "装置名_日: {deviceNameJa}\n"
                    "エラーコード: {errorCode}\n"
                    "エラーメッセージ: {errorMessage}\n"
                    "投入者: {createdByName} <{createdByMail}>\n"
                    "所有者: {dataOwnerName} <{dataOwnerMail}>\n"
                    "エントリID: {entryId}\n"
                ),
            }
        )
        self.template_combo.addItem(name)
        self.template_combo.setCurrentIndex(len(self._templates) - 1)
        self._edit_template_dialog()

    def _delete_template(self):
        if len(self._templates) <= 1:
            self._set_status("テンプレートは1つ以上必要です。", ThemeKey.TEXT_WARNING)
            return
        idx = int(self.template_combo.currentIndex())
        if idx < 0 or idx >= len(self._templates):
            return
        name = self._templates[idx].get("name") or ""
        ret = QMessageBox.question(
            self,
            "テンプレート削除",
            f"テンプレート『{name}』を削除します。よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        self._templates.pop(idx)
        self.template_combo.removeItem(idx)
        new_idx = max(0, idx - 1)
        self.template_combo.setCurrentIndex(new_idx)

    def _on_template_changed(self, idx: int):
        self._current_template_index = max(0, int(idx))
        # 既に抽出済みなら、テンプレ変更に合わせて表を更新
        try:
            if self._targets:
                self._rebuild_and_render()
        except Exception:
            pass

    def _edit_template_dialog(self):
        idx = int(self._current_template_index)
        if idx < 0 or idx >= len(self._templates):
            return
        t = self._templates[idx]
        dlg = _TemplateEditDialog(
            self,
            template_name=str(t.get("name") or ""),
            subject=str(t.get("subject") or ""),
            body=str(t.get("body") or ""),
        )
        if dlg.exec() != QDialog.Accepted:
            return
        subj, body = dlg.values()
        self._templates[idx]["subject"] = subj
        self._templates[idx]["body"] = body
        # 表示中の候補もテンプレ適用結果が変わるため更新
        if self._targets:
            self._rebuild_and_render()

    def _sync_mode_controls(self):
        ref_on = self.mode_reference_radio.isChecked()
        self.reference_dt.setEnabled(ref_on)
        self.range_days_spin.setEnabled(ref_on)
        self.start_dt.setEnabled(not ref_on)
        self.end_dt.setEnabled(not ref_on)

        is_prod = self._is_production_mode()
        self.production_send_creator_checkbox.setEnabled(is_prod)
        self.production_send_owner_checkbox.setEnabled(is_prod)
        self.production_send_equipment_manager_checkbox.setEnabled(is_prod)

    def _is_production_mode(self) -> bool:
        return bool(getattr(self, "production_mode_radio", None) and self.production_mode_radio.isChecked())

    def _set_status(self, message: str, theme_key: ThemeKey | None):
        color = get_color(theme_key or ThemeKey.TEXT_MUTED)
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)

    def _apply_table_filters(self):
        filters = []
        try:
            filters = [(f.text() or "").strip().lower() for f in (getattr(self, "_table_filters", []) or [])]
        except Exception:
            filters = []

        if not filters:
            return

        for r in range(self.table.rowCount()):
            hide = False
            for c, t in enumerate(filters):
                if not t:
                    continue
                item = self.table.item(r, c)
                cell = (item.text() if item else "").lower()
                if t not in cell:
                    hide = True
                    break
            self.table.setRowHidden(r, hide)

    def _show_send_log(self):
        try:
            items = load_history(limit=200)
        except Exception:
            items = []

        if not items:
            QMessageBox.information(self, "送信ログ", "送信ログがありません。")
            return

        dlg = _SendLogDialog(self, items=items)
        dlg.exec()

    def _open_equipment_manager_dialog(self):
        dlg = EquipmentManagerListDialog(self)
        if dlg.exec() == QDialog.Accepted:
            # 保存後、抽出済みの表示・テンプレ置換結果も変わるため更新
            try:
                if self._targets:
                    self._rebuild_and_render()
            except Exception:
                pass

    def _test_to_address(self) -> str:
        try:
            mgr = get_config_manager()
            return str(mgr.get("mail.test.to_address", "") or "").strip()
        except Exception:
            return ""

    def _selected_interval_seconds(self) -> int:
        try:
            sec = int(self.auto_interval_combo.currentData())
            return sec if sec > 0 else 60
        except Exception:
            return 60

    def _on_auto_run_toggled(self, checked: bool):
        # 自動実行のモードは「運用モード」設定で決める
        current_mode = "production" if self._is_production_mode() else "test"

        if checked:
            if not self._confirm_auto_run(action="start", mode=current_mode):
                try:
                    self.auto_run_btn.blockSignals(True)
                    self.auto_run_btn.setChecked(False)
                finally:
                    self.auto_run_btn.blockSignals(False)
                self._refresh_auto_run_button_text()
                return
            self._start_auto_run(mode=current_mode)
        else:
            # 未起動なら何もしない
            if not self._auto_is_running():
                self._refresh_auto_run_button_text()
                return
            if not self._confirm_auto_run(action="stop", mode=self._auto_mode or current_mode):
                # 停止キャンセル → 走り続ける
                try:
                    self.auto_run_btn.blockSignals(True)
                    self.auto_run_btn.setChecked(True)
                finally:
                    self.auto_run_btn.blockSignals(False)
                self._refresh_auto_run_button_text()
                return
            self._stop_auto_run()

    def _start_auto_run(self, *, mode: str):
        # mode: "test" | "production"
        if self._auto_worker_is_running():
            self._set_status("自動実行が停止処理中です。少し待ってから再度開始してください。", ThemeKey.TEXT_WARNING)
            try:
                self.auto_run_btn.blockSignals(True)
                self.auto_run_btn.setChecked(False)
            finally:
                self.auto_run_btn.blockSignals(False)
            self._refresh_auto_run_button_text()
            return

        self._stop_auto_run(invalidate_only=True)

        production_mode = mode == "production"
        if production_mode:
            if not (
                self._include_creator_in_production()
                or self._include_owner_in_production()
                or self._include_equipment_manager_in_production()
            ):
                self._set_status("本番送信先が未選択です（投入者/所有者/設備管理者のいずれかは必須）。", ThemeKey.TEXT_WARNING)
                try:
                    self.auto_run_btn.blockSignals(True)
                    self.auto_run_btn.setChecked(False)
                finally:
                    self.auto_run_btn.blockSignals(False)
                self._refresh_auto_run_button_text()
                return
        else:
            if not self._test_to_address():
                self._set_status("テスト運用の送信先(To)が未設定です（設定→メール→テストメール）。", ThemeKey.TEXT_WARNING)
                try:
                    self.auto_run_btn.blockSignals(True)
                    self.auto_run_btn.setChecked(False)
                finally:
                    self.auto_run_btn.blockSignals(False)
                self._refresh_auto_run_button_text()
                return

            # 要件: テスト自動実行開始時、テストモード分だけログをクリア（本番は残す）
            try:
                removed = clear_history_by_mode(mode="test")
                if removed:
                    self._set_status(f"テスト送信ログをクリアしました: {removed}件", ThemeKey.TEXT_INFO)
            except Exception:
                pass

        self._auto_run_token += 1
        self._auto_mode = mode
        self._refresh_auto_run_button_text()

        self._run_auto_once(self._auto_run_token)
        try:
            self._auto_timer.start(int(self._selected_interval_seconds() * 1000))
        except Exception:
            self._auto_timer.start(int(60 * 1000))

    def _stop_auto_run(self, *, invalidate_only: bool = False):
        try:
            if self._auto_timer.isActive():
                self._auto_timer.stop()
        except Exception:
            pass

        # 進行中の worker 結果を無効化
        self._auto_run_token += 1

        # 進行中スレッドには中断を要求（destroyed while running 対策）
        try:
            if self._auto_worker is not None and self._auto_worker.isRunning():
                self._auto_worker.requestInterruption()
        except Exception:
            pass

        self._auto_mode = None
        if invalidate_only:
            # start 前の初期化用途（ボタン状態は呼び出し元で調整）
            return

        try:
            self.auto_run_btn.blockSignals(True)
            self.auto_run_btn.setChecked(False)
        except Exception:
            pass
        finally:
            try:
                self.auto_run_btn.blockSignals(False)
            except Exception:
                pass

        self._refresh_auto_run_button_text()

    def _on_auto_tick(self):
        if self._auto_mode not in ("test", "production"):
            return
        if self._auto_worker_is_running():
            return
        self._run_auto_once(self._auto_run_token)

    def _run_auto_once(self, run_token: int):
        production = self._auto_mode == "production"
        days = int(self.range_days_spin.value())

        include_creator = self._include_creator_in_production()
        include_owner = self._include_owner_in_production()
        include_equipment_manager = self._include_equipment_manager_in_production()
        test_to = self._test_to_address()

        tmpl_name = ""
        try:
            tmpl_name = str(self._templates[int(self._current_template_index)].get("name") or "")
        except Exception:
            tmpl_name = ""

        app_parent = QApplication.instance()
        self._auto_worker = _AutoRunWorker(
            app_parent,
            run_token=run_token,
            range_days=days,
            production_mode=production,
            include_creator=include_creator,
            include_owner=include_owner,
            include_equipment_manager=include_equipment_manager,
            test_to_address=test_to,
            subject_template=self._current_template_subject(),
            body_template=self._current_template_body(),
            template_name=tmpl_name,
            build_email_map=self._build_email_map,
            augment_entries_for_display=self._augment_entries_for_display,
        )
        self._auto_worker.finished.connect(self._on_auto_finished)
        # 完了後に安全に破棄
        try:
            self._auto_worker.finished.connect(self._auto_worker.deleteLater)
        except Exception:
            pass
        self._auto_worker.start()

    def _on_auto_finished(self, result: Dict[str, Any]):
        try:
            if int(result.get("run_token") or 0) != int(self._auto_run_token):
                return
        except Exception:
            return

        # finished を受け取った時点で、次回起動に備えて参照を外す
        # （Qt側は deleteLater で消える可能性がある）
        self._auto_worker = None

        checked_at_utc = result.get("checked_at_utc")
        if isinstance(checked_at_utc, datetime):
            try:
                jst = checked_at_utc.astimezone(_JST)
                self.last_check_label.setText(f"最終登録状況確認: {jst.strftime('%Y-%m-%d %H:%M')}")
            except Exception:
                pass

        entries = result.get("entries") or []
        planned = result.get("planned") or []
        email_map = result.get("email_map") or {}

        try:
            self._targets = list(entries)
            self._planned_rows = list(planned)
            self._email_map = dict(email_map)
            self._render_table(self._planned_rows)
        except Exception:
            pass

        errors = result.get("errors") or []
        if errors:
            self._set_status(f"自動実行エラー: {errors[0]}", ThemeKey.TEXT_ERROR)
            return

        sent_batches = int(result.get("sent_batches") or 0)
        sent_to_count = int(result.get("sent_to_count") or 0)
        skipped_batches = int(result.get("skipped_batches") or 0)
        excluded_logged = int(result.get("excluded_logged") or 0)
        unresolved = int(result.get("unresolved") or 0)

        last_sent_at_utc = result.get("last_sent_at_utc")
        if isinstance(last_sent_at_utc, datetime) and sent_batches > 0:
            try:
                jst = last_sent_at_utc.astimezone(_JST)
                self.last_send_label.setText(f"最終送信: {jst.strftime('%Y-%m-%d %H:%M')}（宛先{sent_to_count}件）")
            except Exception:
                pass

        try:
            if self._auto_mode == "production" and sent_batches > 0:
                self._rebuild_and_render()
        except Exception:
            pass

        self._set_status(
            f"自動実行: 対象={len(planned)}件, 除外(ログ)={excluded_logged}件, 未解決={unresolved}件, 送信={sent_batches}通, skip={skipped_batches}通",
            ThemeKey.TEXT_SUCCESS,
        )

        # 停止/モード変更によりUI側のチェックが外れている場合でも、表示は整合させる
        self._refresh_auto_run_button_text()

    def extract_once(self):
        if self._worker is not None and self._worker.isRunning():
            return

        if self.mode_reference_radio.isChecked():
            ref_jst = _dtedit_to_jst(self.reference_dt)
            ref_utc = ref_jst.astimezone(_UTC)
            days = int(self.range_days_spin.value())
            self._worker = _ExtractWorker(mode="reference", reference_utc=ref_utc, range_days=days, start_utc=None, end_utc=None)
        else:
            start_jst = _dtedit_to_jst(self.start_dt)
            end_jst = _dtedit_to_jst(self.end_dt)
            if end_jst < start_jst:
                self._set_status("期間範囲が不正です（終了が開始より前です）。", ThemeKey.TEXT_ERROR)
                return
            self._worker = _ExtractWorker(
                mode="range",
                reference_utc=None,
                range_days=1,
                start_utc=start_jst.astimezone(_UTC),
                end_utc=end_jst.astimezone(_UTC),
            )

        self.extract_once_btn.setEnabled(False)
        self._set_status("抽出中...", ThemeKey.TEXT_INFO)
        self._worker.finished.connect(self._on_extracted)
        self._worker.start()

    def _on_extracted(self, selected: List[Dict[str, Any]]):
        self.extract_once_btn.setEnabled(True)

        self._email_map = self._build_email_map(selected)

        self._augment_entries_for_display(selected)

        production = self._is_production_mode()
        try:
            production_sent_at_by_entry_id = load_last_sent_at_by_entry_id(mode="production")
        except Exception:
            production_sent_at_by_entry_id = {}
        planned = build_planned_notification_rows(
            entries=selected,
            email_map=self._email_map,
            production_mode=production,
            include_creator=self._include_creator_in_production(),
            include_owner=self._include_owner_in_production(),
            include_equipment_manager=self._include_equipment_manager_in_production(),
            test_to_address=self._test_to_address(),
            subject_template=self._current_template_subject(),
            body_template=self._current_template_body(),
            production_sent_at_by_entry_id=production_sent_at_by_entry_id,
        )

        self._targets = selected
        self._planned_rows = planned
        self._render_table(planned)
        self._set_status(f"抽出完了: {len(planned)} 件", ThemeKey.TEXT_SUCCESS)

    def _augment_entries_for_display(self, entries: List[Dict[str, Any]]):
        # dataset template name
        try:
            entry_ids = [str((e or {}).get("id") or "").strip() for e in entries or []]
            tmpl_map = build_dataset_template_name_map_for_entry_ids([eid for eid in entry_ids if eid])
        except Exception:
            tmpl_map = {}

        # equipment name lookup cache (merged_data2)
        try:
            name_map = load_equipment_name_map_from_merged_data2()
        except Exception:
            name_map = None

        # instrument uuid -> localId (instruments.json)
        try:
            local_id_map = load_instrument_local_id_map_from_instruments_json()
        except Exception:
            local_id_map = None

        # equipment manager store (input/equipment_managers.json)
        try:
            manager_map = equipment_manager_store.load_equipment_managers()
        except Exception:
            manager_map = {}

        for e in entries or []:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id") or "")
            if eid and eid in tmpl_map:
                e["datasetTemplateName"] = tmpl_map.get(eid) or ""

            # 装置名_日: 登録状況サマリの instrumentNameJa を優先
            dev_ja = str(e.get("instrumentNameJa") or "").strip()
            dev_en = str(e.get("instrumentNameEn") or "").strip()

            # equipmentId: merged_data2 の「設備ID」を優先（装置名から逆引き→文字列から抽出→既存値）
            equip_id = ""
            instrument_uuid = str(e.get("instrumentId") or "").strip()
            try:
                equip_id = (lookup_equipment_id_by_device_name(dev_ja, dev_en, name_map=name_map) or "").strip()
            except Exception:
                equip_id = ""
            if not equip_id:
                equip_id = (extract_equipment_id(dev_ja) or "").strip()
            if not equip_id:
                equip_id = (extract_equipment_id(dev_en) or "").strip()
            if not equip_id:
                # フォールバック: instruments.json の localId を採用
                try:
                    equip_id = (lookup_instrument_local_id(instrument_uuid, local_id_map=local_id_map) or "").strip()
                except Exception:
                    equip_id = ""
            if not equip_id:
                # 最後のフォールバック: instrumentId が既に設備ID形式なら採用
                extracted = (extract_equipment_id(instrument_uuid) or "").strip()
                equip_id = extracted or ""

            if equip_id:
                e["equipmentId"] = equip_id

            # 設備管理者プレースホルダ
            try:
                managers = (manager_map or {}).get(str(e.get("equipmentId") or "").strip(), [])
                names, emails, notes = equipment_manager_store.managers_to_placeholder_fields(managers)
                e["equipmentManagerNames"] = names
                e["equipmentManagerEmails"] = emails
                e["equipmentManagerNotes"] = notes
            except Exception:
                # フォールバック: 空
                e["equipmentManagerNames"] = e.get("equipmentManagerNames") or ""
                e["equipmentManagerEmails"] = e.get("equipmentManagerEmails") or ""
                e["equipmentManagerNotes"] = e.get("equipmentManagerNotes") or ""

            # 装置名_日が空なら merged_data2 から補完
            if not dev_ja and equip_id:
                try:
                    dev_ja = lookup_device_name_ja(equip_id, name_map=name_map) or ""
                except Exception:
                    dev_ja = ""
            if dev_ja:
                e["deviceNameJa"] = dev_ja

    def _rebuild_and_render(self):
        production = self._is_production_mode()
        try:
            production_sent_at_by_entry_id = load_last_sent_at_by_entry_id(mode="production")
        except Exception:
            production_sent_at_by_entry_id = {}
        planned = build_planned_notification_rows(
            entries=self._targets,
            email_map=self._email_map,
            production_mode=production,
            include_creator=self._include_creator_in_production(),
            include_owner=self._include_owner_in_production(),
            include_equipment_manager=self._include_equipment_manager_in_production(),
            test_to_address=self._test_to_address(),
            subject_template=self._current_template_subject(),
            body_template=self._current_template_body(),
            production_sent_at_by_entry_id=production_sent_at_by_entry_id,
        )
        self._planned_rows = planned
        self._render_table(planned)

    def _build_email_map(self, entries: List[Dict[str, Any]]) -> Dict[str, str]:
        # 1) エントリ→dataset→groupId から、複数グループを跨いでメールを合成（実データの解決率優先）
        entry_ids = [str((e or {}).get("id") or "").strip() for e in (entries or [])]
        email_map: Dict[str, str] = {}
        try:
            email_map.update(build_email_map_for_entry_ids([eid for eid in entry_ids if eid]))
        except Exception:
            pass

        # 2) subGroup.json(included user) を不足補完として使う（従来方式）
        try:
            users = SubgroupDataManager.load_user_entries()
            if users and not isinstance(users, str):
                user_map = SubgroupDataManager.create_user_map(users)
                for uid, info in (user_map or {}).items():
                    email = str((info or {}).get("emailAddress") or "").strip()
                    if uid and email:
                        email_map.setdefault(str(uid), email)
        except Exception:
            pass

        # 3) 選択サブグループの詳細キャッシュ（なければAPIフォールバック）も補完として使う
        try:
            selected_group_id = _load_selected_subgroup_id()
        except Exception:
            selected_group_id = ""
        if selected_group_id:
            try:
                users = load_group_members(selected_group_id)
            except Exception:
                users = []
            for u in users or []:
                uid = str(u.get("id") or "").strip()
                attr = u.get("attributes") or {}
                email = (
                    str(attr.get("emailAddress") or "")
                    or str(attr.get("email") or "")
                    or str(attr.get("mailAddress") or "")
                ).strip()
                if uid and email:
                    email_map.setdefault(uid, email)

        return email_map

    def _render_table(self, planned: List[PlannedNotificationRow]):
        # ソート有効のまま行を追加すると、行が途中で並び替えられて
        # setItem() の row インデックスがズレ、各列が空欄に見えることがある。
        was_sorting = False
        try:
            was_sorting = bool(self.table.isSortingEnabled())
            if was_sorting:
                self.table.setSortingEnabled(False)
        except Exception:
            was_sorting = False

        self.table.setRowCount(0)

        for r in planned:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r.start_time_jst))
            self.table.setItem(row, 1, QTableWidgetItem(r.error_code))
            self.table.setItem(row, 2, QTableWidgetItem(r.equipment_id))
            self.table.setItem(row, 3, QTableWidgetItem(r.device_name_ja))
            self.table.setItem(row, 4, QTableWidgetItem(r.dataset_name))
            self.table.setItem(row, 5, QTableWidgetItem(r.data_name))
            self.table.setItem(row, 6, QTableWidgetItem(r.dataset_template_name))
            self.table.setItem(row, 7, QTableWidgetItem(_format_iso_to_jst(r.production_sent_at)))
            created_display = (r.created_name or "")
            if r.created_org:
                created_display = f"{created_display} ({r.created_org})" if created_display else f"({r.created_org})"
            owner_display = (r.owner_name or "")
            if r.owner_org:
                owner_display = f"{owner_display} ({r.owner_org})" if owner_display else f"({r.owner_org})"

            self.table.setItem(row, 8, QTableWidgetItem(created_display))
            self.table.setItem(row, 9, QTableWidgetItem(r.created_mail))
            self.table.setItem(row, 10, QTableWidgetItem(owner_display))
            self.table.setItem(row, 11, QTableWidgetItem(r.owner_mail))
            self.table.setItem(row, 12, QTableWidgetItem(r.test_to))
            self.table.setItem(row, 13, QTableWidgetItem(r.production_to))
            self.table.setItem(row, 14, QTableWidgetItem(r.effective_to))
            self.table.setItem(row, 15, QTableWidgetItem(r.error_message))
            self.table.setItem(row, 16, QTableWidgetItem(r.subject))
            self.table.setItem(row, 17, QTableWidgetItem(r.entry_id))

            # 長文は省略表示＋ツールチップで全文
            try:
                if self.table.item(row, 15):
                    self.table.item(row, 15).setToolTip(r.error_message)
                if self.table.item(row, 16):
                    self.table.item(row, 16).setToolTip(r.subject)
            except Exception:
                pass

        # Stretch指定済みのため resizeColumnsToContents は基本不要

        try:
            if was_sorting:
                self.table.setSortingEnabled(True)
        except Exception:
            pass

        # フィルタ再適用
        try:
            self._apply_table_filters()
        except Exception:
            pass

    def _effective_to_addr(self, real_to: str, *, production_mode: bool) -> str:
        if production_mode:
            return (real_to or "").strip()
        return self._test_to_address()

    def _unique_in_order(self, values: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for v in values:
            vv = (v or "").strip()
            if not vv:
                continue
            if vv in seen:
                continue
            seen.add(vv)
            result.append(vv)
        return result

    def _find_entry_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        for e in self._targets or []:
            if str(e.get("id") or "") == str(entry_id or ""):
                return e
        return None

    def _send_for_entry(
        self,
        entry: Dict[str, Any],
        quiet: bool = False,
        *,
        force_production_mode: Optional[bool] = None,
        include_creator: Optional[bool] = None,
        include_owner: Optional[bool] = None,
        include_equipment_manager: Optional[bool] = None,
    ) -> Tuple[int, int]:
        row_map = None
        for r in self._planned_rows:
            if r.entry_id == str(entry.get("id") or ""):
                row_map = r
                break

        subject = row_map.subject if row_map else (self._current_template_subject() or "")
        body = row_map.body if row_map else (self._current_template_body() or "")

        created_id = str(entry.get("createdByUserId") or "")
        owner_id = str(entry.get("dataOwnerUserId") or "")
        created_mail = (self._email_map.get(created_id) or "").strip()
        owner_mail = (self._email_map.get(owner_id) or "").strip()

        production = bool(force_production_mode) if force_production_mode is not None else self._is_production_mode()
        mode = "production" if production else "test"

        tmpl_name = ""
        try:
            tmpl_name = str(self._templates[int(self._current_template_index)].get("name") or "")
        except Exception:
            tmpl_name = ""
        if production:
            use_creator = self._include_creator_in_production() if include_creator is None else bool(include_creator)
            use_owner = self._include_owner_in_production() if include_owner is None else bool(include_owner)
            use_equipment_manager = (
                self._include_equipment_manager_in_production()
                if include_equipment_manager is None
                else bool(include_equipment_manager)
            )
            if not use_creator and not use_owner and not use_equipment_manager:
                if not quiet:
                    self._set_status("本番送信先が未選択です（投入者/所有者/設備管理者のいずれかは必須）。", ThemeKey.TEXT_WARNING)
                return (0, 1)
            real_targets: List[str] = []
            if use_creator:
                real_targets.append(created_mail)
            if use_owner:
                real_targets.append(owner_mail)
            if use_equipment_manager:
                try:
                    real_targets.extend(list(getattr(row_map, "equipment_manager_emails", ()) or ()))
                except Exception:
                    pass
            targets = self._unique_in_order(real_targets)

            if not targets:
                if not quiet:
                    self._set_status("本番送信先のメールアドレスが解決できません。", ThemeKey.TEXT_WARNING)
                return (0, 1)
        else:
            test_to = self._test_to_address()
            if not test_to:
                if not quiet:
                    self._set_status("テスト運用の送信先(To)が未設定です（設定→メール→テストメール）。", ThemeKey.TEXT_WARNING)
                return (0, 1)
            # テスト運用は実宛先の解決有無に関わらず、確認用に test_to へ1通送る
            targets = [test_to]

        sent = 0
        skipped = 0
        for real_to in targets:
            effective_to = self._effective_to_addr(real_to, production_mode=production)
            if not effective_to:
                skipped += 1
                continue
            if not should_send(to_addr=effective_to, subject=subject):
                skipped += 1
                continue

            try:
                send_using_app_mail_settings(to_addr=effective_to, subject=subject, body=body)
                record_sent_ex(
                    to_addr=effective_to,
                    subject=subject,
                    mode=mode,
                    entry_id=str(entry.get("id") or ""),
                    template_name=tmpl_name,
                )
                sent += 1
            except Exception as exc:
                logger.debug("send failed: %s", exc)
                if not quiet:
                    self._set_status(f"送信失敗: {exc}", ThemeKey.TEXT_ERROR)
                return (sent, skipped)

        if not quiet:
            self._set_status(f"個別送信完了: sent={sent}, skipped={skipped}", ThemeKey.TEXT_SUCCESS)

        # 本番送信のログ反映（本番通知済み列）
        try:
            if production and sent > 0:
                self._rebuild_and_render()
        except Exception:
            pass
        return (sent, skipped)

    def _on_row_clicked(self, row: int, col: int):
        try:
            entry_id = self.table.item(row, self._col_entry_id).text() if self.table.item(row, self._col_entry_id) else ""
        except Exception:
            entry_id = ""
        if not entry_id:
            return

        entry = self._find_entry_by_id(entry_id)
        if not entry:
            return

        planned_row = None
        for r in self._planned_rows:
            if r.entry_id == str(entry_id):
                planned_row = r
                break
        if not planned_row:
            return

        tmpl_name = ""
        try:
            tmpl_name = str(self._templates[int(self._current_template_index)].get("name") or "")
        except Exception:
            tmpl_name = ""

        dlg = _NotificationConfirmDialog(self, template_name=tmpl_name, row=planned_row)

        def _do_send_test():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("テスト送信の確認")
            box.setText("テスト送信を実行します。\nキャンセルできます。")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() != QMessageBox.Yes:
                return
            s, k = self._send_for_entry(entry, quiet=True, force_production_mode=False)
            self._set_status(f"テスト送信: sent={s}, skipped={k}", ThemeKey.TEXT_SUCCESS if s else ThemeKey.TEXT_WARNING)
            dlg.accept()

        def _do_send_prod():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("本番送信の確認")
            box.setText("本番送信を実行します。\nキャンセルできます。")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() != QMessageBox.Yes:
                return
            s, k = self._send_for_entry(
                entry,
                quiet=True,
                force_production_mode=True,
                include_creator=self._include_creator_in_production(),
                include_owner=self._include_owner_in_production(),
                include_equipment_manager=self._include_equipment_manager_in_production(),
            )
            self._set_status(f"本番送信: sent={s}, skipped={k}", ThemeKey.TEXT_SUCCESS if s else ThemeKey.TEXT_WARNING)
            dlg.accept()

        dlg.send_test_btn.clicked.connect(_do_send_test)
        dlg.send_prod_btn.clicked.connect(_do_send_prod)
        dlg.exec()

    def send_all(self):
        if not self._targets:
            self._set_status("対象がありません。", ThemeKey.TEXT_WARNING)
            return

        if not self._confirm_send(self._targets):
            return

        sent = 0
        skipped = 0
        for e in self._targets:
            s, k = self._send_for_entry(e, quiet=True)
            sent += s
            skipped += k

        self._set_status(f"通知完了: sent={sent}, skipped={skipped}", ThemeKey.TEXT_SUCCESS)

    def send_selected(self):
        selected_entries = self._get_selected_entries()
        if not selected_entries:
            self._set_status("対象行が選択されていません。", ThemeKey.TEXT_WARNING)
            return

        if not self._confirm_send(selected_entries):
            return

        sent = 0
        skipped = 0
        for e in selected_entries:
            s, k = self._send_for_entry(e, quiet=True)
            sent += s
            skipped += k
        self._set_status(f"通知完了（選択）: sent={sent}, skipped={skipped}", ThemeKey.TEXT_SUCCESS)

    def _get_selected_entries(self) -> List[Dict[str, Any]]:
        try:
            rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        except Exception:
            rows = []
        entry_ids: List[str] = []
        for r in rows:
            try:
                # entryId列（最終列）から取得
                entry_ids.append(self.table.item(r, self._col_entry_id).text())
            except Exception:
                continue
        entries: List[Dict[str, Any]] = []
        for eid in entry_ids:
            e = self._find_entry_by_id(eid)
            if e:
                entries.append(e)
        return entries

    def _confirm_send(self, entries: List[Dict[str, Any]]) -> bool:
        # 宛先解決（投入者/所有者/設備管理者×件数）
        production = self._is_production_mode()
        test_to = self._test_to_address()
        recipients: List[str] = []
        unresolved = 0

        include_creator = self._include_creator_in_production()
        include_owner = self._include_owner_in_production()
        include_equipment_manager = self._include_equipment_manager_in_production()
        if production and not (include_creator or include_owner or include_equipment_manager):
            self._set_status("本番送信先が未選択です（投入者/所有者/設備管理者のいずれかは必須）。", ThemeKey.TEXT_WARNING)
            return False

        for e in entries or []:
            row_map = None
            try:
                eid = str(e.get("id") or "")
                for r in self._planned_rows:
                    if r.entry_id == eid:
                        row_map = r
                        break
            except Exception:
                row_map = None

            created_id = str(e.get("createdByUserId") or "")
            owner_id = str(e.get("dataOwnerUserId") or "")
            created_mail = (self._email_map.get(created_id) or "").strip()
            owner_mail = (self._email_map.get(owner_id) or "").strip()
            if production:
                real_targets: List[str] = []
                if include_creator:
                    real_targets.append(created_mail)
                if include_owner:
                    real_targets.append(owner_mail)
                if include_equipment_manager:
                    try:
                        real_targets.extend(list(getattr(row_map, "equipment_manager_emails", ()) or ()))
                    except Exception:
                        pass
                real_targets = self._unique_in_order(real_targets)
                if not real_targets:
                    unresolved += 1
                    continue
                for real_to in real_targets:
                    recipients.append(real_to)
            else:
                # テスト運用は実宛先解決有無に関わらず、test_to に送る（未設定なら結果的に送信スキップ）
                effective = (test_to or "").strip()
                if effective:
                    recipients.append(effective)

        uniq = sorted(set(recipients))
        msg = (
            f"通知を実行します。\n\n"
            f"対象エントリ数: {len(entries)}\n"
            f"通知先（ユニーク）: {len(uniq)}\n"
        )
        if not production:
            msg += f"\nテスト運用: 実送信先は {test_to or '(未設定)'} になります。\n"
        if unresolved:
            msg += f"\nメール未解決のエントリ: {unresolved} 件（送信はスキップされます）\n"

        detail = "\n".join(uniq[:50])
        if len(uniq) > 50:
            detail += f"\n... and {len(uniq) - 50} more"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("通知実行の確認")
        box.setText(msg)
        box.setDetailedText(detail)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes
