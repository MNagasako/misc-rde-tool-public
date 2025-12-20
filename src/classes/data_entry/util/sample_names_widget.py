import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
    QLabel, QScrollArea, QFrame
)
from qt_compat.core import Qt, Signal
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color

logger = logging.getLogger(__name__)

class SampleNamesWidget(QWidget):
    """
    試料名管理ウィジェット
    
    機能:
    - 最大5件までの試料名を入力可能
    - 追加/削除ボタン
    """
    
    def __init__(self, parent=None, max_samples=5):
        super().__init__(parent)
        self.max_samples = max_samples
        self.sample_inputs = []
        self.setup_ui()

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

    def _get_input_style(self) -> str:
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
            for item in self.sample_inputs:
                item["input"].setStyleSheet(self._get_input_style())
                item["remove_btn"].setStyleSheet(self._get_remove_button_style())
        except Exception:
            pass
        
    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5)
        
        # 試料名入力エリア
        self.inputs_layout = QVBoxLayout()
        self.inputs_layout.setSpacing(5)
        self.main_layout.addLayout(self.inputs_layout)
        
        # 追加ボタン
        self.add_button = QPushButton("+ 試料名を追加")
        self.add_button.clicked.connect(lambda: self.add_sample_input())
        self.add_button.setStyleSheet(self._get_add_button_style())
        self.main_layout.addWidget(self.add_button)
        
        # 初期状態で1つ追加
        self.add_sample_input()
        
    def add_sample_input(self, text=""):
        if len(self.sample_inputs) >= self.max_samples:
            return
            
        index = len(self.sample_inputs)
        
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        label = QLabel(f"試料名 {index + 1}")
        label.setFixedWidth(80)
        
        input_field = QLineEdit()
        input_field.setText(text)
        input_field.setPlaceholderText(f"試料名 {index + 1}")
        input_field.setStyleSheet(self._get_input_style())
        
        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(30)
        remove_btn.setToolTip("削除")
        remove_btn.clicked.connect(lambda: self.remove_sample_input(row_widget))
        remove_btn.setStyleSheet(self._get_remove_button_style())
        
        # 最初の1つは削除不可にする場合もあるが、
        # ここでは全て削除可能にして、0個になったら自動で1つ追加するか、
        # あるいは最初の1つは削除ボタンを無効にするか。
        # 仕様書には「最大5件」とあるが、最小件数は明記されていない。
        # 通常は少なくとも1つは必要。
        if index == 0:
            remove_btn.setEnabled(False)
            remove_btn.setVisible(False)
        
        row_layout.addWidget(label)
        row_layout.addWidget(input_field)
        row_layout.addWidget(remove_btn)
        
        self.inputs_layout.addWidget(row_widget)
        self.sample_inputs.append({
            "widget": row_widget,
            "input": input_field,
            "remove_btn": remove_btn,
            "label": label
        })
        
        self._update_ui_state()
        
    def remove_sample_input(self, row_widget):
        # 削除対象のインデックスを探す
        target_index = -1
        for i, item in enumerate(self.sample_inputs):
            if item["widget"] == row_widget:
                target_index = i
                break
        
        if target_index != -1:
            # ウィジェットを削除
            self.inputs_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self.sample_inputs.pop(target_index)
            
            # ラベルと削除ボタンの状態を更新
            self._update_ui_state()
            
    def _update_ui_state(self):
        # ラベルの番号を振り直す
        for i, item in enumerate(self.sample_inputs):
            item["label"].setText(f"試料名 {i + 1}")
            item["input"].setPlaceholderText(f"試料名 {i + 1}")
            
            # 最初の項目は削除不可
            if i == 0:
                item["remove_btn"].setEnabled(False)
                item["remove_btn"].setVisible(False)
            else:
                item["remove_btn"].setEnabled(True)
                item["remove_btn"].setVisible(True)
                
        # 追加ボタンの有効/無効
        if len(self.sample_inputs) >= self.max_samples:
            self.add_button.setEnabled(False)
            self.add_button.setText(f"最大{self.max_samples}件までです")
        else:
            self.add_button.setEnabled(True)
            self.add_button.setText("+ 試料名を追加")

    def get_sample_names(self):
        """入力された試料名のリストを取得（空文字は除外）"""
        names = []
        for item in self.sample_inputs:
            text = item["input"].text().strip()
            if text:
                names.append(text)
        return names

    def set_sample_names(self, names):
        """試料名を設定"""
        # 既存の入力をクリア（最初の1つを残して削除し、値をクリア）
        while len(self.sample_inputs) > 1:
            self.remove_sample_input(self.sample_inputs[-1]["widget"])
        
        self.sample_inputs[0]["input"].setText("")
        
        if not names:
            return
            
        # 1つ目は既存のフィールドにセット
        if len(names) > 0:
            self.sample_inputs[0]["input"].setText(names[0])
            
        # 2つ目以降は追加
        for name in names[1:]:
            self.add_sample_input(name)
