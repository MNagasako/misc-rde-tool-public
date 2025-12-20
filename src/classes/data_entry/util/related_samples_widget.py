import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
    QLabel, QComboBox, QFrame
)
from qt_compat.core import Qt, Signal
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color
from classes.data_entry.util.sample_loader import load_existing_samples, format_sample_display_name

logger = logging.getLogger(__name__)

class RelatedSamplesWidget(QWidget):
    """
    関連試料管理ウィジェット
    
    機能:
    - 既存試料から選択して関連付け
    - 関連付けごとの説明入力
    - 複数追加可能
    """
    
    def __init__(self, parent=None, group_id=None):
        super().__init__(parent)
        self.group_id = group_id
        self.related_samples = []
        self.available_samples = []
        self.setup_ui()
        if group_id:
            self.load_samples(group_id)

        try:
            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass

    def _get_add_button_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};
                border-radius: 4px;
                padding: 4px 10px;
                min-height: 26px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};
            }}
        """

    def _get_desc_input_style(self) -> str:
        return f"""
            QLineEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 4px;
            }}
        """

    def _get_remove_button_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
        """

    def refresh_theme(self, *_args):
        try:
            self.add_button.setStyleSheet(self._get_add_button_style())
            for item in self.related_samples:
                item["desc_input"].setStyleSheet(self._get_desc_input_style())
                # remove_btn はlistに保持していないため、row_widgetから再取得
                row_widget = item.get("widget")
                if row_widget is not None:
                    for btn in row_widget.findChildren(QPushButton):
                        if btn.text() == "✕":
                            btn.setStyleSheet(self._get_remove_button_style())
        except Exception:
            pass
        
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5)
        
        # 関連試料リストエリア
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(5)
        self.main_layout.addLayout(self.list_layout)
        
        # 追加ボタン
        self.add_button = QPushButton("+ 関連試料を追加")
        self.add_button.clicked.connect(lambda: self.add_related_sample_row())
        self.add_button.setStyleSheet(self._get_add_button_style())
        self.main_layout.addWidget(self.add_button)
        
    def load_samples(self, group_id):
        self.group_id = group_id
        self.available_samples = load_existing_samples(group_id)
        # 既存の行のコンボボックスを更新
        for item in self.related_samples:
            self._update_combo_items(item["combo"])
            
    def _update_combo_items(self, combo):
        current_data = combo.currentData()
        combo.clear()
        combo.addItem("試料を選択...", None)
        for sample in self.available_samples:
            display_name = format_sample_display_name(sample)
            combo.addItem(display_name, sample)
            
        if current_data:
            # 以前選択していた項目を再選択
            index = combo.findData(current_data)
            if index >= 0:
                combo.setCurrentIndex(index)
                
    def add_related_sample_row(self, sample_id=None, description=""):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        # 試料選択コンボボックス
        combo = QComboBox()
        combo.setMinimumWidth(200)
        self._update_combo_items(combo)
        
        if sample_id:
            # sample_idに一致するデータを探して選択
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data and data.get("id") == sample_id:
                    combo.setCurrentIndex(i)
                    break
        
        # 説明入力
        desc_input = QLineEdit()
        desc_input.setText(description)
        desc_input.setPlaceholderText("関連の説明")
        desc_input.setStyleSheet(self._get_desc_input_style())
        
        # 削除ボタン
        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(30)
        remove_btn.setToolTip("削除")
        remove_btn.clicked.connect(lambda: self.remove_related_sample_row(row_widget))
        remove_btn.setStyleSheet(self._get_remove_button_style())
        
        row_layout.addWidget(combo, 1) # Stretch factor 1
        row_layout.addWidget(desc_input, 2) # Stretch factor 2
        row_layout.addWidget(remove_btn)
        
        self.list_layout.addWidget(row_widget)
        self.related_samples.append({
            "widget": row_widget,
            "combo": combo,
            "desc_input": desc_input
        })
        
    def remove_related_sample_row(self, row_widget):
        target_index = -1
        for i, item in enumerate(self.related_samples):
            if item["widget"] == row_widget:
                target_index = i
                break
        
        if target_index != -1:
            self.list_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self.related_samples.pop(target_index)

    def get_related_samples(self):
        """
        関連試料リストを取得
        Returns:
            list: [{"relatedSampleId": "...", "description": "..."}, ...]
        """
        result = []
        for item in self.related_samples:
            data = item["combo"].currentData()
            if data and data.get("id"):
                result.append({
                    "relatedSampleId": data.get("id"),
                    "description": item["desc_input"].text()
                })
        return result

    def set_related_samples(self, related_samples_data):
        """
        関連試料リストを設定
        Args:
            related_samples_data: [{"relatedSampleId": "...", "description": "..."}, ...]
        """
        # 既存をクリア
        while self.related_samples:
            self.remove_related_sample_row(self.related_samples[0]["widget"])
            
        if not related_samples_data:
            return
            
        for item in related_samples_data:
            self.add_related_sample_row(
                sample_id=item.get("relatedSampleId"),
                description=item.get("description", "")
            )
