"""
動的リストウィジェット

複数の項目を動的に追加・削除できるリストウィジェット
装置・プロセス、論文・プロシーディング等で使用
"""

from typing import List, Dict, Any, Callable
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QLineEdit, QFormLayout, QScrollArea
)
from qt_compat.core import Qt

from classes.managers.log_manager import get_logger

logger = get_logger("DataPortal.DynamicListWidget")


class DynamicListWidget(QWidget):
    """
    動的リストウィジェット
    
    機能:
    - 項目の追加・削除
    - トグル表示（空項目は折りたたみ）
    - 添え字番号表示
    """
    
    def __init__(self, field_prefix: str, label: str, field_names: List[str], 
                 field_labels: List[str], items: List[Dict[str, str]] = None, parent=None):
        """
        初期化
        
        Args:
            field_prefix: フィールド名プレフィックス（例: 't_eq_prs'）
            label: グループラベル（例: '装置・プロセス'）
            field_names: フィールド名リスト（例: ['name', 'model']）
            field_labels: フィールドラベルリスト（例: ['装置名', '型番']）
            items: 既存項目リスト [{'name': 'xxx', 'model': 'yyy'}, ...]
            parent: 親ウィジェット
        """
        super().__init__(parent)
        
        self.field_prefix = field_prefix
        self.label = label
        self.field_names = field_names
        self.field_labels = field_labels
        self.items = items or [{}]  # 最低1つの空項目
        self.item_widgets = []  # 各項目のウィジェットリスト
        
        self._init_ui()
        self._populate_items()
        
        logger.info(f"DynamicListWidget初期化: {field_prefix}, {len(self.items)}項目")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # ヘッダー
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"📋 {self.label}"))
        header_layout.addStretch()
        
        # 追加ボタン
        self.add_btn = QPushButton("➕ 項目を追加")
        self.add_btn.clicked.connect(self._on_add_item)
        header_layout.addWidget(self.add_btn)
        
        layout.addLayout(header_layout)
        
        # スクロールエリア（項目リスト）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMaximumHeight(400)
        
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll.setWidget(self.scroll_widget)
        layout.addWidget(scroll)
    
    def _populate_items(self):
        """項目を表示"""
        # 既存ウィジェットをクリア
        for widget in self.item_widgets:
            self.scroll_layout.removeWidget(widget)
            widget.deleteLater()
        self.item_widgets.clear()
        
        # 各項目のグループボックスを作成
        for index, item in enumerate(self.items):
            item_widget = self._create_item_widget(index, item)
            self.item_widgets.append(item_widget)
            self.scroll_layout.addWidget(item_widget)
        
        self.scroll_layout.addStretch()
    
    def _create_item_widget(self, index: int, item: Dict[str, str]) -> QGroupBox:
        """項目ウィジェットを作成"""
        # 項目が空かチェック
        is_empty = all(not item.get(fn, '').strip() for fn in self.field_names)
        
        group = QGroupBox(f"{self.label} #{index + 1}")
        group.setCheckable(True)
        group.setChecked(not is_empty)  # 空項目は折りたたみ
        group.setProperty('item_index', index)
        
        layout = QVBoxLayout(group)
        
        # フィールド
        form_layout = QFormLayout()
        field_widgets = {}
        
        for fn, fl in zip(self.field_names, self.field_labels):
            line_edit = QLineEdit(item.get(fn, ''))
            line_edit.setProperty('field_name', fn)
            line_edit.setProperty('item_index', index)
            line_edit.textChanged.connect(lambda text, idx=index, name=fn: self._on_field_changed(idx, name, text))
            field_widgets[fn] = line_edit
            form_layout.addRow(f"{fl}:", line_edit)
        
        group.setProperty('field_widgets', field_widgets)
        layout.addLayout(form_layout)
        
        # 削除ボタン
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        delete_btn = QPushButton("🗑️ この項目を削除")
        delete_btn.clicked.connect(lambda: self._on_delete_item(index))
        delete_btn.setStyleSheet("color: #f44336;")
        btn_layout.addWidget(delete_btn)
        
        layout.addLayout(btn_layout)
        
        return group
    
    def _on_add_item(self):
        """項目追加"""
        self.items.append({})
        self._populate_items()
        logger.info(f"{self.field_prefix}: 項目追加, 合計={len(self.items)}件")
    
    def _on_delete_item(self, index: int):
        """項目削除"""
        if len(self.items) <= 1:
            # 最低1つは残す
            logger.warning(f"{self.field_prefix}: 最後の項目は削除できません")
            return
        
        del self.items[index]
        self._populate_items()
        logger.info(f"{self.field_prefix}: 項目削除 (#{index + 1}), 残り={len(self.items)}件")
    
    def _on_field_changed(self, index: int, field_name: str, text: str):
        """フィールド変更時の処理"""
        if index < len(self.items):
            self.items[index][field_name] = text
            logger.debug(f"{self.field_prefix}[{index}].{field_name} = {text}")
    
    def get_items(self) -> List[Dict[str, str]]:
        """全項目を取得"""
        # 空項目を除外
        non_empty_items = []
        for item in self.items:
            if any(item.get(fn, '').strip() for fn in self.field_names):
                non_empty_items.append(item)
        
        return non_empty_items
    
    def set_items(self, items: List[Dict[str, str]]):
        """項目を設定"""
        self.items = items if items else [{}]
        self._populate_items()
