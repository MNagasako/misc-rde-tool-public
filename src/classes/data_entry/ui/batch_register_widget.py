"""
一括登録UI実装

ファイルセット管理、データツリー表示、登録設定UIを提供
"""

import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QScrollArea, QSplitter, QTabWidget, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QMenu, QAction, QApplication, QFrame, QSizePolicy,
    QInputDialog, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush

from ..core.file_set_manager import (
    FileSetManager, FileSet, FileItem, FileType, PathOrganizeMethod, FileItemType
)
from ..core.batch_register_logic import BatchRegisterLogic, BatchRegisterResult
from ..core.temp_folder_manager import TempFolderManager
from ..util.data_entry_filter_util import get_datasets_for_data_entry, get_filtered_datasets
from classes.data_entry.conf.ui_constants import (
    BATCH_REGISTER_STYLE,
    FILE_TREE_STYLE,
    FILESET_TABLE_STYLE
)


class FileTreeWidget(QTreeWidget):
    """ファイルツリー表示ウィジェット"""
    
    # シグナル定義
    items_selected = pyqtSignal(list)  # 選択されたアイテム
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_items = {}  # id(QTreeWidgetItem) -> FileItem のマッピング
        self.setup_ui()
    
    def setup_ui(self):
        """UIセットアップ"""
        self.setHeaderLabels(["名前", "タイプ", "種類", "拡張子", "サイズ", "含む", "ZIP"])
        self.setSelectionMode(QTreeWidget.ExtendedSelection)  # 複数選択可能
        self.setAlternatingRowColors(True)
        self.setStyleSheet(FILE_TREE_STYLE)
        
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
                    tree_item.setForeground(col, QColor("#999999"))
            else:
                # サイズ列の色分け（ファイルとディレクトリで色を変える）
                if file_item.file_type == FileType.FILE:
                    tree_item.setForeground(4, QColor("#2E8B57"))  # SeaGreen
                else:
                    tree_item.setForeground(4, QColor("#4682B4"))  # SteelBlue
            
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
            print(f"[DEBUG] ファイル '{file_item.name}' の種類を {item_type.value} に変更")
    
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
            is_checked = (state == Qt.Checked)
            file_item.is_excluded = not is_checked
            
            # 視覚的フィードバック
            if file_item.is_excluded:
                tree_item.setForeground(0, QColor("#999999"))
                tree_item.setForeground(1, QColor("#999999"))
                tree_item.setForeground(2, QColor("#999999"))
            else:
                tree_item.setForeground(0, QColor("#000000"))
                tree_item.setForeground(1, QColor("#000000"))
                tree_item.setForeground(2, QColor("#000000"))
            
            # 選択状態をシグナルで通知
            selected_items = self.get_selected_items()
            self.items_selected.emit(selected_items)
            
        except Exception as e:
            print(f"[ERROR] チェックボックス変更エラー: {e}")
    
    def find_tree_item_by_file_item(self, target_file_item: 'FileItem') -> Optional[QTreeWidgetItem]:
        """FileItemに対応するQTreeWidgetItemを検索"""
        for item_id, file_item in self.file_items.items():
            if file_item == target_file_item or file_item.relative_path == target_file_item.relative_path:
                # item_idからQTreeWidgetItemを逆引き
                return self._find_tree_item_by_id(item_id)
        return None
    
    def _find_tree_item_by_id(self, target_id: int) -> Optional[QTreeWidgetItem]:
        """IDからQTreeWidgetItemを再帰的に検索"""
        return self._search_tree_item_recursive(self.invisibleRootItem(), target_id)
    
    def _search_tree_item_recursive(self, parent: QTreeWidgetItem, target_id: int) -> Optional[QTreeWidgetItem]:
        """ツリーアイテムを再帰的に検索"""
        # 親アイテム自体をチェック
        if id(parent) == target_id:
            return parent
        
        # 子アイテムを検索
        for i in range(parent.childCount()):
            child = parent.child(i)
            if id(child) == target_id:
                return child
            
            # 再帰的に検索
            result = self._search_tree_item_recursive(child, target_id)
            if result:
                return result
        
        return None
    
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
            tree_item.setForeground(0, QColor(0, 0, 255))  # 青色でZIP化対象を示す
            tree_item.setText(0, f"📦 {file_item.name}")
        else:
            tree_item.setForeground(0, QColor(0, 0, 0))    # 通常の色に戻す
            tree_item.setText(0, file_item.name)
        
        print(f"[DEBUG] ZIP化フラグ設定: {file_item.name} -> {is_zip}")
    
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
            
            print(f"[DEBUG] add_to_fileset: フォルダ={file_item.name}, include_subdirs={include_subdirs}")
            
            # チェック済みアイテムを収集（ファイルのみ）
            all_checked_items = parent_widget._get_checked_items_from_tree()
            checked_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            print(f"[DEBUG] add_to_fileset: 全チェック済みファイル数={len(checked_files)}")
            
            if include_subdirs:
                # 配下全フォルダの場合：選択したフォルダ以下のファイルのみ
                target_path = file_item.relative_path
                print(f"[DEBUG] add_to_fileset（配下全て）: target_path={target_path}")
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
                    
                    print(f"[DEBUG] add_to_fileset（配下全て）: ファイル={item.relative_path}, parent={item_parent}, is_subdir={is_subdir}, is_direct={is_direct}")
                    
                    if is_subdir or is_direct:
                        filtered_items.append(item)
                        print(f"[DEBUG] add_to_fileset（配下全て）: 含める -> {item.relative_path}")
                    else:
                        print(f"[DEBUG] add_to_fileset（配下全て）: 除外 -> {item.relative_path}")
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
                        print(f"[DEBUG] add_to_fileset（このフォルダのみ）: 直下ファイル含める -> {item.relative_path}")
                    else:
                        # サブフォルダ内のファイルは除外
                        print(f"[DEBUG] add_to_fileset（このフォルダのみ）: サブフォルダ内ファイル除外 -> {item.relative_path}")
                checked_items = filtered_items
            
            if not checked_items:
                QMessageBox.information(self, "情報", "選択したフォルダ範囲に「含む」にチェックされたファイルがありません")
                return
            
            print(f"[DEBUG] add_to_fileset: フィルタ後のファイル数={len(checked_items)}")
            
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
                
                reply = QMessageBox.question(self, "重複ファイル", conflict_msg,
                                           QMessageBox.Yes | QMessageBox.No,
                                           QMessageBox.Yes)
                
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
            print(f"[DEBUG] ファイルセット作成前: checked_items={len(checked_items)}個")
            for i, item in enumerate(checked_items):
                print(f"[DEBUG]   {i+1}: {item.name} ({item.file_type.name}) -> {item.relative_path}")
            
            # ZIP化指定されたディレクトリがあるか確認し、ファイルリストにディレクトリ情報を追加
            items_to_add = list(checked_items)  # ファイルリストをコピー
            
            # ZIP化指定されたディレクトリ情報を追加
            if getattr(file_item, 'is_zip', False) and file_item.file_type == FileType.DIRECTORY:
                print(f"[DEBUG] ZIP化ディレクトリを追加: {file_item.name}")
                # ディレクトリ情報をアイテムリストに追加（ZIP化フラグ付き）
                zip_dir_item = FileItem(
                    path=file_item.path,
                    relative_path=file_item.relative_path,
                    name=file_item.name,
                    file_type=FileType.DIRECTORY,
                    is_zip=True
                )
                items_to_add.append(zip_dir_item)
                print(f"[DEBUG] ZIP化ディレクトリ追加完了: {zip_dir_item.name}, is_zip={zip_dir_item.is_zip}")
            
            new_fileset = parent_widget.file_set_manager.create_manual_fileset(
                fileset_name, items_to_add)
            
            # 作成直後に一時フォルダとマッピングファイルを作成
            parent_widget._create_temp_folder_and_mapping(new_fileset)
            
            # デバッグ情報：作成後のファイル数
            print(f"[DEBUG] ファイルセット作成後: items={len(new_fileset.items)}個")
            for i, item in enumerate(new_fileset.items):
                print(f"[DEBUG]   {i+1}: {item.name} ({item.file_type.name}) -> {item.relative_path}")
            
            # ファイルセットテーブル更新
            parent_widget.refresh_fileset_display()
            parent_widget.update_summary()
            
            # 成功メッセージ
            file_count = len(checked_items)
            
            QMessageBox.information(self, "完了", 
                f"ファイルセット '{fileset_name}' を作成しました。\n"
                f"ファイル数: {file_count}個")
            
        except Exception as e:
            print(f"[ERROR] add_to_fileset: {e}")
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
            is_checked = state == Qt.Checked
            file_item.is_excluded = not is_checked
            
            # フォルダの場合は配下の全アイテムも連動
            if file_item.file_type == FileType.DIRECTORY:
                self._update_children_include_state(tree_item, is_checked)
            
            # 親フォルダの状態更新
            self._update_parent_include_state(tree_item)
            
            # 表示スタイル更新
            self._update_item_style(tree_item, file_item)
            
        except Exception as e:
            print(f"[WARNING] 含むチェックボックス変更エラー: {e}")
    
    def on_zip_checkbox_changed(self, state, tree_item, file_item):
        """ZIPチェックボックス変更時の処理"""
        try:
            is_checked = state == Qt.Checked
            # ZIP状態をfile_itemの拡張属性に保存
            if not hasattr(file_item, 'is_zip'):
                file_item.is_zip = False
            file_item.is_zip = is_checked
            print(f"[DEBUG] ZIP状態変更: {file_item.name} -> {is_checked}")
            
            # ZIPにチェックが入った場合、配下の全フォルダのZIPチェックを外す
            if is_checked:
                self._clear_child_zip_flags(tree_item)
                print(f"[INFO] フォルダ '{file_item.name}' をZIP化設定。配下フォルダのZIP設定を解除しました。")
            
        except Exception as e:
            print(f"[WARNING] ZIPチェックボックス変更エラー: {e}")
    
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
                tree_item.setForeground(col, QColor("#999999"))
        else:
            # 通常色に戻す
            for col in range(4):
                tree_item.setForeground(col, QColor("#000000"))
            
            # サイズ列の色分け
            if file_item.file_type == FileType.FILE:
                tree_item.setForeground(3, QColor("#2E8B57"))  # SeaGreen
            else:
                tree_item.setForeground(3, QColor("#4682B4"))  # SteelBlue
    
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
        tree_item.setCheckState(0, Qt.Unchecked if exclude else Qt.Checked)
        
        # スタイル更新
        if exclude:
            tree_item.setForeground(0, QColor("#999999"))
            tree_item.setForeground(1, QColor("#999999"))
            tree_item.setForeground(2, QColor("#999999"))
            tree_item.setForeground(3, QColor("#999999"))
        else:
            tree_item.setForeground(0, QColor("#000000"))
            tree_item.setForeground(1, QColor("#000000"))
            tree_item.setForeground(2, QColor("#000000"))
            tree_item.setForeground(3, QColor("#000000"))
    
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
    fileset_selected = pyqtSignal(object)  # FileSet
    fileset_deleted = pyqtSignal(int)      # ファイルセットID
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_sets = []
        self.file_set_manager = None  # file_set_managerへの参照
        self.setup_ui()
    
    def setup_ui(self):
        """UIセットアップ"""
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels([
            "ファイルセット名", "ファイル数", "マッピングファイル", "サイズ", "整理方法", "データ名", "試料", "データセット", "操作"
        ])
        
        # スタイル設定
        self.setStyleSheet(FILESET_TABLE_STYLE)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        
        # ヘッダー設定
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultSectionSize(100)  # デフォルト列幅を設定
        header.setMinimumSectionSize(60)   # 最小列幅を設定
        
        # カラム幅設定とリサイズ可能設定
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # ファイルセット名（リサイズ可能）
        header.setSectionResizeMode(1, QHeaderView.Interactive)        # ファイル数（固定）
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # マッピングファイル（リサイズ可能）
        header.setSectionResizeMode(3, QHeaderView.Interactive)        # サイズ（固定）
        header.setSectionResizeMode(4, QHeaderView.Interactive)  # 整理方法（リサイズ可能）
        header.setSectionResizeMode(5, QHeaderView.Interactive)  # データ名（リサイズ可能）
        header.setSectionResizeMode(6, QHeaderView.Interactive)  # 試料（リサイズ可能）
        header.setSectionResizeMode(7, QHeaderView.Interactive)  # データセット（リサイズ可能）
        header.setSectionResizeMode(8, QHeaderView.Fixed)        # 操作（固定）
        
        # 初期幅設定（推奨値）
        self.setColumnWidth(0, 180)  # ファイルセット名（少し大きく）
        self.setColumnWidth(1, 170)   # ファイル数
        self.setColumnWidth(2, 120)  # マッピングファイル
        self.setColumnWidth(3, 80)   # サイズ
        self.setColumnWidth(4, 100)  # 整理方法
        self.setColumnWidth(5, 120)  # データ名
        self.setColumnWidth(6, 100)  # 試料
        self.setColumnWidth(7, 140)  # データセット
        self.setColumnWidth(8, 140)  # 操作（登録・削除ボタン用に拡大）
        
        # 選択変更シグナル
        self.itemSelectionChanged.connect(self.on_selection_changed)
        
        # ダブルクリックシグナル
        self.itemDoubleClicked.connect(self.on_double_clicked)
    
    def set_file_set_manager(self, file_set_manager):
        """file_set_managerへの参照を設定"""
        print(f"[DEBUG] FileSetTableWidget.set_file_set_manager: 設定開始")
        print(f"[DEBUG] set_file_set_manager: file_set_manager={file_set_manager}")
        if file_set_manager:
            print(f"[DEBUG] set_file_set_manager: file_sets count={len(getattr(file_set_manager, 'file_sets', []))}")
        self.file_set_manager = file_set_manager
        print(f"[DEBUG] FileSetTableWidget.set_file_set_manager: 設定完了")
    
    def load_file_sets(self, file_sets: List[FileSet]):
        """ファイルセット一覧をロード"""
        import traceback
        print(f"[DEBUG] FileSetTableWidget.load_file_sets: 受信 {len(file_sets)} ファイルセット")
        print(f"[DEBUG] load_file_sets 呼び出し元:")
        for line in traceback.format_stack()[-3:-1]:
            print(f"  {line.strip()}")
        
        self.file_sets = file_sets
        self.setRowCount(len(file_sets))
        print(f"[DEBUG] FileSetTableWidget.load_file_sets: テーブル行数を {len(file_sets)} に設定")
        
        for row, file_set in enumerate(file_sets):
            print(f"[DEBUG] FileSetTableWidget: 行{row} 処理中: {file_set.name}")
            
            # ファイルセット名（アイコン付きのクリック可能ウィジェット）
            name_widget = self._create_name_widget_with_icon(file_set)
            self.setCellWidget(row, 0, name_widget)
            
            # ファイル数（ファイル / フォルダの形式）
            try:
                file_count = file_set.get_file_count()
                dir_count = file_set.get_directory_count()
                count_text = f"{file_count}F / {dir_count}D"
            except:
                count_text = "0F / 0D"
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
            operations_layout.setContentsMargins(2, 2, 2, 2)
            operations_layout.setSpacing(4)
            
            # 登録ボタン
            register_btn = QPushButton("登録")
            register_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                    min-width: 40px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            register_btn.clicked.connect(lambda checked, fid=file_set.id: self.register_single_fileset(fid))
            operations_layout.addWidget(register_btn)
            
            # 削除ボタン
            delete_btn = QPushButton("削除")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                    min-width: 40px;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
            """)
            delete_btn.clicked.connect(lambda checked, fid=file_set.id: self.delete_fileset(fid))
            operations_layout.addWidget(delete_btn)
            
            self.setCellWidget(row, 8, operations_widget)  # 操作列に配置
    
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
            print(f"[DEBUG] ファイルセット '{file_set.name}' の整理方法を '{method_text}' に変更")
        except Exception as e:
            print(f"[ERROR] 整理方法変更エラー: {e}")

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
            print(f"[ERROR] 試料情報取得エラー: {e}")
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
            print(f"[ERROR] データセット名取得エラー: {e}")
            return "未設定"
    
    def on_selection_changed(self):
        """選択変更処理"""
        current_row = self.currentRow()
        if 0 <= current_row < len(self.file_sets):
            file_set = self.file_sets[current_row]
            self.fileset_selected.emit(file_set)
    
    def delete_fileset(self, fileset_id: int):
        """ファイルセット削除"""
        reply = QMessageBox.question(
            self, "確認", "選択されたファイルセットを削除しますか？",
            QMessageBox.Yes | QMessageBox.No
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
            
            # Bearerトークンを共通ヘルパーで取得（通常登録タブ方式に統一）
            from core.bearer_token_helper import get_current_bearer_token
            bearer_token = get_current_bearer_token(self)
            if not bearer_token:
                QMessageBox.warning(self, "エラー", "認証トークンが設定されていません。ログインを確認してください。")
                return
            print(f"[DEBUG] register_single_fileset: トークン取得成功 (長さ: {len(bearer_token)})")
            from .batch_preview_dialog import BatchRegisterPreviewDialog
            dialog = BatchRegisterPreviewDialog(
                file_sets=[target_fileset],
                parent=self,
                bearer_token=bearer_token
            )
            dialog.exec_()
            
        except Exception as e:
            print(f"[ERROR] register_single_fileset エラー: {e}")
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
        print(f"[DEBUG] FileSetTableWidget.refresh_data: 呼び出された")
        try:
            # file_set_managerから最新のデータを取得
            if self.file_set_manager and hasattr(self.file_set_manager, 'file_sets'):
                latest_file_sets = self.file_set_manager.file_sets
                print(f"[DEBUG] refresh_data: file_set_managerから{len(latest_file_sets)}個のファイルセットを取得")
                self.load_file_sets(latest_file_sets)
            elif hasattr(self, 'file_sets') and self.file_sets:
                print(f"[DEBUG] refresh_data: 内部file_setsから{len(self.file_sets)}個のファイルセットで再読み込み")
                self.load_file_sets(self.file_sets)
            else:
                print(f"[DEBUG] refresh_data: ファイルセットが存在しません")
                self.setRowCount(0)
        except Exception as e:
            print(f"[ERROR] refresh_data: {e}")
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
            print(f"[ERROR] on_double_clicked: {e}")
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
                color: {'green' if mapping_file_exists else 'red'};
                font-weight: bold;
                font-size: 12px;
            }}
        """)
        layout.addWidget(status_label)
        
        # 表示ボタン
        view_btn = QPushButton("表示")
        view_btn.setEnabled(mapping_file_exists)
        view_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover:enabled {
                background-color: #138496;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                color: #adb5bd;
            }
        """)
        view_btn.clicked.connect(lambda: self._view_mapping_file(file_set))
        layout.addWidget(view_btn)
        
        # 更新ボタン
        update_btn = QPushButton("更新")
        update_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
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
        name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(name_label)
        
        # 間隔調整
        layout.addStretch()
        
        # フォルダ書き出しアイコンボタン
        export_icon = QPushButton("出力")
        export_icon.setToolTip("ファイルセットをフォルダまたはZIPファイルとして書き出し")
        export_icon.setFixedSize(35, 25)
        export_icon.setStyleSheet("""
            QPushButton {
                border: 1px solid #28a745;
                background-color: #f8f9fa;
                font-size: 10px;
                border-radius: 3px;
                color: #28a745;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d4edda;
                border-color: #1e7e34;
                color: #1e7e34;
            }
        """)
        export_icon.clicked.connect(lambda: self._export_fileset_folder(file_set))
        layout.addWidget(export_icon)
        
        # 内容表示アイコンボタン
        view_icon = QPushButton("表示")
        view_icon.setToolTip("ファイルセットの内容を表示・編集")
        view_icon.setFixedSize(35, 25)
        view_icon.setStyleSheet("""
            QPushButton {
                border: 1px solid #2196f3;
                background-color: #ffffff;
                font-size: 10px;
                border-radius: 3px;
                color: #2196f3;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #1976d2;
                color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
                border-color: #0d47a1;
                color: #0d47a1;
            }
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
            
            msgbox.exec_()
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
            print(f"[ERROR] フォルダ書き出しエラー: {e}")
            QMessageBox.warning(self, "エラー", f"フォルダ書き出しに失敗しました: {str(e)}")
    
    def _show_fileset_content_dialog(self, file_set):
        """ファイルセット内容表示・編集ダイアログを表示"""
        try:
            # 専用ダイアログが存在しない場合は、簡易版を使用
            self._show_simple_fileset_content_dialog(file_set)
        except Exception as e:
            print(f"[ERROR] ファイルセット内容ダイアログエラー: {e}")
            QMessageBox.warning(self, "エラー", f"ファイルセット内容の表示に失敗しました: {str(e)}")
    
    def _show_simple_fileset_content_dialog(self, file_set):
        """簡易版ファイルセット内容ダイアログ（組み込み版）"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"ファイルセット内容 - {file_set.name}")
        dialog.setModal(True)
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
        dialog.exec_()
    
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
                                    print(f"[DEBUG] ファイルセット変更適用 - ZIP設定: {file_item.name} -> {file_item.is_zip}")
                            
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
            try:
                self._update_mapping_file(file_set)
            except Exception as e:
                print(f"[WARNING] マッピングファイル自動更新エラー: {e}")
            
            # ダイアログを閉じる
            dialog.accept()
            
            QMessageBox.information(self, "完了", 
                f"ファイルセット '{file_set.name}' を更新しました。\n"
                f"選択ファイル数: {len(updated_items)}個")
                
        except Exception as e:
            print(f"[ERROR] ファイルセット変更適用エラー: {e}")
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
                                    print(f"[DEBUG] ZIP設定復元: {file_item.name} -> {original_item.is_zip}")
                                
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
                print(f"[WARNING] TempFolderManagerアクセスエラー: {e}")
        
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
                print(f"[WARNING] TempFolderManagerフォールバックエラー: {e}")
        
        return None
    
    def _view_mapping_file(self, file_set):
        """マッピングファイルを表示"""
        try:
            mapping_file_path = self._get_mapping_file_path(file_set)
            if mapping_file_path and os.path.exists(mapping_file_path):
                # ファイルを外部プログラムで開く
                os.startfile(mapping_file_path)
            else:
                QMessageBox.warning(self, "エラー", "マッピングファイルが見つかりません。")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"マッピングファイルの表示に失敗しました: {str(e)}")
    
    def _update_mapping_file(self, file_set):
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
            QMessageBox.information(self, "完了", 
                f"ファイルセット '{file_set.name}' のマッピングファイルを作成しました。\n"
                f"パス: {mapping_file}")
            
        except Exception as e:
            print(f"[ERROR] マッピングファイル更新エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "エラー", f"マッピングファイルの更新に失敗しました: {str(e)}")
    
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
        self.resize(600, 500)
        
        layout = QVBoxLayout()
        
        # 説明ラベル
        info_label = QLabel("ファイルセットに含めるファイル・フォルダを選択してください")
        info_label.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(info_label)
        
        # ファイルツリー
        self.file_tree = FileTreeWidget()
        # ダイアログ内では右クリックメニューを無効化
        self.file_tree.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.file_tree)
        
        # ファイルツリーにデータをロード
        if self.file_items:
            print(f"[DEBUG] DataTreeDialog: {len(self.file_items)}個のファイルアイテムをロード")
            self.file_tree.load_file_tree(self.file_items)
        else:
            print("[WARNING] DataTreeDialog: ファイルアイテムが空です")
        
        # 選択情報
        self.selection_info = QLabel("選択されたアイテム: 0個")
        self.selection_info.setStyleSheet("color: #666; padding: 5px;")
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
            print(f"[ERROR] ダイアログからのファイルセット更新エラー: {e}")
            QMessageBox.warning(self, "エラー", f"ファイルセット更新に失敗しました: {e}")


class BatchRegisterWidget(QWidget):
    """一括登録メインウィジェット"""
    
    def __init__(self, parent_controller, parent=None):
        super().__init__(parent)
        print("[DEBUG] BatchRegisterWidget初期化開始")
        self.parent_controller = parent_controller
        self.file_set_manager = None
        self.batch_logic = BatchRegisterLogic(self)
        self.temp_folder_manager = TempFolderManager()  # 一時フォルダ管理
        self.datasets = []  # データセット一覧
        
        # ファイルセット復元処理中フラグ（自動設定適用を防ぐため）
        self._restoring_fileset = False
        
        # ベアラートークンを初期化時に設定
        self.bearer_token = None
        if hasattr(parent_controller, 'bearer_token'):
            self.bearer_token = parent_controller.bearer_token
            print(f"[DEBUG] BatchRegisterWidget: parent_controllerからトークンを設定")
        
        # 既存の一時フォルダをクリーンアップ
        self.cleanup_temp_folders_on_init()
        
        self.setup_ui()
        self.connect_signals()
        self.load_initial_data()
        self.adjust_window_size()
        print("[DEBUG] BatchRegisterWidget初期化完了")
        
    def setup_ui(self):
        """UIセットアップ"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # スタイル設定
        self.setStyleSheet(BATCH_REGISTER_STYLE)
        
        # スプリッターでエリア分割
        splitter = QSplitter(Qt.Horizontal)
        
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
        
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)
    
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
        
        # ファイルセット一覧
        fileset_group = QGroupBox("ファイルセット一覧")
        fileset_layout = QVBoxLayout()
        
        # ツールバー
        toolbar_layout = QHBoxLayout()
        
        toolbar_layout.addStretch()
        
        clear_all_btn = QPushButton("全て削除")
        clear_all_btn.clicked.connect(self.clear_all_filesets)
        toolbar_layout.addWidget(clear_all_btn)
        
        fileset_layout.addLayout(toolbar_layout)
        
        # ファイルセットテーブル
        self.fileset_table = FileSetTableWidget()
        self.fileset_table.set_file_set_manager(self.file_set_manager)  # file_set_managerを設定
        fileset_layout.addWidget(self.fileset_table)
        
        fileset_group.setLayout(fileset_layout)
        layout.addWidget(fileset_group)
        
        # ファイルセット詳細・設定
        detail_group = QGroupBox("選択ファイルセット設定")
        detail_layout = QVBoxLayout()
        
        # 上部に適用ボタンを配置（色付け）
        button_layout = QHBoxLayout()
        
        # 適用ボタン（旧設定保存ボタン）
        save_btn = QPushButton("適用")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        save_btn.setToolTip("現在の設定を選択されたファイルセットに適用します")
        save_btn.clicked.connect(self.save_fileset_config)
        button_layout.addWidget(save_btn)
        
        apply_all_btn = QPushButton("全適用")
        apply_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        apply_all_btn.setToolTip("現在の設定を全てのファイルセットに適用します")
        apply_all_btn.clicked.connect(self.apply_to_all_filesets)
        button_layout.addWidget(apply_all_btn)
        
        apply_selected_btn = QPushButton("選択適用")
        apply_selected_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: black;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
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
            print(f"[WARNING] データセット選択ウィジェット作成失敗: {e}")
            # フォールバック: 通常のコンボボックス
            self.dataset_combo = QComboBox()
            self.dataset_combo.setEditable(True)
            self.dataset_combo.setMinimumWidth(400)
            self.dataset_combo.addItem("")
            self.dataset_combo.setCurrentIndex(0)
            self.dataset_combo.lineEdit().setPlaceholderText("リストから選択、またはキーワードで検索して選択してください")
            dataset_layout.addWidget(self.dataset_combo)
        
        detail_layout.addLayout(dataset_layout)
        
        # スクロールエリアでラップ
        scroll_area = QScrollArea()
        self.scroll_widget = QWidget()  # クラス属性として保存
        scroll_layout = QVBoxLayout()
        
        # データエントリー基本情報
        data_group = QGroupBox("データエントリー基本情報")
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
        scroll_layout.addWidget(data_group)
        
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
        scroll_layout.addWidget(sample_group)
        
        # 廃止されたsample_mode_comboの参照を削除（sample_id_comboで統合）
        self.sample_mode_combo = self.sample_id_combo  # 互換性維持
        
        # 固有情報（インボイススキーマ対応）- QGroupBoxを削除し直接レイアウトに追加
        self.schema_form_layout = QVBoxLayout()
        self.schema_form_layout.setContentsMargins(10, 10, 10, 10)
        
        # 初期状態のメッセージ
        self.schema_placeholder_label = QLabel("データセット選択後に固有情報入力フォームが表示されます")
        self.schema_placeholder_label.setAlignment(Qt.AlignCenter)
        self.schema_placeholder_label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
        self.schema_form_layout.addWidget(self.schema_placeholder_label)
        
        # 固有情報フォームを直接scroll_layoutに追加（QGroupBox不使用）
        scroll_layout.addLayout(self.schema_form_layout)
        
        self.scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(self.scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        detail_layout.addWidget(scroll_area)
        
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_execution_area(self) -> QWidget:
        """登録実行ペイン作成"""
        # グループボックスでレジェンドを追加
        widget = QGroupBox("登録実行")
        widget.setStyleSheet("""
            QGroupBox {
                background-color: #f8f9fa;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin: 5px;
                padding-top: 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #495057;
            }
        """)
        
        layout = QHBoxLayout()
        
        # 左側：サマリー情報
        summary_layout = QVBoxLayout()
        
        self.summary_label = QLabel("ファイルセット: 0個、総ファイル数: 0、総サイズ: 0 B")
        self.summary_label.setStyleSheet("font-weight: bold; color: #495057;")
        summary_layout.addWidget(self.summary_label)
        
        self.estimate_label = QLabel("推定処理時間: 計算中...")
        self.estimate_label.setStyleSheet("color: #6c757d;")
        summary_layout.addWidget(self.estimate_label)
        
        # ステータスラベル追加
        self.status_label = QLabel("一括登録の準備ができました")
        self.status_label.setStyleSheet("color: #28a745; font-style: italic;")
        summary_layout.addWidget(self.status_label)
        
        layout.addLayout(summary_layout)
        
        layout.addStretch()
        
        # 右側：実行ボタン
        button_layout = QVBoxLayout()
        
        preview_btn = QPushButton("プレビュー")
        preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        preview_btn.clicked.connect(self.preview_batch_register)
        button_layout.addWidget(preview_btn)
        
        execute_btn = QPushButton("一括登録実行")
        execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 12px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        execute_btn.clicked.connect(self.execute_batch_register)
        button_layout.addWidget(execute_btn)
        
        # 一時フォルダ削除ボタンを追加
        cleanup_btn = QPushButton("一時フォルダ削除")
        cleanup_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
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
            print(f"[DEBUG] _get_bearer_token: 自分のプロパティから取得")
        
        # 2. 親ウィジェットから取得を試行
        if not bearer_token:
            parent_widget = self.parent()
            while parent_widget:
                if hasattr(parent_widget, 'bearer_token') and parent_widget.bearer_token:
                    bearer_token = parent_widget.bearer_token
                    print(f"[DEBUG] _get_bearer_token: 親ウィジェット {type(parent_widget).__name__} から取得")
                    break
                parent_widget = parent_widget.parent()
        
        # 3. AppConfigManagerから取得を試行
        if not bearer_token:
            try:
                from classes.managers.app_config_manager import get_config_manager
                app_config = get_config_manager()
                bearer_token = app_config.get('bearer_token')
                if bearer_token:
                    print(f"[DEBUG] _get_bearer_token: AppConfigManagerから取得")
            except Exception as e:
                print(f"[WARNING] _get_bearer_token: AppConfigManagerからの取得に失敗: {e}")
        
        # 4. 親コントローラから取得を試行
        if not bearer_token and hasattr(self, 'parent_controller'):
            if hasattr(self.parent_controller, 'bearer_token') and self.parent_controller.bearer_token:
                bearer_token = self.parent_controller.bearer_token
                print(f"[DEBUG] _get_bearer_token: parent_controllerから取得")
        
        if not bearer_token:
            print(f"[WARNING] _get_bearer_token: ベアラートークンが見つかりませんでした")
        else:
            print(f"[DEBUG] _get_bearer_token: トークン取得成功 (長さ: {len(bearer_token)})")
        
        return bearer_token
    
    def set_bearer_token(self, token: str):
        """ベアラートークンを設定"""
        self.bearer_token = token
        print(f"[DEBUG] BatchRegisterWidget: ベアラートークンを設定 (長さ: {len(token) if token else 0})")
    
    def update_bearer_token_from_parent(self):
        """親コントローラからベアラートークンを更新"""
        if hasattr(self.parent_controller, 'bearer_token'):
            self.bearer_token = self.parent_controller.bearer_token
            print(f"[DEBUG] BatchRegisterWidget: parent_controllerからトークンを更新")
            
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
                print(f"[INFO] ファイルセット '{file_set.name}' の一時フォルダ・マッピングファイルを作成/更新")
                self._create_temp_folder_and_mapping(file_set)
            else:
                print(f"[INFO] ファイルセット '{file_set.name}' の一時フォルダ・マッピングファイルは既に存在")
                
        except Exception as e:
            print(f"[ERROR] 一時フォルダ・マッピングファイル確認エラー: {e}")
    
    def _create_temp_folder_and_mapping(self, file_set):
        """ファイルセットの一時フォルダとマッピングファイルを作成（UUID対応版）"""
        try:
            if not file_set or not file_set.items:
                print(f"[WARNING] ファイルセットが空のため、一時フォルダ作成をスキップ: {file_set.name if file_set else 'None'}")
                return
            
            from ..core.temp_folder_manager import TempFolderManager
            
            temp_manager = TempFolderManager()
            temp_folder, mapping_file = temp_manager.create_temp_folder_for_fileset(file_set)
            
            # UUID固定版では、ファイルセットオブジェクト内に直接パスが設定される
            # （temp_folder_path と mapping_file_path）
            print(f"[INFO] ファイルセット '{file_set.name}' の一時フォルダとマッピングファイルを作成")
            print(f"[INFO]   ファイルセットUUID: {file_set.uuid}")
            print(f"[INFO]   一時フォルダ: {temp_folder}")
            print(f"[INFO]   マッピングファイル: {mapping_file}")
            
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
            print(f"[ERROR] 一時フォルダ・マッピングファイル作成エラー: {e}")
            # エラーが発生してもファイルセット作成は続行
    
    def cleanup_temp_folders(self):
        """一時フォルダを一括削除（UUID対応版）"""
        try:
            reply = QMessageBox.question(
                self, "確認", 
                "本アプリで作成した一時フォルダをすべて削除しますか？\n\n"
                "この操作は元に戻せません。",
                QMessageBox.Yes | QMessageBox.No
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
            print(f"[ERROR] 一時フォルダ削除エラー: {e}")
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
            print(f"[DEBUG] データセットコンボボックスイベント接続: {type(self.dataset_combo)}")
            self.dataset_combo.currentIndexChanged.connect(self.on_dataset_changed)
            
            # 追加のイベント処理（即座の反応を確保）
            self.dataset_combo.activated.connect(self.on_dataset_changed)
            
            print(f"[DEBUG] データセット選択イベント接続完了")
            
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
            print(f"[ERROR] ファイルセット更新エラー: {e}")
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
                
                print(f"[INFO] ファイルセット '{fileset.name}' の整理方法を '{organize_method}' に設定")
                
        except Exception as e:
            print(f"[ERROR] 整理方法変更エラー: {e}")
    
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
            print(f"[ERROR] ファイルセットコピーエラー: {e}")
            QMessageBox.warning(self, "エラー", f"ファイルセットのコピーに失敗しました: {e}")
    
    def delete_fileset_row(self, row):
        """ファイルセット行を削除"""
        try:
            if row < len(self.file_set_manager.file_sets):
                fileset = self.file_set_manager.file_sets[row]
                
                reply = QMessageBox.question(
                    self, "確認",
                    f"ファイルセット '{fileset.name}' を削除しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
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
            print(f"[ERROR] ファイルセット削除エラー: {e}")
            QMessageBox.warning(self, "エラー", f"ファイルセットの削除に失敗しました: {e}")
    
    def refresh_fileset_display(self):
        """ファイルセット表示を更新"""
        print(f"[DEBUG] refresh_fileset_display: 呼び出された")
        try:
            print(f"[DEBUG] refresh_fileset_display: file_set_manager={self.file_set_manager}")
            if self.file_set_manager:
                print(f"[DEBUG] refresh_fileset_display: file_sets count={len(self.file_set_manager.file_sets)}")
                for i, fs in enumerate(self.file_set_manager.file_sets):
                    print(f"[DEBUG] FileSet {i}: id={fs.id}, name={fs.name}, items={len(fs.items)}")
            
            if self.file_set_manager and self.file_set_manager.file_sets:
                # ファイルセットテーブルを更新
                print(f"[DEBUG] refresh_fileset_display: テーブル更新開始")
                self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
                print(f"[DEBUG] refresh_fileset_display: テーブル更新完了")
            else:
                # ファイルセットがない場合はクリア
                print(f"[DEBUG] refresh_fileset_display: テーブルクリア")
                self.fileset_table.setRowCount(0)
            
            # ファイルセット選択コンボボックスも更新
            self.update_target_fileset_combo()
                
        except Exception as e:
            print(f"[ERROR] ファイルセット表示更新エラー: {e}")
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
            
            reply = QMessageBox.question(
                self, "確認",
                f"現在の設定をすべてのファイルセット（{len(self.file_set_manager.file_sets)}個）に適用しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                applied_count = 0
                for fileset in self.file_set_manager.file_sets:
                    self._apply_settings_to_fileset(fileset, settings)
                    applied_count += 1
                
                QMessageBox.information(self, "完了", f"{applied_count}個のファイルセットに設定を適用しました。")
                self.refresh_fileset_display()
            
        except Exception as e:
            print(f"[ERROR] 全ファイルセット適用エラー: {e}")
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
            
            reply = QMessageBox.question(
                self, "確認",
                f"現在の設定をファイルセット '{target_name}' に適用しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self._apply_settings_to_fileset(target_fileset, settings)
                QMessageBox.information(self, "完了", f"ファイルセット '{target_name}' に設定を適用しました。")
                self.refresh_fileset_display()
            
        except Exception as e:
            print(f"[ERROR] ターゲットファイルセット適用エラー: {e}")
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
                        print(f"[DEBUG] get_current_settings - データセット情報: {current_data}")
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
                        print(f"[DEBUG] save_fileset_config - 既存試料選択: {selected_sample_data['id']}")
                    else:
                        # UUIDが取得できない場合は新規として扱う
                        settings['sample_mode'] = 'new'
                        print("[WARNING] 既存試料が選択されているがUUIDが取得できませんでした")
                else:
                    # 新規作成の場合
                    settings['sample_mode'] = 'new'
                    print("[DEBUG] save_fileset_config - 新規試料作成")
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
            
            # インボイススキーマフォームから取得を試行
            if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form:
                try:
                    schema_custom_values = self.invoice_schema_form.get_form_data()
                    if schema_custom_values:
                        custom_values.update(schema_custom_values)
                        print(f"[DEBUG] get_current_settings - インボイススキーマから取得: {schema_custom_values}")
                except Exception as e:
                    print(f"[WARNING] インボイススキーマフォームからの取得エラー: {e}")
            
            # 従来のカスタムフィールドウィジェットからも取得
            if hasattr(self, 'custom_field_widgets'):
                for field_name, widget in self.custom_field_widgets.items():
                    try:
                        if hasattr(widget, 'text'):
                            value = widget.text()
                        elif hasattr(widget, 'toPlainText'):
                            value = widget.toPlainText()
                        elif hasattr(widget, 'currentText'):
                            value = widget.currentText()
                        else:
                            continue
                        
                        if value:  # 空でない値のみ保存
                            custom_values[field_name] = value
                    except Exception as e:
                        print(f"[WARNING] カスタムフィールド '{field_name}' の取得エラー: {e}")
                        
            settings['custom_values'] = custom_values
            
            print(f"[DEBUG] get_current_settings - 固有情報取得完了: {len(custom_values)}個の項目")
            
            print(f"[DEBUG] get_current_settings: {settings}")
            
        except Exception as e:
            print(f"[ERROR] 設定取得エラー: {e}")
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
                print(f"[DEBUG] データセットIDを fileset.dataset_id に設定: {settings['dataset_id']}")
                
                # dataset_infoも同時に設定
                if not hasattr(fileset, 'dataset_info') or not fileset.dataset_info:
                    fileset.dataset_info = {}
                fileset.dataset_info['id'] = settings['dataset_id']
                print(f"[DEBUG] データセットIDを fileset.dataset_info['id'] に設定: {settings['dataset_id']}")
                
            if 'dataset_name' in settings:
                if not hasattr(fileset, 'dataset_info') or not fileset.dataset_info:
                    fileset.dataset_info = {}
                fileset.dataset_info['name'] = settings['dataset_name']
                print(f"[DEBUG] データセット名を fileset.dataset_info['name'] に設定: {settings['dataset_name']}")
                
            # extended_configにも保存（フォールバック用）
            if 'selected_dataset' in settings:
                if not hasattr(fileset, 'extended_config'):
                    fileset.extended_config = {}
                fileset.extended_config['selected_dataset'] = settings['selected_dataset']
                print(f"[DEBUG] データセット情報を extended_config に保存: {settings['selected_dataset']}")
            
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
            if 'custom_values' in settings and settings['custom_values']:
                if not hasattr(fileset, 'custom_values'):
                    fileset.custom_values = {}
                
                # カスタム値を更新（既存値を上書き）
                fileset.custom_values.clear()
                fileset.custom_values.update(settings['custom_values'])
                
                print(f"[DEBUG] カスタム値をファイルセットに適用: {len(settings['custom_values'])}個")
                for key, value in settings['custom_values'].items():
                    print(f"[DEBUG]   - {key}: {value}")
            
            # 拡張設定に保存（バックアップとして、ただし内部データは除外）
            if not hasattr(fileset, 'extended_config'):
                fileset.extended_config = {}
            
            # 内部データを除外してから保存
            filtered_settings = {k: v for k, v in settings.items() 
                               if k not in {'selected_dataset'}}
            fileset.extended_config.update(filtered_settings)
            
            print(f"[INFO] ファイルセット '{fileset.name}' に設定を適用しました")
            print(f"[DEBUG] 適用後のfileset.data_name: {getattr(fileset, 'data_name', None)}")
            print(f"[DEBUG] 適用後のfileset.dataset_id: {getattr(fileset, 'dataset_id', None)}")
            print(f"[DEBUG] 適用後のfileset.sample_mode: {getattr(fileset, 'sample_mode', None)}")
            
        except Exception as e:
            print(f"[ERROR] ファイルセット設定適用エラー: {e}")
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
            print(f"[ERROR] ターゲットファイルセットコンボボックス更新エラー: {e}")
    
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
            print(f"[DEBUG] load_directory: FileSetManager作成完了 {directory}")
            
            # FileSetTableWidgetにfile_set_managerを再設定
            if hasattr(self, 'fileset_table') and self.fileset_table:
                print(f"[DEBUG] load_directory: FileSetTableWidgetにfile_set_manager再設定")
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
            print(f"[WARNING] 設定ファイル読み込みエラー: {e}")
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
            print(f"[WARNING] 設定ファイル保存エラー: {e}")
    
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
            print(f"Tree expansion warning: {e}")
    
    def refresh_file_tree(self):
        """ファイルツリー更新"""
        if self.file_set_manager:
            directory = self.file_set_manager.base_directory
            self.load_directory(directory)
    
    def refresh_file_tree_with_warning(self):
        """ファイルツリー更新（警告付き）"""
        reply = QMessageBox.question(self, "確認", 
            "ファイルツリーを再読み込みします。\n\n「含む」状態がリセットされますが、続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        
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
            print(f"[ERROR] 全選択エラー: {e}")
    
    def deselect_all_files(self):
        """ファイルツリーの全てのファイルの選択を解除"""
        try:
            # ツリーの全アイテムを走査してチェックボックスを解除
            root = self.file_tree.invisibleRootItem()
            self._set_all_items_checked(root, False)
        except Exception as e:
            print(f"[ERROR] 全解除エラー: {e}")
    
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
                        print(f"[DEBUG] {indent}チェックボックス状態確認: {file_item.name} -> checked={is_checked}")
                    else:
                        # チェックボックスがない場合はFileItemの状態を参照
                        is_checked = not getattr(file_item, 'is_excluded', False)
                        print(f"[DEBUG] {indent}FileItem状態参照: {file_item.name} -> excluded={getattr(file_item, 'is_excluded', False)} -> checked={is_checked}")
                    
                    # チェック済みの場合は追加
                    if is_checked:
                        checked_items.append(file_item)
                        print(f"[DEBUG] {indent}✓ チェック済みアイテム追加: {file_item.name} ({file_item.file_type.name}) - Path: {file_item.relative_path}")
                    else:
                        print(f"[DEBUG] {indent}✗ チェックなしアイテム除外: {file_item.name} ({file_item.file_type.name})")
                else:
                    print(f"[DEBUG] {indent}⚠ FileItemが見つからない: tree_item_id={id(child)}")
                
                # 子アイテムも再帰的に処理
                collect_checked_items(child, depth + 1)
        
        print(f"[DEBUG] _get_checked_items_from_tree: 開始")
        root = self.file_tree.invisibleRootItem()
        collect_checked_items(root)
        
        print(f"[DEBUG] _get_checked_items_from_tree: 合計チェック済みアイテム数={len(checked_items)}")
        
        # 収集されたアイテムのパス一覧を表示
        for item in checked_items:
            print(f"[DEBUG] 最終収集: {item.name} -> {item.relative_path}")
            
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
        reply = QMessageBox.question(self, "確認", 
            "既存のファイルセットをリセットして、全体を1つのファイルセットとして作成します。\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.auto_assign_all_as_one()
    
    def auto_assign_by_top_dirs_with_confirm(self):
        """最上位フォルダごとにファイルセット作成（確認ダイアログ付き）"""
        reply = QMessageBox.question(self, "確認", 
            "既存のファイルセットをリセットして、最上位フォルダごとにファイルセットを作成します。\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.auto_assign_by_top_dirs()
    
    def auto_assign_all_dirs_with_confirm(self):
        """全フォルダを個別ファイルセット作成（確認ダイアログ付き）"""
        reply = QMessageBox.question(self, "確認", 
            "既存のファイルセットをリセットして、全フォルダを個別にファイルセットとして作成します。\n\n続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.auto_assign_all_dirs()
    
    def auto_assign_all_as_one(self):
        """全体で1つのファイルセット作成"""
        print(f"[DEBUG] auto_assign_all_as_one: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            # 既存のファイルセットをクリア
            self.file_set_manager.clear_all_filesets()
            print(f"[DEBUG] auto_assign_all_as_one: 既存ファイルセットをクリア")
            
            # 「含む」チェックボックスがオンのファイルのみを取得
            all_checked_items = self._get_checked_items_from_tree()
            selected_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            print(f"[DEBUG] auto_assign_all_as_one: チェック済みファイル数={len(selected_files)}")
            
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
            
            print(f"[DEBUG] auto_assign_all_as_one: 最終ファイルセット数={len(file_sets) if file_sets else 0}")
            print(f"[DEBUG] auto_assign_all_as_one: refresh_fileset_display() 呼び出し直前")
            self.refresh_fileset_display()
            print(f"[DEBUG] auto_assign_all_as_one: refresh_fileset_display() 呼び出し完了")
            self.update_summary()
        except Exception as e:
            print(f"[ERROR] auto_assign_all_as_one: エラー発生: {e}")
            import traceback
            traceback.print_exc()
    
    def auto_assign_by_top_dirs(self):
        """最上位フォルダごとにファイルセット作成"""
        print(f"[DEBUG] auto_assign_by_top_dirs: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            # 既存のファイルセットをクリア
            self.file_set_manager.clear_all_filesets()
            print(f"[DEBUG] auto_assign_by_top_dirs: 既存ファイルセットをクリア")
            
            # 「含む」チェックボックスがオンのファイルのみを取得
            all_checked_items = self._get_checked_items_from_tree()
            selected_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            print(f"[DEBUG] auto_assign_by_top_dirs: チェック済みファイル数={len(selected_files)}")
            
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
            
            print(f"[DEBUG] auto_assign_by_top_dirs: 最終ファイルセット数={len(file_sets) if file_sets else 0}")
            print(f"[DEBUG] auto_assign_by_top_dirs: refresh_fileset_display() 呼び出し直前")
            self.refresh_fileset_display()
            print(f"[DEBUG] auto_assign_by_top_dirs: refresh_fileset_display() 呼び出し完了")
            self.update_summary()
        except Exception as e:
            print(f"[ERROR] auto_assign_by_top_dirs: エラー発生: {e}")
            import traceback
            traceback.print_exc()
    
    def auto_assign_all_dirs(self):
        """全フォルダを個別ファイルセット作成"""
        print(f"[DEBUG] auto_assign_all_dirs: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            # 既存のファイルセットをクリア
            self.file_set_manager.clear_all_filesets()
            print(f"[DEBUG] auto_assign_all_dirs: 既存ファイルセットをクリア")
            
            # 「含む」チェックボックスがオンのファイルのみを取得
            all_checked_items = self._get_checked_items_from_tree()
            selected_files = [item for item in all_checked_items if item.file_type == FileType.FILE]
            print(f"[DEBUG] auto_assign_all_dirs: チェック済みファイル数={len(selected_files)}")
            
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
            
            print(f"[DEBUG] auto_assign_all_dirs: 最終ファイルセット数={len(file_sets) if file_sets else 0}")
            print(f"[DEBUG] auto_assign_all_dirs: refresh_fileset_display() 呼び出し直前")
            self.refresh_fileset_display()
            print(f"[DEBUG] auto_assign_all_dirs: refresh_fileset_display() 呼び出し完了")
            self.update_summary()
        except Exception as e:
            print(f"[ERROR] auto_assign_all_dirs: エラー発生: {e}")
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
            if dialog.exec_() == QDialog.Accepted:
                selected_items = dialog.get_selected_items()
                if selected_items:
                    # ファイルセット名入力
                    name, ok = QInputDialog.getText(self, "ファイルセット名", "ファイルセット名を入力してください:")
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
            print(f"[ERROR] 手動ファイルセット作成エラー: {e}")
            QMessageBox.warning(self, "エラー", f"手動ファイルセット作成に失敗しました:\n{str(e)}")
    
    def clear_all_filesets(self):
        """全ファイルセット削除"""
        reply = QMessageBox.question(
            self, "確認", "全てのファイルセットを削除しますか？",
            QMessageBox.Yes | QMessageBox.No
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
                print(f"[DEBUG] ファイルセット選択: データセットID={file_set.dataset_id}を設定中")
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
                        print(f"[DEBUG] データセットコンボボックス: インデックス{i}を選択")
                        self.dataset_combo.setCurrentIndex(i)
                        found = True
                        # データセット選択変更イベントを手動で発火
                        print(f"[DEBUG] 復元時on_dataset_changed呼び出し前: invoice_schema_form={getattr(self, 'invoice_schema_form', None)}")
                        self.on_dataset_changed(i)
                        print(f"[DEBUG] 復元時on_dataset_changed呼び出し後: invoice_schema_form={getattr(self, 'invoice_schema_form', None)}")
                        break
                if not found:
                    print(f"[WARNING] データセットID {file_set.dataset_id} がコンボボックスに見つかりません")
                    # データセット未選択状態にする（有効な最初のアイテムを選択）
                    self.dataset_combo.setCurrentIndex(-1)
            else:
                print("[DEBUG] ファイルセット選択: データセット未設定")
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
                            print(f"[DEBUG] extended_configからカスタム値を復元: {len(custom_values)}個")
                        else:
                            # インボイススキーマ項目を直接チェック
                            schema_fields = [
                                'electron_gun', 'accelerating_voltage', 'observation_method',
                                'ion_species', 'major_processing_observation_conditions', 'remark'
                            ]
                            for field in schema_fields:
                                if field in extended_config and extended_config[field]:
                                    custom_values[field] = extended_config[field]
                    
                    print(f"[DEBUG] ファイルセット選択時のカスタム値復元: {len(custom_values)}個の項目")
                    for key, value in custom_values.items():
                        print(f"[DEBUG]   復元: {key} = {value}")
                    
                    # フォーム型をチェックして適切なメソッドを呼び出す
                    if hasattr(self.invoice_schema_form, 'set_form_data'):
                        if custom_values:
                            self.invoice_schema_form.set_form_data(custom_values)
                            print(f"[DEBUG] インボイススキーマフォームにカスタム値を設定完了")
                        else:
                            self.invoice_schema_form.clear_form()
                            print(f"[DEBUG] カスタム値が空のため、フォームをクリア")
                    else:
                        print(f"[DEBUG] invoice_schema_form ({type(self.invoice_schema_form)}) はset_form_dataメソッドを持っていません")
                        # フォーム参照をクリアして再作成を促す
                        print(f"[DEBUG] 現在のデータセット情報で再作成を試行...")
                        
                        # 現在選択されているデータセット情報を取得
                        current_dataset_data = self.dataset_combo.currentData()
                        if current_dataset_data and isinstance(current_dataset_data, dict):
                            print(f"[DEBUG] データセット情報を使用してスキーマフォーム再作成: {current_dataset_data.get('id')}")
                            # フォーム再作成を試行
                            self.update_schema_form(current_dataset_data, force_clear=False)
                            
                            # フォーム再作成後、カスタム値を再設定
                            if hasattr(self.invoice_schema_form, 'set_form_data') and custom_values:
                                print(f"[DEBUG] 再作成後にカスタム値を設定")
                                self.invoice_schema_form.set_form_data(custom_values)
                                print(f"[DEBUG] 再設定完了")
                            else:
                                print(f"[DEBUG] 再作成後もset_form_dataメソッドが利用できません")
                        
                        # フォーム参照のクリアは不要（update_schema_formで更新済み）
                        
                except Exception as e:
                    print(f"[WARNING] カスタム値復元エラー: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("[DEBUG] インボイススキーマフォームが存在しないため、カスタム値復元をスキップ")
            
            # 現在のファイルセットを記録
            self.current_fileset = file_set
            
        finally:
            # ファイルセット復元処理完了フラグをリセット
            self._restoring_fileset = False
            print("[DEBUG] ファイルセット復元処理完了 - 自動設定適用を再有効化")
    
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
                            print(f"[DEBUG] 前回と同じオプション有効: 上位エントリー({previous_fileset.name})に試料情報あり")
                        else:
                            print(f"[DEBUG] 前回と同じオプション無効: 上位エントリー({previous_fileset.name})に試料情報なし")
                    else:
                        print("[DEBUG] 前回と同じオプション無効: 上位エントリーなし")
                else:
                    print("[DEBUG] 前回と同じオプション無効: ファイルセット未選択")
            else:
                if self.file_set_manager:
                    print(f"[DEBUG] 前回と同じオプション無効: ファイルセット数={len(self.file_set_manager.file_sets)}")
                else:
                    print("[DEBUG] 前回と同じオプション無効: ファイルセットマネージャー未初期化")
            
            # オプションの追加/削除を制御
            if should_enable_same_as_previous and not has_same_as_previous:
                # 「前回と同じ」オプションを追加
                self.sample_mode_combo.addItem("前回と同じ")
                print("[INFO] 「前回と同じ」オプションを追加")
            elif not should_enable_same_as_previous and has_same_as_previous:
                # 「前回と同じ」オプションを削除
                for i in range(self.sample_mode_combo.count()):
                    if self.sample_mode_combo.itemText(i) == "前回と同じ":
                        # 現在選択されている場合は、別のオプションに変更
                        if self.sample_mode_combo.currentIndex() == i:
                            self.sample_mode_combo.setCurrentIndex(0)  # 「新規作成」に変更
                        self.sample_mode_combo.removeItem(i)
                        print("[INFO] 「前回と同じ」オプションを削除")
                        break
                        
        except Exception as e:
            print(f"[WARNING] 前回と同じオプション制御エラー: {e}")
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
        print(f"[DEBUG] 試料モード状態確認:")
        print(f"[DEBUG] - currentText(): '{sample_mode_text}'")
        print(f"[DEBUG] - currentIndex(): {sample_mode_index}")
        print(f"[DEBUG] - count(): {self.sample_mode_combo.count()}")
        for i in range(self.sample_mode_combo.count()):
            print(f"[DEBUG] - itemText({i}): '{self.sample_mode_combo.itemText(i)}'")
        
        # 試料モード判定：index=0は新規作成、それ以外は既存試料選択
        if sample_mode_index == 0 or sample_mode_text == "新規作成":
            # 新規作成モード
            selected_fileset.sample_mode = "new"
            selected_fileset.sample_name = self.sample_name_edit.text()
            selected_fileset.sample_description = self.sample_description_edit.toPlainText()
            selected_fileset.sample_composition = self.sample_composition_edit.text()
            print(f"[DEBUG] 試料モード設定: new")
            print(f"[DEBUG] - sample_name: {selected_fileset.sample_name}")
            print(f"[DEBUG] - sample_description: {selected_fileset.sample_description}")
            print(f"[DEBUG] - sample_composition: {selected_fileset.sample_composition}")
        elif sample_mode_text == "前回と同じ":
            # 前回と同じモード
            selected_fileset.sample_mode = "same_as_previous"
            print(f"[DEBUG] 試料モード設定: same_as_previous")
        else:
            # 既存試料選択モード（index > 0 かつ "前回と同じ"以外）
            selected_fileset.sample_mode = "existing"
            
            # 統合コンボボックスの場合、sample_mode_comboのcurrentData()からUUIDを取得
            sample_data = self.sample_mode_combo.currentData()
            print(f"[DEBUG] 既存試料選択状態:")
            print(f"[DEBUG] - sample_mode_combo.currentText(): '{sample_mode_text}'")
            print(f"[DEBUG] - sample_mode_combo.currentData(): {sample_data}")
            print(f"[DEBUG] - sample_data type: {type(sample_data)}")
            
            # sample_mode_comboの全データ内容も確認
            print(f"[DEBUG] - sample_mode_combo全項目データ確認:")
            for idx in range(self.sample_mode_combo.count()):
                item_text = self.sample_mode_combo.itemText(idx)
                item_data = self.sample_mode_combo.itemData(idx)
                print(f"[DEBUG]   [{idx}] '{item_text}' -> {item_data}")
            
            if sample_data and isinstance(sample_data, dict) and 'id' in sample_data:
                selected_fileset.sample_id = sample_data['id']
                print(f"[DEBUG] 既存試料ID保存成功（統合コンボボックス）: {sample_data['id']}")
            else:
                # フォールバック：sample_id_comboがある場合はそちらを確認
                if hasattr(self, 'sample_id_combo'):
                    fallback_data = self.sample_id_combo.currentData()
                    if fallback_data and isinstance(fallback_data, dict) and 'id' in fallback_data:
                        selected_fileset.sample_id = fallback_data['id']
                        print(f"[DEBUG] 既存試料ID保存成功（フォールバック）: {fallback_data['id']}")
                    else:
                        selected_fileset.sample_id = self.sample_mode_combo.currentText()
                        print(f"[WARNING] 既存試料IDの取得に失敗、テキストを使用: {selected_fileset.sample_id}")
                        print(f"[WARNING] - sample_data: {sample_data}")
                        print(f"[WARNING] - fallback_data: {fallback_data if hasattr(self, 'sample_id_combo') else 'No sample_id_combo'}")
                else:
                    selected_fileset.sample_id = self.sample_mode_combo.currentText()
                    print(f"[WARNING] 既存試料IDの取得に失敗（sample_id_combo無し）、テキストを使用: {selected_fileset.sample_id}")
                    print(f"[WARNING] - sample_data: {sample_data}")
            print(f"[DEBUG] 試料モード設定: existing")
        
        # カスタム値を取得（インボイススキーマフォーム）
        print(f"[DEBUG] インボイススキーマフォーム状態確認:")
        print(f"[DEBUG] - hasattr(self, 'invoice_schema_form'): {hasattr(self, 'invoice_schema_form')}")
        if hasattr(self, 'invoice_schema_form'):
            print(f"[DEBUG] - self.invoice_schema_form: {self.invoice_schema_form}")
            print(f"[DEBUG] - invoice_schema_form is not None: {self.invoice_schema_form is not None}")
            
        if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form:
            try:
                # QGroupBoxの場合はget_schema_form_values関数を使用
                from classes.utils.schema_form_util import get_schema_form_values
                custom_values = get_schema_form_values(self.invoice_schema_form)
                selected_fileset.custom_values = custom_values
                print(f"[DEBUG] カスタム値を保存: {len(custom_values)}個の項目")
                for key, value in custom_values.items():
                    print(f"[DEBUG]   {key}: {value}")
            except Exception as e:
                print(f"[WARNING] カスタム値取得エラー: {e}")
                import traceback
                traceback.print_exc()
                selected_fileset.custom_values = {}
        else:
            print("[DEBUG] インボイススキーマフォームが存在しません")
            # フォールバック: 既存のcustom_values属性を維持
            if hasattr(selected_fileset, 'custom_values'):
                print(f"[DEBUG] 既存のcustom_values属性を維持: {selected_fileset.custom_values}")
            else:
                selected_fileset.custom_values = {}
                print("[DEBUG] 空のcustom_valuesを設定")
        
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
                print(f"[DEBUG] 既存試料IDをextended_configに保存: {sample_data['id']}")
            else:
                selected_fileset.extended_config['sample_id'] = self.sample_id_combo.currentText()
                print(f"[WARNING] 既存試料IDの取得に失敗、extended_configにテキストを保存: {self.sample_id_combo.currentText()}")
        else:
            # 新規作成または前回と同じの場合
            selected_fileset.extended_config['sample_name'] = self.sample_name_edit.text()
            selected_fileset.extended_config['sample_description'] = self.sample_description_edit.toPlainText()
            selected_fileset.extended_config['sample_composition'] = self.sample_composition_edit.text()
        
        # カスタム値もextended_configに保存（データ登録時のフォーム値構築で利用）
        if hasattr(selected_fileset, 'custom_values') and selected_fileset.custom_values:
            selected_fileset.extended_config['custom_values'] = selected_fileset.custom_values
            print(f"[DEBUG] カスタム値もextended_configに保存: {len(selected_fileset.custom_values)}個")
        else:
            selected_fileset.extended_config['custom_values'] = {}
        
        # テーブル更新
        self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
        
        # 「前回と同じ」オプションを再評価
        self.update_same_as_previous_option()
        
        # 最終確認：extended_configの内容をログ出力
        print(f"[DEBUG] save_fileset_config完了 - extended_config内容:")
        for key, value in selected_fileset.extended_config.items():
            print(f"[DEBUG]   - {key}: {value}")
        print(f"[DEBUG] save_fileset_config完了 - 直接属性:")
        print(f"[DEBUG]   - sample_mode: {getattr(selected_fileset, 'sample_mode', 'None')}")
        print(f"[DEBUG]   - sample_id: {getattr(selected_fileset, 'sample_id', 'None')}")
        
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
            
            # Bearerトークンを取得（統一メソッドを使用）
            bearer_token = self._get_bearer_token()
            
            # 新しい詳細プレビューダイアログを表示
            from classes.data_entry.ui.batch_preview_dialog import BatchRegisterPreviewDialog
            
            dialog = BatchRegisterPreviewDialog(self.file_set_manager.file_sets, self, bearer_token)
            result = dialog.exec_()
            
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
            print(f"[ERROR] プレビューエラー: {e}")
            import traceback
            traceback.print_exc()
    
    def execute_batch_register(self):
        """一括登録実行（ファイルセットごとにデータ登録を自動実行）"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            QMessageBox.warning(self, "エラー", "実行するファイルセットがありません")
            return
        
        # ベアラートークンの確認（統一メソッドを使用）
        bearer_token = self._get_bearer_token()
        
        if not bearer_token:
            QMessageBox.warning(self, "エラー", "認証トークンが設定されていません。ログインを確認してください。")
            return
        
        # 妥当性検証
        is_valid, errors = self.batch_logic.validate_filesets(self.file_set_manager.file_sets)
        if not is_valid:
            error_text = "以下のエラーがあります:\n\n" + "\n".join(errors)
            QMessageBox.warning(self, "検証エラー", error_text)
            return
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self, "確認", 
            f"{len(self.file_set_manager.file_sets)}個のファイルセットを一括登録しますか？\n\n"
            "この処理では以下が実行されます：\n"
            "1. 各ファイルセットのファイル一括アップロード\n"
            "2. 各ファイルセットのデータエントリー登録\n"
            "3. 試料情報の保存\n\n"
            "処理には時間がかかる場合があります。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 一括登録実行（複数ファイルセット一括処理）
            self._execute_multi_fileset_batch_register(bearer_token)
    
    def _execute_multi_fileset_batch_register(self, bearer_token: str):
        """複数ファイルセット一括登録処理"""
        try:
            from .batch_preview_dialog import BatchRegisterPreviewDialog
            
            # 複数ファイルセット用のプレビューダイアログを作成して実行
            batch_dialog = BatchRegisterPreviewDialog(
                file_sets=self.file_set_manager.file_sets,
                parent=self,
                bearer_token=bearer_token
            )
            
            # プログレスダイアログの表示設定
            batch_dialog.show_progress_dialog = True
            
            # 確認ダイアログなしで直接一括データ登録を実行
            batch_dialog._batch_register_all_filesets_without_confirmation()
            
            # 結果を取得して表示
            if hasattr(batch_dialog, 'batch_result') and batch_dialog.batch_result:
                self.on_batch_register_finished(batch_dialog.batch_result)
            
        except Exception as e:
            print(f"[ERROR] 一括登録実行エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"一括登録処理でエラーが発生しました:\n{str(e)}")
            
            # ファイルセットテーブルを更新して状態を反映
            if self.file_set_manager:
                self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
                self.update_summary()
    
    def on_batch_register_finished(self, result: BatchRegisterResult):
        """一括登録完了処理"""
        # 結果表示
        if result.error_count == 0:
            QMessageBox.information(
                self, "完了", 
                f"一括登録が完了しました！\n\n"
                f"成功: {result.success_count}個\n"
                f"処理時間: {result.duration:.1f}秒"
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
            
            QMessageBox.warning(self, "完了（一部エラー）", error_text)
        
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
            print(f"[WARNING] データセット更新エラー: {e}")
            # エラーダイアログは表示しない（起動時の遅延を防ぐため）
    
    def update_dataset_combo(self):
        """データセットコンボボックスを更新"""
        self.dataset_combo.clear()
        
        if not self.datasets:
            self.dataset_combo.addItem("データセットが見つかりません")
            return
        
        # 最初の空のアイテムを追加
        self.dataset_combo.addItem("データセットを選択...")
        
        # データセットを追加
        for dataset in self.datasets:
            dataset_id = dataset.get('id', '')
            attributes = dataset.get('attributes', {})
            title = attributes.get('title', 'タイトルなし')
            
            # コンボボックス表示用のテキスト
            display_text = f"{title} ({dataset_id[:8]}...)" if len(dataset_id) > 8 else f"{title} ({dataset_id})"
            
            # アイテムを追加（データとしてdataset_idを保存）
            self.dataset_combo.addItem(display_text, dataset_id)
    
    def get_selected_dataset_id(self) -> Optional[str]:
        """選択されたデータセットIDを取得"""
        current_index = self.dataset_combo.currentIndex()
        current_text = self.dataset_combo.currentText()
        current_data = self.dataset_combo.currentData()
        
        print(f"[DEBUG] get_selected_dataset_id: currentIndex={current_index}, currentText='{current_text}'")
        
        # インデックス-1は選択なし状態
        if current_index < 0:
            print(f"[DEBUG] get_selected_dataset_id: インデックス{current_index}は選択なし状態")
            return None
        
        # currentDataからデータセットIDを取得
        if current_data:
            # 辞書オブジェクトの場合、'id'キーを取得
            if isinstance(current_data, dict) and 'id' in current_data:
                dataset_id = current_data['id']
                print(f"[DEBUG] get_selected_dataset_id: 辞書からID取得={dataset_id}")
                return dataset_id
            # 文字列の場合はそのまま返す
            elif isinstance(current_data, str):
                print(f"[DEBUG] get_selected_dataset_id: 文字列ID取得={current_data}")
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
                                print(f"[DEBUG] get_selected_dataset_id: テキストから推定={dataset.get('id')}")
                                return dataset.get('id')
                    else:
                        print(f"[DEBUG] get_selected_dataset_id: テキストから抽出={id_part}")
                        return id_part
                except Exception as e:
                    print(f"[DEBUG] get_selected_dataset_id: テキスト解析エラー={e}")
        
        print("[DEBUG] get_selected_dataset_id: データセットIDを取得できませんでした")
        return None
    
    def adjust_window_size(self):
        """一括登録用にウィンドウサイズを調整（通常登録と同等機能）"""
        try:
            # 画面サイズを取得
            screen = QApplication.primaryScreen()
            if not screen:
                return
            
            screen_geometry = screen.geometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
            
            # 一括登録用サイズ設定（通常登録データ登録タブと同等）
            # 横幅：画面の90%または最低1600px（通常登録と同等設定）
            target_width = max(int(screen_width * 0.90), 1600)
            # 高さ：画面の85%または最低900px（通常登録と同等設定）
            target_height = max(int(screen_height * 0.85), 900)
            
            # 画面サイズを超えないよう制限（通常登録と同等）
            target_width = min(target_width, screen_width - 40)
            target_height = min(target_height, screen_height - 80)
            
            print(f"[DEBUG] 画面サイズ: {screen_width}x{screen_height}")
            print(f"[DEBUG] 目標サイズ: {target_width}x{target_height}")
            
            # 親ウィンドウを取得して調整
            top_level = self.window()
            if top_level and top_level != self:
                print(f"[INFO] ウィンドウサイズ調整開始: 現在={top_level.size()}, 目標={target_width}x{target_height}")
                
                # 既存の固定サイズ設定をクリア（通常登録と同等処理）
                try:
                    top_level.setFixedSize(16777215, 16777215)  # Qt最大値でクリア
                except Exception:
                    pass
                
                # サイズ制限を適切に設定（通常登録と同等）
                top_level.setMinimumSize(1400, 800)
                top_level.setMaximumSize(screen_width, screen_height)
                
                # 現在のサイズを確認
                current_size = top_level.size()
                current_width = current_size.width()
                current_height = current_size.height()
                
                # ウィンドウサイズを調整
                if (current_width != target_width or current_height != target_height):
                    print(f"[DEBUG] リサイズ実行中: {current_width}x{current_height} → {target_width}x{target_height}")
                    top_level.resize(target_width, target_height)
                    
                    # 画面中央に配置
                    x = max(0, (screen_width - target_width) // 2)
                    y = max(0, (screen_height - target_height) // 2)
                    top_level.move(x, y)
                    
                    # UI更新を強制
                    top_level.update()
                    QApplication.processEvents()
                    
                    # 結果確認
                    new_size = top_level.size()
                    print(f"[INFO] ウィンドウサイズ調整完了: 結果={new_size.width()}x{new_size.height()}")
                else:
                    print(f"[INFO] ウィンドウサイズは既に適切です: {current_width}x{current_height}")
                
                # フレキシブルなサイズ設定（通常登録と同等）
                top_level.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                
                # ウィンドウタイトルを更新して一括登録モードを明示
                if "一括登録" not in top_level.windowTitle():
                    original_title = top_level.windowTitle()
                    top_level.setWindowTitle(f"{original_title} - 一括登録モード")
                
        except Exception as e:
            print(f"[WARNING] ウィンドウサイズ調整に失敗: {e}")
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
            print(f"[INFO] 固定幅制限を解除しました - リサイズ可能になりました")
        except Exception as e:
            print(f"[WARNING] 固定幅クリアに失敗: {e}")

    def _on_capacity_enable_toggled(self, enabled: bool):
        """容量制限有効/無効の切り替え"""
        try:
            self.capacity_spinbox.setEnabled(enabled)
            self.capacity_unit_combo.setEnabled(enabled)
            
            if enabled:
                print("[INFO] 容量制限が有効になりました")
            else:
                print("[INFO] 容量制限が無効になりました")
                
        except Exception as e:
            print(f"[ERROR] 容量制限切り替えエラー: {e}")
    
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
                
            print(f"[INFO] 容量制限単位を {unit} に変更")
            
        except Exception as e:
            print(f"[ERROR] 容量制限単位変更エラー: {e}")
    
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
            print(f"[ERROR] 容量制限取得エラー: {e}")
            return None
    
    def _apply_capacity_limit_to_filesets(self, file_sets: List[FileSet], capacity_limit: int) -> List[FileSet]:
        """容量制限をファイルセットに適用して分割"""
        try:
            print(f"[INFO] 容量制限適用開始: {self._format_file_size(capacity_limit)} 以下に分割")
            
            # まずZIP階層競合を解決
            file_sets = self._resolve_zip_hierarchy_conflicts(file_sets)
            
            new_file_sets = []
            
            for file_set in file_sets:
                # ファイルセットの総サイズを計算
                total_size = self._calculate_fileset_size(file_set)
                print(f"[DEBUG] ファイルセット '{file_set.name}': {self._format_file_size(total_size)}")
                
                if total_size <= capacity_limit:
                    # 制限内なのでそのまま追加
                    new_file_sets.append(file_set)
                else:
                    # 分割が必要
                    split_sets = self._split_fileset_by_capacity(file_set, capacity_limit)
                    new_file_sets.extend(split_sets)
            
            print(f"[INFO] 容量制限適用完了: {len(file_sets)} → {len(new_file_sets)} ファイルセット")
            
            # 分割後のファイルセットをマネージャーに設定
            self.file_set_manager.file_sets = new_file_sets
            
            return new_file_sets
            
        except Exception as e:
            print(f"[ERROR] 容量制限適用エラー: {e}")
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
            print(f"[ERROR] ファイルセットサイズ計算エラー: {e}")
            return 0
    
    def _split_fileset_by_capacity(self, file_set: FileSet, capacity_limit: int) -> List[FileSet]:
        """ファイルセットを容量制限で分割"""
        try:
            print(f"[INFO] ファイルセット '{file_set.name}' を分割中...")
            
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
                    
                    print(f"[WARNING] 大容量ファイル ({self._format_file_size(size)}) を独立セットに分離: {item.name}")
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
            
            print(f"[INFO] 分割完了: {len(split_sets)} 個のファイルセットに分割")
            
            return split_sets
            
        except Exception as e:
            print(f"[ERROR] ファイルセット分割エラー: {e}")
            import traceback
            traceback.print_exc()
            return [file_set]  # エラー時は元のファイルセットを返す
    
    def _resolve_zip_hierarchy_conflicts(self, file_sets: List[FileSet]) -> List[FileSet]:
        """ZIP階層の競合を解決"""
        try:
            print(f"[INFO] ZIP階層競合チェック開始: {len(file_sets)} ファイルセット")
            
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
                    print(f"[INFO] ファイルセット '{file_set.name}': ZIP競合により {len(items_removed)} 個のアイテムを除外")
            
            # 空のファイルセットを除去
            non_empty_sets = [fs for fs in file_sets if fs.items]
            
            if conflicts_resolved > 0:
                print(f"[INFO] ZIP階層競合解決完了: {conflicts_resolved} 個のアイテムを調整, "
                      f"{len(file_sets) - len(non_empty_sets)} 個の空セットを除去")
            
            return non_empty_sets
            
        except Exception as e:
            print(f"[ERROR] ZIP階層競合解決エラー: {e}")
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
                    print(f"[INFO] データセット選択確定: {current_text}")
                    
        except Exception as e:
            print(f"[WARNING] データセットフォーカス外れ処理エラー: {e}")
    
    def on_dataset_changed(self, index):
        """データセット選択変更時の処理"""
        try:
            print(f"[DEBUG] データセット選択変更: index={index}")
            print(f"[DEBUG] コンボボックス状態: currentText='{self.dataset_combo.currentText()}', totalItems={self.dataset_combo.count()}")
            
            # 選択されたデータセット情報を取得
            dataset_id = None
            dataset_data = None
            
            # index < 0 は選択なし状態のみ除外
            if index < 0:
                print("[DEBUG] データセット未選択（index < 0）")
                self.clear_dynamic_fields()
                return
            
            # currentDataから取得
            try:
                current_data = self.dataset_combo.currentData()
                print(f"[DEBUG] currentDataから取得したデータ: {type(current_data)}")
                
                if current_data:
                    # 辞書オブジェクトの場合、それがデータセット情報そのもの
                    if isinstance(current_data, dict) and 'id' in current_data:
                        dataset_id = current_data['id']
                        dataset_data = current_data
                        print(f"[DEBUG] 辞書からデータセット情報を取得: ID={dataset_id}")
                    # 文字列の場合、IDとして扱ってself.datasetsから検索
                    elif isinstance(current_data, str):
                        dataset_id = current_data
                        for dataset in self.datasets:
                            if dataset.get('id') == dataset_id:
                                dataset_data = dataset
                                print(f"[DEBUG] IDからデータセット情報を特定: {dataset.get('attributes', {}).get('title', 'タイトルなし')}")
                                break
                    
                    if not dataset_data:
                        print(f"[WARNING] データセットID {dataset_id} に対応するデータセット情報が見つかりません")
                        return
            except Exception as e:
                print(f"[ERROR] データセット取得に失敗: {e}")
                return
            
            if dataset_id and dataset_data:
                print(f"[INFO] データセット選択確定: {dataset_id}")
                
                # サンプル一覧を更新
                self.update_sample_list(dataset_id)
                
                # 実験ID一覧を更新
                self.update_experiment_list(dataset_id)
                
                # インボイススキーマフォームを更新
                print(f"[DEBUG] update_schema_form呼び出し前: dataset_data={dataset_data}")
                self.update_schema_form(dataset_data)
                print(f"[DEBUG] update_schema_form呼び出し後")
                
                # 選択された旨を表示
                QTimer.singleShot(500, lambda: print(f"[INFO] データセット反映完了: {dataset_id}"))
                
                # 選択されたファイルセットに設定を自動適用
                self.auto_apply_settings_to_selected()
            else:
                # データセット未選択時はクリア
                print("[DEBUG] データセット未選択 - フィールドをクリア")
                self.clear_dynamic_fields()
                
        except Exception as e:
            print(f"[WARNING] データセット変更処理エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def on_sample_mode_changed(self, mode):
        """試料選択変更時の処理（統合フォーム対応）"""
        try:
            print(f"[DEBUG] 試料選択変更: {mode}")
            
            if mode == "新規作成":
                # 新規作成時は入力フィールドを有効化
                self.sample_name_edit.setEnabled(True)
                self.sample_description_edit.setEnabled(True)
                self.sample_composition_edit.setEnabled(True)
                # 入力フィールドをクリア
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                print("[DEBUG] 新規作成モード: 入力フィールドを有効化")
                
            
            elif mode == "既存試料を選択してください":
                # 既存試料選択時は入力フィールドを無効化
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                
                # 現在選択されているデータセットの試料リストを更新
                selected_dataset_id = self.get_selected_dataset_id()
                if selected_dataset_id:
                    print(f"[DEBUG] 既存試料選択モード: 試料リスト更新開始")
                    self.update_sample_list(selected_dataset_id)
                else:
                    print("[WARNING] 既存試料選択モード: データセットが選択されていません")
                    
            elif mode == "前回と同じ":
                # 前回と同じ時は入力フィールドを無効化
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                
                # 前のファイルセットから試料情報を取得
                self._load_previous_sample_info()
                print("[DEBUG] 前回と同じモード: 前回の試料情報を読み込み")
                
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
                    print(f"[DEBUG] 既存試料選択: {current_data.get('name', '')}")
                
        except Exception as e:
            print(f"[WARNING] 試料選択変更処理エラー: {e}")
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
            
            print(f"[DEBUG] 前回の試料情報を読み込み: {prev_sample_name}")
            
        except Exception as e:
            print(f"[WARNING] 前回試料情報読み込みエラー: {e}")
            self.sample_name_edit.setText("前回の情報読み込みに失敗しました")
                
        except Exception as e:
            print(f"[WARNING] 試料モード変更処理エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def on_sample_selection_changed(self, index):
        """試料選択インデックス変更時の処理（既存試料選択用）"""
        try:
            current_text = self.sample_mode_combo.currentText()
            current_data = self.sample_mode_combo.currentData()
            
            print(f"[DEBUG] 試料選択インデックス変更: index={index}, text='{current_text}'")
            
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
                
                print(f"[INFO] 既存試料情報を表示: {sample_name}")
            
        except Exception as e:
            print(f"[WARNING] 試料選択インデックス変更エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def update_sample_list(self, dataset_id):
        """選択されたデータセットのサンプル一覧を更新（統合コンボボックス対応）"""
        try:
            print(f"[DEBUG] サンプル一覧更新開始: dataset_id={dataset_id}")
            
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
                        print(f"[DEBUG] 対象データセット取得成功: {target_dataset.get('attributes', {}).get('name', '')}")
                        
                        # データセットに紐づくグループIDを取得（通常登録と同じ方法）
                        group_id = None
                        
                        try:
                            # 方法1: 通常登録と同じようにdatasetファイルからグループIDを取得
                            dataset_id = target_dataset.get('id', '')
                            if dataset_id:
                                import os
                                from config.common import get_dynamic_file_path
                                
                                dataset_json_path = get_dynamic_file_path(f'output/rde/data/datasets/{dataset_id}.json')
                                print(f"[DEBUG] データセットファイル確認: {dataset_json_path}")
                                
                                if os.path.exists(dataset_json_path):
                                    import json
                                    with open(dataset_json_path, 'r', encoding='utf-8') as f:
                                        dataset_data = json.load(f)
                                        relationships = dataset_data.get("data", {}).get('relationships', {})
                                        group = relationships.get('group', {}).get('data', {})
                                        group_id = group.get('id', '')
                                        print(f"[DEBUG] データセットファイルからグループID取得: {group_id}")
                                else:
                                    print(f"[DEBUG] データセットファイルが存在しません: {dataset_json_path}")
                            
                            # 方法2: フォールバック - APIレスポンスから直接取得
                            if not group_id:
                                relationships = target_dataset.get('relationships', {})
                                group_data = relationships.get('group', {}).get('data', {})
                                if not group_data:
                                    group_data = relationships.get('subgroup', {}).get('data', {})
                                
                                if group_data and group_data.get('id'):
                                    group_id = group_data.get('id')
                                    print(f"[DEBUG] APIレスポンスからグループID取得: {group_id}")
                            
                            if group_id:
                                print(f"[DEBUG] 最終決定グループID: {group_id}")
                            else:
                                print("[WARNING] 全ての方法でグループID取得失敗")
                                
                        except Exception as e:
                            print(f"[WARNING] グループID取得エラー: {e}")
                            import traceback
                            traceback.print_exc()
                        
                        if group_id:
                            print(f"[DEBUG] 最終決定グループID: {group_id}")
                            
                            # 通常登録のsample_loaderを使用
                            from classes.data_entry.util.sample_loader import load_existing_samples, format_sample_display_name
                            
                            existing_samples = load_existing_samples(group_id)
                            print(f"[DEBUG] 既存試料データ取得: {len(existing_samples)}件")
                            
                            if existing_samples:
                                for sample in existing_samples:
                                    display_name = format_sample_display_name(sample)
                                    self.sample_mode_combo.addItem(display_name, sample)
                                    print(f"[DEBUG] 既存試料追加: {display_name}")
                                
                                print(f"[INFO] 既存試料を統合コンボボックスに追加完了: {len(existing_samples)}件")
                            else:
                                print("[DEBUG] 既存試料データなし")
                        else:
                            print("[WARNING] グループID/サブグループIDが取得できません")
                    else:
                        print(f"[WARNING] 対象データセットが見つかりません: {dataset_id}")
                    
                except Exception as e:
                    print(f"[WARNING] サンプル情報取得失敗: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("[DEBUG] データセットIDが無効")
            
            print(f"[DEBUG] サンプル一覧更新完了: {self.sample_mode_combo.count()}個の選択肢")
            
        except Exception as e:
            print(f"[WARNING] サンプル一覧更新エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def update_experiment_list(self, dataset_id):
        """選択されたデータセットの実験ID一覧を更新（入力フィールドなので何もしない）"""
        try:
            print(f"[DEBUG] 実験ID一覧更新開始: dataset_id={dataset_id}")
            
            # 実験IDは入力フィールドになったため、リスト更新は不要
            print(f"[DEBUG] 実験ID一覧更新完了: 入力フィールドのため処理なし")
            
        except Exception as e:
            print(f"[WARNING] 実験ID一覧更新エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def update_schema_form(self, dataset_data, force_clear=True):
        """インボイススキーマに基づく固有情報フォームを更新（通常登録と同等機能）"""
        try:
            print(f"[DEBUG] スキーマフォーム更新開始: {dataset_data}")
            
            # フォーム重複を防ぐため、常に既存フォームをクリア
            # 復元モードでも既存フォームが存在すれば必ずクリアする
            if force_clear:
                print(f"[DEBUG] 既存フォームをクリア中...")
                self.clear_schema_form()
            else:
                # 復元モードでも重複を防ぐため、既存フォームが存在すればクリアする
                if hasattr(self, 'invoice_schema_form') and self.invoice_schema_form is not None:
                    print(f"[DEBUG] 復元モードですが既存フォームをクリア中（重複防止）...")
                    self.clear_schema_form()
                else:
                    print(f"[DEBUG] 復元モード：既存フォームなし、クリアをスキップ")

            # データセットのスキーマ情報を取得
            dataset_id = dataset_data.get('id', '')
            attributes = dataset_data.get('attributes', {})
            dataset_name = attributes.get('name', '')
            relationships = dataset_data.get('relationships', {})

            if dataset_id:
                print(f"[INFO] スキーマフォーム生成: {dataset_name} ({dataset_id})")
                try:
                    # 通常登録と同じ方法でテンプレートIDを取得
                    template_id = ''
                    template = relationships.get('template', {}).get('data', {})
                    if isinstance(template, dict):
                        template_id = template.get('id', '')
                    print(f"[DEBUG] テンプレートID: {template_id}")
                    if template_id:
                        # 通常登録と同じパスでinvoiceSchemaを確認
                        from config.common import get_dynamic_file_path
                        from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
                        
                        invoice_schema_path = get_dynamic_file_path(f'output/rde/data/invoiceSchemas/{template_id}.json')
                        
                        print(f"[DEBUG] invoiceSchemaファイル確認: {invoice_schema_path}")
                        
                        import os
                        if os.path.exists(invoice_schema_path):
                            print(f"[INFO] invoiceSchemaファイル発見: {invoice_schema_path}")
                            
                            # フォーム生成時に適切な親ウィジェットを指定（スクロール領域内に配置）
                            schema_form = create_schema_form_from_path(invoice_schema_path, self.scroll_widget)
                            
                            if schema_form:
                                print("[INFO] インボイススキーマフォーム生成成功")
                                
                                # フォームの親ウィジェットを明示的に設定
                                schema_form.setParent(self.scroll_widget)
                                
                                # 独立ダイアログ表示を完全に防ぐ
                                schema_form.setWindowFlags(Qt.Widget)
                                schema_form.setWindowModality(Qt.NonModal)
                                schema_form.setAttribute(Qt.WA_DeleteOnClose, False)
                                
                                # 表示関連メソッドを抑制
                                schema_form.setVisible(False)  # いったん非表示
                                
                                print(f"[DEBUG] フォーム親ウィジェット設定完了: {type(self.scroll_widget)}")
                                print(f"[DEBUG] フォームフラグ設定: {schema_form.windowFlags()}")
                                print(f"[DEBUG] フォーム可視性制御: visible={schema_form.isVisible()}")
                                print(f"[DEBUG] scroll_widget object id: {id(self.scroll_widget)}")
                                print(f"[DEBUG] schema_form object id: {id(schema_form)}")
                                
                                # レイアウト重複確認
                                widget_count_before = self.schema_form_layout.count()
                                print(f"[DEBUG] フォーム追加前のレイアウト項目数: {widget_count_before}")
                                
                                # プレースホルダーを非表示
                                self.schema_placeholder_label.hide()
                                
                                # 動的生成フォームを追加
                                self.schema_form_layout.addWidget(schema_form)
                                self.schema_form = schema_form  # 保存（後で値取得で使用）
                                self.invoice_schema_form = schema_form  # 互換性のため（save_fileset_configで使用）
                                
                                # レイアウト追加後に表示制御
                                schema_form.setVisible(True)  # レイアウト内でのみ表示
                                
                                widget_count_after = self.schema_form_layout.count()
                                print(f"[DEBUG] フォーム追加後のレイアウト項目数: {widget_count_after}")
                                print(f"[DEBUG] レイアウト追加後の可視性: {schema_form.isVisible()}")
                                print(f"[DEBUG] レイアウト追加後の親: {type(schema_form.parent())}")
                                
                                print(f"[DEBUG] invoice_schema_form 設定完了: {type(schema_form)}")
                                print("[INFO] インボイススキーマフォーム表示完了")
                            else:
                                print("[WARNING] スキーマフォーム生成失敗")
                                # フォーム生成失敗時のみ空フォームを作成
                                self._create_empty_schema_form()
                                self.schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマフォーム生成に失敗しました")
                                self.schema_placeholder_label.show()
                        else:
                            print(f"[INFO] invoiceSchemaファイル未発見: {invoice_schema_path}")
                            # インボイススキーマファイルがない場合のみ空フォームを作成
                            self._create_empty_schema_form()
                            self.schema_placeholder_label.setText(f"データセット '{dataset_name}' にはカスタム固有情報がありません")
                            self.schema_placeholder_label.show()
                    else:
                        print("[DEBUG] テンプレートIDが無効")
                        # テンプレートIDがない場合でも空フォームを作成
                        self._create_empty_schema_form()
                        self.schema_placeholder_label.setText(f"データセット '{dataset_name}' にテンプレートIDがありません")
                        self.schema_placeholder_label.show()
                    
                except Exception as e:
                    print(f"[WARNING] スキーマ処理失敗: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # エラー時も空フォームを作成
                    self._create_empty_schema_form()
                    self.schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマ処理でエラーが発生しました")
                    self.schema_placeholder_label.show()
            else:
                print("[DEBUG] データセットIDが無効")
                # データセットIDがない場合でも空フォームを作成
                self._create_empty_schema_form()
                self.schema_placeholder_label.setText("データセットを選択してください")
                self.schema_placeholder_label.show()
            
            print("[DEBUG] スキーマフォーム更新完了")
            
        except Exception as e:
            print(f"[WARNING] スキーマフォーム更新エラー: {e}")
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
            self.sample_id_combo.clear()
            self.experiment_id_combo.clear()
            self.clear_schema_form()
            
        except Exception as e:
            print(f"[WARNING] 動的フィールドクリアエラー: {e}")
    
    def clear_schema_form(self):
        """スキーマフォームをクリア"""
        try:
            widget_count_before = self.schema_form_layout.count()
            print(f"[DEBUG] フォームクリア開始：現在のレイアウト項目数={widget_count_before}")
            
            # 現在のフォーム参照状況をログ出力
            print(f"[DEBUG] 現在のフォーム参照: schema_form={getattr(self, 'schema_form', None)}, invoice_schema_form={getattr(self, 'invoice_schema_form', None)}")
            
            # 動的に生成されたフォーム要素を削除
            removed_count = 0
            for i in reversed(range(self.schema_form_layout.count())):
                child = self.schema_form_layout.itemAt(i).widget()
                if child and child != self.schema_placeholder_label:
                    print(f"[DEBUG] ウィジェットを削除: {type(child).__name__}")
                    child.setParent(None)
                    removed_count += 1
            
            print(f"[DEBUG] 削除されたウィジェット数: {removed_count}")
            
            # フォーム参照をクリア
            self.schema_form = None
            self.invoice_schema_form = None
            
            print(f"[DEBUG] フォーム参照クリア完了: schema_form={self.schema_form}, invoice_schema_form={self.invoice_schema_form}")
            
            # プレースホルダーを表示
            self.schema_placeholder_label.setText("データセット選択後に固有情報入力フォームが表示されます")
            self.schema_placeholder_label.show()
            
        except Exception as e:
            print(f"[WARNING] スキーマフォームクリアエラー: {e}")
    
    def _create_empty_schema_form(self):
        """空のインボイススキーマフォームを作成（参照確保用）"""
        try:
            from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QLabel
            
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
            
            print(f"[DEBUG] 空のinvoice_schema_form作成完了: {type(empty_form)}")
            
        except Exception as e:
            print(f"[ERROR] 空フォーム作成エラー: {e}")
            # フォールバック: 最低限のオブジェクトを作成
            class EmptyForm:
                def get_form_data(self):
                    return {}
                def set_form_data(self, data):
                    pass
                def clear_form(self):
                    pass
            
            self.invoice_schema_form = EmptyForm()
            print(f"[DEBUG] フォールバック空フォーム作成: {type(self.invoice_schema_form)}")

    def apply_to_all_filesets(self):
        """現在の設定を全てのファイルセットに適用"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            QMessageBox.information(self, "情報", "適用対象のファイルセットがありません。")
            return
        
        reply = QMessageBox.question(
            self, "確認",
            f"現在の設定を全ての{len(self.file_set_manager.file_sets)}個のファイルセットに適用しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # 現在の設定を取得
                settings = self.get_current_settings()
                applied_count = 0
                for fileset in self.file_set_manager.file_sets:
                    self._apply_settings_to_fileset(fileset, settings)
                    applied_count += 1
                
                QMessageBox.information(self, "完了", f"{applied_count}個のファイルセットに設定を適用しました。")
                self.refresh_fileset_display()
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
    
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
    
    def refresh_fileset_display(self):
        """ファイルセット表示を更新"""
        print(f"[DEBUG] refresh_fileset_display (2nd method): 呼び出された")
        try:
            print(f"[DEBUG] refresh_fileset_display (2nd method): fileset_table存在確認")
            if hasattr(self, 'fileset_table'):
                print(f"[DEBUG] refresh_fileset_display (2nd method): fileset_table.refresh_data() 呼び出し")
                self.fileset_table.refresh_data()
                print(f"[DEBUG] refresh_fileset_display (2nd method): fileset_table.refresh_data() 完了")
            else:
                print(f"[DEBUG] refresh_fileset_display (2nd method): fileset_table 未存在")
            
            # ターゲットファイルセットコンボボックスを更新
            if hasattr(self, 'target_fileset_combo'):
                print(f"[DEBUG] refresh_fileset_display (2nd method): target_fileset_combo 更新開始")
                self.update_target_fileset_combo()
                print(f"[DEBUG] refresh_fileset_display (2nd method): target_fileset_combo 更新完了")
        except Exception as e:
            print(f"[ERROR] refresh_fileset_display (2nd method): {e}")
            import traceback
            traceback.print_exc()
    
    def update_target_fileset_combo(self):
        """ターゲットファイルセットコンボボックスを更新"""
        if not hasattr(self, 'target_fileset_combo'):
            return
        
        current_text = self.target_fileset_combo.currentText()
        self.target_fileset_combo.clear()
        
        if self.file_set_manager and self.file_set_manager.file_sets:
            for fileset in self.file_set_manager.file_sets:
                self.target_fileset_combo.addItem(fileset.name)
        
        # 以前の選択を復元
        if current_text:
            index = self.target_fileset_combo.findText(current_text)
            if index >= 0:
                self.target_fileset_combo.setCurrentIndex(index)


# QInputDialogのインポートを追加
from PyQt5.QtWidgets import QInputDialog


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
        self.dialog_schema_placeholder_label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
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
            print("[DEBUG] ダイアログ: データセット選択イベント接続完了")
        
        # 試料モード・試料選択イベント接続
        self.sample_mode_combo.currentTextChanged.connect(self.on_dialog_sample_mode_changed)
        self.sample_id_combo.currentIndexChanged.connect(self.on_dialog_sample_selected)
        print("[DEBUG] ダイアログ: 試料関連イベント接続完了")
        
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
                    print(f"[INFO] データセット選択確定: {current_text}")
                    
        except Exception as e:
            print(f"[WARNING] データセットフォーカス外れ処理エラー: {e}")
    
    def on_dialog_dataset_changed(self, index):
        """ダイアログでのデータセット選択変更処理"""
        try:
            print(f"[DEBUG] ダイアログ: データセット選択変更 index={index}")
            
            if index < 0:
                print("[DEBUG] ダイアログ: 無効なインデックス")
                return
            
            # 選択されたデータセット情報を取得
            current_data = self.dataset_combo.currentData()
            dataset_id = None
            
            if current_data:
                if isinstance(current_data, dict) and 'id' in current_data:
                    dataset_id = current_data['id']
                    print(f"[DEBUG] ダイアログ: 辞書からデータセットID取得: {dataset_id}")
                elif isinstance(current_data, str):
                    dataset_id = current_data
                    print(f"[DEBUG] ダイアログ: 文字列データセットID: {dataset_id}")
            
            if dataset_id:
                print(f"[INFO] ダイアログ: データセット選択確定: {dataset_id}")
                
                # 試料リストを更新（メインウィンドウと同じ処理）
                self.update_dialog_sample_list(dataset_id)
                
                # スキーマフォームを表示（メインウィンドウと同じ処理）
                self.update_dialog_schema_form()
                
            else:
                print("[DEBUG] ダイアログ: データセットIDなし")
                
        except Exception as e:
            print(f"[WARNING] ダイアログ: データセット選択変更エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def update_dialog_sample_list(self, dataset_id):
        """ダイアログ用のサンプル一覧更新"""
        try:
            print(f"[DEBUG] ダイアログ: サンプル一覧更新開始: dataset_id={dataset_id}")
            
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
                        print(f"[DEBUG] ダイアログ: 対象データセット取得成功: {target_dataset.get('attributes', {}).get('name', '')}")
                        
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
                                print(f"[DEBUG] ダイアログ: データセットファイル確認: {dataset_json_path}")
                                
                                if os.path.exists(dataset_json_path):
                                    import json
                                    with open(dataset_json_path, 'r', encoding='utf-8') as f:
                                        dataset_data = json.load(f)
                                        relationships = dataset_data.get("data", {}).get('relationships', {})
                                        group = relationships.get('group', {}).get('data', {})
                                        group_id = group.get('id', '')
                                        print(f"[DEBUG] ダイアログ: データセットファイルからグループID取得: {group_id}")
                                else:
                                    print(f"[DEBUG] ダイアログ: データセットファイルが存在しません: {dataset_json_path}")
                            
                            # 方法2: フォールバック - APIレスポンスから直接取得
                            if not group_id:
                                relationships = target_dataset.get('relationships', {})
                                group_data = relationships.get('group', {}).get('data', {})
                                if not group_data:
                                    group_data = relationships.get('subgroup', {}).get('data', {})
                                
                                if group_data and group_data.get('id'):
                                    group_id = group_data.get('id')
                                    print(f"[DEBUG] ダイアログ: APIレスポンスからグループID取得: {group_id}")
                            
                        except Exception as e:
                            print(f"[WARNING] ダイアログ: グループID取得エラー: {e}")
                            import traceback
                            traceback.print_exc()
                        
                        if group_id:
                            print(f"[DEBUG] ダイアログ: 最終決定グループID: {group_id}")
                            
                            # 通常登録のsample_loaderを使用
                            from classes.data_entry.util.sample_loader import load_existing_samples, format_sample_display_name
                            
                            existing_samples = load_existing_samples(group_id)
                            print(f"[DEBUG] ダイアログ: 既存試料データ取得: {len(existing_samples)}件")
                            
                            if existing_samples:
                                for sample in existing_samples:
                                    display_name = format_sample_display_name(sample)
                                    self.sample_id_combo.addItem(display_name, sample)
                                    print(f"[DEBUG] ダイアログ: 既存試料追加: {display_name}")
                                
                                print(f"[INFO] ダイアログ: 既存試料をコンボボックスに追加完了: {len(existing_samples)}件")
                            else:
                                print("[DEBUG] ダイアログ: 既存試料データなし")
                                self.sample_id_combo.addItem("（既存試料なし）", None)
                        else:
                            print("[WARNING] ダイアログ: グループID/サブグループIDが取得できません")
                            self.sample_id_combo.addItem("（グループ情報取得失敗）", None)
                    else:
                        print(f"[WARNING] ダイアログ: 対象データセットが見つかりません: {dataset_id}")
                    
                except Exception as e:
                    print(f"[WARNING] ダイアログ: サンプル情報取得失敗: {e}")
                    import traceback
                    traceback.print_exc()
                    self.sample_id_combo.addItem("（サンプル取得失敗）", None)
            else:
                print("[DEBUG] ダイアログ: データセットIDが無効")
            
            print(f"[DEBUG] ダイアログ: サンプル一覧更新完了: {self.sample_id_combo.count()}個の選択肢")
            
        except Exception as e:
            print(f"[WARNING] ダイアログ: サンプル一覧更新エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def on_dialog_sample_mode_changed(self, mode):
        """ダイアログ: 試料モード変更時の処理"""
        try:
            print(f"[DEBUG] ダイアログ: 試料モード変更: {mode}")
            
            if mode == "既存試料を使用":
                # 既存試料コンボボックスを有効化し、試料リストを更新
                self.sample_id_combo.setEnabled(True)
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                print("[DEBUG] ダイアログ: 既存試料使用モード")
                
                # 現在選択されているデータセットの試料リストを再取得
                current_data = self.dataset_combo.currentData()
                dataset_id = None
                if current_data and isinstance(current_data, dict) and 'id' in current_data:
                    dataset_id = current_data['id']
                elif isinstance(current_data, str):
                    dataset_id = current_data
                
                if dataset_id:
                    print(f"[DEBUG] ダイアログ: 既存試料使用モード - 試料リスト更新")
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
                print("[DEBUG] ダイアログ: 新規作成モード")
                
        except Exception as e:
            print(f"[WARNING] ダイアログ: 試料モード変更エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def on_dialog_sample_selected(self, index):
        """ダイアログ: 既存試料選択時の処理"""
        try:
            print(f"[DEBUG] ダイアログ: 既存試料選択: index={index}")
            
            if index <= 0:  # 最初のアイテム（プレースホルダー）の場合
                print("[DEBUG] ダイアログ: プレースホルダー選択 - フィールドをクリア")
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                return
            
            # 選択された試料データを取得
            current_data = self.sample_id_combo.currentData()
            if current_data and isinstance(current_data, dict):
                print(f"[DEBUG] ダイアログ: 既存試料データ取得成功: {current_data.get('name', '')}")
                
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
                
                print(f"[INFO] ダイアログ: 既存試料情報を表示: {sample_name}")
            else:
                print("[WARNING] ダイアログ: 既存試料データが取得できません")
                
        except Exception as e:
            print(f"[WARNING] ダイアログ: 既存試料選択エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def update_dialog_schema_form(self):
        """ダイアログ用スキーマフォーム更新"""
        try:
            print("[DEBUG] ダイアログ: スキーマフォーム更新開始")
            # 既存のスキーマフォームを完全クリア（多重表示防止）
            if hasattr(self, 'dialog_schema_form_layout'):
                for i in reversed(range(self.dialog_schema_form_layout.count())):
                    child = self.dialog_schema_form_layout.itemAt(i).widget()
                    if child and child != getattr(self, 'dialog_schema_placeholder_label', None):
                        child.setParent(None)
            self.dialog_schema_form = None
            print("[DEBUG] ダイアログ: 既存スキーマフォーム完全クリア")

            # プレースホルダーを非表示
            if hasattr(self, 'dialog_schema_placeholder_label'):
                self.dialog_schema_placeholder_label.hide()

            # 現在選択されているデータセット情報を取得
            current_data = self.dataset_combo.currentData()

            if not current_data or not isinstance(current_data, dict):
                print("[DEBUG] ダイアログ: データセット情報なし")
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
                print(f"[INFO] ダイアログ: スキーマフォーム生成: {dataset_name} ({dataset_id})")
                
                try:
                    # 通常登録と同じ方法でテンプレートIDを取得
                    template_id = ''
                    template = relationships.get('template', {}).get('data', {})
                    if isinstance(template, dict):
                        template_id = template.get('id', '')
                    
                    print(f"[DEBUG] ダイアログ: テンプレートID: {template_id}")
                    
                    if template_id:
                        # 通常登録と同じパスでinvoiceSchemaを確認
                        from config.common import get_dynamic_file_path
                        from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
                        
                        invoice_schema_path = get_dynamic_file_path(f'output/rde/data/invoiceSchemas/{template_id}.json')
                        
                        print(f"[DEBUG] ダイアログ: invoiceSchemaファイル確認: {invoice_schema_path}")
                        
                        import os
                        if os.path.exists(invoice_schema_path):
                            print(f"[INFO] ダイアログ: invoiceSchemaファイル発見: {invoice_schema_path}")
                            
                            # 通常登録と同じ方法でフォーム生成
                            schema_form = create_schema_form_from_path(invoice_schema_path, self)
                            
                            if schema_form:
                                print("[INFO] ダイアログ: インボイススキーマフォーム生成成功")
                                
                                # 動的生成フォームを追加
                                self.dialog_schema_form_layout.addWidget(schema_form)
                                self.dialog_schema_form = schema_form  # 保存（後で値取得で使用）
                                
                                print("[INFO] ダイアログ: インボイススキーマフォーム表示完了")
                            else:
                                print("[WARNING] ダイアログ: スキーマフォーム生成失敗")
                                if hasattr(self, 'dialog_schema_placeholder_label'):
                                    self.dialog_schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマフォーム生成に失敗しました")
                                    self.dialog_schema_placeholder_label.show()
                        else:
                            print(f"[WARNING] ダイアログ: invoiceSchemaファイルが存在しません: {invoice_schema_path}")
                            if hasattr(self, 'dialog_schema_placeholder_label'):
                                self.dialog_schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマファイルが見つかりません")
                                self.dialog_schema_placeholder_label.show()
                    else:
                        print("[WARNING] ダイアログ: テンプレートIDなし")
                        if hasattr(self, 'dialog_schema_placeholder_label'):
                            self.dialog_schema_placeholder_label.setText(f"データセット '{dataset_name}' にテンプレート情報がありません")
                            self.dialog_schema_placeholder_label.show()
                        
                except Exception as e:
                    print(f"[WARNING] ダイアログ: スキーマフォーム処理エラー: {e}")
                    import traceback
                    traceback.print_exc()
                    if hasattr(self, 'dialog_schema_placeholder_label'):
                        self.dialog_schema_placeholder_label.setText(f"スキーマフォーム処理でエラーが発生しました: {str(e)}")
                        self.dialog_schema_placeholder_label.show()
                        
        except Exception as e:
            print(f"[WARNING] ダイアログ: スキーマフォーム更新エラー: {e}")
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
                print(f"[DEBUG] ダイアログ: データセットID={self.fileset.dataset_id}を設定中")
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
                        print(f"[DEBUG] ダイアログ: データセットコンボボックス インデックス{i}を選択")
                        self.dataset_combo.setCurrentIndex(i)
                        found = True
                        break
                if not found:
                    print(f"[WARNING] ダイアログ: データセットID {self.fileset.dataset_id} がコンボボックスに見つかりません")
                    self.dataset_combo.setCurrentIndex(-1)
            else:
                print("[DEBUG] ダイアログ: データセット未設定")
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
            print(f"[WARNING] ファイルセットデータ読み込みエラー: {e}")
    
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
            print(f"[ERROR] accept_changes: {e}")


# BatchRegisterWidget に一時フォルダ管理メソッドを追加
def _prepare_temp_folders(self):
    """一時フォルダ準備（フラット化・ZIP化対応）"""
    try:
        print("[INFO] 一時フォルダ準備を開始")
        
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
                    
                    print(f"[INFO] ファイルセット '{file_set.name}' の一時フォルダを作成: {temp_dir}")
                    
                except Exception as e:
                    print(f"[ERROR] ファイルセット '{file_set.name}' の一時フォルダ作成エラー: {e}")
                    # エラーがあっても処理を続行
                    continue
        
        print("[INFO] 一時フォルダ準備完了")
        
    except Exception as e:
        print(f"[ERROR] 一時フォルダ準備処理エラー: {e}")
        raise

def cleanup_temp_folders_on_init(self):
    """初期化時に既存の一時フォルダをクリーンアップ（UUID対応版）"""
    try:
        print("[INFO] 既存一時フォルダのクリーンアップを開始")
        
        # 新しいUUID管理方式で全てクリーンアップ
        self.temp_folder_manager.cleanup_all_temp_folders()
        
        # 孤立したフォルダも削除（file_setsは初期化時は空なのですべて孤立扱い）
        orphaned_count = self.temp_folder_manager.cleanup_orphaned_temp_folders([])
        
        print(f"[INFO] 既存一時フォルダのクリーンアップ完了（孤立フォルダ {orphaned_count} 個削除）")
    except Exception as e:
        print(f"[WARNING] 一時フォルダクリーンアップエラー: {e}")

def auto_apply_settings_to_selected(self):
    """選択されたファイルセットに現在の設定を自動適用"""
    try:
        # ファイルセット復元処理中の場合は自動適用をスキップ
        if getattr(self, '_restoring_fileset', False):
            print("[DEBUG] ファイルセット復元中のため自動設定適用をスキップ")
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
                        print(f"[INFO] 設定をファイルセット '{target_name}' に自動適用しました")
                        # テーブル表示を更新
                        QTimer.singleShot(100, self.refresh_fileset_display)
    except Exception as e:
        print(f"[WARNING] 設定自動適用エラー: {e}")

    def show_data_tree_dialog(self, fileset: FileSet):
        """データツリー選択ダイアログを表示"""
        try:
            dialog = DataTreeDialog(fileset.items, self)
            if dialog.exec_() == QDialog.Accepted:
                # 選択されたファイルでファイルセットを更新
                selected_files = dialog.get_selected_files()
                if selected_files:
                    fileset.items = selected_files
                    self.refresh_fileset_display()
                    QMessageBox.information(self, "完了", 
                        f"ファイルセット '{fileset.name}' を更新しました。\n"
                        f"選択ファイル数: {len(selected_files)}個")
        except Exception as e:
            print(f"[ERROR] show_data_tree_dialog: {e}")
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
            print(f"[ERROR] _create_mapping_file: {e}")
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
