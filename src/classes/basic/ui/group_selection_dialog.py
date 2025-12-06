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

logger = logging.getLogger(__name__)


_SELECTION_HISTORY_PATH = Path(GROUP_SELECTION_HISTORY_FILE)


class _DialogInvoker(QtCore.QObject):
    """Execute the selection dialog on the UI thread to avoid cross-thread parenting warnings."""

    def __init__(self):
        super().__init__()
        self._loop: Optional[QEventLoop] = None
        self._result: Optional[Dict[str, str]] = None

    @QtCore.Slot(list, object, str, bool, object, object)
    def _run_dialog(self, groups, parent, context_name, force_dialog, default_group_id, remember_context):
        self._result = show_group_selection_dialog(
            groups,
            parent,
            context_name,
            force_dialog=force_dialog,
            default_group_id=default_group_id,
            remember_context=remember_context,
        )
        if self._loop and self._loop.isRunning():
            self._loop.quit()
        return self._result

    def exec_dialog(self, groups, parent, context_name, force_dialog, default_group_id, remember_context):
        app = QCoreApplication.instance()
        if app and self.thread() != app.thread():
            # Ensure this invoker lives on the UI thread so queued work executes there
            self.moveToThread(app.thread())

        # If called from a worker thread, queue execution to the UI thread and block until completion
        if app and QThread.currentThread() != app.thread():
            self._result = None
            self._loop = QEventLoop()

            def _deferred_run():
                self._run_dialog(groups, parent, context_name, force_dialog, default_group_id, remember_context)
                if self._loop.isRunning():
                    self._loop.quit()

            # Use the QObject-aware overload so the callback runs on the UI thread
            QTimer.singleShot(0, self, _deferred_run)
            self._loop.exec()
            return self._result

        return self._run_dialog(groups, parent, context_name, force_dialog, default_group_id, remember_context)


_dialog_invoker = _DialogInvoker()


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
        
        logger.debug(f"グループ選択ダイアログ初期化: {len(groups)}件のグループ")
    
    def setup_ui(self):
        """UI構築"""
        self.setWindowTitle("プログラム選択")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout()
        
        # 説明ラベル
        if len(self.groups) == 1:
            info_text = "取得対象のプログラムを確認してください。"
        else:
            info_text = (
                f"複数のプログラム（{len(self.groups)}件）に属しています。\n"
                "基本情報を取得する対象プログラムを選択してください。"
            )
        
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("padding: 10px; background-color: #e7f3ff; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: 1px solid #ccc; }")
        
        # グループリスト用コンテナ
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(10)
        
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
            
            # グループ情報表示レイアウト
            group_layout = QVBoxLayout()
            group_layout.setSpacing(5)
            
            # グループ名（太字・大きめ）
            name_label = QLabel(f"<b>{group_name}</b>")
            name_label.setWordWrap(True)
            name_label.setStyleSheet("font-size: 14px;")
            
            # グループID・タイプ（小さめ・グレー）
            id_text = f"<span style='color: #666; font-size: 11px;'>ID: {group_id[:20]}...</span>"
            if group_type:
                id_text += f" <span style='color: #666; font-size: 11px;'>| Type: {group_type}</span>"
            id_label = QLabel(id_text)
            id_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            
            # 説明文（ある場合のみ）
            if description:
                desc_label = QLabel(description)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet("color: #555; font-size: 12px; margin-top: 5px;")
            
            group_layout.addWidget(name_label)
            group_layout.addWidget(id_label)
            if description:
                group_layout.addWidget(desc_label)
            
            # ラジオボタンと情報を横並び
            row_layout = QHBoxLayout()
            row_layout.addWidget(radio)
            row_layout.addLayout(group_layout, 1)
            
            # 背景色付きコンテナ
            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            row_widget.setStyleSheet("""
                QWidget {
                    background-color: #f9f9f9;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    padding: 10px;
                }
                QWidget:hover {
                    background-color: #f0f0f0;
                }
            """)
            
            container_layout.addWidget(row_widget)
        
        container_layout.addStretch()
        scroll_area.setWidget(container)
        layout.addWidget(scroll_area, 1)
        
        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        ok_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
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

    return _dialog_invoker.exec_dialog(
        groups,
        parent,
        context_name,
        force_dialog=True,
        default_group_id=default_group_id,
        remember_context=remember_context,
    )
