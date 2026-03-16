"""
一括登録UI実装

ファイルセット管理、データツリー表示、登録設定UIを提供
"""

import os
import json
import logging
import time
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color, get_qcolor
from classes.data_entry.util.template_format_validator import TemplateFormatValidator
from config.common import get_dynamic_file_path
from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload

# ロガー設定
logger = logging.getLogger(__name__)

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QScrollArea, QSplitter, QTabWidget, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QMenu, QAction, QApplication, QFrame, QSizePolicy,
    QInputDialog, QRadioButton, QButtonGroup
)
from qt_compat.core import Qt, Signal, QTimer, QThread
from qt_compat.gui import QFont, QIcon, QPixmap, QPainter, QBrush

from classes.data_entry.ui.toggle_section_widget import ToggleSectionWidget


def _centered_question(parent, title: str, text: str, buttons, default_button=None):
    """QMessageBox.question 相当を「親ウィンドウ中央」に表示する。"""

    try:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        if default_button is not None:
            try:
                box.setDefaultButton(default_button)
            except Exception:
                pass

        try:
            from ..core.data_register_logic import _center_on_parent

            anchor = None
            try:
                anchor = parent.window() if parent is not None else None
            except Exception:
                anchor = None
            _center_on_parent(box, anchor)
        except Exception:
            pass

        return box.exec()
    except Exception:
        try:
            # フォールバック
            if default_button is not None:
                return QMessageBox.question(parent, title, text, buttons, default_button)
            return QMessageBox.question(parent, title, text, buttons)
        except Exception:
            return QMessageBox.No


def _theme_brush(key: ThemeKey) -> QBrush:
    return QBrush(get_qcolor(key))

from ..core.file_set_manager import (
    FileSetManager, FileSet, FileItem, FileType, PathOrganizeMethod, FileItemType
)
from ..core.batch_register_logic import BatchRegisterLogic, BatchRegisterResult
from ..core.temp_folder_manager import TempFolderManager
from ..util.data_entry_filter_util import get_datasets_for_data_entry, get_filtered_datasets
from classes.data_entry.conf.ui_constants import (
    get_batch_register_style,
    get_file_tree_style,
    get_fileset_table_style,
    TAB_HEIGHT_RATIO,
    TAB_MIN_WIDTH,
)


