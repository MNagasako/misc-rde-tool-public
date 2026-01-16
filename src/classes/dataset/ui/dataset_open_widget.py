"""
データセット開設・編集のタブ付きウィジェット

将来的な拡張:
    このウィジェットでもAI説明文提案機能を実装する場合は、
    AIDescriptionSuggestionDialog を mode="dataset_suggestion" で呼び出す。
    
    使用例:
        from classes.dataset.ui.ai_suggestion_dialog import AISuggestionDialog
        
        dialog = AISuggestionDialog(
            parent=self,
            context_data=context_data,
            auto_generate=True,
            mode="dataset_suggestion"  # データセット提案モード
        )
        
        if dialog.exec() == QDialog.Accepted:
            suggestion = dialog.get_selected_suggestion()
            # 説明文フィールドに反映
"""
import os
import json
import math
from qt_compat.widgets import QWidget, QVBoxLayout, QLabel, QTabWidget, QScrollArea, QApplication
from qt_compat.widgets import QHBoxLayout, QFormLayout, QLineEdit, QTextEdit, QPushButton
from qt_compat.widgets import QButtonGroup, QComboBox, QRadioButton, QSizePolicy
from qt_compat.widgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from qt_compat.core import QDate, Qt
from classes.dataset.core.dataset_open_logic import create_group_select_widget
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import DATASET_JSON_PATH, SUBGROUP_DETAILS_DIR, SUBGROUP_REL_DETAILS_DIR, get_dynamic_file_path

import logging

# ロガー設定
logger = logging.getLogger(__name__)


def _parse_tags_text(text: str) -> list[str]:
    return [tag.strip() for tag in (text or "").split(",") if tag.strip()]


