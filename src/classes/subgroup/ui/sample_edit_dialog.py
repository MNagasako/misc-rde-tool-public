"""Sample edit dialog (RDE Material API)

要件:
- JSONを直接編集させず、フォームUIで閲覧/修正する
- 保存時にフォーム値からpayloadを組み立ててAPI送信する
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, Optional

from qt_compat.widgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from classes.managers.log_manager import get_logger
from classes.subgroup.core.subgroup_api_client import SubgroupApiClient
from classes.data_entry.util.sample_names_widget import SampleNamesWidget
from classes.data_entry.util.tag_input_widget import TagInputWidget
from classes.data_entry.util.markdown_editor import MarkdownEditor
from classes.data_entry.util.related_samples_widget import RelatedSamplesWidget
from qt_compat.core import QTimer
from classes.theme.theme_manager import ThemeManager
from classes.utils.button_styles import get_button_style

logger = get_logger("SampleEdit")


class SampleEditDialog(QDialog):
    def __init__(self, parent=None, *, sample_id: str, api_client: Optional[SubgroupApiClient] = None):
        super().__init__(parent)
        self._sample_id = str(sample_id or "").strip()
        self._api = api_client or SubgroupApiClient(self)
        self._last_loaded: Optional[Dict[str, Any]] = None
        self._loaded_type: str = "sample"
        self._loaded_attrs: Dict[str, Any] = {}
        self._loaded_relationships: Dict[str, Any] = {}
        self._loaded_owning_group_id: str = ""

        self._term_defs: Dict[str, Dict[str, Any]] = {}
        self._general_term_keys: list[str] = []
        self._sample_classes: list[Dict[str, Any]] = []
        self._selected_class_keys: list[str] = []

        self._load_failed: bool = False
        self._btn_save: Optional[QPushButton] = None

        self.setWindowTitle("試料編集")
        try:
            self.resize(1100, 800)
        except Exception:
            pass

        if not self._sample_id:
            QMessageBox.warning(self, "試料編集", "試料UUIDが空のため編集できません。")
            return

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"試料UUID: {self._sample_id}"), 1)

        self._status = QLabel("", self)
        top.addWidget(self._status)

        btn_load = QPushButton("再取得（GET）", self)
        btn_load.clicked.connect(self._on_load)
        top.addWidget(btn_load)

        self._btn_save = QPushButton("保存", self)
        self._btn_save.setObjectName("sample_edit_save")
        self._btn_save.clicked.connect(self._on_save)
        try:
            # Make the save button prominent and theme-aware.
            self._btn_save.setStyleSheet(get_button_style("primary"))
        except Exception:
            pass
        top.addWidget(self._btn_save)

        btn_close = QPushButton("閉じる", self)
        btn_close.clicked.connect(self.reject)
        top.addWidget(btn_close)

        root.addLayout(top)

        # Theme follow-up (dynamic)
        try:
            ThemeManager.instance().theme_changed.connect(lambda *_: self._apply_theme())
        except Exception:
            pass

        form_group = QGroupBox("試料情報", self)
        form_layout = QVBoxLayout(form_group)

        # --- 必須: 試料名（複数可） ---
        names_row = QHBoxLayout()
        names_label = QLabel("試料名 *", self)
        names_label.setMinimumWidth(140)
        names_row.addWidget(names_label)

        self._names = SampleNamesWidget(self, max_samples=5)
        self._names.setObjectName("sample_edit_names")
        names_row.addWidget(self._names, 1)
        form_layout.addLayout(names_row)

        # --- 任意: 試料の説明（WebUI側はテキスト。ツール側はMarkdownEditorで入力/プレビュー） ---
        desc_row = QHBoxLayout()
        desc_label = QLabel("試料の説明", self)
        desc_label.setMinimumWidth(140)
        desc_label.setToolTip("任意")
        desc_row.addWidget(desc_label)

        self._description = MarkdownEditor(self)
        self._description.setObjectName("sample_edit_description")
        desc_row.addWidget(self._description, 1)
        form_layout.addLayout(desc_row)

        # --- 任意: 化学式・組成式・分子式 ---
        comp_row = QHBoxLayout()
        comp_label = QLabel("化学式・組成式・分子式", self)
        comp_label.setMinimumWidth(140)
        comp_label.setToolTip("任意")
        comp_row.addWidget(comp_label)

        self._composition = QLineEdit(self)
        self._composition.setObjectName("sample_edit_composition")
        self._composition.setPlaceholderText("化学式、組成式、または分子式を入力")
        comp_row.addWidget(self._composition, 1)
        form_layout.addLayout(comp_row)

        # --- 任意: 参考URL ---
        url_row = QHBoxLayout()
        url_label = QLabel("参考URL", self)
        url_label.setMinimumWidth(140)
        url_label.setToolTip("任意")
        url_row.addWidget(url_label)

        self._reference_url = QLineEdit(self)
        self._reference_url.setObjectName("sample_edit_reference_url")
        self._reference_url.setPlaceholderText("参考URL")
        url_row.addWidget(self._reference_url, 1)
        form_layout.addLayout(url_row)

        # --- 任意: タグ（チップ表示） ---
        tags_row = QHBoxLayout()
        tags_label = QLabel("タグ", self)
        tags_label.setMinimumWidth(140)
        tags_label.setToolTip("任意 / カンマ区切り")
        tags_row.addWidget(tags_label)

        self._tags = TagInputWidget(self)
        self._tags.setObjectName("sample_edit_tags")
        self._tags.setPlaceholderText("タグ（カンマ区切り）")
        tags_row.addWidget(self._tags, 1)
        form_layout.addLayout(tags_row)

        # --- 任意: 匿名化（owner非表示） ---
        hide_row = QHBoxLayout()
        hide_label = QLabel("試料管理者を非表示", self)
        hide_label.setMinimumWidth(140)
        hide_label.setToolTip("任意")
        hide_row.addWidget(hide_label)

        self._hide_owner = QCheckBox("hideOwner", self)
        self._hide_owner.setObjectName("sample_edit_hide_owner")
        hide_row.addWidget(self._hide_owner, 1)
        form_layout.addLayout(hide_row)

        # --- 選択: 試料分類（SampleClass） ---
        class_row = QHBoxLayout()
        class_label = QLabel("試料分類", self)
        class_label.setMinimumWidth(140)
        class_label.setToolTip("WebUI準拠: 選択方式（任意）")
        class_row.addWidget(class_label)

        self._sample_class = QComboBox(self)
        self._sample_class.setObjectName("sample_edit_sample_class")
        self._sample_class.addItem("（未選択）", "")
        self._sample_class.currentIndexChanged.connect(self._on_sample_class_changed)
        class_row.addWidget(self._sample_class, 1)
        form_layout.addLayout(class_row)

        # --- 一般属性（キー選択 + 値入力の行追加） ---
        self._general_attrs = _AttributeRowsWidget(self, title="一般属性", object_name="sample_edit_general_attributes")
        form_layout.addWidget(self._general_attrs)

        # --- 固有属性（試料分類に応じたキー選択 + 値入力） ---
        self._specific_attrs = _AttributeRowsWidget(self, title="固有属性", object_name="sample_edit_specific_attributes")
        form_layout.addWidget(self._specific_attrs)

        # --- 関連試料（WebUI準拠: 選択方式 + 説明） ---
        self._related_samples = RelatedSamplesWidget(self, group_id=None)
        self._related_samples.setObjectName("sample_edit_related_samples")
        form_layout.addWidget(self._related_samples)

        root.addWidget(form_group, 2)

        root.addWidget(QLabel("送信内容プレビュー（編集不可）:", self))
        self._preview = QPlainTextEdit(self)
        self._preview.setObjectName("sample_edit_payload_preview")
        self._preview.setReadOnly(True)
        root.addWidget(self._preview, 1)

        # 入力変更でプレビュー更新
        try:
            for item in self._names.sample_inputs:
                item["input"].textChanged.connect(lambda *_: self._refresh_preview())
            self._names.add_button.clicked.connect(lambda *_: self._refresh_preview())
        except Exception:
            pass

        try:
            self._description.textChanged.connect(lambda *_: self._refresh_preview())
        except Exception:
            pass

        try:
            self._composition.textChanged.connect(lambda *_: self._refresh_preview())
            self._reference_url.textChanged.connect(lambda *_: self._refresh_preview())
            self._tags.textChanged.connect(lambda *_: self._refresh_preview())
            self._hide_owner.stateChanged.connect(lambda *_: self._refresh_preview())
        except Exception:
            pass

        try:
            self._general_attrs.changed.connect(lambda *_: self._refresh_preview())
            self._specific_attrs.changed.connect(lambda *_: self._refresh_preview())
        except Exception:
            pass

        try:
            self._sample_class.currentIndexChanged.connect(lambda *_: self._refresh_preview())
        except Exception:
            pass

        self._refresh_preview()

        # ダイアログ起動時に自動でGETし、フォームへ反映する（手動GETを不要にする）
        try:
            self._set_status("起動時に自動取得します...")
            QTimer.singleShot(0, self._on_load)
        except Exception:
            pass

    def _apply_theme(self) -> None:
        try:
            if self._btn_save is not None:
                self._btn_save.setStyleSheet(get_button_style("primary"))
        except Exception:
            pass

    def load_failed(self) -> bool:
        return bool(self._load_failed)

    def _set_status(self, text: str) -> None:
        try:
            self._status.setText(str(text or ""))
        except Exception:
            pass

    def _format_json(self, obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return str(obj)

    def _build_names_list(self) -> list[str]:
        try:
            names = self._names.get_sample_names()
            return [str(x) for x in names if str(x).strip()]
        except Exception:
            return []

    def _build_description_value(self) -> Optional[str]:
        try:
            text = str(self._description.editor.toPlainText() or "").strip()
            return text or None
        except Exception:
            return None

    def _build_tags_list(self) -> list[str]:
        try:
            raw = str(self._tags.text() or "")
            tags = [t.strip() for t in raw.split(",") if t.strip()]
            return tags
        except Exception:
            return []

    def _build_reference_url(self) -> Optional[str]:
        try:
            text = str(self._reference_url.text() or "").strip()
            return text or None
        except Exception:
            return None

    def _normalize_list_attr(self, attrs: Dict[str, Any], key: str) -> None:
        val = attrs.get(key)
        if val is None:
            attrs[key] = []
            return
        if not isinstance(val, list):
            attrs[key] = []

    def _build_payload_from_form(self) -> Dict[str, Any]:
        base_attrs: Dict[str, Any] = {}
        base_rels: Dict[str, Any] = {}
        if isinstance(self._loaded_attrs, dict) and self._loaded_attrs:
            base_attrs = copy.deepcopy(self._loaded_attrs)
        if isinstance(self._loaded_relationships, dict) and self._loaded_relationships:
            base_rels = copy.deepcopy(self._loaded_relationships)

        # ブラウザのPATCHに合わせ、配列フィールドは常に list へ正規化
        for key in ("tags", "generalAttributes", "relatedSamples", "specificAttributes", "customAttributes"):
            self._normalize_list_attr(base_attrs, key)

        # hideOwner は bool（未取得時はFalse）
        if not isinstance(base_attrs.get("hideOwner"), bool):
            base_attrs["hideOwner"] = False

        # names: list[str]
        names = self._build_names_list()
        if names:
            base_attrs["names"] = names

        # description: string
        desc_val = self._build_description_value()
        if desc_val is not None:
            base_attrs["description"] = desc_val

        # composition: 空ならnull（ブラウザ準拠）
        comp_text = str(self._composition.text() or "").strip()
        base_attrs["composition"] = comp_text if comp_text else None

        # referenceUrl: 空ならnull（ブラウザ準拠）
        base_attrs["referenceUrl"] = self._build_reference_url()

        # tags: list[str]（ブラウザ準拠）
        base_attrs["tags"] = self._build_tags_list()

        # hideOwner
        base_attrs["hideOwner"] = bool(self._hide_owner.isChecked())

        # generalAttributes / specificAttributes
        base_attrs["generalAttributes"] = self._general_attrs.get_attributes()
        base_attrs["specificAttributes"] = self._specific_attrs.get_attributes()

        # relatedSamples
        try:
            base_attrs["relatedSamples"] = self._related_samples.get_related_samples()
        except Exception:
            base_attrs["relatedSamples"] = base_attrs.get("relatedSamples") if isinstance(base_attrs.get("relatedSamples"), list) else []

        # relationships: ownerだけを維持（他relationshipの誤更新を避ける）
        relationships: Dict[str, Any] = {}
        owner_rel = base_rels.get("owner") if isinstance(base_rels, dict) else None
        if isinstance(owner_rel, dict) and "data" in owner_rel:
            relationships["owner"] = owner_rel

        data_obj: Dict[str, Any] = {
            "type": str(self._loaded_type or "sample"),
            "id": self._sample_id,
            "attributes": base_attrs,
        }
        if relationships:
            data_obj["relationships"] = relationships

        return {"data": data_obj}

    def _refresh_preview(self) -> None:
        try:
            self._preview.setPlainText(self._format_json(self._build_payload_from_form()))
        except Exception:
            pass

    def _on_load(self) -> None:
        self._set_status("取得中...")
        try:
            resp = self._api.get_sample_detail(self._sample_id)
        except Exception as e:
            logger.error("[SAMPLE-EDIT] GET failed: %s", str(e))
            QMessageBox.warning(self, "試料編集", f"試料詳細の取得に失敗しました:\n{e}")
            self._set_status("取得失敗")
            self._load_failed = True
            try:
                self.reject()
            except Exception:
                pass
            return

        if not resp:
            QMessageBox.warning(self, "試料編集", "試料詳細の取得に失敗しました（レスポンスなし）。")
            self._set_status("取得失敗")
            self._load_failed = True
            try:
                self.reject()
            except Exception:
                pass
            return

        self._last_loaded = resp if isinstance(resp, dict) else None
        data = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(data, dict):
            self._set_status("取得失敗")
            QMessageBox.warning(self, "試料編集", "取得レスポンスの形式が不正です。")
            self._load_failed = True
            try:
                self.reject()
            except Exception:
                pass
            return

        self._loaded_type = str(data.get("type") or "sample")
        attrs = data.get("attributes")
        self._loaded_attrs = attrs if isinstance(attrs, dict) else {}
        rels = data.get("relationships")
        self._loaded_relationships = rels if isinstance(rels, dict) else {}

        # owningGroup id（関連試料の候補読み込みに使用）
        self._loaded_owning_group_id = ""
        try:
            og = self._loaded_relationships.get("owningGroup")
            og_data = og.get("data") if isinstance(og, dict) else None
            if isinstance(og_data, dict) and og_data.get("id"):
                self._loaded_owning_group_id = str(og_data.get("id"))
        except Exception:
            self._loaded_owning_group_id = ""

        # names は list[str]
        names_val = self._loaded_attrs.get("names")
        if isinstance(names_val, list):
            try:
                self._names.set_sample_names([str(x) for x in names_val])
            except Exception:
                pass
        elif isinstance(names_val, str):
            try:
                self._names.set_sample_names([names_val])
            except Exception:
                pass
        else:
            # primaryName があればそれを優先
            primary = self._loaded_attrs.get("primaryName")
            try:
                self._names.set_sample_names([str(primary)]) if isinstance(primary, str) else self._names.set_sample_names([])
            except Exception:
                pass

        desc_val = self._loaded_attrs.get("description")
        if isinstance(desc_val, str):
            try:
                self._description.editor.setPlainText(desc_val)
            except Exception:
                pass
        else:
            try:
                self._description.editor.setPlainText("")
            except Exception:
                pass

        comp = self._loaded_attrs.get("composition")
        if isinstance(comp, str):
            self._composition.setText(comp)
        else:
            self._composition.setText("")

        ref = self._loaded_attrs.get("referenceUrl")
        if isinstance(ref, str):
            self._reference_url.setText(ref)
        else:
            self._reference_url.setText("")

        tags_val = self._loaded_attrs.get("tags")
        if isinstance(tags_val, list):
            self._tags.setText(",".join([str(x) for x in tags_val if str(x).strip()]))
        elif isinstance(tags_val, str):
            self._tags.setText(tags_val)
        else:
            self._tags.setText("")

        hide_owner_val = self._loaded_attrs.get("hideOwner")
        self._hide_owner.setChecked(bool(hide_owner_val) if isinstance(hide_owner_val, bool) else False)

        # attributes rows
        gen = self._loaded_attrs.get("generalAttributes")
        if isinstance(gen, list):
            self._general_attrs.set_attributes(gen)
        else:
            self._general_attrs.set_attributes([])

        spec = self._loaded_attrs.get("specificAttributes")
        if isinstance(spec, list):
            self._specific_attrs.set_attributes(spec)
        else:
            self._specific_attrs.set_attributes([])

        rel = self._loaded_attrs.get("relatedSamples")
        if isinstance(rel, list):
            try:
                self._related_samples.set_related_samples(rel)
            except Exception:
                pass

        # dictionaries
        self._load_terms_and_classes()
        self._configure_related_samples_group()

        self._refresh_preview()
        self._set_status("取得完了")

    def _on_save(self) -> None:
        # 必須チェック（WebUI準拠: 試料名）
        names = self._build_names_list()
        if not names:
            QMessageBox.warning(self, "試料編集", "試料名は必須です。")
            return

        payload = self._build_payload_from_form()
        self._refresh_preview()

        self._set_status("送信中...")
        ok = False
        message = ""
        try:
            ok, message = self._api.update_sample_payload(self._sample_id, payload)
        except Exception as e:
            ok = False
            message = f"更新処理で例外が発生しました: {e}"

        if ok:
            self._set_status("保存完了")
            QMessageBox.information(self, "試料編集", "試料情報を更新しました。")
            self.accept()
        else:
            self._set_status("保存失敗")
            QMessageBox.warning(self, "試料編集", f"試料情報の更新に失敗しました。\n\n{message}")

    def _load_terms_and_classes(self) -> None:
        # 取得に失敗しても編集自体は可能にする
        try:
            terms = None
            if hasattr(self._api, "get_sample_terms"):
                terms = self._api.get_sample_terms(for_general_use=True)
            if isinstance(terms, list):
                self._term_defs = {}
                self._general_term_keys = []
                for item in terms:
                    if not isinstance(item, dict):
                        continue
                    attrs = item.get("attributes")
                    if not isinstance(attrs, dict):
                        continue
                    key_name = str(attrs.get("keyName") or "").strip()
                    if not key_name:
                        continue
                    self._term_defs[key_name] = attrs
                    self._general_term_keys.append(key_name)
        except Exception:
            pass

        try:
            classes = None
            if hasattr(self._api, "get_sample_classes"):
                classes = self._api.get_sample_classes()
            if isinstance(classes, list):
                self._sample_classes = [c for c in classes if isinstance(c, dict)]
        except Exception:
            pass

        # combobox
        try:
            current = str(self._sample_class.currentData() or "")
        except Exception:
            current = ""

        try:
            self._sample_class.blockSignals(True)
            self._sample_class.clear()
            self._sample_class.addItem("（未選択）", "")
            for c in self._sample_classes:
                attrs = c.get("attributes")
                if not isinstance(attrs, dict):
                    continue
                cid = str(c.get("id") or "").strip()
                if not cid:
                    continue
                name_ja = str(attrs.get("nameJa") or "").strip()
                name_en = str(attrs.get("nameEn") or "").strip()
                label = name_ja or name_en or cid
                self._sample_class.addItem(label, cid)
            if current:
                idx = self._sample_class.findData(current)
                if idx >= 0:
                    self._sample_class.setCurrentIndex(idx)
        except Exception:
            pass
        finally:
            try:
                self._sample_class.blockSignals(False)
            except Exception:
                pass

        # rows widgets
        try:
            self._general_attrs.set_term_keys(self._general_term_keys, self._term_defs)
        except Exception:
            pass

        self._on_sample_class_changed()

    def _on_sample_class_changed(self, *_args) -> None:
        cid = ""
        try:
            cid = str(self._sample_class.currentData() or "").strip()
        except Exception:
            cid = ""

        keys: list[str] = []
        if cid:
            for c in self._sample_classes:
                if str(c.get("id") or "").strip() != cid:
                    continue
                attrs = c.get("attributes")
                if not isinstance(attrs, dict):
                    break
                for k in attrs.get("keys") or []:
                    if not isinstance(k, dict):
                        continue
                    key_name = str(k.get("keyName") or "").strip()
                    if key_name:
                        keys.append(key_name)
                break
        self._selected_class_keys = keys

        try:
            self._specific_attrs.set_term_keys(self._selected_class_keys, self._term_defs)
        except Exception:
            pass

    def _configure_related_samples_group(self) -> None:
        # owningGroup が取れた場合のみ候補試料を読み込み
        gid = str(self._loaded_owning_group_id or "").strip()
        if not gid:
            return
        try:
            self._related_samples.load_samples(gid)
        except Exception:
            pass


from qt_compat.core import Signal


class _AttributeRowsWidget(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, title: str, object_name: str):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._term_keys: list[str] = []
        self._term_defs: Dict[str, Dict[str, Any]] = {}
        self._rows: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel(title, self), 1)
        btn_add = QPushButton("+ 追加", self)
        btn_add.clicked.connect(self.add_row)
        header.addWidget(btn_add)
        layout.addLayout(header)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._container = QWidget(self._scroll)
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(4)
        self._container_layout.addStretch(1)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

    def set_term_keys(self, keys: list[str], term_defs: Dict[str, Dict[str, Any]]) -> None:
        self._term_keys = list(keys or [])
        self._term_defs = dict(term_defs or {})
        for row in self._rows:
            self._populate_combo(row["combo"], preserve=row["combo"].currentData())

    def _populate_combo(self, combo: QComboBox, preserve: Any = None) -> None:
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("選択してください...", "")
            for key_name in self._term_keys:
                meta = self._term_defs.get(key_name) or {}
                label = str(meta.get("nameJa") or meta.get("nameEn") or key_name)
                combo.addItem(label, key_name)
                hint = str(meta.get("hintJa") or meta.get("hintEn") or "")
                if hint:
                    combo.setItemData(combo.count() - 1, hint, role=0x0001)  # Qt.ToolTipRole

            if preserve:
                idx = combo.findData(preserve)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        finally:
            combo.blockSignals(False)

    def add_row(self, key_name: str = "", value: str = "") -> None:
        row_widget = QWidget(self._container)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        combo = QComboBox(row_widget)
        self._populate_combo(combo)
        if key_name:
            idx = combo.findData(key_name)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        edit = QLineEdit(row_widget)
        edit.setPlaceholderText("値")
        edit.setText(value or "")

        btn_remove = QPushButton("✕", row_widget)
        btn_remove.setFixedWidth(32)
        btn_remove.clicked.connect(lambda *_: self.remove_row(row_widget))

        combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
        edit.textChanged.connect(lambda *_: self.changed.emit())

        row_layout.addWidget(combo, 2)
        row_layout.addWidget(edit, 3)
        row_layout.addWidget(btn_remove)

        # stretch の前に挿入
        stretch_index = max(0, self._container_layout.count() - 1)
        self._container_layout.insertWidget(stretch_index, row_widget)
        self._rows.append({"widget": row_widget, "combo": combo, "edit": edit})
        self.changed.emit()

    def remove_row(self, row_widget: QWidget) -> None:
        idx = -1
        for i, row in enumerate(self._rows):
            if row.get("widget") is row_widget:
                idx = i
                break
        if idx < 0:
            return
        self._container_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        self._rows.pop(idx)
        self.changed.emit()

    def set_attributes(self, items: list) -> None:
        # clear
        while self._rows:
            self.remove_row(self._rows[-1]["widget"])

        if not items:
            return

        for it in items:
            if not isinstance(it, dict):
                continue
            key_name = str(it.get("keyName") or "").strip()
            value = it.get("value")
            if value is None:
                value = it.get("text")
            self.add_row(key_name=key_name, value=str(value or ""))

    def get_attributes(self) -> list[dict]:
        out: list[dict] = []
        for row in self._rows:
            key = str(row["combo"].currentData() or "").strip()
            val = str(row["edit"].text() or "").strip()
            if not key:
                continue
            if val == "":
                continue
            out.append({"keyName": key, "value": val})
        return out
