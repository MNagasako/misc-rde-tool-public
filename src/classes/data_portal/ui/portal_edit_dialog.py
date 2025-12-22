"""
データポータル修正ダイアログ

データポータルに登録済みのエントリを修正するためのダイアログ
"""

import logging
from typing import Dict, Any, Optional
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit, QPushButton,
    QGroupBox, QMessageBox, QProgressDialog, QApplication, QScrollArea, QWidget, QCheckBox, QRadioButton, QButtonGroup, QListWidget, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from qt_compat.core import Qt
from qt_compat import get_screen_geometry

from classes.theme import get_color, ThemeKey

from classes.managers.log_manager import get_logger
from classes.data_portal.ui.widgets import FilterableCheckboxTable
from classes.dataset.util.data_entry_summary import (
    get_data_entry_summary,
    format_size_with_bytes,
)
from classes.dataset.core.dataset_dataentry_logic import fetch_dataset_dataentry
from core.bearer_token_manager import BearerTokenManager

logger = get_logger("DataPortal.PortalEditDialog")


class PortalEditDialog(QDialog):
    """データポータル修正ダイアログ"""
    
    def __init__(self, form_data: Dict[str, Any], t_code: str, dataset_id: str, portal_client, parent=None, metadata: Optional[Dict[str, Any]] = None):
        """
        初期化
        
        Args:
            form_data: フォームデータ（_parse_edit_formの戻り値）
            t_code: テーマコード
            dataset_id: データセットID
            portal_client: PortalClientインスタンス
            parent: 親ウィジェット
            metadata: メタデータ（選択肢情報）
        """
        super().__init__(parent)
        
        self.form_data = form_data
        self.t_code = t_code
        self.dataset_id = dataset_id
        self.portal_client = portal_client
        self.metadata = metadata or {}
        self.field_widgets = {}
        self.file_stats_auto_button = None
        
        self.setWindowTitle(f"データポータル修正 - {dataset_id[:8]}...")
        self.setMinimumWidth(800)
        
        # 初期ウィンドウ高さを画面高さ - 100px に設定
        screen_rect = get_screen_geometry(self)
        initial_height = max(600, screen_rect.height() - 100)  # 最低600pxを保証
        self.resize(800, initial_height)
        
        self._init_ui()
        logger.info(f"修正ダイアログ初期化: t_code={t_code}, dataset_id={dataset_id}, metadata={len(self.metadata)}項目")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        
        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # 主要項目グループ
        main_group = self._create_main_fields_group()
        scroll_layout.addWidget(main_group)
        
        # その他の項目グループ
        other_group = self._create_other_fields_group()
        scroll_layout.addWidget(other_group)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
    
    def _create_main_fields_group(self) -> QGroupBox:
        """主要項目グループを作成"""
        group = QGroupBox("主要項目")
        layout = QFormLayout()
        
        # 機関 (t_mi_code)
        if 't_mi_code' in self.form_data and self.form_data['t_mi_code']['type'] == 'select':
            field_data = self.form_data['t_mi_code']
            combo = QComboBox()
            combo.setMaximumWidth(600)  # 最大幅を設定
            for opt in field_data['options']:
                combo.addItem(opt['text'], opt['value'])
                if opt['selected']:
                    combo.setCurrentText(opt['text'])
            self.field_widgets['t_mi_code'] = combo
            layout.addRow("機関:", combo)
        
        # ライセンスレベル (t_license_level)
        if 't_license_level' in self.form_data and self.form_data['t_license_level']['type'] == 'select':
            field_data = self.form_data['t_license_level']
            combo = QComboBox()
            combo.setMaximumWidth(600)  # 最大幅を設定
            for opt in field_data['options']:
                combo.addItem(opt['text'], opt['value'])
                if opt['selected']:
                    combo.setCurrentText(opt['text'])
            self.field_widgets['t_license_level'] = combo
            layout.addRow("ライセンスレベル:", combo)
        
        # 重要技術領域（主） (t_a_code)
        if 't_a_code' in self.form_data and self.form_data['t_a_code']['type'] == 'select':
            field_data = self.form_data['t_a_code']
            combo = QComboBox()
            for opt in field_data['options']:
                combo.addItem(opt['text'], opt['value'])
                if opt['selected']:
                    combo.setCurrentText(opt['text'])
            self.field_widgets['t_a_code'] = combo
            layout.addRow("重要技術領域（主）:", combo)
        
        # 重要技術領域（副） - 複数ある場合があるため動的に追加
        for key in self.form_data.keys():
            if key.startswith('t_a_sub_code'):
                field_data = self.form_data[key]
                if field_data['type'] == 'select':
                    combo = QComboBox()
                    for opt in field_data['options']:
                        combo.addItem(opt['text'], opt['value'])
                        if opt['selected']:
                            combo.setCurrentText(opt['text'])
                    self.field_widgets[key] = combo
                    label = field_data.get('label', key)
                    layout.addRow(f"{label}:", combo)
        
        group.setLayout(layout)
        return group
    
    def _create_editable_list_table(self, field_prefix: str, label: str, max_rows: int = 20, visible_rows: int = 5):
        """
        編集可能なリストテーブルを作成（装置・プロセス、論文・プロシーディング用）
        常に20行表示、5行以上はスクロールバーで表示
        
        Args:
            field_prefix: フィールドのプレフィックス（例: 't_equip_process', 't_paper_proceed'）
            label: ラベル
            max_rows: 固定行数（常に20）
            visible_rows: スクロールなしで表示する行数（デフォルト5）
        
        Returns:
            QTableWidget: テーブルウィジェット
        """
        table = QTableWidget()
        table.setColumnCount(1)
        table.setHorizontalHeaderLabels([label])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        # 常に20行表示
        table.setRowCount(20)
        
        # 既存データを読み込み
        for i in range(1, 21):
            field_name = f"{field_prefix}{i}"
            value = ""
            if field_name in self.form_data:
                value = self.form_data[field_name].get('value', '')
            
            item = QTableWidgetItem(value)
            table.setItem(i - 1, 0, item)
        
        # 行の高さを設定
        table.verticalHeader().setDefaultSectionSize(25)
        
        # 5行分の表示高さに固定（それ以上はスクロール）
        table_height = visible_rows * 25 + table.horizontalHeader().height() + 2
        table.setMaximumHeight(table_height)
        table.setMinimumHeight(table_height)
        
        return table
    
    def _create_checkbox_group(self, field_name: str, label: str, max_selections: int = None) -> QWidget:
        """
        チェックボックスグループを作成
        
        Args:
            field_name: フィールド名（例: 't_a_code[]'）
            label: グループラベル
            max_selections: 最大選択数（Noneの場合は無制限）
        
        Returns:
            QWidget: チェックボックスグループウィジェット
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # メタデータから選択肢を取得
        if field_name not in self.metadata:
            logger.warning(f"メタデータに {field_name} が見つかりません")
            return container
        
        meta = self.metadata[field_name]
        
        # 現在の選択値を取得
        selected_values = []
        if field_name in self.form_data:
            field_data = self.form_data[field_name]
            if field_data['type'] == 'checkbox_array':
                selected_values = [v['value'] for v in field_data['values'] if v.get('checked', False)]
        
        # チェックボックスを作成
        checkboxes = []
        for opt in meta['options']:
            checkbox = QCheckBox(opt['label'] or opt['value'])
            checkbox.setProperty('value', opt['value'])
            if opt['value'] in selected_values:
                checkbox.setChecked(True)
            
            # 最大選択数の制限
            if max_selections is not None:
                checkbox.toggled.connect(lambda checked, cb=checkbox: self._on_checkbox_toggled(cb, checkboxes, max_selections))
            
            checkboxes.append(checkbox)
            layout.addWidget(checkbox)
        
        # ウィジェット辞書に保存
        self.field_widgets[field_name] = checkboxes
        
        return container
    
    def _on_checkbox_toggled(self, checkbox: 'QCheckBox', all_checkboxes: list, max_selections: int):
        """
        チェックボックストグル時の処理（最大選択数制限）
        
        Args:
            checkbox: トグルされたチェックボックス
            all_checkboxes: 全チェックボックスのリスト
            max_selections: 最大選択数
        """
        if not checkbox.isChecked():
            return
        
        # 選択されているチェックボックス数をカウント
        checked_count = sum(1 for cb in all_checkboxes if cb.isChecked())
        
        if checked_count > max_selections:
            # 最大選択数を超えた場合、このチェックボックスの選択を解除
            checkbox.setChecked(False)
            QMessageBox.warning(
                self,
                "選択数エラー",
                f"最大{max_selections}個まで選択できます。"
            )
    
    def _create_other_fields_group(self) -> QGroupBox:
        """その他の項目グループを作成"""
        group = QGroupBox("その他の項目")
        layout = QFormLayout()
        
        # 主要項目以外のフィールドを追加
        main_fields = {'t_mi_code', 't_license_level', 't_a_code', 't_code', 'mode', 'mode2', 'mode3', 'keyword', 'search_inst', 'search_license_level', 'search_status', 'page'}
        
        # ライセンス (t_license) - ドロップダウン
        if 't_license' in self.metadata:
            combo = QComboBox()
            combo.setMaximumWidth(400)
            current_value = self.form_data.get('t_license', {}).get('value', '')
            
            for opt in self.metadata['t_license']['options']:
                combo.addItem(opt['label'] or opt['value'], opt['value'])
                if opt['value'] == current_value:
                    combo.setCurrentText(opt['label'] or opt['value'])
            
            self.field_widgets['t_license'] = combo
            layout.addRow("ライセンス:", combo)
        
        # 重要技術領域（主） (main_mita_code_array[]) - ドロップダウン（複数選択不可）
        if 'main_mita_code_array[]' in self.metadata:
            combo = QComboBox()
            combo.setMaximumWidth(400)
            combo.addItem("（選択なし）", "")
            
            # 既存の選択値を取得
            selected_values = []
            if 'main_mita_code_array[]' in self.form_data and self.form_data['main_mita_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['main_mita_code_array[]']['values'] if item['checked']]
            
            for opt in self.metadata['main_mita_code_array[]']['options']:
                combo.addItem(opt['label'], opt['value'])
                if opt['value'] in selected_values:
                    combo.setCurrentText(opt['label'])
            
            self.field_widgets['main_mita_code_array[]'] = combo
            layout.addRow("重要技術領域（主）:", combo)
        
        # 重要技術領域（副） (sub_mita_code_array[]) - ドロップダウン（複数選択不可）
        if 'sub_mita_code_array[]' in self.metadata:
            combo = QComboBox()
            combo.setMaximumWidth(400)
            combo.addItem("（選択なし）", "")
            
            # 既存の選択値を取得
            selected_values = []
            if 'sub_mita_code_array[]' in self.form_data and self.form_data['sub_mita_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['sub_mita_code_array[]']['values'] if item['checked']]
            
            for opt in self.metadata['sub_mita_code_array[]']['options']:
                combo.addItem(opt['label'], opt['value'])
                if opt['value'] in selected_values:
                    combo.setCurrentText(opt['label'])
            
            self.field_widgets['sub_mita_code_array[]'] = combo
            layout.addRow("重要技術領域（副）:", combo)
        
        # 重要技術領域（主・副）自動設定ボタン
        if 'main_mita_code_array[]' in self.metadata or 'sub_mita_code_array[]' in self.metadata:
            auto_tech_btn = QPushButton("🤖 重要技術領域 自動設定")
            auto_tech_btn.clicked.connect(self._on_auto_set_important_tech_areas)
            auto_tech_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_tech_btn.setToolTip("報告書またはAIから重要技術領域を自動設定します")
            layout.addRow("", auto_tech_btn)
        
        # 横断技術領域 (mcta_code_array[]) - チェックボックスグループ（複数選択可）
        if 'mcta_code_array[]' in self.metadata:
            container = QWidget()
            layout_mcta = QVBoxLayout(container)
            layout_mcta.setContentsMargins(0, 0, 0, 0)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMaximumHeight(120)
            scroll.setMinimumHeight(120)
            
            scroll_content = QWidget()
            scroll_layout = QVBoxLayout(scroll_content)
            scroll_layout.setContentsMargins(5, 5, 5, 5)
            
            # 既存の選択値を取得
            selected_values = []
            if 'mcta_code_array[]' in self.form_data and self.form_data['mcta_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mcta_code_array[]']['values'] if item['checked']]
            
            checkboxes = []
            for opt in self.metadata['mcta_code_array[]']['options']:
                checkbox = QCheckBox(opt['label'])
                checkbox.setProperty('value', opt['value'])
                if opt['value'] in selected_values:
                    checkbox.setChecked(True)
                checkboxes.append(checkbox)
                scroll_layout.addWidget(checkbox)
            
            scroll_layout.addStretch()
            scroll.setWidget(scroll_content)
            layout_mcta.addWidget(scroll)
            
            self.field_widgets['mcta_code_array[]'] = checkboxes
            layout.addRow("横断技術領域:", container)
        
        # 横断技術領域 自動設定ボタン
        if 'mcta_code_array[]' in self.metadata:
            auto_cross_tech_btn = QPushButton("🤖 横断技術領域 自動設定")
            auto_cross_tech_btn.clicked.connect(self._on_auto_set_cross_tech_areas)
            auto_cross_tech_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_cross_tech_btn.setToolTip("報告書から横断技術領域を自動設定します")
            layout.addRow("", auto_cross_tech_btn)
        
        # 設備分類 (mec_code_array[]) - フィルタ可能チェックボックステーブル
        if 'mec_code_array[]' in self.metadata:
            options = self.metadata['mec_code_array[]']['options']
            # 既存のform_dataから選択済み値を取得
            selected_values = []
            if 'mec_code_array[]' in self.form_data and self.form_data['mec_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mec_code_array[]']['values'] if item['checked']]
            
            table_widget = FilterableCheckboxTable(
                field_name='mec_code_array[]',
                label='設備分類',
                options=options,
                selected_values=selected_values,
                max_height=150  # 5行分の高さ
            )
            self.field_widgets['mec_code_array[]'] = table_widget
            layout.addRow("設備分類:", table_widget)

            # 自動設定（設備分類）
            auto_btn = QPushButton("🤖 設備分類 自動設定")
            auto_btn.setToolTip("専用ダイアログでAI提案を確認・適用します")
            auto_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_btn.clicked.connect(lambda: self._open_checkbox_autoset_dialog('設備分類 自動設定', 'mec_code_array[]', 'equipment'))
            layout.addRow("", auto_btn)
        
        # マテリアルインデックス (mmi_code_array[]) - フィルタ可能チェックボックステーブル
        if 'mmi_code_array[]' in self.metadata:
            options = self.metadata['mmi_code_array[]']['options']
            # 既存のform_dataから選択済み値を取得
            selected_values = []
            if 'mmi_code_array[]' in self.form_data and self.form_data['mmi_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mmi_code_array[]']['values'] if item['checked']]
            
            table_widget = FilterableCheckboxTable(
                field_name='mmi_code_array[]',
                label='マテリアルインデックス',
                options=options,
                selected_values=selected_values,
                max_height=150  # 5行分の高さ
            )
            self.field_widgets['mmi_code_array[]'] = table_widget
            layout.addRow("マテリアルインデックス:", table_widget)

            auto_btn = QPushButton("🤖 マテリアルインデックス 自動設定")
            auto_btn.setToolTip("専用ダイアログでAI提案を確認・適用します")
            auto_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_btn.clicked.connect(lambda: self._open_checkbox_autoset_dialog('マテリアルインデックス 自動設定', 'mmi_code_array[]', 'material_index'))
            layout.addRow("", auto_btn)
        
        # タグ (mt_code_array[]) - フィルタ可能チェックボックステーブル
        if 'mt_code_array[]' in self.metadata:
            options = self.metadata['mt_code_array[]']['options']
            # 既存のform_dataから選択済み値を取得
            selected_values = []
            if 'mt_code_array[]' in self.form_data and self.form_data['mt_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mt_code_array[]']['values'] if item['checked']]
            
            table_widget = FilterableCheckboxTable(
                field_name='mt_code_array[]',
                label='タグ',
                options=options,
                selected_values=selected_values,
                max_height=150  # 5行分の高さ
            )
            self.field_widgets['mt_code_array[]'] = table_widget
            layout.addRow("タグ:", table_widget)

            auto_btn = QPushButton("🤖 タグ 自動設定")
            auto_btn.setToolTip("専用ダイアログでAI提案を確認・適用します")
            auto_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_btn.clicked.connect(lambda: self._open_checkbox_autoset_dialog('タグ 自動設定', 'mt_code_array[]', 'tag'))
            layout.addRow("", auto_btn)
        
        # 装置・プロセス - テーブル表示（20行固定、5行以上はスクロール）
        equip_process_table = self._create_editable_list_table('t_equip_process', '装置・プロセス', max_rows=20, visible_rows=5)
        self.field_widgets['t_equip_process'] = equip_process_table
        layout.addRow("装置・プロセス:", equip_process_table)
        
        # 装置・プロセス 自動設定ボタン
        auto_equipment_btn = QPushButton("🤖 装置・プロセス 自動設定")
        auto_equipment_btn.clicked.connect(self._on_auto_set_equipment)
        auto_equipment_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
        """)
        auto_equipment_btn.setToolTip("報告書から利用した主な設備を自動設定します")
        layout.addRow("", auto_equipment_btn)
        
        # 論文・プロシーディング - テーブル表示（20行固定、5行以上はスクロール）
        paper_proceed_table = self._create_editable_list_table('t_paper_proceed', '論文・プロシーディング（DOI URL）', max_rows=20, visible_rows=5)
        self.field_widgets['t_paper_proceed'] = paper_proceed_table
        layout.addRow("論文・プロシーディング:", paper_proceed_table)
        
        # 論文・プロシーディング 自動設定ボタン（将来復活する可能性あり、現在は非表示）
        # auto_publications_btn = QPushButton("🤖 論文・プロシーディング 自動設定")
        # auto_publications_btn.clicked.connect(self._on_auto_set_publications)
        # auto_publications_btn.setStyleSheet(f"""
        #     QPushButton {{
        #         background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
        #         color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
        #         padding: 6px 12px;
        #         border: none;
        #         border-radius: 4px;
        #         font-weight: bold;
        #     }}
        #     QPushButton:hover {{
        #         background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
        #     }}
        # """)
        # auto_publications_btn.setToolTip("報告書から論文・プロシーディング（DOI）を自動設定します")
        # layout.addRow("", auto_publications_btn)
        
        # その他のフィールド
        for key, field_data in self.form_data.items():
            # 主要項目と非表示フィールドはスキップ
            if key in main_fields or key.startswith('t_a_sub_code') or field_data['type'] == 'hidden':
                continue
            
            # 上記で処理済みのフィールドをスキップ
            if key in ['t_license', 'main_mita_code_array[]', 'sub_mita_code_array[]', 'mcta_code_array[]', 't_eqp_code_array[]', 'mi_code_array[]', 'tag_code_array[]']:
                continue
            
            # 装置・プロセスと論文・プロシーディングのフィールドもスキップ
            if key.startswith('t_equip_process') or key.startswith('t_paper_proceed'):
                continue
            
            label = field_data.get('label', key)
            
            if field_data['type'] == 'select':
                combo = QComboBox()
                for opt in field_data['options']:
                    combo.addItem(opt['text'], opt['value'])
                    if opt['selected']:
                        combo.setCurrentText(opt['text'])
                self.field_widgets[key] = combo
                layout.addRow(f"{label}:", combo)
            
            elif field_data['type'] in ['text', 'number', 'datetime-local', 'date', 'time']:
                line_edit = QLineEdit(field_data['value'])
                self.field_widgets[key] = line_edit
                layout.addRow(f"{label}:", line_edit)
            
            elif field_data['type'] == 'textarea':
                text_edit = QTextEdit()
                text_edit.setPlainText(field_data['value'])
                text_edit.setMaximumHeight(100)
                self.field_widgets[key] = text_edit
                layout.addRow(f"{label}:", text_edit)
            
            # その他のチェックボックス配列（既に上記で処理済み）
            elif field_data['type'] == 'checkbox_array':
                continue

        # ファイル数 / 全ファイルサイズ 自動設定ボタン
        file_count_widget = self.field_widgets.get('t_file_count')
        filesize_widget = self.field_widgets.get('t_meta_totalfilesize') or self.field_widgets.get('t_meta_totalfilesizeinthisversion')
        if file_count_widget and filesize_widget:
            auto_file_stats_btn = QPushButton("🤖 ファイル数/サイズ 自動設定")
            auto_file_stats_btn.clicked.connect(self._on_auto_set_file_stats)
            auto_file_stats_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_file_stats_btn.setToolTip("データエントリー情報から総計（全ファイル）の統計を推定し、ファイル数と全ファイルサイズを更新します")
            layout.addRow("", auto_file_stats_btn)
            self.file_stats_auto_button = auto_file_stats_btn
        
        group.setLayout(layout)
        return group
    
    def _on_save(self):
        """保存処理（2段階: conf→rec）"""
        try:
            # 確認ダイアログ
            reply = QMessageBox.question(
                self,
                "修正確認",
                "データポータルのエントリを修正しますか?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("修正中...", None, 0, 2, self)
            progress.setWindowTitle("データポータル修正")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setCancelButton(None)
            progress.setValue(0)
            QApplication.processEvents()
            
            # Step 1: 確認画面へ (mode3=conf)
            logger.info("[SAVE-STEP1] 確認画面へのPOST開始")
            progress.setLabelText("確認画面へ送信中...")
            QApplication.processEvents()
            
            conf_data = self._collect_form_data('conf')
            logger.info(f"[SAVE-STEP1] 送信データ: {len(conf_data)} fields")
            
            success, response = self.portal_client.post("main.php", data=conf_data)
            
            if not success:
                progress.close()
                logger.error(f"[SAVE-STEP1] 確認画面POST失敗: {response}")
                QMessageBox.critical(self, "エラー", f"確認画面への送信に失敗\n{response}")
                return
            
            # デバッグ保存
            if hasattr(response, 'text'):
                self._save_debug_response("edit_conf", response.text)
            
            logger.info("[SAVE-STEP1] 確認画面POST成功")
            
            # confレスポンスからhiddenフィールドを抽出
            conf_hidden_fields = self._parse_conf_response(response.text)
            logger.info(f"[SAVE-STEP1] 確認画面から抽出したフィールド数: {len(conf_hidden_fields)}")
            
            progress.setValue(1)
            
            # Step 2: 確定登録 (mode3=rec)
            logger.info("[SAVE-STEP2] 確定登録POST開始")
            progress.setLabelText("確定登録中...")
            QApplication.processEvents()
            
            # confレスポンスのhiddenフィールドを使用してrecデータを作成
            rec_data = {
                'mode': 'theme',
                'mode2': 'change',
                'mode3': 'rec',
                't_code': self.t_code,
                'keyword': self.dataset_id,
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            rec_data.update(conf_hidden_fields)
            logger.info(f"[SAVE-STEP2] 送信データ: {len(rec_data)} fields")
            
            success, response = self.portal_client.post("main.php", data=rec_data)
            
            progress.setValue(2)
            progress.close()
            
            if success:
                # デバッグ保存
                if hasattr(response, 'text'):
                    self._save_debug_response("edit_rec", response.text)
                
                logger.info("[SAVE-STEP2] 確定登録成功")
                QMessageBox.information(self, "成功", "データポータルの修正が完了しました")
                self.accept()
            else:
                logger.error(f"[SAVE-STEP2] 確定登録失敗: {response}")
                QMessageBox.critical(self, "エラー", f"確定登録に失敗\n{response}")
                
        except Exception as e:
            logger.error(f"保存エラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"保存エラー\n{e}")
    
    def _collect_form_data(self, mode3: str) -> dict:
        """フォームデータ収集"""
        post_data = {
            'mode': 'theme',
            'mode2': 'change',
            'mode3': mode3,
            't_code': self.t_code,
            'keyword': self.dataset_id,
            'search_inst': '',
            'search_license_level': '',
            'search_status': '',
            'page': '1'
        }
        
        # 非表示フィールドとチェックボックス配列
        for key, field_data in self.form_data.items():
            if field_data['type'] == 'hidden':
                post_data[key] = field_data['value']
            elif field_data['type'] == 'checkbox_array':
                # チェックされている値のみを配列として送信
                checked_values = [item['value'] for item in field_data['values'] if item['checked']]
                if checked_values:
                    post_data[key] = checked_values
        
        # 編集可能フィールド
        for key, widget in self.field_widgets.items():
            if isinstance(widget, FilterableCheckboxTable):
                # FilterableCheckboxTableからデータ取得
                checked = widget.get_selected_values()
                if checked:
                    post_data[key] = checked
                # 空の場合も空配列として送信（フォームクリア用）
                elif key in ['mmi_code_array[]', 'mt_code_array[]', 'mec_code_array[]']:
                    post_data[key] = []
            elif key in ['t_equip_process', 't_paper_proceed']:
                # QTableWidget（装置・プロセス、論文・プロシーディング）
                # サーバー側は20件固定を期待しているため、常に20件分送信
                if isinstance(widget, QTableWidget):
                    # テーブルから値を取得（圧縮されている可能性があるため実際の行数のみ）
                    values = []
                    for row in range(widget.rowCount()):
                        item = widget.item(row, 0)
                        if item and item.text().strip():
                            values.append(item.text().strip())
                    
                    # 20件固定で送信（不足分は空文字列）
                    for i in range(1, 21):
                        field_name = f"{key}{i}"
                        if i - 1 < len(values):
                            post_data[field_name] = values[i - 1]
                        else:
                            post_data[field_name] = ""
            elif isinstance(widget, QComboBox):
                value = widget.currentData()
                if value is not None and value != "":  # 空文字列は送信しない
                    # 配列フィールド（[]付き）の場合はリストとして送信
                    if key.endswith('[]'):
                        post_data[key] = [value]
                    else:
                        post_data[key] = value
            elif isinstance(widget, QLineEdit):
                post_data[key] = widget.text()
            elif isinstance(widget, QTextEdit):
                post_data[key] = widget.toPlainText()
            elif isinstance(widget, QButtonGroup):
                # ラジオボタングループ
                checked_button = widget.checkedButton()
                if checked_button:
                    post_data[key] = checked_button.property('value')
            elif isinstance(widget, list):
                # チェックボックスリスト（横断技術領域など）
                checked = []
                for cb in widget:
                    if cb.isChecked():
                        checked.append(cb.property('value'))
                if checked:
                    post_data[key] = checked
        
        return post_data
    
    def _parse_conf_response(self, html: str) -> dict:
        """
        確認画面のレスポンスからhiddenフィールドを抽出
        
        Args:
            html: 確認画面のHTML
        
        Returns:
            dict: hiddenフィールドのkey-valueマップ
        """
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html, 'html.parser')
            hidden_fields = {}
            
            # 全てのhidden inputを取得
            for hidden_input in soup.find_all('input', {'type': 'hidden'}):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                
                if name and name not in ['mode', 'mode2', 'mode3', 't_code', 'keyword', 'search_inst', 'search_license_level', 'search_status', 'page']:
                    # 配列フィールド（名前に[]が含まれる）の処理
                    if '[]' in name:
                        if name not in hidden_fields:
                            hidden_fields[name] = []
                        hidden_fields[name].append(value)
                    else:
                        hidden_fields[name] = value
            
            logger.info(f"[PARSE_CONF] 抽出したフィールド: {list(hidden_fields.keys())}")
            return hidden_fields
            
        except Exception as e:
            logger.error(f"[PARSE_CONF] 確認画面解析エラー: {e}", exc_info=True)
            return {}
    
    def _save_debug_response(self, step: str, html: str):
        """デバッグレスポンス保存"""
        try:
            from datetime import datetime
            from config.common import get_dynamic_file_path
            import os
            
            debug_dir = get_dynamic_file_path("output/data_portal_debug/edit")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{step}_{self.dataset_id}_{timestamp}.html"
            filepath = os.path.join(debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            logger.info(f"[DEBUG] 保存: {filepath}")
        except Exception as e:
            logger.warning(f"デバッグ保存失敗: {e}")
    
    def _on_auto_set_important_tech_areas(self):
        """重要技術領域（主・副）を自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_important_tech_areas_from_report,
                suggest_important_tech_areas_with_ai,
                get_grant_number_from_dataset_json
            )
            from .auto_setting_dialog import AutoSettingDialog
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # 報告書ベースの候補取得関数
            def fetch_from_report(dataset_id: str) -> dict:
                return extract_important_tech_areas_from_report(dataset_id, grant_number)
            
            # AIベースの候補取得関数
            def fetch_from_ai(dataset_id: str) -> dict:
                return suggest_important_tech_areas_with_ai(dataset_id)
            
            # 自動設定ダイアログを表示
            dialog = AutoSettingDialog(
                title="重要技術領域 自動設定",
                field_name="重要技術領域（主・副）",
                dataset_id=self.dataset_id,
                report_fetcher=fetch_from_report,
                ai_fetcher=fetch_from_ai,
                metadata=self.metadata,
                parent=self
            )
            
            if dialog.exec_() == QDialog.Accepted:
                result = dialog.get_result()
                
                if result:
                    # 主を設定
                    if "main" in result and result["main"]:
                        main_combo = self.field_widgets.get('main_mita_code_array[]')
                        if main_combo and isinstance(main_combo, QComboBox):
                            # メタデータから対応するvalueを検索
                            main_value = self._find_metadata_value('main_mita_code_array[]', result["main"])
                            if main_value:
                                index = main_combo.findData(main_value)
                                if index >= 0:
                                    main_combo.setCurrentIndex(index)
                                    logger.info(f"重要技術領域（主）設定: {result['main']}")
                                else:
                                    # valueで見つからない場合、テキストで検索
                                    index = main_combo.findText(result["main"])
                                    if index >= 0:
                                        main_combo.setCurrentIndex(index)
                                        logger.info(f"重要技術領域（主）設定（テキスト一致）: {result['main']}")
                    
                    # 副を設定
                    if "sub" in result and result["sub"]:
                        sub_combo = self.field_widgets.get('sub_mita_code_array[]')
                        if sub_combo and isinstance(sub_combo, QComboBox):
                            # メタデータから対応するvalueを検索
                            sub_value = self._find_metadata_value('sub_mita_code_array[]', result["sub"])
                            if sub_value:
                                index = sub_combo.findData(sub_value)
                                if index >= 0:
                                    sub_combo.setCurrentIndex(index)
                                    logger.info(f"重要技術領域（副）設定: {result['sub']}")
                                else:
                                    # valueで見つからない場合、テキストで検索
                                    index = sub_combo.findText(result["sub"])
                                    if index >= 0:
                                        sub_combo.setCurrentIndex(index)
                                        logger.info(f"重要技術領域（副）設定（テキスト一致）: {result['sub']}")
                    
                    QMessageBox.information(
                        self,
                        "完了",
                        f"重要技術領域を設定しました。\n\n主: {result.get('main', '(なし)')}\n副: {result.get('sub', '(なし)')}"
                    )
        
        except Exception as e:
            logger.error(f"重要技術領域自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _find_metadata_value(self, field_name: str, label_or_value: str) -> Optional[str]:
        """
        メタデータからラベルまたは値に対応するvalueを検索
        
        Args:
            field_name: フィールド名（例: 'main_mita_code_array[]'）
            label_or_value: 検索するラベルまたは値
        
        Returns:
            Optional[str]: 対応するvalue（見つからない場合はNone）
        """
        if field_name not in self.metadata:
            return None
        
        for opt in self.metadata[field_name].get("options", []):
            if opt.get("value") == label_or_value or opt.get("label") == label_or_value:
                return opt.get("value")
        
        return None

    def _on_auto_set_cross_tech_areas(self):
        """横断技術領域を自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_cross_tech_areas_from_report,
                get_grant_number_from_dataset_json
            )
            from .auto_setting_dialog import AutoSettingDialog
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # 報告書ベースの候補取得関数
            def fetch_from_report(dataset_id: str) -> dict:
                return extract_cross_tech_areas_from_report(dataset_id, grant_number)
            
            # 自動設定ダイアログを表示
            dialog = AutoSettingDialog(
                title="横断技術領域 自動設定",
                field_name="横断技術領域（主・副）",
                dataset_id=self.dataset_id,
                report_fetcher=fetch_from_report,
                ai_fetcher=None,  # AI推定は未対応
                metadata=self.metadata,
                parent=self
            )
            
            if dialog.exec_() == QDialog.Accepted:
                result = dialog.get_result()
                
                if result:
                    # 横断技術領域はチェックボックスリスト
                    checkboxes = self.field_widgets.get('mcta_code_array[]', [])
                    
                    if checkboxes:
                        # まず全てのチェックを外す
                        for cb in checkboxes:
                            cb.setChecked(False)
                        
                        # 主を設定
                        if "main" in result and result["main"]:
                            for cb in checkboxes:
                                if result["main"] in cb.text():
                                    cb.setChecked(True)
                                    logger.info(f"横断技術領域（主）設定: {result['main']}")
                                    break
                        
                        # 副を設定
                        if "sub" in result and result["sub"]:
                            for cb in checkboxes:
                                if result["sub"] in cb.text():
                                    cb.setChecked(True)
                                    logger.info(f"横断技術領域（副）設定: {result['sub']}")
                                    break
                        
                        QMessageBox.information(
                            self,
                            "完了",
                            f"横断技術領域を設定しました。\n\n主: {result.get('main', '(なし)')}\n副: {result.get('sub', '(なし)')}"
                        )
        
        except Exception as e:
            logger.error(f"横断技術領域自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_equipment(self):
        """装置・プロセスを選択的置換ダイアログで自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_equipment_from_report,
                get_grant_number_from_dataset_json
            )
            from .auto_setting_dialog import AutoSettingDialog
            from .selective_replacement_dialog import SelectiveReplacementDialog
            from classes.utils.facility_link_helper import (
                find_latest_facilities_json,
                lookup_facility_code_by_equipment_id,
                lookup_facility_name_by_equipment_id,
                extract_equipment_id,
                build_equipment_anchor,
                build_equipment_anchor_with_name,
            )
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # 報告書ベースの候補取得関数（装置リスト用）
            def fetch_equipment_from_report(dataset_id: str) -> dict:
                result = extract_equipment_from_report(dataset_id, grant_number)
                # 装置リストを文字列に変換（AutoSettingDialog表示用）
                equipment_list = result.get("equipment", []) if result else []
                text = "\n".join(equipment_list) if equipment_list else ""
                return {"equipment": equipment_list, "text": text}
            
            # 情報源選択ダイアログを表示
            info_dialog = AutoSettingDialog(
                title="装置・プロセス 自動設定",
                field_name="装置・プロセス",
                dataset_id=self.dataset_id,
                report_fetcher=fetch_equipment_from_report,
                ai_fetcher=None,  # AI推定は未対応
                metadata=self.metadata,
                parent=self
            )
            
            if info_dialog.exec_() != QDialog.Accepted:
                return  # キャンセルされた
            
            # 取得した候補を取り出す
            info_result = info_dialog.get_result()
            if not info_result or "equipment" not in info_result:
                QMessageBox.warning(
                    self,
                    "警告",
                    "装置・プロセスの候補が取得できませんでした。"
                )
                return
            
            equipment_list = info_result.get("equipment", [])
            
            # 既存のテーブル内容を取得
            table = self.field_widgets.get('t_equip_process')
            current_items = []
            if table and isinstance(table, QTableWidget):
                for i in range(table.rowCount()):
                    item = table.item(i, 0)
                    text = item.text() if item else ""
                    current_items.append(text)
            
            # 装置ID正規化関数（facility_link_helper使用）
            def equipment_normalizer(text: str) -> str:
                equip_id = extract_equipment_id(text)
                return equip_id.lower() if equip_id else text.strip().lower()
            
            # リンク化拡張機能（設備ID + 設備名）
            def apply_equipment_link(row: int, current_text: str, suggested_text: str) -> str:
                """装置IDをリンクタグに変換（設備名付き）"""
                text = suggested_text if suggested_text else current_text
                if not text:
                    return text
                
                latest_path = find_latest_facilities_json()
                if latest_path is None:
                    return text
                
                equip_id = extract_equipment_id(text)
                if equip_id:
                    code = lookup_facility_code_by_equipment_id(latest_path, equip_id)
                    name = lookup_facility_name_by_equipment_id(latest_path, equip_id)
                    if code and name:
                        return build_equipment_anchor_with_name(code, equip_id, name)
                return text
            
            extension_buttons = [
                {"label": "リンク化", "callback": apply_equipment_link}
            ]
            
            # 選択的置換ダイアログ表示
            dialog = SelectiveReplacementDialog(
                title="装置・プロセス 選択的置換",
                field_prefix="t_equip_process",
                current_items=current_items,
                suggested_items=equipment_list,
                normalizer=equipment_normalizer,
                extension_buttons=extension_buttons,
                parent=self
            )
            
            if dialog.exec_() == QDialog.Accepted:
                result_data = dialog.get_result()
                final_items = result_data.get('final_items', [])
                
                # テーブルに適用（最大5行）
                if table and isinstance(table, QTableWidget):
                    # クリア
                    for i in range(table.rowCount()):
                        table.setItem(i, 0, QTableWidgetItem(""))
                    
                    # リンク化して設定（設備名付き）
                    latest_path = find_latest_facilities_json()
                    for i, equipment in enumerate(final_items[:5]):
                        text = str(equipment) if equipment is not None else ""
                        anchor_text = None
                        if latest_path is not None:
                            equip_id = extract_equipment_id(text)
                            if equip_id:
                                code = lookup_facility_code_by_equipment_id(latest_path, equip_id)
                                name = lookup_facility_name_by_equipment_id(latest_path, equip_id)
                                if code and name:
                                    anchor_text = build_equipment_anchor_with_name(code, equip_id, name)
                        table.setItem(i, 0, QTableWidgetItem(anchor_text or text))
                    
                    logger.info(f"装置・プロセス適用: {len(final_items)}件（最大5件表示）")
                    QMessageBox.information(
                        self,
                        "完了",
                        f"装置・プロセスを{len(final_items)}件設定しました。"
                    )
        
        except Exception as e:
            logger.error(f"装置・プロセス自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_equipment_legacy(self):
        """装置・プロセスを自動設定（旧実装・参考用）"""
        try:
            from ..core.auto_setting_helper import (
                extract_equipment_from_report,
                get_grant_number_from_dataset_json
            )
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("報告書から設備情報を取得中...", "中止", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            try:
                # 報告書から設備情報を取得
                result = extract_equipment_from_report(self.dataset_id, grant_number)
                
                progress.close()
                
                if result and result.get("equipment"):
                    equipment_list = result["equipment"]
                    # リンクタグ化準備
                    from classes.utils.facility_link_helper import (
                        find_latest_facilities_json,
                        lookup_facility_code_by_equipment_id,
                        lookup_facility_name_by_equipment_id,
                        extract_equipment_id,
                        build_equipment_anchor,
                        build_equipment_anchor_with_name,
                    )
                    latest_path = find_latest_facilities_json()
                    
                    # 装置・プロセステーブルに設定
                    table = self.field_widgets.get('t_equip_process')
                    if table and isinstance(table, QTableWidget):
                        # 既存の内容をクリア
                        for i in range(table.rowCount()):
                            table.setItem(i, 0, QTableWidgetItem(""))
                        
                        # 新しいデータを設定（最大5行）（設備名付き）
                        for i, equipment in enumerate(equipment_list[:5]):
                            text = str(equipment) if equipment is not None else ""
                            anchor_text = None
                            if latest_path is not None:
                                equip_id = extract_equipment_id(text)
                                if equip_id:
                                    code = lookup_facility_code_by_equipment_id(latest_path, equip_id)
                                    name = lookup_facility_name_by_equipment_id(latest_path, equip_id)
                                    if code and name:
                                        anchor_text = build_equipment_anchor_with_name(code, equip_id, name)
                            table.setItem(i, 0, QTableWidgetItem(anchor_text or text))
                        
                        logger.info(f"装置・プロセス設定(リンク化): {len(equipment_list)}件（最大5件表示） 最新JSON: {latest_path if latest_path else 'なし'}")
                        
                        QMessageBox.information(
                            self,
                            "完了",
                            f"装置・プロセスを設定しました。\n\n{len(equipment_list)}件の設備情報を取得しました。"
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "エラー",
                            "装置・プロセステーブルが見つかりませんでした。"
                        )
                else:
                    QMessageBox.warning(
                        self,
                        "情報なし",
                        "報告書に設備情報が登録されていません。"
                    )
            
            finally:
                progress.close()
        
        except Exception as e:
            logger.error(f"装置・プロセス自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_publications(self):
        """論文・プロシーディングを選択的置換ダイアログで自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_publications_from_report,
                get_grant_number_from_dataset_json
            )
            from .selective_replacement_dialog import SelectiveReplacementDialog
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("報告書から論文情報を取得中...", "中止", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            try:
                # 報告書から論文情報を取得
                result = extract_publications_from_report(self.dataset_id, grant_number)
                progress.close()
                
                # 結果に関わらずダイアログを表示（空の場合も含む）
                publications_list = result.get("publications", []) if result else []
                
                # 既存のテーブル内容を取得
                table = self.field_widgets.get('t_paper_proceed')
                current_items = []
                if table and isinstance(table, QTableWidget):
                    for i in range(table.rowCount()):
                        item = table.item(i, 0)
                        text = item.text() if item else ""
                        current_items.append(text)
                
                # DOI正規化関数
                def doi_normalizer(text: str) -> str:
                    """DOIを正規化（プロトコル除去・小文字化）"""
                    normalized = text.strip().lower()
                    # https://doi.org/ や http://dx.doi.org/ を除去
                    normalized = normalized.replace("https://doi.org/", "")
                    normalized = normalized.replace("http://doi.org/", "")
                    normalized = normalized.replace("http://dx.doi.org/", "")
                    normalized = normalized.replace("https://dx.doi.org/", "")
                    return normalized
                
                # 将来の拡張機能用（現在は空）
                extension_buttons = []
                
                # 選択的置換ダイアログ表示
                dialog = SelectiveReplacementDialog(
                    title="論文・プロシーディング 選択的置換",
                    field_prefix="t_paper_proceed",
                    current_items=current_items,
                    suggested_items=publications_list,
                    normalizer=doi_normalizer,
                    extension_buttons=extension_buttons,
                    parent=self
                )
                
                if dialog.exec_() == QDialog.Accepted:
                    result_data = dialog.get_result()
                    final_items = result_data.get('final_items', [])
                    
                    # テーブルに適用（最大20行）
                    if table and isinstance(table, QTableWidget):
                        # クリア
                        for i in range(table.rowCount()):
                            table.setItem(i, 0, QTableWidgetItem(""))
                        
                        # 設定
                        for i, publication in enumerate(final_items[:20]):
                            table.setItem(i, 0, QTableWidgetItem(publication))
                        
                        logger.info(f"論文・プロシーディング適用: {len(final_items)}件（最大20件表示）")
                        QMessageBox.information(
                            self,
                            "完了",
                            f"論文・プロシーディングを{len(final_items)}件設定しました。"
                        )
            
            except Exception as e:
                progress.close()
                raise
        
        except Exception as e:
            logger.error(f"論文・プロシーディング自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_publications_legacy(self):
        """論文・プロシーディングを自動設定（旧実装・参考用）"""
        try:
            from ..core.auto_setting_helper import (
                extract_publications_from_report,
                get_grant_number_from_dataset_json
            )
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("報告書から論文情報を取得中...", "中止", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            try:
                # 報告書から論文情報を取得
                result = extract_publications_from_report(self.dataset_id, grant_number)
                
                progress.close()
                
                if result and result.get("publications"):
                    publications_list = result["publications"]
                    
                    # 論文・プロシーディングテーブルに設定
                    table = self.field_widgets.get('t_paper_proceed')
                    if table and isinstance(table, QTableWidget):
                        # 既存の内容をクリア
                        for i in range(table.rowCount()):
                            table.setItem(i, 0, QTableWidgetItem(""))
                        
                        # 新しいデータを設定（最大20行）
                        for i, publication in enumerate(publications_list[:20]):
                            table.setItem(i, 0, QTableWidgetItem(publication))
                        
                        logger.info(f"論文・プロシーディング設定: {len(publications_list)}件（最大20件表示）")
                        
                        QMessageBox.information(
                            self,
                            "完了",
                            f"論文・プロシーディングを設定しました。\n\n{len(publications_list)}件の論文情報を取得しました。"
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "エラー",
                            "論文・プロシーディングテーブルが見つかりませんでした。"
                        )
                else:
                    QMessageBox.warning(
                        self,
                        "情報なし",
                        "報告書に論文情報が登録されていません。"
                    )
            
            finally:
                progress.close()
        
        except Exception as e:
            logger.error(f"論文・プロシーディング自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )

    def _on_auto_set_file_stats(self):
        """ファイル数 / 全ファイルサイズを総計（全ファイル）の統計から自動設定"""
        try:
            summary = self._load_data_entry_summary()
            if not summary:
                QMessageBox.warning(
                    self,
                    "データなし",
                    "データエントリー情報からファイル統計を取得できませんでした。\n"
                    "基本情報タブでデータエントリーを取得済みか確認してください。"
                )
                return

            total = summary.get("total") or {}
            total_count = int(total.get("count", 0) or 0)
            total_bytes = int(total.get("bytes", 0) or 0)

            shared2 = summary.get("shared2") or {}
            shared2_count = int(shared2.get("count", 0) or 0)
            shared2_bytes = int(shared2.get("bytes", 0) or 0)

            nonshared = (summary.get("filetypes") or {}).get("NONSHARED_RAW") or {}
            nonshared_count = int(nonshared.get("count", 0) or 0)
            nonshared_bytes = int(nonshared.get("bytes", 0) or 0)

            formatted_total = format_size_with_bytes(total_bytes)
            formatted_shared2 = format_size_with_bytes(shared2_bytes)
            formatted_nonshared = format_size_with_bytes(nonshared_bytes)

            # fileTypeごとの短いラベル（dataset_dataentry_widget_minimal と同じ表示）
            file_type_labels = {
                "MAIN_IMAGE": "MAIN",
                "STRUCTURED": "STRCT",
                "NONSHARED_RAW": "NOSHARE",
                "RAW": "RAW",
                "META": "META",
                "ATTACHEMENT": "ATTACH",
                "THUMBNAIL": "THUMB",
                "OTHER": "OTHER",
            }
            filetypes = summary.get("filetypes") or {}
            breakdown_lines = []
            for ft, stats in filetypes.items():
                if not isinstance(stats, dict):
                    continue
                count = int(stats.get("count", 0) or 0)
                bytes_ = int(stats.get("bytes", 0) or 0)
                label = file_type_labels.get(ft, ft)
                breakdown_lines.append(f"- {label}: {count:,} 件 / {format_size_with_bytes(bytes_)}")
            breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "- (内訳なし)"

            message = (
                "データエントリー情報集計に基づく推定値です。\n\n"
                f"【総計】ファイル数: {total_count:,} 件\n"
                f"【総計】ファイルサイズ: {formatted_total}\n\n"
                "（参考）\n"
                f"【共用合計２】ファイル数: {shared2_count:,} 件\n"
                f"【共用合計２】ファイルサイズ: {formatted_shared2}\n\n"
                f"NONSHARED_RAW: {nonshared_count:,} 件 / {formatted_nonshared}\n\n"
                "【fileType別 内訳】\n"
                f"{breakdown_text}\n\n"
                "これらの値を適用しますか?"
            )
            reply = QMessageBox.question(
                self,
                "ファイル統計の適用",
                message,
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            if self._apply_file_stats(shared2_count, shared2_bytes, total_bytes):
                QMessageBox.information(
                    self,
                    "適用完了",
                    "ファイル数と全ファイルサイズを更新しました。"
                )
        except Exception as exc:  # pragma: no cover
            logger.error(f"ファイル統計自動設定エラー: {exc}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"ファイル統計の取得中にエラーが発生しました:\n{exc}"
            )

    def _load_data_entry_summary(self, allow_fetch: bool = True):
        """Load dataEntry summary; optionally fetch dataEntry JSON when missing."""

        summary = get_data_entry_summary(self.dataset_id)
        if summary or not allow_fetch:
            return summary

        reply = QMessageBox.question(
            self,
            "データエントリー取得",
            "データエントリー情報が見つかりません。\n"
            "APIから最新情報を取得して推定値を計算しますか?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return None

        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
        if not bearer_token:
            QMessageBox.warning(
                self,
                "認証エラー",
                "Bearer Tokenを取得できませんでした。ログイン状態を確認してください。"
            )
            return None

        progress = QProgressDialog("データエントリー情報を取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        try:
            success = fetch_dataset_dataentry(self.dataset_id, bearer_token=bearer_token, force_refresh=True)
        finally:
            progress.close()

        if not success:
            QMessageBox.warning(
                self,
                "取得失敗",
                "データエントリー情報の取得に失敗しました。\n"
                "基本情報タブで先に取得できているか確認してください。"
            )
            return None

        return get_data_entry_summary(self.dataset_id)

    def _apply_file_stats(self, shared2_file_count: int, shared2_bytes: int, total_bytes: int) -> bool:
        """Apply calculated stats to corresponding widgets."""
        updated = False

        target_widgets = [
            # ファイル数: 共用合計２
            ('t_file_count', str(shared2_file_count)),
            # ファイルサイズ欄: 共用合計２
            ('t_meta_totalfilesizeinthisversion', str(shared2_bytes)),
            # 全ファイルサイズ欄: 総計
            ('t_meta_totalfilesize', str(total_bytes)),
        ]

        for field_name, value in target_widgets:
            widget = self.field_widgets.get(field_name)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
                updated = True
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(value)
                updated = True

        if not updated:
            QMessageBox.warning(
                self,
                "適用不可",
                "ファイル数または全ファイルサイズの入力フィールドが見つかりませんでした。"
            )

        return updated

    def _on_ai_suggest_checkbox_array(self, field_key: str, category: str):
        """AIで提案を取得し、チェックボックス配列に適用（設備/MI/タグ）"""
        try:
            from ..core.auto_setting_helper import fetch_ai_proposals_for_category

            widget = self.field_widgets.get(field_key)
            if not isinstance(widget, FilterableCheckboxTable):
                QMessageBox.warning(self, "エラー", "対象フィールドが見つかりませんでした")
                return

            # 適用モード
            mode = "append"
            if category == 'equipment' and hasattr(self, 'apply_mode_mec'):
                mode = 'replace' if self.apply_mode_mec.currentText() == '置換' else 'append'
            elif category == 'material_index' and hasattr(self, 'apply_mode_mmi'):
                mode = 'replace' if self.apply_mode_mmi.currentText() == '置換' else 'append'
            elif category == 'tag' and hasattr(self, 'apply_mode_mt'):
                mode = 'replace' if self.apply_mode_mt.currentText() == '置換' else 'append'

            # 取得中インジケータ
            progress = QProgressDialog("AIから候補を取得中...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            try:
                proposals = fetch_ai_proposals_for_category(self.dataset_id, category)
            finally:
                progress.close()

            if not proposals:
                QMessageBox.warning(self, "候補なし", "AIから候補を取得できませんでした")
                return

            # メタデータ上の有効なIDにフィルタ
            meta = self.metadata.get(field_key, {}).get('options', [])
            valid_ids = {str(opt.get('value')) for opt in meta}
            proposed_ids = [p.get('id') for p in proposals if p.get('id') in valid_ids]

            if not proposed_ids:
                QMessageBox.warning(self, "候補不一致", "AI候補はメタデータに一致しませんでした")
                return

            current = set(widget.get_selected_values())
            new_set = set(proposed_ids) if mode == 'replace' else (current.union(proposed_ids))

            widget.set_selected_values(sorted(new_set))

            QMessageBox.information(
                self,
                "AI適用完了",
                f"{len(proposed_ids)}件の候補を{ '置換' if mode=='replace' else '追記' }で適用しました。\n現在の選択数: {len(new_set)}"
            )
        except Exception as e:
            logger.error(f"AI提案適用エラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"AI提案の適用中にエラーが発生しました:\n{e}")

    def _open_checkbox_autoset_dialog(self, title: str, field_key: str, category: str):
        """チェックボックス配列用 自動設定ダイアログを開き、適用する"""
        try:
            from .auto_setting_checkbox_dialog import AutoSettingCheckboxDialog
            from ..core.auto_setting_helper import fetch_ai_proposals_for_category_with_debug

            dialog = AutoSettingCheckboxDialog(
                title=title,
                field_key=field_key,
                dataset_id=self.dataset_id,
                category=category,
                metadata=self.metadata,
                report_fetcher=None,
                ai_fetcher_debug=lambda dataset_id, cat: fetch_ai_proposals_for_category_with_debug(dataset_id, cat),
                parent=self,
            )

            if dialog.exec_() == QDialog.Accepted:
                result = dialog.get_result()
                if not result:
                    return
                mode = result.get('mode', 'append')
                ids = result.get('ids', [])

                widget = self.field_widgets.get(field_key)
                if not isinstance(widget, FilterableCheckboxTable):
                    QMessageBox.warning(self, "エラー", "対象フィールドが見つかりませんでした")
                    return

                current = set(widget.get_selected_values())
                new_set = set(ids) if mode == 'replace' else (current.union(ids))
                widget.set_selected_values(sorted(new_set))

                QMessageBox.information(
                    self,
                    "完了",
                    f"{len(ids)}件の候補を{ '置換' if mode=='replace' else '追記' }で適用しました。\n現在の選択数: {len(new_set)}"
                )
        except Exception as e:
            logger.error(f"自動設定ダイアログエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"自動設定ダイアログ処理中にエラーが発生しました:\n{e}")
    
    def _on_facility_link_batch(self):
        """装置・プロセステーブル内の設備IDを一括リンク化"""
        try:
            from classes.utils.facility_link_helper import (
                find_latest_facilities_json,
                lookup_facility_code_by_equipment_id,
                lookup_facility_name_by_equipment_id,
                extract_equipment_id,
                build_equipment_anchor,
                build_equipment_anchor_with_name,
            )
            
            # テーブルウィジェット取得
            table = self.field_widgets.get('t_equip_process')
            if not table or not isinstance(table, QTableWidget):
                QMessageBox.warning(
                    self,
                    "警告",
                    "装置・プロセステーブルが見つかりません。"
                )
                return
            
            # 最新の設備マスターJSON取得
            latest_path = find_latest_facilities_json()
            if latest_path is None:
                QMessageBox.warning(
                    self,
                    "警告",
                    "設備マスターJSONファイルが見つかりません。\n基本情報タブで設備情報を取得してください。"
                )
                return
            
            # 各行をスキャンしてリンク化
            linked_count = 0
            unchanged_count = 0
            
            for i in range(table.rowCount()):
                item = table.item(i, 0)
                if not item:
                    continue
                
                text = item.text().strip()
                if not text:
                    continue
                
                # 既にアンカータグの場合はスキップ
                if text.startswith('<a ') and '</a>' in text:
                    unchanged_count += 1
                    continue
                
                # 設備ID抽出
                equip_id = extract_equipment_id(text)
                if equip_id:
                    # 設備コード・設備名取得
                    code = lookup_facility_code_by_equipment_id(latest_path, equip_id)
                    name = lookup_facility_name_by_equipment_id(latest_path, equip_id)
                    if code and name:
                        # リンクタグ生成（設備名付き）
                        anchor_text = build_equipment_anchor_with_name(code, equip_id, name)
                        table.setItem(i, 0, QTableWidgetItem(anchor_text))
                        linked_count += 1
                        logger.debug(f"設備リンク化: {equip_id} -> {code} ({name})")
                    else:
                        unchanged_count += 1
                        logger.debug(f"設備コードまたは設備名未取得: {equip_id}")
                else:
                    unchanged_count += 1
            
            # 結果通知
            if linked_count > 0:
                QMessageBox.information(
                    self,
                    "完了",
                    f"設備リンク化完了:\n{linked_count}件をリンク化しました。\n{unchanged_count}件は変更なし。"
                )
                logger.info(f"設備リンク化完了: {linked_count}件")
            else:
                QMessageBox.information(
                    self,
                    "完了",
                    "リンク化対象の設備IDが見つかりませんでした。"
                )
        
        except Exception as e:
            logger.error(f"設備リンク化エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"設備リンク化中にエラーが発生しました:\n{e}"
            )
    


