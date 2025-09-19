"""
データ登録UI作成モジュール

データ登録機能のUI構築を担当します。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QTextEdit, QGroupBox, QComboBox, QSizePolicy, QMessageBox
)
from classes.data_entry.conf.ui_constants import DATA_REGISTER_FORM_STYLE
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QTimer, Qt
import json
import os
from config.common import get_dynamic_file_path
from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
from classes.data_entry.util.data_entry_forms_fixed import create_sample_form


def safe_remove_widget(layout, widget):
    """
    ウィジェットを安全に削除するヘルパー関数
    
    Args:
        layout: 親レイアウト
        widget: 削除するウィジェット
    """
    if widget is None:
        return
    
    try:
        # ウィジェットが有効かチェック（親ウィジェットがあるかで判定）
        if widget.parent() is not None and layout:
            layout.removeWidget(widget)
        widget.deleteLater()
    except RuntimeError:
        # 既に削除済みの場合は何もしない
        pass


def create_data_register_widget(parent_controller, title="データ登録", button_style=None):
    """
    データ登録ウィジェットを作成
    
    Args:
        parent_controller: 親のUIController
        title: ウィジェットのタイトル
        button_style: ボタンのスタイル
        
    Returns:
        QWidget: データ登録用ウィジェット
    """
    widget = QWidget()
    widget.setVisible(True)  # 明示的に表示設定
    layout = QVBoxLayout()
    layout.setContentsMargins(15, 15, 15, 15)  # より適切な余白
    layout.setSpacing(15)  # 要素間の間隔を増加
    
    if button_style is None:
        button_style = """
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                   stop: 0 #2196f3, stop: 1 #1976d2);
        color: white; 
        font-weight: bold; 
        border-radius: 8px;
        padding: 10px 16px;
        border: none;
        """
    

    # --- データセット選択 ---

    # --- データセット選択ラベル・ドロップダウンをインデックス指定で挿入 ---
    try:
        from classes.data_entry.util.data_entry_filter_checkbox import create_checkbox_filter_dropdown
        dataset_dropdown = create_checkbox_filter_dropdown(widget)
        dataset_dropdown.setMinimumWidth(450)
        if hasattr(dataset_dropdown, 'dataset_dropdown'):
            dataset_combo_font = QFont("Yu Gothic UI", 11)
            dataset_dropdown.dataset_dropdown.setFont(dataset_combo_font)
            dataset_dropdown.dataset_dropdown.setStyleSheet("QComboBox { font-size: 12px; padding: 4px; }")
        dataset_label = QLabel("📊 データセット選択")
        layout.insertWidget(0, dataset_label)
        layout.insertWidget(1, dataset_dropdown)
        parent_controller.dataset_dropdown = dataset_dropdown
    except ImportError as e:
        parent_controller.show_error(f"フィルタのインポートに失敗しました: {e}")
        try:
            from classes.dataset.util.dataset_dropdown_util import create_dataset_dropdown_with_user
            from config.common import INFO_JSON_PATH, DATASET_JSON_PATH
            dataset_dropdown = create_dataset_dropdown_with_user(DATASET_JSON_PATH, INFO_JSON_PATH, widget)
            dataset_dropdown.setMinimumWidth(320)
            dataset_label = QLabel("📊 データセット選択")
            layout.insertWidget(0, dataset_label)
            layout.insertWidget(1, dataset_dropdown)
            parent_controller.dataset_dropdown = dataset_dropdown
        except Exception as fallback_e:
            parent_controller.show_error(f"フォールバックドロップダウンも失敗: {fallback_e}")
            dataset_dropdown = QLabel("データ登録機能が利用できません")
            layout.insertWidget(0, dataset_dropdown)
            parent_controller.dataset_dropdown = dataset_dropdown
    except Exception as e:
        parent_controller.show_error(f"データ登録画面の作成でエラーが発生しました: {e}")
        dataset_dropdown = QLabel("データ登録機能が利用できません")
        layout.insertWidget(0, dataset_dropdown)
        parent_controller.dataset_dropdown = dataset_dropdown

    # --- 基本情報フィールドセットを追加（常に2番目） ---
    from .data_register_ui_creator import create_basic_info_group
    basic_info_group, basic_info_widgets = create_basic_info_group()
    layout.insertWidget(2, basic_info_group)
    parent_controller.data_name_input = basic_info_widgets["data_name"]
    parent_controller.basic_description_input = basic_info_widgets["data_desc"]
    parent_controller.experiment_id_input = basic_info_widgets["exp_id"]
    parent_controller.sample_reference_url_input = basic_info_widgets["url"]
    parent_controller.sample_tags_input = basic_info_widgets["tags"]

    # --- 固有情報フォームの動的生成用 ---
    schema_form_widget = None

    # combo取得（dataset_dropdownの型によって異なる）
    if hasattr(parent_controller.dataset_dropdown, 'dataset_dropdown'):
        combo = parent_controller.dataset_dropdown.dataset_dropdown
    elif hasattr(parent_controller.dataset_dropdown, 'dataset_filter_widget') and hasattr(parent_controller.dataset_dropdown.dataset_filter_widget, 'dataset_dropdown'):
        combo = parent_controller.dataset_dropdown.dataset_filter_widget.dataset_dropdown
    elif isinstance(parent_controller.dataset_dropdown, QComboBox):
        combo = parent_controller.dataset_dropdown
    else:
        combo = None

    def on_dataset_changed(idx):
        nonlocal schema_form_widget
        if combo is None:
            return
        # --- 既存の試料フォーム・スキーマフォームを削除 ---
        if hasattr(parent_controller, 'sample_form_widget') and parent_controller.sample_form_widget:
            safe_remove_widget(layout, parent_controller.sample_form_widget)
            parent_controller.sample_form_widget = None
        if hasattr(parent_controller, 'schema_form_widget') and parent_controller.schema_form_widget:
            safe_remove_widget(layout, parent_controller.schema_form_widget)
            parent_controller.schema_form_widget = None

        # --- データセット情報取得 ---
        dataset_item = combo.itemData(idx, 0x0100)
        if not (dataset_item and hasattr(dataset_item, 'get')):
            return
        dataset_id = dataset_item.get('id', '')
        dataset_json_path = get_dynamic_file_path(f'output/rde/data/datasets/{dataset_id}.json')
        if not os.path.exists(dataset_json_path):
            QMessageBox.warning(widget, "エラー", f"データセットファイルが見つかりません: {dataset_json_path}")
            return
        with open(dataset_json_path, 'r', encoding='utf-8') as f:
            dataset_data = json.load(f)
            relationships = dataset_data.get("data",{}).get('relationships', {})
            group = relationships.get('group', {}).get('data', {})
            group_id = group.get('id', '')

        # --- 試料フォーム生成（常に3番目に挿入） ---
        try:
            parent_controller.sample_form_widget = create_sample_form(widget, group_id, parent_controller)
            if parent_controller.sample_form_widget:
                # データセット選択(0), ドロップダウン(1), 基本情報(2)の次に挿入
                layout.insertWidget(3, parent_controller.sample_form_widget)
                parent_controller.sample_form_widget.setVisible(True)
                parent_controller.sample_form_widget.update()
                widget.update()
        except Exception as form_error:
            print(f"[ERROR] 試料フォーム作成エラー: {form_error}")
            import traceback
            traceback.print_exc()
            parent_controller.sample_form_widget = None

        # --- 固有情報フォーム生成（常に4番目に挿入） ---
        template_id = ''
        instrument_id = ''
        invoice_schema_exists = ''
        template = relationships.get('template', {}).get('data', {})
        if isinstance(template, dict):
            template_id = template.get('id', '')
        instruments = relationships.get('instruments', {}).get('data', [])
        if isinstance(instruments, list) and len(instruments) > 0 and isinstance(instruments[0], dict):
            instrument_id = instruments[0].get('id', '')
        invoice_schema_path = None
        if template_id:
            invoice_schema_path = get_dynamic_file_path(f'output/rde/data/invoiceSchemas/{template_id}.json')
            invoice_schema_exists = 'あり' if os.path.exists(invoice_schema_path) else 'なし'
        else:
            invoice_schema_exists = 'テンプレートIDなし'
        if invoice_schema_exists == 'あり' and invoice_schema_path:
            form = create_schema_form_from_path(invoice_schema_path, widget)
            if form:
                layout.insertWidget(4, form)
                schema_form_widget = form
                parent_controller.schema_form_widget = schema_form_widget
                form.setVisible(True)
                widget.setVisible(True)
                widget.update()
                layout.update()
                widget.repaint()
                def safe_show_schema_form():
                    if hasattr(parent_controller, 'schema_form_widget') and parent_controller.schema_form_widget is not None:
                        try:
                            parent_controller.schema_form_widget.setVisible(True)
                        except RuntimeError:
                            pass
                def safe_update_widget_schema():
                    try:
                        widget.update()
                    except RuntimeError:
                        pass
                QTimer.singleShot(100, safe_show_schema_form)
                QTimer.singleShot(100, safe_update_widget_schema)
                for child in form.findChildren((QLineEdit, QComboBox)):
                    name = child.objectName() or child.placeholderText() or child.__class__.__name__
                    safe_name = f"schema_{name}".replace(' ', '_').replace('（', '').replace('）', '')
                    setattr(parent_controller, safe_name, child)



    combo.currentIndexChanged.connect(on_dataset_changed)

    # ファイル選択・登録実行ボタンを分離
    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(15)  # ボタン間隔を広げる


    # ファイル選択ボタン
    button_file_select_text = "📁 ファイル選択(未選択)"
    button_file_select = parent_controller.create_auto_resize_button(
        button_file_select_text, 220, 45, button_style
    )
    button_file_select.clicked.connect(parent_controller.on_file_select_clicked)
    parent_controller.file_select_button = button_file_select
    btn_layout.addWidget(button_file_select)

    # 登録実行ボタン
    button_register_exec_text = f"🚀 {title}"
    button_register_exec = parent_controller.create_auto_resize_button(
        button_register_exec_text, 220, 45, button_style
    )
    button_register_exec.clicked.connect(parent_controller.on_register_exec_clicked)
    button_register_exec.setEnabled(False)  # 初期状態は無効
    parent_controller.register_exec_button = button_register_exec
    btn_layout.addWidget(button_register_exec)

    # ファイル選択状態に応じて登録実行ボタンの有効/無効を切り替える
    def update_register_button_state():
        # 必須項目（データ名、ファイル選択）がすべて入力済みか判定（添付ファイルは判定に使わない）
        files = getattr(parent_controller, 'selected_register_files', [])
        file_selected = bool(files)
        data_name = getattr(parent_controller, 'data_name_input', None)
        data_name_filled = data_name and data_name.text().strip() != ""
        # QPushButtonが既に削除済みの場合は何もしない
        try:
            if button_register_exec is not None and button_register_exec.parent() is not None:
                if file_selected and data_name_filled:
                    button_register_exec.setEnabled(True)
                else:
                    button_register_exec.setEnabled(False)
        except RuntimeError:
            # 既に削除済みの場合は無視
            pass

    # データ名入力時にも状態更新
    if hasattr(parent_controller, 'data_name_input'):
        parent_controller.data_name_input.textChanged.connect(lambda: update_register_button_state())

    # ファイル選択時に呼ばれるコールバックで状態更新
    if hasattr(parent_controller, 'on_file_select_clicked'):
        orig_file_select = parent_controller.on_file_select_clicked
        def wrapped_file_select():
            result = orig_file_select()
            update_register_button_state()
            return result
        parent_controller.on_file_select_clicked = wrapped_file_select
        button_file_select.clicked.disconnect()
        button_file_select.clicked.connect(parent_controller.on_file_select_clicked)

    # 初期状態も反映
    update_register_button_state()

    # 添付ファイル選択ボタン（有効・無効判定から除外）
    button_attachment_file_select_text = "📎 添付ファイル選択(未選択)"
    button_attachment_file_select = parent_controller.create_auto_resize_button(
        button_attachment_file_select_text, 220, 45, button_style
    )
    button_attachment_file_select.clicked.connect(parent_controller.on_attachment_file_select_clicked)
    parent_controller.attachment_file_select_button = button_attachment_file_select
    btn_layout.addWidget(button_attachment_file_select)

    layout.addLayout(btn_layout)

    # 最後にStretchを追加
    layout.addStretch()
    widget.setLayout(layout)
    
    # レスポンシブデザイン対応
    widget.setMinimumWidth(600)  # 最小幅設定
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    # ウィジェットを確実に表示
    widget.setVisible(True)
    # widget.show()  # 削除 - これがメインウィンドウから分離する原因
    
    return widget

def create_basic_info_group():
    """
    データ名、データ説明、実験ID、参考URL,タグを基本情報として
    フィールドセット(QGroupBox)＋LEGEND(タイトル)付きでグルーピングし、固有情報と同様の横並びスタイルで返す
    """
    group_box = QGroupBox("基本情報")
    group_box.setStyleSheet(DATA_REGISTER_FORM_STYLE)
    layout = QVBoxLayout(group_box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    row_style = """
        QLabel {
            font-weight: 600;
            min-width: 120px;
            color: #495057;
            padding: 2px 0;
        }
        QLineEdit, QTextEdit {
            border: 2px solid #e9ecef;
            border-radius: 3px;
            padding: 2px 3px;
            font-size: 10pt;
            background-color: white;
        }
        QLineEdit:focus, QTextEdit:focus {
            border-color: #2196f3;
            outline: none;
        }
        QLineEdit::placeholder, QTextEdit::placeholder {
            color: #28a745;
            font-style: italic;
        }
    """

    # データ名
    name_row = QHBoxLayout()
    name_label = QLabel("データ名 *")
    name_label.setStyleSheet("font-weight: bold; min-width: 120px; color: #d32f2f;")
    name_input = QLineEdit()
    name_input.setPlaceholderText("データ名（必須）")
    name_input.setMinimumHeight(24)
    name_input.setStyleSheet(row_style)
    name_row.addWidget(name_label)
    name_row.addWidget(name_input)
    layout.addLayout(name_row)

    # データ説明
    desc_row = QHBoxLayout()
    desc_label = QLabel("データ説明")
    desc_label.setStyleSheet("font-weight: bold; min-width: 120px; color: #495057;")
    desc_input = QTextEdit()
    desc_input.setMinimumHeight(32)
    desc_input.setMaximumHeight(48)
    desc_input.setPlaceholderText("データ説明")
    desc_input.setStyleSheet(row_style)
    desc_row.addWidget(desc_label)
    desc_row.addWidget(desc_input)
    layout.addLayout(desc_row)

    # 実験ID
    expid_row = QHBoxLayout()
    expid_label = QLabel("実験ID")
    expid_label.setStyleSheet("font-weight: bold; min-width: 120px; color: #495057;")
    expid_input = QLineEdit()
    expid_input.setPlaceholderText("実験ID（半角英数記号のみ）")
    expid_input.setMinimumHeight(24)
    expid_input.setStyleSheet(row_style)
    expid_row.addWidget(expid_label)
    expid_row.addWidget(expid_input)
    layout.addLayout(expid_row)

    # 参考URL
    url_row = QHBoxLayout()
    url_label = QLabel("参考URL")
    url_label.setStyleSheet("font-weight: bold; min-width: 120px; color: #495057;")
    url_input = QLineEdit()
    url_input.setPlaceholderText("参考URL")
    url_input.setMinimumHeight(24)
    url_input.setStyleSheet(row_style)
    url_row.addWidget(url_label)
    url_row.addWidget(url_input)
    layout.addLayout(url_row)

    # タグ
    tag_row = QHBoxLayout()
    tag_label = QLabel("タグ(カンマ区切り)")
    tag_label.setStyleSheet("font-weight: bold; min-width: 120px; color: #495057;")
    tag_input = QLineEdit()
    tag_input.setPlaceholderText("タグ(カンマ区切り)")
    tag_input.setMinimumHeight(24)
    tag_input.setStyleSheet(row_style)
    tag_row.addWidget(tag_label)
    tag_row.addWidget(tag_input)
    layout.addLayout(tag_row)

    widgets = {
        "data_name": name_input,
        "data_desc": desc_input,
        "exp_id": expid_input,
        "url": url_input,
        "tags": tag_input
    }
    return group_box, widgets

# 補助関数: データ説明欄の値取得
def get_data_desc_value(desc_input):
    # QTextEditの場合はtoPlainText()、QLineEditの場合はtext()
    if hasattr(desc_input, 'toPlainText'):
        return desc_input.toPlainText()
    return desc_input.text()
