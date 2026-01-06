"""
グループ選択ダイアログ

複数のプログラムグループから1つを選択するダイアログ
基本情報取得時に、ユーザーが属する複数のプログラムから
取得対象を選択可能にする
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QRadioButton,
    QPushButton, QLabel, QScrollArea, QWidget, QButtonGroup
)
from qt_compat import QtCore
from qt_compat.core import QCoreApplication, QEventLoop, QThread, QTimer

from config.common import GROUP_SELECTION_HISTORY_FILE
from classes.theme import ThemeManager, ThemeKey, get_color

logger = logging.getLogger(__name__)


_SELECTION_HISTORY_PATH = Path(GROUP_SELECTION_HISTORY_FILE)


def _exec_dialog_on_ui_thread(groups, parent, context_name, force_dialog, default_group_id, remember_context):
    """Run the selection dialog on the UI thread.

    Note:
        Qt forbids calling QObject.moveToThread() from a thread other than the object's
        current thread. In practice, module import timing can create helper QObjects on
        non-UI threads, so we avoid moveToThread entirely and instead schedule execution
        onto QCoreApplication's thread.
    """
    app = QCoreApplication.instance()
    if not app:
        return show_group_selection_dialog(
            groups,
            parent,
            context_name,
            force_dialog=force_dialog,
            default_group_id=default_group_id,
            remember_context=remember_context,
        )

    # Already on UI thread -> run directly
    if QThread.currentThread() == app.thread():
        return show_group_selection_dialog(
            groups,
            parent,
            context_name,
            force_dialog=force_dialog,
            default_group_id=default_group_id,
            remember_context=remember_context,
        )

    # Called from worker thread -> queue to UI thread and block until completion.
    # NOTE: PySide6 QMetaObject.invokeMethod does NOT accept Python callables, so we
    # use a QObject + Signal/Slot to guarantee UI-thread execution.
    result_holder: Dict[str, Optional[Dict[str, str]]] = {"result": None}
    loop = QEventLoop()

    class _WorkerReceiver(QtCore.QObject):
        @QtCore.Slot(object)
        def on_finished(self, res):
            result_holder["result"] = res
            # This slot runs on the worker thread (QueuedConnection), so quitting
            # the worker-thread event loop is safe.
            try:
                loop.quit()
            except Exception:
                pass

    class _DialogInvoker(QtCore.QObject):
        requested = QtCore.Signal(object, object, object, object, object, object)
        finished = QtCore.Signal(object)

        def __init__(self):
            super().__init__()
            self.requested.connect(self._run, QtCore.Qt.ConnectionType.QueuedConnection)
            self.finished.connect(self.deleteLater)

        @QtCore.Slot(object, object, object, object, object, object)
        def _run(self, _groups, _parent, _context_name, _force_dialog, _default_group_id, _remember_context):
            try:
                res = show_group_selection_dialog(
                    _groups,
                    _parent,
                    _context_name,
                    force_dialog=bool(_force_dialog),
                    default_group_id=_default_group_id,
                    remember_context=_remember_context,
                )
            except Exception:
                res = None
            self.finished.emit(res)

    invoker = _DialogInvoker()
    # Create in current (worker) thread, then move to UI thread.
    # IMPORTANT: After moving, ensure the object is Qt-owned (parented on UI thread),
    # otherwise Python GC may delete the underlying QObject from the worker thread.
    invoker.moveToThread(app.thread())
    try:
        QTimer.singleShot(0, app, lambda inv=invoker: inv.setParent(app))
    except Exception:
        # If parenting fails, we still proceed; worst case is additional GC pressure.
        pass

    worker_receiver = _WorkerReceiver()
    invoker.finished.connect(worker_receiver.on_finished, QtCore.Qt.ConnectionType.QueuedConnection)
    invoker.requested.emit(groups, parent, context_name, force_dialog, default_group_id, remember_context)
    loop.exec()
    return result_holder.get("result")


def _load_selection_history() -> Dict[str, Dict[str, str]]:
    if not _SELECTION_HISTORY_PATH.exists():
        return {}
    try:
        with _SELECTION_HISTORY_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.debug("グループ選択履歴の読み込みに失敗: %s", exc)
    return {}


def _save_selection_history(data: Dict[str, Dict[str, str]]):
    try:
        _SELECTION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _SELECTION_HISTORY_PATH.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("グループ選択履歴の保存に失敗: %s", exc)


def remember_group_selection(context_key: Optional[str], group_id: str, group_name: str = ""):
    if not context_key or not group_id:
        return
    history = _load_selection_history()
    history[context_key] = {
        "id": group_id,
        "name": group_name,
        "updatedAt": datetime.utcnow().isoformat(timespec="seconds")
    }
    _save_selection_history(history)


def get_saved_group_selection(context_key: Optional[str]) -> Optional[Dict[str, str]]:
    if not context_key:
        return None
    record = _load_selection_history().get(context_key)
    if isinstance(record, dict) and record.get("id"):
        return record
    if isinstance(record, str):
        return {"id": record, "name": ""}
    return None


class GroupSelectionDialog(QDialog):
    """
    グループ選択ダイアログ
    
    self.json の included 配列から複数のグループを表示し、
    ユーザーに選択させる
    """
    
    def __init__(self, groups: List[Dict], parent=None, default_group_id: Optional[str] = None):
        """
        初期化
        
        Args:
            groups: グループ情報のリスト（self.json の included 配列から抽出）
            parent: 親ウィジェット
            default_group_id: デフォルト選択するグループID
        """
        super().__init__(parent)
        self.groups = groups
        self.selected_group_id: Optional[str] = None
        self.selected_group_name: Optional[str] = None
        self.default_group_id = default_group_id
        self._info_label: Optional[QLabel] = None
        self._scroll_area: Optional[QScrollArea] = None
        self._row_entries: List[Dict[str, object]] = []
        self._ok_button: Optional[QPushButton] = None
        self._cancel_button: Optional[QPushButton] = None
        self._theme_manager = ThemeManager.instance()
        
        # デフォルト選択の決定
        if groups:
            provisional_id = default_group_id or groups[0].get("id")
            if provisional_id:
                for group in groups:
                    if group.get("id") == provisional_id:
                        self.selected_group_id = provisional_id
                        self.selected_group_name = group.get("attributes", {}).get("name", "")
                        break
            if not self.selected_group_id:
                self.selected_group_id = groups[0].get("id")
                self.selected_group_name = groups[0].get("attributes", {}).get("name", "")
        
        self.setup_ui()
        self._theme_manager.theme_changed.connect(self._apply_theme)
        self._apply_theme(self._theme_manager.get_mode())
        
        logger.debug(f"グループ選択ダイアログ初期化: {len(groups)}件のグループ")
    
    def setup_ui(self):
        """UI構築"""
        self.setWindowTitle("プログラム選択")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self._row_entries = []
        
        layout = QVBoxLayout()
        
        # 説明ラベル
        if len(self.groups) == 1:
            info_text = "取得対象のプログラムを確認してください。"
        else:
            info_text = (
                f"複数のプログラム（{len(self.groups)}件）に属しています。\n"
                "基本情報を取得する対象プログラムを選択してください。"
            )
        
        self._info_label = QLabel(info_text)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)
        
        # スクロールエリア
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        
        # グループリスト用コンテナ
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(4)
        
        # ラジオボタングループ
        self.button_group = QButtonGroup(self)
        
        # 各グループのラジオボタン作成
        for i, group in enumerate(self.groups):
            group_id = group.get("id", "")
            group_attrs = group.get("attributes", {})
            group_name = group_attrs.get("name", "名称不明")
            group_type = group_attrs.get("groupType", "")
            description = group_attrs.get("description", "")
            
            # ラジオボタン
            radio = QRadioButton()
            radio.setProperty("group_id", group_id)
            radio.setProperty("group_name", group_name)
            
            # 既定選択状態
            if group_id and group_id == self.selected_group_id:
                radio.setChecked(True)
            
            # ラジオボタンクリック時のイベント
            radio.toggled.connect(lambda checked, gid=group_id, gname=group_name: 
                                self._on_group_selected(checked, gid, gname))
            
            self.button_group.addButton(radio, i)
            
            # 1行表示のシンプルな行レイアウト
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(12)

            name_label = QLabel(group_name)
            name_label.setWordWrap(False)
            name_label.setMinimumHeight(20)
            name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)

            row_layout.addWidget(radio, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(name_label, 1)
            row_layout.addStretch()
            
            # 背景色付きコンテナ
            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            row_widget.setProperty("groupRow", True)
            
            tooltip_lines = []
            if group_id:
                tooltip_lines.append(f"ID: {group_id}")
            if group_type:
                tooltip_lines.append(f"Type: {group_type}")
            if description:
                desc_text = description.strip()
                if desc_text:
                    if tooltip_lines:
                        tooltip_lines.append("")
                    tooltip_lines.append(desc_text)
            tooltip_text = "\n".join([line for line in tooltip_lines if line]) or group_name
            row_widget.setToolTip(tooltip_text)
            name_label.setToolTip(tooltip_text)
            radio.setToolTip(tooltip_text)
            container_layout.addWidget(row_widget)
            
            self._row_entries.append({
                "widget": row_widget,
                "name_label": name_label,
                "tooltip": tooltip_text,
                "radio": radio,
            })
        
        container_layout.addStretch()
        self._scroll_area.setWidget(container)
        layout.addWidget(self._scroll_area, 1)
        
        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self._ok_button = QPushButton("OK")
        self._ok_button.setDefault(True)
        self._ok_button.clicked.connect(self.accept)
        
        self._cancel_button = QPushButton("キャンセル")
        self._cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self._ok_button)
        button_layout.addWidget(self._cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _apply_theme(self, *_):
        """テーマ変更時に背景・文字色を再適用"""
        info_bg = get_color(ThemeKey.PANEL_INFO_BACKGROUND)
        info_text = get_color(ThemeKey.PANEL_INFO_TEXT)
        info_border = get_color(ThemeKey.PANEL_INFO_BORDER)
        panel_bg = get_color(ThemeKey.TABLE_ROW_BACKGROUND)
        panel_border = get_color(ThemeKey.TABLE_BORDER)
        hover_bg = get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)
        primary_text = get_color(ThemeKey.TEXT_PRIMARY)
        
        if self._info_label:
            self._info_label.setStyleSheet(
                f"padding: 10px; border-radius: 5px; border: 1px solid {info_border}; "
                f"background-color: {info_bg}; color: {info_text};"
            )
        
        if self._scroll_area:
            self._scroll_area.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {panel_border}; background-color: {panel_bg}; }}"
                f" QScrollArea > QWidget > QWidget {{ background-color: {panel_bg}; }}"
            )
        
        for entry in self._row_entries:
            row_widget: QWidget = entry["widget"]  # type: ignore[assignment]
            name_label: QLabel = entry["name_label"]  # type: ignore[assignment]
            
            row_widget.setStyleSheet(
                f"QWidget[groupRow=\"true\"] {{ background-color: {panel_bg}; border: 1px solid {panel_border}; "
                f"border-radius: 4px; }}"
                f" QWidget[groupRow=\"true\"]:hover {{ background-color: {hover_bg}; }}"
            )
            name_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {primary_text};")
        
        if self._ok_button:
            self._ok_button.setStyleSheet(
                f"QPushButton {{ background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)}; padding: 8px 20px; border-radius: 4px; "
                f"border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)}; font-weight: bold; }}"
                f" QPushButton:hover {{ background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)}; }}"
            )
        if self._cancel_button:
            self._cancel_button.setStyleSheet(
                f"QPushButton {{ background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)}; padding: 8px 20px; border-radius: 4px; "
                f"border: 1px solid {get_color(ThemeKey.BUTTON_DANGER_BORDER)}; }}"
                f" QPushButton:hover {{ background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)}; }}"
            )
    
    def _on_group_selected(self, checked: bool, group_id: str, group_name: str):
        """
        グループ選択時のイベントハンドラ
        
        Args:
            checked: ラジオボタンがチェックされたか
            group_id: グループID
            group_name: グループ名
        """
        if checked:
            self.selected_group_id = group_id
            self.selected_group_name = group_name
            logger.debug(f"グループ選択: {group_name} ({group_id[:20]}...)")
    
    def get_selected_group(self) -> Optional[Dict[str, str]]:
        """
        選択されたグループ情報を取得
        
        Returns:
            {"id": グループID, "name": グループ名} または None
        """
        if self.selected_group_id:
            return {
                "id": self.selected_group_id,
                "name": self.selected_group_name or ""
            }
        return None


def show_group_selection_dialog(
    groups: List[Dict],
    parent=None,
    context_name: str = "グループ",
    force_dialog: bool = True,
    default_group_id: Optional[str] = None,
    remember_context: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """
    グループ選択ダイアログを表示（便利関数）
    
    Args:
        groups: グループ情報のリスト
        parent: 親ウィジェット
        context_name: コンテキスト名（ログ出力用）
        force_dialog: True の場合、単一グループでもダイアログを表示
    
    Returns:
        選択されたグループ情報 {"id": ..., "name": ...} または None（キャンセル時）
    """
    if not groups:
        logger.warning("グループが0件のため、ダイアログを表示できません")
        return None
    
    # 単一グループかつ force_dialog=False の場合は自動選択
    if len(groups) == 1 and not force_dialog:
        selected = {
            "id": groups[0].get("id", ""),
            "name": groups[0].get("attributes", {}).get("name", "名称不明")
        }
        logger.info(f"[v2.1.17] {context_name}自動選択: {selected['name']} ({selected['id'][:20]}...)")
        remember_group_selection(remember_context, selected["id"], selected["name"])
        return selected
    
    dialog = GroupSelectionDialog(groups, parent, default_group_id=default_group_id)
    result = dialog.exec()
    
    if result == QDialog.DialogCode.Accepted:
        selected = dialog.get_selected_group()
        if selected:
            logger.info(f"{context_name}選択完了: {selected['name']} ({selected['id'][:20]}...)")
            remember_group_selection(remember_context, selected["id"], selected["name"])
        return selected
    else:
        logger.info(f"{context_name}選択がキャンセルされました")
        return None


def show_group_selection_if_needed(
    groups: List[Dict],
    parent=None,
    context_name: str = "グループ",
    force_dialog: bool = False,
    preferred_group_id: Optional[str] = None,
    remember_context: Optional[str] = None,
    auto_select_saved: bool = True
) -> Optional[Dict[str, str]]:
    """
    グループ選択ダイアログを必要に応じて表示
    
    - 0件: Noneを返す
    - 1件: 自動選択してログ出力（ダイアログなし）またはforce_dialog=Trueならダイアログ表示
    - 2件以上: ダイアログを表示
    
    Args:
        groups: グループ情報のリスト
        parent: 親ウィジェット
        context_name: コンテキスト名（ログ出力用）
        force_dialog: True の場合、単一グループでもダイアログを表示
    
    Returns:
        選択されたグループ情報 {"id": ..., "name": ...} または None
    """
    if not groups:
        logger.warning(f"{context_name}が0件のため、選択できません")
        return None
    
    saved_record = get_saved_group_selection(remember_context) if auto_select_saved else None
    default_group_id = preferred_group_id or (saved_record.get("id") if saved_record else None)

    if len(groups) == 1 and not force_dialog:
        group = groups[0]
        group_id = group.get("id", "")
        group_name = group.get("attributes", {}).get("name", "名称不明")
        logger.info(f"{context_name}が1件のみのため、自動選択しました: {group_name} ({group_id[:20]}...)")
        remember_group_selection(remember_context, group_id, group_name)
        return {"id": group_id, "name": group_name}
    
    if not force_dialog and default_group_id:
        for group in groups:
            if group.get("id") == default_group_id:
                group_name = group.get("attributes", {}).get("name", "名称不明")
                logger.info(
                    f"{context_name}: 以前の選択 {group_name} ({default_group_id[:20]}...) を再利用します"
                )
                remember_group_selection(remember_context, default_group_id, group_name)
                return {"id": default_group_id, "name": group_name}
    
    logger.info(f"{context_name}が{len(groups)}件あります。選択ダイアログを表示します。")

    return _exec_dialog_on_ui_thread(
        groups,
        parent,
        context_name,
        force_dialog=True,
        default_group_id=default_group_id,
        remember_context=remember_context,
    )
