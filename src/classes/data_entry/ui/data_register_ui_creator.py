"""
データ登録UI作成モジュール

データ登録機能のUI構築を担当します。
"""

import json
import os
import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QTextEdit, QGroupBox, QComboBox, QSizePolicy, QMessageBox
)
from classes.data_entry.conf.ui_constants import get_data_register_form_style, TAB_HEIGHT_RATIO
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from qt_compat.gui import QFont
from qt_compat.core import QTimer, Qt
from config.common import get_dynamic_file_path
from classes.data_entry.util.template_format_validator import TemplateFormatValidator
from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload
from classes.managers.log_manager import get_logger

# ロガー設定
logger = get_logger(__name__)
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
    # pytest環境では強制表示がWindows側で不安定になることがあるため抑制
    if not os.environ.get("PYTEST_CURRENT_TEST"):
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
    
    # --- ファイル検証用バリデータ ---
    validator = TemplateFormatValidator()
    
    # --- テンプレート対応拡張子表示ラベル ---
    template_format_label = QLabel("データセットを選択してください")
    template_format_label.setWordWrap(True)
    template_format_label.setStyleSheet(
        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
    )
    layout.addWidget(template_format_label)
    parent_controller.template_format_label = template_format_label
    
    # --- ファイル検証結果表示ラベル ---
    file_validation_label = QLabel("")
    file_validation_label.setWordWrap(True)
    file_validation_label.setStyleSheet(
        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
    )
    file_validation_label.setVisible(False)
    layout.addWidget(file_validation_label)
    parent_controller.file_validation_label = file_validation_label
    parent_controller.current_template_id = None  # 現在選択中のテンプレートID

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
            logger.error("試料フォーム作成エラー: %s", form_error)
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
                
                # PySide6ではfindChildrenにタプルを渡せないため、個別に取得
                line_edits = form.findChildren(QLineEdit)
                combo_boxes = form.findChildren(QComboBox)
                all_children = line_edits + combo_boxes
                
                for child in all_children:
                    name = child.objectName() or child.placeholderText() or child.__class__.__name__
                    safe_name = f"schema_{name}".replace(' ', '_').replace('（', '').replace('）', '')
                    setattr(parent_controller, safe_name, child)
        
        # --- テンプレート対応拡張子表示を更新 ---
        parent_controller.current_template_id = template_id
        if not validator.is_formats_json_available():
            template_format_label.setText(
                "⚠ 対応ファイル形式情報が読み込まれていません。\n"
                "設定 → データ構造化タブでXLSXファイルを読み込んでください。"
            )
            template_format_label.setStyleSheet(
                f"padding: 8px; background-color: #fff3cd; color: #856404; "
                f"border: 1px solid #ffc107; border-radius: 4px;"
            )
        else:
            format_text = validator.get_format_display_text(template_id)
            template_format_label.setText(f"📋 対応ファイル形式: {format_text}")
            template_format_label.setStyleSheet(
                f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
                f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
            )
        
        # --- ファイル選択済みの場合は再検証 ---
        if hasattr(parent_controller, 'selected_register_files') and parent_controller.selected_register_files:
            update_file_validation()

    def _relax_dataset_filters_for_launch() -> None:
        dropdown_widget = getattr(parent_controller, 'dataset_dropdown', None)
        relax_fn = getattr(dropdown_widget, 'relax_filters_for_launch', None)
        if callable(relax_fn):
            try:
                relax_fn()
            except Exception:
                logger.debug("data_register: relax_filters_for_launch failed", exc_info=True)

    def _format_dataset_display(dataset_dict: dict, fallback: str | None = None) -> str:
        if not isinstance(dataset_dict, dict):
            return fallback or ""
        attrs = dataset_dict.get('attributes', {})
        grant = attrs.get('grantNumber') or ""
        name = attrs.get('name') or ""
        parts = [part for part in (grant, name) if part]
        if parts:
            return " - ".join(parts)
        return fallback or dataset_dict.get('id', '') or ''

    def _find_dataset_index(dataset_id: str) -> int:
        if combo is None or not dataset_id:
            return -1
        for idx in range(combo.count()):
            data = combo.itemData(idx, 0x0100)
            if isinstance(data, dict) and data.get('id') == dataset_id:
                return idx
        return -1

    def _ensure_dataset_entry(payload: DatasetPayload) -> int:
        if combo is None or not payload.raw:
            return -1
        display_text = payload.display_text or _format_dataset_display(payload.raw, payload.id)
        combo.blockSignals(True)
        combo.addItem(display_text, payload.raw)
        combo.blockSignals(False)
        return combo.count() - 1

    def _apply_dataset_launch_payload(payload: DatasetPayload) -> bool:
        if combo is None or payload is None or not payload.id:
            return False
        _relax_dataset_filters_for_launch()
        target_index = _find_dataset_index(payload.id)
        if target_index < 0 and payload.raw:
            target_index = _ensure_dataset_entry(payload)
        if target_index < 0:
            logger.debug("data_register: dataset not found for launch id=%s", payload.id)
            return False
        previous_index = combo.currentIndex()
        combo.setCurrentIndex(target_index)
        if previous_index == target_index:
            try:
                on_dataset_changed(target_index)
            except Exception:
                logger.debug("data_register: manual dataset refresh failed", exc_info=True)
        return True

    if combo is not None:
        combo.currentIndexChanged.connect(on_dataset_changed)
        DatasetLaunchManager.instance().register_receiver("data_register", _apply_dataset_launch_payload)

    # 他機能連携（通常登録 → データセット修正）
    launch_button_style = f"""
        QPushButton {{
            background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
            border-radius: 6px;
            padding: 6px 12px;
            border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
        }}
        QPushButton:hover {{
            background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
        }}
        QPushButton:disabled {{
            background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
        }}
    """

    def _get_current_dataset_payload_for_launch():
        if combo is None:
            return None
        idx = combo.currentIndex()
        if idx < 0:
            return None
        dataset_item = combo.itemData(idx, 0x0100)
        if not isinstance(dataset_item, dict):
            return None
        dataset_id = dataset_item.get("id")
        if not dataset_id:
            return None
        display_text = combo.itemText(idx) or dataset_id
        return {
            "dataset_id": dataset_id,
            "display_text": display_text,
            "raw_dataset": dataset_item,
        }

    def _update_launch_button_state() -> None:
        enabled = bool(_get_current_dataset_payload_for_launch())
        for btn in getattr(widget, "_dataset_launch_buttons", []):
            btn.setEnabled(enabled)

    def _launch_to_dataset_edit() -> None:
        payload = _get_current_dataset_payload_for_launch()
        if not payload:
            QMessageBox.warning(widget, "データセット未選択", "連携するデータセットを選択してください。")
            return
        logger.info(
            "data_register: launch request target=dataset_edit dataset_id=%s display=%s",
            payload["dataset_id"],
            payload["display_text"],
        )
        DatasetLaunchManager.instance().request_launch(
            target_key="dataset_edit",
            dataset_id=payload["dataset_id"],
            display_text=payload["display_text"],
            raw_dataset=payload["raw_dataset"],
            source_name="data_register",
        )

    def _launch_to_dataset_dataentry() -> None:
        payload = _get_current_dataset_payload_for_launch()
        if not payload:
            QMessageBox.warning(widget, "データセット未選択", "連携するデータセットを選択してください。")
            return
        logger.info(
            "data_register: launch request target=dataset_dataentry dataset_id=%s display=%s",
            payload["dataset_id"],
            payload["display_text"],
        )
        DatasetLaunchManager.instance().request_launch(
            target_key="dataset_dataentry",
            dataset_id=payload["dataset_id"],
            display_text=payload["display_text"],
            raw_dataset=payload["raw_dataset"],
            source_name="data_register",
        )

    # ファイル選択・登録実行ボタンを分離
    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(15)  # ボタン間隔を広げる

    # 他機能連携ボタン（データセット修正）
    launch_dataset_edit_button = parent_controller.create_auto_resize_button(
        "データセット修正",
        160,
        45,
        launch_button_style,
    )
    launch_dataset_edit_button.clicked.connect(_launch_to_dataset_edit)
    btn_layout.addWidget(launch_dataset_edit_button)

    # 他機能連携ボタン（データエントリー）
    launch_dataset_dataentry_button = parent_controller.create_auto_resize_button(
        "データエントリー",
        160,
        45,
        launch_button_style,
    )
    launch_dataset_dataentry_button.clicked.connect(_launch_to_dataset_dataentry)
    btn_layout.addWidget(launch_dataset_dataentry_button)

    widget._dataset_launch_buttons = [
        launch_dataset_edit_button,
        launch_dataset_dataentry_button,
    ]  # type: ignore[attr-defined]

    if combo is not None:
        combo.currentIndexChanged.connect(lambda *_: _update_launch_button_state())
    _update_launch_button_state()


    # --- ファイル検証関数 ---
    def update_file_validation():
        """選択されたファイルを検証して結果を表示"""
        files = getattr(parent_controller, 'selected_register_files', [])
        template_id = getattr(parent_controller, 'current_template_id', None)
        
        if not files:
            file_validation_label.setVisible(False)
            return
        
        if not template_id:
            file_validation_label.setText("⚠ データセットを選択してください")
            file_validation_label.setStyleSheet(
                "padding: 8px; background-color: #fff3cd; color: #856404; "
                "border: 1px solid #ffc107; border-radius: 4px;"
            )
            file_validation_label.setVisible(True)
            return
        
        # 検証実行
        result = validator.validate_files(files, template_id)
        
        if result.is_valid:
            # 有効なファイルあり
            file_validation_label.setText(f"✅ {result.validation_message}")
            file_validation_label.setStyleSheet(
                "padding: 8px; background-color: #d4edda; color: #155724; "
                "border: 1px solid #c3e6cb; border-radius: 4px;"
            )
        else:
            # 有効なファイルなし
            file_validation_label.setText(f"{result.validation_message}")
            file_validation_label.setStyleSheet(
                "padding: 8px; background-color: #f8d7da; color: #721c24; "
                "border: 1px solid #f5c6cb; border-radius: 4px;"
            )
        
        file_validation_label.setVisible(True)
    
    parent_controller.update_file_validation = update_file_validation

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

    # ファイル選択時に呼ばれるコールバックで状態更新と検証実行
    if hasattr(parent_controller, 'on_file_select_clicked'):
        orig_file_select = parent_controller.on_file_select_clicked
        def wrapped_file_select():
            result = orig_file_select()
            update_register_button_state()
            update_file_validation()
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
    
    # ウィジェットを確実に表示（pytest環境では不安定化することがあるため抑制）
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        widget.setVisible(True)
    # widget.show()  # 削除 - これがメインウィンドウから分離する原因
    
    return widget

