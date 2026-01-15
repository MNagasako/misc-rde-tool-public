"""Invoice edit dialog used from dataset data-entry tab."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from qt_compat.widgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QPushButton,
    QMessageBox,
    QGroupBox,
    QFileDialog,
    QScrollArea,
    QSizePolicy,
    QApplication,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from classes.managers.log_manager import get_logger
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import get_dynamic_file_path
from core.bearer_token_manager import BearerTokenManager
from net.http_helpers import proxy_get, proxy_patch
from qt_compat.core import Qt

from classes.data_entry.core.data_register_logic import upload_file
from classes.data_entry.util.group_member_loader import load_group_members
from classes.utils.schema_form_util import get_schema_form_all_fields
from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
from classes.dataset.util.dataset_dropdown_util import get_current_user_id

from classes.dataset.core.invoice_edit_logic import (
    build_invoice_patch_payload,
    merge_invoice_attributes,
    merge_custom_from_schema_form,
    split_comma_list,
)

logger = get_logger(__name__)


def fetch_invoice_for_edit(entry_id: str, bearer_token: Optional[str] = None) -> Dict[str, Any]:
    token = bearer_token or BearerTokenManager.get_current_token()
    if not token:
        raise RuntimeError("Bearer Tokenが取得できません")

    url = f"https://rde-api.nims.go.jp/invoices/{entry_id}?include=submittedBy%2CdataOwner%2Cinstrument"
    headers = {
        "Accept": "application/vnd.api+json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/",
    }
    resp = proxy_get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def patch_invoice_for_edit(entry_id: str, attributes: Dict[str, Any], bearer_token: Optional[str] = None) -> Dict[str, Any]:
    token = bearer_token or BearerTokenManager.get_current_token()
    if not token:
        raise RuntimeError("Bearer Tokenが取得できません")

    url = f"https://rde-api.nims.go.jp/invoices/{entry_id}"
    payload = build_invoice_patch_payload(entry_id, attributes)
    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/",
    }
    resp = proxy_patch(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def patch_invoice_for_edit_with_meta(
    entry_id: str,
    attributes: Dict[str, Any],
    *,
    meta: Optional[Dict[str, Any]] = None,
    bearer_token: Optional[str] = None,
) -> Dict[str, Any]:
    token = bearer_token or BearerTokenManager.get_current_token()
    if not token:
        raise RuntimeError("Bearer Tokenが取得できません")

    url = f"https://rde-api.nims.go.jp/invoices/{entry_id}"
    payload = build_invoice_patch_payload(entry_id, attributes, meta=meta)
    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/",
    }
    resp = proxy_patch(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


class InvoiceEditDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        entry_id: str,
        template_id: str = "",
        bearer_token: Optional[str] = None,
    ):
        super().__init__(parent)
        self._entry_id = entry_id
        self._template_id = (template_id or "").strip()
        self._bearer_token = bearer_token
        self._original_attributes: Dict[str, Any] = {}

        self._schema_form = None
        self._schema_initial_values: Dict[str, Any] = {}
        self._pending_attachments: List[Dict[str, str]] = []
        self._dataset_id_for_upload: str = ""
        self._previous_sample_id: str = ""
        self._previous_sample_values: Dict[str, Any] = {}
        self._manual_sample_id: str = ""

        self.setWindowTitle("データエントリー編集（送り状）")
        self.setModal(True)

        main_layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        content_widget = QWidget(scroll_area)
        layout = QVBoxLayout(content_widget)
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        title = QLabel(f"エントリーID: {entry_id}")
        title.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        layout.addWidget(title)

        # ----------------
        # 基本情報（2列レイアウト）
        # ----------------
        basic_group = QGroupBox("基本情報")
        basic_layout = QGridLayout(basic_group)
        basic_layout.setContentsMargins(8, 8, 8, 8)
        basic_layout.setHorizontalSpacing(10)
        basic_layout.setVerticalSpacing(6)
        basic_layout.setColumnStretch(1, 1)

        self.data_name_edit = QLineEdit()
        self.data_name_edit.setObjectName("invoiceBasicDataName")

        self.experiment_id_edit = QLineEdit()
        self.experiment_id_edit.setObjectName("invoiceBasicExperimentId")

        self.basic_description_edit = QTextEdit()
        self.basic_description_edit.setObjectName("invoiceBasicDescription")

        self.data_owner_combo = QComboBox()
        self.data_owner_combo.setObjectName("invoiceBasicDataOwner")
        self.data_owner_combo.addItem("データセット情報から読み込み中...", None)
        self.data_owner_combo.setEnabled(False)

        basic_labels = [
            QLabel("データ名"),
            QLabel("実験ID"),
            QLabel("説明"),
            QLabel("データ所有者(所属) *"),
        ]
        self._align_label_widths(basic_labels)

        row = 0
        basic_layout.addWidget(basic_labels[0], row, 0)
        basic_layout.addWidget(self.data_name_edit, row, 1)
        row += 1

        basic_layout.addWidget(basic_labels[1], row, 0)
        basic_layout.addWidget(self.experiment_id_edit, row, 1)
        row += 1

        basic_layout.addWidget(basic_labels[2], row, 0, Qt.AlignTop)
        basic_layout.addWidget(self.basic_description_edit, row, 1)
        row += 1

        basic_layout.addWidget(basic_labels[3], row, 0)
        basic_layout.addWidget(self.data_owner_combo, row, 1)

        layout.addWidget(basic_group)

        # ----------------
        # 試料情報（2列レイアウト）
        # ----------------
        sample_group = QGroupBox("試料情報")
        sample_layout = QGridLayout(sample_group)
        sample_layout.setContentsMargins(8, 8, 8, 8)
        sample_layout.setHorizontalSpacing(10)
        sample_layout.setVerticalSpacing(6)
        sample_layout.setColumnStretch(1, 1)

        self.sample_mode_combo = QComboBox()
        self.sample_mode_combo.setObjectName("invoiceSampleMode")
        # 「既存試料IDを指定」は廃止し、既存試料名の一覧を選択肢として表示する。
        # 初期状態では固定選択肢のみ（既存試料は _setup_sample_mode_combo() で追加）。
        self.sample_mode_combo.addItem("新規", "new")
        self.sample_mode_combo.addItem("前回と同じ", "keep")
        self.sample_mode_combo.addItem("ID直接入力", "id_input")

        self.sample_id_edit = QLineEdit()
        self.sample_id_edit.setObjectName("invoiceSampleId")
        # UUID欄はモードにより入力可否を切替
        self.sample_id_edit.setReadOnly(True)

        self.sample_names_edit = QLineEdit()
        self.sample_names_edit.setObjectName("invoiceSampleNames")

        self.sample_tags_edit = QLineEdit()
        self.sample_tags_edit.setObjectName("invoiceSampleTags")

        self.sample_description_edit = QTextEdit()
        self.sample_description_edit.setObjectName("invoiceSampleDescription")

        self.sample_composition_edit = QTextEdit()
        self.sample_composition_edit.setObjectName("invoiceSampleComposition")

        self.sample_reference_url_edit = QLineEdit()
        self.sample_reference_url_edit.setObjectName("invoiceSampleReferenceUrl")

        sample_labels = [
            QLabel("新規/選択"),
            QLabel("試料ID（UUID）"),
            QLabel("試料名"),
            QLabel("タグ（カンマ区切り）"),
            QLabel("試料の説明"),
            QLabel("化学式・組成式・分子式"),
            QLabel("参照URL"),
        ]
        self._align_label_widths(sample_labels)

        row = 0
        sample_layout.addWidget(sample_labels[0], row, 0)
        sample_layout.addWidget(self.sample_mode_combo, row, 1)
        row += 1

        sample_layout.addWidget(sample_labels[1], row, 0)
        sample_layout.addWidget(self.sample_id_edit, row, 1)
        row += 1

        sample_layout.addWidget(sample_labels[2], row, 0)
        sample_layout.addWidget(self.sample_names_edit, row, 1)
        row += 1

        sample_layout.addWidget(sample_labels[3], row, 0)
        sample_layout.addWidget(self.sample_tags_edit, row, 1)
        row += 1

        sample_layout.addWidget(sample_labels[4], row, 0, Qt.AlignTop)
        sample_layout.addWidget(self.sample_description_edit, row, 1)
        row += 1

        sample_layout.addWidget(sample_labels[5], row, 0, Qt.AlignTop)
        sample_layout.addWidget(self.sample_composition_edit, row, 1)
        row += 1

        sample_layout.addWidget(sample_labels[6], row, 0)
        sample_layout.addWidget(self.sample_reference_url_edit, row, 1)

        layout.addWidget(sample_group)

        # ----------------
        # 固有情報（入れ子を解消）
        # ----------------
        custom_group = QGroupBox("固有情報")
        custom_layout = QVBoxLayout(custom_group)
        self.custom_placeholder = QLabel("テンプレートに固有情報がない、または invoiceSchema が未取得です。")
        self.custom_placeholder.setObjectName("invoiceSchemaPlaceholder")
        self.custom_placeholder.setWordWrap(True)
        custom_layout.addWidget(self.custom_placeholder)
        layout.addWidget(custom_group)

        attachments_group = QGroupBox("添付ファイル")
        attachments_layout = QVBoxLayout(attachments_group)
        attachments_help = QLabel("※ データ登録（エントリー作成）は行いません。添付のみ uploadId を発行して送り状へ関連付けます。")
        attachments_help.setWordWrap(True)
        attachments_layout.addWidget(attachments_help)

        self.attachments_table = QTableWidget(0, 2)
        self.attachments_table.setObjectName("invoiceAttachmentsTable")
        self.attachments_table.setHorizontalHeaderLabels(["ファイル名", "uploadId"])
        self.attachments_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.attachments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.attachments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        attachments_layout.addWidget(self.attachments_table)

        attach_buttons = QHBoxLayout()
        self.add_attachment_btn = QPushButton("添付ファイル追加")
        self.add_attachment_btn.setObjectName("invoiceAddAttachmentButton")
        attach_buttons.addStretch(1)
        attach_buttons.addWidget(self.add_attachment_btn)
        attachments_layout.addLayout(attach_buttons)
        layout.addWidget(attachments_group)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("キャンセル")
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("invoiceEditSaveButton")

        self.save_btn.setStyleSheet(
            f"background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)}; font-weight: bold; "
            f"border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)}; border-radius: 6px; padding: 6px 12px;"
        )
        self.cancel_btn.setStyleSheet(
            f"background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)}; font-weight: bold; border-radius: 6px; padding: 6px 12px;"
        )

        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        main_layout.addLayout(buttons)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._on_save)
        self.add_attachment_btn.clicked.connect(self._on_add_attachments)

        self.sample_mode_combo.currentIndexChanged.connect(self._apply_sample_mode)

        # 初期サイズ: 画面の幅50%、高さ80%（リサイズ可）
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.resize(int(geo.width() * 0.50), int(geo.height() * 0.80))
        except Exception:
            # 取得できない環境（テスト等）では既定サイズに任せる
            pass

        # テキスト入力エリアの高さ調整
        self._set_text_edit_height_lines(self.basic_description_edit, 3)
        self._set_text_edit_height_lines(self.sample_description_edit, 1)
        self._set_text_edit_height_lines(self.sample_composition_edit, 1)

        self._load()

    def _get_sample_mode(self) -> str:
        data = self.sample_mode_combo.currentData()
        if data in ("keep", "new", "id_input"):
            return str(data)
        if isinstance(data, dict) and str(data.get("id") or "").strip():
            return "existing"
        return "new"

    def _get_selected_existing_sample_id(self) -> str:
        data = self.sample_mode_combo.currentData()
        if isinstance(data, dict):
            return str(data.get("id") or "").strip()
        return ""

    def _setup_sample_mode_combo(self, *, dataset_id: str) -> None:
        """試料の扱いコンボを更新（新規作成/前回と同じ/既存試料名一覧）。"""
        dataset_id = (dataset_id or "").strip()
        combo = self.sample_mode_combo

        # 現在の選択状態を可能な範囲で維持する
        selected_mode = self._get_sample_mode()
        selected_existing_id = self._get_selected_existing_sample_id() if selected_mode == "existing" else ""

        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("新規", "new")
            combo.addItem("前回と同じ", "keep")
            combo.addItem("ID直接入力", "id_input")

            group_id = self._load_group_id_from_dataset(dataset_id)
            if group_id:
                try:
                    from classes.data_entry.util.sample_loader import load_existing_samples, format_sample_display_name

                    existing_samples = load_existing_samples(group_id)
                    for sample in existing_samples:
                        display_name = format_sample_display_name(sample)
                        combo.addItem(display_name, sample)
                except Exception as exc:
                    logger.warning("既存試料一覧の取得に失敗: %s", exc)

            # 選択を復元
            if selected_mode == "existing" and selected_existing_id:
                for i in range(combo.count()):
                    d = combo.itemData(i)
                    if isinstance(d, dict) and str(d.get("id") or "").strip() == selected_existing_id:
                        combo.setCurrentIndex(i)
                        break
                else:
                    # 選択肢にない場合は前回/新規へフォールバック
                    combo.setCurrentIndex(1 if self._previous_sample_id else 0)
            elif selected_mode == "keep":
                combo.setCurrentIndex(1)
            elif selected_mode == "id_input":
                combo.setCurrentIndex(2)
            else:
                # new
                combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(False)

        self._apply_sample_mode()

    def _set_line_edit_editable(self, edit: QLineEdit, *, editable: bool) -> None:
        # 入力不可時は Qt の disabled 状態にして、テーマ(:disabled)の配色に寄せる
        edit.setEnabled(bool(editable))
        edit.setReadOnly(not editable)

    def _set_text_edit_editable(self, edit: QTextEdit, *, editable: bool) -> None:
        # 入力不可時は Qt の disabled 状態にして、テーマ(:disabled)の配色に寄せる
        edit.setEnabled(bool(editable))
        edit.setReadOnly(not editable)

    def _apply_sample_values(self, sample_values: Dict[str, Any]) -> None:
        sample_id = str(sample_values.get("sampleId") or sample_values.get("id") or "").strip()
        self.sample_id_edit.setText(sample_id)

        names = sample_values.get("names")
        if isinstance(names, list):
            name_text = ", ".join([str(x) for x in names if str(x).strip()])
        else:
            name_text = str(sample_values.get("name") or "")
        self.sample_names_edit.setText(name_text)

        tags = sample_values.get("tags")
        if isinstance(tags, list):
            self.sample_tags_edit.setText(", ".join([str(x) for x in tags if str(x).strip()]))
        else:
            self.sample_tags_edit.setText("")

        self.sample_description_edit.setPlainText(str(sample_values.get("description") or ""))
        self.sample_composition_edit.setPlainText(str(sample_values.get("composition") or ""))
        self.sample_reference_url_edit.setText(str(sample_values.get("referenceUrl") or ""))

    def _align_label_widths(self, labels: List[QLabel]) -> None:
        try:
            widths = [label.fontMetrics().horizontalAdvance(label.text()) for label in labels]
            if not widths:
                return
            max_width = max(widths)
            for label in labels:
                label.setMinimumWidth(max_width)
        except Exception:
            return

    def _set_text_edit_height_lines(self, edit: QTextEdit, lines: int) -> None:
        try:
            fm = edit.fontMetrics()
            # 余白分を少し足して、行数に近い高さへ
            height = int(fm.lineSpacing() * max(lines, 1) + 14)
            edit.setFixedHeight(height)
        except Exception:
            return

    def _load_group_id_from_dataset(self, dataset_id: str) -> str:
        dataset_id = (dataset_id or "").strip()
        if not dataset_id:
            return ""
        try:
            dataset_json_path = get_dynamic_file_path(f"output/rde/data/datasets/{dataset_id}.json")
            if not os.path.exists(dataset_json_path):
                return ""
            import json

            with open(dataset_json_path, "r", encoding="utf-8") as f:
                dataset_data = json.load(f)
            relationships = dataset_data.get("data", {}).get("relationships", {})
            group = relationships.get("group", {}).get("data", {})
            return str(group.get("id") or "").strip()
        except Exception:
            return ""

    def _setup_data_owner_combo(self, *, dataset_id: str, current_owner_id: str) -> None:
        combo = self.data_owner_combo
        combo.clear()
        combo.addItem("選択してください...", None)
        combo.setEnabled(False)

        group_id = self._load_group_id_from_dataset(dataset_id)
        if not group_id:
            combo.addItem("グループ情報なし", None)
            return

        try:
            members = load_group_members(group_id)
            current_user_id = get_current_user_id()
            for member in members:
                user_id = member.get("id")
                attrs = member.get("attributes", {})
                name = attrs.get("name") or attrs.get("userName") or user_id
                org = attrs.get("organizationName")
                display_text = f"{name} ({org})" if org else name
                combo.addItem(display_text, user_id)
            combo.setEnabled(True)

            if current_owner_id:
                idx = combo.findData(current_owner_id)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    return

            if current_user_id:
                idx = combo.findData(current_user_id)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    return

            if combo.count() > 1:
                combo.setCurrentIndex(1)
        except Exception as exc:
            logger.error("グループメンバー取得エラー: %s", exc, exc_info=True)
            combo.clear()
            combo.addItem("メンバー取得エラー", None)
            combo.setEnabled(False)

    def _apply_sample_mode(self) -> None:
        mode = self._get_sample_mode()
        is_keep = mode == "keep"
        is_id_input = mode == "id_input"
        is_existing = mode == "existing"
        is_new = mode == "new"

        # 入力可否・配色の制御
        self._set_line_edit_editable(self.sample_id_edit, editable=is_id_input)

        # 試料名は、新規のみ編集可。前回/既存/ID直接入力では表示のみ。
        self._set_line_edit_editable(self.sample_names_edit, editable=is_new)
        self._set_line_edit_editable(self.sample_tags_edit, editable=is_new)
        self._set_text_edit_editable(self.sample_description_edit, editable=is_new)
        self._set_text_edit_editable(self.sample_composition_edit, editable=is_new)
        self._set_line_edit_editable(self.sample_reference_url_edit, editable=is_new)

        if is_id_input:
            # ID直接入力の値は保持・復元
            if self._manual_sample_id:
                self.sample_id_edit.setText(self._manual_sample_id)
            self._manual_sample_id = self.sample_id_edit.text().strip()
            return

        if is_new:
            # 新規はUUID未使用
            self.sample_id_edit.setText("")
            return

        if is_keep:
            # 前回と同じ: 前回の試料情報を表示
            self._apply_sample_values(self._previous_sample_values)
            return

        if is_existing:
            # 既存試料: 選択された既存試料の値を表示
            data = self.sample_mode_combo.currentData()
            if isinstance(data, dict):
                self._apply_sample_values(data)
            else:
                self.sample_id_edit.setText(self._get_selected_existing_sample_id())
            return

    def _load(self) -> None:
        try:
            payload = fetch_invoice_for_edit(self._entry_id, self._bearer_token)
            data = payload.get("data") if isinstance(payload, dict) else None
            attributes = data.get("attributes") if isinstance(data, dict) else {}
            if not isinstance(attributes, dict):
                attributes = {}
            self._original_attributes = attributes

            self._dataset_id_for_upload = str(attributes.get("datasetId") or "").strip()

            basic = attributes.get("basic") if isinstance(attributes.get("basic"), dict) else {}
            sample = attributes.get("sample") if isinstance(attributes.get("sample"), dict) else {}
            custom = attributes.get("custom") if isinstance(attributes.get("custom"), dict) else {}

            self.data_name_edit.setText(str(basic.get("dataName", "") or ""))
            self.experiment_id_edit.setText(str(basic.get("experimentId", "") or ""))
            self.basic_description_edit.setPlainText(str(basic.get("description", "") or ""))

            current_owner_id = str(basic.get("dataOwnerId") or "").strip()
            self._setup_data_owner_combo(dataset_id=self._dataset_id_for_upload, current_owner_id=current_owner_id)

            names = sample.get("names")
            if isinstance(names, list):
                self.sample_names_edit.setText(", ".join([str(x) for x in names if str(x).strip()]))
            else:
                self.sample_names_edit.setText("")

            tags = sample.get("tags")
            if isinstance(tags, list):
                self.sample_tags_edit.setText(", ".join([str(x) for x in tags if str(x).strip()]))
            else:
                self.sample_tags_edit.setText("")

            self.sample_description_edit.setPlainText(str(sample.get("description", "") or ""))
            self.sample_composition_edit.setPlainText(str(sample.get("composition", "") or ""))
            self.sample_reference_url_edit.setText(str(sample.get("referenceUrl", "") or ""))

            # 前回試料情報として保持し、「前回と同じ」選択時に表示する
            self._previous_sample_id = str(sample.get("sampleId", "") or "").strip()
            self._previous_sample_values = dict(sample) if isinstance(sample, dict) else {}
            self.sample_id_edit.setText(self._previous_sample_id)

            # データセット選択済み相当のため、既存試料名のリストを構築
            self._setup_sample_mode_combo(dataset_id=self._dataset_id_for_upload)

            # デフォルト選択: 前回UUIDがあれば「前回と同じ」、なければ「新規」
            self.sample_mode_combo.setCurrentIndex(1 if self._previous_sample_id else 0)
            self._apply_sample_mode()

            self._setup_schema_form(custom)

        except Exception as exc:
            logger.error("InvoiceEditDialog load failed: %s", exc, exc_info=True)
            QMessageBox.critical(self, "エラー", f"送り状情報の取得に失敗しました:\n{exc}")

    def _setup_schema_form(self, current_custom: Dict[str, Any]) -> None:
        try:
            template_id = self._template_id
            if not template_id:
                self.custom_placeholder.setText("テンプレートIDが不明なため、固有情報フォームを表示できません。")
                return

            invoice_schema_path = get_dynamic_file_path(f"output/rde/data/invoiceSchemas/{template_id}.json")
            if not os.path.exists(invoice_schema_path):
                self.custom_placeholder.setText(
                    "invoiceSchema ファイルが未取得です。\n"
                    "必要なら『基本情報』タブ等から invoiceSchema 取得を実行してください。"
                )
                return

            schema_form = create_schema_form_from_path(invoice_schema_path, self)
            if not schema_form:
                self.custom_placeholder.setText("固有情報フォームの生成に失敗しました。")
                return

            # create_schema_form_from_path が QGroupBox を返す場合があり、
            # そのままだと「固有情報」内にさらに「固有情報」が入れ子になって見える。
            # 見た目の入れ子を避けるため、内側の枠/タイトルを無効化する。
            try:
                if isinstance(schema_form, QGroupBox):
                    schema_form.setTitle("")
                    schema_form.setFlat(True)
                    schema_form.setContentsMargins(0, 0, 0, 0)
                    # 色を使わずに枠だけ消す（テーマに依存しない）
                    schema_form.setStyleSheet(
                        "QGroupBox { border: none; margin-top: 0px; padding-top: 0px; }"
                        "QGroupBox::title { subcontrol-origin: margin; left: -9999px; }"
                    )
            except Exception:
                pass

            schema_form.setParent(self)
            schema_form.setWindowFlags(Qt.Widget)
            schema_form.setWindowModality(Qt.NonModal)

            self.custom_placeholder.hide()
            schema_form.setVisible(True)

            # 初期値を反映（customの中から schema key に一致するもののみ）
            schema_keys = list(getattr(schema_form, "_schema_key_to_widget", {}).keys())
            initial_values: Dict[str, Any] = {}
            for key in schema_keys:
                value = current_custom.get(key)
                initial_values[key] = "" if value is None else str(value)

            if hasattr(schema_form, "set_form_data"):
                schema_form.set_form_data({k: v for k, v in initial_values.items() if v != ""})

            self._schema_form = schema_form
            self._schema_initial_values = dict(initial_values)

            # layout は groupbox 内に保持されている想定だが、ここでは placeholder の直後に差し込む
            # (custom_group の layout は閉じられているので、親の layout 検索で追加)
            # custom_group 自体を直接保持していないため、placeholder の親を辿る
            parent_layout = self.custom_placeholder.parentWidget().layout() if self.custom_placeholder.parentWidget() else None
            if parent_layout is not None:
                parent_layout.addWidget(schema_form)

        except Exception as exc:
            logger.debug("schema form setup failed", exc_info=True)
            self.custom_placeholder.setText(f"固有情報フォームの初期化に失敗しました: {exc}")

    def _on_add_attachments(self) -> None:
        dataset_id = (self._dataset_id_for_upload or "").strip()
        if not dataset_id:
            QMessageBox.warning(self, "エラー", "datasetId が取得できないため、添付を追加できません。")
            return

        files, _ = QFileDialog.getOpenFileNames(self, "添付ファイルを選択", "", "All Files (*)")
        if not files:
            return

        token = self._bearer_token or BearerTokenManager.get_current_token()
        if not token:
            QMessageBox.warning(self, "認証エラー", "Bearer Tokenが取得できません。ログイン状態を確認してください。")
            return

        for path in files:
            try:
                upload_id = upload_file(token, datasetId=dataset_id, file_path=path)
                if not upload_id:
                    raise RuntimeError("uploadId が取得できませんでした")

                record = {"uploadId": str(upload_id), "description": os.path.basename(path)}
                self._pending_attachments.append(record)
                self._append_attachment_row(record)
            except Exception as exc:
                QMessageBox.warning(self, "添付失敗", f"添付ファイルのアップロードに失敗しました:\n{os.path.basename(path)}\n{exc}")

    def _append_attachment_row(self, record: Dict[str, str]) -> None:
        row = self.attachments_table.rowCount()
        self.attachments_table.insertRow(row)
        self.attachments_table.setItem(row, 0, QTableWidgetItem(record.get("description", "")))
        self.attachments_table.setItem(row, 1, QTableWidgetItem(record.get("uploadId", "")))

    def _on_save(self) -> None:
        data_name = self.data_name_edit.text().strip()
        if not data_name:
            QMessageBox.warning(self, "入力エラー", "データ名は必須です。")
            return

        data_owner_id = None
        if self.data_owner_combo.isEnabled():
            data_owner_id = self.data_owner_combo.currentData()
            if data_owner_id is None:
                QMessageBox.warning(self, "入力エラー", "データ所有者(所属)は必須です。")
                return

        original_custom = (
            self._original_attributes.get("custom")
            if isinstance(self._original_attributes.get("custom"), dict)
            else {}
        )

        custom = dict(original_custom)
        if self._schema_form is not None and hasattr(self._schema_form, "_schema_key_to_widget"):
            schema_keys = list(getattr(self._schema_form, "_schema_key_to_widget", {}).keys())
            current_values = get_schema_form_all_fields(self._schema_form)
            custom = merge_custom_from_schema_form(
                original_custom,
                schema_keys=schema_keys,
                current_values=current_values,
                initial_values=self._schema_initial_values,
            )

        mode = self._get_sample_mode()
        is_keep = mode == "keep"
        is_existing = mode in ("existing", "id_input")
        is_new = mode == "new"

        merged = merge_invoice_attributes(
            self._original_attributes,
            data_name=data_name,
            basic_description=self.basic_description_edit.toPlainText().strip(),
            experiment_id=self.experiment_id_edit.text().strip(),
            sample_description=self.sample_description_edit.toPlainText().strip() if is_new else None,
            sample_composition=self.sample_composition_edit.toPlainText().strip() if is_new else None,
            sample_reference_url=self.sample_reference_url_edit.text().strip() if is_new else None,
            sample_names=split_comma_list(self.sample_names_edit.text()) if is_new else None,
            sample_tags=split_comma_list(self.sample_tags_edit.text()) if is_new else None,
            custom=custom,
        )

        if data_owner_id is not None:
            basic: Dict[str, Any] = merged.get("basic") if isinstance(merged.get("basic"), dict) else {}
            basic["dataOwnerId"] = data_owner_id
            merged["basic"] = basic

        if is_existing:
            sample_id = self.sample_id_edit.text().strip()
            if not sample_id:
                QMessageBox.warning(self, "入力エラー", "試料を選択/指定する場合、試料IDは必須です。")
                return
            sample: Dict[str, Any] = merged.get("sample") if isinstance(merged.get("sample"), dict) else {}
            sample["sampleId"] = sample_id
            # 既存試料を一覧から選択した場合は、対応する試料情報も保存する
            selected = self.sample_mode_combo.currentData()
            if isinstance(selected, dict):
                names = selected.get("names")
                if isinstance(names, list):
                    sample["names"] = [str(x) for x in names if str(x).strip()]
                else:
                    name_text = str(selected.get("name") or "")
                    sample["names"] = split_comma_list(name_text)

                tags = selected.get("tags")
                if isinstance(tags, list):
                    sample["tags"] = [str(x) for x in tags if str(x).strip()]
                sample["description"] = str(selected.get("description") or "")
                sample["composition"] = str(selected.get("composition") or "")
                sample["referenceUrl"] = str(selected.get("referenceUrl") or "")
            merged["sample"] = sample
        elif is_new:
            sample: Dict[str, Any] = merged.get("sample") if isinstance(merged.get("sample"), dict) else {}
            sample.pop("sampleId", None)
            merged["sample"] = sample
        elif is_keep:
            # 前回と同じ: sample は一切変更しない
            merged["sample"] = (
                self._original_attributes.get("sample")
                if isinstance(self._original_attributes.get("sample"), dict)
                else merged.get("sample", {})
            )

        try:
            meta = None
            if self._pending_attachments:
                meta = {"attachments": list(self._pending_attachments)}
            patch_invoice_for_edit_with_meta(self._entry_id, merged, meta=meta, bearer_token=self._bearer_token)
        except Exception as exc:
            logger.error("InvoiceEditDialog patch failed: %s", exc, exc_info=True)
            QMessageBox.critical(self, "更新失敗", f"送り状の更新に失敗しました:\n{exc}")
            return

        QMessageBox.information(self, "更新完了", "送り状を更新しました。")
        self.accept()
