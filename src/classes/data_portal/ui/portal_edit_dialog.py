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

from classes.theme import get_color, ThemeKey

from classes.managers.log_manager import get_logger
from classes.data_portal.ui.widgets import FilterableCheckboxTable

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
        
        self.setWindowTitle(f"データポータル修正 - {dataset_id[:8]}...")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        
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
    
    def _create_editable_list_table(self, field_prefix: str, label: str, max_rows: int = 20, visible_rows: int = 5) -> 'QTableWidget':
        """
        編集可能なリストテーブルを作成（装置・プロセス、論文・プロシーディング用）
        
        Args:
            field_prefix: フィールドのプレフィックス（例: 't_equip_process', 't_paper_proceed'）
            label: ラベル
            max_rows: 最大行数（デフォルト20）
            visible_rows: 表示行数（デフォルト5）
        
        Returns:
            QTableWidget: テーブルウィジェット
        """
        table = QTableWidget()
        table.setColumnCount(1)
        table.setHorizontalHeaderLabels([label])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setRowCount(max_rows)
        
        # 行の高さを設定
        table.verticalHeader().setDefaultSectionSize(25)
        # 表示行数分の高さに設定
        table_height = visible_rows * 25 + table.horizontalHeader().height() + 2
        table.setMaximumHeight(table_height)
        table.setMinimumHeight(table_height)
        
        # 既存データを読み込み
        for i in range(1, max_rows + 1):
            field_name = f"{field_prefix}{i}"
            if field_name in self.form_data:
                value = self.form_data[field_name].get('value', '')
                if value:
                    item = QTableWidgetItem(value)
                    table.setItem(i - 1, 0, item)
        
        # 空のセルを追加
        for i in range(table.rowCount()):
            if table.item(i, 0) is None:
                table.setItem(i, 0, QTableWidgetItem(""))
        
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
        
        # 装置・プロセス - テーブル表示（5行表示、最大5行）
        equip_process_table = self._create_editable_list_table('t_equip_process', '装置・プロセス', max_rows=5, visible_rows=5)
        self.field_widgets['t_equip_process'] = equip_process_table
        layout.addRow("装置・プロセス:", equip_process_table)
        
        # 論文・プロシーディング - テーブル表示（5行表示、最大20行）
        paper_proceed_table = self._create_editable_list_table('t_paper_proceed', '論文・プロシーディング', max_rows=20, visible_rows=5)
        self.field_widgets['t_paper_proceed'] = paper_proceed_table
        layout.addRow("論文・プロシーディング:", paper_proceed_table)
        
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
                if isinstance(widget, QTableWidget):
                    # 全ての行について、空値でもキーを含める
                    for row in range(widget.rowCount()):
                        field_name = f"{key}{row + 1}"
                        item = widget.item(row, 0)
                        if item and item.text().strip():
                            post_data[field_name] = item.text().strip()
                        else:
                            # 空値の場合も空文字列として送信
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
