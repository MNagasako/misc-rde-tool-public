from __future__ import annotations

import json
import os
from typing import Any

from config.common import get_dynamic_file_path

try:
    from qt_compat.core import QTimer
    from qt_compat.widgets import QMessageBox, QWidget
except Exception:  # pragma: no cover
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox, QWidget


def _resolve_group_id(dataset_id: str, raw_dataset: Any | None) -> str:
    # 1) raw_dataset(listing) の relationships.group.data.id を優先
    if isinstance(raw_dataset, dict):
        try:
            rel = raw_dataset.get("relationships") or {}
            gid = (((rel.get("group") or {}).get("data") or {}).get("id") or "")
            gid = str(gid or "").strip()
            if gid:
                return gid
        except Exception:
            pass

    # 2) dataset detail JSON から取得
    dsid = str(dataset_id or "").strip()
    if not dsid:
        return ""

    dataset_path = get_dynamic_file_path(f"output/rde/data/datasets/{dsid}.json")
    if not dataset_path or not os.path.exists(dataset_path):
        return ""

    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        group_data = (
            (((payload.get("data") or {}).get("relationships") or {}).get("group") or {}).get("data") or {}
        )
        if isinstance(group_data, dict):
            return str(group_data.get("id") or "").strip()
    except Exception:
        return ""

    return ""


def _get_ui_controller_from_launch_manager():
    try:
        from classes.utils.dataset_launch_manager import DatasetLaunchManager

        manager = DatasetLaunchManager.instance()
        return getattr(manager, "_ui_controller", None)
    except Exception:
        return None


def launch_to_subgroup_edit(
    *,
    owner_widget: QWidget,
    dataset_id: str,
    raw_dataset: Any | None = None,
    source_name: str = "",
) -> bool:
    """選択中データセットのサブグループを「サブグループ閲覧・修正」で開く。"""

    group_id = _resolve_group_id(dataset_id, raw_dataset)
    if not group_id:
        try:
            QMessageBox.warning(owner_widget, "サブグループ未解決", "選択中データセットのサブグループIDを取得できませんでした。")
        except Exception:
            pass
        return False

    ui_controller = _get_ui_controller_from_launch_manager()
    if ui_controller is None:
        try:
            QMessageBox.warning(owner_widget, "画面遷移失敗", "UIコントローラーを取得できませんでした。")
        except Exception:
            pass
        return False

    try:
        ui_controller.switch_mode("subgroup_create")
    except Exception:
        try:
            QMessageBox.warning(owner_widget, "画面遷移失敗", "サブグループ画面へ遷移できませんでした。")
        except Exception:
            pass
        return False

    def _try_focus() -> None:
        try:
            host = getattr(ui_controller, "parent", None)
            layout = getattr(host, "menu_area_layout", None)
            root = None
            if layout is not None and hasattr(layout, "count") and layout.count() > 0:
                item = layout.itemAt(layout.count() - 1)
                root = item.widget() if item is not None else None

            if root is not None and hasattr(root, "focus_edit_subgroup_by_id"):
                ok = bool(root.focus_edit_subgroup_by_id(group_id))
                if not ok:
                    QMessageBox.information(
                        owner_widget,
                        "サブグループ選択",
                        "サブグループ画面へ遷移しましたが、指定IDの自動選択に失敗しました。\n"
                        "閲覧・修正タブで手動選択してください。",
                    )
        except Exception:
            # best-effort
            pass

    QTimer.singleShot(0, _try_focus)
    return True
