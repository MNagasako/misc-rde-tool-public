"""
データ登録UI作成モジュール

データ登録機能のUI構築を担当します。
"""

import json
import os
import logging
from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QTextEdit,
    QGroupBox,
    QComboBox,
    QSizePolicy,
    QMessageBox,
    QPushButton,
)
from classes.data_entry.conf.ui_constants import get_data_register_form_style, TAB_HEIGHT_RATIO, get_launch_button_style
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
from qt_compat.gui import QFont
from qt_compat.core import QTimer, Qt
from config.common import get_dynamic_file_path
from classes.data_entry.util.template_format_validator import TemplateFormatValidator
from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload
from classes.managers.log_manager import get_logger
from classes.dataset.util.dataset_dropdown_util import get_current_user_id

# ロガー設定
logger = get_logger(__name__)
from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
from classes.data_entry.util.data_entry_forms_fixed import create_sample_form
from classes.data_entry.util.group_member_loader import load_group_members


def _set_required_label_state(label: QLabel, *, ok: bool) -> None:
    """必須項目ラベルの最小表示制御（未選択時のみエラー色）。"""

    try:
        from classes.utils.label_style import apply_label_style

        apply_label_style(label, get_color(ThemeKey.TEXT_PRIMARY if ok else ThemeKey.TEXT_ERROR), bold=True)
    except Exception:
        # 既存UIの動作を優先（label_style が使えない場合でも落とさない）
        label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY if ok else ThemeKey.TEXT_ERROR)}; font-weight: bold;"
        )


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
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    
    if button_style is None:
        button_style = f"""
        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
        color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
        font-weight: bold;
        border-radius: 8px;
        padding: 10px 16px;
        border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
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
    parent_controller.data_owner_combo = basic_info_widgets["data_owner"]
    parent_controller.data_owner_label = basic_info_widgets.get("data_owner_label")
    # URLとタグは試料情報へ移動のため削除
    # parent_controller.sample_reference_url_input = basic_info_widgets["url"]
    # parent_controller.sample_tags_input = basic_info_widgets["tags"]

    # --- 固有情報フォームの動的生成用 ---
    schema_form_widget = None
    
    # --- ファイル検証用バリデータ ---
    validator = TemplateFormatValidator()
    
    # --- テンプレート対応拡張子表示ラベル ---
    template_format_label = QLabel("データセットを選択してください")
    template_format_label.setWordWrap(True)
    template_format_label.setStyleSheet(
        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
        f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
    )
    layout.addWidget(template_format_label)
    parent_controller.template_format_label = template_format_label
    
    # --- ファイル検証結果表示ラベル ---
    file_validation_label = QLabel("")
    file_validation_label.setWordWrap(True)
    file_validation_label.setStyleSheet(
        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
        f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
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

        # --- データ所有者（所属）コンボボックス更新 ---
        if hasattr(parent_controller, 'data_owner_combo') and parent_controller.data_owner_combo:
            combo_owner = parent_controller.data_owner_combo
            combo_owner.clear()
            combo_owner.addItem("選択してください...", None)
            
            if group_id:
                try:
                    members = load_group_members(group_id)
                    current_user_id = get_current_user_id()
                    default_index = 0
                    
                    for i, member in enumerate(members):
                        user_id = member.get('id')
                        attrs = member.get('attributes', {})
                        name = attrs.get('name') or attrs.get('userName') or user_id
                        # 所属情報があれば追加
                        org = attrs.get('organizationName')
                        if org:
                            display_text = f"{name} ({org})"
                        else:
                            display_text = name
                        combo_owner.addItem(display_text, user_id)
                        
                        # ログインユーザーと一致する場合、そのインデックスを記録
                        # combo_ownerには"選択してください..."が先頭にあるため、indexは i + 1
                        if current_user_id and user_id == current_user_id:
                            default_index = i + 1
                    
                    combo_owner.setEnabled(True)
                    
                    # デフォルト選択: ログインユーザー > 先頭のメンバー
                    if default_index > 0:
                        combo_owner.setCurrentIndex(default_index)
                    elif combo_owner.count() > 1:
                        # ログインユーザーがいない場合は先頭のメンバー（index 1）を選択
                        combo_owner.setCurrentIndex(1)
                    
                except Exception as e:
                    logger.error("グループメンバー取得エラー: %s", e)
                    combo_owner.addItem("メンバー取得エラー", None)
                    combo_owner.setEnabled(False)
            else:
                combo_owner.addItem("グループ情報なし", None)
                combo_owner.setEnabled(False)

        # --- 試料フォーム生成（常に基本情報の次に挿入） ---
        try:
            parent_controller.sample_form_widget = create_sample_form(widget, group_id, parent_controller)
            if parent_controller.sample_form_widget:
                # データセット選択(0), ドロップダウン(1), 他機能連携(2), 基本情報(3)の次に挿入
                layout.insertWidget(4, parent_controller.sample_form_widget)
                parent_controller.sample_form_widget.setVisible(True)
                parent_controller.sample_form_widget.update()
                widget.update()

                # 必須項目の状態（試料管理者など）を反映
                updater = getattr(parent_controller, 'update_register_button_state', None)
                try:
                    if callable(updater):
                        updater()
                except Exception:
                    pass

                # 試料管理者の選択変更でも状態更新
                try:
                    sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
                    manager_combo = sample_widgets.get('manager') if isinstance(sample_widgets, dict) else None
                    if manager_combo is not None:
                        manager_combo.currentIndexChanged.connect(lambda *_: updater() if callable(updater) else None)
                except Exception:
                    pass
        except Exception as form_error:
            logger.error("試料フォーム作成エラー: %s", form_error)
            import traceback
            traceback.print_exc()
            parent_controller.sample_form_widget = None

        # --- 固有情報フォーム生成（常に試料フォームの次に挿入） ---
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
                layout.insertWidget(5, form)
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
                f"padding: 8px; background-color: {get_color(ThemeKey.PANEL_WARNING_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.PANEL_WARNING_TEXT)}; "
                f"border: 1px solid {get_color(ThemeKey.PANEL_WARNING_BORDER)}; border-radius: 4px;"
            )
        else:
            format_text = validator.get_format_display_text(template_id)
            template_format_label.setText(f"📋 対応ファイル形式: {format_text}")
            template_format_label.setStyleSheet(
                f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
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
    launch_button_style = get_launch_button_style()

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

    # 他機能連携ボタン（データセットコンボボックス直下に配置）
    # 他タブ（データセット編集/データエントリー）と同様に、項目名ラベルの右側へボタンを並べる
    launch_controls_widget = QWidget()
    launch_controls_layout = QHBoxLayout()
    launch_controls_layout.setContentsMargins(0, 0, 0, 0)

    launch_label = QLabel("他機能連携:")
    launch_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;")
    launch_controls_layout.addWidget(launch_label)

    # 他機能連携ボタン（データセット修正）
    launch_dataset_edit_button = QPushButton("データセット修正")
    launch_dataset_edit_button.setStyleSheet(launch_button_style)
    launch_dataset_edit_button.clicked.connect(_launch_to_dataset_edit)
    launch_controls_layout.addWidget(launch_dataset_edit_button)

    # 他機能連携ボタン（データエントリー）
    launch_dataset_dataentry_button = QPushButton("データエントリー")
    launch_dataset_dataentry_button.setStyleSheet(launch_button_style)
    launch_dataset_dataentry_button.clicked.connect(_launch_to_dataset_dataentry)
    launch_controls_layout.addWidget(launch_dataset_dataentry_button)

    launch_controls_layout.addStretch()
    launch_controls_widget.setLayout(launch_controls_layout)

    widget._dataset_launch_buttons = [
        launch_dataset_edit_button,
        launch_dataset_dataentry_button,
    ]  # type: ignore[attr-defined]

    if combo is not None:
        combo.currentIndexChanged.connect(lambda *_: _update_launch_button_state())
    _update_launch_button_state()

    # データセットドロップダウンの直下に「他機能連携」ボタン行を挿入
    layout.insertWidget(2, launch_controls_widget)


    # ファイル選択・登録実行ボタン（通常登録の主操作）
    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(15)  # ボタン間隔を広げる


    def _build_warning_button_style() -> str:
        return (
            f"background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};"
            f"color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};"
            "font-weight: bold;"
            "border-radius: 8px;"
            "padding: 10px 16px;"
            f"border: 1px solid {get_color(ThemeKey.BUTTON_WARNING_BORDER)};"
        )


    def _build_warning_badge_style() -> str:
        return (
            f"padding: 6px 10px; "
            f"background-color: {get_color(ThemeKey.PANEL_WARNING_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.PANEL_WARNING_TEXT)}; "
            f"border: 1px solid {get_color(ThemeKey.PANEL_WARNING_BORDER)}; "
            "border-radius: 4px; "
            "font-weight: bold;"
        )


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
                f"padding: 6px; background-color: {get_color(ThemeKey.PANEL_WARNING_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.PANEL_WARNING_TEXT)}; "
                f"border: 1px solid {get_color(ThemeKey.PANEL_WARNING_BORDER)}; border-radius: 4px;"
            )
            file_validation_label.setVisible(True)
            return
        
        # 検証実行
        result = validator.validate_files(files, template_id)
        
        if result.is_valid:
            # 有効なファイルあり
            file_validation_label.setText(f"✅ {result.validation_message}")
            file_validation_label.setStyleSheet(
                f"padding: 6px; background-color: {get_color(ThemeKey.PANEL_SUCCESS_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.PANEL_SUCCESS_TEXT)}; "
                f"border: 1px solid {get_color(ThemeKey.PANEL_SUCCESS_BORDER)}; border-radius: 4px;"
            )
        else:
            # 有効なファイルなし
            file_validation_label.setText(f"{result.validation_message}")
            file_validation_label.setStyleSheet(
                f"padding: 6px; background-color: {get_color(ThemeKey.PANEL_WARNING_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.TEXT_ERROR)}; "
                f"border: 1px solid {get_color(ThemeKey.PANEL_WARNING_BORDER)}; border-radius: 4px;"
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
    # 必須未入力でも押せる（アラートで促す）
    button_register_exec.setEnabled(True)
    parent_controller.register_exec_button = button_register_exec
    btn_layout.addWidget(button_register_exec)

    # 必須未入力の表示（ボタン右側）
    required_missing_label = QLabel("未入力必須項目有り")
    required_missing_label.setWordWrap(True)
    required_missing_label.setStyleSheet(_build_warning_badge_style())
    required_missing_label.setVisible(False)
    parent_controller.register_required_missing_label = required_missing_label
    btn_layout.addWidget(required_missing_label)

    # ファイル選択状態に応じて登録実行ボタンの有効/無効を切り替える
    def update_register_button_state():
        # Qtオブジェクトが破棄された後にシグナル経由で呼ばれるケースがあるため、
        # isValid/RuntimeError を吸収して安全に判定する。
        try:
            from shiboken6 import isValid  # type: ignore
        except Exception:  # pragma: no cover
            isValid = None  # type: ignore

        def _alive(w) -> bool:
            if w is None:
                return False
            if isValid is not None and not isValid(w):
                return False
            return True

        def _combo_selected(combo) -> bool:
            if not _alive(combo):
                return False
            try:
                return bool(combo.isEnabled() and combo.currentData() is not None)
            except RuntimeError:
                return False

        def _is_existing_sample_selected() -> bool:
            sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
            sample_combo = None
            if isinstance(sample_widgets, dict):
                sample_combo = sample_widgets.get('sample_combo')
            if sample_combo is None:
                sample_combo = getattr(parent_controller, 'sample_combo', None)
            if not _alive(sample_combo):
                return False
            try:
                # index=0 は「新規作成」
                current_index = sample_combo.currentIndex()
                if not isinstance(current_index, int):
                    try:
                        current_index = int(current_index)
                    except Exception:
                        return False
                if current_index <= 0:
                    return False
                return sample_combo.currentData() is not None
            except RuntimeError:
                return False

        def _get_missing_required_items() -> list[str]:
            missing: list[str] = []
            existing_sample_selected = _is_existing_sample_selected()
            # 必須: ファイル
            if not bool(getattr(parent_controller, 'selected_register_files', [])):
                missing.append("ファイル選択")
            # 必須: データ名
            data_name = getattr(parent_controller, 'data_name_input', None)
            try:
                if not (_alive(data_name) and data_name.text().strip() != ""):
                    missing.append("データ名")
            except RuntimeError:
                missing.append("データ名")
            # 必須: データ所有者（所属）
            owner_combo = getattr(parent_controller, 'data_owner_combo', None)
            if not _combo_selected(owner_combo):
                missing.append("データ所有者(所属)")
            # 必須: 試料管理者
            # 既存試料選択時は、試料管理者は既に確定しているため必須から除外
            if not existing_sample_selected:
                sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
                manager_combo = sample_widgets.get('manager') if isinstance(sample_widgets, dict) else None
                if not _combo_selected(manager_combo):
                    missing.append("試料管理者")
            return missing

        # 必須項目（データ名、ファイル選択、所属、試料管理者）がすべて入力済みか判定（添付ファイルは判定に使わない）
        missing_required = _get_missing_required_items()
        required_ok = len(missing_required) == 0

        # 必須: データ所有者（所属）
        owner_combo = getattr(parent_controller, 'data_owner_combo', None)
        owner_label = getattr(parent_controller, 'data_owner_label', None)
        owner_selected = _combo_selected(owner_combo)
        try:
            if isinstance(owner_label, QLabel) and _alive(owner_label):
                _set_required_label_state(owner_label, ok=owner_selected)
        except RuntimeError:
            pass

        # 必須: 試料管理者
        sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
        manager_combo = sample_widgets.get('manager') if isinstance(sample_widgets, dict) else None
        manager_label = sample_widgets.get('manager_label') if isinstance(sample_widgets, dict) else None
        # 既存試料選択時は必須ではないため、エラー表示にしない
        manager_required = not _is_existing_sample_selected()
        manager_selected = _combo_selected(manager_combo) if manager_required else True
        try:
            if isinstance(manager_label, QLabel) and _alive(manager_label):
                _set_required_label_state(manager_label, ok=manager_selected)
        except RuntimeError:
            pass
        # ボタン表示制御（押下は常に可能。未入力時は色変更＋表示）
        try:
            if _alive(button_register_exec):
                button_register_exec.setStyleSheet(button_style if required_ok else _build_warning_button_style())
            if hasattr(parent_controller, 'register_required_missing_label'):
                try:
                    parent_controller.register_required_missing_label.setStyleSheet(_build_warning_badge_style())
                    if not required_ok:
                        joined = " / ".join(missing_required) if missing_required else ""
                        parent_controller.register_required_missing_label.setText(f"未入力: {joined}" if joined else "未入力必須項目有り")
                        parent_controller.register_required_missing_label.setToolTip("\n".join(missing_required))
                    parent_controller.register_required_missing_label.setVisible(not required_ok)
                except RuntimeError:
                    pass
        except RuntimeError:
            pass

    parent_controller.update_register_button_state = update_register_button_state

    def _show_required_missing_alert(missing: list[str]) -> None:
        from qt_compat.widgets import QMessageBox
        from qt_compat.core import Qt

        msg_box = QMessageBox(widget)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("必須項目未入力")
        msg_box.setText("必須項目の入力が完了していません。")
        msg_box.setInformativeText("以下の必須項目を入力してください:\n- " + "\n- ".join(missing))
        msg_box.setStandardButtons(QMessageBox.Ok)
        try:
            msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        except Exception:
            pass
        msg_box.show()
        try:
            msg_box.raise_()
            msg_box.activateWindow()
        except Exception:
            pass
        msg_box.exec()

    # データ所有者の選択変更でも状態更新
    try:
        owner_combo = getattr(parent_controller, 'data_owner_combo', None)
        if owner_combo is not None:
            owner_combo.currentIndexChanged.connect(update_register_button_state)
    except Exception:
        pass

    # 試料管理者の選択変更でも状態更新（フォーム未生成の場合でも後付けされるケースがあるため）
    try:
        sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
        manager_combo = sample_widgets.get('manager') if isinstance(sample_widgets, dict) else None
        if manager_combo is not None:
            manager_combo.currentIndexChanged.connect(update_register_button_state)
    except Exception:
        pass

    # 試料「新規/選択」切り替えでも状態更新
    try:
        sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
        sample_combo = sample_widgets.get('sample_combo') if isinstance(sample_widgets, dict) else None
        if sample_combo is None:
            sample_combo = getattr(parent_controller, 'sample_combo', None)
        if sample_combo is not None:
            sample_combo.currentIndexChanged.connect(update_register_button_state)
    except Exception:
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

    # 登録実行ボタンのクリックは、必須未入力ならアラートを出して促す
    if hasattr(parent_controller, 'on_register_exec_clicked'):
        orig_register_exec = parent_controller.on_register_exec_clicked

        def wrapped_register_exec():
            try:
                # ここでは state 計算を再利用できないため、同等判定を行う
                files = getattr(parent_controller, 'selected_register_files', [])
                file_selected = bool(files)
                data_name = getattr(parent_controller, 'data_name_input', None)
                try:
                    data_name_filled = bool(data_name is not None and data_name.text().strip() != "")
                except Exception:
                    data_name_filled = False
                owner_combo = getattr(parent_controller, 'data_owner_combo', None)
                owner_selected = bool(owner_combo is not None and owner_combo.isEnabled() and owner_combo.currentData() is not None)

                sample_widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}
                sample_combo = None
                if isinstance(sample_widgets, dict):
                    sample_combo = sample_widgets.get('sample_combo')
                if sample_combo is None:
                    sample_combo = getattr(parent_controller, 'sample_combo', None)
                existing_sample_selected = False
                try:
                    if sample_combo is not None and sample_combo.currentIndex() > 0 and sample_combo.currentData() is not None:
                        existing_sample_selected = True
                except Exception:
                    existing_sample_selected = False

                manager_combo = sample_widgets.get('manager') if isinstance(sample_widgets, dict) else None
                manager_required = not existing_sample_selected
                if manager_required:
                    manager_selected = bool(
                        manager_combo is not None and manager_combo.isEnabled() and manager_combo.currentData() is not None
                    )
                else:
                    manager_selected = True

                required_ok = file_selected and data_name_filled and owner_selected and manager_selected
                if not required_ok:
                    missing_items = []
                    if not file_selected:
                        missing_items.append("ファイル選択")
                    if not data_name_filled:
                        missing_items.append("データ名")
                    if not owner_selected:
                        missing_items.append("データ所有者(所属)")
                    if manager_required and not manager_selected:
                        missing_items.append("試料管理者")
                    _show_required_missing_alert(missing_items)
                    update_register_button_state()
                    return None
            except Exception:
                pass
            return orig_register_exec()

        parent_controller.on_register_exec_clicked = wrapped_register_exec
        button_register_exec.clicked.connect(parent_controller.on_register_exec_clicked)

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
    # NOTE: setStyleSheet("") はスタイル継承を阻害する可能性があるため設定しない
    layout = QVBoxLayout(group_box)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    # 個別スタイル設定は行わず、親フォームの get_data_register_form_style から継承
    # これによりテーマ変更時に自動的に正しい色が適用される

    # データ名
    name_row = QHBoxLayout()
    name_label = QLabel("データ名 *")
    # ラベルも個別スタイル不要（親で定義済み）
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    name_input = QLineEdit()
    name_input.setPlaceholderText("データ名（必須）")
    name_input.setMinimumHeight(24)
    # 個別スタイル不要（親のQLineEditルールを継承）
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    name_row.addWidget(name_label)
    name_row.addWidget(name_input)
    layout.addLayout(name_row)

    # データ説明
    desc_row = QHBoxLayout()
    desc_label = QLabel("説明")
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    desc_input = QTextEdit()
    # QAbstractScrollArea系(QTextEdit)は環境によってQSSのborderが描画されないことがあるため、
    # StyledBackgroundを有効化してスタイルシート描画を確実にする。
    try:
        desc_input.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        desc_input.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass
    desc_input.setMinimumHeight(32)
    desc_input.setMaximumHeight(48)
    desc_input.setPlaceholderText("データ説明")
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    desc_row.addWidget(desc_label)
    desc_row.addWidget(desc_input)
    layout.addLayout(desc_row)

    # 実験ID
    expid_row = QHBoxLayout()
    expid_label = QLabel("実験ID")
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    expid_input = QLineEdit()
    expid_input.setPlaceholderText("実験ID（半角英数記号のみ）")
    expid_input.setMinimumHeight(24)
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    expid_row.addWidget(expid_label)
    expid_row.addWidget(expid_input)
    layout.addLayout(expid_row)

    # データ所有者（所属）
    owner_row = QHBoxLayout()
    owner_label = QLabel("データ所有者(所属) *")
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    owner_combo = QComboBox()
    owner_combo.setMinimumHeight(24)
    # NOTE: setStyleSheet("") は設定しない（親/グローバルQSSに追従）
    owner_combo.addItem("データセット選択後に選択可能", None)
    owner_combo.setEnabled(False)
    owner_row.addWidget(owner_label)
    owner_row.addWidget(owner_combo)
    layout.addLayout(owner_row)

    widgets = {
        "data_name": name_input,
        "data_desc": desc_input,
        "exp_id": expid_input,
        "data_owner": owner_combo,
        "data_owner_label": owner_label,
    }
    return group_box, widgets

# 補助関数: データ説明欄の値取得
def get_data_desc_value(desc_input):
    # QTextEditの場合はtoPlainText()、QLineEditの場合はtext()
    if hasattr(desc_input, 'toPlainText'):
        return desc_input.toPlainText()
    return desc_input.text()
