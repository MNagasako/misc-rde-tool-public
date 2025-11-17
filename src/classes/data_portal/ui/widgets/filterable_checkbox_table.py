"""
フィルタリング可能なチェックボックステーブルウィジェット

大量のチェックボックス項目を表示・検索・選択するためのテーブルウィジェット
"""

from typing import List, Dict, Any
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QAbstractItemView
)
from qt_compat.core import Qt

from classes.managers.log_manager import get_logger

logger = get_logger("DataPortal.FilterableCheckboxTable")


class FilterableCheckboxTable(QWidget):
    """
    フィルタリング可能なチェックボックステーブル
    
    機能:
    - 大量のチェックボックス項目をテーブル表示
    - リアルタイムフィルタリング
    - チェック済み項目は常に表示
    - ソート可能
    """
    
    def __init__(self, field_name: str, label: str, options: List[Dict[str, str]], 
                 selected_values: List[str] = None, max_height: int = 150, parent=None):
        """
        初期化
        
        Args:
            field_name: フィールド名（例: 't_eqp_code_array[]'）
            label: ラベル（例: '設備分類'）
            options: 選択肢リスト [{'value': 'xxx', 'label': 'yyy'}, ...]
            selected_values: 選択済みの値リスト
            max_height: テーブルの最大高さ（デフォルト: 150px = 約5行）
            parent: 親ウィジェット
        """
        super().__init__(parent)
        
        self.field_name = field_name
        self.label = label
        self.options = options
        self.selected_values = set(selected_values or [])
        self.filter_text = ""
        self.max_height = max_height
        
        self._init_ui()
        self._populate_table()
        
        logger.info(f"FilterableCheckboxTable初期化: {field_name}, {len(options)}項目, {len(self.selected_values)}選択済み, 高さ={max_height}px")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # ヘッダー行
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"🔍 {self.label} - フィルタ:"))
        
        # フィルタ入力
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(f"{self.label}名で検索...")
        self.filter_input.textChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.filter_input)
        
        # 件数表示
        self.count_label = QLabel()
        header_layout.addWidget(self.count_label)
        
        layout.addLayout(header_layout)
        
        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["選択", self.label])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        
        # 行の高さを設定して5行確実に表示
        self.table.verticalHeader().setDefaultSectionSize(25)  # 各行25px
        self.table.setMaximumHeight(self.max_height)
        self.table.setMinimumHeight(self.max_height)  # 最小高さも設定
        layout.addWidget(self.table)
    
    def _populate_table(self):
        """テーブルにデータを投入"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        visible_count = 0
        checked_count = 0
        
        for opt in self.options:
            value = opt['value']
            label = opt.get('label', value)
            is_checked = value in self.selected_values
            
            # フィルタリング判定
            if self.filter_text and not is_checked:
                # チェック済みでない場合はフィルタを適用
                if self.filter_text.lower() not in label.lower():
                    continue
            
            # 行を追加
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # チェックボックス
            checkbox = QCheckBox()
            checkbox.setChecked(is_checked)
            checkbox.setProperty('value', value)
            checkbox.toggled.connect(lambda checked, v=value: self._on_checkbox_toggled(v, checked))
            
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(row, 0, checkbox_widget)
            
            # ラベル
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, value)  # valueをUserRoleに保存
            self.table.setItem(row, 1, label_item)
            
            visible_count += 1
            if is_checked:
                checked_count += 1
        
        self.table.setSortingEnabled(True)
        self._update_count_label(visible_count, checked_count)
        
        logger.debug(f"{self.field_name}: 表示={visible_count}件, 選択={checked_count}件")
    
    def _on_filter_changed(self, text: str):
        """フィルタ変更時の処理"""
        self.filter_text = text.strip()
        self._populate_table()
    
    def _on_checkbox_toggled(self, value: str, checked: bool):
        """チェックボックストグル時の処理"""
        if checked:
            self.selected_values.add(value)
        else:
            self.selected_values.discard(value)
        
        self._update_count_label(self.table.rowCount(), len(self.selected_values))
        logger.debug(f"{self.field_name}: {value} {'選択' if checked else '解除'}, 合計={len(self.selected_values)}件")
    
    def _update_count_label(self, visible: int, checked: int):
        """件数ラベルを更新"""
        self.count_label.setText(f"表示: {visible}/{len(self.options)}件 | 選択: {checked}件")
    
    def get_selected_values(self) -> List[str]:
        """選択されている値のリストを取得"""
        return list(self.selected_values)
    
    def set_selected_values(self, values: List[str]):
        """選択値を設定"""
        self.selected_values = set(values)
        self._populate_table()
