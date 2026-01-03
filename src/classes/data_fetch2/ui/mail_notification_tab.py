from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from qt_compat.widgets import (
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
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QAbstractItemView,
    )
    from qt_compat.core import Qt, QTimer, QThread, Signal
except Exception:
    from PySide6.QtWidgets import (
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
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QAbstractItemView,
    )
    from PySide6.QtCore import Qt, QTimer, QThread, Signal

from config.common import SUBGROUP_JSON_PATH
from classes.core.mail_dispatcher import send_using_app_mail_settings
from classes.core.mail_send_log import record_sent, should_send
from classes.data_entry.core import registration_status_service as regsvc
from classes.data_entry.util.group_member_loader import load_group_members
from classes.data_fetch2.core.logic.notification_selection import select_failed_entries_within_window
from classes.managers.app_config_manager import get_config_manager
from classes.theme import ThemeKey, get_color

logger = logging.getLogger(__name__)

_UTC = timezone.utc


def _parse_reference_time(text: str) -> Optional[datetime]:
    t = (text or "").strip()
    if not t:
        return None
    # 例: 2026-01-02 12:34 / 2026-01-02T12:34:56+09:00
    try:
        if "T" not in t and " " in t:
            t = t.replace(" ", "T")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            # ローカル(JST想定)で解釈してUTCへ
            jst = timezone(timedelta(hours=9))
            dt = dt.replace(tzinfo=jst)
        return dt.astimezone(_UTC)
    except Exception:
        return None


def _load_selected_subgroup_id() -> str:
    try:
        with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        data = (payload or {}).get("data") or {}
        return str(data.get("id") or "")
    except Exception:
        return ""


def _member_email_map(group_id: str) -> Dict[str, str]:
    # group_member_loader は included(type=user) を返す
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


class _ExtractWorker(QThread):
    finished = Signal(object)  # list[dict]

    def __init__(self, reference_time: datetime):
        super().__init__()
        self._reference_time = reference_time

    def run(self):
        try:
            entries: List[Dict] = []
            if getattr(regsvc, "has_all_cache", None) and regsvc.has_all_cache(ignore_ttl=True):
                entries = regsvc.load_all_cache(ignore_ttl=True)
            else:
                entries = regsvc.fetch_latest(limit=100, use_cache=True)

            selected = select_failed_entries_within_window(
                entries=entries,
                reference_time=self._reference_time,
                window=timedelta(days=1),
            )
            self.finished.emit(selected)
        except Exception as exc:
            logger.debug("extract worker failed: %s", exc)
            self.finished.emit([])


class MailNotificationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._timer: QTimer | None = None
        self._worker: _ExtractWorker | None = None
        self._targets: List[Dict] = []
        self._email_map: Dict[str, str] = {}

        layout = QVBoxLayout(self)

        title = QLabel("メール通知")
        layout.addWidget(title)

        mode_group = QGroupBox("運用モード")
        mode_layout = QHBoxLayout(mode_group)
        self.production_checkbox = QCheckBox("本番運用（実際の宛先に送る）")
        self.production_checkbox.setChecked(False)
        mode_layout.addWidget(self.production_checkbox)
        mode_layout.addStretch()
        layout.addWidget(mode_group)

        ctrl_group = QGroupBox("抽出")
        ctrl = QVBoxLayout(ctrl_group)

        row_ref = QHBoxLayout()
        row_ref.addWidget(QLabel("基準時刻(ISO/JST可):"))
        self.reference_time_edit = QLineEdit()
        # デフォルト: 現在(JST)のISO簡易
        now_jst = datetime.now(timezone(timedelta(hours=9))).replace(microsecond=0)
        self.reference_time_edit.setText(now_jst.isoformat(timespec="seconds"))
        row_ref.addWidget(self.reference_time_edit)
        ctrl.addLayout(row_ref)

        row_interval = QHBoxLayout()
        row_interval.addWidget(QLabel("インターバル(秒):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setMinimum(10)
        self.interval_spin.setMaximum(3600)
        self.interval_spin.setValue(60)
        row_interval.addWidget(self.interval_spin)
        row_interval.addStretch()
        ctrl.addLayout(row_interval)

        btn_row = QHBoxLayout()
        self.extract_once_btn = QPushButton("エラーメール通知対象抽出（ワンショット）")
        self.extract_once_btn.clicked.connect(self.extract_once)
        btn_row.addWidget(self.extract_once_btn)

        self.start_interval_btn = QPushButton("インターバル抽出開始")
        self.start_interval_btn.clicked.connect(self.start_interval)
        btn_row.addWidget(self.start_interval_btn)

        self.stop_interval_btn = QPushButton("中止")
        self.stop_interval_btn.clicked.connect(self.stop_interval)
        self.stop_interval_btn.setEnabled(False)
        btn_row.addWidget(self.stop_interval_btn)
        btn_row.addStretch()
        ctrl.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        ctrl.addWidget(self.status_label)

        layout.addWidget(ctrl_group)

        tmpl_group = QGroupBox("テンプレート")
        tmpl = QVBoxLayout(tmpl_group)

        row_subj = QHBoxLayout()
        row_subj.addWidget(QLabel("件名テンプレ:"))
        self.subject_template_edit = QLineEdit()
        self.subject_template_edit.setText("[RDE] 登録失敗: {dataName} ({entryId})")
        row_subj.addWidget(self.subject_template_edit)
        tmpl.addLayout(row_subj)

        self.body_template_edit = QTextEdit()
        self.body_template_edit.setPlainText(
            "登録状況: FAILED\n"
            "開始時刻: {startTime}\n"
            "データ名: {dataName}\n"
            "データセット: {datasetName}\n"
            "エラーコード: {errorCode}\n"
            "エラーメッセージ: {errorMessage}\n"
            "投入者: {createdByName} \n"
            "所有者: {dataOwnerName} \n"
            "装置管理者: {equipmentManagerName} \n"
            "エントリID: {entryId}\n"
        )
        tmpl.addWidget(self.body_template_edit)
        layout.addWidget(tmpl_group)

        list_group = QGroupBox("通知対象リスト")
        list_layout = QVBoxLayout(list_group)

        self.table = QTableWidget(0, 9, self)
        self.table.setHorizontalHeaderLabels(
            [
                "開始時刻",
                "データ名",
                "投入者メール",
                "所有者メール",
                "実送信先",
                "エラーコード",
                "エラーメッセージ",
                "件名",
                "entryId",
            ]
        )
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        list_layout.addWidget(self.table)

        send_row = QHBoxLayout()
        self.send_all_btn = QPushButton("通知実行（全件）")
        self.send_all_btn.clicked.connect(self.send_all)
        send_row.addWidget(self.send_all_btn)
        send_row.addStretch()
        list_layout.addLayout(send_row)

        self.table.cellClicked.connect(self._on_row_clicked)

        layout.addWidget(list_group)
        layout.addStretch()

        self._set_status("対象抽出を実行してください。", ThemeKey.TEXT_MUTED)

    def _set_status(self, message: str, theme_key: ThemeKey | None):
        self.status_label.setText(message)
        if theme_key is None:
            self.status_label.setStyleSheet("")
        else:
            self.status_label.setStyleSheet(f"color: {get_color(theme_key)}; font-weight: bold;")

    def _effective_to_addr(self, real_to: str) -> str:
        if self.production_checkbox.isChecked():
            return real_to
        cfg = get_config_manager()
        return str(cfg.get("mail.test.to_address", "")).strip()

    def extract_once(self):
        ref = _parse_reference_time(self.reference_time_edit.text())
        if ref is None:
            self._set_status("基準時刻の形式が不正です。", ThemeKey.TEXT_WARNING)
            return

        self._set_status("抽出中...", ThemeKey.TEXT_INFO)
        self.extract_once_btn.setEnabled(False)
        try:
            self._worker = _ExtractWorker(ref)
            self._worker.finished.connect(self._on_extracted)
            self._worker.start()
        except Exception as exc:
            logger.debug("extract start failed: %s", exc)
            self._on_extracted([])

    def _on_extracted(self, selected: List[Dict]):
        self.extract_once_btn.setEnabled(True)

        group_id = _load_selected_subgroup_id()
        self._email_map = _member_email_map(group_id) if group_id else {}

        # 送信対象を構築: createdBy/dataOwner のメールを解決
        targets: List[Dict] = []
        for e in selected:
            created_id = str(e.get("createdByUserId") or "")
            owner_id = str(e.get("dataOwnerUserId") or "")
            created_mail = self._email_map.get(created_id, "")
            owner_mail = self._email_map.get(owner_id, "")
            targets.append(
                {
                    "entry": e,
                    "created_mail": created_mail,
                    "owner_mail": owner_mail,
                }
            )

        self._targets = targets
        self._render_table()
        self._set_status(f"抽出完了: {len(targets)} 件", ThemeKey.TEXT_SUCCESS)

    def _render_table(self):
        self.table.setRowCount(0)

        for t in self._targets:
            e = t["entry"]
            created_mail = t.get("created_mail") or ""
            owner_mail = t.get("owner_mail") or ""

            subject = self._render_subject(e)
            effective_to_created = self._effective_to_addr(created_mail)
            effective_to_owner = self._effective_to_addr(owner_mail)

            # テスト運用時も本番宛先は表示するが、実送信先は test.to_address
            effective_to = effective_to_created
            if not effective_to and effective_to_owner:
                effective_to = effective_to_owner

            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(e.get("startTime") or "")))
            self.table.setItem(row, 1, QTableWidgetItem(str(e.get("dataName") or "")))
            self.table.setItem(row, 2, QTableWidgetItem(created_mail or "(不明)"))
            self.table.setItem(row, 3, QTableWidgetItem(owner_mail or "(不明)"))
            self.table.setItem(row, 4, QTableWidgetItem(effective_to or "(未設定)"))
            self.table.setItem(row, 5, QTableWidgetItem(str(e.get("errorCode") or "")))
            self.table.setItem(row, 6, QTableWidgetItem(str(e.get("errorMessage") or "")))
            self.table.setItem(row, 7, QTableWidgetItem(subject))
            self.table.setItem(row, 8, QTableWidgetItem(str(e.get("id") or "")))

    def _render_subject(self, entry: Dict) -> str:
        template = self.subject_template_edit.text() or ""
        return self._format_template(template, entry)

    def _render_body(self, entry: Dict) -> str:
        template = self.body_template_edit.toPlainText() or ""
        return self._format_template(template, entry)

    def _format_template(self, template: str, entry: Dict) -> str:
        values = {
            "entryId": entry.get("id") or "",
            "startTime": entry.get("startTime") or "",
            "dataName": entry.get("dataName") or "",
            "datasetName": entry.get("datasetName") or "",
            "errorCode": entry.get("errorCode") or "",
            "errorMessage": entry.get("errorMessage") or "",
            "createdByUserId": entry.get("createdByUserId") or "",
            "createdByName": entry.get("createdByName") or "",
            "dataOwnerUserId": entry.get("dataOwnerUserId") or "",
            "dataOwnerName": entry.get("dataOwnerName") or "",
        }
        try:
            return template.format(**values)
        except Exception:
            # 欠落キー等はそのまま返す
            return template

    def start_interval(self):
        self.stop_interval()
        interval_ms = int(self.interval_spin.value()) * 1000
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.extract_once)
        self._timer.start(interval_ms)
        self.start_interval_btn.setEnabled(False)
        self.stop_interval_btn.setEnabled(True)
        self._set_status("インターバル抽出を開始しました。", ThemeKey.TEXT_INFO)

    def stop_interval(self):
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None
        self.start_interval_btn.setEnabled(True)
        self.stop_interval_btn.setEnabled(False)

    def _on_row_clicked(self, row: int, col: int):
        try:
            entry_id = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
        except Exception:
            entry_id = ""
        if not entry_id:
            return

        for t in self._targets:
            e = t.get("entry") or {}
            if str(e.get("id") or "") == entry_id:
                self._send_for_entry(e, t.get("created_mail") or "", t.get("owner_mail") or "")
                return

    def send_all(self):
        if not self._targets:
            self._set_status("対象がありません。", ThemeKey.TEXT_WARNING)
            return

        sent = 0
        skipped = 0
        for t in self._targets:
            e = t.get("entry") or {}
            created_mail = t.get("created_mail") or ""
            owner_mail = t.get("owner_mail") or ""
            s, k = self._send_for_entry(e, created_mail, owner_mail, quiet=True)
            sent += s
            skipped += k

        self._set_status(f"通知完了: sent={sent}, skipped={skipped}", ThemeKey.TEXT_SUCCESS)

    def _send_for_entry(self, entry: Dict, created_mail: str, owner_mail: str, quiet: bool = False) -> Tuple[int, int]:
        subject = self._render_subject(entry)
        body = self._render_body(entry)

        real_targets = [m for m in [created_mail, owner_mail] if m]
        if not real_targets:
            if not quiet:
                self._set_status("投入者/所有者のメールアドレスが解決できません。", ThemeKey.TEXT_WARNING)
            return (0, 1)

        sent = 0
        skipped = 0
        for real_to in real_targets:
            effective_to = self._effective_to_addr(real_to)
            if not effective_to:
                skipped += 1
                continue
            if not should_send(to_addr=effective_to, subject=subject):
                skipped += 1
                continue

            try:
                send_using_app_mail_settings(to_addr=effective_to, subject=subject, body=body)
                record_sent(to_addr=effective_to, subject=subject)
                sent += 1
            except Exception as exc:
                logger.debug("send failed: %s", exc)
                if not quiet:
                    self._set_status(f"送信失敗: {exc}", ThemeKey.TEXT_ERROR)
                return (sent, skipped)

        if not quiet:
            self._set_status(f"個別送信完了: sent={sent}, skipped={skipped}", ThemeKey.TEXT_SUCCESS)
        return (sent, skipped)
