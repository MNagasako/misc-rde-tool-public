"""
フィルタリング可能なチェックボックステーブルウィジェット

大量のチェックボックス項目を表示・検索・選択するためのテーブルウィジェット
"""

from typing import List, Dict, Any
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from qt_compat.core import Qt

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

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
        self._populating = False
        self._sort_column = 1
        self._sort_order = Qt.SortOrder.AscendingOrder
        
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
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # NOTE: PySide6ではQTableWidgetItemの__lt__オーバーライド等が環境によって
        #       アクセス違反を引き起こしうるため、ソートはヘッダクリックで独自実装する。
        self.table.setSortingEnabled(False)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        # 選択列（チェックボックス）の表示: 0/1は表示せず、塗りつぶしでチェックを明瞭化
        # QTableWidgetItemのチェックボックスはindicatorとして描画されるためQSSでカスタム
        self.table.setStyleSheet(
            f"""
            QTableWidget::indicator {{
                width: 16px;
                height: 16px;
            }}
            QTableWidget::indicator:unchecked {{
                image: none;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background: transparent;
                border-radius: 3px;
            }}
            QTableWidget::indicator:checked {{
                image: none;
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
                background: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                border-radius: 3px;
            }}
            """
        )
        
        # 行の高さを設定して5行確実に表示
        self.table.verticalHeader().setDefaultSectionSize(25)  # 各行25px
        self.table.setMaximumHeight(self.max_height)
        self.table.setMinimumHeight(self.max_height)  # 最小高さも設定
        layout.addWidget(self.table)
    
    def _populate_table(self):
        """テーブルにデータを投入"""
        self._populating = True
        # 独自ソートのためQt標準ソートは常に無効
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

            # 選択（チェック状態はチェックボックスで表現。数値表示はしない）
            select_item = QTableWidgetItem("")
            select_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            select_item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            select_item.setData(Qt.ItemDataRole.UserRole, value)
            # 独自ソート用キー（表示しない）
            select_item.setData(Qt.ItemDataRole.UserRole + 1, 1 if is_checked else 0)
            self.table.setItem(row, 0, select_item)
            
            # ラベル
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, value)  # valueをUserRoleに保存
            self.table.setItem(row, 1, label_item)
            
            visible_count += 1
            if is_checked:
                checked_count += 1
        
        self.table.setSortingEnabled(False)
        self._update_count_label(visible_count, checked_count)

        # 直前のソート条件があれば適用
        try:
            self._apply_sort(self._sort_column, self._sort_order)
        except Exception:
            pass

        self._populating = False
        
        logger.debug(f"{self.field_name}: 表示={visible_count}件, 選択={checked_count}件")
    
    def _on_filter_changed(self, text: str):
        """フィルタ変更時の処理"""
        self.filter_text = text.strip()
        self._populate_table()
    
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """選択列（チェック）の変更をselected_valuesへ反映"""
        if self._populating:
            return
        if item is None:
            return
        if item.column() != 0:
            return

        value = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not value:
            return

        checked = item.checkState() == Qt.CheckState.Checked

        # 独自ソート用キー更新
        try:
            self._populating = True
            item.setData(Qt.ItemDataRole.UserRole + 1, 1 if checked else 0)
        finally:
            self._populating = False

        if checked:
            self.selected_values.add(value)
        else:
            self.selected_values.discard(value)

        self._update_count_label(self.table.rowCount(), len(self.selected_values))
        logger.debug(f"{self.field_name}: {value} {'選択' if checked else '解除'}, 合計={len(self.selected_values)}件")

    def _on_header_clicked(self, section: int) -> None:
        """ヘッダクリックで独自ソート（選択列はチェック状態でソート）"""
        if section not in (0, 1):
            return

        # 同じ列を連続クリックしたら昇降順をトグル
        if self._sort_column == section:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = section
            self._sort_order = Qt.SortOrder.AscendingOrder

        self._apply_sort(self._sort_column, self._sort_order)

    def _apply_sort(self, column: int, order: Qt.SortOrder) -> None:
        """現在表示中の行をソートして並び替える（チェック状態/ラベル）"""
        if self._populating:
            return

        row_count = self.table.rowCount()
        if row_count <= 1:
            return

        def _row_key(row: int):
            if column == 0:
                item = self.table.item(row, 0)
                checked = item is not None and item.checkState() == Qt.CheckState.Checked
                # Asc: 未チェック→チェック, Desc: 逆
                return (1 if checked else 0,)

            item = self.table.item(row, 1)
            text = item.text() if item is not None else ""
            return (text.casefold(),)

        reverse = order == Qt.SortOrder.DescendingOrder
        new_order = sorted(range(row_count), key=_row_key, reverse=reverse)

        # 並び替え（itemChangedが走らないようブロック）
        self._populating = True
        try:
            snapshots: list[list[QTableWidgetItem | None]] = []
            for r in range(row_count):
                row_items: list[QTableWidgetItem | None] = []
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    row_items.append(it.clone() if it is not None else None)
                snapshots.append(row_items)

            self.table.setRowCount(0)
            for src_row in new_order:
                dst_row = self.table.rowCount()
                self.table.insertRow(dst_row)
                for c, it in enumerate(snapshots[src_row]):
                    if it is not None:
                        self.table.setItem(dst_row, c, it)
        finally:
            self._populating = False

        # ソートインジケータ更新
        try:
            self.table.horizontalHeader().setSortIndicator(column, order)
        except Exception:
            pass
    
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