class FileTreeWidget(QTreeWidget):
    """ファイルツリー表示ウィジェット"""
    
    # シグナル定義（PySide6: list→objectに変更）
    items_selected = Signal(object)  # 選択されたアイテム
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_items = {}  # id(QTreeWidgetItem) -> FileItem のマッピング
        self.setup_ui()
    
    def setup_ui(self):
        """UIセットアップ"""
        self.setHeaderLabels(["名前", "タイプ", "種類", "拡張子", "サイズ", "含む", "ZIP"])
        self.setSelectionMode(QTreeWidget.ExtendedSelection)  # 複数選択可能
        self.setAlternatingRowColors(True)
        # ファイルツリースタイル適用（動的）
        self.setStyleSheet(get_file_tree_style())
        
        # ヘッダー設定
        header = self.header()
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(80)   # デフォルト列幅を設定
        header.setMinimumSectionSize(40)   # 最小列幅を設定
        
        # カラム幅設定とリサイズ設定
        header.setSectionResizeMode(0, QHeaderView.Interactive)    # 名前列（リサイズ可能）
        header.setSectionResizeMode(1, QHeaderView.Fixed)          # タイプ列（固定）
        header.setSectionResizeMode(2, QHeaderView.Interactive)    # 種類列（リサイズ可能）
        header.setSectionResizeMode(3, QHeaderView.Fixed)          # 拡張子列（固定）
        header.setSectionResizeMode(4, QHeaderView.Fixed)          # サイズ列（固定）
        header.setSectionResizeMode(5, QHeaderView.Fixed)          # 含む列（固定）
        header.setSectionResizeMode(6, QHeaderView.Fixed)          # ZIP列（固定）
        
        # 初期幅設定
        self.setColumnWidth(0, 220)  # 名前（初期値を大きく）
        self.setColumnWidth(1, 60)   # タイプ（狭く）
        self.setColumnWidth(2, 120)  # 種類（ラジオボタン用に幅を広げる）
        self.setColumnWidth(3, 60)   # 拡張子（狭く）
        self.setColumnWidth(4, 80)   # サイズ（狭く）
        self.setColumnWidth(5, 50)   # 含む（狭く）
        self.setColumnWidth(6, 40)   # ZIP（狭く）
        
        # コンテキストメニュー
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        # チェックボックス変更の監視
        self.itemChanged.connect(self.on_item_changed)
        
        # 選択変更シグナル
        self.itemSelectionChanged.connect(self.on_selection_changed)
        
        # 状態列にチェックボックスを配置するための準備
        self.checkbox_items = {}  # id(tree_item) -> QCheckBox のマッピング
    
    def clear(self):
        """ツリーをクリア"""
        super().clear()
        self.checkbox_items.clear()
    
    def load_file_tree(self, file_items: List[FileItem]):
        """ファイルツリーをロード"""
        self.clear()
        self.file_items.clear()
        
        # ディレクトリ構造を構築
        dir_items = {}  # パス -> QTreeWidgetItem
        
        # ルートアイテム
        dir_items[""] = self.invisibleRootItem()
        
        for file_item in file_items:
            parent_path = str(Path(file_item.relative_path).parent)
            if parent_path == ".":
                parent_path = ""
            
            # 親ディレクトリが存在しない場合は作成
            if parent_path and parent_path not in dir_items:
                self._create_parent_dirs(parent_path, dir_items, file_items)
            
            # アイテム作成
            tree_item = QTreeWidgetItem()
            tree_item.setText(0, file_item.name)
            tree_item.setText(1, "📁" if file_item.file_type == FileType.DIRECTORY else "📄")
            
            # 親に追加（ウィジェットを設定する前に）
            parent_item = dir_items.get(parent_path, self.invisibleRootItem())
            parent_item.addChild(tree_item)
            
            # 種類選択ラジオボタン（2列目）- ファイルのみ
            if file_item.file_type == FileType.FILE:
                item_type_widget = self._create_item_type_widget(file_item, tree_item)
                self.setItemWidget(tree_item, 2, item_type_widget)
            
            # 拡張子列とサイズ列（3列目・4列目）
            if file_item.file_type == FileType.FILE:
                extension = Path(file_item.name).suffix
                tree_item.setText(3, extension)
                tree_item.setText(4, self._format_size(file_item.size))
            else:
                tree_item.setText(3, "")  # ディレクトリは拡張子なし
                tree_item.setText(4, f"{file_item.child_count} files")
            
            # 含むチェックボックス（5列目）
            include_checkbox = QCheckBox()
            # ダイアログでの使用を判定するために、親ウィジェットチェーンを確認
            is_in_dialog = False
            parent_widget = self
            while parent_widget:
                if isinstance(parent_widget, QDialog):
                    is_in_dialog = True
                    break
                parent_widget = parent_widget.parent()
            
            # ダイアログ内の場合は初期値を未チェックに設定（後で_set_fileset_selectionsで適切に設定される）
            if is_in_dialog:
                include_checkbox.setChecked(False)
            else:
                include_checkbox.setChecked(not file_item.is_excluded)
            
            include_checkbox.stateChanged.connect(
                lambda state, item=tree_item, file_item=file_item: self.on_include_checkbox_changed(state, item, file_item)
            )
            self.setItemWidget(tree_item, 5, include_checkbox)
            
            # ZIPチェックボックス（6列目）- フォルダのみ
            if file_item.file_type == FileType.DIRECTORY:
                zip_checkbox = QCheckBox()
                # 初期値はファイルアイテムのis_zip属性から取得（存在しない場合はFalse）
                initial_zip_state = getattr(file_item, 'is_zip', False)
                zip_checkbox.setChecked(initial_zip_state)
                zip_checkbox.stateChanged.connect(
                    lambda state, item=tree_item, file_item=file_item: self.on_zip_checkbox_changed(state, item, file_item)
                )
                self.setItemWidget(tree_item, 6, zip_checkbox)
            
            # スタイル設定
            if file_item.is_excluded:
                for col in range(5):  # 拡張子列まで（サイズ列含む）
                    tree_item.setForeground(col, _theme_brush(ThemeKey.TEXT_MUTED))
            else:
                # サイズ列の色分け（ファイルとディレクトリで色を変える）
                if file_item.file_type == FileType.FILE:
                    tree_item.setForeground(4, _theme_brush(ThemeKey.TEXT_SUCCESS))  # ファイル：緑系
                else:
                    tree_item.setForeground(4, _theme_brush(ThemeKey.TEXT_INFO))  # ディレクトリ：青系
            
            # マッピング保存
            self.file_items[id(tree_item)] = file_item
            
            # ディレクトリの場合は dir_items に追加
            if file_item.file_type == FileType.DIRECTORY:
                dir_items[file_item.relative_path] = tree_item
        
        # 展開
        self.expandAll()
    
    def _create_item_type_widget(self, file_item: FileItem, tree_item: QTreeWidgetItem) -> QWidget:
        """ファイル種類選択ウィジェットを作成"""
        widget = QWidget()
        widget.setMinimumWidth(120)  # 最小幅を設定
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(5)  # スペースを少し広げる
        
        # ラジオボタングループ
        button_group = QButtonGroup(widget)  # 親を設定
        
        # データラジオボタン
        data_radio = QRadioButton("データ")
        data_radio.setMinimumWidth(50)  # 最小幅を設定
        data_radio.setChecked(file_item.item_type == FileItemType.DATA)
        data_radio.toggled.connect(
            lambda checked, item=file_item, tree_item=tree_item: 
            self.on_item_type_changed(checked, item, tree_item, FileItemType.DATA)
        )
        
        # 添付ラジオボタン
        attachment_radio = QRadioButton("添付")
        attachment_radio.setMinimumWidth(50)  # 最小幅を設定
        attachment_radio.setChecked(file_item.item_type == FileItemType.ATTACHMENT)
        attachment_radio.toggled.connect(
            lambda checked, item=file_item, tree_item=tree_item: 
            self.on_item_type_changed(checked, item, tree_item, FileItemType.ATTACHMENT)
        )
        
        # ボタングループに追加
        button_group.addButton(data_radio)
        button_group.addButton(attachment_radio)
        
        # レイアウトに追加
        layout.addWidget(data_radio)
        layout.addWidget(attachment_radio)
        # layout.addStretch()  # ストレッチを削除して幅を確保
        
        return widget
    
    def on_item_type_changed(self, checked: bool, file_item: FileItem, tree_item: QTreeWidgetItem, item_type: FileItemType):
        """ファイル種類変更ハンドラ"""
        if checked:
            file_item.item_type = item_type
            logger.debug("ファイル '%s' の種類を %s に変更", file_item.name, item_type.value)
    
    def _create_parent_dirs(self, path: str, dir_items: dict, file_items: List[FileItem]):
        """親ディレクトリを再帰的に作成"""
        if path in dir_items:
            return
        
        parent_path = str(Path(path).parent)
        if parent_path == ".":
            parent_path = ""
        
        # 親を先に作成
        if parent_path and parent_path not in dir_items:
            self._create_parent_dirs(parent_path, dir_items, file_items)
        
        # 対応するFileItemを検索
        dir_item = None
        for file_item in file_items:
            if file_item.relative_path == path and file_item.file_type == FileType.DIRECTORY:
                dir_item = file_item
                break
        
        if dir_item:
            tree_item = QTreeWidgetItem()
            tree_item.setText(0, dir_item.name)
            tree_item.setText(1, "📁")
            tree_item.setText(3, "")  # 拡張子列（空）
            tree_item.setText(4, f"{dir_item.child_count} files")  # サイズ列
            
            parent_item = dir_items.get(parent_path, self.invisibleRootItem())
            parent_item.addChild(tree_item)
            
            dir_items[path] = tree_item
            self.file_items[id(tree_item)] = dir_item
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズをフォーマット"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def get_selected_items(self) -> List[FileItem]:
        """選択されたアイテムを取得"""
        selected_items = []
        for tree_item in self.selectedItems():
            if id(tree_item) in self.file_items:
                selected_items.append(self.file_items[id(tree_item)])
        return selected_items
    
    def on_selection_changed(self):
        """選択変更処理"""
        selected_items = self.get_selected_items()
        self.items_selected.emit(selected_items)
    
    def on_checkbox_changed(self, state, tree_item, file_item):
        """チェックボックス状態変更処理"""
        try:
            is_checked = (state == 2)  # Qt.CheckState.Checked.value
            file_item.is_excluded = not is_checked
            
            # 視覚的フィードバック
            if file_item.is_excluded:
                tree_item.setForeground(0, _theme_brush(ThemeKey.TEXT_MUTED))
                tree_item.setForeground(1, _theme_brush(ThemeKey.TEXT_MUTED))
                tree_item.setForeground(2, _theme_brush(ThemeKey.TEXT_MUTED))
            else:
                tree_item.setForeground(0, _theme_brush(ThemeKey.TEXT_PRIMARY))
                tree_item.setForeground(1, _theme_brush(ThemeKey.TEXT_PRIMARY))
                tree_item.setForeground(2, _theme_brush(ThemeKey.TEXT_PRIMARY))
            
            # 選択状態をシグナルで通知
            selected_items = self.get_selected_items()
            self.items_selected.emit(selected_items)
            
        except Exception as e:
            logger.error("チェックボックス変更エラー: %s", e)
    
    def show_context_menu(self, position):
        """コンテキストメニュー表示"""
        item = self.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        if id(item) in self.file_items:
            file_item = self.file_items[id(item)]
            
            # フォルダの場合のみファイルセット追加メニューを表示
            if file_item.file_type == FileType.DIRECTORY:
                menu.addAction("ファイルセットに追加（配下全フォルダ）", 
                             lambda: self.add_to_fileset(item, include_subdirs=True))
                menu.addAction("ファイルセットに追加（このフォルダのみ）", 
                             lambda: self.add_to_fileset(item, include_subdirs=False))
                menu.addSeparator()
                
                # ZIP化指定メニューを追加
                zip_menu = menu.addMenu("ZIP化設定")
                
                # 現在のZIP化状態を確認
                is_zip_enabled = getattr(file_item, 'is_zip', False)
                
                zip_on_action = zip_menu.addAction("ZIP化する")
                zip_on_action.setCheckable(True)
                zip_on_action.setChecked(is_zip_enabled)
                zip_on_action.triggered.connect(lambda: self.set_zip_flag(item, True))
                
                zip_off_action = zip_menu.addAction("ZIP化しない")
                zip_off_action.setCheckable(True)
                zip_off_action.setChecked(not is_zip_enabled)
                zip_off_action.triggered.connect(lambda: self.set_zip_flag(item, False))
        
        # 従来の「除外する」メニューは削除
        # チェックボックスのみで制御
        menu.exec_(self.mapToGlobal(position))
    
    def set_zip_flag(self, tree_item: QTreeWidgetItem, is_zip: bool):
        """フォルダのZIP化フラグを設定"""
        if id(tree_item) not in self.file_items:
            return
        
        file_item = self.file_items[id(tree_item)]
        if file_item.file_type != FileType.DIRECTORY:
            return
        
        # ZIP化フラグを設定
        file_item.is_zip = is_zip
        
        # 視覚的なインジケーターを追加（アイコンやテキスト色の変更）
        if is_zip:
            tree_item.setForeground(0, _theme_brush(ThemeKey.TEXT_INFO))  # 青色でZIP化対象を示す
            tree_item.setText(0, f"📦 {file_item.name}")
        else:
            tree_item.setForeground(0, _theme_brush(ThemeKey.TEXT_PRIMARY))  # 通常の色に戻す
            tree_item.setText(0, file_item.name)
        
        logger.debug("ZIP化フラグ設定: %s -> %s", file_item.name, is_zip)
    
    def add_to_fileset(self, tree_item: QTreeWidgetItem, include_subdirs: bool):
        """選択したフォルダをファイルセットに追加"""
        if id(tree_item) not in self.file_items:
            return
        
        file_item = self.file_items[id(tree_item)]
        if file_item.file_type != FileType.DIRECTORY:
            return
        
        try:
            # 親ウィジェット（BatchRegisterWidget）を取得
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'file_set_manager'):
                parent_widget = parent_widget.parent()
            
            if not parent_widget or not parent_widget.file_set_manager:
                QMessageBox.warning(self, "エラー", "ファイルセットマネージャーが見つかりません")
                return
            
            logger.debug("add_to_fileset: フォルダ=%s, include_subdirs=%s", file_item.name, include_subdirs)
            
            # チェック済みアイテムを収集（ファイルのみ）
            all_checked_items = parent_widget._get_checked_items_from_tree()
            checked_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            logger.debug("add_to_fileset: 全チェック済みファイル数=%s", len(checked_files))
            
            if include_subdirs:
                # 配下全フォルダの場合：選択したフォルダ以下のファイルのみ
                target_path = file_item.relative_path
                logger.debug("add_to_fileset（配下全て）: target_path=%s", target_path)
                filtered_items = []
                for item in checked_files:
                    # パス区切り文字を統一してチェック
                    item_path = item.relative_path.replace('\\', '/')
                    target_normalized = target_path.replace('\\', '/')
                    
                    # 選択したフォルダ以下のパスかどうかチェック
                    is_subdir = item_path.startswith(target_normalized + "/")
                    
                    # 直下のファイルかどうかチェック
                    item_parent = os.path.dirname(item.relative_path)
                    is_direct = item_parent == target_path
                    
                    logger.debug("add_to_fileset（配下全て）: ファイル=%s, parent=%s, is_subdir=%s, is_direct=%s", item.relative_path, item_parent, is_subdir, is_direct)
                    
                    if is_subdir or is_direct:
                        filtered_items.append(item)
                        logger.debug("add_to_fileset（配下全て）: 含める -> %s", item.relative_path)
                    else:
                        logger.debug("add_to_fileset（配下全て）: 除外 -> %s", item.relative_path)
                checked_items = filtered_items
            else:
                # このフォルダのみの場合：選択したフォルダの直下のファイルのみ
                target_path = file_item.relative_path
                filtered_items = []
                for item in checked_files:
                    # 直下のファイルかどうかチェック
                    parent_path = os.path.dirname(item.relative_path)
                    
                    if parent_path == target_path:
                        # 直下のファイルのみを含める
                        filtered_items.append(item)
                        logger.debug("add_to_fileset（このフォルダのみ）: 直下ファイル含める -> %s", item.relative_path)
                    else:
                        # サブフォルダ内のファイルは除外
                        logger.debug("add_to_fileset（このフォルダのみ）: サブフォルダ内ファイル除外 -> %s", item.relative_path)
                checked_items = filtered_items
            
            if not checked_items:
                QMessageBox.information(self, "情報", "選択したフォルダ範囲に「含む」にチェックされたファイルがありません")
                return
            
            logger.debug("add_to_fileset: フィルタ後のファイル数=%s", len(checked_items))
            
            # 既存ファイルセットとの重複チェック
            conflicts = []
            checked_paths = {item.path for item in checked_items}
            
            for fileset in parent_widget.file_set_manager.file_sets:
                for existing_file in fileset.items:
                    if existing_file.path in checked_paths:
                        conflicts.append(existing_file.path)
            
            if conflicts:
                conflict_msg = "以下のファイルは既に他のファイルセットに含まれています：\n"
                conflict_msg += "\n".join([f"- {os.path.basename(f)}" for f in conflicts[:10]])  # 最初の10件
                if len(conflicts) > 10:
                    conflict_msg += f"\n... 他{len(conflicts) - 10}件"
                conflict_msg += "\n\nこれらのファイルを除外して追加しますか？"

                reply = _centered_question(
                    self,
                    "重複ファイル",
                    conflict_msg,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                
                if reply != QMessageBox.Yes:
                    return
                
                # 重複ファイルを除外
                checked_items = [item for item in checked_items if item.path not in conflicts]
            
            if not checked_items:
                QMessageBox.information(self, "情報", "追加可能なファイルがありません")
                return
            
            # 新しいファイルセットを作成（既存セットはクリアしない）
            fileset_name = file_item.name  # フォルダ名のみ
            
            # デバッグ情報：作成前のファイル数
            logger.debug("ファイルセット作成前: checked_items=%s個", len(checked_items))
            for i, item in enumerate(checked_items):
                logger.debug("%s: %s (%s) -> %s", i+1, item.name, item.file_type.name, item.relative_path)
            
            # ZIP化指定されたディレクトリがあるか確認し、ファイルリストにディレクトリ情報を追加
            items_to_add = list(checked_items)  # ファイルリストをコピー
            
            # ZIP化指定されたディレクトリ情報を追加
            if getattr(file_item, 'is_zip', False) and file_item.file_type == FileType.DIRECTORY:
                logger.debug("ZIP化ディレクトリを追加: %s", file_item.name)
                # ディレクトリ情報をアイテムリストに追加（ZIP化フラグ付き）
                zip_dir_item = FileItem(
                    path=file_item.path,
                    relative_path=file_item.relative_path,
                    name=file_item.name,
                    file_type=FileType.DIRECTORY,
                    is_zip=True
                )
                items_to_add.append(zip_dir_item)
                logger.debug("ZIP化ディレクトリ追加完了: %s, is_zip=%s", zip_dir_item.name, zip_dir_item.is_zip)
            
            new_fileset = parent_widget.file_set_manager.create_manual_fileset(
                fileset_name, items_to_add)
            
            # 作成直後に一時フォルダとマッピングファイルを作成
            parent_widget._create_temp_folder_and_mapping(new_fileset)
            
            # デバッグ情報：作成後のファイル数
            logger.debug("ファイルセット作成後: items=%s個", len(new_fileset.items))
            for i, item in enumerate(new_fileset.items):
                logger.debug("%s: %s (%s) -> %s", i+1, item.name, item.file_type.name, item.relative_path)
            
            # ファイルセットテーブル更新
            parent_widget.refresh_fileset_display()
            parent_widget.update_summary()
            
            # 成功メッセージ
            file_count = len(checked_items)
            
            QMessageBox.information(self, "完了", 
                f"ファイルセット '{fileset_name}' を作成しました。\n"
                f"ファイル数: {file_count}個")
            
        except Exception as e:
            logger.error("add_to_fileset: %s", e)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "エラー", f"ファイルセット作成に失敗しました: {str(e)}")
    
    def _collect_files_recursive(self, tree_item, file_item):
        """再帰的にファイルを収集（配下全フォルダ用）"""
        files = []
        
        # 子アイテムを再帰的に処理（すべてのサブフォルダとファイルを含む）
        for i in range(tree_item.childCount()):
            child_item = tree_item.child(i)
            if id(child_item) in self.file_items:
                child_file_item = self.file_items[id(child_item)]
                files.append((child_item, child_file_item))
                
                # ディレクトリの場合は再帰的に処理
                if child_file_item.file_type == FileType.DIRECTORY:
                    files.extend(self._collect_files_recursive(child_item, child_file_item))
        
        return files
    
    def _collect_files_single(self, tree_item, file_item):
        """単一フォルダ内のファイルを収集（このフォルダのみ用）"""
        files = []
        
        # 直下のファイル・フォルダのみ処理
        for i in range(tree_item.childCount()):
            child_item = tree_item.child(i)
            if id(child_item) in self.file_items:
                child_file_item = self.file_items[id(child_item)]
                files.append((child_item, child_file_item))
        
        return files
    
    def _is_item_checked(self, tree_item):
        """アイテムがチェックされているかどうか"""
        # チェックボックスの状態を直接確認
        include_checkbox = self.itemWidget(tree_item, 5)  # 「含む」列（インデックス5）
        if include_checkbox and isinstance(include_checkbox, QCheckBox):
            # チェックボックスの状態とFileItemの状態を同期させる
            file_item = self.file_items.get(id(tree_item))
            if file_item:
                # チェックボックスの状態をFileItemに反映
                is_checked = include_checkbox.isChecked()
                file_item.is_excluded = not is_checked
                return is_checked
            return include_checkbox.isChecked()
        
        # チェックボックスがない場合はFileItemの状態を確認
        file_item = self.file_items.get(id(tree_item))
        if file_item:
            return not file_item.is_excluded
        
        return False
    
    def _check_conflicts(self, files, file_set_manager):
        """既存ファイルセットとの重複チェック"""
        conflicts = []
        file_paths = [file_item.path for _, file_item in files]
        
        for fileset in file_set_manager.file_sets:
            for existing_file in fileset.items:  # filesではなくitems
                if existing_file.path in file_paths:
                    conflicts.append(existing_file.path)
        
        return list(set(conflicts))  # 重複を除去
    
    def on_include_checkbox_changed(self, state, tree_item, file_item):
        """含むチェックボックス変更時の処理"""
        try:
            is_checked = state == 2  # Qt.CheckState.Checked.value
            file_item.is_excluded = not is_checked
            
            # フォルダの場合は配下の全アイテムも連動
            if file_item.file_type == FileType.DIRECTORY:
                self._update_children_include_state(tree_item, is_checked)
            
            # 親フォルダの状態更新
            self._update_parent_include_state(tree_item)
            
            # 表示スタイル更新
            self._update_item_style(tree_item, file_item)
            
        except Exception as e:
            logger.warning("含むチェックボックス変更エラー: %s", e)
    
    def on_zip_checkbox_changed(self, state, tree_item, file_item):
        """ZIPチェックボックス変更時の処理"""
        try:
            is_checked = state == 2  # Qt.CheckState.Checked.value
            # ZIP状態をfile_itemの拡張属性に保存
            if not hasattr(file_item, 'is_zip'):
                file_item.is_zip = False
            file_item.is_zip = is_checked
            logger.debug("ZIP状態変更: %s -> %s", file_item.name, is_checked)
            
            # ZIPにチェックが入った場合、配下の全フォルダのZIPチェックを外す
            if is_checked:
                self._clear_child_zip_flags(tree_item)
                logger.info("フォルダ '%s' をZIP化設定。配下フォルダのZIP設定を解除しました。", file_item.name)
            
        except Exception as e:
            logger.warning("ZIPチェックボックス変更エラー: %s", e)
    
    def _clear_child_zip_flags(self, tree_item):
        """子フォルダのZIP設定を再帰的に解除"""
        for i in range(tree_item.childCount()):
            child_item = tree_item.child(i)
            if id(child_item) in self.file_items:
                child_file_item = self.file_items[id(child_item)]
                
                # フォルダの場合のみZIP設定を解除
                if child_file_item.file_type == FileType.DIRECTORY:
                    # ファイルアイテムのZIP状態を解除
                    if hasattr(child_file_item, 'is_zip'):
                        child_file_item.is_zip = False
                    
                    # ZIPチェックボックス（6列目）を解除
                    zip_checkbox = self.itemWidget(child_item, 6)
                    if zip_checkbox and isinstance(zip_checkbox, QCheckBox):
                        zip_checkbox.blockSignals(True)  # シグナル無効化
                        zip_checkbox.setChecked(False)
                        zip_checkbox.blockSignals(False)  # シグナル再有効化
                    
                    # 再帰的に子フォルダも処理
                    self._clear_child_zip_flags(child_item)

    def _update_children_include_state(self, tree_item, is_checked):
        """子アイテムの含む状態を更新"""
        for i in range(tree_item.childCount()):
            child_item = tree_item.child(i)
            if id(child_item) in self.file_items:
                child_file_item = self.file_items[id(child_item)]
                child_file_item.is_excluded = not is_checked
                
                # チェックボックスUIも更新
                include_checkbox = self.itemWidget(child_item, 5)
                if include_checkbox and isinstance(include_checkbox, QCheckBox):
                    include_checkbox.setChecked(is_checked)
                
                # 表示スタイル更新
                self._update_item_style(child_item, child_file_item)
                
                # 再帰的に子要素も更新
                if child_file_item.file_type == FileType.DIRECTORY:
                    self._update_children_include_state(child_item, is_checked)
    
    def _update_parent_include_state(self, tree_item):
        """親アイテムの含む状態を更新"""
        parent_item = tree_item.parent()
        if not parent_item or id(parent_item) not in self.file_items:
            return
        
        # 親の全子要素の状態をチェック
        checked_children = 0
        total_children = parent_item.childCount()
        
        for i in range(total_children):
            child_item = parent_item.child(i)
            if id(child_item) in self.file_items:
                child_file_item = self.file_items[id(child_item)]
                if not child_file_item.is_excluded:
                    checked_children += 1
        
        # 親の状態を決定
        parent_file_item = self.file_items[id(parent_item)]
        parent_checkbox = self.itemWidget(parent_item, 5)
        
        if parent_checkbox and isinstance(parent_checkbox, QCheckBox):
            if checked_children == 0:
                # 全て未チェック
                parent_file_item.is_excluded = True
                parent_checkbox.setChecked(False)
            elif checked_children == total_children:
                # 全てチェック
                parent_file_item.is_excluded = False
                parent_checkbox.setChecked(True)
            else:
                # 一部チェック - 親は含むにする
                parent_file_item.is_excluded = False
                parent_checkbox.setChecked(True)
        
        # 表示スタイル更新
        self._update_item_style(parent_item, parent_file_item)
        
        # さらに上の親も更新
        self._update_parent_include_state(parent_item)
    
    def _update_item_style(self, tree_item, file_item):
        """アイテムの表示スタイルを更新"""
        if file_item.is_excluded:
            for col in range(4):
                tree_item.setForeground(col, _theme_brush(ThemeKey.TEXT_MUTED))
        else:
            # 通常色に戻す
            for col in range(4):
                tree_item.setForeground(col, _theme_brush(ThemeKey.TEXT_PRIMARY))
            
            # サイズ列の色分け
            if file_item.file_type == FileType.FILE:
                tree_item.setForeground(3, _theme_brush(ThemeKey.TEXT_SUCCESS))  # ファイル：緑系
            else:
                tree_item.setForeground(3, _theme_brush(ThemeKey.TEXT_INFO))  # ディレクトリ：青系
    
    def on_item_changed(self, item, column):
        """アイテム変更時の処理（未使用だが、互換性のため残す）"""
        pass
    
    def toggle_exclude(self, tree_item: QTreeWidgetItem, exclude: bool):
        """除外状態を切り替え"""
        if id(tree_item) not in self.file_items:
            return
        
        file_item = self.file_items[id(tree_item)]
        file_item.is_excluded = exclude
        
        # 表示更新
        tree_item.setText(3, "除外" if exclude else "含む")
        tree_item.setCheckState(0, Qt.CheckState.Unchecked if exclude else Qt.CheckState.Checked)
        
        # スタイル更新
        if exclude:
            tree_item.setForeground(0, _theme_brush(ThemeKey.TEXT_MUTED))
            tree_item.setForeground(1, _theme_brush(ThemeKey.TEXT_MUTED))
            tree_item.setForeground(2, _theme_brush(ThemeKey.TEXT_MUTED))
            tree_item.setForeground(3, _theme_brush(ThemeKey.TEXT_MUTED))
        else:
            tree_item.setForeground(0, _theme_brush(ThemeKey.TEXT_PRIMARY))
            tree_item.setForeground(1, _theme_brush(ThemeKey.TEXT_PRIMARY))
            tree_item.setForeground(2, _theme_brush(ThemeKey.TEXT_PRIMARY))
            tree_item.setForeground(3, _theme_brush(ThemeKey.TEXT_PRIMARY))
    
    def find_tree_item_by_file_item(self, target_file_item: FileItem) -> Optional[QTreeWidgetItem]:
        """FileItemに対応するQTreeWidgetItemを検索"""
        for tree_item_id, file_item in self.file_items.items():
            if file_item.relative_path == target_file_item.relative_path:
                # IDからQTreeWidgetItemを逆引き
                return self._find_tree_item_by_id(tree_item_id)
        return None
    
    def _find_tree_item_by_id(self, target_id: int) -> Optional[QTreeWidgetItem]:
        """IDでQTreeWidgetItemを検索（再帰的）"""
        def search_recursive(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if id(item) == target_id:
                return item
            
            for i in range(item.childCount()):
                child = item.child(i)
                result = search_recursive(child)
                if result:
                    return result
            return None
        
        # ルートアイテムから検索
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            result = search_recursive(root.child(i))
            if result:
                return result
        return None


class FileSetTableWidget(QTableWidget):
    """ファイルセット一覧表示ウィジェット"""
    
    # シグナル定義
    fileset_selected = Signal(object)  # FileSet
    fileset_deleted = Signal(int)      # ファイルセットID
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_sets = []
        self.file_set_manager = None  # file_set_managerへの参照
        self.required_exts = []  # テンプレート対応拡張子（正規化済み）
        self._compact_visible_rows: int | None = None
        self.setup_ui()

    def apply_theme_style(self) -> None:
        """テーマ由来の基本スタイル + 本ウィジェット固有の微調整を反映する。"""

        extra = """
        QTableWidget::item { padding: 2px 4px; }
        QHeaderView::section { padding: 1px; }
        """
        self.setStyleSheet(get_fileset_table_style() + extra)

        # テーマ変更でヘッダ高さが変わる場合があるため、固定高さも追従させる
        if self._compact_visible_rows is not None:
            try:
                self.set_compact_view_rows(self._compact_visible_rows)
            except Exception:
                pass

    def compute_compact_height_for_rows(self, visible_rows: int) -> int:
        """ヘッダ行 + データ行(visible_rows)分の表示に必要な高さを算出する。"""
        rows = max(0, int(visible_rows))
        try:
            header_h = int(self.horizontalHeader().sizeHint().height())
        except Exception:
            header_h = 0

        row_h = 0
        try:
            row_h = int(self.verticalHeader().defaultSectionSize())
        except Exception:
            row_h = 0

        frame = 0
        try:
            frame = int(self.frameWidth()) * 2
        except Exception:
            frame = 0

        # 見切れ防止の微小マージン
        return header_h + (row_h * rows) + frame + 2

    def set_compact_view_rows(self, visible_rows: int) -> None:
        """一覧の表示行数を固定する（スクロールで全件閲覧する）。"""
        try:
            self._compact_visible_rows = max(0, int(visible_rows))
            h = self.compute_compact_height_for_rows(visible_rows)
            if h > 0:
                self.setFixedHeight(h)
        except Exception:
            pass
    
    def setup_ui(self):
        """UIセットアップ"""
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels([
            "ファイルセット名", "ファイル数", "マッピング", "サイズ", "整理方法", "データ名", "試料", "データセット", "操作"
        ])
        
        # スタイル設定（テーマ + 微調整）
        self.apply_theme_style()
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        
        # ヘッダー設定
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(100)  # デフォルト列幅を設定
        header.setMinimumSectionSize(60)   # 最小列幅を設定
        
        # カラム幅設定とリサイズ可能設定
        # 内容に応じて自動幅を優先しつつ長い列は手動調整可能
        header.setSectionResizeMode(0, QHeaderView.Interactive)      # 名称
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # ファイル数(対象数含む)
        header.setSectionResizeMode(2, QHeaderView.Interactive)      # マッピング
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # サイズ
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # 整理方法
        header.setSectionResizeMode(5, QHeaderView.Interactive)      # データ名
        header.setSectionResizeMode(6, QHeaderView.Interactive)      # 試料
        header.setSectionResizeMode(7, QHeaderView.Interactive)      # データセット
        header.setSectionResizeMode(8, QHeaderView.Fixed)            # 操作
        
        # 初期幅設定（推奨値）
        self.setColumnWidth(0, 160)
        self.setColumnWidth(1, 110)  # F/D/M 表示で十分
        # マッピング列は内容に合わせて初期幅を最小化する（後続の load_file_sets で resizeColumnToContents も実施）
        self.setColumnWidth(2, 80)
        self.setColumnWidth(3, 70)
        self.setColumnWidth(4, 80)
        self.setColumnWidth(5, 110)
        self.setColumnWidth(6, 110)
        self.setColumnWidth(7, 130)
        self.setColumnWidth(8, 140)

        # 行高さ・余白調整（視認性 + ボタン収まり改善）
        # 既存 26px を +15% 程度に（約 30px）
        vh = self.verticalHeader()
        vh.setDefaultSectionSize(30)
        vh.setMinimumSectionSize(28)
        vh.setVisible(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        # 一覧の表示行数（ヘッダ + データ4行）
        self.set_compact_view_rows(4)

        # 表示後にヘッダ高さが確定してから再度固定高さを調整する
        try:
            QTimer.singleShot(0, lambda: self.set_compact_view_rows(4))
        except Exception:
            pass
        
        # 選択変更シグナル
        self.itemSelectionChanged.connect(self.on_selection_changed)
        
        # ダブルクリックシグナル
        self.itemDoubleClicked.connect(self.on_double_clicked)
    
    def set_file_set_manager(self, file_set_manager):
        """file_set_managerへの参照を設定"""
        logger.debug("FileSetTableWidget.set_file_set_manager: 設定開始")
        logger.debug("set_file_set_manager: file_set_manager=%s", file_set_manager)
        if file_set_manager:
            logger.debug("set_file_set_manager: file_sets count=%s", len(getattr(file_set_manager, 'file_sets', [])))
        self.file_set_manager = file_set_manager
        logger.debug("FileSetTableWidget.set_file_set_manager: 設定完了")
    
    def load_file_sets(self, file_sets: List[FileSet]):
        """ファイルセット一覧をロード"""
        import traceback
        logger.debug("FileSetTableWidget.load_file_sets: 受信 %s ファイルセット", len(file_sets))
        logger.debug("load_file_sets 呼び出し元:")
        for line in traceback.format_stack()[-3:-1]:
            logger.debug("  %s", line.strip())
        
        # 受信したファイルセットの詳細をログ出力
        for i, fs in enumerate(file_sets):
            logger.debug("load_file_sets: FileSet[%s] id=%s, name=%s, items=%s", i, fs.id, fs.name, len(fs.items))
        
        self.file_sets = file_sets
        self.setRowCount(len(file_sets))
        logger.debug("FileSetTableWidget.load_file_sets: テーブル行数を %s に設定", len(file_sets))
        
        for row, file_set in enumerate(file_sets):
            logger.debug("FileSetTableWidget: 行%s 処理中: %s (id=%s, items=%s)", row, file_set.name, file_set.id, len(file_set.items))
            
            # ファイルセット名（アイコン付きのクリック可能ウィジェット）
            name_widget = self._create_name_widget_with_icon(file_set)
            self.setCellWidget(row, 0, name_widget)
            
            # ファイル数 + 対象拡張子一致数（F/D/M 形式）
            try:
                file_count = file_set.get_file_count()
                dir_count = file_set.get_directory_count()
            except:
                file_count = 0
                dir_count = 0
            match_count = self._compute_match_count(file_set)
            count_text = f"{file_count}F/{dir_count}D({match_count}M)"
            count_item = QTableWidgetItem(count_text)
            count_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 1, count_item)
            
            # マッピングファイル
            mapping_widget = self._create_mapping_file_widget(file_set)
            self.setCellWidget(row, 2, mapping_widget)
            
            # サイズ
            try:
                total_size = file_set.get_total_size()
            except:
                total_size = 0
            size_item = QTableWidgetItem(self._format_size(total_size))
            size_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 3, size_item)
            
            # 整理方法（コンボボックス）
            method_combo = QComboBox()
            method_combo.addItems(["フラット", "ZIP"])
            try:
                current_method = "ZIP" if getattr(file_set, 'organize_method', None) == PathOrganizeMethod.ZIP else "フラット"
            except:
                current_method = "フラット"
            method_combo.setCurrentText(current_method)
            method_combo.currentTextChanged.connect(
                lambda text, fs=file_set: self._on_organize_method_changed(fs, text)
            )
            self.setCellWidget(row, 4, method_combo)
            
            # データ名
            data_name = getattr(file_set, 'data_name', '') or "未設定"
            data_name_item = QTableWidgetItem(data_name)
            data_name_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 5, data_name_item)
            
            # 試料情報
            sample_info = self._get_sample_info_text(file_set)
            sample_item = QTableWidgetItem(sample_info)
            sample_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 6, sample_item)
            
            # データセット名
            dataset_name = self._get_dataset_name(file_set)
            dataset_item = QTableWidgetItem(dataset_name)
            dataset_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 7, dataset_item)
            
            # 操作ボタンのコンテナウィジェット作成
            operations_widget = QWidget()
            operations_layout = QHBoxLayout(operations_widget)
            operations_layout.setContentsMargins(0, 0, 0, 0)
            operations_layout.setSpacing(4)
            
            # 登録ボタン
            register_btn = QPushButton("登録")
            try:
                register_btn.setFont(self.font())
            except Exception:
                pass
            register_btn.setToolTip("このファイルセットを登録します")
            register_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                    border: none;
                    padding: 0px 6px;
                    border-radius: 4px;
                    min-width: 40px;
                    min-height: 22px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
                }}
            """)
            register_btn.clicked.connect(lambda checked, fid=file_set.id: self.register_single_fileset(fid))
            operations_layout.addWidget(register_btn)
            
            # 削除ボタン
            delete_btn = QPushButton("削除")
            try:
                delete_btn.setFont(self.font())
            except Exception:
                pass
            delete_btn.setToolTip("このファイルセットを削除します")
            delete_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                    border: none;
                    padding: 0px 6px;
                    border-radius: 4px;
                    min-width: 40px;
                    min-height: 22px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
                }}
            """)
            delete_btn.clicked.connect(lambda checked, fid=file_set.id: self.delete_fileset(fid))
            operations_layout.addWidget(delete_btn)
            
            self.setCellWidget(row, 8, operations_widget)  # 操作列に配置

        # マッピング列は内容に合わせて初期幅を最小化
        try:
            self.resizeColumnToContents(2)
        except Exception:
            pass

    def _compute_match_count(self, file_set: FileSet) -> int:
        """テンプレート対応拡張子に一致するファイル数を算出"""
        if not self.required_exts:
            return 0
        total = 0
        try:
            for item in file_set.get_valid_items():
                if getattr(item, 'file_type', None) == FileType.FILE:
                    name = getattr(item, 'name', '') or getattr(item, 'relative_path', '')
                    ext = Path(name).suffix.lower().lstrip('.')
                    if ext in self.required_exts:
                        total += 1
        except Exception:
            pass
        return total

    def set_required_extensions(self, exts: List[str]):
        """対象拡張子を設定し再描画"""
        self.required_exts = [e.lower().strip().lstrip('.') for e in exts]
        if self.file_sets:
            # 行を再ロードして F/D/M を更新
            self.load_file_sets(self.file_sets)
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズをフォーマット"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _on_organize_method_changed(self, file_set, method_text: str):
        """整理方法変更処理"""
        try:
            if method_text == "ZIP":
                file_set.organize_method = PathOrganizeMethod.ZIP
            else:
                file_set.organize_method = PathOrganizeMethod.FLATTEN
            logger.debug("ファイルセット '%s' の整理方法を '%s' に変更", file_set.name, method_text)
        except Exception as e:
            logger.error("整理方法変更エラー: %s", e)

    def _get_sample_info_text(self, file_set) -> str:
        """試料情報テキストを取得"""
        try:
            # ファイルセットから試料情報を取得
            if hasattr(file_set, 'sample_mode'):
                mode = getattr(file_set, 'sample_mode', '未設定')
                
                # 内部値での判定
                if mode == 'existing' or mode == '既存試料使用':
                    sample_id = getattr(file_set, 'sample_id', '')
                    return f"既存: {sample_id}" if sample_id else "既存: 未設定"
                elif mode == 'new' or mode == '新規作成':
                    sample_name = getattr(file_set, 'sample_name', '')
                    return f"新規: {sample_name}" if sample_name else "新規"
                elif mode == 'same_as_previous' or mode == '前回と同じ':
                    return "前と同じ"
                else:
                    return f"設定済み({mode})"
            
            # sample_modeが設定されていない場合、他の試料情報で判定
            sample_name = getattr(file_set, 'sample_name', '')
            sample_id = getattr(file_set, 'sample_id', '')
            if sample_name:
                return f"新規: {sample_name}"
            elif sample_id:
                return f"既存: {sample_id}"
            
            return "未設定"
        except Exception as e:
            logger.error("試料情報取得エラー: %s", e)
            return "未設定"
    
    def _get_dataset_name(self, file_set) -> str:
        """データセット名を取得"""
        try:
            dataset_id = getattr(file_set, 'dataset_id', '')
            if not dataset_id:
                return "未設定"
            
            # まずファイルセット内のdataset_infoから名前を取得を試行
            dataset_info = getattr(file_set, 'dataset_info', None)
            if dataset_info and isinstance(dataset_info, dict):
                dataset_name = dataset_info.get('name', '')
                if dataset_name:
                    return dataset_name
            
            # 拡張設定からデータセット名を取得を試行
            extended_config = getattr(file_set, 'extended_config', None)
            if extended_config and isinstance(extended_config, dict):
                dataset_name = extended_config.get('dataset_name', '')
                if dataset_name:
                    return dataset_name
            
            # 親ウィジェットからデータセット一覧を取得
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'datasets'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'datasets'):
                for dataset in parent_widget.datasets:
                    if dataset.get('id') == dataset_id:
                        return dataset.get('attributes', {}).get('name', '未設定')
            
            # データセット名が見つからない場合は、IDの一部を表示
            return f"ID: {dataset_id[:8]}..." if len(dataset_id) > 8 else dataset_id
            
        except Exception as e:
            logger.error("データセット名取得エラー: %s", e)
            return "未設定"
    
    def on_selection_changed(self):
        """選択変更処理"""
        current_row = self.currentRow()
        if 0 <= current_row < len(self.file_sets):
            file_set = self.file_sets[current_row]
            self.fileset_selected.emit(file_set)
    
    def delete_fileset(self, fileset_id: int):
        """ファイルセット削除"""
        reply = _centered_question(
            self,
            "確認",
            "選択されたファイルセットを削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            self.fileset_deleted.emit(fileset_id)
    
    def register_single_fileset(self, fileset_id: int):
        """単一ファイルセットのデータ登録"""
        try:
            # 対象のファイルセットを検索
            target_fileset = None
            for fs in self.file_sets:
                if fs.id == fileset_id:
                    target_fileset = fs
                    break
            
            if not target_fileset:
                QMessageBox.warning(self, "エラー", "対象のファイルセットが見つかりません")
                return
            
            # v1.18.4: Bearer Tokenはapi_request_helperが自動選択するため、取得不要
            from .batch_preview_dialog import BatchRegisterPreviewDialog
            allowed_exts = []
            try:
                if hasattr(self, 'fileset_table') and self.fileset_table:
                    allowed_exts = getattr(self.fileset_table, 'required_exts', []) or []
            except Exception:
                allowed_exts = []
            dialog = BatchRegisterPreviewDialog(
                file_sets=[target_fileset],
                parent=self,
                bearer_token=None,  # v1.18.4: 自動選択に変更
                allowed_exts=allowed_exts
            )
            dialog.show()  # ダイアログを表示
            dialog.raise_()  # 最前面に持ってくる
            dialog.activateWindow()  # アクティブ化
            dialog.exec()
            
        except Exception as e:
            logger.error("register_single_fileset エラー: %s", e)
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"データ登録処理でエラーが発生しました:\n{str(e)}")
    
    def get_selected_fileset(self) -> Optional[FileSet]:
        """選択されたファイルセットを取得"""
        current_row = self.currentRow()
        if 0 <= current_row < len(self.file_sets):
            return self.file_sets[current_row]
        return None
    
    def refresh_data(self):
        """テーブルデータを再読み込み"""
        logger.debug("FileSetTableWidget.refresh_data: 呼び出された")
        try:
            # file_set_managerから最新のデータを取得
            if self.file_set_manager and hasattr(self.file_set_manager, 'file_sets'):
                latest_file_sets = self.file_set_manager.file_sets
                logger.debug("refresh_data: file_set_managerから%s個のファイルセットを取得", len(latest_file_sets))
                self.load_file_sets(latest_file_sets)
            elif hasattr(self, 'file_sets') and self.file_sets:
                logger.debug("refresh_data: 内部file_setsから%s個のファイルセットで再読み込み", len(self.file_sets))
                self.load_file_sets(self.file_sets)
            else:
                logger.debug("refresh_data: ファイルセットが存在しません")
                self.setRowCount(0)
        except Exception as e:
            logger.error("refresh_data: %s", e)
            import traceback
            traceback.print_exc()
    
    def on_double_clicked(self, item):
        """ダブルクリック時の処理"""
        try:
            fileset = self.get_selected_fileset()
            if fileset:
                parent_widget = self.parent()
                while parent_widget and not hasattr(parent_widget, 'show_data_tree_dialog'):
                    parent_widget = parent_widget.parent()
                
                if parent_widget:
                    parent_widget.show_data_tree_dialog(fileset)
        except Exception as e:
            logger.error("on_double_clicked: %s", e)
            import traceback
            traceback.print_exc()
    
    def _create_mapping_file_widget(self, file_set):
        """マッピングファイル列のウィジェットを作成"""
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # マッピングファイルの存在チェック
        mapping_file_exists = self._check_mapping_file_exists(file_set)
        
        # 状態表示ラベル
        status_label = QLabel("○" if mapping_file_exists else "×")
        status_label.setStyleSheet(f"""
            QLabel {{
                color: {get_color(ThemeKey.TEXT_SUCCESS) if mapping_file_exists else get_color(ThemeKey.TEXT_ERROR)};
                font-weight: bold;
            }}
        """)
        layout.addWidget(status_label)
        
        # 表示ボタン
        view_btn = QPushButton("表示")
        view_btn.setEnabled(mapping_file_exists)
        try:
            view_btn.setFont(self.font())
        except Exception:
            pass
        view_btn.setToolTip("マッピングファイルを表示します")
        view_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                border: none;
                padding: 0px 4px;
                border-radius: 3px;
                min-height: 22px;
            }}
            QPushButton:hover:enabled {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        view_btn.clicked.connect(lambda: self._view_mapping_file(file_set))
        layout.addWidget(view_btn)
        
        # 更新ボタン
        update_btn = QPushButton("更新")
        try:
            update_btn.setFont(self.font())
        except Exception:
            pass
        update_btn.setToolTip("マッピングファイルを更新します")
        update_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: none;
                padding: 0px 4px;
                border-radius: 3px;
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        update_btn.clicked.connect(lambda: self._update_mapping_file(file_set))
        layout.addWidget(update_btn)
        
        widget.setLayout(layout)
        return widget
    
    def _create_name_widget_with_icon(self, file_set):
        """ファイルセット名とアイコンのウィジェットを作成"""
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        
        # ファイルセット名ラベル
        name_label = QLabel(file_set.name)
        from classes.utils.label_style import apply_label_style
        apply_label_style(name_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
        layout.addWidget(name_label)
        
        # 間隔調整
        layout.addStretch()
        
        # フォルダ書き出しアイコンボタン
        export_icon = QPushButton("出力")
        export_icon.setToolTip("ファイルセットをフォルダまたはZIPファイルとして書き出し")
        try:
            export_icon.setFont(self.font())
        except Exception:
            pass
        export_icon.setMinimumWidth(40)
        export_icon.setFixedHeight(24)
        export_icon.setStyleSheet(f"""
            QPushButton {{
                border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                border-radius: 3px;
                color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                font-weight: bold;
                padding: 0px 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.PANEL_SUCCESS_BACKGROUND)};
                border-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        export_icon.clicked.connect(lambda: self._export_fileset_folder(file_set))
        layout.addWidget(export_icon)
        
        # 内容表示アイコンボタン
        view_icon = QPushButton("表示")
        view_icon.setToolTip("ファイルセットの内容を表示・編集")
        try:
            view_icon.setFont(self.font())
        except Exception:
            pass
        view_icon.setMinimumWidth(40)
        view_icon.setFixedHeight(24)
        view_icon.setStyleSheet(f"""
            QPushButton {{
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                border-radius: 3px;
                color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                font-weight: bold;
                padding: 0px 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)};
                border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
            }}
        """)
        view_icon.clicked.connect(lambda: self._show_fileset_content_dialog(file_set))
        layout.addWidget(view_icon)
        
        widget.setLayout(layout)
        return widget
    
    def _export_fileset_folder(self, file_set):
        """ファイルセットフォルダを書き出し"""
        try:
            # 一時フォルダが存在しない場合は先に作成
            temp_folder = None
            if hasattr(file_set, 'extended_config') and file_set.extended_config:
                temp_folder = file_set.extended_config.get('temp_folder')
            
            if not temp_folder or not os.path.exists(temp_folder):
                # 一時フォルダを作成
                from ..core.temp_folder_manager import TempFolderManager
                temp_manager = TempFolderManager()
                temp_folder, mapping_file = temp_manager.create_temp_folder_for_fileset(file_set)
                
                if not hasattr(file_set, 'extended_config'):
                    file_set.extended_config = {}
                file_set.extended_config['temp_folder'] = temp_folder
                file_set.extended_config['temp_created'] = True
                file_set.extended_config['mapping_file'] = mapping_file
                file_set.mapping_file = mapping_file
            
            # 書き出し形式を選択
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle("書き出し形式選択")
            msgbox.setText(f"ファイルセット '{file_set.name}' の書き出し形式を選択してください。")
            
            folder_btn = msgbox.addButton("フォルダとして書き出し", QMessageBox.ActionRole)
            zip_btn = msgbox.addButton("ZIPファイルとして書き出し", QMessageBox.ActionRole)
            cancel_btn = msgbox.addButton("キャンセル", QMessageBox.RejectRole)
            
            msgbox.exec()
            clicked_button = msgbox.clickedButton()
            
            if clicked_button == cancel_btn:
                return
                
            export_as_zip = (clicked_button == zip_btn)
            
            # 保存先を選択
            if export_as_zip:
                # ZIPファイル保存先を選択
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "ZIPファイル保存先", 
                    f"{file_set.name}.zip",
                    "ZIPファイル (*.zip)"
                )
                if not file_path:
                    return
                
                # ZIPファイルとして保存
                import shutil
                shutil.make_archive(file_path[:-4], 'zip', temp_folder)
                
                QMessageBox.information(self, "完了", 
                    f"ファイルセット '{file_set.name}' をZIPファイルとして保存しました。\n"
                    f"パス: {file_path}")
            else:
                # フォルダ保存先を選択
                folder_path = QFileDialog.getExistingDirectory(
                    self, "フォルダ保存先", ""
                )
                if not folder_path:
                    return
                
                # フォルダとして保存
                import shutil
                dest_folder = os.path.join(folder_path, file_set.name)
                shutil.copytree(temp_folder, dest_folder, dirs_exist_ok=True)
                
                QMessageBox.information(self, "完了", 
                    f"ファイルセット '{file_set.name}' をフォルダとして保存しました。\n"
                    f"パス: {dest_folder}")
                
        except Exception as e:
            logger.error("フォルダ書き出しエラー: %s", e)
            QMessageBox.warning(self, "エラー", f"フォルダ書き出しに失敗しました: {str(e)}")
    
    def _show_fileset_content_dialog(self, file_set):
        """ファイルセット内容表示・編集ダイアログを表示"""
        try:
            # 専用ダイアログが存在しない場合は、簡易版を使用
            self._show_simple_fileset_content_dialog(file_set)
        except Exception as e:
            logger.error("ファイルセット内容ダイアログエラー: %s", e)
            QMessageBox.warning(self, "エラー", f"ファイルセット内容の表示に失敗しました: {str(e)}")
    
    def _show_simple_fileset_content_dialog(self, file_set):
        """簡易版ファイルセット内容ダイアログ（組み込み版）"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"ファイルセット内容 - {file_set.name}")
        dialog.setModal(True)
        # 最前面表示設定（マルチディスプレイ環境対応）
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        dialog.resize(800, 600)
        
        layout = QVBoxLayout()
        
        # 情報表示
        info_label = QLabel(f"""
        <b>ファイルセット:</b> {file_set.name}<br>
        <b>総ファイル数:</b> {file_set.get_file_count()}個<br>
        <b>総フォルダ数:</b> {file_set.get_directory_count()}個<br>
        <b>総サイズ:</b> {self._format_size(file_set.get_total_size())}
        """)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 全ファイルツリーを取得（親ウィジェットから）
        parent_widget = self.parent()
        while parent_widget and not hasattr(parent_widget, 'file_tree'):
            parent_widget = parent_widget.parent()
        
        # ファイルリスト（全ツリーを表示、現在のファイルセットの項目を選択状態に）
        file_tree = FileTreeWidget()
        file_tree.setContextMenuPolicy(Qt.NoContextMenu)  # 右クリックメニュー無効化
        
        if parent_widget and hasattr(parent_widget, 'file_tree'):
            # 全ファイルツリーをロード
            all_file_items = []
            self._collect_all_file_items(parent_widget.file_tree.invisibleRootItem(), all_file_items, parent_widget.file_tree)
            file_tree.load_file_tree(all_file_items)
            
            # 現在のファイルセット内容を選択状態に設定
            self._set_fileset_selections(file_tree, file_set.items)
        else:
            # フォールバック：ファイルセットの内容のみ表示
            file_tree.load_file_tree(file_set.items)
            
        layout.addWidget(file_tree)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        ok_btn = QPushButton("適用")
        ok_btn.clicked.connect(lambda: self._apply_fileset_changes(dialog, file_set, file_tree))
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        dialog.show()  # ダイアログを表示
        dialog.raise_()  # 最前面に持ってくる
        dialog.activateWindow()  # アクティブ化
        if dialog.exec() == QDialog.Accepted:
            completion_message = dialog.property("_fileset_completion_message")
            if completion_message:
                QMessageBox.information(self.window() or self, "完了", str(completion_message))
    
    def _apply_fileset_changes(self, dialog, file_set, file_tree):
        """ファイルセットへの変更を適用（重複チェック付き・種類変更・ZIP設定対応）"""
        try:
            # チェック状態と種類変更に基づいてファイルセットを更新
            updated_items = []
            
            def collect_checked_items(parent_item):
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    # FileTreeWidgetの場合、「含む」列は5列目（種類列追加により変更）
                    checkbox = file_tree.itemWidget(child, 5)  # 含む列
                    if checkbox and isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                        # tree_itemからFileItemを取得
                        if id(child) in file_tree.file_items:
                            file_item = file_tree.file_items[id(child)]
                            
                            # 種類の変更も反映（ファイルの場合のみ）
                            if file_item.file_type == FileType.FILE:
                                item_type_widget = file_tree.itemWidget(child, 2)  # 種類列
                                if item_type_widget:
                                    # ラジオボタンの状態を確認
                                    for radio in item_type_widget.findChildren(QRadioButton):
                                        if radio.isChecked():
                                            if radio.text() == "データ":
                                                file_item.item_type = FileItemType.DATA
                                            elif radio.text() == "添付":
                                                file_item.item_type = FileItemType.ATTACHMENT
                                            break
                            
                            # ZIP設定の変更も反映（ディレクトリの場合のみ）
                            if file_item.file_type == FileType.DIRECTORY:
                                zip_checkbox = file_tree.itemWidget(child, 6)  # ZIP列
                                if zip_checkbox and isinstance(zip_checkbox, QCheckBox):
                                    file_item.is_zip = zip_checkbox.isChecked()
                                    logger.debug("ファイルセット変更適用 - ZIP設定: %s -> %s", file_item.name, file_item.is_zip)
                            
                            updated_items.append(file_item)
                    collect_checked_items(child)
            
            # ルートから収集
            root = file_tree.invisibleRootItem()
            collect_checked_items(root)
            
            # 他のファイルセットとの重複チェック
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'file_set_manager'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and parent_widget.file_set_manager:
                conflicts = []
                updated_paths = {item.path for item in updated_items}
                
                for other_fileset in parent_widget.file_set_manager.file_sets:
                    if other_fileset.id == file_set.id:
                        continue  # 自分自身は除外
                    
                    other_paths = {item.path for item in other_fileset.items}
                    conflicts.extend(updated_paths.intersection(other_paths))
                
                if conflicts:
                    conflict_msg = f"以下のファイルは他のファイルセットに既に含まれています：\n"
                    conflict_msg += "\n".join([f"- {os.path.basename(path)}" for path in conflicts[:10]])
                    if len(conflicts) > 10:
                        conflict_msg += f"\n... 他{len(conflicts) - 10}件"
                    conflict_msg += "\n\n変更を続行できません。"
                    
                    QMessageBox.warning(dialog, "重複エラー", conflict_msg)
                    return  # ダイアログを閉じない
            
            # ファイルセットを更新
            file_set.items = updated_items
            
            # マッピングファイルを自動更新
            mapping_file_path = None
            try:
                mapping_file_path = self._update_mapping_file(file_set, show_completion_dialog=False)
            except Exception as e:
                logger.warning("マッピングファイル自動更新エラー: %s", e)
            
            completion_lines = [
                f"ファイルセット '{file_set.name}' を更新しました。",
                f"選択ファイル数: {len(updated_items)}個",
            ]
            if mapping_file_path:
                completion_lines.append(f"マッピングファイル: {mapping_file_path}")

            dialog.setProperty("_fileset_completion_message", "\n".join(completion_lines))

            # ダイアログを閉じる
            dialog.accept()
                
        except Exception as e:
            logger.error("ファイルセット変更適用エラー: %s", e)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "エラー", f"ファイルセットの更新に失敗しました: {str(e)}")
    
    def _collect_all_file_items(self, parent_item, file_items_list, file_tree):
        """全ファイルアイテムを再帰的に収集"""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if id(child) in file_tree.file_items:
                file_item = file_tree.file_items[id(child)]
                file_items_list.append(file_item)
            self._collect_all_file_items(child, file_items_list, file_tree)
    
    def _set_fileset_selections(self, file_tree, fileset_items):
        """ファイルセットの内容に応じてチェックボックスとZIP設定を設定"""
        fileset_paths = {item.path for item in fileset_items}
        fileset_items_dict = {item.path: item for item in fileset_items}
        
        def set_checkbox_recursive(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if id(child) in file_tree.file_items:
                    file_item = file_tree.file_items[id(child)]
                    
                    # 含むチェックボックス設定
                    checkbox = file_tree.itemWidget(child, 5)  # 含む列（種類列追加により変更）
                    if checkbox and isinstance(checkbox, QCheckBox):
                        is_in_fileset = file_item.path in fileset_paths
                        checkbox.setChecked(is_in_fileset)
                    
                    # ZIP設定を復元（ディレクトリの場合のみ）
                    if file_item.file_type == FileType.DIRECTORY:
                        zip_checkbox = file_tree.itemWidget(child, 6)  # ZIP列
                        if zip_checkbox and isinstance(zip_checkbox, QCheckBox):
                            # ファイルセット内の対応するアイテムからZIP設定を取得
                            if file_item.path in fileset_items_dict:
                                original_item = fileset_items_dict[file_item.path]
                                if hasattr(original_item, 'is_zip'):
                                    zip_checkbox.setChecked(original_item.is_zip)
                                    file_tree.file_items[id(child)].is_zip = original_item.is_zip
                                    logger.debug("ZIP設定復元: %s -> %s", file_item.name, original_item.is_zip)
                                
                set_checkbox_recursive(child)
        
        root = file_tree.invisibleRootItem()
        set_checkbox_recursive(root)
    
    def _check_mapping_file_exists(self, file_set):
        """マッピングファイルの存在をチェック"""
        try:
            mapping_file_path = self._get_mapping_file_path(file_set)
            return os.path.exists(mapping_file_path)
        except:
            return False
    
    def _get_mapping_file_path(self, file_set):
        """マッピングファイルのパスを取得（UUID固定版）"""
        # 新しいUUID固定パス管理を優先
        if hasattr(file_set, 'mapping_file_path') and file_set.mapping_file_path:
            if os.path.exists(file_set.mapping_file_path):
                return file_set.mapping_file_path
        
        # TempFolderManagerから固定パスを取得
        if hasattr(file_set, 'uuid'):
            try:
                from ..core.temp_folder_manager import TempFolderManager
                temp_manager = TempFolderManager()
                stable_path = temp_manager.get_stable_mapping_file_path(file_set)
                if os.path.exists(stable_path):
                    return stable_path
            except Exception as e:
                logger.warning("TempFolderManagerアクセスエラー: %s", e)
        
        # 後方互換性：extended_configから取得を試行
        if hasattr(file_set, 'extended_config') and file_set.extended_config:
            mapping_file = file_set.extended_config.get('mapping_file')
            if mapping_file and os.path.exists(mapping_file):
                return mapping_file
        
        # 後方互換性：ファイルセット属性から取得を試行
        if hasattr(file_set, 'mapping_file') and file_set.mapping_file:
            if os.path.exists(file_set.mapping_file):
                return file_set.mapping_file
        
        # フォールバック：固定パスを返す（存在しない場合でも）
        if hasattr(file_set, 'uuid'):
            try:
                from ..core.temp_folder_manager import TempFolderManager
                temp_manager = TempFolderManager()
                return temp_manager.get_stable_mapping_file_path(file_set)
            except Exception as e:
                logger.warning("TempFolderManagerフォールバックエラー: %s", e)
        
        return None
    
    def _view_mapping_file(self, file_set):
        """マッピングファイルを表示"""
        try:
            mapping_file_path = self._get_mapping_file_path(file_set)
            if mapping_file_path and os.path.exists(mapping_file_path):
                # ファイルを外部プログラムで開く
                from classes.core.platform import open_path

                if not open_path(mapping_file_path):
                    raise RuntimeError("open_path failed")
            else:
                QMessageBox.warning(self, "エラー", "マッピングファイルが見つかりません。")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"マッピングファイルの表示に失敗しました: {str(e)}")
    
    def _update_mapping_file(self, file_set, *, show_completion_dialog=True):
        """マッピングファイルを更新（TempFolderManager統一版）"""
        try:
            # TempFolderManagerを使用してマッピングファイルを作成
            from ..core.temp_folder_manager import TempFolderManager
            
            temp_manager = TempFolderManager()
            
            # 既存の一時フォルダを確認
            temp_folder = None
            if hasattr(file_set, 'extended_config') and file_set.extended_config:
                temp_folder = file_set.extended_config.get('temp_folder')
            
            # 一時フォルダが存在しない場合は新規作成
            if not temp_folder or not os.path.exists(temp_folder):
                temp_folder, mapping_file = temp_manager.create_temp_folder_for_fileset(file_set)
                # ファイルセットに一時フォルダ情報を設定
                if not hasattr(file_set, 'extended_config'):
                    file_set.extended_config = {}
                file_set.extended_config['temp_folder'] = temp_folder
                file_set.extended_config['temp_created'] = True
                file_set.extended_config['mapping_file'] = mapping_file
                file_set.mapping_file = mapping_file
            else:
                # 既存の一時フォルダでマッピングファイルを更新
                temp_manager.temp_folders[file_set.id] = temp_folder
                
                if file_set.organize_method == PathOrganizeMethod.FLATTEN:
                    mapping_file = temp_manager._create_flatten_structure(file_set, temp_folder)
                else:
                    mapping_file = temp_manager._create_zip_structure(file_set, temp_folder)
                
                # ファイルセットのマッピングファイル情報を更新
                file_set.extended_config['mapping_file'] = mapping_file
                file_set.mapping_file = mapping_file
            
            # テーブル表示を更新
            self.refresh_data()
            if show_completion_dialog:
                QMessageBox.information(self, "完了", 
                    f"ファイルセット '{file_set.name}' のマッピングファイルを作成しました。\n"
                    f"パス: {mapping_file}")
            return mapping_file
            
        except Exception as e:
            logger.error("マッピングファイル更新エラー: %s", e)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "エラー", f"マッピングファイルの更新に失敗しました: {str(e)}")
            raise
    
    def _get_current_timestamp(self):
        """現在のタイムスタンプを取得"""
        import datetime
        return datetime.datetime.now().isoformat()


