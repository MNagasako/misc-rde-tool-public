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
        QRadioButton,
        QButtonGroup,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QAbstractItemView,
        QDateTimeEdit,
        QComboBox,
        QMessageBox,
        QInputDialog,
    )
    from qt_compat.core import Qt, QThread, Signal
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
        QRadioButton,
        QButtonGroup,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QAbstractItemView,
        QDateTimeEdit,
        QComboBox,
        QMessageBox,
        QInputDialog,
    )
    from PySide6.QtCore import Qt, QThread, Signal

from config.common import SUBGROUP_JSON_PATH
from classes.core.mail_dispatcher import send_using_app_mail_settings
from classes.core.mail_send_log import record_sent, should_send
from classes.core.mail_send_log import load_history
from classes.data_entry.core import registration_status_service as regsvc
from classes.data_entry.core.logic.notification_selection import (
    PlannedNotificationRow,
    build_planned_notification_rows,
    select_failed_entries_by_reference,
    select_failed_entries_in_range,
)
from classes.data_entry.util.group_member_loader import load_group_members
from classes.data_entry.util.entry_group_email_resolver import build_email_map_for_entry_ids
from classes.subgroup.core.subgroup_data_manager import SubgroupDataManager
from classes.managers.app_config_manager import get_config_manager
from classes.theme import ThemeKey, get_color

logger = logging.getLogger(__name__)

_JST = timezone(timedelta(hours=9))
_UTC = timezone.utc

_RECIPIENT_BOTH = "both"
_RECIPIENT_CREATOR = "creator"
_RECIPIENT_OWNER = "owner"


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


class MailNotificationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker: _ExtractWorker | None = None
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
        self.test_mode_radio = QRadioButton("テストモード（テストメールの宛先のみに送信）")
        self.production_mode_radio = QRadioButton("本番モード（実際の宛先に送信）")
        self.test_mode_radio.setChecked(True)
        mode_bg = QButtonGroup(self)
        mode_bg.addButton(self.test_mode_radio)
        mode_bg.addButton(self.production_mode_radio)
        mode_layout.addWidget(self.test_mode_radio)
        mode_layout.addWidget(self.production_mode_radio)

        mode_layout.addWidget(QLabel("本番送信先:"))
        self.production_recipient_combo = QComboBox()
        self.production_recipient_combo.addItem("所有者・投入者", _RECIPIENT_BOTH)
        self.production_recipient_combo.addItem("投入者のみ", _RECIPIENT_CREATOR)
        self.production_recipient_combo.addItem("所有者のみ", _RECIPIENT_OWNER)
        self.production_recipient_combo.setCurrentIndex(0)
        mode_layout.addWidget(self.production_recipient_combo)

        self.view_log_btn = QPushButton("送信ログ表示")
        self.view_log_btn.clicked.connect(self._show_send_log)
        mode_layout.addWidget(self.view_log_btn)
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
        btn_row.addStretch()
        cond_layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        cond_layout.addWidget(self.status_label)

        layout.addWidget(cond_group)

        tmpl_group = QGroupBox("テンプレート")
        tmpl = QVBoxLayout(tmpl_group)

        tmpl_top = QHBoxLayout()
        tmpl_top.addWidget(QLabel("テンプレート:"))
        self.template_combo = QComboBox()
        tmpl_top.addWidget(self.template_combo)
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

        row_subj = QHBoxLayout()
        row_subj.addWidget(QLabel("件名テンプレ:"))
        self.subject_template_edit = QLineEdit()
        self.subject_template_edit.setText("[RDE] 登録失敗: {dataName} ({entryId})")
        row_subj.addWidget(self.subject_template_edit)
        tmpl.addLayout(row_subj)

        self.body_template_edit = QTextEdit()
        self.body_template_edit.setPlainText(
            "登録状況: FAILED\n"
            "開始時刻(JST): {startTime}\n"
            "データ名: {dataName}\n"
            "データセット: {datasetName}\n"
            "エラーコード: {errorCode}\n"
            "エラーメッセージ: {errorMessage}\n"
            "投入者: {createdByName} ({createdByUserId})\n"
            "所有者: {dataOwnerName} ({dataOwnerUserId})\n"
            "エントリID: {entryId}\n"
        )
        tmpl.addWidget(self.body_template_edit)
        layout.addWidget(tmpl_group)

        list_group = QGroupBox("通知対象リスト")
        list_layout = QVBoxLayout(list_group)

        self.table = QTableWidget(0, 11, self)
        self.table.setHorizontalHeaderLabels(
            [
                "開始時刻(JST)",
                "データ名",
                "投入者（所属）",
                "投入者メール",
                "所有者（所属）",
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
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setTextElideMode(Qt.ElideRight)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
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
        self.subject_template_edit.textChanged.connect(self._on_template_edited)
        self.body_template_edit.textChanged.connect(self._on_template_edited)

        self._set_status("条件を設定して『通知対象抽出』を実行してください。", ThemeKey.TEXT_MUTED)

        # モードUI
        self.test_mode_radio.toggled.connect(self._sync_mode_controls)
        self.production_mode_radio.toggled.connect(self._sync_mode_controls)
        self._sync_mode_controls()

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
                        "エラーコード: {errorCode}\n"
                        "エラーメッセージ: {errorMessage}\n"
                        "投入者: {createdByName} ({createdByUserId})\n"
                        "所有者: {dataOwnerName} ({dataOwnerUserId})\n"
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
        self._apply_template_to_editors(0)

    def _save_templates(self):
        try:
            self._sync_current_template_from_editors()
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

        self._sync_current_template_from_editors()
        self._templates.append(
            {
                "name": name,
                "subject": self.subject_template_edit.text() or "",
                "body": self.body_template_edit.toPlainText() or "",
            }
        )
        self.template_combo.addItem(name)
        self.template_combo.setCurrentIndex(len(self._templates) - 1)

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
        self._sync_current_template_from_editors()
        self._current_template_index = max(0, int(idx))
        self._apply_template_to_editors(self._current_template_index)

    def _apply_template_to_editors(self, idx: int):
        if idx < 0 or idx >= len(self._templates):
            return
        t = self._templates[idx]
        self.subject_template_edit.blockSignals(True)
        self.body_template_edit.blockSignals(True)
        self.subject_template_edit.setText(t.get("subject") or "")
        self.body_template_edit.setPlainText(t.get("body") or "")
        self.subject_template_edit.blockSignals(False)
        self.body_template_edit.blockSignals(False)

    def _sync_current_template_from_editors(self):
        idx = int(self._current_template_index)
        if idx < 0 or idx >= len(self._templates):
            return
        self._templates[idx]["subject"] = self.subject_template_edit.text() or ""
        self._templates[idx]["body"] = self.body_template_edit.toPlainText() or ""

    def _on_template_edited(self):
        self._sync_current_template_from_editors()

    def _sync_mode_controls(self):
        ref_on = self.mode_reference_radio.isChecked()
        self.reference_dt.setEnabled(ref_on)
        self.range_days_spin.setEnabled(ref_on)
        self.start_dt.setEnabled(not ref_on)
        self.end_dt.setEnabled(not ref_on)

        is_prod = self._is_production_mode()
        self.production_recipient_combo.setEnabled(is_prod)

    def _is_production_mode(self) -> bool:
        return bool(getattr(self, "production_mode_radio", None) and self.production_mode_radio.isChecked())

    def _set_status(self, message: str, theme_key: ThemeKey | None):
        color = get_color(theme_key or ThemeKey.TEXT_MUTED)
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)

    def _show_send_log(self):
        try:
            items = load_history(limit=200)
        except Exception:
            items = []

        if not items:
            QMessageBox.information(self, "送信ログ", "送信ログがありません。")
            return

        lines = []
        for h in items:
            sent_at = str(h.get("sentAt") or "")
            to_addr = str(h.get("to") or "")
            subject = str(h.get("subject") or "")
            lines.append(f"{sent_at} | {to_addr} | {subject}")

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("送信ログ")
        msg.setText(f"送信ログ（最新{len(lines)}件）")
        msg.setDetailedText("\n".join(lines))
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _test_to_address(self) -> str:
        try:
            mgr = get_config_manager()
            return str(mgr.get("mail.test.to_address", "") or "").strip()
        except Exception:
            return ""

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

        production = self._is_production_mode()
        planned = build_planned_notification_rows(
            entries=selected,
            email_map=self._email_map,
            production_mode=production,
            test_to_address=self._test_to_address(),
            subject_template=self.subject_template_edit.text() or "",
            body_template=self.body_template_edit.toPlainText() or "",
        )

        self._targets = selected
        self._planned_rows = planned
        self._render_table(planned)
        self._set_status(f"抽出完了: {len(planned)} 件", ThemeKey.TEXT_SUCCESS)

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
            self.table.setItem(row, 1, QTableWidgetItem(r.data_name))
            created_display = (r.created_name or "")
            if r.created_org:
                created_display = f"{created_display} ({r.created_org})" if created_display else f"({r.created_org})"
            owner_display = (r.owner_name or "")
            if r.owner_org:
                owner_display = f"{owner_display} ({r.owner_org})" if owner_display else f"({r.owner_org})"

            self.table.setItem(row, 2, QTableWidgetItem(created_display))
            self.table.setItem(row, 3, QTableWidgetItem(r.created_mail))
            self.table.setItem(row, 4, QTableWidgetItem(owner_display))
            self.table.setItem(row, 5, QTableWidgetItem(r.owner_mail))
            self.table.setItem(row, 6, QTableWidgetItem(r.effective_to))
            self.table.setItem(row, 7, QTableWidgetItem(r.error_code))
            self.table.setItem(row, 8, QTableWidgetItem(r.error_message))
            self.table.setItem(row, 9, QTableWidgetItem(r.subject))
            self.table.setItem(row, 10, QTableWidgetItem(r.entry_id))

            # 長文は省略表示＋ツールチップで全文
            try:
                if self.table.item(row, 8):
                    self.table.item(row, 8).setToolTip(r.error_message)
                if self.table.item(row, 9):
                    self.table.item(row, 9).setToolTip(r.subject)
            except Exception:
                pass

        # 初期幅は内容に合わせつつ、長文列は過剰に広がり過ぎないように上限を設ける
        try:
            self.table.resizeColumnsToContents()
            max_w = 420
            for col in (8, 9):
                w = self.table.columnWidth(col)
                if w > max_w:
                    self.table.setColumnWidth(col, max_w)
        except Exception:
            pass

        try:
            if was_sorting:
                self.table.setSortingEnabled(True)
        except Exception:
            pass

    def _effective_to_addr(self, real_to: str) -> str:
        if self._is_production_mode():
            return (real_to or "").strip()
        return self._test_to_address()

    def _production_recipient_mode(self) -> str:
        try:
            return str(self.production_recipient_combo.currentData())
        except Exception:
            return _RECIPIENT_BOTH

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

    def _send_for_entry(self, entry: Dict[str, Any], quiet: bool = False) -> Tuple[int, int]:
        row_map = None
        for r in self._planned_rows:
            if r.entry_id == str(entry.get("id") or ""):
                row_map = r
                break

        subject = row_map.subject if row_map else (self.subject_template_edit.text() or "")
        body = row_map.body if row_map else (self.body_template_edit.toPlainText() or "")

        created_id = str(entry.get("createdByUserId") or "")
        owner_id = str(entry.get("dataOwnerUserId") or "")
        created_mail = (self._email_map.get(created_id) or "").strip()
        owner_mail = (self._email_map.get(owner_id) or "").strip()

        production = self._is_production_mode()
        if production:
            mode = self._production_recipient_mode()
            if mode == _RECIPIENT_CREATOR:
                real_targets = [created_mail]
            elif mode == _RECIPIENT_OWNER:
                real_targets = [owner_mail]
            else:
                real_targets = [created_mail, owner_mail]
            targets = self._unique_in_order(real_targets)

            if not targets:
                if not quiet:
                    self._set_status("投入者/所有者のメールアドレスが解決できません。", ThemeKey.TEXT_WARNING)
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

    def _on_row_clicked(self, row: int, col: int):
        try:
            entry_id = self.table.item(row, 10).text() if self.table.item(row, 10) else ""
        except Exception:
            entry_id = ""
        if not entry_id:
            return

        entry = self._find_entry_by_id(entry_id)
        if not entry:
            return

        self._send_for_entry(entry)

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
                entry_ids.append(self.table.item(r, 10).text())
            except Exception:
                continue
        entries: List[Dict[str, Any]] = []
        for eid in entry_ids:
            e = self._find_entry_by_id(eid)
            if e:
                entries.append(e)
        return entries

    def _confirm_send(self, entries: List[Dict[str, Any]]) -> bool:
        # 宛先解決（投入者/所有者×件数）
        production = self._is_production_mode()
        test_to = self._test_to_address()
        recipients: List[str] = []
        unresolved = 0

        prod_mode = self._production_recipient_mode()

        for e in entries or []:
            created_id = str(e.get("createdByUserId") or "")
            owner_id = str(e.get("dataOwnerUserId") or "")
            created_mail = (self._email_map.get(created_id) or "").strip()
            owner_mail = (self._email_map.get(owner_id) or "").strip()
            if production:
                if prod_mode == _RECIPIENT_CREATOR:
                    real_targets = [created_mail]
                elif prod_mode == _RECIPIENT_OWNER:
                    real_targets = [owner_mail]
                else:
                    real_targets = [created_mail, owner_mail]
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
