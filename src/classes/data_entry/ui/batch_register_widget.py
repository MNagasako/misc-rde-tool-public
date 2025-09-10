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
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QSpinBox,
    QFileDialog, QMessageBox, QMenu, QAction, QApplication, QFrame, QSizePolicy,
    QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush

from ..core.file_set_manager import (
    FileSetManager, FileSet, FileItem, FileType, PathOrganizeMethod
)
from ..core.batch_register_logic import BatchRegisterLogic, BatchRegisterResult
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
        self.setHeaderLabels(["名前", "タイプ", "サイズ", "含む"])
        self.setSelectionMode(QTreeWidget.ExtendedSelection)  # 複数選択可能
        self.setAlternatingRowColors(True)
        self.setStyleSheet(FILE_TREE_STYLE)
        
        # カラム幅設定
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 名前列は可変
        header.setSectionResizeMode(1, QHeaderView.Fixed)    # タイプ列は固定
        header.setSectionResizeMode(2, QHeaderView.Fixed)    # サイズ列は固定  
        header.setSectionResizeMode(3, QHeaderView.Fixed)    # 含む列は固定
        self.setColumnWidth(1, 80)   # タイプ
        self.setColumnWidth(2, 100)  # サイズ
        self.setColumnWidth(3, 80)   # 含む
        
        # コンテキストメニュー
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
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
            
            if file_item.file_type == FileType.FILE:
                tree_item.setText(2, self._format_size(file_item.size))
            else:
                tree_item.setText(2, f"{file_item.child_count} files")
            
            # 親に追加（チェックボックスを設定する前に）
            parent_item = dir_items.get(parent_path, self.invisibleRootItem())
            parent_item.addChild(tree_item)
            
            # チェックボックスをウィジェットとして追加
            checkbox = QCheckBox()
            checkbox.setChecked(not file_item.is_excluded)
            checkbox.stateChanged.connect(
                lambda state, item=tree_item, file_item=file_item: self.on_checkbox_changed(state, item, file_item)
            )
            self.checkbox_items[id(tree_item)] = checkbox
            self.setItemWidget(tree_item, 3, checkbox)  # 含む列にチェックボックスを配置
            
            # スタイル設定
            if file_item.is_excluded:
                tree_item.setForeground(0, QColor("#999999"))
                tree_item.setForeground(1, QColor("#999999"))
                tree_item.setForeground(2, QColor("#999999"))
            
            # マッピング保存
            self.file_items[id(tree_item)] = file_item
            
            # ディレクトリの場合は dir_items に追加
            if file_item.file_type == FileType.DIRECTORY:
                dir_items[file_item.relative_path] = tree_item
        
        # 展開
        self.expandAll()
    
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
            tree_item.setText(2, f"{dir_item.child_count} files")
            tree_item.setText(3, "除外" if dir_item.is_excluded else "含む")
            tree_item.setCheckState(0, Qt.Unchecked if dir_item.is_excluded else Qt.Checked)
            
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
        
        # 除外/含む切り替え
        if id(item) in self.file_items:
            file_item = self.file_items[id(item)]
            if file_item.is_excluded:
                action = QAction("含める", self)
                action.triggered.connect(lambda: self.toggle_exclude(item, False))
            else:
                action = QAction("除外する", self)
                action.triggered.connect(lambda: self.toggle_exclude(item, True))
            menu.addAction(action)
        
        menu.exec_(self.mapToGlobal(position))
    
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
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "ファイルセット名", "ファイル数", "サイズ", "整理方法", "データ名", "試料", "データセット", "操作"
        ])
        
        # スタイル設定
        self.setStyleSheet(FILESET_TABLE_STYLE)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        
        # カラム幅設定
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # ファイルセット名
        header.setSectionResizeMode(1, QHeaderView.Fixed)    # ファイル数
        header.setSectionResizeMode(2, QHeaderView.Fixed)    # サイズ
        header.setSectionResizeMode(3, QHeaderView.Fixed)    # 整理方法（各行でコンボボックス）
        header.setSectionResizeMode(4, QHeaderView.Fixed)    # データ名
        header.setSectionResizeMode(5, QHeaderView.Fixed)    # 試料
        header.setSectionResizeMode(6, QHeaderView.Fixed)    # データセット
        header.setSectionResizeMode(7, QHeaderView.Fixed)    # 操作
        
        self.setColumnWidth(1, 80)   # ファイル数
        self.setColumnWidth(2, 100)  # サイズ
        self.setColumnWidth(3, 100)  # 整理方法
        self.setColumnWidth(4, 120)  # データ名
        self.setColumnWidth(5, 120)  # 試料
        self.setColumnWidth(6, 150)  # データセット
        self.setColumnWidth(7, 80)   # 操作
        
        # 選択変更シグナル
        self.itemSelectionChanged.connect(self.on_selection_changed)
    
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
            
            # ファイルセット名
            name_item = QTableWidgetItem(file_set.name)
            self.setItem(row, 0, name_item)
            
            # ファイル数
            try:
                file_count = len(file_set.get_valid_items())
            except:
                file_count = 0
            count_item = QTableWidgetItem(str(file_count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 1, count_item)
            
            # サイズ
            try:
                total_size = file_set.get_total_size()
            except:
                total_size = 0
            size_item = QTableWidgetItem(self._format_size(total_size))
            size_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 2, size_item)
            
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
            self.setCellWidget(row, 3, method_combo)
            
            # データ名
            data_name = getattr(file_set, 'data_name', '') or "未設定"
            data_name_item = QTableWidgetItem(data_name)
            data_name_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 4, data_name_item)
            
            # 試料情報
            sample_info = self._get_sample_info_text(file_set)
            sample_item = QTableWidgetItem(sample_info)
            sample_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 5, sample_item)
            
            # データセット名
            dataset_name = self._get_dataset_name(file_set)
            dataset_item = QTableWidgetItem(dataset_name)
            dataset_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 6, dataset_item)
            
            # 削除ボタン
            delete_btn = QPushButton("削除")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
            """)
            delete_btn.clicked.connect(lambda checked, fid=file_set.id: self.delete_fileset(fid))
            self.setCellWidget(row, 7, delete_btn)  # 操作列に配置
    
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
                if mode == '既存試料を使用':
                    sample_id = getattr(file_set, 'sample_id', '')
                    return f"既存: {sample_id}" if sample_id else "既存: 未設定"
                elif mode == '新規試料作成':
                    return "新規"
                elif mode == '前回と同じ':
                    return "前と同じ"
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
        layout.addWidget(self.file_tree)
        
        # ファイルセット更新ボタン
        update_fileset_btn = QPushButton("選択ファイルセットを更新")
        update_fileset_btn.setToolTip("ファイルツリーの選択状態を選択されたファイルセットに反映します")
        update_fileset_btn.clicked.connect(self.update_selected_fileset_from_tree)
        update_fileset_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        layout.addWidget(update_fileset_btn)
        
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
        self.datasets = []  # データセット一覧
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
        
        refresh_btn = QPushButton("更新")
        refresh_btn.clicked.connect(self.refresh_file_tree)
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
        
        # ファイルセット作成（横一列表示）
        auto_group = QGroupBox("ファイルセット作成")
        auto_layout = QHBoxLayout()  # 横一列レイアウトに変更
        
        auto_all_btn = QPushButton("全体")
        auto_all_btn.clicked.connect(self.auto_assign_all_as_one)
        auto_layout.addWidget(auto_all_btn)
        
        auto_top_btn = QPushButton("最上位フォルダ")
        auto_top_btn.clicked.connect(self.auto_assign_by_top_dirs)
        auto_layout.addWidget(auto_top_btn)
        
        auto_all_dirs_btn = QPushButton("個別")
        auto_all_dirs_btn.clicked.connect(self.auto_assign_all_dirs)
        auto_layout.addWidget(auto_all_dirs_btn)
        
        auto_group.setLayout(auto_layout)
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
        
        add_manual_btn = QPushButton("手動作成...")
        add_manual_btn.clicked.connect(self.create_manual_fileset)
        toolbar_layout.addWidget(add_manual_btn)
        
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
        
        # ヘッダー部分（ボタンを最上段に横一列配置）
        header_layout = QHBoxLayout()
        
        popup_btn = QPushButton("別ウインドウで設定")
        popup_btn.setToolTip("選択ファイルセット設定を別ダイアログで開きます")
        popup_btn.clicked.connect(self.open_fileset_config_dialog)
        popup_btn.setMinimumHeight(30)
        header_layout.addWidget(popup_btn)
        
        save_individual_btn = QPushButton("一覧に反映（個別）")
        save_individual_btn.setToolTip("現在の設定を選択されたファイルセットに適用します")
        save_individual_btn.clicked.connect(self.save_current_fileset_settings)
        save_individual_btn.setMinimumHeight(30)
        header_layout.addWidget(save_individual_btn)
        
        detail_layout.addLayout(header_layout)
        
        # 2段目：一括適用ボタン
        batch_layout = QHBoxLayout()
        
        apply_all_btn = QPushButton("全ファイルセットに適用")
        apply_all_btn.setToolTip("現在の設定を全てのファイルセットに適用します")
        apply_all_btn.clicked.connect(self.apply_to_all_filesets)
        apply_all_btn.setMinimumHeight(30)
        batch_layout.addWidget(apply_all_btn)
        
        # ファイルセット選択適用
        apply_selected_btn = QPushButton("ファイルセットに適用")
        apply_selected_btn.setToolTip("現在の設定を選択されたファイルセットに適用します")
        apply_selected_btn.clicked.connect(self.apply_to_selected_filesets)
        apply_selected_btn.setMinimumHeight(30)
        batch_layout.addWidget(apply_selected_btn)
        
        self.target_fileset_combo = QComboBox()
        self.target_fileset_combo.setToolTip("適用対象のファイルセットを選択")
        self.target_fileset_combo.setMinimumWidth(200)
        batch_layout.addWidget(self.target_fileset_combo)
        
        detail_layout.addLayout(batch_layout)
        
        # スクロールエリアでラップ
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
        
        # データセット選択（通常登録と同様の実装）
        dataset_group = QGroupBox("データセット選択")
        dataset_layout = QVBoxLayout()
        
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
                dataset_layout.addWidget(self.dataset_combo)
        
        dataset_group.setLayout(dataset_layout)
        scroll_layout.addWidget(dataset_group)
        
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
        scroll_layout.addWidget(data_group)
        
        # 試料情報
        sample_group = QGroupBox("試料情報")
        sample_layout = QGridLayout()
        
        sample_layout.addWidget(QLabel("試料モード:"), 0, 0)
        self.sample_mode_combo = QComboBox()
        # 初期状態では基本オプションのみ
        self.sample_mode_combo.addItems(["新規作成", "既存試料使用"])
        sample_layout.addWidget(self.sample_mode_combo, 0, 1)
        
        sample_layout.addWidget(QLabel("試料選択:"), 1, 0)
        self.sample_id_combo = QComboBox()
        self.sample_id_combo.setEditable(True)
        self.sample_id_combo.setInsertPolicy(QComboBox.NoInsert)
        self.sample_id_combo.lineEdit().setPlaceholderText("既存試料を検索または新規入力...")
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
        
        # 固有情報（インボイススキーマ対応）- レイアウト簡素化
        custom_group = QGroupBox("固有情報")
        self.schema_form_layout = QVBoxLayout()
        self.schema_form_layout.setContentsMargins(10, 10, 10, 10)
        
        # 初期状態のメッセージ
        self.schema_placeholder_label = QLabel("データセット選択後に固有情報入力フォームが表示されます")
        self.schema_placeholder_label.setAlignment(Qt.AlignCenter)
        self.schema_placeholder_label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
        self.schema_form_layout.addWidget(self.schema_placeholder_label)
        
        custom_group.setLayout(self.schema_form_layout)
        scroll_layout.addWidget(custom_group)
        
        # 設定保存ボタン
        save_btn = QPushButton("設定保存")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        save_btn.clicked.connect(self.save_fileset_config)
        scroll_layout.addWidget(save_btn)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
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
        
        layout.addLayout(button_layout)
        
        widget.setLayout(layout)
        return widget
    
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
        
        # 既存試料選択
        self.sample_id_combo.currentIndexChanged.connect(self.on_sample_selected)
        
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
                    for fs_file_item in self.current_fileset.file_items:
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
            for file_item in fileset.file_items:
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
                        for file_item in fileset.file_items:
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
            # データ名設定
            if hasattr(self, 'data_name_input'):
                settings['data_name'] = self.data_name_input.text()
            
            # サンプル設定
            if hasattr(self, 'sample_input'):
                settings['sample'] = self.sample_input.text()
            
            # データセット設定
            if hasattr(self, 'dataset_combo'):
                settings['dataset'] = self.dataset_combo.currentText()
            
            # その他の設定項目があれば追加
            
        except Exception as e:
            print(f"[ERROR] 設定取得エラー: {e}")
            settings = {}
        
        return settings
    
    def _apply_settings_to_fileset(self, fileset, settings):
        """ファイルセットに設定を適用"""
        try:
            if 'data_name' in settings:
                fileset.data_name = settings['data_name']
            
            if 'sample' in settings:
                fileset.sample = settings['sample']
            
            if 'dataset' in settings:
                fileset.dataset = settings['dataset']
            
            # メタデータに保存
            if not hasattr(fileset, 'metadata'):
                fileset.metadata = {}
            fileset.metadata.update(settings)
            
            print(f"[INFO] ファイルセット '{fileset.name}' に設定を適用しました")
            
        except Exception as e:
            print(f"[ERROR] ファイルセット設定適用エラー: {e}")
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
    
    def save_current_fileset_settings(self):
        """現在選択されているファイルセットの設定を保存"""
        if not hasattr(self, 'current_fileset') or not self.current_fileset:
            QMessageBox.information(self, "情報", "ファイルセットが選択されていません。")
            return
        
        try:
            # 現在の設定を取得
            settings = self.get_current_settings()
            
            # 現在のファイルセットに適用
            self._apply_settings_to_fileset(self.current_fileset, settings)
            
            QMessageBox.information(self, "完了", f"ファイルセット '{self.current_fileset.name}' の設定を保存しました。")
            self.refresh_fileset_display()
            
        except Exception as e:
            print(f"[ERROR] ファイルセット設定保存エラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定の保存に失敗しました: {e}")
    
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
        directory = QFileDialog.getExistingDirectory(
            self, "ベースディレクトリを選択", self.dir_path_edit.text()
        )
        if directory:
            self.dir_path_edit.setText(directory)
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
    
    def expand_all(self):
        """全て展開"""
        self.file_tree.expandAll()
    
    def collapse_all(self):
        """全て折りたたみ"""
        self.file_tree.collapseAll()
    
    def select_all_files(self):
        """ファイルツリーの全てのファイルを選択"""
        try:
            for checkbox in self.file_tree.checkbox_items.values():
                checkbox.setChecked(True)
        except Exception as e:
            print(f"[ERROR] 全選択エラー: {e}")
    
    def deselect_all_files(self):
        """ファイルツリーの全てのファイルの選択を解除"""
        try:
            for checkbox in self.file_tree.checkbox_items.values():
                checkbox.setChecked(False)
        except Exception as e:
            print(f"[ERROR] 全解除エラー: {e}")
    
    def auto_assign_all_as_one(self):
        """全体で1つのファイルセット作成"""
        print(f"[DEBUG] auto_assign_all_as_one: 開始")
        if not self.file_set_manager:
            QMessageBox.warning(self, "エラー", "ベースディレクトリを選択してください")
            return

        try:
            file_sets = self.file_set_manager.auto_assign_filesets_all_as_one()
            print(f"[DEBUG] auto_assign_all_as_one: 作成されたファイルセット数={len(file_sets) if file_sets else 0}")
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
            file_sets = self.file_set_manager.auto_assign_filesets_by_top_level_dirs()
            print(f"[DEBUG] auto_assign_by_top_dirs: 作成されたファイルセット数={len(file_sets) if file_sets else 0}")
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
            file_sets = self.file_set_manager.auto_assign_filesets_all_directories()
            print(f"[DEBUG] auto_assign_all_dirs: 作成されたファイルセット数={len(file_sets) if file_sets else 0}")
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
                    self.on_dataset_changed(i)
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
        
        # データ情報を更新
        selected_fileset.data_name = self.data_name_edit.text()
        
        # 拡張フィールドを辞書に保存
        selected_fileset.extended_config = {
            # データ情報
            'description': self.description_edit.toPlainText(),
            'experiment_id': self.experiment_id_edit.text(),
            'reference_url': self.reference_url_edit.text(),
            'tags': self.tags_edit.text(),
            
            # 試料情報
            'sample_mode': self.sample_mode_combo.currentText(),
            'sample_id': self.sample_id_combo.currentText(),
            'sample_name': self.sample_name_edit.text(),
            'sample_description': self.sample_description_edit.toPlainText(),
            'sample_composition': self.sample_composition_edit.text(),
        }
        
        # テーブル更新
        self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
        
        # 「前回と同じ」オプションを再評価
        self.update_same_as_previous_option()
        
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
        
        preview = self.batch_logic.preview_batch_register(self.file_set_manager.file_sets)
        
        # プレビューダイアログ表示（簡易実装）
        preview_text = f"""