class DataTreeDialog(QDialog):
    """データツリー選択ダイアログ"""
    
    def __init__(self, file_items: List[FileItem], parent=None):
        super().__init__(parent)
        self.file_items = file_items
        self.selected_items = []
        self.setup_ui()
    
    def setup_ui(self):
        """UIセットアップ"""
        self.setWindowTitle("データツリー選択")
        self.setModal(True)
        # 最前面表示設定（マルチディスプレイ環境対応）
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(600, 500)
        
        layout = QVBoxLayout()
        
        # 説明ラベル
        info_label = QLabel("ファイルセットに含めるファイル・フォルダを選択してください")
        from classes.utils.label_style import apply_label_style
        apply_label_style(info_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
        layout.addWidget(info_label)
        
        # ファイルツリー
        self.file_tree = FileTreeWidget()
        # ダイアログ内では右クリックメニューを無効化
        self.file_tree.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.file_tree)
        
        # ファイルツリーにデータをロード
        if self.file_items:
            logger.debug("DataTreeDialog: %s個のファイルアイテムをロード", len(self.file_items))
            self.file_tree.load_file_tree(self.file_items)
        else:
            logger.warning("DataTreeDialog: ファイルアイテムが空です")
        
        # 選択情報
        self.selection_info = QLabel("選択されたアイテム: 0個")
        self.selection_info.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; padding: 5px;")
        layout.addWidget(self.selection_info)
        
        # ボタン
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def on_items_selected(self, items: List[FileItem]):
        """アイテム選択処理"""
        self.selected_items = items
        self.selection_info.setText(f"選択されたアイテム: {len(items)}個")
    
    def get_selected_items(self) -> List[FileItem]:
        """選択されたアイテムを取得"""
        return self.selected_items
    
    def get_selected_files(self) -> List[FileItem]:
        """選択されたファイルを取得（get_selected_itemsのエイリアス）"""
        # チェックボックスの状態から選択されたファイルを収集
        selected_files = []
        if hasattr(self.file_tree, 'checkbox_items'):
            for item_id, checkbox in self.file_tree.checkbox_items.items():
                if checkbox.isChecked():
                    # item_idからFileItemを探す
                    for file_item in self.file_items:
                        if id(file_item) == item_id or file_item in self.file_tree.file_items.values():
                            selected_files.append(file_item)
                            break
        return selected_files
    
    def update_selected_fileset_from_tree(self):
        """ファイルツリーの選択状態を選択されたファイルセットに反映（ダイアログ版）"""
        try:
            # 親ウィジェットのメソッドを呼び出し
            if hasattr(self.parent(), 'update_selected_fileset_from_tree'):
                self.parent().update_selected_fileset_from_tree()
            else:
                QMessageBox.information(self, "情報", "ファイルセット更新機能は現在利用できません。")
        except Exception as e:
            logger.error("ダイアログからのファイルセット更新エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"ファイルセット更新に失敗しました: {e}")


class BatchRegisterWidget(QWidget):
    """一括登録メインウィジェット"""
    
    def __init__(self, parent_controller, parent=None):
        super().__init__(parent)
        logger.debug("BatchRegisterWidget初期化開始")
        self.parent_controller = parent_controller
        self.file_set_manager = None
        self.batch_logic = BatchRegisterLogic(self)
        self.temp_folder_manager = TempFolderManager()  # 一時フォルダ管理
        self.datasets = []  # データセット一覧
        self._dataset_lookup: Dict[str, dict] = {}
        
        # ファイルセット復元処理中フラグ（自動設定適用を防ぐため）
        self._restoring_fileset = False
        
        # データセット存在検証キャッシュ（重複検証を防止）
        self._verified_datasets = set()

        # NOTE: タブごとのウィンドウサイズは DataRegisterTabWidget 側で管理する。
        # ここでトップレベルの geometry を保存/復元すると他タブへ影響が出るため、管理しない。
        self._batch_window_active = False
        self._batch_window_size_initialized = False
        self._saved_top_level_geometry = None
        self._saved_top_level_title = None
        
        # ベアラートークンを初期化時に設定
        self.bearer_token = None
        if hasattr(parent_controller, 'bearer_token'):
            self.bearer_token = parent_controller.bearer_token
            logger.debug("BatchRegisterWidget: parent_controllerからトークンを設定")
        
        # 既存の一時フォルダをクリーンアップ
        self.cleanup_temp_folders_on_init()
        
        self.setup_ui()
        self.connect_signals()
        self.load_initial_data()
        logger.debug("BatchRegisterWidget初期化完了")

        # splitter状態（左右比率）はウィジェット存続期間中に独立して保持する
        self._main_splitter = getattr(self, '_main_splitter', None)
        self._splitter_sizes: Optional[List[int]] = None
        self._splitter_initialized: bool = False

        # 右ペイン（ファイルセット一覧/詳細）の縦splitter初期比率
        self._fileset_splitter = getattr(self, '_fileset_splitter', None)
        self._fileset_splitter_initialized: bool = False

        # テーマ変更シグナル接続（動的再スタイル対応）
        try:
            from classes.theme import ThemeManager
            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception as e:
            logger.warning("BatchRegisterWidget: テーマ変更シグナル接続失敗: %s", e)

        DatasetLaunchManager.instance().register_receiver(
            "data_register_batch", self._apply_dataset_launch_payload
        )

    def showEvent(self, event):  # noqa: N802
        result = super().showEvent(event)
        # 初回表示時に splitter 初期レイアウトを決定（ファイルツリー列幅に合わせる）
        try:
            QTimer.singleShot(0, self._ensure_splitter_initialized)
        except Exception:
            pass
        # 右ペインの縦splitter（一覧:詳細 = 60:40）も初期化
        try:
            QTimer.singleShot(0, self._ensure_fileset_splitter_initialized)
        except Exception:
            pass
        return result

    def hideEvent(self, event):  # noqa: N802
        return super().hideEvent(event)
        
    def setup_ui(self):
        """UIセットアップ"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 一括登録ウィジェットスタイル適用（動的）
        self.setStyleSheet(get_batch_register_style())
        
        # スプリッターでエリア分割
        splitter = QSplitter(Qt.Horizontal)
        self._main_splitter = splitter
        
        # 左側：ファイル操作エリア
        left_widget = self.create_file_operations_area()
        splitter.addWidget(left_widget)
        
        # 右側：ファイルセット管理エリア
        right_widget = self.create_fileset_management_area()  
        splitter.addWidget(right_widget)
        
        # スプリッター比率設定（左:右 = 50:50）
        splitter.setSizes([500, 500])
        
        # ペインが隠れることを防ぐ最小サイズ設定
        left_widget.setMinimumWidth(300)
        right_widget.setMinimumWidth(300)
        
        # ハンドルを見えるようにする
        splitter.setHandleWidth(5)
        splitter.setChildrenCollapsible(False)  # ペインが完全に折りたたまれることを防ぐ

        try:
            splitter.splitterMoved.connect(self._on_splitter_moved)
        except Exception:
            pass
        
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)

    def _on_splitter_moved(self, *_args) -> None:
        try:
            if self._main_splitter is not None:
                self._splitter_sizes = list(self._main_splitter.sizes())
        except Exception:
            pass

    def _compute_left_pane_min_width(self) -> int:
        """左ペインの最小幅（ファイルツリーに水平スクロールが出ない幅）を推定する。"""
        tree = getattr(self, 'file_tree', None)
        if tree is None:
            return 300

        try:
            header_len = int(tree.header().length())
        except Exception:
            header_len = 0

        extra = 0
        try:
            extra += int(tree.frameWidth()) * 2
        except Exception:
            pass
        try:
            sb = tree.verticalScrollBar()
            extra += int(sb.sizeHint().width())
        except Exception:
            # だいたいのスクロールバー幅
            extra += 18

        # GroupBox / レイアウトの余白分を少し上乗せ
        extra += 48

        return max(300, header_len + extra)

    def _ensure_splitter_initialized(self) -> None:
        """初回表示時に splitter の左右幅を適切に設定する。"""
        try:
            splitter = getattr(self, '_main_splitter', None)
            if splitter is None:
                return
            # 破棄後に Qt の queued call が走ることがあるため、参照可能か軽く確認
            _ = splitter.count()
        except RuntimeError:
            return
        except Exception:
            splitter = getattr(self, '_main_splitter', None)
            if splitter is None:
                return

        # 既にユーザー操作で sizes を保持している場合はそれを優先
        if isinstance(self._splitter_sizes, list) and self._splitter_sizes:
            try:
                splitter.setSizes(self._splitter_sizes)
            except RuntimeError:
                return
            except Exception:
                pass
            return

        if self._splitter_initialized:
            return
        self._splitter_initialized = True

        left_min = self._compute_left_pane_min_width()

        try:
            left_widget = splitter.widget(0)
            if left_widget is not None:
                left_widget.setMinimumWidth(left_min)
        except Exception:
            pass

        try:
            right_widget = splitter.widget(1)
            right_min = int(getattr(right_widget, 'minimumWidth', lambda: 300)()) if right_widget is not None else 300
        except Exception:
            right_min = 300

        total = 0
        try:
            total = int(splitter.width())
        except Exception:
            total = 0

        if total <= 0:
            try:
                splitter.setSizes([left_min, max(300, right_min)])
                self._splitter_sizes = list(splitter.sizes())
            except RuntimeError:
                return
            except Exception:
                pass
            return

        left_width = min(max(left_min, 300), max(300, total - right_min))
        right_width = max(right_min, total - left_width)
        try:
            splitter.setSizes([left_width, right_width])
            self._splitter_sizes = list(splitter.sizes())
        except RuntimeError:
            return
        except Exception:
            pass

    def _ensure_fileset_splitter_initialized(self) -> None:
        """初回表示時に右ペインの縦splitterを初期化する。

        一覧領域は「テーブルのヘッダ + データ4行」の高さを優先し、
        収まらない場合のみ下側（詳細）を確保しつつ縮める。
        """
        if self._fileset_splitter_initialized:
            return

        splitter = getattr(self, '_fileset_splitter', None)
        if splitter is None:
            return

        try:
            _ = splitter.count()
        except RuntimeError:
            return
        except Exception:
            pass

        try:
            sizes = list(splitter.sizes())
        except Exception:
            sizes = []

        total = 0
        try:
            total = int(sum(sizes)) if sizes else int(splitter.height())
        except Exception:
            total = 0

        if total <= 0:
            total = 1000

        desired_top = 0
        try:
            group = getattr(self, '_fileset_list_group', None)
            if group is not None:
                desired_top = int(group.sizeHint().height())
        except Exception:
            desired_top = 0

        if desired_top <= 0:
            desired_top = int(total * 0.60)

        bottom_min = 220
        top = min(desired_top, max(1, total - bottom_min))
        bottom = max(1, total - top)

        try:
            splitter.setSizes([top, bottom])
            self._fileset_splitter_initialized = True
        except RuntimeError:
            return
        except Exception:
            pass

        # 一覧領域を「ヘッダ + 4行」相当に固定する（初回レイアウト確定後）
        try:
            QTimer.singleShot(0, self._apply_fileset_list_group_fixed_height)
        except Exception:
            pass

    def _apply_fileset_list_group_fixed_height(self) -> None:
        """ファイルセット一覧グループの高さを sizeHint 基準で固定する。"""
        try:
            group = getattr(self, '_fileset_list_group', None)
            if group is None:
                return
            if group.layout() is None:
                return
            h = int(group.sizeHint().height())
            if h > 0:
                group.setFixedHeight(h)
        except Exception:
            pass

    def refresh_theme(self):
        """テーマ変更時にスタイルを再適用"""
        try:
            # ルートウィジェット
            self.setStyleSheet(get_batch_register_style())
            # ファイルツリー
            if hasattr(self, 'file_tree') and self.file_tree:
                self.file_tree.setStyleSheet(get_file_tree_style())
            # ファイルセットテーブル
            if hasattr(self, 'fileset_table') and self.fileset_table:
                if hasattr(self.fileset_table, 'apply_theme_style'):
                    self.fileset_table.apply_theme_style()
                else:
                    self.fileset_table.setStyleSheet(get_fileset_table_style())

            # 一覧領域の固定高さも再適用（テーマ変更でsizeHintが変わることがある）
            try:
                QTimer.singleShot(0, self._apply_fileset_list_group_fixed_height)
            except Exception:
                pass
            # 登録実行エリア（execution_group）
            if hasattr(self, 'execution_group') and self.execution_group:
                self.execution_group.setStyleSheet(f"""
                QGroupBox {{
                    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                    border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                    border-radius: 8px;
                    margin: 5px;
                    padding-top: 15px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 5px;
                    color: {get_color(ThemeKey.GROUPBOX_TITLE_TEXT)};
                }}
                """)
            # 大量項目を含むQComboBoxの高速化最適化
            try:
                from classes.utils.theme_perf_util import optimize_combo_boxes
                optimize_combo_boxes(self, threshold=500)
            except Exception:
                pass
            self.update()
            logger.debug("BatchRegisterWidget: 動的スタイル再適用完了")
        except Exception as e:
            logger.error("BatchRegisterWidget: テーマ更新エラー: %s", e)
    
    def create_file_operations_area(self) -> QWidget:
        """ファイル操作エリア作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # ベースディレクトリ選択
        dir_group = QGroupBox("ベースディレクトリ")
        dir_layout = QHBoxLayout()
        
        self.dir_path_edit = QLineEdit()
        self.dir_path_edit.setPlaceholderText("ベースディレクトリを選択...")
        dir_layout.addWidget(self.dir_path_edit)
        
        browse_btn = QPushButton("参照...")
        browse_btn.clicked.connect(self.browse_directory)
        dir_layout.addWidget(browse_btn)
        
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # ファイルツリー表示
        tree_group = QGroupBox("ファイルツリー")
        tree_layout = QVBoxLayout()
        
        # ツールバー
        toolbar_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("再読み込み")
        refresh_btn.clicked.connect(self.refresh_file_tree_with_warning)
        refresh_btn.setToolTip("ファイルツリーを再読み込みします（「含む」状態はリセットされます）")
        toolbar_layout.addWidget(refresh_btn)
        
        toolbar_layout.addStretch()
        
        expand_btn = QPushButton("全て展開")
        expand_btn.clicked.connect(self.expand_all)
        toolbar_layout.addWidget(expand_btn)
        
        collapse_btn = QPushButton("全て折りたたみ")
        collapse_btn.clicked.connect(self.collapse_all)
        toolbar_layout.addWidget(collapse_btn)
        
        # 選択操作ボタン
        toolbar_layout.addStretch()
        
        select_all_btn = QPushButton("全選択")
        select_all_btn.clicked.connect(self.select_all_files)
        toolbar_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("全解除")
        deselect_all_btn.clicked.connect(self.deselect_all_files)
        toolbar_layout.addWidget(deselect_all_btn)
        
        tree_layout.addLayout(toolbar_layout)
        
        # ファイルツリー
        self.file_tree = FileTreeWidget()
        tree_layout.addWidget(self.file_tree)
        
        tree_group.setLayout(tree_layout)
        layout.addWidget(tree_group)
        
        # ファイルセット作成（縦レイアウトで容量制限付き）
        auto_group = QGroupBox("ファイルセット作成")
        auto_main_layout = QVBoxLayout()
        
        # 容量制限設定エリア
        capacity_layout = QHBoxLayout()
        
        self.capacity_enable_cb = QCheckBox("容量制限を有効にする")
        self.capacity_enable_cb.setToolTip("ファイルセットあたりの最大容量を設定します")
        capacity_layout.addWidget(self.capacity_enable_cb)
        
        capacity_layout.addWidget(QLabel("最大容量:"))
        
        self.capacity_spinbox = QDoubleSpinBox()
        self.capacity_spinbox.setMinimum(0.1)
        self.capacity_spinbox.setMaximum(1000.0)
        self.capacity_spinbox.setValue(10.0)
        self.capacity_spinbox.setSuffix(" GB")
        self.capacity_spinbox.setDecimals(1)
        self.capacity_spinbox.setEnabled(False)
        capacity_layout.addWidget(self.capacity_spinbox)
        
        self.capacity_unit_combo = QComboBox()
        self.capacity_unit_combo.addItems(["GB", "MB"])
        self.capacity_unit_combo.setEnabled(False)
        capacity_layout.addWidget(self.capacity_unit_combo)
        
        # 容量制限チェックボックスの状態変化で他のウィジェットを有効/無効化
        self.capacity_enable_cb.toggled.connect(self._on_capacity_enable_toggled)
        
        # 単位変更時の処理
        self.capacity_unit_combo.currentTextChanged.connect(self._on_capacity_unit_changed)
        
        capacity_layout.addStretch()
        auto_main_layout.addLayout(capacity_layout)
        
        # 作成ボタンエリア（横一列表示）
        buttons_layout = QHBoxLayout()
        
        auto_all_btn = QPushButton("全体")
        auto_all_btn.setToolTip("既存のファイルセットをリセットして、全体を1つのファイルセットとして作成します")
        auto_all_btn.clicked.connect(self.auto_assign_all_as_one_with_confirm)
        buttons_layout.addWidget(auto_all_btn)
        
        auto_top_btn = QPushButton("最上位フォルダ")
        auto_top_btn.setToolTip("既存のファイルセットをリセットして、最上位フォルダごとにファイルセットを作成します")
        auto_top_btn.clicked.connect(self.auto_assign_by_top_dirs_with_confirm)
        buttons_layout.addWidget(auto_top_btn)
        
        auto_all_dirs_btn = QPushButton("個別フォルダ")
        auto_all_dirs_btn.setToolTip("既存のファイルセットをリセットして、全フォルダを個別にファイルセットとして作成します")
        auto_all_dirs_btn.clicked.connect(self.auto_assign_all_dirs_with_confirm)
        buttons_layout.addWidget(auto_all_dirs_btn)

        clear_all_btn = QPushButton("全て削除")
        clear_all_btn.setToolTip("全てのファイルセットを削除します")
        clear_all_btn.clicked.connect(self.clear_all_filesets)
        buttons_layout.addWidget(clear_all_btn)
        
        auto_main_layout.addLayout(buttons_layout)
        
        auto_group.setLayout(auto_main_layout)
        layout.addWidget(auto_group)
        
        # プレビュー＆一括登録実行エリアを左側ペインに追加
        execution_area = self.create_execution_area()
        layout.addWidget(execution_area)
        
        widget.setLayout(layout)
        return widget
    
    def create_fileset_management_area(self) -> QWidget:
        """ファイルセット管理エリア作成"""
        widget = QWidget()
        layout = QVBoxLayout()

        # 一覧(上)と詳細(下)を縦分割して、一覧を約60%確保
        v_splitter = QSplitter(Qt.Vertical)
        self._fileset_splitter = v_splitter
        v_splitter.setChildrenCollapsible(False)
        v_splitter.setHandleWidth(5)
        
        # ファイルセット一覧
        fileset_group = QGroupBox("ファイルセット一覧")
        self._fileset_list_group = fileset_group
        fileset_layout = QVBoxLayout()
        
        # ファイルセットテーブル
        self.fileset_table = FileSetTableWidget()
        # 一覧は「ヘッダ + データ4行」の高さに固定し、スクロールで全件閲覧
        try:
            self.fileset_table.set_compact_view_rows(4)
            self.fileset_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            # スクロールバーの表示ポリシー（縦は常時表示）
            self.fileset_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            self.fileset_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        except Exception:
            pass
        self.fileset_table.set_file_set_manager(self.file_set_manager)  # file_set_managerを設定
        fileset_layout.addWidget(self.fileset_table)
        
        fileset_group.setLayout(fileset_layout)
        # グループ自体はテーブル高さに追従（一覧領域を固定する）
        try:
            fileset_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            fileset_group.setMaximumHeight(fileset_group.sizeHint().height())
        except Exception:
            pass
        v_splitter.addWidget(fileset_group)
        
        # ファイルセット詳細・設定
        detail_group = QGroupBox("選択ファイルセット設定")
        detail_layout = QVBoxLayout()
        
        # 上部に適用ボタンを配置（色付け）
        button_layout = QHBoxLayout()
        
        # 適用ボタン（旧設定保存ボタン）
        save_btn = QPushButton("適用")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
        """)
        save_btn.setToolTip("現在の設定を選択されたファイルセットに適用します")
        save_btn.clicked.connect(self.save_fileset_config)
        # button_layout.addWidget(save_btn)
        
        apply_all_btn = QPushButton("全ファイルセットに適用")
        apply_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        apply_all_btn.setToolTip("現在の設定を全てのファイルセットに適用します")
        apply_all_btn.clicked.connect(self.apply_to_all_filesets)
        button_layout.addWidget(apply_all_btn)
        
        apply_selected_btn = QPushButton("選択適用")
        apply_selected_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
            }}
        """)
        apply_selected_btn.setToolTip("現在の設定を選択されたファイルセットに適用します")
        apply_selected_btn.clicked.connect(self.apply_to_selected_filesets)
        button_layout.addWidget(apply_selected_btn)
        
        self.target_fileset_combo = QComboBox()
        self.target_fileset_combo.setToolTip("適用対象のファイルセットを選択")
        self.target_fileset_combo.setMinimumWidth(150)
        button_layout.addWidget(self.target_fileset_combo)
        
        detail_layout.addLayout(button_layout)
        
        # ファイルセット基本情報を直接配置（フィールドセットなし）
        basic_layout = QHBoxLayout()
        
        basic_layout.addWidget(QLabel("ファイルセット名:"))
        self.fileset_name_edit = QLineEdit()
        basic_layout.addWidget(self.fileset_name_edit)
        
        basic_layout.addWidget(QLabel("整理方法:"))
        self.organize_method_combo = QComboBox()
        self.organize_method_combo.addItems(["フラット化", "ZIP化"])
        basic_layout.addWidget(self.organize_method_combo)
        
        detail_layout.addLayout(basic_layout)
        
        # データセット選択を直接配置（フィールドセットなし）
        dataset_layout = QHBoxLayout()
        #dataset_layout.addWidget(QLabel("データセット:"))
        
        # 検索可能なデータセット選択ウィジェットを作成
        try:
            from classes.data_entry.util.data_entry_filter_checkbox import create_checkbox_filter_dropdown
            self.dataset_dropdown_widget = create_checkbox_filter_dropdown(self)
            self.dataset_dropdown_widget.setMinimumWidth(400)
            dataset_layout.addWidget(self.dataset_dropdown_widget)
            
            # 実際のコンボボックスを取得
            if hasattr(self.dataset_dropdown_widget, 'dataset_dropdown'):
                self.dataset_combo = self.dataset_dropdown_widget.dataset_dropdown
            else:
                # フォールバック
                raise ImportError("dataset_dropdown not found")
                
        except ImportError:
            # フォールバック：基本コンボボックス + 検索機能
            from classes.dataset.util.dataset_dropdown_util import create_dataset_dropdown_with_user
            from config.common import DATASET_JSON_PATH, INFO_JSON_PATH
            
            self.dataset_dropdown_widget = create_dataset_dropdown_with_user(
                DATASET_JSON_PATH, INFO_JSON_PATH, self
            )
            dataset_layout.addWidget(self.dataset_dropdown_widget)
            
            # 実際のコンボボックスを取得
            if hasattr(self.dataset_dropdown_widget, 'dataset_dropdown'):
                self.dataset_combo = self.dataset_dropdown_widget.dataset_dropdown
            else:
                # 最終フォールバック
                self.dataset_combo = QComboBox()
                self.dataset_combo.setEditable(True)
                self.dataset_combo.setMinimumWidth(400)
                self.dataset_combo.addItem("")
                self.dataset_combo.setCurrentIndex(0)
                self.dataset_combo.lineEdit().setPlaceholderText("リストから選択、またはキーワードで検索して選択してください")
                dataset_layout.addWidget(self.dataset_combo)
        except Exception as e:
            logger.warning("データセット選択ウィジェット作成失敗: %s", e)
            # フォールバック: 通常のコンボボックス
            self.dataset_combo = QComboBox()
            self.dataset_combo.setEditable(True)
            self.dataset_combo.setMinimumWidth(400)
            self.dataset_combo.addItem("")
            self.dataset_combo.setCurrentIndex(0)
            self.dataset_combo.lineEdit().setPlaceholderText("リストから選択、またはキーワードで検索して選択してください")
            dataset_layout.addWidget(self.dataset_combo)
        
        detail_layout.addLayout(dataset_layout)

        launch_controls_widget = QWidget()
        launch_controls_layout = QHBoxLayout()
        launch_controls_layout.setContentsMargins(0, 0, 0, 0)
        launch_label = QLabel("他機能連携:")
        launch_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;")
        launch_controls_layout.addWidget(launch_label)

        from classes.utils.launch_ui_styles import get_launch_button_style

        launch_button_style = get_launch_button_style()

        launch_targets = [
            ("data_fetch2", "データ取得2"),
            ("dataset_edit", "データセット修正"),
            ("dataset_dataentry", "データエントリー"),
        ]

        self._launch_buttons = []

        def _has_dataset_selection() -> bool:
            return bool(self.get_selected_dataset_id())

        def _update_launch_buttons_state() -> None:
            enabled = _has_dataset_selection()
            for button in self._launch_buttons:
                button.setEnabled(enabled)

        self._update_launch_buttons_state = _update_launch_buttons_state

        for target_key, caption in launch_targets:
            btn = QPushButton(caption)
            btn.setStyleSheet(launch_button_style)
            btn.clicked.connect(lambda _=None, key=target_key: self._handle_dataset_launch(key))
            launch_controls_layout.addWidget(btn)
            self._launch_buttons.append(btn)

        def _launch_to_subgroup_edit() -> None:
            dataset_id = str(self.get_selected_dataset_id() or "").strip()
            if not dataset_id:
                QMessageBox.warning(self, "データセット未選択", "連携するデータセットを選択してください。")
                return
            try:
                from classes.utils.subgroup_launch_helper import launch_to_subgroup_edit

                launch_to_subgroup_edit(
                    owner_widget=self,
                    dataset_id=dataset_id,
                    raw_dataset=None,
                    source_name="data_register_batch",
                )
            except Exception:
                logger.debug("batch_register: launch_to_subgroup_edit failed", exc_info=True)

        subgroup_btn = QPushButton("サブグループ閲覧・修正")
        subgroup_btn.setStyleSheet(launch_button_style)
        subgroup_btn.clicked.connect(_launch_to_subgroup_edit)
        launch_controls_layout.addWidget(subgroup_btn)
        self._launch_buttons.append(subgroup_btn)

        # テーマ切替時に「他機能連携」の個別styleSheetを再適用（更新漏れ対策）
        try:
            from classes.utils.launch_ui_styles import apply_launch_controls_theme, bind_launch_controls_to_theme

            apply_launch_controls_theme(launch_label, self._launch_buttons)
            bind_launch_controls_to_theme(launch_label, self._launch_buttons)
        except Exception:
            pass

        launch_controls_layout.addStretch()
        launch_controls_widget.setLayout(launch_controls_layout)
        detail_layout.addWidget(launch_controls_widget)

        if self.dataset_combo is not None:
            try:
                self.dataset_combo.currentIndexChanged.connect(lambda *_: self._update_launch_buttons_state())
            except Exception:
                logger.debug("dataset_combo currentIndexChanged connection failed", exc_info=True)
        self._update_launch_buttons_state()
        
        # --- テンプレート対応拡張子表示ラベル ---
        self.batch_template_format_label = QLabel("データセットを選択してください")
        self.batch_template_format_label.setWordWrap(True)
        self.batch_template_format_label.setStyleSheet(
            f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
            f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
        )
        detail_layout.addWidget(self.batch_template_format_label)
        
        # 検証用バリデータ
        self.batch_validator = TemplateFormatValidator()
        self.batch_current_template_id = None
        
        # スクロールエリアでラップ
        scroll_area = QScrollArea()
        self.scroll_widget = QWidget()  # クラス属性として保存
        scroll_layout = QVBoxLayout()

        summary_style = (
            f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
            f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
        )
        
        # 基本情報
        data_group = QGroupBox("基本情報")
        data_layout = QGridLayout()
        
        data_layout.addWidget(QLabel("データ名:"), 0, 0)
        self.data_name_edit = QLineEdit()
        data_layout.addWidget(self.data_name_edit, 0, 1)
        
        data_layout.addWidget(QLabel("データ説明:"), 1, 0)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(60)
        data_layout.addWidget(self.description_edit, 1, 1)
        
        data_layout.addWidget(QLabel("実験ID:"), 2, 0)
        self.experiment_id_edit = QLineEdit()
        self.experiment_id_edit.setPlaceholderText("実験IDを入力（半角英数のみ）...")
        data_layout.addWidget(self.experiment_id_edit, 2, 1)
        
        data_layout.addWidget(QLabel("参考URL:"), 3, 0)
        self.reference_url_edit = QLineEdit()
        data_layout.addWidget(self.reference_url_edit, 3, 1)
        
        data_layout.addWidget(QLabel("タグ:"), 4, 0)
        self.tags_edit = QLineEdit()
        data_layout.addWidget(self.tags_edit, 4, 1)
        
        data_group.setLayout(data_layout)
        basic_toggle = ToggleSectionWidget("基本情報", self.scroll_widget, default_mode="summary")
        basic_summary = QLabel("基本情報は『入力』に切り替えて編集できます。", basic_toggle)
        basic_summary.setWordWrap(True)
        basic_summary.setStyleSheet(summary_style)

        def _refresh_basic_summary() -> None:
            parts = []
            try:
                v = (self.data_name_edit.text() or '').strip()
                if v:
                    parts.append(f"データ名: {v}")
            except Exception:
                pass
            try:
                v = (self.experiment_id_edit.text() or '').strip()
                if v:
                    parts.append(f"実験ID: {v}")
            except Exception:
                pass
            try:
                v = (self.reference_url_edit.text() or '').strip()
                if v:
                    parts.append(f"参考URL: {v}")
            except Exception:
                pass
            try:
                v = (self.tags_edit.text() or '').strip()
                if v:
                    parts.append(f"タグ: {v}")
            except Exception:
                pass
            try:
                v = (self.description_edit.toPlainText() or '').strip()
                if v:
                    preview = v.replace("\n", " ")
                    if len(preview) > 80:
                        preview = preview[:77] + "..."
                    parts.append(f"データ説明: {preview}")
            except Exception:
                pass

            basic_summary.setText("\n".join(parts) if parts else "基本情報は『入力』に切り替えて編集できます。")

        setattr(basic_summary, 'refresh', _refresh_basic_summary)
        try:
            self.data_name_edit.textChanged.connect(lambda *_: _refresh_basic_summary())
            self.experiment_id_edit.textChanged.connect(lambda *_: _refresh_basic_summary())
            self.reference_url_edit.textChanged.connect(lambda *_: _refresh_basic_summary())
            self.tags_edit.textChanged.connect(lambda *_: _refresh_basic_summary())
            self.description_edit.textChanged.connect(lambda *_: _refresh_basic_summary())
        except Exception:
            pass

        basic_toggle.set_summary_widget(basic_summary)
        basic_toggle.set_edit_widget(data_group)
        scroll_layout.addWidget(basic_toggle)
        
        # 試料情報（統合フォーム）
        sample_group = QGroupBox("試料情報")
        sample_layout = QGridLayout()
        
        sample_layout.addWidget(QLabel("試料選択:"), 0, 0)
        self.sample_id_combo = QComboBox()
        self.sample_id_combo.setEditable(True)
        self.sample_id_combo.setInsertPolicy(QComboBox.NoInsert)
        # 選択肢に「新規作成」と「前回と同じ」を追加
        self.sample_id_combo.addItems(["新規作成", "前回と同じ"])
        self.sample_id_combo.lineEdit().setPlaceholderText("試料を選択または検索...")
        sample_layout.addWidget(self.sample_id_combo, 0, 1)
        
        sample_layout.addWidget(QLabel("試料名:"), 1, 0)
        self.sample_name_edit = QLineEdit()
        sample_layout.addWidget(self.sample_name_edit, 1, 1)
        
        sample_layout.addWidget(QLabel("試料説明:"), 2, 0)
        self.sample_description_edit = QTextEdit()
        self.sample_description_edit.setMaximumHeight(60)
        sample_layout.addWidget(self.sample_description_edit, 2, 1)
        
        sample_layout.addWidget(QLabel("試料組成:"), 3, 0)
        self.sample_composition_edit = QLineEdit()
        sample_layout.addWidget(self.sample_composition_edit, 3, 1)
        
        sample_group.setLayout(sample_layout)
        sample_toggle = ToggleSectionWidget("試料情報", self.scroll_widget, default_mode="summary")
        sample_summary = QLabel("試料情報は『入力』に切り替えて編集できます。", sample_toggle)
        sample_summary.setWordWrap(True)
        sample_summary.setStyleSheet(summary_style)

        def _refresh_sample_summary() -> None:
            parts = []
            try:
                parts.append(f"試料選択: {self.sample_id_combo.currentText()}")
            except Exception:
                pass
            try:
                v = (self.sample_name_edit.text() or '').strip()
                if v:
                    parts.append(f"試料名: {v}")
            except Exception:
                pass
            try:
                v = (self.sample_composition_edit.text() or '').strip()
                if v:
                    parts.append(f"試料組成: {v}")
            except Exception:
                pass
            try:
                v = (self.sample_description_edit.toPlainText() or '').strip()
                if v:
                    preview = v.replace("\n", " ")
                    if len(preview) > 80:
                        preview = preview[:77] + "..."
                    parts.append(f"試料説明: {preview}")
            except Exception:
                pass

            sample_summary.setText("\n".join(parts) if parts else "試料情報は『入力』に切り替えて編集できます。")

        setattr(sample_summary, 'refresh', _refresh_sample_summary)
        try:
            self.sample_id_combo.currentIndexChanged.connect(lambda *_: _refresh_sample_summary())
            self.sample_name_edit.textChanged.connect(lambda *_: _refresh_sample_summary())
            self.sample_composition_edit.textChanged.connect(lambda *_: _refresh_sample_summary())
            self.sample_description_edit.textChanged.connect(lambda *_: _refresh_sample_summary())
        except Exception:
            pass

        sample_toggle.set_summary_widget(sample_summary)
        sample_toggle.set_edit_widget(sample_group)
        scroll_layout.addWidget(sample_toggle)
        
        # 廃止されたsample_mode_comboの参照を削除（sample_id_comboで統合）
        self.sample_mode_combo = self.sample_id_combo  # 互換性維持
        
        # 固有情報（インボイススキーマ対応）
        schema_toggle = ToggleSectionWidget("固有情報", self.scroll_widget, default_mode="summary")
        self._schema_toggle = schema_toggle
        self._current_invoice_schema_path = None

        schema_summary = QLabel("固有情報は『入力』に切り替えて編集できます。", schema_toggle)
        schema_summary.setWordWrap(True)
        schema_summary.setStyleSheet(summary_style)

        def _refresh_schema_summary() -> None:
            form = getattr(self, 'invoice_schema_form', None)
            key_to_widget = getattr(form, '_schema_key_to_widget', None) if form is not None else None
            if not isinstance(key_to_widget, dict) or not key_to_widget:
                schema_summary.setText("入力項目なし")
                return

            labels = {}
            try:
                p = getattr(self, '_current_invoice_schema_path', None)
                if p:
                    with open(p, 'r', encoding='utf-8') as f:
                        schema_json = json.load(f)
                    custom = (schema_json.get('properties', {}) or {}).get('custom') or {}
                    props = (custom.get('properties', {}) or {}) if isinstance(custom, dict) else {}
                    if isinstance(props, dict):
                        for k, prop in props.items():
                            if isinstance(prop, dict):
                                label = (prop.get('label', {}) or {}).get('ja')
                                labels[k] = label or k
            except Exception:
                labels = {}

            filled_items = []
            for k, w in key_to_widget.items():
                try:
                    if hasattr(w, 'currentText'):
                        v = (w.currentText() or '').strip()
                    elif hasattr(w, 'text'):
                        v = (w.text() or '').strip()
                    else:
                        v = ''
                except Exception:
                    v = ''
                if v:
                    filled_items.append((labels.get(k) or k, v))

            total = len(key_to_widget)
            filled = len(filled_items)
            lines = [f"入力済み: {filled}/{total}"]
            for label, value in filled_items[:10]:
                lines.append(f"- {label}: {value}")
            if len(filled_items) > 10:
                lines.append(f"… 他 {len(filled_items) - 10} 件")
            schema_summary.setText("\n".join(lines))

        self._refresh_schema_summary = _refresh_schema_summary
        setattr(schema_summary, 'refresh', _refresh_schema_summary)

        schema_edit_widget = QWidget(self.scroll_widget)
        self.schema_form_layout = QVBoxLayout(schema_edit_widget)
        self.schema_form_layout.setContentsMargins(10, 10, 10, 10)
        
        # 初期状態のメッセージ
        self.schema_placeholder_label = QLabel("データセット選択後に固有情報入力フォームが表示されます")
        self.schema_placeholder_label.setAlignment(Qt.AlignCenter)
        self.schema_placeholder_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-style: italic; padding: 20px;")
        self.schema_form_layout.addWidget(self.schema_placeholder_label)

        schema_toggle.set_summary_widget(schema_summary)
        schema_toggle.set_edit_widget(schema_edit_widget)
        try:
            toggle_button = schema_toggle.findChild(QPushButton, "toggleButton")
            if toggle_button is not None:
                toggle_button.clicked.connect(lambda *_: self._sync_schema_form_visibility())
        except Exception:
            logger.debug("schema toggle visibility sync connection failed", exc_info=True)
        scroll_layout.addWidget(schema_toggle)
        self._sync_schema_form_visibility()
        
        self.scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(self.scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        detail_layout.addWidget(scroll_area)
        
        detail_group.setLayout(detail_layout)
        try:
            detail_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        v_splitter.addWidget(detail_group)

        # 初期比率（一覧:詳細 = 60:40）
        try:
            v_splitter.setStretchFactor(0, 3)
            v_splitter.setStretchFactor(1, 2)
            v_splitter.setSizes([600, 400])
        except Exception:
            pass

        layout.addWidget(v_splitter)
        
        widget.setLayout(layout)
        return widget
    
    def create_execution_area(self) -> QWidget:
        """登録実行ペイン作成"""
        # グループボックスでレジェンドを追加
        widget = QGroupBox("登録実行")
        widget.setStyleSheet(f"""
            QGroupBox {{
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 8px;
                margin: 5px;
                padding-top: 15px;
                font-weight: bold;
                font-size: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: {get_color(ThemeKey.GROUPBOX_TITLE_TEXT)};
            }}
        """)
        # 参照保持し refresh_theme で再スタイル
        self.execution_group = widget

        
        layout = QHBoxLayout()
        
        # 左側：サマリー情報
        summary_layout = QVBoxLayout()
        
        self.summary_label = QLabel("ファイルセット: 0個、総ファイル数: 0、総サイズ: 0 B")
        from classes.utils.label_style import apply_label_style
        apply_label_style(self.summary_label, get_color(ThemeKey.TEXT_SECONDARY), bold=True)
        summary_layout.addWidget(self.summary_label)
        
        self.estimate_label = QLabel("推定処理時間: 計算中...")
        self.estimate_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        summary_layout.addWidget(self.estimate_label)
        
        # ステータスラベル追加
        self.status_label = QLabel("一括登録の準備ができました")
        self.status_label.setStyleSheet(f"color: {get_color(ThemeKey.STATUS_SUCCESS)}; font-style: italic;")
        summary_layout.addWidget(self.status_label)
        
        layout.addLayout(summary_layout)
        
        layout.addStretch()
        
        # 右側：実行ボタン
        button_layout = QVBoxLayout()
        
        preview_btn = QPushButton("プレビュー")
        preview_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
        """)
        preview_btn.clicked.connect(self.preview_batch_register)
        button_layout.addWidget(preview_btn)
        
        # 並列アップロード数（「一括登録実行」ボタンの左側）
        self.parallel_upload_spinbox = QSpinBox(self)
        self.parallel_upload_spinbox.setRange(1, 20)
        self.parallel_upload_spinbox.setValue(5)
        self.parallel_upload_spinbox.setToolTip("uploads へのアップロード並列数（既定: 5）")
        parallel_label = QLabel("並列", self)
        parallel_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")

        execute_btn = QPushButton("一括登録実行")
        execute_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 12px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        execute_btn.clicked.connect(self.execute_batch_register)

        execute_row = QHBoxLayout()
        execute_row.addWidget(parallel_label)
        execute_row.addWidget(self.parallel_upload_spinbox)
        execute_row.addWidget(execute_btn)
        button_layout.addLayout(execute_row)
        
        # 一時フォルダ削除ボタンを追加
        cleanup_btn = QPushButton("一時フォルダ削除")
        cleanup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                margin-top: 10px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
        """)
        cleanup_btn.clicked.connect(self.cleanup_temp_folders)
        button_layout.addWidget(cleanup_btn)
        
        layout.addLayout(button_layout)
        
        widget.setLayout(layout)
        return widget
    
    def _ensure_temp_folder_and_mapping(self, file_set):
        """ファイルセットの一時フォルダとマッピングファイルが存在することを確認・作成"""
        pass  # この機能は_ensure_temp_folder_and_mapping_continueに移動
    
    def _get_bearer_token(self) -> Optional[str]:
        """ベアラートークンを取得する統一メソッド（親ウィジェット継承対応）"""
        bearer_token = None
        
        # 1. 自分のプロパティから取得を試行
        if hasattr(self, 'bearer_token') and self.bearer_token:
            bearer_token = self.bearer_token
            logger.debug("_get_bearer_token: 自分のプロパティから取得")
        
        # 2. 親ウィジェットから取得を試行
        if not bearer_token:
            parent_widget = self.parent()
            while parent_widget:
                if hasattr(parent_widget, 'bearer_token') and parent_widget.bearer_token:
                    bearer_token = parent_widget.bearer_token
                    logger.debug("_get_bearer_token: 親ウィジェット %s から取得", type(parent_widget).__name__)
                    break
                parent_widget = parent_widget.parent()
        
        # 3. AppConfigManagerから取得を試行
        if not bearer_token:
            try:
                from classes.managers.app_config_manager import get_config_manager
                app_config = get_config_manager()
                bearer_token = app_config.get('bearer_token')
                if bearer_token:
                    logger.debug("_get_bearer_token: AppConfigManagerから取得")
            except Exception as e:
                logger.warning("_get_bearer_token: AppConfigManagerからの取得に失敗: %s", e)
        
        # 4. 親コントローラから取得を試行
        if not bearer_token and hasattr(self, 'parent_controller'):
            if hasattr(self.parent_controller, 'bearer_token') and self.parent_controller.bearer_token:
                bearer_token = self.parent_controller.bearer_token
                logger.debug("_get_bearer_token: parent_controllerから取得")
        
        if not bearer_token:
            logger.warning("_get_bearer_token: ベアラートークンが見つかりませんでした")
        else:
            logger.debug("_get_bearer_token: トークン取得成功 (長さ: %s)", len(bearer_token))
        
        return bearer_token
    
    def set_bearer_token(self, token: str):
        """ベアラートークンを設定"""
        self.bearer_token = token
        logger.debug("BatchRegisterWidget: ベアラートークンを設定 (長さ: %s)", len(token) if token else 0)
    
    def update_bearer_token_from_parent(self):
        """親コントローラからベアラートークンを更新"""
        if hasattr(self.parent_controller, 'bearer_token'):
            self.bearer_token = self.parent_controller.bearer_token
            logger.debug("BatchRegisterWidget: parent_controllerからトークンを更新")
            
    def _ensure_temp_folder_and_mapping_continue(self, file_set):
        """ファイルセットの一時フォルダとマッピングファイルが存在することを確認・作成（続き）"""
        try:
            # 既存の一時フォルダとマッピングファイルをチェック
            temp_folder = None
            mapping_file = None
            
            if hasattr(file_set, 'extended_config') and file_set.extended_config:
                temp_folder = file_set.extended_config.get('temp_folder')
                mapping_file = file_set.extended_config.get('mapping_file')
            
            # 一時フォルダまたはマッピングファイルが存在しない場合は作成
            needs_creation = (
                not temp_folder or not os.path.exists(temp_folder) or
                not mapping_file or not os.path.exists(mapping_file)
            )
            
            if needs_creation:
                logger.info("ファイルセット '%s' の一時フォルダ・マッピングファイルを作成/更新", file_set.name)
                self._create_temp_folder_and_mapping(file_set)
            else:
                logger.info("ファイルセット '%s' の一時フォルダ・マッピングファイルは既に存在", file_set.name)
                
        except Exception as e:
            logger.error("一時フォルダ・マッピングファイル確認エラー: %s", e)
    
    def _create_temp_folder_and_mapping(self, file_set):
        """ファイルセットの一時フォルダとマッピングファイルを作成（UUID対応版）"""
        try:
            if not file_set or not file_set.items:
                logger.warning("ファイルセットが空のため、一時フォルダ作成をスキップ: %s", file_set.name if file_set else 'None')
                return
            
            from ..core.temp_folder_manager import TempFolderManager
            
            temp_manager = TempFolderManager()
            temp_folder, mapping_file = temp_manager.create_temp_folder_for_fileset(file_set)
            
            # UUID固定版では、ファイルセットオブジェクト内に直接パスが設定される
            # （temp_folder_path と mapping_file_path）
            logger.info("ファイルセット '%s' の一時フォルダとマッピングファイルを作成", file_set.name)
            logger.info("ファイルセットUUID: %s", file_set.uuid)
            logger.info("一時フォルダ: %s", temp_folder)
            logger.info("マッピングファイル: %s", mapping_file)
            
            # 後方互換性のため extended_config も設定
            if not hasattr(file_set, 'extended_config'):
                file_set.extended_config = {}
            file_set.extended_config['temp_folder'] = temp_folder
            file_set.extended_config['temp_created'] = True
            file_set.extended_config['mapping_file'] = mapping_file
            file_set.mapping_file = mapping_file  # 下位互換性用
            
            # メタデータを更新保存
            if hasattr(self.file_set_manager, 'save_fileset_metadata'):
                self.file_set_manager.save_fileset_metadata(file_set)
            
        except Exception as e:
            logger.error("一時フォルダ・マッピングファイル作成エラー: %s", e)
            # エラーが発生してもファイルセット作成は続行
    
    def cleanup_temp_folders(self):
        """一時フォルダを一括削除（UUID対応版）"""
        try:
            reply = _centered_question(
                self,
                "確認",
                "本アプリで作成した一時フォルダをすべて削除しますか？\n\n"
                "この操作は元に戻せません。",
                QMessageBox.Yes | QMessageBox.No,
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 新しいUUID管理方式で一時フォルダを削除
            self.temp_folder_manager.cleanup_all_temp_folders()
            
            # ファイルセットの状態をクリア
            if self.file_set_manager:
                for file_set in self.file_set_manager.file_sets:
                    # 新しい固定パス管理をクリア
                    file_set.temp_folder_path = None
                    file_set.mapping_file_path = None
                    
                    # 後方互換性のため既存設定もクリア
                    if hasattr(file_set, 'extended_config') and file_set.extended_config:
                        if 'temp_folder' in file_set.extended_config:
                            del file_set.extended_config['temp_folder']
                        if 'temp_created' in file_set.extended_config:
                            del file_set.extended_config['temp_created']
                        if 'mapping_file' in file_set.extended_config:
                            del file_set.extended_config['mapping_file']
                    
                    if hasattr(file_set, 'mapping_file'):
                        delattr(file_set, 'mapping_file')
                    
                    # メタデータも更新
                    if hasattr(self.file_set_manager, 'save_fileset_metadata'):
                        self.file_set_manager.save_fileset_metadata(file_set)
            
            # 孤立フォルダもクリーンアップ
            orphaned_count = 0
            if self.file_set_manager:
                orphaned_count = self.temp_folder_manager.cleanup_orphaned_temp_folders(
                    self.file_set_manager.file_sets)
            
            # ファイルセット表示を更新
            self.refresh_fileset_display()
            
            QMessageBox.information(
                self, "完了", 
                f"一時フォルダを削除しました。\n"
                f"孤立フォルダも {orphaned_count} 個削除しました。"
            )
                
        except Exception as e:
            logger.error("一時フォルダ削除エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"一時フォルダ削除に失敗しました: {str(e)}")
    
    def connect_signals(self):
        """シグナル接続"""
        # ファイルツリー
        self.file_tree.items_selected.connect(self.on_file_tree_selection)
        
        # ファイルセットテーブル
        self.fileset_table.fileset_selected.connect(self.on_fileset_selected)
        self.fileset_table.fileset_deleted.connect(self.on_fileset_deleted)
        
        # データセット選択（通常登録と同等のイベント処理）
        if hasattr(self, 'dataset_combo') and self.dataset_combo:
            logger.debug("データセットコンボボックスイベント接続: %s", type(self.dataset_combo))
            self.dataset_combo.currentIndexChanged.connect(self.on_dataset_changed)
            
            # 追加のイベント処理（即座の反応を確保）
            self.dataset_combo.activated.connect(self.on_dataset_changed)
            
            logger.debug("データセット選択イベント接続完了")
            
            # フォーカス外れ時の処理を追加
            original_focus_out = self.dataset_combo.focusOutEvent
            def enhanced_focus_out(event):
                self.on_dataset_focus_out(event)
                original_focus_out(event)
            self.dataset_combo.focusOutEvent = enhanced_focus_out
        
        # 試料モード変更
        self.sample_mode_combo.currentTextChanged.connect(self.on_sample_mode_changed)
        self.sample_mode_combo.currentIndexChanged.connect(self.on_sample_selection_changed)
        
        # 一括登録ロジック
        self.batch_logic.finished.connect(self.on_batch_register_finished)
        
        # ターゲットファイルセットコンボボックス初期化
        if hasattr(self, 'target_fileset_combo'):
            self.update_target_fileset_combo()
    
    def update_selected_fileset_from_tree(self):
        """ファイルツリーの選択状態を選択されたファイルセットに反映"""
        if not hasattr(self, 'current_fileset') or not self.current_fileset:
            QMessageBox.information(self, "情報", "ファイルセットが選択されていません。")
            return
        
        try:
            # ファイルツリーから現在の選択状態を取得
            # すべてのファイルアイテムをチェックして、除外状態を更新
            updated_count = 0
            
            for item_id, file_item in self.file_tree.file_items.items():
                # チェックボックスの状態を取得
                tree_item = None
                for i in range(self.file_tree.topLevelItemCount()):
                    if self._find_tree_item_recursive(self.file_tree.topLevelItem(i), item_id):
                        tree_item = self._find_tree_item_recursive(self.file_tree.topLevelItem(i), item_id)
                        break
                
                if tree_item and id(tree_item) in self.file_tree.checkbox_items:
                    checkbox = self.file_tree.checkbox_items[id(tree_item)]
                    is_included = checkbox.isChecked()
                    
                    # ファイルセット内の対応するファイルアイテムを更新
                    for fs_file_item in self.current_fileset.get_valid_items():
                        if fs_file_item.relative_path == file_item.relative_path:
                            fs_file_item.is_excluded = not is_included
                            updated_count += 1
                            break
            
            # 重複チェック
            self._check_file_duplicates()
            
            QMessageBox.information(self, "完了", f"{updated_count}個のファイルの状態を更新しました。")
            self.refresh_fileset_display()
            
        except Exception as e:
            logger.error("ファイルセット更新エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"ファイルセットの更新に失敗しました: {e}")
    
    def _find_tree_item_recursive(self, parent_item, target_id):
        """ツリーアイテムを再帰的に検索"""
        if id(parent_item) == target_id:
            return parent_item
        
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            result = self._find_tree_item_recursive(child, target_id)
            if result:
                return result
        
        return None
    
    def _check_file_duplicates(self):
        """ファイルの重複をチェックし、重複があればアラートを出して除外"""
        if not self.file_set_manager:
            return
        
        # 全ファイルセットのファイルパスを収集
        file_path_to_filesets = {}  # {file_path: [fileset1, fileset2, ...]}
        
        for fileset in self.file_set_manager.file_sets:
            for file_item in fileset.get_valid_items():
                if not file_item.is_excluded:
                    path = file_item.relative_path
                    if path not in file_path_to_filesets:
                        file_path_to_filesets[path] = []
                    file_path_to_filesets[path].append(fileset)
        
        # 重複を検出
        duplicates = {path: filesets for path, filesets in file_path_to_filesets.items() if len(filesets) > 1}
        
        if duplicates:
            duplicate_files = list(duplicates.keys())
            reply = QMessageBox.warning(
                self, "ファイル重複検出",
                f"{len(duplicate_files)}個のファイルが複数のファイルセットに含まれています。\n\n"
                f"重複ファイル例:\n" + "\n".join(duplicate_files[:5]) +
                ("\n..." if len(duplicate_files) > 5 else "") +
                f"\n\n重複ファイルをすべてのファイルセットから除外しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # 重複ファイルを除外
                excluded_count = 0
                for path, filesets in duplicates.items():
                    for fileset in filesets:
                        for file_item in fileset.get_valid_items():
                            if file_item.relative_path == path:
                                file_item.is_excluded = True
                                excluded_count += 1
                
                QMessageBox.information(self, "完了", f"{excluded_count}個の重複ファイルを除外しました。")
    
    def organize_method_changed(self, row, combo_box):
        """整理方法コンボボックスが変更された時の処理"""
        try:
            if row < len(self.file_set_manager.file_sets):
                fileset = self.file_set_manager.file_sets[row]
                organize_method = combo_box.currentText()
                
                # ファイルセットのメタデータに整理方法を保存
                if not hasattr(fileset, 'metadata'):
                    fileset.metadata = {}
                fileset.metadata['organize_method'] = organize_method
                
                logger.info("ファイルセット '%s' の整理方法を '%s' に設定", fileset.name, organize_method)
                
        except Exception as e:
            logger.error("整理方法変更エラー: %s", e)
    
    def copy_fileset_row(self, row):
        """ファイルセット行をコピー"""
        try:
            if row < len(self.file_set_manager.file_sets):
                source_fileset = self.file_set_manager.file_sets[row]
                
                # 新しいファイルセットを作成（ディープコピー）
                import copy
                new_fileset = copy.deepcopy(source_fileset)
                new_fileset.name = f"{source_fileset.name}_copy"
                
                # ファイルセットを追加
                self.file_set_manager.file_sets.append(new_fileset)
                
                # テーブル表示を更新
                self.refresh_fileset_display()
                
                QMessageBox.information(self, "完了", f"ファイルセット '{new_fileset.name}' をコピーしました。")
                
        except Exception as e:
            logger.error("ファイルセットコピーエラー: %s", e)
            QMessageBox.warning(self, "エラー", f"ファイルセットのコピーに失敗しました: {e}")
    
    def delete_fileset_row(self, row):
        """ファイルセット行を削除"""
        try:
            if row < len(self.file_set_manager.file_sets):
                fileset = self.file_set_manager.file_sets[row]
                
                reply = _centered_question(
                    self,
                    "確認",
                    f"ファイルセット '{fileset.name}' を削除しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                
                if reply == QMessageBox.Yes:
                    # ファイルセットを削除
                    self.file_set_manager.file_sets.remove(fileset)
                    
                    # 現在選択中のファイルセットが削除された場合
                    if hasattr(self, 'current_fileset') and self.current_fileset == fileset:
                        self.current_fileset = None
                    
                    # テーブル表示を更新
                    self.refresh_fileset_display()
                    
                    QMessageBox.information(self, "完了", f"ファイルセット '{fileset.name}' を削除しました。")
                
        except Exception as e:
            logger.error("ファイルセット削除エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"ファイルセットの削除に失敗しました: {e}")
    
    def refresh_fileset_display(self):
        """ファイルセット表示を更新"""
        logger.debug("refresh_fileset_display: 呼び出された")
        try:
            logger.debug("refresh_fileset_display: file_set_manager=%s", self.file_set_manager)
            if self.file_set_manager:
                logger.debug("refresh_fileset_display: file_sets count=%s", len(self.file_set_manager.file_sets))
                for i, fs in enumerate(self.file_set_manager.file_sets):
                    logger.debug("FileSet %s: id=%s, name=%s, items=%s", i, fs.id, fs.name, len(fs.items))
            
            # 条件判定を明示的に: file_setsが存在し、かつ空でないこと
            if self.file_set_manager and len(self.file_set_manager.file_sets) > 0:
                # ファイルセットテーブルを更新
                logger.debug("refresh_fileset_display: テーブル更新開始 (件数=%s)", len(self.file_set_manager.file_sets))
                self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
                logger.debug("refresh_fileset_display: テーブル更新完了")
            else:
                # ファイルセットがない場合はクリア
                logger.debug("refresh_fileset_display: テーブルクリア (manager=%s)", self.file_set_manager)
                self.fileset_table.setRowCount(0)
            
            # ファイルセット選択コンボボックスも更新
            self.update_target_fileset_combo()
                
        except Exception as e:
            logger.error("ファイルセット表示更新エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def apply_to_all_filesets(self):
        """現在の設定をすべてのファイルセットに適用"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            QMessageBox.information(self, "情報", "適用するファイルセットがありません。")
            return
        
        try:
            # 現在の設定を取得
            settings = self.get_current_settings()
            
            reply = _centered_question(
                self,
                "確認",
                f"現在の設定をすべてのファイルセット（{len(self.file_set_manager.file_sets)}個）に適用しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            
            if reply == QMessageBox.Yes:
                applied_count = 0
                for fileset in self.file_set_manager.file_sets:
                    self._apply_settings_to_fileset(fileset, settings)
                    applied_count += 1
                
                QMessageBox.information(self, "完了", f"{applied_count}個のファイルセットに設定を適用しました。")
                self.refresh_fileset_display()
            
        except Exception as e:
            logger.error("全ファイルセット適用エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
    
    def apply_to_target_fileset(self):
        """現在の設定をターゲットファイルセットに適用"""
        if not hasattr(self, 'target_fileset_combo'):
            return
        
        target_name = self.target_fileset_combo.currentText()
        if not target_name or target_name == "選択してください":
            QMessageBox.information(self, "情報", "ターゲットファイルセットを選択してください。")
            return
        
        try:
            # ターゲットファイルセットを検索
            target_fileset = None
            for fileset in self.file_set_manager.file_sets:
                if fileset.name == target_name:
                    target_fileset = fileset
                    break
            
            if not target_fileset:
                QMessageBox.warning(self, "エラー", f"ファイルセット '{target_name}' が見つかりません。")
                return
            
            # 現在の設定を取得
            settings = self.get_current_settings()
            
            reply = _centered_question(
                self,
                "確認",
                f"現在の設定をファイルセット '{target_name}' に適用しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            
            if reply == QMessageBox.Yes:
                self._apply_settings_to_fileset(target_fileset, settings)
                QMessageBox.information(self, "完了", f"ファイルセット '{target_name}' に設定を適用しました。")
                self.refresh_fileset_display()
            
        except Exception as e:
            logger.error("ターゲットファイルセット適用エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
    
    def get_current_settings(self):
        """現在のUI設定を取得"""
        settings = {}
        
        try:
            # 基本情報
            if hasattr(self, 'data_name_edit'):
                settings['data_name'] = self.data_name_edit.text()
            if hasattr(self, 'description_edit'):
                settings['description'] = self.description_edit.toPlainText()
            if hasattr(self, 'experiment_id_edit'):
                settings['experiment_id'] = self.experiment_id_edit.text()
            if hasattr(self, 'reference_url_edit'):
                settings['reference_url'] = self.reference_url_edit.text()
            if hasattr(self, 'tags_edit'):
                settings['tags'] = self.tags_edit.text()
            
            # データセット設定
            if hasattr(self, 'dataset_combo'):
                current_data = self.dataset_combo.currentData()
                if current_data:
                    if isinstance(current_data, dict) and 'id' in current_data:
                        settings['dataset_id'] = current_data['id']
                        settings['dataset_name'] = current_data.get('name', '')
                        settings['selected_dataset'] = current_data  # 完全なデータセット情報を保存
                        logger.debug("get_current_settings - データセット情報: %s", current_data)
                    else:
                        settings['dataset_id'] = str(current_data)
                        settings['dataset_name'] = self.dataset_combo.currentText()
                        settings['selected_dataset'] = {'id': str(current_data), 'name': self.dataset_combo.currentText()}
                else:
                    settings['dataset_id'] = None
                    settings['dataset_name'] = self.dataset_combo.currentText()
                    settings['selected_dataset'] = None
            
            # 試料設定
            if hasattr(self, 'sample_id_combo'):
                current_index = self.sample_id_combo.currentIndex()
                if current_index > 0:  # "新規作成"以外が選択された場合
                    selected_sample_data = self.sample_id_combo.currentData()
                    if selected_sample_data and 'id' in selected_sample_data:
                        # 既存試料選択の場合：UUIDを保存
                        settings['sample_mode'] = 'existing'
                        settings['sample_id'] = selected_sample_data['id']
                        logger.debug("save_fileset_config - 既存試料選択: %s", selected_sample_data['id'])
                    else:
                        # UUIDが取得できない場合は新規として扱う
                        settings['sample_mode'] = 'new'
                        logger.warning("既存試料が選択されているがUUIDが取得できませんでした")
                else:
                    # 新規作成の場合
                    settings['sample_mode'] = 'new'
                    logger.debug("save_fileset_config - 新規試料作成")
            if hasattr(self, 'sample_name_edit'):
                sample_name = self.sample_name_edit.text().strip()
                if sample_name:  # 空でない場合のみ保存
                    settings['sample_name'] = sample_name
            if hasattr(self, 'sample_description_edit'):
                sample_description = self.sample_description_edit.toPlainText().strip()
                if sample_description:  # 空でない場合のみ保存
                    settings['sample_description'] = sample_description
            if hasattr(self, 'sample_composition_edit'):
                sample_composition = self.sample_composition_edit.text().strip()
                if sample_composition:  # 空でない場合のみ保存
                    settings['sample_composition'] = sample_composition
            
            # 固有情報（カスタムフィールド）
            custom_values = {}
            
            # インボイススキーマフォームから取得を試行（空値も含む）
            if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form:
                try:
                    # 新しい関数で空値もnullとして取得
                    from classes.utils.schema_form_util import get_schema_form_all_fields
                    schema_custom_values = get_schema_form_all_fields(self.invoice_schema_form)
                    if schema_custom_values is not None:  # Noneでない場合はマージ
                        custom_values.update(schema_custom_values)
                        logger.debug("get_current_settings - インボイススキーマから取得(空値含む): %s", schema_custom_values)
                except Exception as e:
                    logger.warning("インボイススキーマフォームからの取得エラー: %s", e)
            
            # 従来のカスタムフィールドウィジェットからも取得（空値も含む）
            if hasattr(self, 'custom_field_widgets'):
                for field_name, widget in self.custom_field_widgets.items():
                    try:
                        value = None
                        if hasattr(widget, 'text'):
                            value = widget.text()
                        elif hasattr(widget, 'toPlainText'):
                            value = widget.toPlainText()
                        elif hasattr(widget, 'currentText'):
                            value = widget.currentText()
                        else:
                            continue
                        
                        # 空値も空文字列として保存（既存値を上書きしない）
                        if field_name not in custom_values:
                            custom_values[field_name] = value if value else ""
                        
                    except Exception as e:
                        logger.warning("カスタムフィールド '%s' の取得エラー: %s", field_name, e)
                        
            settings['custom_values'] = custom_values
            
            logger.debug("get_current_settings - 固有情報取得完了: %s個の項目", len(custom_values))
            for key, value in custom_values.items():
                logger.debug("- %s: %s", key, value)
            
            logger.debug("get_current_settings: %s", settings)
            
        except Exception as e:
            logger.error("設定取得エラー: %s", e)
            import traceback
            traceback.print_exc()
            settings = {}
        
        return settings
    
    def _apply_settings_to_fileset(self, fileset, settings):
        """ファイルセットに設定を適用"""
        try:
            # 基本情報の適用
            if 'data_name' in settings:
                fileset.data_name = settings['data_name']
            if 'description' in settings:
                fileset.description = settings['description']
            if 'experiment_id' in settings:
                fileset.experiment_id = settings['experiment_id']
            if 'reference_url' in settings:
                fileset.reference_url = settings['reference_url']
            if 'tags' in settings:
                fileset.tags = settings['tags']
            
            # データセット設定の適用
            if 'dataset_id' in settings:
                fileset.dataset_id = settings['dataset_id']
                logger.debug("データセットIDを fileset.dataset_id に設定: %s", settings['dataset_id'])
                
                # dataset_infoも同時に設定
                if not hasattr(fileset, 'dataset_info') or not fileset.dataset_info:
                    fileset.dataset_info = {}
                fileset.dataset_info['id'] = settings['dataset_id']
                logger.debug("データセットIDを fileset.dataset_info['id'] に設定: %s", settings['dataset_id'])
                
            if 'dataset_name' in settings:
                if not hasattr(fileset, 'dataset_info') or not fileset.dataset_info:
                    fileset.dataset_info = {}
                fileset.dataset_info['name'] = settings['dataset_name']
                logger.debug("データセット名を fileset.dataset_info['name'] に設定: %s", settings['dataset_name'])
                
            # extended_configにも保存（フォールバック用）
            if 'selected_dataset' in settings:
                if not hasattr(fileset, 'extended_config'):
                    fileset.extended_config = {}
                fileset.extended_config['selected_dataset'] = settings['selected_dataset']
                logger.debug("データセット情報を extended_config に保存: %s", settings['selected_dataset'])
            
            # 試料設定の適用
            if 'sample_mode' in settings:
                # UIの表示名から内部値に変換
                mode_map = {
                    "新規作成": "new",
                    "既存試料使用": "existing",
                    "前回と同じ": "same_as_previous"
                }
                fileset.sample_mode = mode_map.get(settings['sample_mode'], settings['sample_mode'])
            if 'sample_id' in settings:
                fileset.sample_id = settings['sample_id'] if settings['sample_id'] else None
            if 'sample_name' in settings:
                fileset.sample_name = settings['sample_name']
            if 'sample_description' in settings:
                fileset.sample_description = settings['sample_description']
            if 'sample_composition' in settings:
                fileset.sample_composition = settings['sample_composition']
            
            # 固有情報（カスタム値）の適用
            if 'custom_values' in settings:
                # custom_values属性を必ず初期化
                if not hasattr(fileset, 'custom_values'):
                    fileset.custom_values = {}
                
                # 既存のカスタム値をクリア（空値にした項目を確実にリセット）
                fileset.custom_values.clear()
                
                # 新しいカスタム値を設定（null値も含む）
                if settings['custom_values']:
                    fileset.custom_values.update(settings['custom_values'])
                    logger.debug("カスタム値をファイルセットに適用: %s個", len(settings['custom_values']))
                    for key, value in settings['custom_values'].items():
                        logger.debug("- %s: %s", key, value)
                else:
                    logger.debug("カスタム値は空ですが、フィールドをクリアしました")
            
            # 拡張設定に保存（バックアップとして、ただし内部データは除外）
            if not hasattr(fileset, 'extended_config'):
                fileset.extended_config = {}
            
            # 内部データを除外してから保存
            filtered_settings = {k: v for k, v in settings.items() 
                               if k not in {'selected_dataset'}}
            fileset.extended_config.update(filtered_settings)
            
            logger.info("ファイルセット '%s' に設定を適用しました", fileset.name)
            logger.debug("適用後のfileset.data_name: %s", getattr(fileset, 'data_name', None))
            logger.debug("適用後のfileset.dataset_id: %s", getattr(fileset, 'dataset_id', None))
            logger.debug("適用後のfileset.sample_mode: %s", getattr(fileset, 'sample_mode', None))
            
        except Exception as e:
            logger.error("ファイルセット設定適用エラー: %s", e)
            import traceback
            traceback.print_exc()
            raise
    
    def update_target_fileset_combo(self):
        """ターゲットファイルセットコンボボックスを更新"""
        if not hasattr(self, 'target_fileset_combo'):
            return
        
        try:
            current_text = self.target_fileset_combo.currentText()
            self.target_fileset_combo.clear()
            self.target_fileset_combo.addItem("選択してください")
            
            if self.file_set_manager and self.file_set_manager.file_sets:
                for fileset in self.file_set_manager.file_sets:
                    self.target_fileset_combo.addItem(fileset.name)
            
            # 以前の選択を復元
            if current_text and current_text != "選択してください":
                index = self.target_fileset_combo.findText(current_text)
                if index >= 0:
                    self.target_fileset_combo.setCurrentIndex(index)
            
        except Exception as e:
            logger.error("ターゲットファイルセットコンボボックス更新エラー: %s", e)
    
    # 実装完了：バッチ登録タブの包括的拡張
    # - 選択ファイル設定ペインのボタン再編成
    # - ファイルツリーペインの改善（チェックボックス統合、状態表示簡素化）
    # - ファイルセットリストペインの拡張（8列表示、データ名/サンプル/データセット列追加）
    # - 登録実行ペインの名称変更と凡例追加
    # - 新しいボタン機能の完全実装（全ファイルセット適用、ターゲット適用、設定保存等）
    # - ファイルツリーとファイルセット連動機能
    # - 重複チェックと除外機能
    # - 整理方法選択機能
    # - ファイルセットコピー・削除機能
    def browse_directory(self):
        """ディレクトリ参照"""
        # 前回保存されたディレクトリを取得
        last_directory = self._load_last_directory()
        start_directory = last_directory if last_directory and os.path.exists(last_directory) else self.dir_path_edit.text()
        
        directory = QFileDialog.getExistingDirectory(
            self, "ベースディレクトリを選択", start_directory
        )
        if directory:
            self.dir_path_edit.setText(directory)
            self._save_last_directory(directory)  # ディレクトリを保存
            self.load_directory(directory)
    
    def load_directory(self, directory: str):
        """ディレクトリをロード（自動ツリー展開付き）"""
        try:
            self.file_set_manager = FileSetManager(directory)
            logger.debug("load_directory: FileSetManager作成完了 %s", directory)
            
            # FileSetTableWidgetにfile_set_managerを再設定
            if hasattr(self, 'fileset_table') and self.fileset_table:
                logger.debug("load_directory: FileSetTableWidgetにfile_set_manager再設定")
                self.fileset_table.set_file_set_manager(self.file_set_manager)
            
            file_items = self.file_set_manager.build_file_tree()
            self.file_tree.load_file_tree(file_items)
            
            # ディレクトリロード時に自動展開
            self.auto_expand_tree(file_items)
            
            self.update_summary()
            
            # ステータス更新
            self.status_label.setText(f"ディレクトリを読み込みました: {directory}")
            
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ディレクトリの読み込みに失敗しました:\n{str(e)}")
            self.status_label.setText(f"ディレクトリ読み込みエラー: {str(e)}")
    
    def _load_last_directory(self) -> Optional[str]:
        """前回使用したディレクトリを読み込み"""
        try:
            config_path = self._get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('last_directory')
        except Exception as e:
            logger.warning("設定ファイル読み込みエラー: %s", e)
        return None
    
    def _save_last_directory(self, directory: str):
        """使用したディレクトリを保存"""
        try:
            config_path = self._get_config_path()
            config = {}
            
            # 既存設定を読み込み
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            # ディレクトリを更新
            config['last_directory'] = directory
            
            # 設定ファイルに保存
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.warning("設定ファイル保存エラー: %s", e)
    
    def _get_config_path(self) -> str:
        """設定ファイルパスを取得"""
        from config.common import get_user_config_dir
        config_dir = get_user_config_dir()
        return os.path.join(config_dir, 'batch_register_config.json')
    
    def auto_expand_tree(self, file_items: List[FileItem]):
        """ファイルツリーを適切に展開"""
        try:
            # 最大3階層まで自動展開
            max_expand_depth = 3
            
            # ディレクトリ項目を抽出して階層別に分類
            directories = [item for item in file_items if item.file_type == FileType.DIRECTORY]
            
            # 階層レベル別にソート（浅い階層から展開）
            directories.sort(key=lambda x: x.relative_path.count(os.sep))
            
            for directory in directories:
                # 階層レベルをチェック
                depth = directory.relative_path.count(os.sep)
                if depth >= max_expand_depth:
                    continue
                    
                # ディレクトリアイテムを探して展開
                tree_item = self.file_tree.find_tree_item_by_file_item(directory)
                if tree_item:
                    self.file_tree.expandItem(tree_item)
            
        except Exception as e:
            # 展開エラーは警告のみ（メイン機能には影響しない）
            logger.warning("Tree expansion warning: %s", e)
    
    def refresh_file_tree(self):
        """ファイルツリー更新"""
        if self.file_set_manager:
            directory = self.file_set_manager.base_directory
            self.load_directory(directory)
    
    def refresh_file_tree_with_warning(self):
        """ファイルツリー更新（警告付き）"""
        reply = _centered_question(
            self,
            "確認",
            "ファイルツリーを再読み込みします。\n\n「含む」状態がリセットされますが、続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            self.refresh_file_tree()
    
    def expand_all(self):
        """全て展開"""
        self.file_tree.expandAll()
    
    def collapse_all(self):
        """全て折りたたみ"""
        self.file_tree.collapseAll()
    
    def select_all_files(self):
        """ファイルツリーの全てのファイルを選択"""
        try:
            # ツリーの全アイテムを走査してチェックボックスを設定
            root = self.file_tree.invisibleRootItem()
            self._set_all_items_checked(root, True)
        except Exception as e:
            logger.error("全選択エラー: %s", e)
    
    def deselect_all_files(self):
        """ファイルツリーの全てのファイルの選択を解除"""
        try:
            # ツリーの全アイテムを走査してチェックボックスを解除
            root = self.file_tree.invisibleRootItem()
            self._set_all_items_checked(root, False)
        except Exception as e:
            logger.error("全解除エラー: %s", e)
    
    def _set_all_items_checked(self, parent_item, checked):
        """再帰的に全アイテムのチェック状態を設定"""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            # 「含む」列（列5）のチェックボックスを取得
            checkbox = self.file_tree.itemWidget(child, 5)
            if checkbox and isinstance(checkbox, QCheckBox):
                checkbox.setChecked(checked)
            
            # 子アイテムも再帰的に処理
            self._set_all_items_checked(child, checked)
    
    def _get_checked_items_from_tree(self):
        """ファイルツリーから「含む」チェックがオンのアイテムを取得（改良版）"""
        checked_items = []
        
        def collect_checked_items(parent_item, depth=0):
            indent = "  " * depth
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                
                # チェックボックス状態を確認
                checkbox = self.file_tree.itemWidget(child, 5)  # 含む列
                file_item = self.file_tree.file_items.get(id(child))
                
                if file_item:
                    # チェックボックスの状態を確認
                    is_checked = False
                    if checkbox and isinstance(checkbox, QCheckBox):
                        is_checked = checkbox.isChecked()
                        # FileItemの状態を同期
                        file_item.is_excluded = not is_checked
                        logger.debug("%sチェックボックス状態確認: %s -> checked=%s", indent, file_item.name, is_checked)
                    else:
                        # チェックボックスがない場合はFileItemの状態を参照
                        is_checked = not getattr(file_item, 'is_excluded', False)
                        logger.debug("%sFileItem状態参照: %s -> excluded=%s -> checked=%s", indent, file_item.name, getattr(file_item, 'is_excluded', False), is_checked)
                    
                    # チェック済みの場合は追加
                    if is_checked:
                        checked_items.append(file_item)
                        logger.debug("%s[OK] チェック済みアイテム追加: %s (%s) - Path: %s", indent, file_item.name, file_item.file_type.name, file_item.relative_path)
                    else:
                        logger.debug("%s[X] チェックなしアイテム除外: %s (%s)", indent, file_item.name, file_item.file_type.name)
                else:
                    logger.debug("%sFileItemが見つからない: tree_item_id=%s", indent, id(child))
                
                # 子アイテムも再帰的に処理
                collect_checked_items(child, depth + 1)
        
        logger.debug("_get_checked_items_from_tree: 開始")
        root = self.file_tree.invisibleRootItem()
        collect_checked_items(root)
        
        logger.debug("_get_checked_items_from_tree: 合計チェック済みアイテム数=%s", len(checked_items))
        
        # 収集されたアイテムのパス一覧を表示
        for item in checked_items:
            logger.debug("最終収集: %s -> %s", item.name, item.relative_path)
            
        return checked_items
    
    def _check_duplicate_files_across_filesets(self, new_items):
        """新しいアイテムと既存のファイルセット間での重複ファイルをチェック"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            return []
        
        new_paths = {item.path for item in new_items}
        conflicts = []
        
        for fileset in self.file_set_manager.file_sets:
            for existing_item in fileset.items:
                if existing_item.path in new_paths:
                    conflicts.append(existing_item.path)
        
        return list(set(conflicts))  # 重複を除去
    
    def _format_conflict_message(self, conflicts):
        """重複ファイルのメッセージをフォーマット"""
        conflict_msg = "以下のファイルは既に他のファイルセットに含まれています：\n\n"
        
        # 最初の10件を表示
        display_conflicts = conflicts[:10]
        for conflict_path in display_conflicts:
            # 相対パスで表示
            try:
                rel_path = os.path.relpath(conflict_path, self.file_set_manager.base_directory)
                conflict_msg += f"• {rel_path}\n"
            except:
                conflict_msg += f"• {conflict_path}\n"
        
        if len(conflicts) > 10:
            conflict_msg += f"\n... 他 {len(conflicts) - 10} 件\n"
        
        conflict_msg += "\n重複ファイルを除外して作成を続行しますか？\n"
        conflict_msg += "（「いいえ」を選択すると作成をキャンセルします）"
        
        return conflict_msg
    
    def _create_filesets_by_top_dirs(self, selected_items):
        """最上位ディレクトリごとにファイルセットを作成"""
        # ファイルのみを対象とする
        selected_files = [item for item in selected_items if item.file_type == FileType.FILE]
        
        # 最上位ディレクトリごとにファイルをグループ化
        top_dir_groups = {}
        root_files = []
        
        for file_item in selected_files:
            path_parts = file_item.relative_path.split(os.sep)
            if len(path_parts) == 1:
                # ルート直下のファイル
                root_files.append(file_item)
            else:
                # 最上位サブフォルダ配下のファイル
                top_dir = path_parts[0]
                if top_dir not in top_dir_groups:
                    top_dir_groups[top_dir] = []
                top_dir_groups[top_dir].append(file_item)
        
        file_sets = []
        
        # ルート直下のファイル用のファイルセットを作成
        if root_files:
            # ルートフォルダ名を取得（ベースディレクトリの名前）
            base_dir_name = os.path.basename(self.file_set_manager.base_directory) or "ルートフォルダ"
            root_fileset = self.file_set_manager.create_manual_fileset(base_dir_name, root_files)
            file_sets.append(root_fileset)
        
        # 各最上位ディレクトリ用のファイルセットを作成
        for top_dir, files in top_dir_groups.items():
            if files:
                fileset = self.file_set_manager.create_manual_fileset(top_dir, files)
                file_sets.append(fileset)
        
        return file_sets
    
    def _create_filesets_by_all_dirs(self, selected_items):
        """全ディレクトリごとにファイルセットを作成"""
        # ファイルのみを対象とする
        selected_files = [item for item in selected_items if item.file_type == FileType.FILE]
        
        # ディレクトリごとにファイルをグループ化
        dir_groups = {}
        root_files = []
        
        for file_item in selected_files:
            path_parts = file_item.relative_path.split(os.sep)
            if len(path_parts) == 1:
                # ルート直下のファイル
                root_files.append(file_item)
            else:
                # ディレクトリ配下のファイル
                parent_dir = os.path.dirname(file_item.relative_path)
                if parent_dir not in dir_groups:
                    dir_groups[parent_dir] = []
                dir_groups[parent_dir].append(file_item)
        
        file_sets = []
        
        # ルート直下のファイル用のファイルセットを作成
        if root_files:
            # ルートフォルダ名を取得（ベースディレクトリの名前）
            base_dir_name = os.path.basename(self.file_set_manager.base_directory) or "ルートフォルダ"
            root_fileset = self.file_set_manager.create_manual_fileset(base_dir_name, root_files)
            file_sets.append(root_fileset)
        
        # 各ディレクトリ用のファイルセットを作成
        for dir_path, files in dir_groups.items():
            if files:
                # 相対パスをフラット化（区切り文字を_に変換）
                flat_name = dir_path.replace(os.sep, '_')
                fileset = self.file_set_manager.create_manual_fileset(flat_name, files)
                file_sets.append(fileset)
        
        return file_sets
        
        return file_sets
    
    def auto_assign_all_as_one_with_confirm(self):
        """全体で1つのファイルセット作成（確認ダイアログ付き）"""
        reply = _centered_question(
            self,
            "確認",
            "既存のファイルセットをリセットして、全体を1つのファイルセットとして作成します。\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            self.auto_assign_all_as_one()
    
    def auto_assign_by_top_dirs_with_confirm(self):
        """最上位フォルダごとにファイルセット作成（確認ダイアログ付き）"""
        reply = _centered_question(
            self,
            "確認",
            "既存のファイルセットをリセットして、最上位フォルダごとにファイルセットを作成します。\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            self.auto_assign_by_top_dirs()
    
    def auto_assign_all_dirs_with_confirm(self):
        """全フォルダを個別ファイルセット作成（確認ダイアログ付き）"""
        reply = _centered_question(
            self,
            "確認",
            "既存のファイルセットをリセットして、全フォルダを個別にファイルセットとして作成します。\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            self.auto_assign_all_dirs()
    
    def auto_assign_all_as_one(self):
        """全体で1つのファイルセット作成"""
        logger.debug("auto_assign_all_as_one: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            # 既存のファイルセットをクリア
            self.file_set_manager.clear_all_filesets()
            logger.debug("auto_assign_all_as_one: 既存ファイルセットをクリア")
            
            # 「含む」チェックボックスがオンのファイルのみを取得
            all_checked_items = self._get_checked_items_from_tree()
            selected_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            logger.debug("auto_assign_all_as_one: チェック済みファイル数=%s", len(selected_files))
            
            if not selected_files:
                QMessageBox.information(self, "情報", "「含む」にチェックされたファイルがありません。")
                return
            
            # 全体ファイルセット作成
            file_set = self.file_set_manager.create_manual_fileset("全体", selected_files)
            
            # 容量制限とZIP競合の解決
            file_sets = [file_set]
            capacity_limit = self._get_capacity_limit_bytes()
            if capacity_limit:
                file_sets = self._apply_capacity_limit_to_filesets(file_sets, capacity_limit)
            else:
                file_sets = self._resolve_zip_hierarchy_conflicts(file_sets)
                self.file_set_manager.file_sets = file_sets
            
            logger.debug("auto_assign_all_as_one: 最終ファイルセット数=%s", len(file_sets) if file_sets else 0)
            logger.debug("auto_assign_all_as_one: refresh_fileset_display() 呼び出し直前")
            self.refresh_fileset_display()
            logger.debug("auto_assign_all_as_one: refresh_fileset_display() 呼び出し完了")
            self.update_summary()
        except Exception as e:
            logger.error("auto_assign_all_as_one: エラー発生: %s", e)
            import traceback
            traceback.print_exc()
    
    def auto_assign_by_top_dirs(self):
        """最上位フォルダごとにファイルセット作成"""
        logger.debug("auto_assign_by_top_dirs: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            # 既存のファイルセットをクリア
            self.file_set_manager.clear_all_filesets()
            logger.debug("auto_assign_by_top_dirs: 既存ファイルセットをクリア")
            
            # 「含む」チェックボックスがオンのファイルのみを取得
            all_checked_items = self._get_checked_items_from_tree()
            selected_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            logger.debug("auto_assign_by_top_dirs: チェック済みファイル数=%s", len(selected_files))
            
            if not selected_files:
                QMessageBox.information(self, "情報", "「含む」にチェックされたファイルがありません。")
                return
            
            # 最上位ディレクトリごとにファイルセットを作成
            file_sets = self._create_filesets_by_top_dirs(selected_files)
            
            # 容量制限とZIP競合の解決
            capacity_limit = self._get_capacity_limit_bytes()
            if capacity_limit:
                file_sets = self._apply_capacity_limit_to_filesets(file_sets, capacity_limit)
            else:
                file_sets = self._resolve_zip_hierarchy_conflicts(file_sets)
                self.file_set_manager.file_sets = file_sets
            
            logger.debug("auto_assign_by_top_dirs: 最終ファイルセット数=%s", len(file_sets) if file_sets else 0)
            logger.debug("auto_assign_by_top_dirs: refresh_fileset_display() 呼び出し直前")
            self.refresh_fileset_display()
            logger.debug("auto_assign_by_top_dirs: refresh_fileset_display() 呼び出し完了")
            self.update_summary()
        except Exception as e:
            logger.error("auto_assign_by_top_dirs: エラー発生: %s", e)
            import traceback
            traceback.print_exc()
    
    def auto_assign_all_dirs(self):
        """全フォルダを個別ファイルセット作成"""
        logger.debug("auto_assign_all_dirs: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            # 既存のファイルセットをクリア
            self.file_set_manager.clear_all_filesets()
            logger.debug("auto_assign_all_dirs: 既存ファイルセットをクリア")
            
            # 「含む」チェックボックスがオンのファイルのみを取得
            all_checked_items = self._get_checked_items_from_tree()
            selected_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            logger.debug("auto_assign_all_dirs: チェック済みファイル数=%s", len(selected_files))
            
            if not selected_files:
                QMessageBox.information(self, "情報", "「含む」にチェックされたファイルがありません。")
                return
            
            # 全ディレクトリごとにファイルセットを作成
            file_sets = self._create_filesets_by_all_dirs(selected_files)
            
            # 容量制限とZIP競合の解決
            capacity_limit = self._get_capacity_limit_bytes()
            if capacity_limit:
                file_sets = self._apply_capacity_limit_to_filesets(file_sets, capacity_limit)
            else:
                file_sets = self._resolve_zip_hierarchy_conflicts(file_sets)
                self.file_set_manager.file_sets = file_sets
            
            logger.debug("auto_assign_all_dirs: 最終ファイルセット数=%s", len(file_sets) if file_sets else 0)
            logger.debug("auto_assign_all_dirs: refresh_fileset_display() 呼び出し直前")
            self.refresh_fileset_display()
            logger.debug("auto_assign_all_dirs: refresh_fileset_display() 呼び出し完了")
            self.update_summary()
        except Exception as e:
            logger.error("auto_assign_all_dirs: エラー発生: %s", e)
            import traceback
            traceback.print_exc()
    
    def create_manual_fileset(self):
        """手動ファイルセット作成"""
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return
        
        try:
            # ファイルツリーからファイルアイテムを取得
            file_items = self.file_set_manager.build_file_tree()
            
            # データツリー選択ダイアログ
            dialog = DataTreeDialog(file_items, self)
            dialog.show()  # ダイアログを表示
            dialog.raise_()  # 最前面に持ってくる
            dialog.activateWindow()  # アクティブ化
            if dialog.exec() == QDialog.Accepted:
                selected_items = dialog.get_selected_items()
                if selected_items:
                    # ファイルセット名入力
                    input_dialog = QInputDialog(self)
                    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
                    name, ok = input_dialog.getText(self, "ファイルセット名", "ファイルセット名を入力してください:")
                    if ok and name:
                        file_set = self.file_set_manager.create_manual_fileset(name, selected_items)
                        
                        # 作成直後に一時フォルダとマッピングファイルを作成
                        self._create_temp_folder_and_mapping(file_set)
                        
                        # 作成後にZIP階層競合を解決
                        current_file_sets = self.file_set_manager.get_file_sets()
                        if current_file_sets:
                            resolved_sets = self._resolve_zip_hierarchy_conflicts(current_file_sets)
                            self.file_set_manager.file_sets = resolved_sets
                        
                        self.refresh_fileset_display()
                        self.update_summary()
                
        except Exception as e:
            logger.error("手動ファイルセット作成エラー: %s", e)
            QMessageBox.warning(self, "エラー", f"手動ファイルセット作成に失敗しました:\n{str(e)}")
    
    def clear_all_filesets(self):
        """全ファイルセット削除"""
        reply = _centered_question(
            self,
            "確認",
            "全てのファイルセットを削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            if self.file_set_manager:
                self.file_set_manager.file_sets.clear()
                self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
                self.update_summary()
    
    def on_file_tree_selection(self, items: List[FileItem]):
        """ファイルツリー選択処理"""
        # 選択情報の表示（将来的には詳細情報パネル等で使用）
        pass
    
    def on_fileset_selected(self, file_set: FileSet):
        """ファイルセット選択処理（包括的フォームフィールド対応）"""
        # ファイルセット復元処理中フラグを設定（自動設定適用を防ぐ）
        self._restoring_fileset = True
        
        try:
            # 基本情報を表示
            self.fileset_name_edit.setText(file_set.name)
            self.organize_method_combo.setCurrentText(
                "ZIP化" if file_set.organize_method == PathOrganizeMethod.ZIP else "フラット化"
            )
            self.data_name_edit.setText(file_set.data_name)
            
            # データセットコンボボックス設定
            if file_set.dataset_id:
                logger.debug("ファイルセット選択: データセットID=%sを設定中", file_set.dataset_id)
                # データセットIDで検索してコンボボックスを設定
                found = False
                for i in range(self.dataset_combo.count()):
                    item_data = self.dataset_combo.itemData(i)
                    # 辞書オブジェクトの場合は'id'キーを確認、文字列の場合は直接比較
                    dataset_id = None
                    if isinstance(item_data, dict) and 'id' in item_data:
                        dataset_id = item_data['id']
                    elif isinstance(item_data, str):
                        dataset_id = item_data
                    
                    if dataset_id == file_set.dataset_id:
                        logger.debug("データセットコンボボックス: インデックス%sを選択", i)
                        self.dataset_combo.setCurrentIndex(i)
                        found = True
                        # データセット選択変更イベントを手動で発火
                        logger.debug("復元時on_dataset_changed呼び出し前: invoice_schema_form=%s", getattr(self, 'invoice_schema_form', None))
                        self.on_dataset_changed(i)
                        logger.debug("復元時on_dataset_changed呼び出し後: invoice_schema_form=%s", getattr(self, 'invoice_schema_form', None))
                        break
                if not found:
                    logger.warning("データセットID %s がコンボボックスに見つかりません", file_set.dataset_id)
                    # データセット未選択状態にする（有効な最初のアイテムを選択）
                    self.dataset_combo.setCurrentIndex(-1)
            else:
                logger.debug("ファイルセット選択: データセット未設定")
                # 未設定の場合は最初のアイテム（選択なし）を選択
                self.dataset_combo.setCurrentIndex(0)
            
            # 拡張設定フィールドを表示
            extended_config = getattr(file_set, 'extended_config', {})
            
            # データ情報
            self.description_edit.setPlainText(extended_config.get('description', ''))
            self.experiment_id_edit.setText(extended_config.get('experiment_id', ''))
            self.reference_url_edit.setText(extended_config.get('reference_url', ''))
            self.tags_edit.setText(extended_config.get('tags', ''))
            
            # 試料情報
            # 「前回と同じ」オプションの有効性をチェックして制御
            self.update_same_as_previous_option()
            
            sample_mode = extended_config.get('sample_mode', '新規作成')
            for i in range(self.sample_mode_combo.count()):
                if self.sample_mode_combo.itemText(i) == sample_mode:
                    self.sample_mode_combo.setCurrentIndex(i)
                    break
            
            self.sample_id_combo.setCurrentText(extended_config.get('sample_id', ''))
            self.sample_name_edit.setText(extended_config.get('sample_name', ''))
            self.sample_description_edit.setPlainText(extended_config.get('sample_description', ''))
            self.sample_composition_edit.setText(extended_config.get('sample_composition', ''))
            
            # カスタム値（インボイススキーマフォーム）の復元
            if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form:
                try:
                    custom_values = getattr(file_set, 'custom_values', {}) or {}
                    
                    # custom_valuesが空の場合、extended_configから取得を試行
                    if not custom_values:
                        extended_config = getattr(file_set, 'extended_config', {})
                        if 'custom_values' in extended_config and extended_config['custom_values']:
                            custom_values = extended_config['custom_values']
                            logger.debug("extended_configからカスタム値を復元: %s個", len(custom_values))
                        else:
                            # インボイススキーマ項目を直接チェック
                            schema_fields = [
                                'electron_gun', 'accelerating_voltage', 'observation_method',
                                'ion_species', 'major_processing_observation_conditions', 'remark'
                            ]
                            for field in schema_fields:
                                if field in extended_config and extended_config[field]:
                                    custom_values[field] = extended_config[field]
                    
                    logger.debug("ファイルセット選択時のカスタム値復元: %s個の項目", len(custom_values))
                    for key, value in custom_values.items():
                        logger.debug("復元: %s = %s", key, value)
                    
                    # フォーム型をチェックして適切なメソッドを呼び出す
                    if hasattr(self.invoice_schema_form, 'set_form_data'):
                        if custom_values:
                            self.invoice_schema_form.set_form_data(custom_values)
                            logger.debug("インボイススキーマフォームにカスタム値を設定完了")
                        else:
                            self.invoice_schema_form.clear_form()
                            logger.debug("カスタム値が空のため、フォームをクリア")
                    else:
                        logger.debug("invoice_schema_form (%s) はset_form_dataメソッドを持っていません", type(self.invoice_schema_form))
                        # フォーム参照をクリアして再作成を促す
                        logger.debug("現在のデータセット情報で再作成を試行...")
                        
                        # 現在選択されているデータセット情報を取得
                        current_dataset_data = self.dataset_combo.currentData()
                        if current_dataset_data and isinstance(current_dataset_data, dict):
                            logger.debug("データセット情報を使用してスキーマフォーム再作成: %s", current_dataset_data.get('id'))
                            # フォーム再作成を試行
                            self.update_schema_form(current_dataset_data, force_clear=False)
                            
                            # フォーム再作成後、カスタム値を再設定
                            if hasattr(self.invoice_schema_form, 'set_form_data') and custom_values:
                                logger.debug("再作成後にカスタム値を設定")
                                self.invoice_schema_form.set_form_data(custom_values)
                                logger.debug("再設定完了")
                            else:
                                logger.debug("再作成後もset_form_dataメソッドが利用できません")
                        
                        # フォーム参照のクリアは不要（update_schema_formで更新済み）
                        
                except Exception as e:
                    logger.warning("カスタム値復元エラー: %s", e)
                    import traceback
                    traceback.print_exc()
            else:
                logger.debug("インボイススキーマフォームが存在しないため、カスタム値復元をスキップ")
            
            # 現在のファイルセットを記録
            self.current_fileset = file_set

            # ★ここでtarget_fileset_comboも同期する
            if hasattr(self, 'target_fileset_combo'):
                index = self.target_fileset_combo.findText(file_set.name)
                if index >= 0:
                    self.target_fileset_combo.setCurrentIndex(index)
            
            
        finally:
            # ファイルセット復元処理完了フラグをリセット
            self._restoring_fileset = False
            logger.debug("ファイルセット復元処理完了 - 自動設定適用を再有効化")
    
    def update_same_as_previous_option(self):
        """「前回と同じ」オプションの有効性をチェックして制御"""
        try:
            # 現在の「前回と同じ」オプションの状態を確認
            has_same_as_previous = False
            for i in range(self.sample_mode_combo.count()):
                if self.sample_mode_combo.itemText(i) == "前回と同じ":
                    has_same_as_previous = True
                    break
            
            # 条件をチェック: ファイルセットが複数 and 上位エントリーが存在
            should_enable_same_as_previous = False
            
            if self.file_set_manager and len(self.file_set_manager.file_sets) > 1:
                # 複数のファイルセットが存在する場合、上位エントリーをチェック
                current_fileset = self.fileset_table.get_selected_fileset()
                if current_fileset:
                    # 現在のファイルセットより前に登録されたエントリーがあるかチェック
                    current_index = -1
                    for i, fs in enumerate(self.file_set_manager.file_sets):
                        if fs.id == current_fileset.id:
                            current_index = i
                            break
                    
                    # 上位エントリー（現在のファイルセットより前のもの）が存在するかチェック
                    if current_index > 0:
                        # 直前のファイルセットに試料情報が設定されているかチェック
                        previous_fileset = self.file_set_manager.file_sets[current_index - 1]
                        extended_config = getattr(previous_fileset, 'extended_config', {})
                        
                        # 前のファイルセットに試料IDが設定されている場合のみ有効
                        if (extended_config.get('sample_id') or 
                            extended_config.get('sample_name') or 
                            extended_config.get('sample_mode') in ['既存試料使用', '新規作成']):
                            should_enable_same_as_previous = True
                            logger.debug("前回と同じオプション有効: 上位エントリー(%s)に試料情報あり", previous_fileset.name)
                        else:
                            logger.debug("前回と同じオプション無効: 上位エントリー(%s)に試料情報なし", previous_fileset.name)
                    else:
                        logger.debug("前回と同じオプション無効: 上位エントリーなし")
                else:
                    logger.debug("前回と同じオプション無効: ファイルセット未選択")
            else:
                if self.file_set_manager:
                    logger.debug("前回と同じオプション無効: ファイルセット数=%s", len(self.file_set_manager.file_sets))
                else:
                    logger.debug("前回と同じオプション無効: ファイルセットマネージャー未初期化")
            
            # オプションの追加/削除を制御
            if should_enable_same_as_previous and not has_same_as_previous:
                # 「前回と同じ」オプションを追加
                self.sample_mode_combo.addItem("前回と同じ")
                logger.info("「前回と同じ」オプションを追加")
            elif not should_enable_same_as_previous and has_same_as_previous:
                # 「前回と同じ」オプションを削除
                for i in range(self.sample_mode_combo.count()):
                    if self.sample_mode_combo.itemText(i) == "前回と同じ":
                        # 現在選択されている場合は、別のオプションに変更
                        if self.sample_mode_combo.currentIndex() == i:
                            self.sample_mode_combo.setCurrentIndex(0)  # 「新規作成」に変更
                        self.sample_mode_combo.removeItem(i)
                        logger.info("「前回と同じ」オプションを削除")
                        break
                        
        except Exception as e:
            logger.warning("前回と同じオプション制御エラー: %s", e)
            import traceback
            traceback.print_exc()

    def on_fileset_deleted(self, fileset_id: int):
        """ファイルセット削除処理"""
        if self.file_set_manager:
            self.file_set_manager.remove_fileset(fileset_id)
            self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
            self.update_summary()
            # ファイルセット削除後も「前回と同じ」オプションを再評価
            self.update_same_as_previous_option()
    
    def save_fileset_config(self):
        """ファイルセット設定保存（包括的フォームフィールド対応）"""
        selected_fileset = self.fileset_table.get_selected_fileset()
        if not selected_fileset:
            QMessageBox.information(self, "情報", "設定を保存するファイルセットを選択してください")
            return

        reply = _centered_question(
            self,
            "確認",
            f"ファイルセット「{selected_fileset.name}」を更新します。よろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        # 基本情報を更新
        selected_fileset.name = self.fileset_name_edit.text()
        selected_fileset.organize_method = (
            PathOrganizeMethod.ZIP if self.organize_method_combo.currentText() == "ZIP化" 
            else PathOrganizeMethod.FLATTEN
        )
        
        # データセットID取得
        selected_dataset_id = self.get_selected_dataset_id()
        selected_fileset.dataset_id = selected_dataset_id
        
        # データ情報を直接属性として保存
        selected_fileset.data_name = self.data_name_edit.text()
        selected_fileset.description = self.description_edit.toPlainText()
        selected_fileset.experiment_id = self.experiment_id_edit.text()
        selected_fileset.reference_url = self.reference_url_edit.text()
        selected_fileset.tags = self.tags_edit.text()
        
        # 試料情報を直接属性として保存
        sample_mode_text = self.sample_mode_combo.currentText()
        sample_mode_index = self.sample_mode_combo.currentIndex()
        logger.debug("試料モード状態確認:")
        logger.debug("- currentText(): '%s'", sample_mode_text)
        logger.debug("- currentIndex(): %s", sample_mode_index)
        logger.debug("- count(): %s", self.sample_mode_combo.count())
        for i in range(self.sample_mode_combo.count()):
            logger.debug("- itemText(%s): '%s'", i, self.sample_mode_combo.itemText(i))
        
        # 試料モード判定：index=0は新規作成、それ以外は既存試料選択
        if sample_mode_index == 0 or sample_mode_text == "新規作成":
            # 新規作成モード
            selected_fileset.sample_mode = "new"
            selected_fileset.sample_name = self.sample_name_edit.text()
            selected_fileset.sample_description = self.sample_description_edit.toPlainText()
            selected_fileset.sample_composition = self.sample_composition_edit.text()
            logger.debug("試料モード設定: new")
            logger.debug("- sample_name: %s", selected_fileset.sample_name)
            logger.debug("- sample_description: %s", selected_fileset.sample_description)
            logger.debug("- sample_composition: %s", selected_fileset.sample_composition)
        elif sample_mode_text == "前回と同じ":
            # 前回と同じモード
            selected_fileset.sample_mode = "same_as_previous"
            logger.debug("試料モード設定: same_as_previous")
        else:
            # 既存試料選択モード（index > 0 かつ "前回と同じ"以外）
            selected_fileset.sample_mode = "existing"
            
            # 統合コンボボックスの場合、sample_mode_comboのcurrentData()からUUIDを取得
            sample_data = self.sample_mode_combo.currentData()
            logger.debug("既存試料選択状態:")
            logger.debug("- sample_mode_combo.currentText(): '%s'", sample_mode_text)
            logger.debug("- sample_mode_combo.currentData(): %s", sample_data)
            logger.debug("- sample_data type: %s", type(sample_data))
            
            # sample_mode_comboの全データ内容も確認
            logger.debug("- sample_mode_combo全項目データ確認:")
            for idx in range(self.sample_mode_combo.count()):
                item_text = self.sample_mode_combo.itemText(idx)
                item_data = self.sample_mode_combo.itemData(idx)
                logger.debug("[%s] '%s' -> %s", idx, item_text, item_data)
            
            if sample_data and isinstance(sample_data, dict) and 'id' in sample_data:
                selected_fileset.sample_id = sample_data['id']
                logger.debug("既存試料ID保存成功（統合コンボボックス）: %s", sample_data['id'])
            else:
                # フォールバック：sample_id_comboがある場合はそちらを確認
                if hasattr(self, 'sample_id_combo'):
                    fallback_data = self.sample_id_combo.currentData()
                    if fallback_data and isinstance(fallback_data, dict) and 'id' in fallback_data:
                        selected_fileset.sample_id = fallback_data['id']
                        logger.debug("既存試料ID保存成功（フォールバック）: %s", fallback_data['id'])
                    else:
                        selected_fileset.sample_id = self.sample_mode_combo.currentText()
                        logger.warning("既存試料IDの取得に失敗、テキストを使用: %s", selected_fileset.sample_id)
                        logger.warning("- sample_data: %s", sample_data)
                        logger.warning("- fallback_data: %s", fallback_data if hasattr(self, 'sample_id_combo') else 'No sample_id_combo')
                else:
                    selected_fileset.sample_id = self.sample_mode_combo.currentText()
                    logger.warning("既存試料IDの取得に失敗（sample_id_combo無し）、テキストを使用: %s", selected_fileset.sample_id)
                    logger.warning("- sample_data: %s", sample_data)
            logger.debug("試料モード設定: existing")
        
        # カスタム値を取得（インボイススキーマフォーム）
        logger.debug("インボイススキーマフォーム状態確認:")
        logger.debug("- hasattr(self, 'invoice_schema_form'): %s", hasattr(self, 'invoice_schema_form'))
        if hasattr(self, 'invoice_schema_form'):
            logger.debug("- self.invoice_schema_form: %s", self.invoice_schema_form)
            logger.debug("- invoice_schema_form is not None: %s", self.invoice_schema_form is not None)
            
        if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form:
            try:
                # QGroupBoxの場合はget_schema_form_values関数を使用
                from classes.utils.schema_form_util import get_schema_form_values
                custom_values = get_schema_form_values(self.invoice_schema_form)
                selected_fileset.custom_values = custom_values
                logger.debug("カスタム値を保存: %s個の項目", len(custom_values))
                for key, value in custom_values.items():
                    logger.debug("%s: %s", key, value)
            except Exception as e:
                logger.warning("カスタム値取得エラー: %s", e)
                import traceback
                traceback.print_exc()
                selected_fileset.custom_values = {}
        else:
            logger.debug("インボイススキーマフォームが存在しません")
            # フォールバック: 既存のcustom_values属性を維持
            if hasattr(selected_fileset, 'custom_values'):
                logger.debug("既存のcustom_values属性を維持: %s", selected_fileset.custom_values)
            else:
                selected_fileset.custom_values = {}
                logger.debug("空のcustom_valuesを設定")
        
        # 拡張フィールドを辞書に保存（下位互換性のため）
        selected_fileset.extended_config = {
            # データ情報
            'data_name': self.data_name_edit.text(),  # data_nameも追加
            'description': self.description_edit.toPlainText(),
            'experiment_id': self.experiment_id_edit.text(),
            'reference_url': self.reference_url_edit.text(),
            'tags': self.tags_edit.text(),
            
            # 試料情報 - 内部値を保存
            'sample_mode': selected_fileset.sample_mode,  # 内部値（new/existing/same_as_previous）を使用
        }
        
        # 試料情報の詳細を条件付きで保存
        if sample_mode_text == "既存試料使用":
            # 既存試料の場合、currentData()からサンプルIDを取得
            sample_data = self.sample_id_combo.currentData()
            if sample_data and isinstance(sample_data, dict) and 'id' in sample_data:
                selected_fileset.extended_config['sample_id'] = sample_data['id']
                logger.debug("既存試料IDをextended_configに保存: %s", sample_data['id'])
            else:
                selected_fileset.extended_config['sample_id'] = self.sample_id_combo.currentText()
                logger.warning("既存試料IDの取得に失敗、extended_configにテキストを保存: %s", self.sample_id_combo.currentText())
        else:
            # 新規作成または前回と同じの場合
            selected_fileset.extended_config['sample_name'] = self.sample_name_edit.text()
            selected_fileset.extended_config['sample_description'] = self.sample_description_edit.toPlainText()
            selected_fileset.extended_config['sample_composition'] = self.sample_composition_edit.text()
        
        # カスタム値もextended_configに保存（データ登録時のフォーム値構築で利用）
        if hasattr(selected_fileset, 'custom_values') and selected_fileset.custom_values:
            selected_fileset.extended_config['custom_values'] = selected_fileset.custom_values
            logger.debug("カスタム値もextended_configに保存: %s個", len(selected_fileset.custom_values))
        else:
            selected_fileset.extended_config['custom_values'] = {}
        
        # テーブル更新
        self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
        
        # 「前回と同じ」オプションを再評価
        self.update_same_as_previous_option()
        
        # 最終確認：extended_configの内容をログ出力
        logger.debug("save_fileset_config完了 - extended_config内容:")
        for key, value in selected_fileset.extended_config.items():
            logger.debug("- %s: %s", key, value)
        logger.debug("save_fileset_config完了 - 直接属性:")
        logger.debug("- sample_mode: %s", getattr(selected_fileset, 'sample_mode', 'None'))
        logger.debug("- sample_id: %s", getattr(selected_fileset, 'sample_id', 'None'))
        
        # 成功メッセージ
        config_items = len([v for v in selected_fileset.extended_config.values() if v])
        QMessageBox.information(
            self, "完了", 
            f"ファイルセット設定を保存しました\n"
            f"保存項目: {config_items + 3}個（基本情報含む）"
        )
    
    def update_summary(self):
        """サマリー情報更新"""
        if not self.file_set_manager:
            self.summary_label.setText("ファイルセット: 0個、総ファイル数: 0、総サイズ: 0 B")
            self.estimate_label.setText("推定処理時間: -")
            return
        
        file_sets = self.file_set_manager.file_sets
        total_files = sum(fs.get_file_count() for fs in file_sets)
        total_size = sum(fs.get_total_size() for fs in file_sets)
        
        size_str = self._format_size(total_size)
        self.summary_label.setText(
            f"ファイルセット: {len(file_sets)}個、総ファイル数: {total_files}、総サイズ: {size_str}"
        )
        
        # 処理時間推定
        estimated_time = self._estimate_time(total_files, total_size)
        self.estimate_label.setText(f"推定処理時間: {estimated_time}")
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズをフォーマット"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _estimate_time(self, file_count: int, total_size: int) -> str:
        """処理時間を推定"""
        estimated_seconds = file_count * 2 + (total_size / (1024 * 1024)) * 0.1
        
        if estimated_seconds < 60:
            return f"約 {int(estimated_seconds)} 秒"
        elif estimated_seconds < 3600:
            minutes = int(estimated_seconds / 60)
            return f"約 {minutes} 分"
        else:
            hours = int(estimated_seconds / 3600)
            minutes = int((estimated_seconds % 3600) / 60)
            return f"約 {hours} 時間 {minutes} 分"
    
    def preview_batch_register(self):
        """一括登録プレビュー"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            QMessageBox.warning(self, "エラー", "実行するファイルセットがありません")
            return
        
        try:
            # 全ファイルセットに対して一時フォルダとマッピングファイルを確実に作成
            for file_set in self.file_set_manager.file_sets:
                self._ensure_temp_folder_and_mapping(file_set)
            
            # 一時フォルダ作成（フラット化・ZIP化対応） - 既存処理
            self._prepare_temp_folders()
            
            # v1.18.4: Bearer Tokenはapi_request_helperが自動選択するため、取得不要
            
            # 新しい詳細プレビューダイアログを表示
            from classes.data_entry.ui.batch_preview_dialog import BatchRegisterPreviewDialog
            
            allowed_exts = []
            try:
                if hasattr(self, 'fileset_table') and self.fileset_table:
                    allowed_exts = getattr(self.fileset_table, 'required_exts', []) or []
            except Exception:
                allowed_exts = []
            parallel_workers = 5
            try:
                parallel_workers = int(getattr(self, 'parallel_upload_spinbox', None).value())
            except Exception:
                parallel_workers = 5

            dialog = BatchRegisterPreviewDialog(
                self.file_set_manager.file_sets,
                self,
                bearer_token=None,
                allowed_exts=allowed_exts,
                parallel_upload_workers=parallel_workers,
            )
            result = dialog.exec()
            
            if result == QDialog.Accepted:
                # プレビューで検証済みのファイルセットを取得
                validated_file_sets = dialog.get_validated_file_sets()
                # ファイルセットマネージャーを更新（重複ファイル除外後）
                self.file_set_manager.file_sets = validated_file_sets
                # テーブル表示を更新
                self.fileset_table.load_file_sets(validated_file_sets)
                self.update_summary()
        
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プレビュー処理中にエラーが発生しました:\n{e}")
            logger.error("プレビューエラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def execute_batch_register(self):
        """一括登録実行（ファイルセットごとにデータ登録を自動実行）"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            QMessageBox.warning(self, "エラー", "実行するファイルセットがありません")
            return
        
        # v1.18.4: Bearer Tokenはapi_request_helperが自動選択するため、取得不要
        
        # 妥当性検証
        is_valid, errors = self.batch_logic.validate_filesets(self.file_set_manager.file_sets)
        if not is_valid:
            error_text = "以下のエラーがあります:\n\n" + "\n".join(errors)
            QMessageBox.warning(self, "検証エラー", error_text)
            return
        
        # 確認ダイアログ（親ウィンドウ中央に表示）
        try:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("確認")
            box.setText(
                f"{len(self.file_set_manager.file_sets)}個のファイルセットを一括登録しますか？\n\n"
                "この処理では以下が実行されます：\n"
                "1. 各ファイルセットのファイル一括アップロード\n"
                "2. 各ファイルセットのデータエントリー登録\n"
                "3. 試料情報の保存\n\n"
                "処理には時間がかかる場合があります。"
            )
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            try:
                from ..core.data_register_logic import _center_on_parent

                _center_on_parent(box, self.window())
            except Exception:
                pass
            reply = box.exec()
        except Exception:
            # フォールバック
            reply = QMessageBox.question(
                self,
                "確認",
                f"{len(self.file_set_manager.file_sets)}個のファイルセットを一括登録しますか？\n\n"
                "この処理では以下が実行されます：\n"
                "1. 各ファイルセットのファイル一括アップロード\n"
                "2. 各ファイルセットのデータエントリー登録\n"
                "3. 試料情報の保存\n\n"
                "処理には時間がかかる場合があります。",
                QMessageBox.Yes | QMessageBox.No,
            )
        
        if reply == QMessageBox.Yes:
            # 一括登録実行（複数ファイルセット一括処理）
            self._execute_multi_fileset_batch_register()
    
    def _execute_multi_fileset_batch_register(self):
        """
        複数ファイルセット一括登録処理
        v1.18.4: Bearer Token自動選択対応、bearer_tokenパラメータ削除
        """
        try:
            from .batch_preview_dialog import BatchRegisterPreviewDialog
            
            # 複数ファイルセット用のプレビューダイアログを作成して実行
            allowed_exts = []
            try:
                if hasattr(self, 'fileset_table') and self.fileset_table:
                    allowed_exts = getattr(self.fileset_table, 'required_exts', []) or []
            except Exception:
                allowed_exts = []
            parallel_workers = 5
            try:
                parallel_workers = int(getattr(self, 'parallel_upload_spinbox', None).value())
            except Exception:
                parallel_workers = 5

            batch_dialog = BatchRegisterPreviewDialog(
                file_sets=self.file_set_manager.file_sets,
                parent=self,
                bearer_token=None,  # v1.18.4: 自動選択に変更
                allowed_exts=allowed_exts,
                parallel_upload_workers=parallel_workers,
            )
            
            # プログレスダイアログの表示設定
            batch_dialog.show_progress_dialog = True
            
            # 確認ダイアログなしで直接一括データ登録を実行
            batch_dialog._batch_register_all_filesets_without_confirmation()
            
            # 結果を取得して表示
            if hasattr(batch_dialog, 'batch_result') and batch_dialog.batch_result:
                self.on_batch_register_finished(batch_dialog.batch_result)
            
        except Exception as e:
            logger.error("一括登録実行エラー: %s", e)
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"一括登録処理でエラーが発生しました:\n{str(e)}")
            
            # ファイルセットテーブルを更新して状態を反映
            if self.file_set_manager:
                self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
                self.update_summary()
    
    def on_batch_register_finished(self, result: BatchRegisterResult):
        """一括登録完了処理"""
        def _centered_box(icon, title: str, text: str) -> None:
            try:
                box = QMessageBox(self)
                box.setIcon(icon)
                box.setWindowTitle(title)
                box.setText(text)
                box.setStandardButtons(QMessageBox.Ok)
                try:
                    from ..core.data_register_logic import _center_on_parent

                    _center_on_parent(box, self.window())
                except Exception:
                    pass
                box.exec()
            except Exception:
                # フォールバック
                try:
                    if icon == QMessageBox.Information:
                        QMessageBox.information(self, title, text)
                    elif icon == QMessageBox.Warning:
                        QMessageBox.warning(self, title, text)
                    else:
                        QMessageBox.critical(self, title, text)
                except Exception:
                    pass

        # 結果表示
        if result.error_count == 0:
            _centered_box(
                QMessageBox.Information,
                "完了",
                f"一括登録が完了しました！\n\n"
                f"成功: {result.success_count}個\n"
                f"処理時間: {result.duration:.1f}秒",
            )
        else:
            error_text = f"一括登録が完了しました。\n\n"
            error_text += f"成功: {result.success_count}個\n"
            error_text += f"失敗: {result.error_count}個\n"
            error_text += f"処理時間: {result.duration:.1f}秒\n\n"
            error_text += "エラー詳細:\n"
            for fileset_name, error in result.errors[:5]:  # 最初の5個まで表示
                error_text += f"- {fileset_name}: {error}\n"
            
            if len(result.errors) > 5:
                error_text += f"... および他{len(result.errors)-5}個のエラー"
            
            _centered_box(QMessageBox.Warning, "完了（一部エラー）", error_text)
        
        # ファイルセット一覧をリセット（成功したもののみ残す）
        if self.file_set_manager:
            remaining_filesets = []
            for file_set in self.file_set_manager.file_sets:
                if file_set.name not in result.success_filesets:
                    remaining_filesets.append(file_set)
            
            self.file_set_manager.file_sets = remaining_filesets
            self.fileset_table.load_file_sets(remaining_filesets)
            self.update_summary()
    
    def load_initial_data(self):
        """初期データ読み込み（遅延ロード）"""
        # データセット一覧は使用時に読み込む（高速化のため）
        # 初期化時は何も読み込まない
        pass
    
    def refresh_datasets(self):
        """データセット一覧を更新（遅延ロード対応）"""
        # 通常登録の実装を使用している場合は、そちらで更新される
        if hasattr(self, 'dataset_dropdown_widget') and hasattr(self.dataset_dropdown_widget, 'dataset_dropdown'):
            # データセットドロップダウンが通常登録の実装を使用している場合は何もしない
            return
            
        # フォールバック処理
        try:
            self.datasets = get_filtered_datasets(['OWNER', 'ASSISTANT', 'MEMBER', 'AGENT'])
            self.update_dataset_combo()
        except Exception as e:
            logger.warning("データセット更新エラー: %s", e)
            # エラーダイアログは表示しない（起動時の遅延を防ぐため）
    
    def update_dataset_combo(self):
        """データセットコンボボックスを更新"""
        # 検証キャッシュはデータセット一覧フル更新時のみクリアする（個別エラーでの再構築は行わない方針）
        # ここではクリアしないことで不要な再検証ループを防止
        if not hasattr(self, '_invalid_datasets'):
            self._invalid_datasets = {}  # {dataset_id: error_type}
        
        self.dataset_combo.clear()
        
        if not self.datasets:
            self.dataset_combo.addItem("データセットが見つかりません")
            return
        
        # 最初の空のアイテムを追加
        self.dataset_combo.addItem("データセットを選択...")
        
        # データセットを追加
        for i, dataset in enumerate(self.datasets):
            dataset_id = dataset.get('id', '')
            attributes = dataset.get('attributes', {})
            title = attributes.get('title', 'タイトルなし')
            
            # エラーマーカーを追加
            error_marker = ""
            if hasattr(self, '_invalid_datasets') and dataset_id in self._invalid_datasets:
                error_type = self._invalid_datasets[dataset_id]
                if error_type == 'not_found':
                    error_marker = " [⚠️ 未検出]"
                elif error_type == 'unauthorized':
                    error_marker = " [⚠️ 認証エラー]"
                elif error_type == 'format_error':
                    error_marker = " [⚠️ フォーマットエラー]"
                else:
                    error_marker = " [⚠️ エラー]"
            
            # コンボボックス表示用のテキスト
            display_text = f"{title} ({dataset_id[:8]}...){error_marker}" if len(dataset_id) > 8 else f"{title} ({dataset_id}){error_marker}"
            
            # アイテムを追加（データとしてdataset_idを保存）
            self.dataset_combo.addItem(display_text, dataset_id)
            
            # 無効なデータセットは無効化
            if error_marker:
                from qt_compat.core import Qt
                model = self.dataset_combo.model()
                item = model.item(i + 1)  # +1 for placeholder
                if item:
                    item.setEnabled(False)
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
    
    def get_selected_dataset_id(self) -> Optional[str]:
        """選択されたデータセットIDを取得"""
        current_index = self.dataset_combo.currentIndex()
        current_text = self.dataset_combo.currentText()
        current_data = self.dataset_combo.currentData()
        
        logger.debug("get_selected_dataset_id: currentIndex=%s, currentText='%s'", current_index, current_text)
        
        # インデックス-1は選択なし状態
        if current_index < 0:
            logger.debug("get_selected_dataset_id: インデックス%sは選択なし状態", current_index)
            return None
        
        # currentDataからデータセットIDを取得
        if current_data:
            # 辞書オブジェクトの場合、'id'キーを取得
            if isinstance(current_data, dict) and 'id' in current_data:
                dataset_id = current_data['id']
                logger.debug("get_selected_dataset_id: 辞書からID取得=%s", dataset_id)
                return dataset_id
            # 文字列の場合はそのまま返す
            elif isinstance(current_data, str):
                logger.debug("get_selected_dataset_id: 文字列ID取得=%s", current_data)
                return current_data
        
        # currentDataが取得できない場合の代替手段
        if current_text and current_text != "データセットを選択...":
            # テキストからIDを抽出（"タイトル (dataset_id)" 形式）
            if "(" in current_text and ")" in current_text:
                try:
                    # "タイトル (12345678...)" → "12345678"
                    id_part = current_text.split("(")[-1].split(")")[0]
                    if "..." in id_part:
                        # 短縮表示の場合、self.datasetsから完全なIDを検索
                        id_prefix = id_part.replace("...", "")
                        for dataset in self.datasets:
                            if dataset.get('id', '').startswith(id_prefix):
                                logger.debug("get_selected_dataset_id: テキストから推定=%s", dataset.get('id'))
                                return dataset.get('id')
                    else:
                        logger.debug("get_selected_dataset_id: テキストから抽出=%s", id_part)
                        return id_part
                except Exception as e:
                    logger.debug("get_selected_dataset_id: テキスト解析エラー=%s", e)
        
        logger.debug("get_selected_dataset_id: データセットIDを取得できませんでした")
        return None

    def _relax_dataset_dropdown_filters(self) -> bool:
        """Ensure dropdown-level filters are reset before applying payload."""
        dropdown_widget = getattr(self, 'dataset_dropdown_widget', None)
        if dropdown_widget is None:
            return False

        relax_fn = getattr(dropdown_widget, 'relax_filters_for_launch', None)
        update_fn = getattr(dropdown_widget, 'update_datasets', None)

        try:
            if callable(relax_fn):
                relax_fn()
                return True
            if callable(update_fn):
                update_fn()
                return True
        except Exception:
            logger.debug("BatchRegisterWidget: dropdown filter relax failed", exc_info=True)
        return False

    def _load_dataset_record(self, dataset_id: str) -> Optional[dict]:
        if not dataset_id:
            return None
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        if not os.path.exists(dataset_path):
            return None
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            items = data.get('data') if isinstance(data, dict) else data
            for dataset in items or []:
                if isinstance(dataset, dict) and dataset.get('id') == dataset_id:
                    return dataset
        except Exception as exc:
            logger.debug("BatchRegisterWidget: dataset.json読み込み失敗 %s", exc)
        return None

    def _get_dataset_record(self, dataset_id: str) -> Optional[dict]:
        if not dataset_id:
            return None
        for dataset in self.datasets or []:
            if isinstance(dataset, dict) and dataset.get('id') == dataset_id:
                return dataset
        cached = self._dataset_lookup.get(dataset_id)
        if cached:
            return cached
        record = self._load_dataset_record(dataset_id)
        if record:
            self._dataset_lookup[dataset_id] = record
        return record

    def _format_dataset_display(self, dataset_dict: Optional[dict], fallback: str) -> str:
        if not isinstance(dataset_dict, dict):
            return fallback
        attrs = dataset_dict.get('attributes', {})
        grant = attrs.get('grantNumber') or ""
        name = attrs.get('name') or attrs.get('title') or ""
        parts = [part for part in (grant, name) if part]
        return " - ".join(parts) if parts else fallback

    def _ensure_dataset_in_combo(self, dataset_id: str, dataset_dict: Optional[dict], display_text: Optional[str]) -> int:
        if not dataset_id:
            return -1
        for idx in range(self.dataset_combo.count()):
            item_data = self.dataset_combo.itemData(idx)
            if isinstance(item_data, dict) and item_data.get('id') == dataset_id:
                return idx
            if isinstance(item_data, str) and item_data == dataset_id:
                return idx
        text = display_text or self._format_dataset_display(dataset_dict, dataset_id)
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.addItem(text, dataset_id if not isinstance(dataset_dict, dict) else dataset_dict)
        self.dataset_combo.blockSignals(False)
        return self.dataset_combo.count() - 1

    def _get_dataset_launch_payload(self) -> Optional[dict]:
        dataset_id = self.get_selected_dataset_id()
        if not dataset_id:
            QMessageBox.warning(self, "データセット未選択", "連携するデータセットを選択してください。")
            return None
        dataset_dict = self._get_dataset_record(dataset_id)
        display_text = self.dataset_combo.currentText() or dataset_id
        return {
            "dataset_id": dataset_id,
            "display_text": display_text,
            "raw_dataset": dataset_dict,
        }

    def _handle_dataset_launch(self, target_key: str) -> None:
        payload = self._get_dataset_launch_payload()
        if not payload:
            return
        DatasetLaunchManager.instance().request_launch(
            target_key=target_key,
            dataset_id=payload["dataset_id"],
            display_text=payload["display_text"],
            raw_dataset=payload["raw_dataset"],
            source_name="data_register_batch",
        )

    def _apply_dataset_launch_payload(self, payload: DatasetPayload) -> bool:
        if not payload or not payload.id:
            return False
        self._relax_dataset_dropdown_filters()
        dataset_dict = payload.raw or self._get_dataset_record(payload.id)
        if dataset_dict:
            self._dataset_lookup[payload.id] = dataset_dict
        index = self._ensure_dataset_in_combo(payload.id, dataset_dict, payload.display_text)
        if index < 0:
            return False
        previous_index = self.dataset_combo.currentIndex()
        self.dataset_combo.setCurrentIndex(index)
        if previous_index == index:
            try:
                self.on_dataset_changed(index)
            except Exception:
                logger.debug("BatchRegisterWidget: manual dataset refresh failed", exc_info=True)
        self._update_launch_buttons_state()
        return True
    
    def adjust_window_size(self):
        """一括登録用にウィンドウサイズを調整。

        - 表示中のタブに限って適用（他タブへ影響させない）
        - 初回のみ「画面幅の80%以上」へ拡大（ユーザー操作で可変）
        """
        try:
            if not getattr(self, "_batch_window_active", False):
                return
            if getattr(self, "_batch_window_size_initialized", False):
                return

            # 画面サイズを取得
            screen = QApplication.primaryScreen()
            if not screen:
                return
            
            screen_geometry = screen.geometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
            
            # 初回表示時の目標: 画面幅の80%以上（可変）
            target_width = int(screen_width * 0.80)
            target_width = min(target_width, max(0, screen_width - 40))
            
            logger.debug("画面サイズ: %sx%s", screen_width, screen_height)
            logger.debug("目標幅(80%%): %s", target_width)
            
            # 親ウィンドウを取得して調整
            top_level = self.window()
            if top_level and top_level != self:
                # 現在のサイズを確認
                current_size = top_level.size()
                current_width = current_size.width()
                current_height = current_size.height()

                # 幅が足りない場合のみ拡大（縮小はしない）
                if current_width < target_width and target_width > 0:
                    logger.info("ウィンドウ幅調整: %s → %s", current_width, target_width)
                    try:
                        top_level.resize(target_width, current_height)
                    except Exception:
                        pass

                # 初回調整完了（以後のボタン操作等では触らない）
                self._batch_window_size_initialized = True
                
        except Exception as e:
            logger.warning("ウィンドウサイズ調整に失敗: %s", e)
            import traceback
            traceback.print_exc()
    
    def _clear_fixed_width(self, window, target_width):
        """固定幅設定をクリアしてリサイズ可能にする"""
        try:
            window.resize(target_width, window.height())
            # 固定幅を解除するために最小・最大幅で範囲を設定
            screen = QApplication.primaryScreen()
            if screen:
                screen_width = screen.geometry().width()
                window.setMinimumWidth(1800)
                window.setMaximumWidth(screen_width)
            logger.info("固定幅制限を解除しました - リサイズ可能になりました")
        except Exception as e:
            logger.warning("固定幅クリアに失敗: %s", e)

    def _on_capacity_enable_toggled(self, enabled: bool):
        """容量制限有効/無効の切り替え"""
        try:
            self.capacity_spinbox.setEnabled(enabled)
            self.capacity_unit_combo.setEnabled(enabled)
            
            if enabled:
                logger.info("容量制限が有効になりました")
            else:
                logger.info("容量制限が無効になりました")
                
        except Exception as e:
            logger.error("容量制限切り替えエラー: %s", e)
    
    def _on_capacity_unit_changed(self, unit: str):
        """容量制限単位変更処理"""
        try:
            current_value = self.capacity_spinbox.value()
            
            if unit == "MB":
                # GBからMBに変換
                if self.capacity_spinbox.suffix() == " GB":
                    new_value = current_value * 1024
                    self.capacity_spinbox.setValue(min(new_value, 102400))  # 最大100GB
                    self.capacity_spinbox.setMaximum(102400)
                self.capacity_spinbox.setSuffix(" MB")
            else:  # GB
                # MBからGBに変換
                if self.capacity_spinbox.suffix() == " MB":
                    new_value = current_value / 1024
                    self.capacity_spinbox.setValue(max(new_value, 0.1))
                    self.capacity_spinbox.setMaximum(100.0)
                self.capacity_spinbox.setSuffix(" GB")
                
            logger.info("容量制限単位を %s に変更", unit)
            
        except Exception as e:
            logger.error("容量制限単位変更エラー: %s", e)
    
    def _get_capacity_limit_bytes(self) -> Optional[int]:
        """現在の容量制限をバイト単位で取得"""
        try:
            if not self.capacity_enable_cb.isChecked():
                return None
                
            value = self.capacity_spinbox.value()
            unit = self.capacity_unit_combo.currentText()
            
            if unit == "GB":
                return int(value * 1024 * 1024 * 1024)
            else:  # MB
                return int(value * 1024 * 1024)
                
        except Exception as e:
            logger.error("容量制限取得エラー: %s", e)
            return None
    
    def _apply_capacity_limit_to_filesets(self, file_sets: List[FileSet], capacity_limit: int) -> List[FileSet]:
        """容量制限をファイルセットに適用して分割"""
        try:
            logger.info("容量制限適用開始: %s 以下に分割", self._format_file_size(capacity_limit))
            
            # まずZIP階層競合を解決
            file_sets = self._resolve_zip_hierarchy_conflicts(file_sets)
            
            new_file_sets = []
            
            for file_set in file_sets:
                # ファイルセットの総サイズを計算
                total_size = self._calculate_fileset_size(file_set)
                logger.debug("ファイルセット '%s': %s", file_set.name, self._format_file_size(total_size))
                
                if total_size <= capacity_limit:
                    # 制限内なのでそのまま追加
                    new_file_sets.append(file_set)
                else:
                    # 分割が必要
                    split_sets = self._split_fileset_by_capacity(file_set, capacity_limit)
                    new_file_sets.extend(split_sets)
            
            logger.info("容量制限適用完了: %s → %s ファイルセット", len(file_sets), len(new_file_sets))
            
            # 分割後のファイルセットをマネージャーに設定
            self.file_set_manager.file_sets = new_file_sets
            
            return new_file_sets
            
        except Exception as e:
            logger.error("容量制限適用エラー: %s", e)
            import traceback
            traceback.print_exc()
            return file_sets  # エラー時は元のファイルセットを返す
    
    def _calculate_fileset_size(self, file_set: FileSet) -> int:
        """ファイルセットの総サイズを計算（バイト）"""
        try:
            total_size = 0
            for item in file_set.items:
                if item.file_type == FileType.FILE:
                    try:
                        size = os.path.getsize(item.path)
                        total_size += size
                    except (OSError, IOError):
                        # ファイルが見つからない等の場合は無視
                        pass
            return total_size
        except Exception as e:
            logger.error("ファイルセットサイズ計算エラー: %s", e)
            return 0
    
    def _split_fileset_by_capacity(self, file_set: FileSet, capacity_limit: int) -> List[FileSet]:
        """ファイルセットを容量制限で分割"""
        try:
            logger.info("ファイルセット '%s' を分割中...", file_set.name)
            
            # ファイルを容量順にソート（大きいファイルから優先）
            files_with_size = []
            for item in file_set.items:
                if item.file_type == FileType.FILE:
                    try:
                        size = os.path.getsize(item.path)
                        files_with_size.append((item, size))
                    except (OSError, IOError):
                        files_with_size.append((item, 0))
            
            # サイズでソート（降順）
            files_with_size.sort(key=lambda x: x[1], reverse=True)
            
            split_sets = []
            current_set_items = []
            current_set_size = 0
            set_counter = 1
            
            for item, size in files_with_size:
                # 単一ファイルが制限を超える場合は警告して独立したファイルセットにする
                if size > capacity_limit:
                    if current_set_items:
                        # 現在のセットを保存
                        new_set = FileSet(
                            id=file_set.id + set_counter * 1000,  # ユニークなID生成
                            name=f"{file_set.name}_分割{set_counter}",
                            base_directory=file_set.base_directory
                        )
                        new_set.items = current_set_items.copy()
                        new_set.organize_method = file_set.organize_method
                        split_sets.append(new_set)
                        set_counter += 1
                        current_set_items.clear()
                        current_set_size = 0
                    
                    # 大容量ファイルを独立セットとして作成
                    large_set = FileSet(
                        id=file_set.id + set_counter * 1000,  # ユニークなID生成
                        name=f"{file_set.name}_大容量{set_counter}",
                        base_directory=file_set.base_directory
                    )
                    large_set.items = [item]
                    large_set.organize_method = file_set.organize_method
                    split_sets.append(large_set)
                    set_counter += 1
                    
                    logger.warning("大容量ファイル (%s) を独立セットに分離: %s", self._format_file_size(size), item.name)
                    continue
                
                # 現在のセットに追加できるかチェック
                if current_set_size + size <= capacity_limit:
                    current_set_items.append(item)
                    current_set_size += size
                else:
                    # 現在のセットが満杯なので保存して新しいセットを開始
                    if current_set_items:
                        new_set = FileSet(
                            id=file_set.id + set_counter * 1000,  # ユニークなID生成
                            name=f"{file_set.name}_分割{set_counter}",
                            base_directory=file_set.base_directory
                        )
                        new_set.items = current_set_items.copy()
                        new_set.organize_method = file_set.organize_method
                        split_sets.append(new_set)
                        set_counter += 1
                    
                    # 新しいセットを開始
                    current_set_items = [item]
                    current_set_size = size
            
            # 最後のセットを保存
            if current_set_items:
                new_set = FileSet(
                    id=file_set.id + set_counter * 1000,  # ユニークなID生成
                    name=f"{file_set.name}_分割{set_counter}",
                    base_directory=file_set.base_directory
                )
                new_set.items = current_set_items.copy()
                new_set.organize_method = file_set.organize_method
                split_sets.append(new_set)
            
            logger.info("分割完了: %s 個のファイルセットに分割", len(split_sets))
            
            return split_sets
            
        except Exception as e:
            logger.error("ファイルセット分割エラー: %s", e)
            import traceback
            traceback.print_exc()
            return [file_set]  # エラー時は元のファイルセットを返す
    
    def _resolve_zip_hierarchy_conflicts(self, file_sets: List[FileSet]) -> List[FileSet]:
        """ZIP階層の競合を解決"""
        try:
            logger.info("ZIP階層競合チェック開始: %s ファイルセット", len(file_sets))
            
            # ZIP設定されているパスを収集
            zip_paths = set()
            for file_set in file_sets:
                if file_set.organize_method == PathOrganizeMethod.ZIP:
                    # このファイルセットに含まれるディレクトリパスを追加
                    for item in file_set.items:
                        if item.file_type == FileType.DIRECTORY:
                            zip_paths.add(os.path.normpath(item.path))
                        elif item.file_type == FileType.FILE:
                            # ファイルの親ディレクトリを追加
                            parent_dir = os.path.dirname(item.path)
                            zip_paths.add(os.path.normpath(parent_dir))
            
            conflicts_resolved = 0
            
            for file_set in file_sets:
                if file_set.organize_method == PathOrganizeMethod.ZIP:
                    continue  # ZIP設定はそのまま
                
                # 非ZIPファイルセットが ZIP ディレクトリ配下にあるかチェック
                items_to_keep = []
                items_removed = []
                
                for item in file_set.items:
                    item_path = os.path.normpath(item.path)
                    is_under_zip = False
                    
                    # ファイルの場合は親ディレクトリをチェック
                    if item.file_type == FileType.FILE:
                        check_path = os.path.dirname(item_path)
                    else:
                        check_path = item_path
                    
                    # ZIP設定されたパス配下にあるかチェック
                    for zip_path in zip_paths:
                        try:
                            # check_pathがzip_path配下にあるかチェック
                            rel_path = os.path.relpath(check_path, zip_path)
                            if not rel_path.startswith('..'):
                                is_under_zip = True
                                break
                        except ValueError:
                            # 異なるドライブ等の場合は無視
                            continue
                    
                    if is_under_zip:
                        items_removed.append(item)
                        conflicts_resolved += 1
                    else:
                        items_to_keep.append(item)
                
                # アイテムを更新
                if items_removed:
                    file_set.items = items_to_keep
                    logger.info("ファイルセット '%s': ZIP競合により %s 個のアイテムを除外", file_set.name, len(items_removed))
            
            # 空のファイルセットを除去
            non_empty_sets = [fs for fs in file_sets if fs.items]
            
            if conflicts_resolved > 0:
                print(f"[INFO] ZIP階層競合解決完了: {conflicts_resolved} 個のアイテムを調整, "
                      f"{len(file_sets) - len(non_empty_sets)} 個の空セットを除去")
            
            return non_empty_sets
            
        except Exception as e:
            logger.error("ZIP階層競合解決エラー: %s", e)
            import traceback
            traceback.print_exc()
            return file_sets  # エラー時は元のファイルセットを返す
    
    def _format_file_size(self, size_bytes: int) -> str:
        """ファイルサイズをフォーマット"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def on_dataset_focus_out(self, event):
        """データセット選択フォーカス外れ時の処理"""
        try:
            # 現在の入力値を確定
            current_text = self.dataset_combo.currentText()
            if current_text:
                # 一致するアイテムがあるか確認
                found_index = -1
                for i in range(self.dataset_combo.count()):
                    if self.dataset_combo.itemText(i) == current_text:
                        found_index = i
                        break
                
                if found_index >= 0 and found_index != self.dataset_combo.currentIndex():
                    self.dataset_combo.setCurrentIndex(found_index)
                    logger.info("データセット選択確定: %s", current_text)
                    
        except Exception as e:
            logger.warning("データセットフォーカス外れ処理エラー: %s", e)
    
    def on_dataset_changed(self, index):
        """データセット選択変更時の処理"""
        try:
            self._update_launch_buttons_state()
            logger.debug("データセット選択変更: index=%s", index)
            logger.debug("コンボボックス状態: currentText='%s', totalItems=%s", self.dataset_combo.currentText(), self.dataset_combo.count())
            
            # 選択されたデータセット情報を取得
            dataset_id = None
            dataset_data = None
            
            # index < 0 は選択なし状態のみ除外
            if index < 0:
                logger.debug("データセット未選択（index < 0）")
                self.clear_dynamic_fields()
                return
            
            # currentDataから取得
            try:
                current_data = self.dataset_combo.currentData()
                logger.debug("currentDataから取得したデータ: %s", type(current_data))
                
                if current_data:
                    # 辞書オブジェクトの場合、それがデータセット情報そのもの
                    if isinstance(current_data, dict) and 'id' in current_data:
                        dataset_id = current_data['id']
                        dataset_data = current_data
                        logger.debug("辞書からデータセット情報を取得: ID=%s", dataset_id)
                    # 文字列の場合、IDとして扱ってself.datasetsから検索
                    elif isinstance(current_data, str):
                        dataset_id = current_data
                        for dataset in self.datasets:
                            if dataset.get('id') == dataset_id:
                                dataset_data = dataset
                                logger.debug("IDからデータセット情報を特定: %s", dataset.get('attributes', {}).get('title', 'タイトルなし'))
                                break
                    
                    if not dataset_data:
                        logger.warning("データセットID %s に対応するデータセット情報が見つかりません", dataset_id)
                        return
            except Exception as e:
                logger.error("データセット取得に失敗: %s", e)
                return
            
            if dataset_id and dataset_data:
                logger.info("データセット選択確定: %s", dataset_id)
                
                # ========== データセット存在検証 ==========
                validation_result = self._validate_dataset_existence(dataset_id)
                if not validation_result['valid']:
                    if not hasattr(self, '_invalid_datasets'):
                        self._invalid_datasets = {}
                    self._invalid_datasets[dataset_id] = validation_result.get('error_type', 'other')
                    logger.warning("データセット検証失敗、次の有効なエントリへ移動: %s", dataset_id)
                    # 現在アイテムを即時マーク（再構築せずにテキスト更新＋無効化）
                    self._mark_dataset_invalid(index, dataset_id, validation_result.get('error_type', 'other'))
                    # 次の有効なデータセットへ移動
                    self._select_next_valid_dataset()
                    return
                # ==========================================
                
                # サンプル一覧を更新
                self.update_sample_list(dataset_id)
                
                # 実験ID一覧を更新
                self.update_experiment_list(dataset_id)
                
                # インボイススキーマフォームを更新
                logger.debug("update_schema_form呼び出し前: dataset_data=%s", dataset_data)
                self.update_schema_form(dataset_data)
                logger.debug("update_schema_form呼び出し後")
                
                # --- テンプレート対応拡張子表示を更新 ---
                template_id = None
                relationships = dataset_data.get('relationships', {})
                template = relationships.get('template', {}).get('data', {})
                if isinstance(template, dict):
                    template_id = template.get('id', '')
                
                resolved = self.batch_validator.resolve_template(template_id)
                self.batch_current_template_id = resolved.resolved_template_id or template_id
                if not self.batch_validator.is_formats_json_available():
                    self.batch_template_format_label.setText(
                        "⚠ 対応ファイル形式情報が読み込まれていません。\n"
                        "設定 → データ構造化タブでXLSXファイルを読み込んでください。"
                    )
                    self.batch_template_format_label.setStyleSheet(
                        f"padding: 8px; background-color: {get_color(ThemeKey.PANEL_WARNING_BACKGROUND)}; "
                        f"color: {get_color(ThemeKey.PANEL_WARNING_TEXT)}; "
                        f"border: 1px solid {get_color(ThemeKey.PANEL_WARNING_BORDER)}; border-radius: 4px;"
                    )
                else:
                    format_text = self.batch_validator.get_format_display_text(template_id)
                    ref_text = self.batch_validator.get_template_reference_text(template_id)
                    self.batch_template_format_label.setText(
                        f"📋 対応ファイル形式: {format_text}\n"
                        f"🧩 {ref_text}"
                    )
                    self.batch_template_format_label.setStyleSheet(
                        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
                        f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
                        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
                    )
                    # 対応拡張子をファイルセットテーブルへ反映し対象ファイル数を更新
                    try:
                        required_exts = self.batch_validator.get_extensions_for_template(self.batch_current_template_id)
                        if hasattr(self, 'fileset_table') and self.fileset_table:
                            self.fileset_table.set_required_extensions(required_exts)
                    except Exception as ext_e:
                        logger.warning("対応拡張子反映エラー: %s", ext_e)
                
                # データセット反映ログ（短時間重複抑制）
                now_ts = time.time()
                if not hasattr(self, '_last_reflected_dataset_id'):
                    self._last_reflected_dataset_id = None
                    self._last_reflected_time = 0.0
                if (self._last_reflected_dataset_id != dataset_id) or (now_ts - getattr(self, '_last_reflected_time', 0) > 1.0):
                    logger.info("データセット反映完了: %s", dataset_id)
                    self._last_reflected_dataset_id = dataset_id
                    self._last_reflected_time = now_ts
                else:
                    logger.debug("データセット反映ログ抑制: %s", dataset_id)
                
                # 選択されたファイルセットに設定を自動適用
                self.auto_apply_settings_to_selected()
            else:
                # データセット未選択時はクリア
                logger.debug("データセット未選択 - フィールドをクリア")
                self.clear_dynamic_fields()
                
        except Exception as e:
            logger.warning("データセット変更処理エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def _validate_dataset_existence(self, dataset_id: str) -> Dict[str, any]:
        """
        データセット存在検証（RDE API使用）
        
        Args:
            dataset_id: 検証するデータセットID
            
        Returns:
            Dict: {
                'valid': bool,           # 検証成功/失敗
                'status_code': int,      # HTTPステータスコード
                'error_type': str,       # エラー種別 ('not_found', 'unauthorized', 'network', 'other')
                'message': str           # ユーザー向けメッセージ
            }
        """
        try:
            # キャッシュ確認（既に検証済みのIDはスキップ）
            if not hasattr(self, '_verified_datasets'):
                self._verified_datasets = set()
            
            if dataset_id in self._verified_datasets:
                logger.debug("データセット存在検証スキップ（キャッシュ済み）: %s", dataset_id)
                return {'valid': True, 'status_code': 200, 'error_type': None, 'message': ''}
            
            # API呼び出し
            from config.site_rde import URLS
            from net.http_helpers import proxy_get
            
            detail_url = URLS['api']['dataset_detail'].format(id=dataset_id)
            logger.info("データセット存在検証開始: %s", dataset_id)
            logger.debug("[DATASET-VALIDATION] リクエストURL: %s", detail_url)
            
            # RDE API必須ヘッダー
            headers = {
                'Accept': 'application/vnd.api+json',
                'Content-Type': 'application/vnd.api+json'
            }
            
            resp = proxy_get(detail_url, headers=headers, timeout=10)
            
            # デバッグ: レスポンス詳細をログ出力
            logger.debug("[DATASET-VALIDATION] レスポンスステータス: %s", resp.status_code)
            logger.debug("[DATASET-VALIDATION] レスポンスヘッダー: %s", dict(resp.headers))
            if resp.status_code >= 400:
                try:
                    logger.error("[DATASET-VALIDATION] エラーレスポンスボディ: %s", resp.text[:500])
                except Exception:
                    pass
            
            # ステータスコード別処理
            if resp.status_code == 200:
                self._verified_datasets.add(dataset_id)
                logger.info("データセット存在確認成功: %s", dataset_id)
                return {'valid': True, 'status_code': 200, 'error_type': None, 'message': ''}
            
            elif resp.status_code == 404:
                logger.error("データセット未検出 (404): id=%s", dataset_id)
                return {
                    'valid': False,
                    'status_code': 404,
                    'error_type': 'not_found',
                    'message': f'データセットが存在しないか、アクセス権限がありません。\n\nデータセットID: {dataset_id}\n\nRDEサイトで該当データセットが開設されているか確認してください。'
                }
            
            elif resp.status_code == 401:
                    # 未認証: 選択段階で停止（再ログイン/権限確認を促す）
                    logger.error("未認証 (401) データセットアクセス拒否: id=%s", dataset_id)
                    return {
                        'valid': False,
                        'status_code': 401,
                        'error_type': 'unauthorized',
                        'message': (
                            'データセットにアクセスできません (401 Unauthorized)。\n\n'
                            f'Dataset ID: {dataset_id}\n'
                            'ログイン状態または権限を確認し、必要なら再ログインしてください。'
                        )
                    }
            
            elif resp.status_code == 422:
                # updateViews付きの詳細取得が 422 を返すケースがあるため、パラメータを取り除いたリカバリリクエストを試行
                logger.warning("データセット詳細取得が422を返却: id=%s。パラメータを省いた再取得を試行します", dataset_id)
                from config.site_rde import URL_RDE_API_BASE

                fallback_url = f"{URL_RDE_API_BASE}datasets/{dataset_id}"
                logger.debug("[DATASET-VALIDATION] フォールバックURL: %s", fallback_url)
                try:
                    fallback_resp = proxy_get(fallback_url, headers=headers, timeout=10)
                    if fallback_resp.status_code == 200:
                        self._verified_datasets.add(dataset_id)
                        logger.info("パラメータ簡略化後のデータセット取得に成功: %s", dataset_id)
                        return {'valid': True, 'status_code': 200, 'error_type': None, 'message': ''}
                    else:
                        try:
                            error_body = fallback_resp.text[:500]
                        except Exception:
                            error_body = ''
                        logger.error(
                            "データセット詳細取得失敗 (fallback): id=%s status=%s response=%s",
                            dataset_id,
                            fallback_resp.status_code,
                            error_body,
                        )
                        return {
                            'valid': False,
                            'status_code': fallback_resp.status_code,
                            'error_type': 'format_error',
                            'message': (
                                'データセット情報の取得に失敗しました (422)。\n'
                                f'対象ID: {dataset_id}\n'
                                '登録対象のデータセットが利用可能か、もしくはAPI仕様変更が発生していないかを確認してください。'
                            ),
                        }
                except Exception as fallback_error:
                    logger.error("データセット詳細再取得エラー: %s", fallback_error, exc_info=True)
                    raise
            
            else:
                logger.error("データセット取得失敗: id=%s status=%s", dataset_id, resp.status_code)
                return {
                    'valid': False,
                    'status_code': resp.status_code,
                    'error_type': 'other',
                    'message': f'データセット情報の取得に失敗しました。\n\nHTTPステータス: {resp.status_code}\nデータセットID: {dataset_id}'
                }
        
        except Exception as e:
            logger.error("データセット存在検証エラー: %s", e, exc_info=True)
            return {
                'valid': False,
                'status_code': 0,
                'error_type': 'network',
                'message': f'ネットワークエラーが発生しました。\n\nエラー内容: {str(e)}\n\n接続設定を確認してください。'
            }
    
    def _select_next_valid_dataset(self):
        """次の有効なデータセットを選択"""
        try:
            if not hasattr(self, '_invalid_datasets'):
                self._invalid_datasets = {}
            
            # 現在のインデックスから次の有効なエントリを探す
            current_index = self.dataset_combo.currentIndex()
            total_count = self.dataset_combo.count()
            
            for offset in range(1, total_count):
                next_index = (current_index + offset) % total_count
                
                # プレースホルダーをスキップ
                if next_index == 0:
                    continue
                
                next_dataset_id = self.dataset_combo.itemData(next_index)
                
                # 無効なデータセットをスキップ
                if next_dataset_id and next_dataset_id not in self._invalid_datasets:
                    logger.info("次の有効なデータセットへ移動: index=%s, id=%s", next_index, next_dataset_id)
                    self.dataset_combo.setCurrentIndex(next_index)
                    return
            
            # 有効なデータセットが見つからない場合はプレースホルダーに戻す
            logger.warning("有効なデータセットが見つかりませんでした")
            self.dataset_combo.setCurrentIndex(0)
            self.clear_dynamic_fields()
            
        except Exception as e:
            logger.error("次の有効なデータセット選択エラー: %s", e)
    
    def _mark_dataset_invalid(self, combo_index: int, dataset_id: str, error_type: str):
        """コンボボックス内の対象データセットをエラー表示＆無効化"""
        try:
            from qt_compat.core import Qt
            item_text = self.dataset_combo.itemText(combo_index)
            if not item_text:
                return
            # 既にマーク済みなら二重更新回避
            if '⚠' in item_text:
                return
            if error_type == 'not_found':
                marker = ' [⚠️ 未検出]'
            elif error_type == 'unauthorized':
                marker = ' [⚠️ 認証エラー]'
            elif error_type == 'format_error':
                marker = ' [⚠️ フォーマットエラー]'
            else:
                marker = ' [⚠️ エラー]'
            self.dataset_combo.setItemText(combo_index, f"{item_text}{marker}")
            # 無効化
            model = self.dataset_combo.model()
            item = model.item(combo_index)
            if item:
                item.setEnabled(False)
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            logger.debug("データセットを無効化: index=%s id=%s type=%s", combo_index, dataset_id, error_type)
        except Exception as e:
            logger.warning("データセット無効化処理エラー: %s", e)

    def _handle_dataset_validation_error(self, validation_result: Dict[str, any]):
        """
        データセット検証エラーのUIフィードバック
        
        Args:
            validation_result: _validate_dataset_existence の戻り値
        """
        error_type = validation_result.get('error_type')
        message = validation_result.get('message', '不明なエラーが発生しました。')
        
        # エラー種別に応じたアイコンとタイトル
        if error_type == 'not_found':
            icon = QMessageBox.Warning
            title = "データセット未検出"
        elif error_type == 'unauthorized':
            icon = QMessageBox.Warning
            title = "認証エラー"
        elif error_type == 'network':
            icon = QMessageBox.Critical
            title = "ネットワークエラー"
        else:
            icon = QMessageBox.Critical
            title = "エラー"
        
        # エラーダイアログ表示
        msg_box = QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        
        # データセットコンボボックスをクリア（不正な選択を解除）
        if hasattr(self, 'dataset_combo'):
            self.dataset_combo.setCurrentIndex(0)  # 最初の空白項目に戻す
            logger.info("データセット選択をクリアしました")
    
    def on_sample_mode_changed(self, mode):
        """試料選択変更時の処理（統合フォーム対応）"""
        try:
            logger.debug("試料選択変更: %s", mode)
            
            if mode == "新規作成":
                # 新規作成時は入力フィールドを有効化
                self.sample_name_edit.setEnabled(True)
                self.sample_description_edit.setEnabled(True)
                self.sample_composition_edit.setEnabled(True)
                # 入力フィールドをクリア
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                logger.debug("新規作成モード: 入力フィールドを有効化")
                
            
            elif mode == "既存試料を選択してください":
                # 既存試料選択時は入力フィールドを無効化
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                
                # 現在選択されているデータセットの試料リストを更新
                selected_dataset_id = self.get_selected_dataset_id()
                if selected_dataset_id:
                    logger.debug("既存試料選択モード: 試料リスト更新開始")
                    self.update_sample_list(selected_dataset_id)
                else:
                    logger.warning("既存試料選択モード: データセットが選択されていません")
                    
            elif mode == "前回と同じ":
                # 前回と同じ時は入力フィールドを無効化
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                
                # 前のファイルセットから試料情報を取得
                self._load_previous_sample_info()
                logger.debug("前回と同じモード: 前回の試料情報を読み込み")
                
            else:
                # 既存試料が選択された場合の処理
                current_data = self.sample_id_combo.currentData()
                if current_data and isinstance(current_data, dict):
                    # 既存試料情報を表示し、フィールドを無効化
                    self.sample_name_edit.setText(current_data.get('name', ''))
                    self.sample_description_edit.setText(current_data.get('description', ''))
                    self.sample_composition_edit.setText(current_data.get('composition', ''))
                    
                    self.sample_name_edit.setEnabled(False)
                    self.sample_description_edit.setEnabled(False)
                    self.sample_composition_edit.setEnabled(False)
                    logger.debug("既存試料選択: %s", current_data.get('name', ''))
                
        except Exception as e:
            logger.warning("試料選択変更処理エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def _load_previous_sample_info(self):
        """前のファイルセットの試料情報を読み込む"""
        try:
            if not self.file_set_manager or not self.file_set_manager.file_sets:
                self.sample_name_edit.setText("前のファイルセットがないため選択できません")
                return
            
            # 現在選択されているファイルセットのインデックスを取得
            current_fileset = getattr(self, 'current_fileset', None)
            if not current_fileset:
                self.sample_name_edit.setText("ファイルセットが選択されていません")
                return
            
            current_index = -1
            for i, fs in enumerate(self.file_set_manager.file_sets):
                if fs.id == current_fileset.id:
                    current_index = i
                    break
            
            if current_index <= 0:
                self.sample_name_edit.setText("前のファイルセットがありません")
                return
            
            # 前のファイルセットの試料情報を取得
            prev_fileset = self.file_set_manager.file_sets[current_index - 1]
            
            prev_sample_name = getattr(prev_fileset, 'sample_name', '') or prev_fileset.extended_config.get('sample_name', '')
            prev_sample_desc = getattr(prev_fileset, 'sample_description', '') or prev_fileset.extended_config.get('sample_description', '')
            prev_sample_comp = getattr(prev_fileset, 'sample_composition', '') or prev_fileset.extended_config.get('sample_composition', '')
            
            self.sample_name_edit.setText(prev_sample_name)
            self.sample_description_edit.setText(prev_sample_desc)
            self.sample_composition_edit.setText(prev_sample_comp)
            
            logger.debug("前回の試料情報を読み込み: %s", prev_sample_name)
            
        except Exception as e:
            logger.warning("前回試料情報読み込みエラー: %s", e)
            self.sample_name_edit.setText("前回の情報読み込みに失敗しました")
    
    def on_sample_selection_changed(self, index):
        """試料選択インデックス変更時の処理（既存試料選択用）"""
        try:
            current_text = self.sample_mode_combo.currentText()
            current_data = self.sample_mode_combo.currentData()
            
            logger.debug("試料選択インデックス変更: index=%s, text='%s'", index, current_text)
            
            # 既存試料が選択された場合（データが辞書の場合）
            if current_data and isinstance(current_data, dict):
                sample_name = current_data.get('name', '')
                sample_description = current_data.get('description', '')
                sample_composition = current_data.get('composition', '')
                
                # 既存試料情報を表示し、フィールドを無効化
                self.sample_name_edit.setText(sample_name)
                self.sample_description_edit.setText(sample_description)
                self.sample_composition_edit.setText(sample_composition)
                
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                
                logger.info("既存試料情報を表示: %s", sample_name)
            
        except Exception as e:
            logger.warning("試料選択インデックス変更エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_sample_list(self, dataset_id):
        """選択されたデータセットのサンプル一覧を更新（統合コンボボックス対応）"""
        try:
            logger.debug("サンプル一覧更新開始: dataset_id=%s", dataset_id)
            
            # 統合コンボボックスの既存項目を記録
            default_items = ["新規作成", "前回と同じ"]
            
            # 統合コンボボックスをクリアして基本項目を追加
            self.sample_mode_combo.clear()
            for item in default_items:
                self.sample_mode_combo.addItem(item)
            
            # データセットIDが有効な場合、関連サンプルを取得して追加
            if dataset_id:
                try:
                    # 通常登録と同じ方法でデータセット情報を取得
                    from classes.data_entry.util.data_entry_filter_util import get_datasets_for_data_entry
                    
                    datasets = get_datasets_for_data_entry()
                    target_dataset = None
                    
                    for dataset in datasets:
                        if str(dataset.get('id', '')) == str(dataset_id):
                            target_dataset = dataset
                            break
                    
                    if target_dataset:
                        logger.debug("対象データセット取得成功: %s", target_dataset.get('attributes', {}).get('name', ''))
                        
                        # データセットに紐づくグループIDを取得（通常登録と同じ方法）
                        group_id = None
                        
                        try:
                            # 方法1: 通常登録と同じようにdatasetファイルからグループIDを取得
                            dataset_id = target_dataset.get('id', '')
                            if dataset_id:
                                import os
                                from config.common import get_dynamic_file_path
                                
                                dataset_json_path = get_dynamic_file_path(f'output/rde/data/datasets/{dataset_id}.json')
                                logger.debug("データセットファイル確認: %s", dataset_json_path)
                                
                                if os.path.exists(dataset_json_path):
                                    import json
                                    with open(dataset_json_path, 'r', encoding='utf-8') as f:
                                        dataset_data = json.load(f)
                                        relationships = dataset_data.get("data", {}).get('relationships', {})
                                        group = relationships.get('group', {}).get('data', {})
                                        group_id = group.get('id', '')
                                        logger.debug("データセットファイルからグループID取得: %s", group_id)
                                else:
                                    logger.debug("データセットファイルが存在しません: %s", dataset_json_path)
                            
                            # 方法2: フォールバック - APIレスポンスから直接取得
                            if not group_id:
                                relationships = target_dataset.get('relationships', {})
                                group_data = relationships.get('group', {}).get('data', {})
                                if not group_data:
                                    group_data = relationships.get('subgroup', {}).get('data', {})
                                
                                if group_data and group_data.get('id'):
                                    group_id = group_data.get('id')
                                    logger.debug("APIレスポンスからグループID取得: %s", group_id)
                            
                            if group_id:
                                logger.debug("最終決定グループID: %s", group_id)
                            else:
                                logger.warning("全ての方法でグループID取得失敗")
                                
                        except Exception as e:
                            logger.warning("グループID取得エラー: %s", e)
                            import traceback
                            traceback.print_exc()
                        
                        if group_id:
                            logger.debug("最終決定グループID: %s", group_id)
                            
                            # 通常登録のsample_loaderを使用
                            from classes.data_entry.util.sample_loader import load_existing_samples, format_sample_display_name
                            
                            existing_samples = load_existing_samples(group_id)
                            logger.debug("既存試料データ取得: %s件", len(existing_samples))
                            
                            if existing_samples:
                                for sample in existing_samples:
                                    display_name = format_sample_display_name(sample)
                                    self.sample_mode_combo.addItem(display_name, sample)
                                    logger.debug("既存試料追加: %s", display_name)
                                
                                logger.info("既存試料を統合コンボボックスに追加完了: %s件", len(existing_samples))
                            else:
                                logger.debug("既存試料データなし")
                        else:
                            logger.warning("グループID/サブグループIDが取得できません")
                    else:
                        logger.warning("対象データセットが見つかりません: %s", dataset_id)
                    
                except Exception as e:
                    logger.warning("サンプル情報取得失敗: %s", e)
                    import traceback
                    traceback.print_exc()
            else:
                logger.debug("データセットIDが無効")
            
            logger.debug("サンプル一覧更新完了: %s個の選択肢", self.sample_mode_combo.count())
            
        except Exception as e:
            logger.warning("サンプル一覧更新エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_experiment_list(self, dataset_id):
        """選択されたデータセットの実験ID一覧を更新（入力フィールドなので何もしない）"""
        try:
            logger.debug("実験ID一覧更新開始: dataset_id=%s", dataset_id)
            
            # 実験IDは入力フィールドになったため、リスト更新は不要
            logger.debug("実験ID一覧更新完了: 入力フィールドのため処理なし")
            
        except Exception as e:
            logger.warning("実験ID一覧更新エラー: %s", e)
            import traceback
            traceback.print_exc()

    def _schema_form_has_fields(self) -> bool:
        """現在の固有情報フォームに表示対象フィールドがあるかを返す。"""
        form = getattr(self, 'invoice_schema_form', None)
        key_to_widget = getattr(form, '_schema_key_to_widget', None) if form is not None else None
        return isinstance(key_to_widget, dict) and bool(key_to_widget)

    def _sync_schema_form_visibility(self) -> None:
        """固有情報トグル状態に合わせてフォーム本体の可視性を同期する。"""
        toggle = getattr(self, '_schema_toggle', None)
        edit_mode = toggle is not None and toggle.mode() == 'edit'
        has_fields = self._schema_form_has_fields()

        form = getattr(self, 'invoice_schema_form', None)
        if form is not None:
            try:
                form.setVisible(bool(edit_mode and has_fields))
            except Exception:
                logger.debug("schema form visibility sync failed", exc_info=True)

        placeholder = getattr(self, 'schema_placeholder_label', None)
        if placeholder is not None:
            try:
                placeholder.setVisible(bool(edit_mode and not has_fields))
            except Exception:
                logger.debug("schema placeholder visibility sync failed", exc_info=True)
    
    def update_schema_form(self, dataset_data, force_clear=True):
        """インボイススキーマに基づく固有情報フォームを更新（通常登録と同等機能）"""
        try:
            logger.debug("スキーマフォーム更新開始: %s", dataset_data)
            
            # フォーム重複を防ぐため、常に既存フォームをクリア
            # 復元モードでも既存フォームが存在すれば必ずクリアする
            if force_clear:
                logger.debug("既存フォームをクリア中...")
                self.clear_schema_form()
            else:
                # 復元モードでも重複を防ぐため、既存フォームが存在すればクリアする
                if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form is not None:
                    logger.debug("復元モードですが既存フォームをクリア中（重複防止）...")
                    self.clear_schema_form()
                else:
                    logger.debug("復元モード：既存フォームなし、クリアをスキップ")

            # データセットのスキーマ情報を取得
            dataset_id = dataset_data.get('id', '')
            attributes = dataset_data.get('attributes', {})
            dataset_name = attributes.get('name', '')
            relationships = dataset_data.get('relationships', {})

            if dataset_id:
                logger.info("スキーマフォーム生成: %s (%s)", dataset_name, dataset_id)
                try:
                    # 通常登録と同じ方法でテンプレートIDを取得
                    template_id = ''
                    template = relationships.get('template', {}).get('data', {})
                    if isinstance(template, dict):
                        template_id = template.get('id', '')
                    logger.debug("テンプレートID: %s", template_id)
                    if template_id:
                        # 通常登録と同じパスでinvoiceSchemaを確認
                        from config.common import get_dynamic_file_path
                        from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
                        
                        invoice_schema_path = get_dynamic_file_path(f'output/rde/data/invoiceSchemas/{template_id}.json')
                        try:
                            self._current_invoice_schema_path = invoice_schema_path
                        except Exception:
                            pass
                        
                        logger.debug("invoiceSchemaファイル確認: %s", invoice_schema_path)
                        
                        import os
                        if os.path.exists(invoice_schema_path):
                            logger.info("invoiceSchemaファイル発見: %s", invoice_schema_path)
                            
                            # フォーム生成時に適切な親ウィジェットを指定（スクロール領域内に配置）
                            schema_form = create_schema_form_from_path(invoice_schema_path, self.scroll_widget)
                            
                            if schema_form:
                                logger.info("インボイススキーマフォーム生成成功")
                                
                                # フォームの親ウィジェットを明示的に設定
                                schema_form.setParent(self.scroll_widget)
                                
                                # 独立ダイアログ表示を完全に防ぐ
                                schema_form.setWindowFlags(Qt.Widget)
                                schema_form.setWindowModality(Qt.NonModal)
                                schema_form.setAttribute(Qt.WA_DeleteOnClose, False)
                                
                                # 表示関連メソッドを抑制
                                schema_form.setVisible(False)  # いったん非表示
                                
                                logger.debug("フォーム親ウィジェット設定完了: %s", type(self.scroll_widget))
                                logger.debug("フォームフラグ設定: %s", schema_form.windowFlags())
                                logger.debug("フォーム可視性制御: visible=%s", schema_form.isVisible())
                                logger.debug("scroll_widget object id: %s", id(self.scroll_widget))
                                logger.debug("schema_form object id: %s", id(schema_form))
                                
                                # レイアウト重複確認
                                widget_count_before = self.schema_form_layout.count()
                                logger.debug("フォーム追加前のレイアウト項目数: %s", widget_count_before)
                                
                                # プレースホルダーを非表示
                                self.schema_placeholder_label.hide()
                                
                                # 動的生成フォームを追加
                                self.schema_form_layout.addWidget(schema_form)
                                self.schema_form = schema_form  # 保存（後で値取得で使用）
                                self.invoice_schema_form = schema_form  # 互換性のため（save_fileset_configで使用）

                                self._sync_schema_form_visibility()

                                try:
                                    refresher = getattr(self, '_refresh_schema_summary', None)
                                    if callable(refresher):
                                        refresher()
                                except Exception:
                                    pass
                                
                                widget_count_after = self.schema_form_layout.count()
                                logger.debug("フォーム追加後のレイアウト項目数: %s", widget_count_after)
                                logger.debug("レイアウト追加後の可視性: %s", schema_form.isVisible())
                                logger.debug("レイアウト追加後の親: %s", type(schema_form.parent()))
                                
                                logger.debug("invoice_schema_form 設定完了: %s", type(schema_form))
                                logger.info("インボイススキーマフォーム表示完了")
                            else:
                                logger.warning("スキーマフォーム生成失敗")
                                # フォーム生成失敗時のみ空フォームを作成
                                self._create_empty_schema_form()
                                self.schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマフォーム生成に失敗しました")
                                self.schema_placeholder_label.show()
                        else:
                            logger.info("invoiceSchemaファイル未発見: %s", invoice_schema_path)
                            # インボイススキーマファイルがない場合のみ空フォームを作成
                            self._create_empty_schema_form()
                            self.schema_placeholder_label.setText(f"データセット '{dataset_name}' にはカスタム固有情報がありません")
                            self.schema_placeholder_label.show()
                    else:
                        logger.debug("テンプレートIDが無効")
                        # テンプレートIDがない場合でも空フォームを作成
                        self._create_empty_schema_form()
                        self.schema_placeholder_label.setText(f"データセット '{dataset_name}' にテンプレートIDがありません")
                        self.schema_placeholder_label.show()
                    
                except Exception as e:
                    logger.warning("スキーマ処理失敗: %s", e)
                    import traceback
                    traceback.print_exc()
                    
                    # エラー時も空フォームを作成
                    self._create_empty_schema_form()
                    self.schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマ処理でエラーが発生しました")
                    self.schema_placeholder_label.show()
            else:
                logger.debug("データセットIDが無効")
                # データセットIDがない場合でも空フォームを作成
                self._create_empty_schema_form()
                self.schema_placeholder_label.setText("データセットを選択してください")
                self.schema_placeholder_label.show()
            
            logger.debug("スキーマフォーム更新完了")
            
        except Exception as e:
            logger.warning("スキーマフォーム更新エラー: %s", e)
            import traceback
            traceback.print_exc()
            
            # エラー時も空フォームを作成して参照を確保
            self._create_empty_schema_form()
            
            # エラー時はプレースホルダー表示
            self.schema_placeholder_label.setText("スキーマフォーム更新でエラーが発生しました")
            self.schema_placeholder_label.show()
    
    def clear_dynamic_fields(self):
        """動的フィールドをクリア"""
        try:
            if hasattr(self, 'sample_id_combo') and self.sample_id_combo is not None:
                self.sample_id_combo.clear()
            if hasattr(self, 'experiment_id_combo') and self.experiment_id_combo is not None:
                self.experiment_id_combo.clear()
            self.clear_schema_form()
            
        except Exception as e:
            logger.warning("動的フィールドクリアエラー: %s", e)
    
    def clear_schema_form(self):
        """スキーマフォームをクリア"""
        try:
            widget_count_before = self.schema_form_layout.count()
            logger.debug("フォームクリア開始：現在のレイアウト項目数=%s", widget_count_before)
            
            # 現在のフォーム参照状況をログ出力
            logger.debug("現在のフォーム参照: schema_form=%s, invoice_schema_form=%s", getattr(self, 'schema_form', None), getattr(self, 'invoice_schema_form', None))
            
            # 動的に生成されたフォーム要素を削除
            removed_count = 0
            for i in reversed(range(self.schema_form_layout.count())):
                child = self.schema_form_layout.itemAt(i).widget()
                if child and child != self.schema_placeholder_label:
                    logger.debug("ウィジェットを削除: %s", type(child).__name__)
                    child.setParent(None)
                    removed_count += 1
            
            logger.debug("削除されたウィジェット数: %s", removed_count)
            
            # フォーム参照をクリア
            self.schema_form = None
            self.invoice_schema_form = None
            
            logger.debug("フォーム参照クリア完了: schema_form=%s, invoice_schema_form=%s", self.schema_form, self.invoice_schema_form)
            
            # プレースホルダーを表示
            self.schema_placeholder_label.setText("データセット選択後に固有情報入力フォームが表示されます")
            self.schema_placeholder_label.show()
            self._sync_schema_form_visibility()

            try:
                refresher = getattr(self, '_refresh_schema_summary', None)
                if callable(refresher):
                    refresher()
            except Exception:
                pass
            
        except Exception as e:
            logger.warning("スキーマフォームクリアエラー: %s", e)
    
    def _create_empty_schema_form(self):
        """空のインボイススキーマフォームを作成（参照確保用）"""
        try:
            from qt_compat.widgets import QGroupBox, QVBoxLayout, QLabel
            
            # 空のグループボックスを作成（親ウィジェットをスクロール領域に設定）
            empty_form = QGroupBox("固有情報", self.scroll_widget)
            empty_layout = QVBoxLayout()
            empty_layout.addWidget(QLabel("このデータセットには固有情報項目がありません"))
            empty_form.setLayout(empty_layout)
            empty_form.setVisible(False)  # 非表示にする
            
            # 必要なメソッドを追加
            def get_form_data():
                return {}
            
            def set_form_data(data):
                pass
                
            def clear_form():
                pass
            
            empty_form.get_form_data = get_form_data
            empty_form.set_form_data = set_form_data
            empty_form.clear_form = clear_form
            
            # レイアウトに追加（非表示）
            self.schema_form_layout.addWidget(empty_form)
            
            # 参照を設定
            self.schema_form = empty_form
            self.invoice_schema_form = empty_form
            self._sync_schema_form_visibility()

            try:
                refresher = getattr(self, '_refresh_schema_summary', None)
                if callable(refresher):
                    refresher()
            except Exception:
                pass
            
            logger.debug("空のinvoice_schema_form作成完了: %s", type(empty_form))
            
        except Exception as e:
            logger.error("空フォーム作成エラー: %s", e)
            # フォールバック: 最低限のオブジェクトを作成
            class EmptyForm:
                def get_form_data(self):
                    return {}
                def set_form_data(self, data):
                    pass
                def clear_form(self):
                    pass
            
            self.invoice_schema_form = EmptyForm()
            logger.debug("フォールバック空フォーム作成: %s", type(self.invoice_schema_form))

    def apply_to_selected_filesets(self):
        """現在の設定を選択されたファイルセットに適用"""
        if not hasattr(self, 'target_fileset_combo'):
            QMessageBox.warning(self, "エラー", "ファイルセット選択コンボボックスが初期化されていません。")
            return
            
        target_name = self.target_fileset_combo.currentText()
        if not target_name:
            QMessageBox.information(self, "情報", "適用対象のファイルセットが選択されていません。")
            return
        
        # 対象のファイルセットを検索
        target_fileset = None
        if self.file_set_manager:
            for fileset in self.file_set_manager.file_sets:
                if fileset.name == target_name:
                    target_fileset = fileset
                    break
        
        if not target_fileset:
            QMessageBox.warning(self, "エラー", f"ファイルセット '{target_name}' が見つかりません。")
            return
        
        try:
            # 現在の設定を取得
            settings = self.get_current_settings()
            self._apply_settings_to_fileset(target_fileset, settings)
            QMessageBox.information(self, "完了", f"ファイルセット '{target_name}' に設定を適用しました。")
            self.refresh_fileset_display()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
    
    def setup_dataset_refresh_notification(self):
        """データセット更新通知システムに登録"""
        try:
            from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
            dataset_notifier = get_dataset_refresh_notifier()
            dataset_notifier.register_callback(self.refresh_dataset_list)
            logger.info("一括登録ウィジェット: データセット更新通知に登録完了")
            
            # ウィジェット破棄時の通知解除用
            def cleanup_callback():
                dataset_notifier.unregister_callback(self.refresh_dataset_list)
                logger.info("一括登録ウィジェット: データセット更新通知を解除")
            
            self._cleanup_dataset_callback = cleanup_callback
            
        except Exception as e:
            logger.warning("データセット更新通知への登録に失敗: %s", e)
    
    def refresh_dataset_list(self):
        """データセットリストを更新"""
        try:
            # dataset_dropdown_widgetがある場合は、それを使用して更新
            if hasattr(self, 'dataset_dropdown_widget') and self.dataset_dropdown_widget:
                logger.info("一括登録: dataset_dropdown_widget経由でデータセットリスト更新開始")
                # dataset_dropdown_widgetのrefresh機能を呼び出し
                if hasattr(self.dataset_dropdown_widget, 'refresh_datasets'):
                    self.dataset_dropdown_widget.refresh_datasets()
                    logger.info("一括登録: dataset_dropdown_widget更新完了")
                return
            
            # 代替手段：dataset_comboが存在する場合の処理
            if not hasattr(self, 'dataset_combo') or not self.dataset_combo or self.dataset_combo.parent() is None:
                logger.debug("データセットコンボボックスが破棄されているため更新をスキップ")
                return
            
            logger.info("一括登録: dataset_combo経由でデータセットリスト更新開始")
            
            # 現在選択されているアイテムのIDを保存
            current_dataset_id = None
            current_index = self.dataset_combo.currentIndex()
            if current_index > 0:  # 0番目は通常「選択してください」
                current_data = self.dataset_combo.itemData(current_index)
                if current_data:
                    current_dataset_id = current_data.get("id")
            
            # データセットリストを再読み込み
            self.refresh_datasets()
            
            # 以前の選択を復元
            if current_dataset_id:
                for i in range(self.dataset_combo.count()):
                    item_data = self.dataset_combo.itemData(i)
                    if item_data and item_data.get("id") == current_dataset_id:
                        self.dataset_combo.setCurrentIndex(i)
                        logger.info("一括登録: データセット選択を復元: %s", current_dataset_id)
                        break
            
            logger.info("一括登録: データセットリスト更新完了")
            
        except Exception as e:
            logger.error("一括登録: データセットリスト更新に失敗: %s", e)
    
    def closeEvent(self, event):
        """ウィジェット終了時の処理"""
        try:
            if hasattr(self, '_cleanup_dataset_callback'):
                self._cleanup_dataset_callback()
        except Exception as e:
            logger.warning("データセット更新通知の解除に失敗: %s", e)
        super().closeEvent(event)


# QInputDialogのインポートを追加
from qt_compat.widgets import QInputDialog


class FilesetConfigDialog(QDialog):
    """ファイルセット設定専用ダイアログ"""
    
    def __init__(self, parent, fileset: FileSet):
        super().__init__(parent)
        self.fileset = fileset
        self.parent_widget = parent
        self.setup_ui()
        self.load_fileset_data()
        
    def setup_ui(self):
        """ダイアログUI初期化"""
        self.setWindowTitle(f"ファイルセット設定 - {self.fileset.name}")
        self.setModal(True)
        
        # ダイアログサイズを画面に合わせて調整
        screen = QApplication.primaryScreen()
        if screen:
            screen_size = screen.geometry()
            width = min(800, int(screen_size.width() * 0.6))
            height = min(700, int(screen_size.height() * 0.8))
            self.resize(width, height)
        else:
            self.resize(800, 700)
        
        layout = QVBoxLayout(self)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # 基本情報
        basic_group = QGroupBox("基本情報")
        basic_layout = QGridLayout()
        
        basic_layout.addWidget(QLabel("ファイルセット名:"), 0, 0)
        self.fileset_name_edit = QLineEdit()
        basic_layout.addWidget(self.fileset_name_edit, 0, 1)
        
        basic_layout.addWidget(QLabel("整理方法:"), 1, 0)
        self.organize_method_combo = QComboBox()
        self.organize_method_combo.addItems(["フラット化", "ZIP化"])
        basic_layout.addWidget(self.organize_method_combo, 1, 1)
        
        basic_group.setLayout(basic_layout)
        scroll_layout.addWidget(basic_group)
        
        # データセット選択（メインウィンドウと同じ実装を使用）
        dataset_group = QGroupBox("データセット選択")
        dataset_layout = QVBoxLayout()
        
        # 検索可能なデータセット選択ウィジェットを作成（メインウィンドウと同じ）
        try:
            from classes.data_entry.util.data_entry_filter_checkbox import create_checkbox_filter_dropdown
            self.dataset_dropdown_widget = create_checkbox_filter_dropdown(self)
            self.dataset_dropdown_widget.setMinimumWidth(400)
            dataset_layout.addWidget(self.dataset_dropdown_widget)
            
            # 実際のコンボボックスを取得
            if hasattr(self.dataset_dropdown_widget, 'dataset_dropdown'):
                self.dataset_combo = self.dataset_dropdown_widget.dataset_dropdown
            else:
                # フォールバック
                raise ImportError("dataset_dropdown not found")
                
        except ImportError:
            # フォールバック：基本コンボボックス + 検索機能
            from classes.dataset.util.dataset_dropdown_util import create_dataset_dropdown_with_user
            from config.common import DATASET_JSON_PATH, INFO_JSON_PATH
            
            self.dataset_dropdown_widget = create_dataset_dropdown_with_user(
                DATASET_JSON_PATH, INFO_JSON_PATH, self
            )
            dataset_layout.addWidget(self.dataset_dropdown_widget)
            
            # 実際のコンボボックスを取得
            if hasattr(self.dataset_dropdown_widget, 'dataset_dropdown'):
                self.dataset_combo = self.dataset_dropdown_widget.dataset_dropdown
            else:
                # 最終フォールバック
                self.dataset_combo = QComboBox()
                self.dataset_combo.setEditable(True)
                self.dataset_combo.setMinimumWidth(400)
                dataset_layout.addWidget(self.dataset_combo)
        
        dataset_group.setLayout(dataset_layout)
        scroll_layout.addWidget(dataset_group)
        
        # データ情報
        data_group = QGroupBox("データ情報")
        data_layout = QGridLayout()
        
        data_layout.addWidget(QLabel("データ名:"), 0, 0)
        self.data_name_edit = QLineEdit()
        data_layout.addWidget(self.data_name_edit, 0, 1)
        
        data_layout.addWidget(QLabel("データ説明:"), 1, 0)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        data_layout.addWidget(self.description_edit, 1, 1)
        
        data_layout.addWidget(QLabel("実験ID:"), 2, 0)
        self.experiment_id_combo = QComboBox()
        self.experiment_id_combo.setEditable(True)
        data_layout.addWidget(self.experiment_id_combo, 2, 1)
        
        data_layout.addWidget(QLabel("参照URL:"), 3, 0)
        self.reference_url_edit = QLineEdit()
        data_layout.addWidget(self.reference_url_edit, 3, 1)
        
        data_layout.addWidget(QLabel("タグ:"), 4, 0)
        self.tags_edit = QLineEdit()
        data_layout.addWidget(self.tags_edit, 4, 1)
        
        data_group.setLayout(data_layout)
        scroll_layout.addWidget(data_group)
        
        # 試料情報
        sample_group = QGroupBox("試料情報")
        sample_layout = QGridLayout()
        
        sample_layout.addWidget(QLabel("試料モード:"), 0, 0)
        self.sample_mode_combo = QComboBox()
        self.sample_mode_combo.addItems(["既存試料を使用", "新規試料を作成"])
        sample_layout.addWidget(self.sample_mode_combo, 0, 1)
        
        sample_layout.addWidget(QLabel("試料ID:"), 1, 0)
        self.sample_id_combo = QComboBox()
        self.sample_id_combo.setEditable(True)
        sample_layout.addWidget(self.sample_id_combo, 1, 1)
        
        sample_layout.addWidget(QLabel("試料名:"), 2, 0)
        self.sample_name_edit = QLineEdit()
        sample_layout.addWidget(self.sample_name_edit, 2, 1)
        
        sample_layout.addWidget(QLabel("試料説明:"), 3, 0)
        self.sample_description_edit = QTextEdit()
        self.sample_description_edit.setMaximumHeight(60)
        sample_layout.addWidget(self.sample_description_edit, 3, 1)
        
        sample_layout.addWidget(QLabel("試料組成:"), 4, 0)
        self.sample_composition_edit = QLineEdit()
        sample_layout.addWidget(self.sample_composition_edit, 4, 1)
        
        sample_group.setLayout(sample_layout)
        scroll_layout.addWidget(sample_group)
        
        # 固有情報（スキーマフォーム）
        self.dialog_schema_form_layout = QVBoxLayout()
        self.dialog_schema_placeholder_label = QLabel("データセットを選択すると、固有情報フォームが表示されます")
        self.dialog_schema_placeholder_label.setAlignment(Qt.AlignCenter)
        # テーマ準拠の muted テキストカラーを適用
        self.dialog_schema_placeholder_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-style: italic; padding: 20px;"
        )
        self.dialog_schema_form_layout.addWidget(self.dialog_schema_placeholder_label)
        scroll_layout.addLayout(self.dialog_schema_form_layout)
        
        # フォーム参照を初期化
        self.dialog_schema_form = None
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # ボタン
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self
        )
        button_box.accepted.connect(self.accept_changes)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # データセット選択・試料選択イベント接続（メインウィンドウと同様）
        if hasattr(self, 'dataset_combo'):
            self.dataset_combo.currentIndexChanged.connect(self.on_dialog_dataset_changed)
            logger.debug("ダイアログ: データセット選択イベント接続完了")
        
        # 試料モード・試料選択イベント接続
        self.sample_mode_combo.currentTextChanged.connect(self.on_dialog_sample_mode_changed)
        self.sample_id_combo.currentIndexChanged.connect(self.on_dialog_sample_selected)
        logger.debug("ダイアログ: 試料関連イベント接続完了")
        
    def on_dataset_focus_out(self, event):
        """データセット選択フォーカス外れ時の処理"""
        try:
            # 元のfocusOutEventを呼び出し
            super(type(self.dataset_combo), self.dataset_combo).focusOutEvent(event)
            
            # 現在の入力値を確定
            current_text = self.dataset_combo.currentText()
            if current_text:
                # 一致するアイテムがあるか確認
                found_index = -1
                for i in range(self.dataset_combo.count()):
                    if self.dataset_combo.itemText(i) == current_text:
                        found_index = i
                        break
                
                if found_index >= 0:
                    self.dataset_combo.setCurrentIndex(found_index)
                    logger.info("データセット選択確定: %s", current_text)
                    
        except Exception as e:
            logger.warning("データセットフォーカス外れ処理エラー: %s", e)
    
    def on_dialog_dataset_changed(self, index):
        """ダイアログでのデータセット選択変更処理"""
        try:
            logger.debug("ダイアログ: データセット選択変更 index=%s", index)
            
            if index < 0:
                logger.debug("ダイアログ: 無効なインデックス")
                return
            
            # 選択されたデータセット情報を取得
            current_data = self.dataset_combo.currentData()
            dataset_id = None
            
            if current_data:
                if isinstance(current_data, dict) and 'id' in current_data:
                    dataset_id = current_data['id']
                    logger.debug("ダイアログ: 辞書からデータセットID取得: %s", dataset_id)
                elif isinstance(current_data, str):
                    dataset_id = current_data
                    logger.debug("ダイアログ: 文字列データセットID: %s", dataset_id)
            
            if dataset_id:
                logger.info("ダイアログ: データセット選択確定: %s", dataset_id)
                
                # 試料リストを更新（メインウィンドウと同じ処理）
                self.update_dialog_sample_list(dataset_id)
                
                # スキーマフォームを表示（メインウィンドウと同じ処理）
                self.update_dialog_schema_form()
                
            else:
                logger.debug("ダイアログ: データセットIDなし")
                
        except Exception as e:
            logger.warning("ダイアログ: データセット選択変更エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_dialog_sample_list(self, dataset_id):
        """ダイアログ用のサンプル一覧更新"""
        try:
            logger.debug("ダイアログ: サンプル一覧更新開始: dataset_id=%s", dataset_id)
            
            # サンプルコンボボックスをクリア
            self.sample_id_combo.clear()
            self.sample_id_combo.addItem( None)
            
            # メインウィンドウと同じロジックを使用してサンプルを取得
            if dataset_id:
                try:
                    # 通常登録と同じ方法でデータセット情報を取得
                    from classes.data_entry.util.data_entry_filter_util import get_datasets_for_data_entry
                    
                    datasets = get_datasets_for_data_entry()
                    target_dataset = None
                    
                    for dataset in datasets:
                        if str(dataset.get('id', '')) == str(dataset_id):
                            target_dataset = dataset
                            break
                    
                    if target_dataset:
                        logger.debug("ダイアログ: 対象データセット取得成功: %s", target_dataset.get('attributes', {}).get('name', ''))
                        
                        # メインウィンドウと同じサブグループID取得ロジック
                        group_id = None
                        
                        # メインウィンドウと同じ方法でグループIDを取得（ダイアログ版）
                        try:
                            # 方法1: データセットファイルからグループIDを取得
                            dataset_id_for_file = target_dataset.get('id', '')
                            if dataset_id_for_file:
                                import os
                                from config.common import get_dynamic_file_path
                                
                                dataset_json_path = get_dynamic_file_path(f'output/rde/data/datasets/{dataset_id_for_file}.json')
                                logger.debug("ダイアログ: データセットファイル確認: %s", dataset_json_path)
                                
                                if os.path.exists(dataset_json_path):
                                    import json
                                    with open(dataset_json_path, 'r', encoding='utf-8') as f:
                                        dataset_data = json.load(f)
                                        relationships = dataset_data.get("data", {}).get('relationships', {})
                                        group = relationships.get('group', {}).get('data', {})
                                        group_id = group.get('id', '')
                                        logger.debug("ダイアログ: データセットファイルからグループID取得: %s", group_id)
                                else:
                                    logger.debug("ダイアログ: データセットファイルが存在しません: %s", dataset_json_path)
                            
                            # 方法2: フォールバック - APIレスポンスから直接取得
                            if not group_id:
                                relationships = target_dataset.get('relationships', {})
                                group_data = relationships.get('group', {}).get('data', {})
                                if not group_data:
                                    group_data = relationships.get('subgroup', {}).get('data', {})
                                
                                if group_data and group_data.get('id'):
                                    group_id = group_data.get('id')
                                    logger.debug("ダイアログ: APIレスポンスからグループID取得: %s", group_id)
                            
                        except Exception as e:
                            logger.warning("ダイアログ: グループID取得エラー: %s", e)
                            import traceback
                            traceback.print_exc()
                        
                        if group_id:
                            logger.debug("ダイアログ: 最終決定グループID: %s", group_id)
                            
                            # 通常登録のsample_loaderを使用
                            from classes.data_entry.util.sample_loader import load_existing_samples, format_sample_display_name
                            
                            existing_samples = load_existing_samples(group_id)
                            logger.debug("ダイアログ: 既存試料データ取得: %s件", len(existing_samples))
                            
                            if existing_samples:
                                for sample in existing_samples:
                                    display_name = format_sample_display_name(sample)
                                    self.sample_id_combo.addItem(display_name, sample)
                                    logger.debug("ダイアログ: 既存試料追加: %s", display_name)
                                
                                logger.info("ダイアログ: 既存試料をコンボボックスに追加完了: %s件", len(existing_samples))
                            else:
                                logger.debug("ダイアログ: 既存試料データなし")
                                self.sample_id_combo.addItem("（既存試料なし）", None)
                        else:
                            logger.warning("ダイアログ: グループID/サブグループIDが取得できません")
                            self.sample_id_combo.addItem("（グループ情報取得失敗）", None)
                    else:
                        logger.warning("ダイアログ: 対象データセットが見つかりません: %s", dataset_id)
                    
                except Exception as e:
                    logger.warning("ダイアログ: サンプル情報取得失敗: %s", e)
                    import traceback
                    traceback.print_exc()
                    self.sample_id_combo.addItem("（サンプル取得失敗）", None)
            else:
                logger.debug("ダイアログ: データセットIDが無効")
            
            logger.debug("ダイアログ: サンプル一覧更新完了: %s個の選択肢", self.sample_id_combo.count())
            
        except Exception as e:
            logger.warning("ダイアログ: サンプル一覧更新エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def on_dialog_sample_mode_changed(self, mode):
        """ダイアログ: 試料モード変更時の処理"""
        try:
            logger.debug("ダイアログ: 試料モード変更: %s", mode)
            
            if mode == "既存試料を使用":
                # 既存試料コンボボックスを有効化し、試料リストを更新
                self.sample_id_combo.setEnabled(True)
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                logger.debug("ダイアログ: 既存試料使用モード")
                
                # 現在選択されているデータセットの試料リストを再取得
                current_data = self.dataset_combo.currentData()
                dataset_id = None
                if current_data and isinstance(current_data, dict) and 'id' in current_data:
                    dataset_id = current_data['id']
                elif isinstance(current_data, str):
                    dataset_id = current_data
                
                if dataset_id:
                    logger.debug("ダイアログ: 既存試料使用モード - 試料リスト更新")
                    self.update_dialog_sample_list(dataset_id)
                
            elif mode == "新規試料を作成":
                # 新規作成時は入力フィールドを有効化
                self.sample_id_combo.setEnabled(False)
                self.sample_name_edit.setEnabled(True)
                self.sample_description_edit.setEnabled(True)
                self.sample_composition_edit.setEnabled(True)
                # 入力フィールドをクリア
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                logger.debug("ダイアログ: 新規作成モード")
                
        except Exception as e:
            logger.warning("ダイアログ: 試料モード変更エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def on_dialog_sample_selected(self, index):
        """ダイアログ: 既存試料選択時の処理"""
        try:
            logger.debug("ダイアログ: 既存試料選択: index=%s", index)
            
            if index <= 0:  # 最初のアイテム（プレースホルダー）の場合
                logger.debug("ダイアログ: プレースホルダー選択 - フィールドをクリア")
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                return
            
            # 選択された試料データを取得
            current_data = self.sample_id_combo.currentData()
            if current_data and isinstance(current_data, dict):
                logger.debug("ダイアログ: 既存試料データ取得成功: %s", current_data.get('name', ''))
                
                # 既存試料情報を入力フィールドに表示
                sample_name = current_data.get('name', '')
                sample_description = current_data.get('description', '')
                sample_composition = current_data.get('composition', '')
                
                # 入力フィールドを無効化して内容を表示
                self.sample_name_edit.setText(sample_name)
                self.sample_name_edit.setEnabled(False)
                
                self.sample_description_edit.setText(sample_description)
                self.sample_description_edit.setEnabled(False)
                
                self.sample_composition_edit.setText(sample_composition)
                self.sample_composition_edit.setEnabled(False)
                
                logger.info("ダイアログ: 既存試料情報を表示: %s", sample_name)
            else:
                logger.warning("ダイアログ: 既存試料データが取得できません")
                
        except Exception as e:
            logger.warning("ダイアログ: 既存試料選択エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_dialog_schema_form(self):
        """ダイアログ用スキーマフォーム更新"""
        try:
            logger.debug("ダイアログ: スキーマフォーム更新開始")
            # 既存のスキーマフォームを完全クリア（多重表示防止）
            if hasattr(self, 'dialog_schema_form_layout'):
                for i in reversed(range(self.dialog_schema_form_layout.count())):
                    child = self.dialog_schema_form_layout.itemAt(i).widget()
                    if child and child != getattr(self, 'dialog_schema_placeholder_label', None):
                        child.setParent(None)
            self.dialog_schema_form = None
            logger.debug("ダイアログ: 既存スキーマフォーム完全クリア")

            # プレースホルダーを非表示
            if hasattr(self, 'dialog_schema_placeholder_label'):
                self.dialog_schema_placeholder_label.hide()

            # 現在選択されているデータセット情報を取得
            current_data = self.dataset_combo.currentData()

            if not current_data or not isinstance(current_data, dict):
                logger.debug("ダイアログ: データセット情報なし")
                if hasattr(self, 'dialog_schema_placeholder_label'):
                    self.dialog_schema_placeholder_label.setText("データセットを選択してください")
                    self.dialog_schema_placeholder_label.show()
                return
            
            # データセットのスキーマ情報を取得
            dataset_id = current_data.get('id', '')
            attributes = current_data.get('attributes', {})
            dataset_name = attributes.get('name', '')
            relationships = current_data.get('relationships', {})
            
            if dataset_id:
                logger.info("ダイアログ: スキーマフォーム生成: %s (%s)", dataset_name, dataset_id)
                
                try:
                    # 通常登録と同じ方法でテンプレートIDを取得
                    template_id = ''
                    template = relationships.get('template', {}).get('data', {})
                    if isinstance(template, dict):
                        template_id = template.get('id', '')
                    
                    logger.debug("ダイアログ: テンプレートID: %s", template_id)
                    
                    if template_id:
                        # 通常登録と同じパスでinvoiceSchemaを確認
                        from config.common import get_dynamic_file_path
                        from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
                        
                        invoice_schema_path = get_dynamic_file_path(f'output/rde/data/invoiceSchemas/{template_id}.json')
                        
                        logger.debug("ダイアログ: invoiceSchemaファイル確認: %s", invoice_schema_path)
                        
                        import os
                        if os.path.exists(invoice_schema_path):
                            logger.info("ダイアログ: invoiceSchemaファイル発見: %s", invoice_schema_path)
                            
                            # 通常登録と同じ方法でフォーム生成
                            schema_form = create_schema_form_from_path(invoice_schema_path, self)
                            
                            if schema_form:
                                logger.info("ダイアログ: インボイススキーマフォーム生成成功")
                                
                                # 動的生成フォームを追加
                                self.dialog_schema_form_layout.addWidget(schema_form)
                                self.dialog_schema_form = schema_form  # 保存（後で値取得で使用）
                                
                                logger.info("ダイアログ: インボイススキーマフォーム表示完了")
                            else:
                                logger.warning("ダイアログ: スキーマフォーム生成失敗")
                                if hasattr(self, 'dialog_schema_placeholder_label'):
                                    self.dialog_schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマフォーム生成に失敗しました")
                                    self.dialog_schema_placeholder_label.show()
                        else:
                            logger.warning("ダイアログ: invoiceSchemaファイルが存在しません: %s", invoice_schema_path)
                            if hasattr(self, 'dialog_schema_placeholder_label'):
                                self.dialog_schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマファイルが見つかりません")
                                self.dialog_schema_placeholder_label.show()
                    else:
                        logger.warning("ダイアログ: テンプレートIDなし")
                        if hasattr(self, 'dialog_schema_placeholder_label'):
                            self.dialog_schema_placeholder_label.setText(f"データセット '{dataset_name}' にテンプレート情報がありません")
                            self.dialog_schema_placeholder_label.show()
                        
                except Exception as e:
                    logger.warning("ダイアログ: スキーマフォーム処理エラー: %s", e)
                    import traceback
                    traceback.print_exc()
                    if hasattr(self, 'dialog_schema_placeholder_label'):
                        self.dialog_schema_placeholder_label.setText(f"スキーマフォーム処理でエラーが発生しました: {str(e)}")
                        self.dialog_schema_placeholder_label.show()
                        
        except Exception as e:
            logger.warning("ダイアログ: スキーマフォーム更新エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def load_fileset_data(self):
        """ファイルセットデータをフォームに読み込み"""
        try:
            # 基本情報
            self.fileset_name_edit.setText(self.fileset.name or "")
            if self.fileset.organize_method == PathOrganizeMethod.ZIP:
                self.organize_method_combo.setCurrentText("ZIP化")
            else:
                self.organize_method_combo.setCurrentText("フラット化")
            
            # データ名
            self.data_name_edit.setText(self.fileset.data_name or "")
            
            # データセット設定（メインウィンドウと同じ処理）
            if hasattr(self.fileset, 'dataset_id') and self.fileset.dataset_id:
                logger.debug("ダイアログ: データセットID=%sを設定中", self.fileset.dataset_id)
                # データセットIDで検索してコンボボックスを設定
                found = False
                for i in range(self.dataset_combo.count()):
                    item_data = self.dataset_combo.itemData(i)
                    # 辞書オブジェクトの場合は'id'キーを確認、文字列の場合は直接比較
                    dataset_id = None
                    if isinstance(item_data, dict) and 'id' in item_data:
                        dataset_id = item_data['id']
                    elif isinstance(item_data, str):
                        dataset_id = item_data
                    
                    if dataset_id == self.fileset.dataset_id:
                        logger.debug("ダイアログ: データセットコンボボックス インデックス%sを選択", i)
                        self.dataset_combo.setCurrentIndex(i)
                        found = True
                        break
                if not found:
                    logger.warning("ダイアログ: データセットID %s がコンボボックスに見つかりません", self.fileset.dataset_id)
                    self.dataset_combo.setCurrentIndex(-1)
            else:
                logger.debug("ダイアログ: データセット未設定")
                self.dataset_combo.setCurrentIndex(-1)
            
            # 拡張設定
            if hasattr(self.fileset, 'extended_config') and self.fileset.extended_config:
                config = self.fileset.extended_config
                
                self.description_edit.setPlainText(config.get('description', ''))
                self.experiment_id_combo.setCurrentText(config.get('experiment_id', ''))
                self.reference_url_edit.setText(config.get('reference_url', ''))
                self.tags_edit.setText(config.get('tags', ''))
                
                self.sample_mode_combo.setCurrentText(config.get('sample_mode', '既存試料を使用'))
                self.sample_id_combo.setCurrentText(config.get('sample_id', ''))
                self.sample_name_edit.setText(config.get('sample_name', ''))
                self.sample_description_edit.setPlainText(config.get('sample_description', ''))
                self.sample_composition_edit.setText(config.get('sample_composition', ''))
                
        except Exception as e:
            logger.warning("ファイルセットデータ読み込みエラー: %s", e)
    
    def accept_changes(self):
        """変更を適用してダイアログを閉じる"""
        try:
            # 基本情報を更新
            self.fileset.name = self.fileset_name_edit.text()
            self.fileset.organize_method = (
                PathOrganizeMethod.ZIP if self.organize_method_combo.currentText() == "ZIP化" 
                else PathOrganizeMethod.FLATTEN
            )
            
            # データ名
            self.fileset.data_name = self.data_name_edit.text()
            
            # データセットID（メインウィンドウと同じ処理）
            if hasattr(self, 'dataset_combo'):
                current_data = self.dataset_combo.currentData()
                if current_data:
                    # 辞書オブジェクトの場合、'id'キーを取得
                    if isinstance(current_data, dict) and 'id' in current_data:
                        self.fileset.dataset_id = current_data['id']
                    # 文字列の場合はそのまま使用
                    elif isinstance(current_data, str):
                        self.fileset.dataset_id = current_data
                    else:
                        self.fileset.dataset_id = None
                else:
                    self.fileset.dataset_id = None
            
            # 拡張設定を更新
            if not hasattr(self.fileset, 'extended_config'):
                self.fileset.extended_config = {}
                
            self.fileset.extended_config.update({
                'description': self.description_edit.toPlainText(),
                'experiment_id': self.experiment_id_combo.currentText(),
                'reference_url': self.reference_url_edit.text(),
                'tags': self.tags_edit.text(),
                'sample_mode': self.sample_mode_combo.currentText(),
                'sample_id': self.sample_id_combo.currentText(),
                'sample_name': self.sample_name_edit.text(),
                'sample_description': self.sample_description_edit.toPlainText(),
                'sample_composition': self.sample_composition_edit.text(),
            })
            
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定の保存に失敗しました:\n{e}")
            logger.error("accept_changes: %s", e)


# BatchRegisterWidget に一時フォルダ管理メソッドを追加
def _prepare_temp_folders(self):
    """一時フォルダ準備（フラット化・ZIP化対応）"""
    try:
        logger.info("一時フォルダ準備を開始")
        
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            return
        
        for file_set in self.file_set_manager.file_sets:
            # フラット化・ZIP化が選択されている場合のみ一時フォルダを作成
            if file_set.organize_method in [PathOrganizeMethod.FLATTEN, PathOrganizeMethod.ZIP]:
                try:
                    temp_dir, mapping_xlsx = self.temp_folder_manager.create_temp_folder_for_fileset(file_set)
                    
                    # ファイルセットに一時フォルダ情報を保存
                    if not hasattr(file_set, 'extended_config'):
                        file_set.extended_config = {}
                    
                    file_set.extended_config.update({
                        'temp_folder': temp_dir,
                        'mapping_file': mapping_xlsx,
                        'temp_created': True
                    })
                    
                    logger.info("ファイルセット '%s' の一時フォルダを作成: %s", file_set.name, temp_dir)
                    
                except Exception as e:
                    logger.error("ファイルセット '%s' の一時フォルダ作成エラー: %s", file_set.name, e)
                    # エラーがあっても処理を続行
                    continue
        
        logger.info("一時フォルダ準備完了")
        
    except Exception as e:
        logger.error("一時フォルダ準備処理エラー: %s", e)
        raise

def cleanup_temp_folders_on_init(self):
    """初期化時に既存の一時フォルダをクリーンアップ（UUID対応版）"""
    try:
        logger.info("既存一時フォルダのクリーンアップを開始")
        
        # 新しいUUID管理方式で全てクリーンアップ
        self.temp_folder_manager.cleanup_all_temp_folders()
        
        # 孤立したフォルダも削除（file_setsは初期化時は空なのですべて孤立扱い）
        orphaned_count = self.temp_folder_manager.cleanup_orphaned_temp_folders([])
        
        logger.info("既存一時フォルダのクリーンアップ完了（孤立フォルダ %s 個削除）", orphaned_count)
    except Exception as e:
        logger.warning("一時フォルダクリーンアップエラー: %s", e)

def auto_apply_settings_to_selected(self):
    """選択されたファイルセットに現在の設定を自動適用"""
    try:
        # ファイルセット復元処理中の場合は自動適用をスキップ
        if getattr(self, '_restoring_fileset', False):
            logger.debug("ファイルセット復元中のため自動設定適用をスキップ")
            return
            
        # ターゲットファイルセットコンボボックスが存在し、選択されている場合のみ
        if hasattr(self, 'target_fileset_combo') and self.target_fileset_combo.currentText():
            target_name = self.target_fileset_combo.currentText()
            if target_name and target_name != "選択してください":
                # 対象のファイルセットを検索
                target_fileset = None
                if self.file_set_manager:
                    for fileset in self.file_set_manager.file_sets:
                        if fileset.name == target_name:
                            target_fileset = fileset
                            break
                
                if target_fileset:
                    # 現在の設定を取得して適用
                    settings = self.get_current_settings()
                    if settings:
                        # 新しい方式の適用メソッドを使用（2つの引数）
                        self._apply_settings_to_fileset(target_fileset, settings)
                        logger.info("設定をファイルセット '%s' に自動適用しました", target_name)
                        # テーブル表示を更新
                        QTimer.singleShot(100, self.refresh_fileset_display)
    except Exception as e:
        logger.warning("設定自動適用エラー: %s", e)

    def show_data_tree_dialog(self, fileset: FileSet):
        """データツリー選択ダイアログを表示"""
        try:
            dialog = DataTreeDialog(fileset.items, self)
            if dialog.exec() == QDialog.Accepted:
                # 選択されたファイルでファイルセットを更新
                selected_files = dialog.get_selected_files()
                if selected_files:
                    fileset.items = selected_files
                    self.refresh_fileset_display()
                    QMessageBox.information(self, "完了", 
                        f"ファイルセット '{fileset.name}' を更新しました。\n"
                        f"選択ファイル数: {len(selected_files)}個")
        except Exception as e:
            logger.error("show_data_tree_dialog: %s", e)
            QMessageBox.warning(self, "エラー", f"データツリーダイアログの表示に失敗しました: {str(e)}")
    
    def _create_mapping_file(self, file_set):
        """マッピングファイルを作成・更新"""
        try:
            mapping_file_path = self._get_mapping_file_path_for_fileset(file_set)
            if not mapping_file_path:
                raise ValueError("マッピングファイルのパスを取得できませんでした")
            
            # マッピングデータを作成
            mapping_data = {
                "fileset_name": file_set.name,
                "created_at": self._get_current_timestamp(),
                "files": []
            }
            
            # ファイルセット内のファイル情報（マッピングファイル自体は除外）
            for file_item in file_set.items:
                if file_item.name.endswith("_mapping.json"):
                    continue  # マッピングファイル自体は含めない
                
                file_info = {
                    "name": file_item.name,
                    "path": file_item.relative_path,
                    "size": file_item.size,
                    "type": "directory" if file_item.file_type == FileType.DIRECTORY else "file"
                }
                mapping_data["files"].append(file_info)
            
            # JSONファイルとして保存
            with open(mapping_file_path, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, ensure_ascii=False, indent=2)
            
            # マッピングファイルをファイルセットに追加（実際のファイルとして）
            mapping_file_item = FileItem(
                path=mapping_file_path,
                relative_path=os.path.basename(mapping_file_path),
                name=os.path.basename(mapping_file_path),
                file_type=FileType.FILE,
                size=os.path.getsize(mapping_file_path)
            )
            
            # ファイルセットに追加（重複チェック）
            mapping_exists = any(f.name == mapping_file_item.name for f in file_set.items)
            if not mapping_exists:
                file_set.items.append(mapping_file_item)
            
        except Exception as e:
            logger.error("_create_mapping_file: %s", e)
            raise e
    
    def _get_mapping_file_path_for_fileset(self, file_set):
        """ファイルセット用のマッピングファイルパスを取得"""
        if file_set.items:
            base_dir = os.path.dirname(file_set.items[0].path)
            return os.path.join(base_dir, f"{file_set.name}_mapping.json")
        return None
    
    def _get_current_timestamp(self):
        """現在のタイムスタンプを取得"""
        import datetime
        return datetime.datetime.now().isoformat()

# BatchRegisterWidgetクラスにメソッドを動的に追加
BatchRegisterWidget._prepare_temp_folders = _prepare_temp_folders
BatchRegisterWidget.cleanup_temp_folders_on_init = cleanup_temp_folders_on_init
BatchRegisterWidget.auto_apply_settings_to_selected = auto_apply_settings_to_selected

