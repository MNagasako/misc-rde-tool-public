"""
タクソノミービルダーダイアログ

正しい書式でタクソノミーキーを設定するためのダイアログ
インボイススキーマに基づいて利用可能なカスタムキーを動的に取得
"""

import json
import os
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QTextEdit, QGroupBox, QCheckBox,
    QMessageBox, QScrollArea, QWidget, QSplitter
)
from qt_compat.core import Qt, Signal
from qt_compat.gui import QFont


class TaxonomyBuilderDialog(QDialog):
    """タクソノミーキー構築ダイアログ"""
    
    # タクソノミーキーが変更されたときのシグナル
    taxonomy_changed = Signal(str)
    
    def __init__(self, parent=None, current_taxonomy="", dataset_template_id=""):
        super().__init__(parent)
        self.current_taxonomy = current_taxonomy
        self.dataset_template_id = dataset_template_id
        self.selected_keys = []
        
        # 基本的なタクソノミーキー定義
        self.base_taxonomy_keys = {
            "basic_info": {
                "invoice.basic.data-name": "データ名",
                "invoice.basic.experiment-id": "実験ID", 
                "invoice.basic.date-submitted": "登録日",
                "invoice.basic.registered-by": "登録者",
                "invoice.basic.task-id": "課題番号"
            },
            "instrument_info": {
                "instrument.name": "装置名",
                "instrument.model": "装置型番",
                "instrument.organization": "所属機関"
            },
            "sample_info": {
                "sample.name": "試料名",
                "sample.composition": "化学式/組成式",
                "sample.lot-number": "ロット番号",
                "sample.preparation": "試料作製方法"
            },
            "auto_generated_info": {
                "auto.registered-at": "登録日時",
                "auto.updated-at": "最終更新日時",
                "auto.file-extension": "ファイル拡張子"
            }
        }
        
        # カスタムキーは動的に読み込み
        self.custom_keys = {}
        self.load_custom_keys_from_schema()
        
        self.init_ui()
        self.parse_current_taxonomy()
    
    def load_custom_keys_from_schema(self):
        """インボイススキーマからカスタムキーを読み込み"""
        try:
            # インボイススキーマファイルのパスを構築
            from config.common import OUTPUT_DIR
            schema_dir = os.path.join(OUTPUT_DIR, "rde", "data", "invoiceSchemas")
            
            if not self.dataset_template_id:
                print("[WARNING] データセットテンプレートIDが指定されていません")
                self.set_default_custom_keys()
                return
            
            if not os.path.exists(schema_dir):
                print(f"[WARNING] スキーマディレクトリが見つかりません: {schema_dir}")
                self.set_default_custom_keys()
                return
                
            # テンプレートIDに基づいてスキーマファイルを特定
            schema_file_path = None
            template_id = self.dataset_template_id
            
            # テンプレートIDに対応するスキーマファイルを探す
            for file in os.listdir(schema_dir):
                if file.endswith('.json'):
                    # ファイル名からテンプレートIDを推測
                    # 例: ARIM-R6_TU-508_20241120.json -> ARIM-R6_TU-508_TEM-STEM_20241121
                    file_base = file.replace('.json', '')
                    if template_id.startswith(file_base) or file_base in template_id:
                        schema_file_path = os.path.join(schema_dir, file)
                        break
            
            # 完全一致を優先的に探す
            if not schema_file_path:
                for file in os.listdir(schema_dir):
                    if file.endswith('.json'):
                        if template_id in file or file.replace('.json', '') in template_id:
                            schema_file_path = os.path.join(schema_dir, file)
                            break
            
            # それでも見つからない場合は最初のファイルを使用
            if not schema_file_path:
                json_files = [f for f in os.listdir(schema_dir) if f.endswith('.json')]
                if json_files:
                    schema_file_path = os.path.join(schema_dir, json_files[0])
                    print(f"[WARNING] テンプレートID '{template_id}' に対応するスキーマが見つかりません。デフォルトを使用: {json_files[0]}")
            
            if schema_file_path:
                print(f"[DEBUG] インボイススキーマ読み込み: {schema_file_path}")
                
                with open(schema_file_path, 'r', encoding='utf-8') as f:
                    schema_data = json.load(f)
                
                print(f"[DEBUG] スキーマ全体構造:")
                print(f"[DEBUG] - スキーマID: {schema_data.get('$id', 'N/A')}")
                print(f"[DEBUG] - 説明: {schema_data.get('description', 'N/A')}")
                print(f"[DEBUG] - プロパティ: {list(schema_data.get('properties', {}).keys())}")
                
                # customプロパティからキーを抽出
                properties = schema_data.get('properties', {})
                custom_section = properties.get('custom', {})
                custom_props = custom_section.get('properties', {})
                
                print(f"[DEBUG] customセクション構造:")
                print(f"[DEBUG] - customセクション存在: {'custom' in properties}")
                print(f"[DEBUG] - customプロパティ数: {len(custom_props)}")
                print(f"[DEBUG] - customプロパティキー: {list(custom_props.keys())}")
                
                self.custom_keys = {}
                for key, prop in custom_props.items():
                    label_ja = prop.get('label', {}).get('ja', key)
                    label_en = prop.get('label', {}).get('en', key)
                    taxonomy_key = f"invoice.custom.{key}"
                    self.custom_keys[taxonomy_key] = f"{label_ja} ({label_en})" if label_en != key else label_ja
                    
                    # 詳細なプロパティ情報をログ出力
                    prop_type = prop.get('type', 'unknown')
                    enum_values = prop.get('enum', [])
                    print(f"[DEBUG]   {key}:")
                    print(f"[DEBUG]     - type: {prop_type}")
                    print(f"[DEBUG]     - label.ja: {label_ja}")
                    print(f"[DEBUG]     - label.en: {label_en}")
                    if enum_values:
                        print(f"[DEBUG]     - enum: {enum_values}")
                    
                print(f"[DEBUG] カスタムキー読み込み完了: {len(self.custom_keys)}件")
                
                # 最終的なタクソノミーキー一覧を表示
                print(f"[DEBUG] 生成されたタクソノミーキー:")
                for k, v in self.custom_keys.items():
                    print(f"[DEBUG] - {k}: {v}")
            else:
                print("[WARNING] 利用可能なスキーマファイルが見つかりません")
                self.set_default_custom_keys()
                    
        except Exception as e:
            print(f"[ERROR] インボイススキーマ読み込みエラー: {e}")
            self.set_default_custom_keys()
    
    def set_default_custom_keys(self):
        """デフォルトのカスタムキーを設定"""
        self.custom_keys = {
            # 提供されたスキーマ例に基づく標準的なTEMパラメータ
            "invoice.custom.electron_gun": "電子銃 (Electron Gun)",
            "invoice.custom.accelerating_voltage": "加速電圧 (Accelerating Voltage)",
            "invoice.custom.observation_method": "観察手法 (Observation Method)",
            
            # 従来のデフォルト項目も維持
            "invoice.custom.image-mode": "像モード（TEM/STEMなど）",
            "invoice.custom.stem-image-type": "STEM像種類（BF/DF/HAADFなど）",
            "invoice.custom.camera-length": "カメラ長",
            "invoice.custom.magnification": "倍率",
            "invoice.custom.pixel-size": "ピクセルサイズ",
            "invoice.custom.scan-size": "スキャンサイズ",
            "invoice.custom.dwell-time": "ドウェル時間",
            "invoice.custom.probe-current": "プローブ電流",
            "invoice.custom.convergence-angle": "収束角",
            "invoice.custom.collection-angle": "検出角",
            "invoice.custom.vacuum": "真空条件",
            "invoice.custom.stage-tilt": "試料傾斜角",
            "invoice.custom.temperature": "温度"
        }
    
    def init_ui(self):
        """UI初期化"""
        self.setWindowTitle("タクソノミーキー設定")
        self.setModal(True)
        self.resize(900, 700)
        
        layout = QVBoxLayout(self)
        
        # 説明ラベル
        info_label = QLabel(
            "タクソノミーキーを選択してください。\n"
            "選択したキーはスペース区切りで連結されます。\n"
            "例: sample.name invoice.custom.image-mode invoice.basic.data-name"
        )
        info_label.setStyleSheet(f"""
            background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)};
            padding: 10px;
            border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
        """)
        layout.addWidget(info_label)
        
        # メインスプリッター
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # 左側：キー選択エリア
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # キーカテゴリーごとのグループボックス
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # 基本情報
        self.create_category_group("基本情報", self.base_taxonomy_keys["basic_info"], scroll_layout)
        
        # 装置情報
        self.create_category_group("装置情報", self.base_taxonomy_keys["instrument_info"], scroll_layout)
        
        # 試料情報
        self.create_category_group("試料情報", self.base_taxonomy_keys["sample_info"], scroll_layout)
        
        # カスタム情報（インボイススキーマから動的読み込み）
        if self.custom_keys:
            self.create_category_group("測定情報（カスタム）", self.custom_keys, scroll_layout)
        
        # 自動生成情報
        self.create_category_group("自動生成情報", self.base_taxonomy_keys["auto_generated_info"], scroll_layout)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        left_layout.addWidget(scroll_area)
        
        splitter.addWidget(left_widget)
        
        # 右側：プレビューとコントロール
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 選択済みキー一覧
        selected_group = QGroupBox("選択済みキー")
        selected_layout = QVBoxLayout(selected_group)
        
        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(200)
        selected_layout.addWidget(self.selected_list)
        
        # 上へ/下へボタン
        list_control_layout = QHBoxLayout()
        up_button = QPushButton("↑ 上へ")
        down_button = QPushButton("↓ 下へ")
        remove_button = QPushButton("削除")
        
        up_button.clicked.connect(self.move_up)
        down_button.clicked.connect(self.move_down)
        remove_button.clicked.connect(self.remove_selected)
        
        list_control_layout.addWidget(up_button)
        list_control_layout.addWidget(down_button)
        list_control_layout.addWidget(remove_button)
        selected_layout.addLayout(list_control_layout)
        
        right_layout.addWidget(selected_group)
        
        # プレビュー
        preview_group = QGroupBox("タクソノミーキー プレビュー")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_text = QTextEdit()
        self.preview_text.setMaximumHeight(100)
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Consolas", 10))
        preview_layout.addWidget(self.preview_text)
        
        right_layout.addWidget(preview_group)
        
        splitter.addWidget(right_widget)
        
        # 分割比率を設定
        splitter.setSizes([600, 300])
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        clear_button = QPushButton("すべてクリア")
        clear_button.clicked.connect(self.clear_all)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(clear_button)
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.update_preview()
    
    def create_category_group(self, title, keys_dict, parent_layout):
        """カテゴリーグループボックスを作成"""
        group_box = QGroupBox(title)
        layout = QVBoxLayout(group_box)
        
        for key, description in keys_dict.items():
            checkbox = QCheckBox(f"{key}\n    → {description}")
            checkbox.setObjectName(key)  # キーを識別用に設定
            checkbox.stateChanged.connect(self.on_checkbox_changed)
            layout.addWidget(checkbox)
        
        parent_layout.addWidget(group_box)
    
    def on_checkbox_changed(self, state):
        """チェックボックス状態変更"""
        sender = self.sender()
        key = sender.objectName()
        
        # PySide6のstateChangedシグナルは整数値を渡す（Checked=2, Unchecked=0）
        if state == 2:  # Qt.CheckState.Checked.value
            if key not in self.selected_keys:
                self.selected_keys.append(key)
                # リストウィジェットにも追加
                item = QListWidgetItem(key)
                self.selected_list.addItem(item)
        else:
            if key in self.selected_keys:
                self.selected_keys.remove(key)
                # リストウィジェットからも削除
                for i in range(self.selected_list.count()):
                    item = self.selected_list.item(i)
                    if item.text() == key:
                        self.selected_list.takeItem(i)
                        break
        
        self.update_preview()
    
    def move_up(self):
        """選択項目を上に移動"""
        current_row = self.selected_list.currentRow()
        if current_row > 0:
            # リストの順序を変更
            item = self.selected_list.takeItem(current_row)
            self.selected_list.insertItem(current_row - 1, item)
            self.selected_list.setCurrentRow(current_row - 1)
            
            # selected_keysの順序も変更
            key = self.selected_keys.pop(current_row)
            self.selected_keys.insert(current_row - 1, key)
            
            self.update_preview()
    
    def move_down(self):
        """選択項目を下に移動"""
        current_row = self.selected_list.currentRow()
        if current_row < self.selected_list.count() - 1:
            # リストの順序を変更
            item = self.selected_list.takeItem(current_row)
            self.selected_list.insertItem(current_row + 1, item)
            self.selected_list.setCurrentRow(current_row + 1)
            
            # selected_keysの順序も変更
            key = self.selected_keys.pop(current_row)
            self.selected_keys.insert(current_row + 1, key)
            
            self.update_preview()
    
    def remove_selected(self):
        """選択項目を削除"""
        current_row = self.selected_list.currentRow()
        if current_row >= 0:
            item = self.selected_list.takeItem(current_row)
            key = item.text()
            
            # selected_keysからも削除
            if key in self.selected_keys:
                self.selected_keys.remove(key)
            
            # チェックボックスも解除
            checkbox = self.findChild(QCheckBox, key)
            if checkbox:
                checkbox.setChecked(False)
            
            self.update_preview()
    
    def clear_all(self):
        """すべてクリア"""
        # すべてのチェックボックスを解除
        for checkbox in self.findChildren(QCheckBox):
            checkbox.setChecked(False)
        
        # リストとキーをクリア
        self.selected_list.clear()
        self.selected_keys.clear()
        self.update_preview()
    
    def parse_current_taxonomy(self):
        """現在のタクソノミー文字列を解析してチェックボックスを設定"""
        if not self.current_taxonomy:
            return
        
        keys = self.current_taxonomy.strip().split()
        for key in keys:
            if key:
                checkbox = self.findChild(QCheckBox, key)
                if checkbox:
                    checkbox.setChecked(True)
                # selected_keysとリストにも追加（on_checkbox_changedで処理される）
    
    def update_preview(self):
        """プレビュー更新"""
        taxonomy_string = " ".join(self.selected_keys)
        self.preview_text.setText(taxonomy_string)
    
    def get_taxonomy_string(self):
        """構築されたタクソノミー文字列を取得"""
        return " ".join(self.selected_keys)
    
    def accept(self):
        """OK ボタン押下時"""
        taxonomy_string = self.get_taxonomy_string()
        self.taxonomy_changed.emit(taxonomy_string)
        super().accept()