一括登録プレビュー

総ファイルセット数: {preview['total_filesets']}個
総ファイル数: {preview['total_files']}個
総サイズ: {self._format_size(preview['total_size'])}

ファイルセット詳細:
"""
        
        for fs_preview in preview['filesets']:
            preview_text += f"""
- {fs_preview['name']}
  ファイル数: {fs_preview['file_count']}個
  サイズ: {self._format_size(fs_preview['total_size'])}
  整理方法: {fs_preview['organize_method']}
  データセット: {fs_preview['dataset_id'] or '未設定'}
"""
        
        QMessageBox.information(self, "一括登録プレビュー", preview_text)
    
    def execute_batch_register(self):
        """一括登録実行"""
        if not self.file_set_manager or not self.file_set_manager.file_sets:
            QMessageBox.warning(self, "エラー", "実行するファイルセットがありません")
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
            "この処理は時間がかかる場合があります。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 一括登録実行
            self.batch_logic.run_batch_register(self.file_set_manager.file_sets)
    
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
    
    def open_fileset_config_dialog(self):
        """選択ファイルセット設定を別ダイアログで開く"""
        try:
            selected_fileset = self.fileset_table.get_selected_fileset()
            if not selected_fileset:
                QMessageBox.information(self, "情報", "設定を編集するファイルセットを選択してください")
                return
            
            # 別ダイアログクラスを作成
            dialog = FilesetConfigDialog(self, selected_fileset)
            if dialog.exec_() == QDialog.Accepted:
                # 設定が更新された場合はテーブルを更新
                self.fileset_table.load_file_sets(self.file_set_manager.file_sets)
                QMessageBox.information(self, "完了", "ファイルセット設定を更新しました")
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定ダイアログを開けませんでした:\n{e}")
            print(f"[ERROR] open_fileset_config_dialog: {e}")
    
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
                self.update_schema_form(dataset_data)
                
                # 選択された旨を表示
                QTimer.singleShot(500, lambda: print(f"[INFO] データセット反映完了: {dataset_id}"))
            else:
                # データセット未選択時はクリア
                print("[DEBUG] データセット未選択 - フィールドをクリア")
                self.clear_dynamic_fields()
                
        except Exception as e:
            print(f"[WARNING] データセット変更処理エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def on_sample_mode_changed(self, mode):
        """試料モード変更時の処理（通常登録と同等機能）"""
        try:
            print(f"[DEBUG] 試料モード変更: {mode}")
            
            if mode == "既存試料使用":
                # 既存試料コンボボックスを有効化し、試料リストを更新
                self.sample_id_combo.setEnabled(True)
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                
                # 現在選択されているデータセットの試料リストを再取得
                selected_dataset_id = self.get_selected_dataset_id()
                current_index = self.dataset_combo.currentIndex()
                current_text = self.dataset_combo.currentText()
                current_data = self.dataset_combo.currentData()
                
                print(f"[DEBUG] データセット選択状態: index={current_index}, text='{current_text}', data={current_data}")
                print(f"[DEBUG] get_selected_dataset_id()={selected_dataset_id}")
                
                if selected_dataset_id:
                    print(f"[DEBUG] 既存試料使用モード: 試料リスト更新開始")
                    self.update_sample_list(selected_dataset_id)
                else:
                    print("[WARNING] 既存試料使用モード: データセットが選択されていません")
                    
            elif mode == "新規作成":
                # 新規作成時は入力フィールドを有効化
                self.sample_id_combo.setEnabled(False)
                self.sample_name_edit.setEnabled(True)
                self.sample_description_edit.setEnabled(True)
                self.sample_composition_edit.setEnabled(True)
                # 入力フィールドをクリア
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                print("[DEBUG] 新規作成モード: 入力フィールドを有効化")
                
            elif mode == "前回と同じ":
                # 前回と同じ時は全てのフィールドを無効化
                self.sample_id_combo.setEnabled(False)
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                self.sample_composition_edit.setEnabled(False)
                print("[DEBUG] 前回と同じモード: 全フィールドを無効化")
                
            elif mode == "前回と同じ":
                # 前回と同じ時は全て無効化
                self.sample_id_combo.setEnabled(False)
                self.sample_name_edit.setEnabled(False)
                self.sample_description_edit.setEnabled(False)
                print("[DEBUG] 前回と同じモード: 全フィールドを無効化")
                
        except Exception as e:
            print(f"[WARNING] 試料モード変更処理エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def on_sample_selected(self, index):
        """既存試料選択時の処理"""
        try:
            print(f"[DEBUG] 既存試料選択: index={index}")
            
            if index <= 0:  # 最初のアイテム（プレースホルダー）の場合
                print("[DEBUG] プレースホルダー選択 - フィールドをクリア")
                self.sample_name_edit.clear()
                self.sample_description_edit.clear()
                self.sample_composition_edit.clear()
                return
            
            # 選択された試料データを取得
            current_data = self.sample_id_combo.currentData()
            if current_data and isinstance(current_data, dict):
                print(f"[DEBUG] 既存試料データ取得成功: {current_data.get('name', '')}")
                
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
                
                print(f"[INFO] 既存試料情報を表示: {sample_name}")
            else:
                print("[WARNING] 既存試料データが取得できません")
                
        except Exception as e:
            print(f"[WARNING] 既存試料選択エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def update_sample_list(self, dataset_id):
        """選択されたデータセットのサンプル一覧を更新（通常登録と同等機能）"""
        try:
            print(f"[DEBUG] サンプル一覧更新開始: dataset_id={dataset_id}")
            
            # サンプルコンボボックスをクリア
            self.sample_id_combo.clear()
            self.sample_id_combo.addItem("既存試料を選択してください", None)
            
            # データセットIDが有効な場合、関連サンプルを取得
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
                                    self.sample_id_combo.addItem(display_name, sample)
                                    print(f"[DEBUG] 既存試料追加: {display_name}")
                                
                                print(f"[INFO] 既存試料をコンボボックスに追加完了: {len(existing_samples)}件")
                            else:
                                print("[DEBUG] 既存試料データなし")
                                self.sample_id_combo.addItem("（既存試料なし）", None)
                        else:
                            print("[WARNING] グループID/サブグループIDが取得できません")
                            self.sample_id_combo.addItem("（グループ情報取得失敗）", None)
                    else:
                        print(f"[WARNING] 対象データセットが見つかりません: {dataset_id}")
                    
                except Exception as e:
                    print(f"[WARNING] サンプル情報取得失敗: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # フォールバック処理
                    self.sample_id_combo.addItem("（サンプル取得失敗）", None)
            else:
                print("[DEBUG] データセットIDが無効")
            
            print(f"[DEBUG] サンプル一覧更新完了: {self.sample_id_combo.count()}個の選択肢")
            
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
    
    def update_schema_form(self, dataset_data):
        """インボイススキーマに基づく固有情報フォームを更新（通常登録と同等機能）"""
        try:
            print(f"[DEBUG] スキーマフォーム更新開始: {dataset_data}")
            
            # 既存フォームをクリア
            self.clear_schema_form()
            
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
                            
                            # 通常登録と同じ方法でフォーム生成
                            schema_form = create_schema_form_from_path(invoice_schema_path, self)
                            
                            if schema_form:
                                print("[INFO] インボイススキーマフォーム生成成功")
                                
                                # プレースホルダーを非表示
                                self.schema_placeholder_label.hide()
                                
                                # 動的生成フォームを追加
                                self.schema_form_layout.addWidget(schema_form)
                                self.schema_form = schema_form  # 保存（後で値取得で使用）
                                
                                print("[INFO] インボイススキーマフォーム表示完了")
                            else:
                                print("[WARNING] スキーマフォーム生成失敗")
                                self.schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマフォーム生成に失敗しました")
                                self.schema_placeholder_label.show()
                        else:
                            print(f"[INFO] invoiceSchemaファイル未発見: {invoice_schema_path}")
                            self.schema_placeholder_label.setText(f"データセット '{dataset_name}' にはカスタム固有情報がありません")
                            self.schema_placeholder_label.show()
                    else:
                        print("[DEBUG] テンプレートIDが無効")
                        self.schema_placeholder_label.setText(f"データセット '{dataset_name}' にテンプレートIDがありません")
                        self.schema_placeholder_label.show()
                    
                except Exception as e:
                    print(f"[WARNING] スキーマ処理失敗: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    self.schema_placeholder_label.setText(f"データセット '{dataset_name}' のスキーマ処理でエラーが発生しました")
                    self.schema_placeholder_label.show()
            else:
                print("[DEBUG] データセットIDが無効")
                self.schema_placeholder_label.setText("データセットを選択してください")
                self.schema_placeholder_label.show()
            
            print("[DEBUG] スキーマフォーム更新完了")
            
        except Exception as e:
            print(f"[WARNING] スキーマフォーム更新エラー: {e}")
            import traceback
            traceback.print_exc()
            
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
            # 動的に生成されたフォーム要素を削除
            for i in reversed(range(self.schema_form_layout.count())):
                child = self.schema_form_layout.itemAt(i).widget()
                if child and child != self.schema_placeholder_label:
                    child.setParent(None)
            
            # プレースホルダーを表示
            self.schema_placeholder_label.setText("データセット選択後に固有情報入力フォームが表示されます")
            self.schema_placeholder_label.show()
            
        except Exception as e:
            print(f"[WARNING] スキーマフォームクリアエラー: {e}")

    def save_current_fileset_settings(self):
        """現在の設定を選択されたファイルセットに適用"""
        if not hasattr(self, 'current_fileset') or not self.current_fileset:
            QMessageBox.information(self, "情報", "ファイルセットが選択されていません。")
            return
        
        try:
            self._apply_settings_to_fileset(self.current_fileset)
            QMessageBox.information(self, "完了", f"ファイルセット '{self.current_fileset.name}' に設定を適用しました。")
            self.refresh_fileset_display()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
    
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
                applied_count = 0
                for fileset in self.file_set_manager.file_sets:
                    self._apply_settings_to_fileset(fileset)
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
            self._apply_settings_to_fileset(target_fileset)
            QMessageBox.information(self, "完了", f"ファイルセット '{target_name}' に設定を適用しました。")
            self.refresh_fileset_display()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
    
    def _apply_settings_to_fileset(self, fileset):
        """設定をファイルセットに適用するヘルパーメソッド"""
        try:
            # 基本情報を適用
            if hasattr(self, 'fileset_name_edit') and self.fileset_name_edit.text().strip():
                # 現在のファイルセット以外の場合のみ名前を更新（重複回避）
                if fileset != getattr(self, 'current_fileset', None):
                    base_name = self.fileset_name_edit.text().strip()
                    # 名前の重複を避けるため、必要に応じて番号を追加
                    name_candidate = base_name
                    counter = 1
                    while any(fs.name == name_candidate and fs != fileset for fs in self.file_set_manager.file_sets):
                        name_candidate = f"{base_name}_{counter}"
                        counter += 1
                    fileset.name = name_candidate
            
            if hasattr(self, 'organize_method_combo'):
                organize_text = self.organize_method_combo.currentText()
                from ..core.file_set_manager import PathOrganizeMethod
                fileset.organize_method = PathOrganizeMethod.ZIP if organize_text == "ZIP化" else PathOrganizeMethod.FLATTEN
            
            # データ関連情報を適用
            if hasattr(self, 'data_name_edit') and self.data_name_edit.text().strip():
                if not hasattr(fileset, 'data_name'):
                    fileset.data_name = ""
                fileset.data_name = self.data_name_edit.text().strip()
            
            if hasattr(self, 'description_edit') and self.description_edit.toPlainText().strip():
                if not hasattr(fileset, 'description'):
                    fileset.description = ""
                fileset.description = self.description_edit.toPlainText().strip()
            
            # データセット選択を適用
            if hasattr(self, 'dataset_combo') and self.dataset_combo.currentData():
                dataset_data = self.dataset_combo.currentData()
                if isinstance(dataset_data, dict) and 'id' in dataset_data:
                    if not hasattr(fileset, 'dataset_id'):
                        fileset.dataset_id = ""
                    fileset.dataset_id = dataset_data['id']
                    
        except Exception as e:
            print(f"[ERROR] _apply_settings_to_fileset: {e}")
            raise e
    
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
        schema_group = QGroupBox("固有情報")
        self.dialog_schema_form_layout = QVBoxLayout()
        
        # スキーマフォームプレースホルダー
        self.dialog_schema_placeholder_label = QLabel("データセットを選択すると、固有情報フォームが表示されます")
        self.dialog_schema_placeholder_label.setAlignment(Qt.AlignCenter)
        self.dialog_schema_placeholder_label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
        self.dialog_schema_form_layout.addWidget(self.dialog_schema_placeholder_label)
        
        schema_group.setLayout(self.dialog_schema_form_layout)
        scroll_layout.addWidget(schema_group)
        
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
            self.sample_id_combo.addItem("既存試料を選択してください", None)
            
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
            
            # 既存のスキーマフォームを削除
            if hasattr(self, 'dialog_schema_form') and self.dialog_schema_form:
                self.dialog_schema_form_layout.removeWidget(self.dialog_schema_form)
                self.dialog_schema_form.deleteLater()
                self.dialog_schema_form = None
                print("[DEBUG] ダイアログ: 既存スキーマフォーム削除")
            
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