def _sanitize_dataset_name_part(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    for ch in ["\n", "\r", "\t"]:
        text = text.replace(ch, " ")
    # Replace common separators/spaces with underscore
    for ch in [" ", "　", "/", "\\", ":", "|", "(", ")", "[", "]"]:
        text = text.replace(ch, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _contains_case_insensitive(haystack: str, needle: str) -> bool:
    h = (haystack or "").lower()
    n = (needle or "").lower().strip()
    if not n:
        return True
    return n in h


def _create_dataset_create2_tab(parent: QWidget) -> QWidget:
    """Create a new dataset creation tab with extra metadata inputs."""
    create_tab_result = create_group_select_widget(parent, register_subgroup_notifier=False, connect_open_handler=False)
    if not create_tab_result or len(create_tab_result) < 6:
        fallback_widget = QWidget()
        fallback_layout = QVBoxLayout()
        fallback_layout.addWidget(QLabel("データセット開設機能を読み込み中..."))
        fallback_widget.setLayout(fallback_layout)
        return fallback_widget

    manager_combo = None
    if len(create_tab_result) >= 11:
        (
            container,
            team_groups,
            group_combo,
            grant_combo,
            manager_combo,
            open_btn,
            name_edit,
            embargo_edit,
            template_combo,
            template_list,
            _filter_combo,
        ) = create_tab_result[:11]
    else:
        container, team_groups, group_combo, grant_combo, open_btn, name_edit, embargo_edit, template_combo, template_list, _filter_combo = create_tab_result
        manager_combo = getattr(container, "manager_combo", None)

    filter_combo = _filter_combo

    CORE_SHARE_SCOPE_ID = "22aec474-bbf2-4826-bf63-60c82d75df41"

    def _is_nan_value(value) -> bool:
        try:
            return isinstance(value, float) and math.isnan(value)
        except Exception:
            return False

    def _normalize_text_value(value) -> str:
        if value is None or _is_nan_value(value):
            return ""
        text = str(value)
        if text.strip().lower() == "nan":
            return ""
        return text

    def _get_user_grant_numbers() -> set[str]:
        grants: set[str] = set()
        try:
            self_path = get_dynamic_file_path("output/rde/data/self.json")
            sub_group_path = get_dynamic_file_path("output/rde/data/subGroup.json")
            with open(self_path, encoding="utf-8") as f:
                self_data = json.load(f)
            user_id = (self_data.get("data", {}) or {}).get("id")
            if not user_id:
                return grants

            with open(sub_group_path, encoding="utf-8") as f:
                sub_group_data = json.load(f)

            for item in (sub_group_data.get("included", []) or []):
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "group":
                    continue
                attrs = item.get("attributes", {}) or {}
                if (attrs.get("groupType") or "") != "TEAM":
                    continue
                roles = attrs.get("roles", []) or []
                user_in_group = any((r or {}).get("userId") == user_id for r in roles if isinstance(r, dict))
                if not user_in_group:
                    continue
                subjects = attrs.get("subjects", []) or []
                for subject in subjects:
                    if not isinstance(subject, dict):
                        continue
                    grant_number = _normalize_text_value(subject.get("grantNumber")).strip()
                    if grant_number:
                        grants.add(grant_number)
        except Exception:
            logger.debug("新規開設2: user grantNumbers の取得に失敗", exc_info=True)
        return grants

    def _safe_set_combo_by_data(combo: QComboBox | None, target_data: str) -> bool:
        if combo is None:
            return False
        try:
            idx = combo.findData(target_data)
        except Exception:
            idx = -1
        if idx is None or idx < 0:
            return False
        try:
            combo.setCurrentIndex(int(idx))
            return True
        except Exception:
            return False

    def _safe_set_combo_by_text(combo: QComboBox | None, target_text: str) -> bool:
        if combo is None:
            return False
        try:
            idx = combo.findText(target_text)
        except Exception:
            idx = -1
        if idx is None or idx < 0:
            return False
        try:
            combo.setCurrentIndex(int(idx))
            return True
        except Exception:
            return False

    def _read_json(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _find_template_meta(template_id: str) -> dict | None:
        if not template_id:
            return None
        for t in (template_list or []):
            if isinstance(t, dict) and str(t.get("id") or "") == str(template_id):
                return t
        return None

    def _extract_equipment_id_from_template(template_id: str, template_meta: dict | None, display_text: str) -> str:
        try:
            import re

            def _find_id(s: str) -> str | None:
                if not s:
                    return None
                # Prefer bracketed localId: [TU-507]
                m = re.search(r"\[\s*([A-Za-z]{1,3}-[A-Za-z0-9-]{2,})\s*\]", s)
                if m:
                    return m.group(1)
                # Generic equipment id patterns (TU-507, TU-FDL-215)
                m = re.search(r"\b([A-Za-z]{1,3}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\b", s)
                if m:
                    return m.group(1)
                return None

            # instruments labels are the most reliable
            insts = (template_meta or {}).get("instruments") if isinstance(template_meta, dict) else None
            if isinstance(insts, list):
                for inst_label in insts:
                    eq = _find_id(str(inst_label or ""))
                    if eq:
                        return eq
            eq = _find_id(str(template_id or ""))
            if eq:
                return eq
            eq = _find_id(str(display_text or ""))
            if eq:
                return eq
        except Exception:
            pass
        return ""

    def _extract_registration_name_from_template(template_meta: dict | None, display_text: str) -> str:
        # Prefer first instrument's name portion (before [localId])
        try:
            insts = (template_meta or {}).get("instruments") if isinstance(template_meta, dict) else None
            if isinstance(insts, list) and insts:
                first = str(insts[0] or "")
                if "[" in first:
                    first = first.split("[", 1)[0]
                return first.strip()
        except Exception:
            pass
        # Fallback: try parse from display text "... | <inst_label>"
        try:
            if "|" in (display_text or ""):
                tail = display_text.split("|", 1)[1].strip()
                if "[" in tail:
                    tail = tail.split("[", 1)[0]
                if tail:
                    # if multiple instruments, take first
                    if "," in tail:
                        tail = tail.split(",", 1)[0].strip()
                    return tail.strip()
        except Exception:
            pass
        return ""

    def _extract_individual_name_from_template(template_meta: dict | None, display_text: str) -> str:
        # Heuristic: datasetTemplate nameJa is closest to an "individual" label in this context.
        try:
            name_ja = (template_meta or {}).get("nameJa") if isinstance(template_meta, dict) else ""
            name_ja = str(name_ja or "").strip()
            if name_ja:
                return name_ja
        except Exception:
            pass
        # Fallback: strip "(TYPE)" part from display label
        try:
            text = str(display_text or "").strip()
            if " (" in text:
                text = text.split(" (", 1)[0].strip()
            return text
        except Exception:
            return ""

    def _get_trash_icon():
        try:
            from PySide6.QtWidgets import QStyle  # type: ignore

            return container.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        except Exception:
            return None

    _all_dataset_ids_ref: dict[str, set[str]] = {"ids": set()}

    def _resolve_group_label(group_id: str) -> str | None:
        if not group_id:
            return None
        candidate_paths = [
            os.path.join(SUBGROUP_DETAILS_DIR, f"{group_id}.json"),
            os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{group_id}.json"),
        ]
        for path in candidate_paths:
            data = _read_json(path)
            group = (data or {}).get("data", {}) or {}
            attr = (group or {}).get("attributes", {}) or {}
            name = str(attr.get("name") or "").strip()
            subjects = attr.get("subjects", []) or []
            try:
                grant_count = len(subjects)
            except Exception:
                grant_count = 0
            if name:
                return f"{name} ({grant_count}件の課題)"
        return None

    def _extract_dataset_prefill_fields(dataset_id: str) -> dict:
        if not dataset_id:
            return {}
        detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dataset_id}.json")
        detail = _read_json(detail_path)
        data = (detail or {}).get("data", {}) or {}
        attr = (data or {}).get("attributes", {}) or {}
        rel = (data or {}).get("relationships", {}) or {}
        group_id = ((rel.get("group", {}) or {}).get("data", {}) or {}).get("id")
        grant_number = attr.get("grantNumber")

        template_id = ((rel.get("template", {}) or {}).get("data", {}) or {}).get("id")
        related_links = attr.get("relatedLinks")
        tags = attr.get("tags")
        embargo_date = attr.get("embargoDate")
        description = attr.get("description")
        name = attr.get("name")
        is_anonymized = attr.get("isAnonymized")

        related_dataset_ids: list[str] = []
        for item in ((rel.get("relatedDatasets", {}) or {}).get("data", []) or []):
            if isinstance(item, dict) and item.get("id"):
                related_dataset_ids.append(str(item["id"]))

        share_core_scope = None
        try:
            for pol in (attr.get("sharingPolicies", []) or []):
                if not isinstance(pol, dict):
                    continue
                if str(pol.get("scopeId") or "") == CORE_SHARE_SCOPE_ID:
                    share_core_scope = bool(pol.get("permissionToView"))
                    break
        except Exception:
            share_core_scope = None

        return {
            "group_id": (str(group_id) if group_id else None),
            "grant_number": (str(grant_number) if grant_number else None),
            "template_id": (str(template_id) if template_id else None),
            "name": (str(name) if name is not None else None),
            "embargo_date": (str(embargo_date) if embargo_date is not None else None),
            "description": (str(description) if description is not None else None),
            "related_links": (related_links if related_links is not None else None),
            "tags": (tags if tags is not None else None),
            "related_dataset_ids": related_dataset_ids,
            "share_core_scope": share_core_scope,
            "is_anonymized": (bool(is_anonymized) if is_anonymized is not None else None),
        }

    # AI CHECK thread reference (avoid accessing container from destroyed handler)
    _ai_check_thread_ref: dict[str, object | None] = {"thread": None}

    def _stop_ai_thread(thread_obj) -> None:
        try:
            if thread_obj is None:
                return
            if hasattr(thread_obj, "isRunning") and thread_obj.isRunning():
                if hasattr(thread_obj, "stop"):
                    try:
                        thread_obj.stop()
                    except Exception:
                        pass
                # wait up to 3 seconds
                try:
                    thread_obj.wait(3000)
                except Exception:
                    pass
                # force terminate as last resort
                try:
                    if hasattr(thread_obj, "isRunning") and thread_obj.isRunning() and hasattr(thread_obj, "terminate"):
                        thread_obj.terminate()
                except Exception:
                    pass
        except Exception:
            logger.debug("新規開設2: AI CHECK thread cleanup failed", exc_info=True)

    try:
        container.destroyed.connect(lambda *_: _stop_ai_thread(_ai_check_thread_ref.get("thread")))
    except Exception:
        pass

    # Extend the existing QFormLayout
    form_layout = container.layout()
    if not isinstance(form_layout, QFormLayout):
        # Defensive fallback
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.addWidget(container)
        return wrapper

    def _find_row_for_widget(target) -> int:
        try:
            row_count = form_layout.rowCount()
            for row in range(row_count):
                for role in (QFormLayout.LabelRole, QFormLayout.FieldRole, QFormLayout.SpanningRole):
                    item = form_layout.itemAt(row, role)
                    if item is not None and item.widget() is target:
                        return row
        except Exception:
            pass
        return -1

    insert_row = _find_row_for_widget(open_btn)
    if insert_row < 0:
        insert_row = form_layout.rowCount()

    # --- Existing dataset load panel (top) ---
    existing_panel = QWidget(container)
    existing_panel.setObjectName("dataset_create2_existing_dataset_panel")
    try:
        existing_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass

    existing_panel_layout = QVBoxLayout(existing_panel)
    existing_panel_layout.setContentsMargins(10, 8, 10, 8)
    existing_panel_layout.setSpacing(6)

    existing_title = QLabel("既存データセット読み込み", existing_panel)
    try:
        existing_title.setStyleSheet(
            f"font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)};"
        )
    except Exception:
        pass
    existing_panel_layout.addWidget(existing_title)

    # Filters (similar to データエントリー タブ)
    display_filter_widget = QWidget(existing_panel)
    display_filter_layout = QHBoxLayout(display_filter_widget)
    display_filter_layout.setContentsMargins(0, 0, 0, 0)
    display_filter_layout.setSpacing(8)

    display_label = QLabel("表示対象:", display_filter_widget)
    display_user_only_radio = QRadioButton("所属のみ", display_filter_widget)
    display_others_only_radio = QRadioButton("その他のみ", display_filter_widget)
    display_all_radio = QRadioButton("すべて", display_filter_widget)
    display_all_radio.setChecked(True)

    display_group = QButtonGroup(display_filter_widget)
    display_group.addButton(display_user_only_radio)
    display_group.addButton(display_others_only_radio)
    display_group.addButton(display_all_radio)

    display_filter_layout.addWidget(display_label)
    display_filter_layout.addWidget(display_user_only_radio)
    display_filter_layout.addWidget(display_others_only_radio)
    display_filter_layout.addWidget(display_all_radio)
    display_filter_layout.addStretch(1)
    existing_panel_layout.addWidget(display_filter_widget)

    grant_filter_widget = QWidget(existing_panel)
    grant_filter_layout = QHBoxLayout(grant_filter_widget)
    grant_filter_layout.setContentsMargins(0, 0, 0, 0)
    grant_filter_layout.setSpacing(8)
    grant_filter_label = QLabel("課題番号フィルタ:", grant_filter_widget)
    grant_filter_input = QLineEdit(grant_filter_widget)
    grant_filter_input.setObjectName("dataset_create2_existing_dataset_grant_filter")
    grant_filter_input.setPlaceholderText("課題番号 (例: 22XXXXXX)")
    grant_filter_input.setMinimumWidth(200)
    grant_filter_layout.addWidget(grant_filter_label)
    grant_filter_layout.addWidget(grant_filter_input)
    grant_filter_layout.addStretch(1)
    existing_panel_layout.addWidget(grant_filter_widget)

    existing_row = QWidget(existing_panel)
    existing_row_layout = QHBoxLayout(existing_row)
    existing_row_layout.setContentsMargins(0, 0, 0, 0)
    existing_row_layout.setSpacing(8)

    existing_combo = QComboBox(existing_row)
    existing_combo.setObjectName("dataset_create2_existing_dataset_combo")
    existing_combo.setEditable(True)
    existing_combo.setInsertPolicy(QComboBox.NoInsert)
    existing_combo.setMaxVisibleItems(12)
    try:
        existing_combo.view().setMinimumHeight(240)
    except Exception:
        pass
    existing_combo.lineEdit().setPlaceholderText("既存データセットを選択")

    reload_btn = QPushButton("一覧再読込", existing_row)
    reload_btn.setProperty("variant", "secondary")

    existing_row_layout.addWidget(existing_combo, 1)
    existing_row_layout.addWidget(reload_btn, 0)
    existing_panel_layout.addWidget(existing_row)

    try:
        existing_panel.setStyleSheet(
            f"background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};"
            f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};"
            f"border-radius: 6px;"
        )
    except Exception:
        pass

    def _populate_existing_dataset_combo() -> None:
        preserve_id = ""
        try:
            preserve_id = str(existing_combo.currentData() or "")
        except Exception:
            preserve_id = ""

        if display_user_only_radio.isChecked():
            filter_mode = "user_only"
        elif display_others_only_radio.isChecked():
            filter_mode = "others_only"
        else:
            filter_mode = "all"

        grant_filter_text = (grant_filter_input.text() or "").strip().lower()
        user_grants = _get_user_grant_numbers()

        existing_combo.blockSignals(True)
        existing_combo.clear()
        existing_combo.addItem("(選択してください)", "")
        try:
            data = _read_json(DATASET_JSON_PATH)
            datasets = (data or {}).get("data", []) or []

            # Keep a set of all dataset IDs for validating relatedDatasets.
            try:
                _all_dataset_ids_ref["ids"] = {
                    str(it.get("id"))
                    for it in datasets
                    if isinstance(it, dict) and it.get("id")
                }
            except Exception:
                _all_dataset_ids_ref["ids"] = set()

            user_items: list[tuple[str, str]] = []
            other_items: list[tuple[str, str]] = []

            for item in datasets:
                if not isinstance(item, dict):
                    continue
                ds_id = item.get("id")
                if not ds_id:
                    continue
                attr = item.get("attributes", {}) or {}
                name = _normalize_text_value(attr.get("name")).strip() or "名前なし"
                grant = _normalize_text_value(attr.get("grantNumber")).strip()

                if grant_filter_text and grant_filter_text not in (grant or "").lower():
                    continue

                label_parts = [name]
                if grant:
                    label_parts.append(f"[{grant}]")
                label = " ".join(label_parts) if label_parts else str(ds_id)

                if user_grants and grant and grant in user_grants:
                    user_items.append((label, str(ds_id)))
                else:
                    other_items.append((label, str(ds_id)))

            # safety: user_grants が空の時は user_only でも全件扱い
            if filter_mode == "user_only" and not user_grants:
                filter_mode = "all"

            if filter_mode == "user_only":
                items = user_items
            elif filter_mode == "others_only":
                items = other_items
            else:
                items = user_items + other_items

            for label, dsid in items:
                existing_combo.addItem(label, dsid)
        except Exception:
            logger.debug("新規開設2: dataset.json 読み込みに失敗", exc_info=True)
        finally:
            try:
                if preserve_id:
                    idx = existing_combo.findData(preserve_id)
                    if idx >= 0:
                        existing_combo.setCurrentIndex(idx)
                    else:
                        existing_combo.setCurrentIndex(0)
                else:
                    existing_combo.setCurrentIndex(0)
            except Exception:
                existing_combo.setCurrentIndex(0)
            existing_combo.blockSignals(False)

    def _apply_autofill_from_existing_dataset(dataset_id: str) -> None:
        dataset_id = (dataset_id or "").strip()
        if not dataset_id:
            return

        prefill = _extract_dataset_prefill_fields(dataset_id)
        if not prefill:
            return

        group_id = prefill.get("group_id")
        grant_number = prefill.get("grant_number")
        template_id = prefill.get("template_id")

        # 仕様: ロールフィルタ=none / テンプレフィルタ形式=all
        # ※シグナルを止めない: グループ/課題の再ロードが必要
        _safe_set_combo_by_data(filter_combo, "none")

        template_filter_combo = getattr(container, "template_filter_combo", None)
        _safe_set_combo_by_data(template_filter_combo, "all")

        try:
            # サブグループ/課題番号
            if group_id:
                label = _resolve_group_label(str(group_id))
                if label:
                    if not _safe_set_combo_by_text(group_combo, label):
                        if group_combo and group_combo.lineEdit():
                            group_combo.lineEdit().setText(label)

            if grant_number:
                try:
                    idx = grant_combo.findData(grant_number) if grant_combo is not None else -1
                except Exception:
                    idx = -1
                if idx is not None and idx >= 0:
                    if grant_combo is not None:
                        grant_combo.setCurrentIndex(int(idx))
                else:
                    if grant_combo and grant_combo.lineEdit():
                        grant_combo.lineEdit().setText(str(grant_number))

            # テンプレート
            if template_id:
                try:
                    idx = template_combo.findData(template_id) if template_combo is not None else -1
                except Exception:
                    idx = -1
                if idx is not None and idx >= 0:
                    if template_combo is not None:
                        template_combo.setCurrentIndex(int(idx))
                # 見つからない場合は安全側: 何もしない

            # データセット名
            if prefill.get("name") is not None and hasattr(name_edit, "setText"):
                name_edit.setText(str(prefill.get("name") or ""))

            # エンバーゴ期間終了日
            embargo_val = prefill.get("embargo_date")
            if embargo_val and hasattr(embargo_edit, "setDate"):
                date_part = str(embargo_val).split("T", 1)[0]
                parts = date_part.split("-")
                if len(parts) == 3:
                    y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
                    embargo_edit.setDate(QDate(y, m, d))

            # 説明
            desc_edit = getattr(container, "_create2_description_edit", None)
            if prefill.get("description") is not None and desc_edit is not None and hasattr(desc_edit, "setPlainText"):
                desc_edit.setPlainText(str(prefill.get("description") or ""))

            # 関連情報（TITLE:URL をカンマ区切り）
            related_info_edit = getattr(container, "_create2_related_info_edit", None)
            links_val = prefill.get("related_links")
            if related_info_edit is not None and hasattr(related_info_edit, "setText"):
                link_parts: list[str] = []
                if isinstance(links_val, list):
                    for it in links_val:
                        if not isinstance(it, dict):
                            continue
                        title = _normalize_text_value(it.get("title")).strip()
                        url = _normalize_text_value(it.get("url")).strip()
                        if title and url:
                            link_parts.append(f"{title}:{url}")
                    related_info_edit.setText(", ".join(link_parts))
                elif links_val is None or _is_nan_value(links_val) or str(links_val).strip().lower() == "nan":
                    related_info_edit.setText("")

            # TAG
            tags_edit = getattr(container, "_create2_tags_edit", None)
            tags_val = prefill.get("tags")
            if tags_edit is not None and hasattr(tags_edit, "setText"):
                if isinstance(tags_val, list):
                    tag_text = ", ".join([_normalize_text_value(t).strip() for t in tags_val if _normalize_text_value(t).strip()])
                    tags_edit.setText(tag_text)
                elif tags_val is None or _is_nan_value(tags_val) or str(tags_val).strip().lower() == "nan":
                    tags_edit.setText("")
                else:
                    tags_edit.setText(_normalize_text_value(tags_val).strip())

            # 関連データセット
            selected_ids = getattr(container, "_selected_related_dataset_ids", None)
            display = getattr(container, "_create2_related_datasets_display", None)
            ids_val = prefill.get("related_dataset_ids") or []
            if isinstance(selected_ids, list):
                valid_ids = _all_dataset_ids_ref.get("ids") or set()
                filtered = [str(x) for x in ids_val if str(x) and (not valid_ids or str(x) in valid_ids)]
                selected_ids.clear()
                selected_ids.extend(filtered)
                if display is not None and hasattr(display, "setText"):
                    display.setText(f"{len(selected_ids)}件" if selected_ids else "")

            # データ中核拠点広域シェア / 匿名
            share_val = prefill.get("share_core_scope")
            if share_val is not None and share_core_scope_checkbox is not None and hasattr(share_core_scope_checkbox, "setChecked"):
                share_core_scope_checkbox.setChecked(bool(share_val))
            anon_val = prefill.get("is_anonymized")
            if anon_val is not None and anonymize_checkbox is not None and hasattr(anonymize_checkbox, "setChecked"):
                anonymize_checkbox.setChecked(bool(anon_val))
        except Exception:
            logger.debug("新規開設2: 既存データセットからの自動反映に失敗", exc_info=True)

    _populate_existing_dataset_combo()
    reload_btn.clicked.connect(_populate_existing_dataset_combo)
    display_user_only_radio.toggled.connect(lambda *_: _populate_existing_dataset_combo())
    display_others_only_radio.toggled.connect(lambda *_: _populate_existing_dataset_combo())
    display_all_radio.toggled.connect(lambda *_: _populate_existing_dataset_combo())
    grant_filter_input.textChanged.connect(lambda *_: _populate_existing_dataset_combo())
    existing_combo.currentIndexChanged.connect(lambda *_: _apply_autofill_from_existing_dataset(str(existing_combo.currentData() or "")))
    try:
        existing_combo.activated.connect(lambda *_: _apply_autofill_from_existing_dataset(str(existing_combo.currentData() or "")))
    except Exception:
        pass

    # form の先頭に差し込み（背景/枠線で区別）
    form_layout.insertRow(0, existing_panel)
    insert_row += 1

    # 仕様: デフォルトでもロールフィルタ=none、テンプレフィルタ形式=all に寄せる
    _safe_set_combo_by_data(filter_combo, "none")
    _safe_set_combo_by_data(getattr(container, "template_filter_combo", None), "all")

    # Move checkboxes (share/anonymize) to the bottom (after related datasets)
    share_core_scope_checkbox = getattr(container, "share_core_scope_checkbox", None)
    anonymize_checkbox = getattr(container, "anonymize_checkbox", None)

    def _remove_row_for_widget(target) -> None:
        if target is None:
            return
        try:
            row = _find_row_for_widget(target)
            if row >= 0:
                # takeRow は widget を削除せずに行を除去できる
                try:
                    form_layout.takeRow(row)
                except Exception:
                    # 最終フォールバック（行が残る可能性あり）
                    try:
                        form_layout.removeWidget(target)
                    except Exception:
                        pass
        except Exception:
            pass

    _remove_row_for_widget(share_core_scope_checkbox)
    _remove_row_for_widget(anonymize_checkbox)

    # Recompute insertion point (open_btn row index may have shifted)
    insert_row = _find_row_for_widget(open_btn)
    if insert_row < 0:
        insert_row = form_layout.rowCount()

    # --- Open mode (通常 / まとめて開設) ---
    open_mode_widget = QWidget(container)
    open_mode_widget.setObjectName("dataset_create2_open_mode")
    open_mode_layout = QHBoxLayout(open_mode_widget)
    open_mode_layout.setContentsMargins(0, 0, 0, 0)
    open_mode_layout.setSpacing(10)
    open_mode_normal_radio = QRadioButton("通常", open_mode_widget)
    open_mode_normal_radio.setObjectName("dataset_create2_open_mode_normal_radio")
    open_mode_bulk_radio = QRadioButton("複数設備まとめて", open_mode_widget)
    open_mode_bulk_radio.setObjectName("dataset_create2_open_mode_bulk_radio")
    open_mode_normal_radio.setChecked(True)
    open_mode_group = QButtonGroup(open_mode_widget)
    open_mode_group.addButton(open_mode_normal_radio)
    open_mode_group.addButton(open_mode_bulk_radio)
    open_mode_layout.addWidget(open_mode_normal_radio)
    open_mode_layout.addWidget(open_mode_bulk_radio)
    open_mode_layout.addStretch(1)

    # Insert after template combo row for better UX
    try:
        template_row = _find_row_for_widget(template_combo)
        if template_row >= 0:
            form_layout.insertRow(template_row + 1, QLabel("開設タイプ:"), open_mode_widget)
        else:
            form_layout.insertRow(insert_row, QLabel("開設タイプ:"), open_mode_widget)
            insert_row += 1
    except Exception:
        form_layout.insertRow(insert_row, QLabel("開設タイプ:"), open_mode_widget)
        insert_row += 1

    # --- Bulk template table & presets ---
    bulk_panel = QWidget(container)
    bulk_panel.setObjectName("dataset_create2_bulk_panel")
    bulk_layout = QVBoxLayout(bulk_panel)
    bulk_layout.setContentsMargins(0, 0, 0, 0)
    bulk_layout.setSpacing(6)

    bulk_help = QLabel("複数設備まとめて: テンプレートを複数追加し、テンプレごとにデータセット名を設定して開設します。", bulk_panel)
    bulk_help.setWordWrap(True)
    bulk_layout.addWidget(bulk_help)

    bulk_controls = QWidget(bulk_panel)
    bulk_controls_layout = QHBoxLayout(bulk_controls)
    bulk_controls_layout.setContentsMargins(0, 0, 0, 0)
    bulk_controls_layout.setSpacing(8)
    add_template_btn = QPushButton("選択テンプレを追加", bulk_controls)
    add_template_btn.setObjectName("dataset_create2_bulk_add_template_button")
    select_from_list_btn = QPushButton("一覧から選択", bulk_controls)
    select_from_list_btn.setObjectName("dataset_create2_bulk_select_from_list_button")
    clear_btn = QPushButton("クリア", bulk_controls)
    clear_btn.setObjectName("dataset_create2_bulk_clear_button")
    bulk_controls_layout.addWidget(add_template_btn)
    bulk_controls_layout.addWidget(select_from_list_btn)
    bulk_controls_layout.addWidget(clear_btn)
    bulk_controls_layout.addStretch(1)
    bulk_layout.addWidget(bulk_controls)

    bulk_table = QTableWidget(0, 3, bulk_panel)
    bulk_table.setObjectName("dataset_create2_bulk_table")
    bulk_table.setHorizontalHeaderLabels(["テンプレート名", "データセット名", "除外"])
    bulk_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    bulk_table.setSelectionMode(QAbstractItemView.SingleSelection)
    bulk_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed)
    try:
        header = bulk_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    except Exception:
        pass
    bulk_table.setAlternatingRowColors(True)
    bulk_layout.addWidget(bulk_table)

    preset_row = QWidget(bulk_panel)
    preset_row.setObjectName("dataset_create2_bulk_presets")
    preset_layout = QHBoxLayout(preset_row)
    preset_layout.setContentsMargins(0, 0, 0, 0)
    preset_layout.setSpacing(6)
    preset_layout.addWidget(QLabel("データセット名プリセット:", preset_row))

    preset_btn_eq = QPushButton("設備ID", preset_row)
    preset_btn_eq.setObjectName("dataset_create2_preset_equipment_id")
    preset_btn_reg = QPushButton("登録名", preset_row)
    preset_btn_reg.setObjectName("dataset_create2_preset_registration_name")
    preset_btn_ind = QPushButton("個別名", preset_row)
    preset_btn_ind.setObjectName("dataset_create2_preset_individual_name")
    preset_btn_eq_reg = QPushButton("設備ID+登録名", preset_row)
    preset_btn_eq_reg.setObjectName("dataset_create2_preset_equipment_registration")
    preset_btn_eq_ind = QPushButton("設備ID+個別名", preset_row)
    preset_btn_eq_ind.setObjectName("dataset_create2_preset_equipment_individual")

    for b in [preset_btn_eq, preset_btn_reg, preset_btn_ind, preset_btn_eq_reg, preset_btn_eq_ind]:
        preset_layout.addWidget(b)
    preset_layout.addStretch(1)
    bulk_layout.addWidget(preset_row)

    def _bulk_table_template_ids() -> set[str]:
        ids: set[str] = set()
        for r in range(bulk_table.rowCount()):
            it = bulk_table.item(r, 0)
            if it is None:
                continue
            tid = it.data(Qt.UserRole)
            if tid:
                ids.add(str(tid))
        return ids

    def _bulk_remove_template_by_id(template_id: str) -> None:
        try:
            tid = str(template_id or "")
            if not tid:
                return
            for r in range(bulk_table.rowCount()):
                it = bulk_table.item(r, 0)
                if it is None:
                    continue
                if str(it.data(Qt.UserRole) or "") == tid:
                    bulk_table.removeRow(r)
                    return
        except Exception:
            pass

    def _bulk_set_delete_button(row: int, template_id: str) -> None:
        btn = QPushButton("", bulk_table)
        btn.setObjectName("dataset_create2_bulk_delete_button")
        try:
            icon = _get_trash_icon()
            if icon is not None:
                btn.setIcon(icon)
            else:
                btn.setText("🗑")
        except Exception:
            btn.setText("🗑")
        btn.setToolTip("この行を削除")
        btn.setMaximumWidth(34)
        btn.clicked.connect(lambda *_: _bulk_remove_template_by_id(template_id))
        bulk_table.setCellWidget(row, 2, btn)

    def _bulk_insert_template_row(*, template_id: str, template_text: str) -> None:
        if not template_id:
            return
        if template_id in _bulk_table_template_ids():
            return

        default_name = ""
        try:
            default_name = (name_edit.text().strip() if hasattr(name_edit, "text") else "")
        except Exception:
            default_name = ""

        row = bulk_table.rowCount()
        bulk_table.insertRow(row)

        it0 = QTableWidgetItem(template_text or template_id)
        it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
        it0.setData(Qt.UserRole, template_id)
        bulk_table.setItem(row, 0, it0)

        it1 = QTableWidgetItem(default_name)
        it1.setFlags(it1.flags() | Qt.ItemIsEditable)
        bulk_table.setItem(row, 1, it1)

        _bulk_set_delete_button(row, template_id)

    def _bulk_add_current_template() -> None:
        try:
            tid = ""
            ttext = ""
            try:
                tid = str(template_combo.currentData() or "") if template_combo else ""
                ttext = str(template_combo.currentText() or "") if template_combo else ""
            except Exception:
                tid = ""
                ttext = ""

            # allow typed template name resolution similar to on_open2
            if not tid and template_combo is not None and template_combo.isEditable():
                typed = ""
                try:
                    typed = (template_combo.lineEdit().text() or "").strip()
                except Exception:
                    typed = ""
                if typed:
                    try:
                        match_idx = template_combo.findText(typed)
                    except Exception:
                        match_idx = -1
                    if match_idx is not None and match_idx >= 0:
                        try:
                            template_combo.setCurrentIndex(int(match_idx))
                            tid = str(template_combo.currentData() or "")
                            ttext = str(template_combo.currentText() or "")
                        except Exception:
                            pass

            if not tid:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(container, "入力エラー", "テンプレートを選択してください（複数設備まとめて）。")
                return

            _bulk_insert_template_row(template_id=tid, template_text=(ttext or tid))
        except Exception:
            logger.debug("新規開設2: bulk add template failed", exc_info=True)

    def _bulk_clear() -> None:
        try:
            bulk_table.setRowCount(0)
        except Exception:
            pass

    def _open_template_select_dialog() -> None:
        try:
            from qt_compat.widgets import QDialog

            dlg = QDialog(container)
            dlg.setObjectName("dataset_create2_template_select_dialog")
            dlg.setWindowTitle("一覧から選択")
            v = QVBoxLayout(dlg)

            # Header: filter controls (mirror current tab's filter state)
            filter_row = QWidget(dlg)
            filter_row_layout = QHBoxLayout(filter_row)
            filter_row_layout.setContentsMargins(0, 0, 0, 0)
            filter_row_layout.setSpacing(8)

            tab_mode_combo = getattr(container, "template_filter_combo", None)
            tab_org_combo = getattr(container, "template_org_combo", None)

            mode_combo = QComboBox(filter_row)
            mode_combo.setObjectName("dataset_create2_template_select_mode_combo")
            org_combo = QComboBox(filter_row)
            org_combo.setObjectName("dataset_create2_template_select_org_combo")

            # Copy items from tab combos
            if isinstance(tab_mode_combo, QComboBox):
                for i in range(tab_mode_combo.count()):
                    mode_combo.addItem(tab_mode_combo.itemText(i), tab_mode_combo.itemData(i))
                # match current
                try:
                    cur = tab_mode_combo.currentData()
                    if cur is not None:
                        idx = mode_combo.findData(cur)
                        if idx >= 0:
                            mode_combo.setCurrentIndex(idx)
                except Exception:
                    pass
            else:
                mode_combo.addItem("全件", "all")

            def _sync_org_items_from_tab() -> None:
                org_combo.blockSignals(True)
                org_combo.clear()
                if isinstance(tab_org_combo, QComboBox):
                    for i in range(tab_org_combo.count()):
                        org_combo.addItem(tab_org_combo.itemText(i), tab_org_combo.itemData(i))
                    try:
                        cur = tab_org_combo.currentData()
                        if cur is not None:
                            idx = org_combo.findData(cur)
                            if idx >= 0:
                                org_combo.setCurrentIndex(idx)
                    except Exception:
                        pass
                else:
                    org_combo.addItem("(選択してください)", "")
                org_combo.blockSignals(False)

            _sync_org_items_from_tab()

            name_filter = QLineEdit(filter_row)
            name_filter.setObjectName("dataset_create2_template_select_name_filter")
            name_filter.setPlaceholderText("テンプレート名で絞り込み（部分一致）")

            filter_row_layout.addWidget(QLabel("テンプレートフィルタ形式:", filter_row))
            filter_row_layout.addWidget(mode_combo)
            filter_row_layout.addWidget(QLabel("組織フィルタ:", filter_row))
            filter_row_layout.addWidget(org_combo)
            filter_row_layout.addWidget(QLabel("テンプレート名絞り込み:", filter_row))
            filter_row_layout.addWidget(name_filter, 1)
            v.addWidget(filter_row)

            # Table
            table = QTableWidget(0, 2, dlg)
            table.setObjectName("dataset_create2_template_select_table")
            table.setHorizontalHeaderLabels(["選択", "テンプレート名"])
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setAlternatingRowColors(True)
            try:
                from classes.utils.themed_checkbox_delegate import ThemedCheckboxDelegate

                table.setItemDelegateForColumn(0, ThemedCheckboxDelegate(table))
            except Exception:
                pass
            try:
                h = table.horizontalHeader()
                h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
                h.setSectionResizeMode(1, QHeaderView.Stretch)
            except Exception:
                pass
            v.addWidget(table, 1)

            def _collect_current_templates_from_combo() -> list[tuple[str, str]]:
                items: list[tuple[str, str]] = []
                # Use template_combo, which is already filtered by tab controls
                try:
                    for i in range(template_combo.count()):
                        tid = template_combo.itemData(i)
                        label = template_combo.itemText(i)
                        if tid:
                            items.append((str(label), str(tid)))
                except Exception:
                    pass
                # Deduplicate by id, keep order
                seen: set[str] = set()
                uniq: list[tuple[str, str]] = []
                for label, tid in items:
                    if tid in seen:
                        continue
                    seen.add(tid)
                    uniq.append((label, tid))
                return uniq

            def _refresh_table() -> None:
                needle = name_filter.text() if hasattr(name_filter, "text") else ""
                already_added = set()
                try:
                    already_added = _bulk_table_template_ids()
                except Exception:
                    already_added = set()
                candidates = _collect_current_templates_from_combo()
                filtered = [(lbl, tid) for (lbl, tid) in candidates if _contains_case_insensitive(lbl, needle)]
                table.setRowCount(0)
                for lbl, tid in filtered:
                    r = table.rowCount()
                    table.insertRow(r)
                    it0 = QTableWidgetItem("")
                    it0.setFlags((it0.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                    it0.setCheckState(Qt.Checked if tid in already_added else Qt.Unchecked)
                    it0.setData(Qt.UserRole, tid)
                    table.setItem(r, 0, it0)
                    it1 = QTableWidgetItem(lbl)
                    it1.setData(Qt.UserRole, tid)
                    table.setItem(r, 1, it1)

            def _apply_mode_to_tab() -> None:
                if not isinstance(tab_mode_combo, QComboBox):
                    return
                try:
                    data = mode_combo.currentData()
                    if data is None:
                        return
                    idx = tab_mode_combo.findData(data)
                    if idx >= 0:
                        tab_mode_combo.setCurrentIndex(idx)
                except Exception:
                    pass

            def _apply_org_to_tab() -> None:
                if not isinstance(tab_org_combo, QComboBox):
                    return
                try:
                    data = org_combo.currentData()
                    if data is None:
                        return
                    idx = tab_org_combo.findData(data)
                    if idx >= 0:
                        tab_org_combo.setCurrentIndex(idx)
                except Exception:
                    pass

            def _refresh_org_enabled() -> None:
                try:
                    org_combo.setEnabled(str(mode_combo.currentData() or "") == "org")
                except Exception:
                    pass

            def _on_mode_changed(*_a):
                _refresh_org_enabled()
                _apply_mode_to_tab()
                # tab side may rebuild org items
                try:
                    QApplication.processEvents()
                except Exception:
                    pass
                _sync_org_items_from_tab()
                _refresh_table()

            def _on_org_changed(*_a):
                _apply_org_to_tab()
                try:
                    QApplication.processEvents()
                except Exception:
                    pass
                _refresh_table()

            mode_combo.currentIndexChanged.connect(_on_mode_changed)
            org_combo.currentIndexChanged.connect(_on_org_changed)
            name_filter.textChanged.connect(lambda *_: _refresh_table())

            _refresh_org_enabled()
            _refresh_table()

            # Footer buttons
            footer = QWidget(dlg)
            footer_layout = QHBoxLayout(footer)
            footer_layout.setContentsMargins(0, 0, 0, 0)
            footer_layout.setSpacing(8)

            add_btn = QPushButton("テンプレを一括追加", footer)
            add_btn.setObjectName("dataset_create2_template_select_add_button")
            clear_btn2 = QPushButton("クリア", footer)
            clear_btn2.setObjectName("dataset_create2_template_select_clear_button")
            close_btn = QPushButton("閉じる", footer)
            close_btn.setObjectName("dataset_create2_template_select_close_button")

            def _clear_checks():
                for r in range(table.rowCount()):
                    it = table.item(r, 0)
                    if it is not None:
                        it.setCheckState(Qt.Unchecked)

            def _bulk_add_selected_and_close():
                selected: list[tuple[str, str]] = []
                for r in range(table.rowCount()):
                    it0 = table.item(r, 0)
                    it1 = table.item(r, 1)
                    if it0 is None or it1 is None:
                        continue
                    if it0.checkState() != Qt.Checked:
                        continue
                    tid = str(it0.data(Qt.UserRole) or "")
                    lbl = str(it1.text() or "")
                    if tid:
                        selected.append((lbl, tid))
                for lbl, tid in selected:
                    _bulk_insert_template_row(template_id=tid, template_text=lbl)
                dlg.accept()

            add_btn.clicked.connect(_bulk_add_selected_and_close)
            clear_btn2.clicked.connect(lambda *_: _clear_checks())
            close_btn.clicked.connect(dlg.reject)

            footer_layout.addWidget(add_btn)
            footer_layout.addWidget(clear_btn2)
            footer_layout.addStretch(1)
            footer_layout.addWidget(close_btn)
            v.addWidget(footer)

            dlg.resize(900, 520)
            dlg.exec()
        except Exception:
            logger.debug("新規開設2: template select dialog failed", exc_info=True)

    def _bulk_apply_preset(mode: str) -> None:
        base = ""
        try:
            base = (name_edit.text().strip() if hasattr(name_edit, "text") else "")
        except Exception:
            base = ""
        base = _sanitize_dataset_name_part(base)

        for r in range(bulk_table.rowCount()):
            it0 = bulk_table.item(r, 0)
            it1 = bulk_table.item(r, 1)
            if it0 is None or it1 is None:
                continue
            tid = str(it0.data(Qt.UserRole) or "")
            display = str(it0.text() or "")
            meta = _find_template_meta(tid)
            eq = _sanitize_dataset_name_part(_extract_equipment_id_from_template(tid, meta, display))
            reg = _sanitize_dataset_name_part(_extract_registration_name_from_template(meta, display))
            ind = _sanitize_dataset_name_part(_extract_individual_name_from_template(meta, display))

            parts: list[str] = []
            if base:
                parts.append(base)

            if mode == "equipment_id":
                if eq:
                    parts.append(eq)
            elif mode == "registration_name":
                if reg:
                    parts.append(reg)
            elif mode == "individual_name":
                if ind:
                    parts.append(ind)
            elif mode == "equipment_registration":
                if eq:
                    parts.append(eq)
                if reg:
                    parts.append(reg)
            elif mode == "equipment_individual":
                if eq:
                    parts.append(eq)
                if ind:
                    parts.append(ind)

            new_name = "_".join([p for p in parts if p])
            it1.setText(new_name)

    add_template_btn.clicked.connect(_bulk_add_current_template)
    clear_btn.clicked.connect(_bulk_clear)
    select_from_list_btn.clicked.connect(_open_template_select_dialog)
    preset_btn_eq.clicked.connect(lambda *_: _bulk_apply_preset("equipment_id"))
    preset_btn_reg.clicked.connect(lambda *_: _bulk_apply_preset("registration_name"))
    preset_btn_ind.clicked.connect(lambda *_: _bulk_apply_preset("individual_name"))
    preset_btn_eq_reg.clicked.connect(lambda *_: _bulk_apply_preset("equipment_registration"))
    preset_btn_eq_ind.clicked.connect(lambda *_: _bulk_apply_preset("equipment_individual"))

    # Add bulk panel near bottom (before description/related fields)
    form_layout.insertRow(insert_row, QLabel("まとめて開設:"), bulk_panel)
    insert_row += 1

    def _refresh_open_mode_visibility() -> None:
        try:
            bulk_panel.setVisible(bool(open_mode_bulk_radio.isChecked()))
        except Exception:
            pass

    open_mode_normal_radio.toggled.connect(lambda *_: _refresh_open_mode_visibility())
    open_mode_bulk_radio.toggled.connect(lambda *_: _refresh_open_mode_visibility())
    _refresh_open_mode_visibility()

    # --- Description with AI assist ---
    description_layout = QHBoxLayout()
    description_layout.setContentsMargins(0, 0, 0, 0)
    description_layout.setSpacing(8)
    description_edit = QTextEdit(container)
    description_edit.setPlaceholderText("データセットの説明を入力")

    # QTextEdit/QTextBrowser は環境によって ::viewport の描画が揺れるため、
    # viewport側の枠線/背景(QSS)が確実に描画されるよう StyledBackground を付与する。
    try:
        description_edit.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        description_edit.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass

    # 上側へ寄せる: QTextEdit が余白を取り過ぎないよう縦伸びを抑制
    description_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    description_edit.setMinimumHeight(72)
    description_edit.setMaximumHeight(90)
    description_layout.addWidget(description_edit, 1)

    # データセット閲覧・修正タブと同様に: 縦並び + スピナー表示
    ai_buttons_layout = QVBoxLayout()
    ai_buttons_layout.setContentsMargins(0, 0, 0, 0)
    ai_buttons_layout.setSpacing(4)

    from classes.dataset.ui.spinner_button import SpinnerButton

    ai_button = SpinnerButton("🤖 AI提案", container)
    ai_button.setObjectName("dataset_create2_ai_suggest_button")
    ai_button.setMinimumWidth(80)
    ai_button.setMaximumWidth(100)
    ai_button.setMinimumHeight(32)
    ai_button.setMaximumHeight(36)
    ai_button.setToolTip("AIによる説明文の提案（ダイアログ表示）\n複数の候補から選択できます")
    try:
        from classes.theme.theme_keys import ThemeKey as _TK
        from classes.theme.theme_manager import get_color as _gc
        ai_button.setStyleSheet(
            f"QPushButton {{ background-color: {_gc(_TK.BUTTON_SUCCESS_BACKGROUND)}; color: {_gc(_TK.BUTTON_SUCCESS_TEXT)}; "
            f"font-size: 11px; font-weight: bold; border: 1px solid {_gc(_TK.BUTTON_SUCCESS_BORDER)}; "
            f"border-radius: 6px; padding: 4px 8px; }}"
            f"QPushButton:hover {{ background-color: {_gc(_TK.BUTTON_SUCCESS_BACKGROUND_HOVER)}; }}"
            f"QPushButton:disabled {{ background-color: {_gc(_TK.BUTTON_DISABLED_BACKGROUND)}; color: {_gc(_TK.BUTTON_DISABLED_TEXT)}; "
            f"border: 1px solid {_gc(_TK.BUTTON_DISABLED_BORDER)}; }}"
        )
    except Exception:
        pass
    ai_buttons_layout.addWidget(ai_button)

    ai_check_button = SpinnerButton("📋 AI CHECK", container)
    ai_check_button.setObjectName("dataset_create2_ai_check_button")
    ai_check_button.setMinimumWidth(80)
    ai_check_button.setMaximumWidth(100)
    ai_check_button.setMinimumHeight(32)
    ai_check_button.setMaximumHeight(36)
    ai_check_button.setToolTip("説明文の簡易品質チェック\nAIが妥当性を評価します")
    try:
        from classes.theme.theme_keys import ThemeKey as _TK
        from classes.theme.theme_manager import get_color as _gc
        ai_check_button.setStyleSheet(
            f"QPushButton {{ background-color: {_gc(_TK.BUTTON_INFO_BACKGROUND)}; color: {_gc(_TK.BUTTON_INFO_TEXT)}; "
            f"font-size: 11px; font-weight: bold; border: 1px solid {_gc(_TK.BUTTON_INFO_BORDER)}; "
            f"border-radius: 6px; padding: 4px 8px; }}"
            f"QPushButton:hover {{ background-color: {_gc(_TK.BUTTON_INFO_BACKGROUND_HOVER)}; }}"
            f"QPushButton:pressed {{ background-color: {_gc(_TK.BUTTON_INFO_BACKGROUND_PRESSED)}; }}"
            f"QPushButton:disabled {{ background-color: {_gc(_TK.BUTTON_DISABLED_BACKGROUND)}; color: {_gc(_TK.BUTTON_DISABLED_TEXT)}; "
            f"border: 1px solid {_gc(_TK.BUTTON_DISABLED_BORDER)}; }}"
        )
    except Exception:
        pass
    ai_buttons_layout.addWidget(ai_check_button)

    description_layout.addLayout(ai_buttons_layout)

    description_widget = QWidget(container)
    description_widget.setLayout(description_layout)
    form_layout.insertRow(insert_row, QLabel("説明:"), description_widget)
    insert_row += 1

    def _build_ai_context() -> dict:
        context: dict = {}
        try:
            context["name"] = name_edit.text().strip() if hasattr(name_edit, "text") else ""
        except Exception:
            context["name"] = ""
        try:
            grant_text = grant_combo.lineEdit().text().strip() if grant_combo and grant_combo.lineEdit() else ""
            if grant_combo.currentData():
                context["grant_number"] = grant_combo.currentData()
            else:
                # fallback extract
                context["grant_number"] = (grant_text.split(" - ")[0].strip() if grant_text else "")
        except Exception:
            context["grant_number"] = ""

        try:
            template_idx = template_combo.currentIndex() if template_combo else -1
            dtype = template_list[template_idx].get("datasetType") if 0 <= template_idx < len(template_list) else ""
            context["type"] = dtype or "mixed"
        except Exception:
            context["type"] = "mixed"
        try:
            context["description"] = description_edit.toPlainText().strip()
        except Exception:
            context["description"] = ""
        context["access_policy"] = "restricted"
        return context

    def _show_ai_suggestion_dialog():
        try:
            ai_button.start_loading("AI生成中")
            try:
                from qt_compat.widgets import QApplication
                QApplication.processEvents()
            except Exception:
                pass

            from qt_compat.widgets import QDialog
            from classes.dataset.ui.ai_suggestion_dialog import AISuggestionDialog
            dialog = AISuggestionDialog(
                parent=container,
                context_data=_build_ai_context(),
                auto_generate=True,
                mode="dataset_suggestion",
            )
            if dialog.exec() == QDialog.Accepted:
                suggestion = dialog.get_selected_suggestion()
                if suggestion:
                    description_edit.setPlainText(suggestion)
        except Exception as e:
            logger.warning("新規開設2: AI提案ダイアログ表示に失敗: %s", e)
        finally:
            try:
                ai_button.stop_loading()
            except Exception:
                pass

    ai_button.clicked.connect(_show_ai_suggestion_dialog)

    def _show_ai_check_dialog():
        try:
            current_description = description_edit.toPlainText().strip() if hasattr(description_edit, "toPlainText") else ""
            if not current_description:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(container, "警告", "説明文を入力してください")
                return

            ai_check_button.start_loading("チェック中")
            try:
                from qt_compat.widgets import QApplication
                QApplication.processEvents()
            except Exception:
                pass

            # AIテスト2と同じ設定IDを利用
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config
            ai_ext_config = load_ai_extension_config()
            button_config = None
            for entry in ai_ext_config.get("buttons", []):
                if entry.get("id") == "json_check_dataset_summary_simple_quality":
                    button_config = entry
                    break
            if not button_config:
                from qt_compat.widgets import QMessageBox
                QMessageBox.critical(container, "エラー", "品質チェック設定が見つかりません")
                ai_check_button.stop_loading()
                return

            from config.common import get_dynamic_file_path
            prompt_file = button_config.get("prompt_file")
            prompt_path = get_dynamic_file_path(prompt_file)
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    prompt_template = f.read()
            except FileNotFoundError:
                # widgetテストではパス解決の差異で落ちるとスレッド生成/破棄検証ができないため、最小テンプレで継続
                if os.environ.get("PYTEST_CURRENT_TEST"):
                    prompt_template = "{description}"
                else:
                    raise

            from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
            context_collector = get_dataset_context_collector()

            # 新規開設のため dataset_id は None（フォーム入力のみでコンテキストを構築）
            name = name_edit.text().strip() if hasattr(name_edit, "text") else ""
            grant_number = _get_current_grant_number() or ""
            template_idx = template_combo.currentIndex() if template_combo else -1
            dtype = template_list[template_idx].get("datasetType") if 0 <= template_idx < len(template_list) else "mixed"
            full_context = context_collector.collect_full_context(
                dataset_id=None,
                name=name,
                type=dtype or "mixed",
                existing_description=current_description,
                grant_number=grant_number,
            )

            # llm_model_name プレースホルダ置換用
            from classes.ai.core.ai_manager import AIManager
            ai_manager = AIManager()
            provider = ai_manager.get_default_provider()
            model = ai_manager.get_default_model(provider)
            full_context["llm_provider"] = provider
            full_context["llm_model"] = model
            full_context["llm_model_name"] = f"{provider}:{model}"
            full_context["description"] = current_description

            from classes.dataset.util.ai_extension_helper import format_prompt_with_context
            prompt = format_prompt_with_context(prompt_template, full_context)

            from qt_compat.widgets import QDialog
            from classes.dataset.ui.ai_suggestion_dialog import AIRequestThread

            # Stop previous check thread if still running
            _stop_ai_thread(_ai_check_thread_ref.get("thread"))
            _ai_check_thread_ref["thread"] = None

            def _show_ai_check_details(prompt_text: str, response_text: str):
                from qt_compat.widgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
                dlg = QDialog(container)
                dlg.setWindowTitle("AI CHECK 詳細")
                layout = QVBoxLayout(dlg)
                text = QTextEdit(dlg)
                text.setReadOnly(True)
                text.setPlainText(f"【問い合わせ内容】\n{prompt_text}\n\n【AI レスポンス】\n{response_text}")
                layout.addWidget(text)
                close_btn = QPushButton("閉じる", dlg)
                close_btn.clicked.connect(dlg.close)
                layout.addWidget(close_btn)
                dlg.setLayout(layout)
                dlg.exec()

            def on_check_success(result):
                try:
                    ai_check_button.stop_loading()
                except Exception:
                    pass
                response_text = result.get("response", "")

                # ログ保存（結果一覧タブで参照できるようにする）
                try:
                    from classes.dataset.util.ai_suggest_result_log import append_result

                    target_key = (grant_number or '').strip() or (name or '').strip() or 'unknown'
                    append_result(
                        target_kind='dataset',
                        target_key=target_key,
                        button_id='ai_check',
                        button_label='AI CHECK',
                        prompt=prompt,
                        display_format='text',
                        display_content=str(response_text or ''),
                        provider=(result.get('provider') if isinstance(result, dict) else None),
                        model=(result.get('model') if isinstance(result, dict) else None),
                        request_params=(result.get('request_params') if isinstance(result, dict) else None),
                        response_params=(result.get('response_params') if isinstance(result, dict) else None),
                        started_at=(result.get('started_at') if isinstance(result, dict) else None),
                        finished_at=(result.get('finished_at') if isinstance(result, dict) else None),
                        elapsed_seconds=(result.get('elapsed_seconds') if isinstance(result, dict) else None),
                    )
                except Exception:
                    pass

                summary_text = response_text
                try:
                    import json as _json
                    json_str = response_text
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1].split("```")[0].strip()
                    check_result = _json.loads(json_str)
                    score = check_result.get("score", "N/A")
                    judge = check_result.get("judge", "判定不能")
                    reason = check_result.get("reason", "理由なし")
                    char_count = check_result.get("char_count", "N/A")
                    judge_comment = check_result.get("judge_comment", "")
                    parts = [
                        f"スコア: {score}/10",
                        f"文字数: {char_count}",
                        f"判定: {judge}",
                        "",
                        "【判定コメント】",
                        judge_comment or "(なし)",
                        "",
                        "【評価理由】",
                        reason or "(なし)",
                    ]
                    summary_text = "\n".join(parts)
                except Exception:
                    # JSONとして読めない場合はレスポンス全文を表示
                    pass

                from qt_compat.widgets import QMessageBox
                msg = QMessageBox(container)
                msg.setWindowTitle("AI CHECK 結果")
                msg.setText(summary_text)
                msg.setIcon(QMessageBox.Information)
                detail_btn = msg.addButton("詳細を表示", QMessageBox.ActionRole)
                ok_btn = msg.addButton(QMessageBox.Ok)
                msg.setDefaultButton(ok_btn)
                msg.exec()
                if msg.clickedButton() == detail_btn:
                    _show_ai_check_details(prompt, response_text)

                _ai_check_thread_ref["thread"] = None

            def on_check_error(error_msg):
                from qt_compat.widgets import QMessageBox
                QMessageBox.critical(container, "AIエラー", f"品質チェック実行中にエラーが発生しました\n{error_msg}")

                try:
                    ai_check_button.stop_loading()
                except Exception:
                    pass

                _ai_check_thread_ref["thread"] = None

            ai_thread = AIRequestThread(prompt, full_context)
            _ai_check_thread_ref["thread"] = ai_thread
            try:
                ai_thread.finished.connect(lambda: _ai_check_thread_ref.__setitem__("thread", None))
                def _safe_stop_loading():
                    try:
                        ai_check_button.stop_loading()
                    except Exception:
                        pass

                ai_thread.finished.connect(_safe_stop_loading)
            except Exception:
                pass
            ai_thread.result_ready.connect(on_check_success)
            ai_thread.error_occurred.connect(on_check_error)
            ai_thread.start()

        except Exception as e:
            logger.warning("新規開設2: AI CHECKに失敗: %s", e)
            try:
                ai_check_button.stop_loading()
            except Exception:
                pass

    ai_check_button.clicked.connect(_show_ai_check_dialog)

    # --- Related info ---
    related_info_layout = QHBoxLayout()
    related_info_edit = QLineEdit(container)
    related_info_edit.setPlaceholderText("関連情報（設定ボタンで編集）")
    related_info_button = QPushButton("設定...", container)
    related_info_button.setMaximumWidth(80)
    related_info_layout.addWidget(related_info_edit, 1)
    related_info_layout.addWidget(related_info_button)
    related_info_widget = QWidget(container)
    related_info_widget.setLayout(related_info_layout)
    form_layout.insertRow(insert_row, QLabel("関連情報:"), related_info_widget)
    insert_row += 1

    # --- TAG ---
    tags_layout = QHBoxLayout()
    tags_edit = QLineEdit(container)
    tags_edit.setPlaceholderText("TAG（設定ボタンで編集）")
    tags_button = QPushButton("設定...", container)
    tags_button.setMaximumWidth(80)
    tags_layout.addWidget(tags_edit, 1)
    tags_layout.addWidget(tags_button)
    tags_widget = QWidget(container)
    tags_widget.setLayout(tags_layout)
    form_layout.insertRow(insert_row, QLabel("TAG:"), tags_widget)
    insert_row += 1

    # --- Related datasets (dialog-based, same as edit tab) ---
    related_dataset_ids: list[str] = []
    container._selected_related_dataset_ids = related_dataset_ids  # type: ignore[attr-defined]

    related_datasets_layout = QHBoxLayout()
    related_datasets_display = QLineEdit(container)
    related_datasets_display.setReadOnly(True)
    related_datasets_display.setPlaceholderText("関連データセット（設定ボタンで編集）")
    try:
        related_datasets_display.setObjectName("dataset_create2_related_datasets_display")
    except Exception:
        pass
    try:
        from classes.theme.theme_keys import ThemeKey as _TK
        from classes.theme.theme_manager import get_color as _gc
        related_datasets_display.setStyleSheet(
            f"background-color: {_gc(_TK.INPUT_BACKGROUND_DISABLED)}; color: {_gc(_TK.TEXT_MUTED)};"
        )
    except Exception:
        pass
    related_datasets_button = QPushButton("設定...", container)
    related_datasets_button.setMaximumWidth(80)
    related_datasets_layout.addWidget(related_datasets_display, 1)
    related_datasets_layout.addWidget(related_datasets_button)
    related_datasets_widget = QWidget(container)
    related_datasets_widget.setLayout(related_datasets_layout)
    form_layout.insertRow(insert_row, QLabel("関連データセット:"), related_datasets_widget)
    insert_row += 1

    # expose display for existing dataset autofill
    container._create2_related_datasets_display = related_datasets_display  # type: ignore[attr-defined]

    # テーマ切替時に、新規開設2で個別に色埋め込みしているパネル/表示欄を再適用する。
    def _refresh_create2_theme(*_args):
        try:
            existing_panel.setStyleSheet(
                f"background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};"
                f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};"
                f"border-radius: 6px;"
            )
        except Exception:
            pass
        try:
            existing_title.setStyleSheet(
                f"font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)};"
            )
        except Exception:
            pass
        try:
            related_datasets_display.setStyleSheet(
                f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)}; color: {get_color(ThemeKey.TEXT_MUTED)};"
            )
        except Exception:
            pass

    _refresh_create2_theme()

    try:
        from classes.theme.theme_manager import ThemeManager

        _tm = ThemeManager.instance()
        container._create2_theme_slot = _refresh_create2_theme  # type: ignore[attr-defined]
        _tm.theme_changed.connect(container._create2_theme_slot)

        def _disconnect_create2_theme_slot(*_a):
            try:
                _tm.theme_changed.disconnect(container._create2_theme_slot)
            except Exception:
                pass

        try:
            container.destroyed.connect(_disconnect_create2_theme_slot)
        except Exception:
            pass
    except Exception:
        pass

    # Place checkboxes AFTER related datasets
    if share_core_scope_checkbox is not None:
        form_layout.insertRow(insert_row, share_core_scope_checkbox)
        insert_row += 1
    if anonymize_checkbox is not None:
        form_layout.insertRow(insert_row, anonymize_checkbox)
        insert_row += 1

    def _get_current_grant_number() -> str | None:
        try:
            if grant_combo.currentData():
                return str(grant_combo.currentData())
        except Exception:
            pass
        try:
            grant_text = grant_combo.lineEdit().text().strip() if grant_combo and grant_combo.lineEdit() else ""
            if grant_text:
                return grant_text.split(" - ")[0].strip()
        except Exception:
            pass
        return None

    def open_related_datasets_builder():
        try:
            from classes.dataset.ui.related_datasets_builder_dialog import RelatedDatasetsBuilderDialog
            dialog = RelatedDatasetsBuilderDialog(
                parent=container,
                current_dataset_ids=list(related_dataset_ids),
                exclude_dataset_id=None,
                current_grant_number=_get_current_grant_number(),
            )

            def on_datasets_changed(dataset_ids):
                related_dataset_ids.clear()
                related_dataset_ids.extend(list(dataset_ids or []))
                related_datasets_display.setText(f"{len(related_dataset_ids)}件")

            dialog.datasets_changed.connect(on_datasets_changed)
            dialog.exec()
        except Exception as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(container, "エラー", f"関連データセットビルダーの起動に失敗しました:\n{e}")

    related_datasets_button.clicked.connect(open_related_datasets_builder)

    def open_related_links_builder():
        try:
            from classes.dataset.ui.related_links_builder_dialog import RelatedLinksBuilderDialog
            dialog = RelatedLinksBuilderDialog(parent=container, current_links=related_info_edit.text().strip())
            dialog.links_changed.connect(lambda links: related_info_edit.setText(links))
            dialog.exec()
        except Exception as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(container, "エラー", f"関連情報ビルダーの起動に失敗しました:\n{e}")

    related_info_button.clicked.connect(open_related_links_builder)

    def open_tag_builder():
        try:
            from classes.dataset.ui.tag_builder_dialog import TagBuilderDialog
            selected_template_id = None
            selected_template_type = ""
            try:
                selected_template_id = template_combo.currentData() if template_combo else None
            except Exception:
                selected_template_id = None
            if selected_template_id:
                for t in (template_list or []):
                    if isinstance(t, dict) and str(t.get("id") or "") == str(selected_template_id):
                        selected_template_type = str(t.get("datasetType") or "")
                        break
            if not selected_template_type:
                try:
                    idx = template_combo.currentIndex() if template_combo else -1
                    selected_template_type = (
                        template_list[idx].get("datasetType")
                        if 0 <= idx < len(template_list)
                        else ""
                    )
                except Exception:
                    selected_template_type = ""
            dataset_context = {
                "name": name_edit.text().strip() if hasattr(name_edit, "text") else "",
                "type": selected_template_type,
                "grant_number": _get_current_grant_number() or "",
                "description": description_edit.toPlainText().strip() if hasattr(description_edit, "toPlainText") else "",
            }
            dialog = TagBuilderDialog(
                parent=container,
                current_tags=tags_edit.text().strip(),
                dataset_id=None,
                dataset_context=dataset_context,
            )
            dialog.tags_changed.connect(lambda tags: tags_edit.setText(tags))
            dialog.exec()
        except Exception as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(container, "エラー", f"TAGビルダーの起動に失敗しました:\n{e}")

    tags_button.clicked.connect(open_tag_builder)

    def on_open2():
        # Largely same as create_group_select_widget.on_open, but with extra metadata.
        def _format_group_display_text(group: dict) -> str:
            name = group.get("attributes", {}).get("name", "(no name)")
            subjects = group.get("attributes", {}).get("subjects", [])
            grant_count = len(subjects) if subjects else 0
            return f"{name} ({grant_count}件の課題)"

        # create_group_select_widget 内ではフィルタ変更で team_groups が再代入されるため、
        # 返却されたリスト参照を固定で持つと外側が古くなる。container のアクセサがあればそれを優先する。
        current_team_groups = team_groups
        try:
            getter = getattr(container, "_get_current_team_groups", None)
            if callable(getter):
                current_team_groups = getter() or []
        except Exception:
            current_team_groups = team_groups

        selected_group = None
        idx = group_combo.currentIndex() if group_combo else -1
        if idx is not None and 0 <= idx < len(current_team_groups):
            selected_group = current_team_groups[idx]
        else:
            current_group_text = ""
            try:
                current_group_text = (group_combo.lineEdit().text() or "").strip()
            except Exception:
                current_group_text = ""
            if current_group_text:
                for g in current_team_groups:
                    if _format_group_display_text(g) == current_group_text:
                        selected_group = g
                        break

        if not selected_group:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(parent, "グループ未選択", "グループを選択してください。")
            return

        selected_grant_number = None
        grant_text = grant_combo.lineEdit().text() if grant_combo and grant_combo.lineEdit() else ""
        if grant_text and grant_combo.currentData():
            selected_grant_number = grant_combo.currentData()
        elif grant_text:
            parts = grant_text.split(" - ")
            if parts:
                selected_grant_number = parts[0].strip()
        if not selected_grant_number:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(parent, "課題番号未選択", "課題番号を選択してください。")
            return

        group_info = dict(selected_group)
        group_info["grantNumber"] = selected_grant_number

        dataset_name = name_edit.text().strip() if hasattr(name_edit, "text") else ""
        embargo_str = embargo_edit.date().toString("yyyy-MM-dd") if embargo_edit else ""
        template_idx = template_combo.currentIndex() if template_combo else -1

        template_id = ""
        try:
            current_data = template_combo.currentData() if template_combo else None
            if current_data:
                template_id = str(current_data)
        except Exception:
            template_id = ""

        # If user typed a template name (editable combo), resolve it to a real item.
        if not template_id and template_combo is not None and template_combo.isEditable():
            typed_text = ""
            try:
                typed_text = (template_combo.lineEdit().text() or "").strip()
            except Exception:
                typed_text = ""
            if typed_text:
                try:
                    match_idx = template_combo.findText(typed_text)
                except Exception:
                    match_idx = -1
                if match_idx is not None and match_idx >= 0:
                    try:
                        template_combo.setCurrentIndex(int(match_idx))
                        template_idx = template_combo.currentIndex()
                        current_data = template_combo.currentData()
                        if current_data:
                            template_id = str(current_data)
                    except Exception:
                        pass

        dataset_type = "ANALYSIS"
        if template_id:
            try:
                for t in (template_list or []):
                    if isinstance(t, dict) and str(t.get("id") or "") == str(template_id):
                        dataset_type = str(t.get("datasetType") or "ANALYSIS")
                        break
            except Exception:
                dataset_type = "ANALYSIS"
        elif 0 <= template_idx < len(template_list):
            try:
                dataset_type = str(template_list[template_idx].get("datasetType") or "ANALYSIS")
                template_id = str(template_list[template_idx].get("id") or "")
            except Exception:
                dataset_type = "ANALYSIS"

        # bulk mode: dataset names come from table; single mode: keep existing validation.
        is_bulk_mode = False
        try:
            is_bulk_mode = bool(open_mode_bulk_radio.isChecked())
        except Exception:
            is_bulk_mode = False

        if not is_bulk_mode and not dataset_name:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(parent, "入力エラー", "データセット名は必須です。")
            return
        if not embargo_str:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(parent, "入力エラー", "エンバーゴ期間終了日は必須です。")
            return
        if not is_bulk_mode and not template_id:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(parent, "入力エラー", "テンプレートは必須です。")
            return

        resolve_manager = getattr(container, "_resolve_selected_manager_id", None)
        manager_user_id = resolve_manager() if callable(resolve_manager) else None
        if not manager_user_id:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(parent, "データセット管理者未選択", "データセット管理者を選択してください。")
            return

        # extra fields
        description = description_edit.toPlainText().strip() if hasattr(description_edit, "toPlainText") else ""
        related_info = related_info_edit.text().strip() if hasattr(related_info_edit, "text") else ""
        tags = _parse_tags_text(tags_edit.text()) if hasattr(tags_edit, "text") else []
        selected_related_ids = list(related_dataset_ids)

        # Bearer token
        from core.bearer_token_manager import BearerTokenManager
        from qt_compat.widgets import QMessageBox
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            QMessageBox.warning(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
            return

        from classes.dataset.core.dataset_open_logic import run_dataset_open_logic
        # Preserve existing checkboxes on the base form
        share_core_scope = getattr(container, "share_core_scope_checkbox", None)
        anonymize = getattr(container, "anonymize_checkbox", None)
        share_core_scope_val = share_core_scope.isChecked() if share_core_scope else False
        anonymize_val = anonymize.isChecked() if anonymize else False

        if is_bulk_mode:
            from qt_compat.widgets import QMessageBox

            bulk_items: list[dict] = []
            for r in range(bulk_table.rowCount()):
                it0 = bulk_table.item(r, 0)
                it1 = bulk_table.item(r, 1)
                if it0 is None or it1 is None:
                    continue
                tid = str(it0.data(Qt.UserRole) or "")
                dname = str(it1.text() or "").strip()
                if not tid:
                    continue
                if not dname:
                    QMessageBox.warning(parent, "入力エラー", "まとめて開設: データセット名が未入力の行があります。")
                    return

                meta = _find_template_meta(tid) or {}
                dtype = str(meta.get("datasetType") or "ANALYSIS")
                bulk_items.append(
                    {
                        "template_id": tid,
                        "template_text": str(it0.text() or ""),
                        "dataset_name": dname,
                        "dataset_type": dtype,
                    }
                )

            if not bulk_items:
                QMessageBox.warning(parent, "入力エラー", "まとめて開設: 対象テンプレートがありません（未追加）。")
                return

            from classes.dataset.core.dataset_open_logic import run_dataset_bulk_open_logic

            run_dataset_bulk_open_logic(
                parent,
                bearer_token,
                group_info,
                bulk_items,
                embargo_str,
                share_core_scope_val,
                anonymize_val,
                manager_user_id=manager_user_id,
                description=description,
                related_links_text=related_info,
                tags=tags,
                related_dataset_ids=selected_related_ids,
            )
            return

        run_dataset_open_logic(
            parent,
            bearer_token,
            group_info,
            dataset_name,
            embargo_str,
            template_id,
            dataset_type,
            share_core_scope_val,
            anonymize_val,
            manager_user_id=manager_user_id,
            description=description,
            related_links_text=related_info,
            tags=tags,
            related_dataset_ids=selected_related_ids,
        )

    open_btn.clicked.connect(on_open2)
    # Stash for later reference if needed
    container._create2_description_edit = description_edit  # type: ignore[attr-defined]
    container._create2_related_info_edit = related_info_edit  # type: ignore[attr-defined]
    container._create2_tags_edit = tags_edit  # type: ignore[attr-defined]

    return container


def create_dataset_open_widget(parent, title, create_auto_resize_button):
    """データセット開設・編集のタブ付きウィジェット"""
    # メインコンテナ
    main_widget = QWidget()
    main_layout = QVBoxLayout()
    # タブ管理用のリファレンスを保持（クリーンアップや再生成時に使用）
    main_widget._dataset_tab_widget = None  # type: ignore[attr-defined]
    main_widget._dataset_create_tab = None  # type: ignore[attr-defined]
    main_widget._dataset_create2_tab = None  # type: ignore[attr-defined]
    main_widget._dataset_edit_tab = None  # type: ignore[attr-defined]
    main_widget._dataset_dataentry_tab = None  # type: ignore[attr-defined]
    main_widget._dataset_listing_tab = None  # type: ignore[attr-defined]
    
    # タイトル
    label = QLabel(f"{title}機能")
    label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; padding: 10px;")
    #main_layout.addWidget(label)
    
    # タブウィジェット
    tab_widget = QTabWidget()
    main_widget._dataset_tab_widget = tab_widget  # type: ignore[attr-defined]
    
    # 新規開設タブ
    try:
        create_tab_result = create_group_select_widget(parent, register_subgroup_notifier=False)
        if create_tab_result and len(create_tab_result) >= 1:
            create_tab = create_tab_result[0]  # containerウィジェットを取得
            main_widget._dataset_create_tab = create_tab  # type: ignore[attr-defined]
            tab_widget.addTab(create_tab, "新規開設")
            # 新しい戻り値形式に対応: container, team_groups, combo, grant_combo, open_btn, name_edit, embargo_edit, template_combo, template_list
        else:
            # フォールバック：空のウィジェット
            from qt_compat.widgets import QLabel as FallbackLabel
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout()
            fallback_layout.addWidget(FallbackLabel("データセット開設機能を読み込み中..."))
            fallback_widget.setLayout(fallback_layout)
            tab_widget.addTab(fallback_widget, "新規開設")
    except Exception as e:
        logger.warning("データセット開設タブの作成に失敗: %s", e)
        # エラー時は空のタブを作成
        from qt_compat.widgets import QLabel as ErrorLabel
        error_widget = QWidget()
        error_layout = QVBoxLayout()
        error_layout.addWidget(ErrorLabel(f"データセット開設機能の読み込みに失敗しました: {e}"))
        error_widget.setLayout(error_layout)
        tab_widget.addTab(error_widget, "新規開設")

    # 新規開設2タブ（遅延ロード：初回表示を軽くする）
    create2_tab = None
    create2_idx = -1
    try:
        create2_placeholder = QWidget()
        create2_layout = QVBoxLayout(create2_placeholder)
        create2_layout.addWidget(QLabel("新規開設2を読み込み中..."))
        create2_layout.addStretch(1)
        create2_idx = tab_widget.addTab(create2_placeholder, "新規開設2")
        main_widget._dataset_create2_tab = create2_placeholder  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("データセット開設2タブのプレースホルダ作成に失敗: %s", e)

    create2_tab_ref = {"tab": getattr(main_widget, '_dataset_create2_tab', None)}

    # サブグループ更新通知は dataset_open 全体で1回だけ登録し、両タブを更新する
    try:
        from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier

        create_tab = getattr(main_widget, '_dataset_create_tab', None)

        def _refresh_both_create_tabs():
            for tab in (create_tab, create2_tab_ref.get("tab")):
                refresh_fn = getattr(tab, '_refresh_subgroup_data', None)
                if callable(refresh_fn):
                    try:
                        refresh_fn()
                    except Exception:
                        logger.debug("dataset_open: subgroup refresh failed", exc_info=True)

        subgroup_notifier = get_subgroup_refresh_notifier()
        subgroup_notifier.register_callback(_refresh_both_create_tabs)

        # UIController の既存クリーンアップ経路に乗せる（create_tab の属性として保持）
        if create_tab is not None:
            def _cleanup_callback():
                try:
                    subgroup_notifier.unregister_callback(_refresh_both_create_tabs)
                except Exception:
                    pass
            create_tab._cleanup_subgroup_callback = _cleanup_callback  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug("dataset_open: subgroup notifier wiring failed: %s", e)
    
    # 編集タブ（遅延ロード：初回表示を軽くする）
    edit_tab = None  # 実体（中身）
    edit_scroll = None  # タブとして追加されるラッパ
    edit_built = False
    try:
        edit_scroll = QScrollArea()
        edit_scroll.setWidgetResizable(True)
        edit_scroll.setFrameStyle(0)
        edit_scroll.setContentsMargins(0, 0, 0, 0)
        edit_scroll.setWidget(QLabel("閲覧・修正タブを読み込み中..."))
        tab_widget.addTab(edit_scroll, "閲覧・修正")
        main_widget._dataset_edit_tab = edit_scroll  # type: ignore[attr-defined]
        main_widget._dataset_edit_inner_tab = None  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("データセット編集タブのプレースホルダ作成に失敗: %s", e)
        edit_scroll = None
    
    # データエントリータブ（遅延ロード：初回表示を軽くする）
    dataentry_tab = None
    dataentry_built = False
    try:
        dataentry_placeholder = QWidget()
        dataentry_layout = QVBoxLayout(dataentry_placeholder)
        dataentry_layout.addWidget(QLabel("タイル（データエントリー）を読み込み中..."))
        dataentry_layout.addStretch(1)
        tab_widget.addTab(dataentry_placeholder, "タイル（データエントリー）")
        main_widget._dataset_dataentry_tab = dataentry_placeholder  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("データエントリータブのプレースホルダ作成に失敗: %s", e)

    # 一覧タブ（遅延ロード：初回表示を軽くする）
    listing_tab = None
    listing_built = False
    try:
        listing_placeholder = QWidget()
        listing_layout = QVBoxLayout(listing_placeholder)
        listing_layout.addWidget(QLabel("一覧を読み込み中..."))
        listing_layout.addStretch(1)
        tab_widget.addTab(listing_placeholder, "一覧")
        main_widget._dataset_listing_tab = listing_placeholder  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("一覧タブのプレースホルダ作成に失敗: %s", e)
    
    def _ensure_create2_built() -> None:
        nonlocal create2_tab
        if create2_tab is not None:
            return
        if create2_idx < 0:
            return
        try:
            built = _create_dataset_create2_tab(parent)
            create2_tab = built
            # notifier refresh 対象も差し替える
            try:
                create2_tab_ref["tab"] = built
            except Exception:
                pass

            tab_widget.blockSignals(True)
            tab_widget.removeTab(create2_idx)
            tab_widget.insertTab(create2_idx, built, "新規開設2")
            tab_widget.setCurrentIndex(create2_idx)
        except Exception as e:
            logger.warning("データセット開設2タブの作成に失敗: %s", e)
        finally:
            try:
                tab_widget.blockSignals(False)
            except Exception:
                pass

    def _ensure_edit_built() -> None:
        nonlocal edit_tab, edit_built
        if edit_built:
            return
        if edit_scroll is None:
            edit_built = True
            return
        try:
            from classes.dataset.ui.dataset_edit_widget import create_dataset_edit_widget

            edit_tab = create_dataset_edit_widget(parent, "データセット編集", create_auto_resize_button)
            edit_scroll.setWidget(edit_tab)
            main_widget._dataset_edit_inner_tab = edit_tab  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("データセット編集タブの作成に失敗: %s", e)
            try:
                edit_scroll.setWidget(QLabel(f"データセット編集タブの読み込みに失敗しました: {e}"))
            except Exception:
                pass
        finally:
            edit_built = True

    def _ensure_dataentry_built() -> None:
        nonlocal dataentry_tab, dataentry_built
        if dataentry_built:
            return
        try:
            from classes.dataset.ui.dataset_dataentry_widget_minimal import create_dataset_dataentry_widget

            built = create_dataset_dataentry_widget(parent, "データエントリー", create_auto_resize_button)
            dataentry_tab = built

            # 末尾に追加したプレースホルダを差し替え（同名タブを探して置換）
            idx = next((i for i in range(tab_widget.count()) if tab_widget.tabText(i) == "タイル（データエントリー）"), -1)
            if idx >= 0:
                tab_widget.blockSignals(True)
                tab_widget.removeTab(idx)
                tab_widget.insertTab(idx, built, "タイル（データエントリー）")
                tab_widget.setCurrentIndex(idx)
            main_widget._dataset_dataentry_tab = built  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("データエントリータブの作成に失敗: %s", e)
        finally:
            dataentry_built = True
            try:
                tab_widget.blockSignals(False)
            except Exception:
                pass

    def _ensure_listing_built() -> None:
        nonlocal listing_tab, listing_built
        if listing_built:
            return
        try:
            from classes.dataset.ui.dataset_listing_widget import create_dataset_listing_widget

            built = create_dataset_listing_widget(parent, "一覧")

            # 「ツール内」リンク: 閲覧・修正タブで該当データセットを開く
            try:
                if hasattr(built, "set_tool_open_callback"):
                    def _open_in_tool(dataset_id: str) -> None:
                        try:
                            if not dataset_id:
                                return
                            # 先に閲覧・修正タブへ移動
                            edit_idx = next((i for i in range(tab_widget.count()) if tab_widget.tabText(i) == "閲覧・修正"), -1)
                            if edit_idx >= 0:
                                tab_widget.setCurrentIndex(edit_idx)
                            # 生成を保証
                            _ensure_edit_built()
                            target = edit_tab
                            if target is None and edit_scroll is not None:
                                try:
                                    target = edit_scroll.widget()
                                except Exception:
                                    target = None
                            # 表示スコープを「すべて」に緩和（ユーザー所属のみだと表示されないケースがある）
                            try:
                                from PySide6.QtWidgets import QRadioButton, QLineEdit
                                from classes.dataset.ui.dataset_edit_widget import relax_dataset_edit_filters_for_launch

                                if target is not None:
                                    all_radio = target.findChild(QRadioButton, "dataset_filter_all_radio")
                                    user_radio = target.findChild(QRadioButton, "dataset_filter_user_only_radio")
                                    others_radio = target.findChild(QRadioButton, "dataset_filter_others_radio")
                                    grant_edit = target.findChild(QLineEdit, "dataset_grant_number_filter_edit")
                                    relax_dataset_edit_filters_for_launch(
                                        all_radio,
                                        other_radios=[r for r in [user_radio, others_radio] if r is not None],
                                        grant_filter_edit=grant_edit,
                                        apply_filter_callback=getattr(target, "_refresh_dataset_list", None),
                                    )
                            except Exception:
                                logger.debug("dataset_open: relax filters failed", exc_info=True)
                            if target is not None and hasattr(target, "_restore_dataset_selection"):
                                target._restore_dataset_selection(dataset_id)
                        except Exception:
                            logger.debug("dataset_open: tool-open failed", exc_info=True)

                    built.set_tool_open_callback(_open_in_tool)
            except Exception:
                pass

            # 「アプリ内リンク」: データポータルへ遷移し、dataset_idを事前選択
            try:
                if hasattr(built, "set_portal_open_callback"):
                    def _open_in_portal(dataset_id: str) -> None:
                        try:
                            if not dataset_id:
                                return
                            ui_controller = getattr(parent, "ui_controller", None)
                            if ui_controller is None or not hasattr(ui_controller, "switch_mode"):
                                return

                            ui_controller.switch_mode("data_portal")
                            portal_widget = None
                            try:
                                if hasattr(ui_controller, "get_mode_widget"):
                                    portal_widget = ui_controller.get_mode_widget("data_portal")
                            except Exception:
                                portal_widget = getattr(ui_controller, "data_portal_widget", None)

                            if portal_widget is None:
                                portal_widget = getattr(ui_controller, "data_portal_widget", None)

                            open_fn = getattr(portal_widget, "open_upload_and_select_dataset", None)
                            if callable(open_fn):
                                open_fn(dataset_id)
                        except Exception:
                            logger.debug("dataset_open: portal-open failed", exc_info=True)

                    built.set_portal_open_callback(_open_in_portal)
            except Exception:
                pass

            listing_tab = built

            idx = next((i for i in range(tab_widget.count()) if tab_widget.tabText(i) == "一覧"), -1)
            if idx >= 0:
                tab_widget.blockSignals(True)
                tab_widget.removeTab(idx)
                tab_widget.insertTab(idx, built, "一覧")
                tab_widget.setCurrentIndex(idx)
            main_widget._dataset_listing_tab = built  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("一覧タブの作成に失敗: %s", e)
        finally:
            listing_built = True
            try:
                tab_widget.blockSignals(False)
            except Exception:
                pass

    # タブ切り替え時にデータセットリストをリフレッシュする機能を追加
    def on_tab_changed(index):
        """タブ切り替え時の処理"""
        try:
            current_tab = tab_widget.widget(index)
            if create2_idx >= 0 and index == create2_idx:
                _ensure_create2_built()
                return

            if current_tab is main_widget._dataset_edit_tab:
                _ensure_edit_built()
                logger.info("修正タブが選択されました - データセットリストをリフレッシュします")
                if edit_tab is not None and hasattr(edit_tab, '_refresh_dataset_list'):
                    edit_tab._refresh_dataset_list()
                    logger.info("データセットリストのリフレッシュが完了しました")
                else:
                    logger.debug("データセットリフレッシュ機能がスキップされました (edit_tab=%s)", edit_tab is not None)

                # 表示タイミングで縦サイズをディスプレイに合わせる（再表示のたびにリセット）
                try:
                    window = main_widget.window()
                    screen = window.screen() if hasattr(window, 'screen') else None
                    if screen is None:
                        screen = QApplication.primaryScreen()
                    if screen is not None:
                        available = screen.availableGeometry()
                        window.resize(window.width(), available.height())
                except Exception:
                    logger.debug("dataset_open: window height reset failed", exc_info=True)
            elif current_tab is main_widget._dataset_dataentry_tab:
                _ensure_dataentry_built()
                logger.info("データエントリータブが選択されました")
            elif current_tab is main_widget._dataset_listing_tab:
                _ensure_listing_built()
                logger.info("一覧タブが選択されました")

                # 一覧タブは横幅を十分確保して表示（ユーザーが自由にリサイズ可能）
                try:
                    window = main_widget.window()

                    # UIController/EventHandler による横幅固定を解除
                    try:
                        if hasattr(window, '_fixed_aspect_ratio'):
                            window._fixed_aspect_ratio = None
                        if hasattr(window, 'setMinimumSize'):
                            window.setMinimumSize(200, 200)
                        if hasattr(window, 'setMaximumSize'):
                            window.setMaximumSize(16777215, 16777215)
                        if hasattr(window, 'setMinimumWidth'):
                            window.setMinimumWidth(200)
                        if hasattr(window, 'setMaximumWidth'):
                            window.setMaximumWidth(16777215)
                        if hasattr(window, 'showNormal'):
                            window.showNormal()
                    except Exception:
                        pass

                    screen = window.screen() if hasattr(window, 'screen') else None
                    if screen is None:
                        screen = QApplication.primaryScreen()
                    if screen is not None:
                        available = screen.availableGeometry()
                        target_w = int(available.width() * 0.90)
                        target_h = int(available.height() * 0.90)
                        window.resize(target_w, target_h)
                except Exception:
                    logger.debug("dataset_open: listing window resize failed", exc_info=True)
        except Exception as e:
            logger.error("タブ切り替え時のリフレッシュ処理でエラー: %s", e)
    
    tab_widget.currentChanged.connect(on_tab_changed)
    
    main_layout.addWidget(tab_widget)
    main_widget.setLayout(main_layout)
    
    return main_widget


def create_original_dataset_open_widget(parent, title, create_auto_resize_button):
    """元のデータセット開設ウィジェット（後方互換性のため）"""
    # create_group_select_widgetをラップ
    try:
        result = create_group_select_widget(parent)
        if result and len(result) >= 1:
            return result[0]  # containerウィジェットを返す（新しい戻り値形式でも最初の要素はcontainer）
        else:
            # フォールバック
            widget = QWidget()
            layout = QVBoxLayout()
            layout.addWidget(QLabel("データセット開設機能を読み込み中..."))
            widget.setLayout(layout)
            return widget
    except Exception as e:
        logger.error("データセット開設ウィジェットの作成に失敗: %s", e)
        # エラー時は空のウィジェット
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"データセット開設機能の読み込みに失敗しました: {e}"))
        widget.setLayout(layout)
        return widget
