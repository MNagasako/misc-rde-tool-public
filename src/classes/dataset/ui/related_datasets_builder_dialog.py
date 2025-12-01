"""
関連データセットビルダーダイアログ - RelatedDatasetsBuilderDialog
関連データセットをコンボボックスとテーブルで管理するダイアログ
"""
import os
import json
import logging

# MagicMock汚染回避のため、PySide6から直接インポート
try:
    from qt_compat.widgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QCompleter
    )
    from qt_compat.core import Qt, Signal
    from unittest.mock import MagicMock
    # qt_compatがMagicMockを返している場合はPySide6実体へフォールバック
    if isinstance(QDialog, MagicMock):
        raise ImportError("qt_compat contaminated by MagicMock")
except Exception:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QCompleter
    )
    from PySide6.QtCore import Qt, Signal

from config.common import get_dynamic_file_path
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)


class RelatedDatasetsBuilderDialog(QDialog):
    """関連データセットビルダーダイアログ
    
    関連データセットをコンボボックスで選択し、テーブルで管理する。
    同じ課題番号のデータセットを全て追加する機能も提供。
    
    Signals:
        datasets_changed: 関連データセットが変更された時に発火 (list: dataset_id のリスト)
    """
    
    datasets_changed = Signal(list)
    
    def __init__(self, parent=None, current_dataset_ids=None, exclude_dataset_id=None, current_grant_number=None):
        """
        Args:
            parent: 親ウィジェット
            current_dataset_ids: 現在選択されている関連データセットIDのリスト
            exclude_dataset_id: 除外するデータセットID（編集中のデータセット）
            current_grant_number: 現在のデータセットの課題番号（同じ課題番号追加用）
        """
        super().__init__(parent)
        self.setWindowTitle("関連データセットビルダー")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        
        self.exclude_dataset_id = exclude_dataset_id
        self.current_grant_number = current_grant_number
        self.all_datasets = []
        self.user_grant_numbers = set()
        
        # ダイアログレイアウト
        layout = QVBoxLayout()
        
        # 説明ラベル
        desc_label = QLabel("関連データセットを選択・管理します")
        desc_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)}; margin-bottom: 8px;")
        layout.addWidget(desc_label)
        
        # データセット選択エリア
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("データセット選択:"))
        
        self.dataset_combo = QComboBox()
        self.dataset_combo.setEditable(True)
        self.dataset_combo.setInsertPolicy(QComboBox.NoInsert)
        self.dataset_combo.lineEdit().setPlaceholderText("関連データセットを検索・選択...")
        select_layout.addWidget(self.dataset_combo, 1)
        
        # 課題番号全追加ボタン
        self.add_all_grant_button = QPushButton("同じ課題番号を全て追加")
        self.add_all_grant_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        self.add_all_grant_button.clicked.connect(self.add_all_from_grant_number)
        select_layout.addWidget(self.add_all_grant_button)
        
        # 課題番号が設定されていない場合はボタンを無効化
        if not current_grant_number:
            self.add_all_grant_button.setEnabled(False)
            self.add_all_grant_button.setToolTip("現在のデータセットに課題番号が設定されていません")
        else:
            self.add_all_grant_button.setToolTip(f"課題番号 '{current_grant_number}' の全データセットを追加")
        
        layout.addLayout(select_layout)
        
        # テーブル作成
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["課題番号", "データセット名", "タイプ", "操作"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.setMinimumWidth(100)
        ok_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.setMinimumWidth(100)
        cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # データ読み込みとセットアップ
        self._load_all_datasets()
        self._setup_combo()
        
        # 現在のデータセットを読み込み
        if current_dataset_ids:
            self._load_current_datasets(current_dataset_ids)
        
        # コンボボックスのイベント接続
        self.dataset_combo.activated.connect(self._on_dataset_selected)
        self.dataset_combo.lineEdit().returnPressed.connect(self._on_return_pressed)
    
    def _load_all_datasets(self):
        """全データセットを読み込み"""
        try:
            datasets_file = get_dynamic_file_path("output/rde/data/dataset.json")
            if not os.path.exists(datasets_file):
                logger.error("データセットファイルが見つかりません: %s", datasets_file)
                return
            
            with open(datasets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            all_datasets = data.get("data", [])
            
            # 除外するデータセットIDがある場合はフィルタリング
            if self.exclude_dataset_id:
                all_datasets = [ds for ds in all_datasets if ds.get("id") != self.exclude_dataset_id]
            
            self.all_datasets = all_datasets
            logger.info("全データセット読み込み完了: %s件", len(self.all_datasets))
            
            # ユーザーのgrantNumberを取得
            self._load_user_grant_numbers()
            
        except Exception as e:
            logger.error("データセット読み込みエラー: %s", e)
    
    def _load_user_grant_numbers(self):
        """ユーザーのgrantNumberを取得"""
        try:
            # サブグループファイルとセルフファイルから取得
            sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
            self_path = get_dynamic_file_path('output/rde/data/dataset.json')
            
            grant_numbers = set()
            
            if os.path.exists(sub_group_path):
                with open(sub_group_path, encoding="utf-8") as f:
                    sub_group_data = json.load(f)
                for sg in sub_group_data.get("data", []):
                    gn = sg.get("attributes", {}).get("grantNumber")
                    if gn:
                        grant_numbers.add(gn)
            
            self.user_grant_numbers = grant_numbers
            logger.debug("ユーザー課題番号: %s", grant_numbers)
            
        except Exception as e:
            logger.debug("ユーザー課題番号取得エラー: %s", e)
    
    def _setup_combo(self):
        """コンボボックスのセットアップ"""
        # ユーザーのデータセットとその他に分離してソート
        user_datasets = []
        other_datasets = []
        
        for dataset in self.all_datasets:
            attrs = dataset.get("attributes", {})
            grant_number = attrs.get("grantNumber", "")
            
            if grant_number in self.user_grant_numbers:
                user_datasets.append(dataset)
            else:
                other_datasets.append(dataset)
        
        sorted_datasets = user_datasets + other_datasets
        
        # コンボボックスに追加
        display_names = []
        for i, dataset in enumerate(sorted_datasets):
            attrs = dataset.get("attributes", {})
            name = attrs.get("name", "名前なし")
            grant_number = attrs.get("grantNumber", "")
            dataset_type = attrs.get("datasetType", "")
            dataset_id = dataset.get("id", "")
            
            # ユーザー所属かどうかで表示を区別
            if i < len(user_datasets):
                display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
            else:
                display_text = f"{grant_number} - {name} (ID: {dataset_id})"
            
            if dataset_type:
                display_text += f" [{dataset_type}]"
            
            self.dataset_combo.addItem(display_text, dataset)
            display_names.append(display_text)
        
        # Completer設定
        completer = QCompleter(display_names, self.dataset_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.dataset_combo.setCompleter(completer)
        
        logger.info("コンボボックスセットアップ完了: %s件", len(sorted_datasets))
    
    def _load_current_datasets(self, dataset_ids):
        """現在選択されているデータセットをテーブルに読み込み"""
        for dataset_id in dataset_ids:
            # all_datasetsから該当データセットを検索
            dataset = None
            for ds in self.all_datasets:
                if ds.get("id") == dataset_id:
                    dataset = ds
                    break
            
            if dataset:
                self._add_dataset_to_table(dataset)
            else:
                logger.warning("データセットID '%s' が見つかりません", dataset_id)
    
    def _add_dataset_to_table(self, dataset):
        """テーブルにデータセットを追加"""
        dataset_id = dataset.get("id", "")
        attrs = dataset.get("attributes", {})
        grant_number = attrs.get("grantNumber", "")
        name = attrs.get("name", "名前なし")
        dataset_type = attrs.get("datasetType", "")
        
        # 既に追加済みかチェック
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == dataset_id:
                logger.debug("データセットは既に追加済み: %s", name)
                return False
        
        # 新しい行を追加
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # 課題番号（dataset_idをUserRoleに保存）
        grant_item = QTableWidgetItem(grant_number)
        grant_item.setData(Qt.UserRole, dataset_id)
        self.table.setItem(row, 0, grant_item)
        
        # データセット名
        name_item = QTableWidgetItem(name)
        self.table.setItem(row, 1, name_item)
        
        # タイプ
        type_item = QTableWidgetItem(dataset_type)
        self.table.setItem(row, 2, type_item)
        
        # 削除ボタン
        delete_button = QPushButton("削除")
        delete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
        """)
        delete_button.clicked.connect(lambda checked=False, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 3, delete_button)
        
        logger.debug("データセット追加: %s", name)
        return True
    
    def _delete_row(self, row):
        """指定された行を削除"""
        # ボタンから実際の行を特定
        for i in range(self.table.rowCount()):
            widget = self.table.cellWidget(i, 3)
            if widget and widget.sender() == widget:
                item = self.table.item(i, 1)
                name = item.text() if item else "不明"
                self.table.removeRow(i)
                logger.debug("データセット削除: row=%s, name=%s", i, name)
                return
    
    def _on_dataset_selected(self, index):
        """コンボボックスでデータセットが選択された時"""
        if index < 0:
            return
        
        dataset = self.dataset_combo.itemData(index)
        if dataset:
            self._add_dataset_to_table(dataset)
            self.dataset_combo.setCurrentIndex(-1)
            self.dataset_combo.lineEdit().clear()
    
    def _on_return_pressed(self):
        """Enterキーが押された時"""
        current_index = self.dataset_combo.currentIndex()
        if current_index >= 0:
            self._on_dataset_selected(current_index)
    
    def add_all_from_grant_number(self):
        """同じ課題番号のデータセットを全て追加"""
        if not self.current_grant_number:
            QMessageBox.warning(self, "エラー", "課題番号が設定されていません。")
            return
        
        # 同じ課題番号のデータセットを検索
        matching_datasets = []
        for dataset in self.all_datasets:
            attrs = dataset.get("attributes", {})
            grant_number = attrs.get("grantNumber", "")
            if grant_number == self.current_grant_number:
                matching_datasets.append(dataset)
        
        if not matching_datasets:
            QMessageBox.information(self, "情報", f"課題番号 '{self.current_grant_number}' のデータセットが見つかりません。")
            return
        
        # 全て追加
        added_count = 0
        for dataset in matching_datasets:
            if self._add_dataset_to_table(dataset):
                added_count += 1
        
        if added_count > 0:
            QMessageBox.information(self, "完了", f"課題番号 '{self.current_grant_number}' のデータセット {added_count}件を追加しました。")
            logger.info("同じ課題番号のデータセット追加: %s件", added_count)
        else:
            QMessageBox.information(self, "情報", "追加可能なデータセットはありません（全て選択済みです）。")
    
    def get_selected_dataset_ids(self):
        """選択されているデータセットIDのリストを取得"""
        dataset_ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                dataset_id = item.data(Qt.UserRole)
                if dataset_id:
                    dataset_ids.append(dataset_id)
        return dataset_ids
    
    def accept(self):
        """OKボタンが押された時の処理"""
        dataset_ids = self.get_selected_dataset_ids()
        logger.info("関連データセットビルダー完了: %s件", len(dataset_ids))
        self.datasets_changed.emit(dataset_ids)
        super().accept()