def create_basic_info_group():
    """
    データ名、データ説明、実験ID、参考URL,タグを基本情報として
    フィールドセット(QGroupBox)＋LEGEND(タイトル)付きでグルーピングし、固有情報と同様の横並びスタイルで返す
    """
    group_box = QGroupBox("基本情報")
    # 個別スタイルは付与せず、親フォームウィジェットのスタイル(QGroupBoxルール)を継承させる
    # これによりテーマ変更時に親側の再スタイルのみで反映される
    group_box.setStyleSheet("")
    layout = QVBoxLayout(group_box)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    # 個別スタイル設定は行わず、親フォームの get_data_register_form_style から継承
    # これによりテーマ変更時に自動的に正しい色が適用される

    # データ名
    name_row = QHBoxLayout()
    name_label = QLabel("データ名 *")
    # ラベルも個別スタイル不要（親で定義済み）
    name_label.setStyleSheet("")
    name_input = QLineEdit()
    name_input.setPlaceholderText("データ名（必須）")
    name_input.setMinimumHeight(24)
    # 個別スタイル不要（親のQLineEditルールを継承）
    name_input.setStyleSheet("")
    name_row.addWidget(name_label)
    name_row.addWidget(name_input)
    layout.addLayout(name_row)

    # データ説明
    desc_row = QHBoxLayout()
    desc_label = QLabel("データ説明")
    desc_label.setStyleSheet("")
    desc_input = QTextEdit()
    desc_input.setMinimumHeight(32)
    desc_input.setMaximumHeight(48)
    desc_input.setPlaceholderText("データ説明")
    desc_input.setStyleSheet("")
    desc_row.addWidget(desc_label)
    desc_row.addWidget(desc_input)
    layout.addLayout(desc_row)

    # 実験ID
    expid_row = QHBoxLayout()
    expid_label = QLabel("実験ID")
    expid_label.setStyleSheet("")
    expid_input = QLineEdit()
    expid_input.setPlaceholderText("実験ID（半角英数記号のみ）")
    expid_input.setMinimumHeight(24)
    expid_input.setStyleSheet("")
    expid_row.addWidget(expid_label)
    expid_row.addWidget(expid_input)
    layout.addLayout(expid_row)

    # 参考URL
    url_row = QHBoxLayout()
    url_label = QLabel("参考URL")
    url_label.setStyleSheet("")
    url_input = QLineEdit()
    url_input.setPlaceholderText("参考URL")
    url_input.setMinimumHeight(24)
    url_input.setStyleSheet("")
    url_row.addWidget(url_label)
    url_row.addWidget(url_input)
    layout.addLayout(url_row)

    # タグ
    tag_row = QHBoxLayout()
    tag_label = QLabel("タグ(カンマ区切り)")
    tag_label.setStyleSheet("")
    tag_input = QLineEdit()
    tag_input.setPlaceholderText("タグ(カンマ区切り)")
    tag_input.setMinimumHeight(24)
    tag_input.setStyleSheet("")
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
