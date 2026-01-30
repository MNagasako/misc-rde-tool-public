"""Shared dataset filter helper for combo boxes.

Provides grant/program/text filters (mirroring the Data Fetch 2 UX minus
wide-share/member controls) while keeping combo population logic reusable.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from qt_compat.core import Qt, QObject, QTimer, QEvent
from qt_compat.gui import QKeyEvent, QFontMetrics
from qt_compat.widgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QtWidgets,
)

from classes.dataset.util.dataset_dropdown_util import get_dataset_type_display_map
from classes.dataset.util.dataset_list_table_records import _build_grant_number_to_subgroup_info
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color
from config.common import get_dynamic_file_path

try:
    from shiboken6 import isValid as qt_is_valid  # type: ignore
except Exception:  # pragma: no cover
    def qt_is_valid(obj: object) -> bool:  # type: ignore
        return obj is not None

logger = logging.getLogger(__name__)


class DatasetFilterFetcher(QObject):
    """Create and manage dataset filters bound to a combo box."""

    def __init__(
        self,
        dataset_json_path: str,
        info_json_path: Optional[str] = None,
        subgroup_json_path: Optional[str] = None,
        combo: Optional[QComboBox] = None,
        *,
        show_text_search_field: bool = True,
        clear_on_blank_click: bool = False,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.dataset_json_path = dataset_json_path
        self.info_json_path = info_json_path
        self.subgroup_json_path = subgroup_json_path
        self.combo = combo
        self._show_text_search_field = show_text_search_field
        self._clear_on_blank_click = clear_on_blank_click
        self._filter_widget: Optional[QWidget] = None
        self._program_combo: Optional[QComboBox] = None
        self._subgroup_combo: Optional[QComboBox] = None
        self._grant_edit: Optional[QLineEdit] = None
        self._search_edit: Optional[QLineEdit] = None
        self._count_label: Optional[QLabel] = None
        self._datasets: List[Dict] = []
        self._filtered_datasets: List[Dict] = []
        self._suppress_filters = False
        self._populate_generation = 0
        self._combo_signal_connected = False
        self._combo_event_filter_installed = False
        self._combo_line_edit_event_filter_installed = False
        self._combo_popup_event_filter_installed = False
        self._combo_line_edit: Optional[QLineEdit] = None
        self._combo_popup_view: Optional[QWidget] = None
        self._combo_popup_viewport: Optional[QWidget] = None
        self._popup_focus_suppressed = False
        self._popup_view_old_focus_policy: Optional[Qt.FocusPolicy] = None
        self._popup_viewport_old_focus_policy: Optional[Qt.FocusPolicy] = None
        self._typing_popup_active = False
        self._pending_popup = False
        self._logged_combo_connected = False
        self._logged_first_combo_input = False
        self._app_about_to_quit = False
        self._search_edit_authoritative = False
        self._subgroup_map: Dict[str, Dict[str, str]] = {}

        # When running under pytest-qt (or any GUI app), Qt teardown order can be fragile.
        # Guard all deferred callbacks so they don't touch Qt objects during shutdown.
        try:
            app = QtWidgets.QApplication.instance()
        except Exception:
            app = None
        if app is not None:
            try:
                app.aboutToQuit.connect(self._on_app_about_to_quit)
            except Exception:
                pass

        if self.combo:
            try:
                self.combo.destroyed.connect(self._on_combo_destroyed)
            except Exception:
                pass
        self._load_dataset_items()

    def _on_combo_destroyed(self, *_args: object) -> None:
        # Invalidate any pending QTimer callbacks that may try to touch the combo.
        self._populate_generation += 1
        self.combo = None

    def _on_app_about_to_quit(self, *_args: object) -> None:
        # Invalidate any pending callbacks that might try to touch Qt objects.
        self._app_about_to_quit = True
        self._populate_generation += 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_filter_panel(self, parent: Optional[QWidget] = None) -> QWidget:
        """Return (and lazily create) the filter panel widget."""

        if self._filter_widget:
            return self._filter_widget

        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        filters_layout = QHBoxLayout()
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(10)

        program_label = QLabel("プログラム / タイプ:")
        program_label.setStyleSheet("font-weight: bold;")
        program_combo = QComboBox()
        program_combo.setMinimumWidth(180)
        self._program_combo = program_combo
        self._populate_programs()
        self._program_combo.setCurrentIndex(0)

        subgroup_label = QLabel("サブグループ:")
        subgroup_label.setStyleSheet("font-weight: bold;")
        subgroup_combo = QComboBox()
        subgroup_combo.setObjectName("datasetFilterSubgroupCombo")
        subgroup_combo.setMinimumWidth(200)
        self._subgroup_combo = subgroup_combo
        self._populate_subgroups()

        grant_label = QLabel("課題番号:")
        grant_label.setStyleSheet("font-weight: bold;")
        grant_edit = QLineEdit()
        grant_edit.setPlaceholderText("部分一致で絞り込み (例: JPMXP1234)")
        grant_edit.setMinimumWidth(200)
        self._grant_edit = grant_edit

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("名前・タイトル・説明で検索")
        search_edit.setMinimumWidth(220)
        self._search_edit = search_edit

        filters_layout.addWidget(program_label)
        filters_layout.addWidget(program_combo)
        filters_layout.addWidget(subgroup_label)
        filters_layout.addWidget(subgroup_combo)
        filters_layout.addWidget(grant_label)
        filters_layout.addWidget(grant_edit)
        if self._show_text_search_field:
            search_label = QLabel("テキスト検索:")
            search_label.setStyleSheet("font-weight: bold;")
            filters_layout.addWidget(search_label)
            filters_layout.addWidget(search_edit)
        filters_layout.addStretch()

        layout.addLayout(filters_layout)

        count_label = QLabel("表示中: 0/0 件")
        count_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        count_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-weight: bold;"
        )
        self._count_label = count_label
        layout.addWidget(count_label)

        self._connect_filter_signals()
        self._connect_combo_signals()
        self._filter_widget = container
        self.apply_filters()
        return container

    def eventFilter(self, obj: object, event: object) -> bool:  # type: ignore[override]
        """Intercept combo arrow clicks to behave like 'show all'."""

        if not self.combo:
            return super().eventFilter(obj, event)

        # Popup view lifecycle: when we suppress focus stealing for typing popups,
        # restore the original focus policies once the popup is hidden.
        if obj is self._combo_popup_view or obj is self._combo_popup_viewport:
            try:
                if self._typing_popup_active and event.type() == QEvent.KeyPress:
                    # Even if Qt moves focus to the popup list, keep text entry stable by
                    # forwarding typing keys into the editable lineEdit.
                    line_edit = self.combo.lineEdit() if self.combo and self.combo.isEditable() else None
                    if line_edit and qt_is_valid(line_edit):
                        key = event.key() if hasattr(event, "key") else None
                        if key is not None:
                            navigation_keys = {
                                Qt.Key_Up,
                                Qt.Key_Down,
                                Qt.Key_PageUp,
                                Qt.Key_PageDown,
                                Qt.Key_Home,
                                Qt.Key_End,
                                Qt.Key_Enter,
                                Qt.Key_Return,
                                Qt.Key_Escape,
                                Qt.Key_Tab,
                            }
                            if key not in navigation_keys:
                                try:
                                    forwarded = QKeyEvent(
                                        event.type(),
                                        key,
                                        event.modifiers(),
                                        event.text(),
                                        event.isAutoRepeat(),
                                        event.count(),
                                    )
                                except Exception:
                                    forwarded = None
                                if forwarded is not None:
                                    QtWidgets.QApplication.sendEvent(line_edit, forwarded)
                                    return True

                if event.type() == QEvent.Show and self._typing_popup_active:
                    QTimer.singleShot(0, self._restore_combo_line_edit_focus)
                if event.type() == QEvent.FocusIn and self._typing_popup_active:
                    # Some styles force focus to the popup; immediately return it to the input.
                    QTimer.singleShot(0, self._restore_combo_line_edit_focus)
                if event.type() == QEvent.Hide:
                    self._typing_popup_active = False
                    self._restore_popup_focus_policy_if_needed()
            except Exception:
                pass
            return super().eventFilter(obj, event)

        # Optional UX: clicking the blank area (right side) inside the combo's lineEdit clears input.
        # This is intentionally opt-in because it may surprise in other screens.
        if self._clear_on_blank_click and self._combo_line_edit and obj is self._combo_line_edit:
            try:
                if event.type() == QEvent.MouseButtonPress:
                    text = self._combo_line_edit.text()
                    if not text:
                        return super().eventFilter(obj, event)

                    # Determine click position (Qt6 has position(); Qt5 has pos()).
                    pos = None
                    if hasattr(event, "position"):
                        try:
                            pos = event.position().toPoint()
                        except Exception:
                            pos = None
                    if pos is None and hasattr(event, "pos"):
                        try:
                            pos = event.pos()
                        except Exception:
                            pos = None
                    if pos is None:
                        return super().eventFilter(obj, event)

                    margins = self._combo_line_edit.textMargins()
                    metrics = QFontMetrics(self._combo_line_edit.font())
                    text_width = metrics.horizontalAdvance(text)

                    # If clicked beyond the rendered text area, clear.
                    # Add a small padding to account for caret/spacing.
                    threshold_x = margins.left() + text_width + 6
                    if pos.x() > threshold_x:
                        # Clear selection + typed text without triggering the typing-popup behaviour.
                        self._pending_popup = False
                        self._typing_popup_active = False
                        self._restore_popup_focus_policy_if_needed()

                        self._suppress_filters = True
                        try:
                            if self.combo and qt_is_valid(self.combo):
                                try:
                                    self.combo.blockSignals(True)
                                except Exception:
                                    pass
                                try:
                                    self.combo.setCurrentIndex(-1)
                                finally:
                                    try:
                                        self.combo.blockSignals(False)
                                    except Exception:
                                        pass
                            self._combo_line_edit.clear()
                            if self._search_edit:
                                self._search_edit.clear()
                        finally:
                            self._suppress_filters = False

                        self.apply_filters()
                        QTimer.singleShot(0, self._restore_combo_line_edit_focus)
                        return True
            except Exception:
                pass
            return super().eventFilter(obj, event)

        if obj is not self.combo:
            return super().eventFilter(obj, event)

        try:
            if event.type() == QEvent.MouseButtonPress:
                # Only treat clicks on the arrow sub-control as 'show all'.
                option = QtWidgets.QStyleOptionComboBox()
                option.initFrom(self.combo)
                option.editable = self.combo.isEditable()
                option.currentText = self.combo.currentText()

                arrow_rect = self.combo.style().subControlRect(
                    QtWidgets.QStyle.CC_ComboBox,
                    option,
                    QtWidgets.QStyle.SC_ComboBoxArrow,
                    self.combo,
                )

                pos = event.pos() if hasattr(event, "pos") else None
                if pos is not None and arrow_rect.contains(pos):
                    # Defer so the current mouse event finishes cleanly.
                    QTimer.singleShot(0, self.show_all)
                    return True
        except Exception:
            # Fall back to default behaviour if anything goes wrong.
            pass

        return super().eventFilter(obj, event)

    def _suppress_popup_focus_steal_for_typing(self) -> None:
        """Prevent the combo popup from taking focus away from the lineEdit.

        When QComboBox.showPopup() is called, Qt may transfer focus to the popup QListView.
        That breaks multi-character typing (2nd keypress goes to the list). For typing-driven
        popups we keep the popup non-focusable and keep focus in the lineEdit.
        """

        if self._popup_focus_suppressed:
            return
        if not self.combo or not qt_is_valid(self.combo):
            return

        try:
            view = self.combo.view()
            viewport = view.viewport() if view else None
        except Exception:
            return

        if not view:
            return

        if view is not None and view is not self._combo_popup_view:
            try:
                view.installEventFilter(self)
                self._combo_popup_event_filter_installed = True
            except Exception:
                pass
        if viewport is not None and viewport is not self._combo_popup_viewport:
            try:
                viewport.installEventFilter(self)
                self._combo_popup_event_filter_installed = True
            except Exception:
                pass

        self._combo_popup_view = view
        self._combo_popup_viewport = viewport

        try:
            self._popup_view_old_focus_policy = view.focusPolicy()
            view.setFocusPolicy(Qt.NoFocus)
        except Exception:
            self._popup_view_old_focus_policy = None

        if viewport:
            try:
                self._popup_viewport_old_focus_policy = viewport.focusPolicy()
                viewport.setFocusPolicy(Qt.NoFocus)
            except Exception:
                self._popup_viewport_old_focus_policy = None

        self._popup_focus_suppressed = True

    def _restore_popup_focus_policy_if_needed(self) -> None:
        if not self._popup_focus_suppressed:
            return

        view = self._combo_popup_view
        viewport = self._combo_popup_viewport

        if view and qt_is_valid(view) and self._popup_view_old_focus_policy is not None:
            try:
                view.setFocusPolicy(self._popup_view_old_focus_policy)
            except Exception:
                pass
        if viewport and qt_is_valid(viewport) and self._popup_viewport_old_focus_policy is not None:
            try:
                viewport.setFocusPolicy(self._popup_viewport_old_focus_policy)
            except Exception:
                pass

        self._popup_focus_suppressed = False
        self._popup_view_old_focus_policy = None
        self._popup_viewport_old_focus_policy = None

    def _restore_combo_line_edit_focus(self) -> None:
        if self._app_about_to_quit or QtWidgets.QApplication.instance() is None:
            return
        if not self.combo or not qt_is_valid(self.combo):
            return
        line_edit = self.combo.lineEdit() if self.combo.isEditable() else None
        if not line_edit or not qt_is_valid(line_edit):
            return

        try:
            cursor_pos = line_edit.cursorPosition()
        except Exception:
            cursor_pos = None

        try:
            line_edit.setFocus(Qt.OtherFocusReason)
            if cursor_pos is not None:
                line_edit.setCursorPosition(cursor_pos)
        except Exception:
            pass

    def apply_filters(self) -> None:
        """Apply current filters and refresh the combo box."""

        if self._app_about_to_quit or QtWidgets.QApplication.instance() is None:
            return

        program_raw = self._program_combo.currentData() if self._program_combo else "all"
        program_filter = program_raw or "all"
        subgroup_filter = self._subgroup_combo.currentData() if self._subgroup_combo else ""
        grant_filter = (self._grant_edit.text().strip() if self._grant_edit else "").lower()
        search_filter = (
            self._search_edit.text().strip() if self._search_edit else ""
        ).lower()

        filtered: List[Dict] = []
        for dataset in self._datasets:
            attr = dataset.get("attributes", {})
            dataset_type = attr.get("datasetType", "")
            grant_number = attr.get("grantNumber", "")
            search_blob = dataset.get("_search_blob", "")
            dataset_group_id = str(dataset.get("_group_id") or "")

            if program_filter != "all" and dataset_type != program_filter:
                continue
            if subgroup_filter and str(subgroup_filter) != dataset_group_id:
                continue
            if grant_filter and grant_filter not in grant_number.lower():
                continue
            if search_filter and search_filter not in search_blob:
                continue
            filtered.append(dataset)

        self._filtered_datasets = filtered
        self._update_combo()
        self._update_count_label()

    def _maybe_show_popup_for_user_input(self) -> None:
        """Open the combo popup when the user is typing, so the filtered list is visible."""

        # Do not show popup immediately; combo repopulation may close it.
        # Instead, record the intent and open it after the combo update completes.
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RDE_TEST_ALLOW_COMBO_POPUP"):
            return
        # Coalesce multiple input signals (textEdited/textChanged) into a single popup.
        self._pending_popup = True

    def _show_pending_popup_if_needed(self) -> None:
        if not self._pending_popup:
            return
        if self._app_about_to_quit or QtWidgets.QApplication.instance() is None:
            self._pending_popup = False
            return
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RDE_TEST_ALLOW_COMBO_POPUP"):
            self._pending_popup = False
            return
        if not self.combo or not qt_is_valid(self.combo):
            self._pending_popup = False
            return

        try:
            if not self.combo.isEnabled() or not self.combo.isVisible():
                self._pending_popup = False
                return

            # If it's already visible, avoid re-opening (re-opening may steal focus).
            try:
                if self.combo.view() and self.combo.view().isVisible():
                    self._pending_popup = False
                    return
            except Exception:
                pass

            # Only pop up when the user is interacting with the combo.
            if self.combo.hasFocus():
                pass
            elif self.combo.lineEdit() and self.combo.lineEdit().hasFocus():
                pass
            else:
                self._pending_popup = False
                return

            self._pending_popup = False
            logger.debug("DatasetFilterFetcher: showPopup (deferred)")

            def _show_and_refocus() -> None:
                if self._app_about_to_quit or QtWidgets.QApplication.instance() is None:
                    return
                if not self.combo or not qt_is_valid(self.combo):
                    return
                # Typing-driven popup: keep input focus in the lineEdit.
                self._typing_popup_active = True
                self._suppress_popup_focus_steal_for_typing()
                self.combo.showPopup()
                # Ensure we re-apply suppression in case the popup view is created lazily.
                self._suppress_popup_focus_steal_for_typing()
                # Ensure refocus happens after showPopup() side-effects.
                QTimer.singleShot(0, self._restore_combo_line_edit_focus)
                QTimer.singleShot(50, self._restore_combo_line_edit_focus)

            QTimer.singleShot(0, _show_and_refocus)
        except Exception:
            self._pending_popup = False

    def show_all(self) -> None:
        """Reset filters and open the combo popup."""

        if self._program_combo:
            self._program_combo.setCurrentIndex(0)
        if self._grant_edit:
            self._grant_edit.clear()
        if self._search_edit:
            self._search_edit.clear()
        self.apply_filters()
        # Explicit "show all" (arrow click) should keep default focus behaviour.
        self._typing_popup_active = False
        self._restore_popup_focus_policy_if_needed()
        if self.combo and (not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("RDE_TEST_ALLOW_COMBO_POPUP")):
            self.combo.showPopup()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_dataset_items(self) -> None:
        if not self.dataset_json_path or not os.path.exists(self.dataset_json_path):
            logger.warning("dataset.json が見つかりません: %s", self.dataset_json_path)
            self._datasets = []
            return

        try:
            with open(self.dataset_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("dataset.json の読み込みに失敗: %s", exc)
            self._datasets = []
            return

        if isinstance(data, dict) and "data" in data:
            items = data["data"]
        elif isinstance(data, list):
            items = data
        else:
            items = []

        datasets: List[Dict] = []
        subgroup_map = self._load_subgroup_map()
        grant_to_subgroup: Dict[str, Dict[str, str]] = {}
        try:
            subgroup_path = self.subgroup_json_path or get_dynamic_file_path("output/rde/data/subGroup.json")
            if subgroup_path and os.path.exists(subgroup_path):
                with open(subgroup_path, "r", encoding="utf-8") as f:
                    subgroup_payload = json.load(f)
                grant_to_subgroup = _build_grant_number_to_subgroup_info(subgroup_payload)
        except Exception:
            grant_to_subgroup = {}
        def _extract_group_id(entry_rel: dict, entry_attr: dict) -> str:
            group_id_local = ""
            rel = entry_rel if isinstance(entry_rel, dict) else {}
            for key in ("group", "subgroup", "subGroup", "sub_group", "groups", "subGroups"):
                try:
                    group_data = (rel.get(key) or {}).get("data") if isinstance(rel.get(key), dict) else None
                    if isinstance(group_data, dict):
                        group_id_local = str(group_data.get("id") or "")
                        if group_id_local:
                            return group_id_local
                    if isinstance(group_data, list) and group_data:
                        for item in group_data:
                            if isinstance(item, dict) and item.get("id"):
                                return str(item.get("id"))
                except Exception:
                    continue
            attr = entry_attr if isinstance(entry_attr, dict) else {}
            for key in ("groupId", "subgroupId", "subGroupId", "sub_group_id"):
                try:
                    value = attr.get(key)
                    if value:
                        return str(value)
                except Exception:
                    continue
            return group_id_local

        for entry in items:
            if not isinstance(entry, dict):
                continue
            attr = entry.get("attributes", {})
            rel = entry.get("relationships", {}) if isinstance(entry.get("relationships"), dict) else {}
            group_id = _extract_group_id(rel, attr)
            grant_number = str(attr.get("grantNumber") or "").strip()
            subgroup_info = None
            if not group_id and grant_number:
                subgroup_info = grant_to_subgroup.get(grant_number)
                if isinstance(subgroup_info, dict):
                    group_id = str(subgroup_info.get("id") or "")
            search_parts = [
                attr.get("name", ""),
                attr.get("grantNumber", ""),
                attr.get("subjectTitle", ""),
                attr.get("description", ""),
            ]
            if group_id and group_id in subgroup_map:
                sg = subgroup_map[group_id]
                search_parts.append(sg.get("name", ""))
                search_parts.append(sg.get("description", ""))
                entry["_subgroup_name"] = sg.get("name", "")
                entry["_subgroup_description"] = sg.get("description", "")
            elif isinstance(subgroup_info, dict):
                search_parts.append(subgroup_info.get("name", ""))
                search_parts.append(subgroup_info.get("description", ""))
                entry["_subgroup_name"] = subgroup_info.get("name", "")
                entry["_subgroup_description"] = subgroup_info.get("description", "")
            search_blob = " ".join(part for part in search_parts if part).lower()
            entry["_search_blob"] = search_blob
            entry["_group_id"] = group_id
            datasets.append(entry)

        self._datasets = datasets

    def _load_subgroup_map(self) -> Dict[str, Dict[str, str]]:
        if self._subgroup_map:
            return self._subgroup_map

        path = self.subgroup_json_path
        if not path:
            path = get_dynamic_file_path("output/rde/data/subGroup.json")
        if not path or not os.path.exists(path):
            self._subgroup_map = {}
            return self._subgroup_map

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            self._subgroup_map = {}
            return self._subgroup_map

        included = []
        if isinstance(payload, dict):
            if isinstance(payload.get("included"), list):
                included = payload.get("included") or []
            elif isinstance(payload.get("data"), list):
                included = payload.get("data") or []
        elif isinstance(payload, list):
            included = payload

        subgroup_map: Dict[str, Dict[str, str]] = {}
        for item in included:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "group":
                continue
            attrs = item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {}
            if attrs.get("groupType") != "TEAM":
                continue
            gid = str(item.get("id") or "")
            if not gid:
                continue
            subgroup_map[gid] = {
                "name": str(attrs.get("name", "") or ""),
                "description": str(attrs.get("description", "") or ""),
                "subjects": attrs.get("subjects", []),
            }

        self._subgroup_map = subgroup_map
        return self._subgroup_map

    def _populate_programs(self) -> None:
        if not self._program_combo:
            return

        type_map = get_dataset_type_display_map()
        self._program_combo.clear()
        self._program_combo.addItem("全て", "all")

        seen = set()
        for dataset in self._datasets:
            dtype = dataset.get("attributes", {}).get("datasetType")
            if dtype and dtype not in seen:
                seen.add(dtype)

        for dtype in sorted(seen):
            label = type_map.get(dtype, dtype)
            self._program_combo.addItem(label, dtype)

    def _populate_subgroups(self) -> None:
        if not self._subgroup_combo:
            return

        self._subgroup_combo.clear()
        self._subgroup_combo.addItem("全て", "")

        subgroup_map = self._load_subgroup_map()
        items: List[tuple[str, str]] = []
        for gid, info in subgroup_map.items():
            name = str(info.get("name") or "")
            subjects = info.get("subjects") if isinstance(info.get("subjects"), list) else []
            grant_count = len(subjects) if subjects else 0
            label = f"{name} ({grant_count}件の課題)" if name else gid
            items.append((label, gid))

        for label, gid in sorted(items, key=lambda x: x[0]):
            self._subgroup_combo.addItem(label, gid)

    def _connect_filter_signals(self) -> None:
        if self._program_combo:
            self._program_combo.currentIndexChanged.connect(lambda _: self.apply_filters())
        if self._subgroup_combo:
            self._subgroup_combo.currentIndexChanged.connect(lambda _: self.apply_filters())
        if self._grant_edit:
            self._grant_edit.textChanged.connect(lambda _: self.apply_filters())
        if self._search_edit:
            self._search_edit.textChanged.connect(self._on_search_text_changed)

    def _connect_combo_signals(self) -> None:
        if self._combo_signal_connected:
            return
        if not self.combo or not qt_is_valid(self.combo):
            return
        line_edit = self.combo.lineEdit() if self.combo.isEditable() else None
        if not line_edit:
            return

        self._combo_line_edit = line_edit

        # Also observe combo-level edit text changes. Some styles / platforms may not reliably
        # emit lineEdit signals, but editTextChanged is provided by QComboBox itself.
        try:
            self.combo.editTextChanged.connect(self._on_combo_text_changed)
        except Exception:
            pass

        # User typing directly into the combo should drive the same text filter.
        # Use both textEdited and textChanged to be robust across IME / paste / platform.
        # NOTE: textChanged は選択変更やプログラム更新でも発火するため、
        # _on_combo_text_input 側で "検索入力が既にある場合は上書きしない" を保証する。
        try:
            line_edit.textEdited.connect(self._on_combo_text_edited)
            line_edit.textChanged.connect(self._on_combo_text_changed)
        except Exception:
            return

        if not self._logged_combo_connected:
            logger.info("DatasetFilterFetcher: combo input signals connected")
            self._logged_combo_connected = True

        logger.debug(
            "DatasetFilterFetcher: combo lineEdit signals connected (editable=%s)",
            bool(self.combo and self.combo.isEditable()),
        )

        self._combo_signal_connected = True

        if not self._combo_event_filter_installed:
            try:
                self.combo.installEventFilter(self)
                self._combo_event_filter_installed = True
            except Exception:
                pass

        if self._clear_on_blank_click and not self._combo_line_edit_event_filter_installed:
            try:
                line_edit.installEventFilter(self)
                self._combo_line_edit_event_filter_installed = True
            except Exception:
                pass

        if not self._combo_popup_event_filter_installed:
            try:
                view = self.combo.view()
                if view:
                    view.installEventFilter(self)
                    viewport = view.viewport() if hasattr(view, "viewport") else None
                    if viewport:
                        viewport.installEventFilter(self)
                    self._combo_popup_view = view
                    self._combo_popup_viewport = viewport
                self._combo_popup_event_filter_installed = True
            except Exception:
                pass

    def _on_combo_text_edited(self, text: str) -> None:
        self._on_combo_text_input(text)

    def _on_combo_text_changed(self, text: str) -> None:
        # textChanged can be emitted for programmatic updates as well; guard with suppress flag.
        if self._suppress_filters:
            return

        # When the user selects an item from the popup, an editable QComboBox updates the
        # lineEdit text to the item's display text and emits textChanged.
        # That display text is not a stable search token (it may contain truncation / labels),
        # and treating it as "typing" will re-filter and can wipe out the selection.
        try:
            if self.combo and qt_is_valid(self.combo):
                index = self.combo.currentIndex()
                if index >= 0 and (self.combo.itemText(index) or "") == (text or ""):
                    self._typing_popup_active = False
                    self._restore_popup_focus_policy_if_needed()
                    return
        except Exception:
            pass

        self._on_combo_text_input(text)

    def _on_combo_text_input(self, text: str) -> None:
        if self._suppress_filters:
            return
        if not self._search_edit:
            return

        # 検索欄が既にユーザー入力で埋まっている場合は、
        # combo 側の入力（選択変更/プログラム更新/typing 等）で検索欄を上書きしない。
        # - widget: combo入力で検索する場合は、検索欄が空の状態で入力される想定
        # - unit: 検索欄入力後、combo lineEdit の更新で検索が壊れないことが要件
        current_search = self._search_edit.text() or ""
        normalized = text or ""

        # Only protect the search box when it has been set directly (i.e., via the search box
        # itself or an external programmatic setText). When the search box is being driven by
        # combo typing (we set it under _suppress_filters), allow continuous updates.
        if self._search_edit_authoritative and current_search and current_search != normalized:
            # UIの一貫性のため、combo側の表示を検索欄へ戻す（フィルタも維持）。
            if self.combo and self.combo.lineEdit():
                self._suppress_filters = True
                try:
                    self.combo.lineEdit().setText(current_search)
                finally:
                    self._suppress_filters = False

            self.apply_filters()
            return

        if not self._logged_first_combo_input:
            logger.info("DatasetFilterFetcher: combo input detected")
            self._logged_first_combo_input = True

        logger.debug("DatasetFilterFetcher: combo text input: %r", text)

        # normalized is the authoritative filter text when search_edit is empty.
        if self._search_edit.text() == normalized:
            # Still re-apply filters so the combo list follows the current text.
            self.apply_filters()
            self._maybe_show_popup_for_user_input()
            return

        self._suppress_filters = True
        try:
            self._search_edit.setText(normalized)
        finally:
            self._suppress_filters = False

        self.apply_filters()
        self._maybe_show_popup_for_user_input()

    def _on_search_text_changed(self, text: str) -> None:
        if self._suppress_filters:
            return

        # The search box is now the authoritative input source until it's cleared.
        self._search_edit_authoritative = True

        logger.debug("DatasetFilterFetcher: search text changed: %r", text)
        if self.combo and self.combo.lineEdit():
            # Avoid triggering combo textChanged handlers during sync.
            self._suppress_filters = True
            try:
                self.combo.lineEdit().setText(text)
            finally:
                self._suppress_filters = False
        self.apply_filters()
        self._maybe_show_popup_for_user_input()

    def _update_combo(self) -> None:
        if not self.combo or not qt_is_valid(self.combo):
            return

        # たくさんのデータセットがあると、同期でaddItem+Completer構築がUIを長時間ブロックする。
        # 初回の「操作可能」までを短縮するため、一定件数を超える場合は分割投入する。
        async_threshold = 500
        chunk_size = 200

        overall = len(self._datasets)
        large_overall = overall > async_threshold

        # Any combo refresh should invalidate previously scheduled async append chunks.
        # Otherwise an in-flight async population may continue to append items after a later
        # (sync) update, causing oscillation/duplication and unstable results.
        self._populate_generation += 1
        generation = self._populate_generation

        selected_id = self._current_selection_id()
        line_edit = self.combo.lineEdit() if self.combo.isEditable() else None
        typed_text = line_edit.text() if line_edit else ""

        self._suppress_filters = True
        async_started = False
        try:
            if not self.combo or not qt_is_valid(self.combo):
                return
            self.combo.blockSignals(True)

            if line_edit:
                try:
                    line_edit.blockSignals(True)
                except Exception:
                    pass

            self.combo.clear()

            # 大量件数は非同期更新（イベントループに制御を返す）
            if len(self._filtered_datasets) > async_threshold:
                async_started = True

                # まずプレースホルダを表示
                placeholder = "-- 読み込み中... --"
                self.combo.addItem(placeholder, None)
                self.combo.setCurrentIndex(-1)

                if line_edit and typed_text:
                    line_edit.setText(typed_text)

                if self.combo.lineEdit():
                    total = len(self._filtered_datasets)
                    overall = len(self._datasets)
                    self.combo.lineEdit().setPlaceholderText(f"データセットを検索・選択 ({total}/{overall}件)")

                # IMPORTANT:
                # Do not leave the combo/lineEdit signals blocked while we asynchronously append items.
                # Otherwise user typing won't emit signals (and filtering will appear broken) on large datasets.
                self.combo.blockSignals(False)
                if line_edit:
                    try:
                        line_edit.blockSignals(False)
                    except Exception:
                        pass
                self._suppress_filters = False

                def _append_chunk(start: int) -> None:
                    if self._app_about_to_quit or QtWidgets.QApplication.instance() is None:
                        return
                    if generation != self._populate_generation:
                        return
                    if not self.combo or not qt_is_valid(self.combo):
                        return

                    # Avoid emitting selection/index signals while mutating the combo.
                    # (User typing signals should still work between chunks.)
                    self._suppress_filters = True
                    try:
                        self.combo.blockSignals(True)

                        # 初回chunkでプレースホルダを消す
                        if start == 0:
                            self.combo.clear()

                        end = min(start + chunk_size, len(self._filtered_datasets))
                        for dataset in self._filtered_datasets[start:end]:
                            text = self._format_display_text(dataset)
                            self.combo.addItem(text, dataset)

                        if end < len(self._filtered_datasets):
                            QTimer.singleShot(0, lambda: _append_chunk(end))
                            return

                        # 追加完了
                        if not self._filtered_datasets:
                            empty_placeholder = "-- 該当するデータセットがありません --"
                            self.combo.addItem(empty_placeholder, None)

                        # Completerは大量件数だと重いので付与しない（入力はフィルタ欄で十分）
                        try:
                            self.combo.setCompleter(None)
                        except Exception:
                            pass

                        if selected_id:
                            self._restore_selection(selected_id)
                        else:
                            self.combo.setCurrentIndex(-1)

                        if line_edit and self.combo.currentIndex() == -1 and typed_text:
                            line_edit.setText(typed_text)
                    finally:
                        if self.combo and qt_is_valid(self.combo):
                            self.combo.blockSignals(False)
                        self._suppress_filters = False

                    self._show_pending_popup_if_needed()

                # 非同期開始
                QTimer.singleShot(0, lambda: _append_chunk(0))
                return

            display_list: List[str] = []
            for dataset in self._filtered_datasets:
                text = self._format_display_text(dataset)
                display_list.append(text)
                self.combo.addItem(text, dataset)

            if not self._filtered_datasets:
                placeholder = "-- 該当するデータセットがありません --"
                # Guard against accidental duplicates.
                if self.combo.count() == 0 or self.combo.itemText(self.combo.count() - 1) != placeholder:
                    self.combo.addItem(placeholder, None)
                display_list.append(placeholder)

            # If there are many datasets overall, avoid installing a QCompleter.
            # Completer can open its own popup on typing, which is confusing alongside combo.showPopup().
            if large_overall:
                try:
                    self.combo.setCompleter(None)
                except Exception:
                    pass
            else:
                completer = QCompleter(display_list, self.combo)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                popup_view = completer.popup()
                popup_view.setMinimumHeight(240)
                popup_view.setMaximumHeight(240)
                self.combo.setCompleter(completer)

            if selected_id:
                self._restore_selection(selected_id)
            else:
                self.combo.setCurrentIndex(-1)

            if self.combo.lineEdit():
                total = len(self._filtered_datasets)
                overall = len(self._datasets)
                placeholder = f"データセットを検索・選択 ({total}/{overall}件)"
                self.combo.lineEdit().setPlaceholderText(placeholder)

            if line_edit and self.combo.currentIndex() == -1 and typed_text:
                line_edit.setText(typed_text)
        finally:
            if not async_started:
                if self.combo and qt_is_valid(self.combo):
                    self.combo.blockSignals(False)
                if line_edit:
                    try:
                        line_edit.blockSignals(False)
                    except Exception:
                        pass
                self._suppress_filters = False
                self._show_pending_popup_if_needed()

    def _current_selection_id(self) -> Optional[str]:
        if not self.combo:
            return None
        current_data = self.combo.currentData()
        if isinstance(current_data, dict):
            return current_data.get("id")
        return None

    def _restore_selection(self, dataset_id: str) -> None:
        if not self.combo or not dataset_id:
            return
        for index in range(self.combo.count()):
            data = self.combo.itemData(index)
            if isinstance(data, dict) and data.get("id") == dataset_id:
                self.combo.setCurrentIndex(index)
                return
        # If selection no longer exists, keep combo cleared
        self.combo.setCurrentIndex(-1)

    def _format_display_text(self, dataset: Dict) -> str:
        attr = dataset.get("attributes", {})
        grant = attr.get("grantNumber", "")
        subject = attr.get("subjectTitle", "")
        name = attr.get("name", "名前なし")
        dtype = attr.get("datasetType", "")
        type_map = get_dataset_type_display_map()
        type_label = type_map.get(dtype, dtype)

        parts: List[str] = []
        if grant:
            parts.append(grant)
        if subject:
            truncated_subject = subject[:30] + ("…" if len(subject) > 30 else "")
            parts.append(truncated_subject)
        truncated_name = name[:40] + ("…" if len(name) > 40 else "")
        parts.append(truncated_name)
        if type_label:
            parts.append(f"[{type_label}]")
        return " ".join(parts)

    def _update_count_label(self) -> None:
        if not self._count_label:
            return
        filtered = len(self._filtered_datasets)
        total = len(self._datasets)
        self._count_label.setText(f"表示中: {filtered}/{total} 件")
