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
    QSpinBox,
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
from classes.managers.log_manager import get_logger
from classes.data_entry.ui.toggle_section_widget import ToggleSectionWidget

# ロガー設定
logger = get_logger(__name__)
 

def create_sample_form(*args, **kwargs):
    """試料情報フォーム生成（後方互換ラッパー）。

    以前は本モジュールに存在していたため、テストや他モジュールが
    `classes.data_entry.ui.data_register_ui_creator.create_sample_form` を参照する。
    実装は util 側にあるので遅延 import で委譲する。
    """

    from classes.data_entry.util.data_entry_forms_fixed import create_sample_form as _impl

    return _impl(*args, **kwargs)



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
    # NOTE: ここで setVisible(True) すると、まだレイアウトに組み込まれていない QWidget が
    # トップレベル化して一瞬だけ表示される（Windowsで "python" 空ウィンドウになる）ため禁止。
    widget = QWidget()
    layout = QVBoxLayout(widget)
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
        dataset_label = QLabel("📊 データセット選択", widget)
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
            dataset_label = QLabel("📊 データセット選択", widget)
            layout.insertWidget(0, dataset_label)
            layout.insertWidget(1, dataset_dropdown)
            parent_controller.dataset_dropdown = dataset_dropdown
        except Exception as fallback_e:
            parent_controller.show_error(f"フォールバックドロップダウンも失敗: {fallback_e}")
            dataset_dropdown = QLabel("データ登録機能が利用できません", widget)
            layout.insertWidget(0, dataset_dropdown)
            parent_controller.dataset_dropdown = dataset_dropdown
    except Exception as e:
        parent_controller.show_error(f"データ登録画面の作成でエラーが発生しました: {e}")
        dataset_dropdown = QLabel("データ登録機能が利用できません", widget)
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
    parent_controller.data_owner_error_button = basic_info_widgets.get("data_owner_error_button")

    if getattr(parent_controller, "data_owner_error_button", None) is not None:
        def _show_data_owner_debug_dialog() -> None:
            try:
                from classes.data_entry.ui.data_owner_debug_dialog import show_data_owner_debug_dialog

                ctx = getattr(parent_controller, "_data_owner_debug_context", None)
                show_data_owner_debug_dialog(widget, context=ctx)
            except Exception as exc:
                logger.error("エラー詳細ダイアログ表示失敗: %s", exc, exc_info=True)

        try:
            parent_controller.data_owner_error_button.clicked.connect(_show_data_owner_debug_dialog)
        except Exception:
            pass
    # URLとタグは試料情報へ移動のため削除
    # parent_controller.sample_reference_url_input = basic_info_widgets["url"]
    # parent_controller.sample_tags_input = basic_info_widgets["tags"]

    # --- 固有情報フォームの動的生成用 ---
    schema_form_widget = None

    # --- トグル用コンテナ（試料/固有） ---
    parent_controller.sample_form_container = None
    parent_controller.schema_form_container = None
    
    # --- ファイル検証用バリデータ ---
    from classes.data_entry.util.template_format_validator import TemplateFormatValidator

    validator = TemplateFormatValidator()
    
    # --- テンプレート対応拡張子表示ラベル ---
    template_format_label = QLabel("データセットを選択してください", widget)
    template_format_label.setWordWrap(True)
    template_format_label.setStyleSheet(
        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
        f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
    )
    layout.addWidget(template_format_label)
    parent_controller.template_format_label = template_format_label
    
    # --- ファイル検証結果表示ラベル ---
    file_validation_label = QLabel("", widget)
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

        # 選択時にのみ必要な重い依存を import（初回表示を軽くする）
        from classes.data_entry.util.data_entry_forms import create_schema_form_from_path
        from classes.data_entry.util.group_member_loader import load_group_members_with_debug
        from classes.dataset.util.dataset_dropdown_util import get_current_user_id

        def _build_owner_debug_context(*, dataset_id: str, dataset_json_path: str, dataset_data: dict | None, group_id: str, members: list | None, notes: list[str]) -> dict:
            def _safe_dict_get(d: dict | None, *keys, default=None):
                cur = d
                for k in keys:
                    if not isinstance(cur, dict):
                        return default
                    cur = cur.get(k)
                return cur if cur is not None else default

            # サブグループJSON候補（実装上は group_id=サブグループID）
            subgroup_candidates: list[str] = []
            if group_id:
                subgroup_candidates = [
                    get_dynamic_file_path(f"output/rde/data/subGroups/{group_id}.json"),
                    get_dynamic_file_path(f"output/rde/data/subGroupsAncestors/{group_id}.json"),
                    get_dynamic_file_path(f"output/rde/data/subgroups/{group_id}.json"),
                ]

            existing_subgroup_paths = [p for p in subgroup_candidates if p and os.path.exists(p)]

            dataset_rel_keys = []
            try:
                relationships = _safe_dict_get(dataset_data, "data", "relationships", default={})
                if isinstance(relationships, dict):
                    dataset_rel_keys = sorted(list(relationships.keys()))
            except Exception:
                dataset_rel_keys = []

            dataset_included_types: dict[str, int] = {}
            try:
                included = (dataset_data or {}).get("included")
                if isinstance(included, list):
                    for item in included:
                        if isinstance(item, dict):
                            t = str(item.get("type") or "")
                            if t:
                                dataset_included_types[t] = dataset_included_types.get(t, 0) + 1
            except Exception:
                dataset_included_types = {}

            member_ids: list[str] = []
            displayable_members: list[dict] = []
            for m in (members or []):
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "").strip()
                if mid:
                    member_ids.append(mid)
                attrs = m.get("attributes") if isinstance(m.get("attributes"), dict) else {}
                displayable_members.append(
                    {
                        "id": mid,
                        "userName": str(attrs.get("userName") or ""),
                        "organizationName": str(attrs.get("organizationName") or ""),
                        "isDeleted": attrs.get("isDeleted"),
                    }
                )

            return {
                "dataset_id": str(dataset_id or ""),
                "dataset_json_path": str(dataset_json_path or ""),
                "dataset_json_exists": bool(dataset_json_path and os.path.exists(dataset_json_path)),
                "dataset_relationship_keys": dataset_rel_keys,
                "dataset_included_type_counts": dataset_included_types,
                "group_id": str(group_id or ""),
                "subgroup_candidate_paths": subgroup_candidates,
                "subgroup_existing_paths": existing_subgroup_paths,
                "members_count": len(members or []),
                "member_ids": member_ids,
                "members_preview": displayable_members[:20],
                "notes": list(notes or []),
            }

        def _set_owner_detail_button_state(*, is_error: bool, context: dict | None) -> None:
            btn = getattr(parent_controller, "data_owner_error_button", None)
            if btn is None:
                return
            parent_controller._data_owner_debug_context = context
            try:
                btn.setEnabled(context is not None)
            except Exception:
                pass

            label = "詳細（エラー）" if is_error else "詳細"
            try:
                btn.setText(label)
                btn.setFixedWidth(btn.sizeHint().width())
            except Exception:
                pass

        # --- 既存の試料フォーム・スキーマフォームを削除 ---
        # NOTE: 試料/固有はトグル用コンテナでラップしているため、コンテナを削除する。
        if getattr(parent_controller, 'sample_form_container', None) is not None:
            safe_remove_widget(layout, parent_controller.sample_form_container)
            parent_controller.sample_form_container = None
        if getattr(parent_controller, 'schema_form_container', None) is not None:
            safe_remove_widget(layout, parent_controller.schema_form_container)
            parent_controller.schema_form_container = None

        parent_controller.sample_form_widget = None
        parent_controller.schema_form_widget = None

        # --- データセット情報取得 ---
        dataset_item = combo.itemData(idx, 0x0100)
        if not (dataset_item and hasattr(dataset_item, 'get')):
            return
        dataset_id = dataset_item.get('id', '')
        dataset_json_path = get_dynamic_file_path(f'output/rde/data/datasets/{dataset_id}.json')
        dataset_data = None
        group_id = ""
        notes: list[str] = []
        if not os.path.exists(dataset_json_path):
            notes.append("データセットJSONが存在しません")
            # UI側で原因を可視化（エラー詳細）
            if hasattr(parent_controller, 'data_owner_combo') and parent_controller.data_owner_combo:
                combo_owner = parent_controller.data_owner_combo
                combo_owner.clear()
                combo_owner.addItem("データセットJSONなし（詳細（エラー）を確認）", None)
                combo_owner.setEnabled(False)
            ctx = _build_owner_debug_context(
                dataset_id=str(dataset_id or ""),
                dataset_json_path=str(dataset_json_path or ""),
                dataset_data=None,
                group_id="",
                members=None,
                notes=notes,
            )
            ctx["is_error"] = True
            _set_owner_detail_button_state(is_error=True, context=ctx)
            return

        try:
            with open(dataset_json_path, 'r', encoding='utf-8') as f:
                dataset_data = json.load(f)
            relationships = (dataset_data or {}).get("data", {}).get('relationships', {})
            group = relationships.get('group', {}).get('data', {})
            group_id = group.get('id', '')
        except Exception as e:
            notes.append(f"データセットJSONの読み込みに失敗: {e}")
            if hasattr(parent_controller, 'data_owner_combo') and parent_controller.data_owner_combo:
                combo_owner = parent_controller.data_owner_combo
                combo_owner.clear()
                combo_owner.addItem("データセットJSON読込エラー（詳細（エラー）を確認）", None)
                combo_owner.setEnabled(False)
            ctx = _build_owner_debug_context(
                dataset_id=str(dataset_id or ""),
                dataset_json_path=str(dataset_json_path or ""),
                dataset_data=None,
                group_id="",
                members=None,
                notes=notes,
            )
            ctx["is_error"] = True
            _set_owner_detail_button_state(is_error=True, context=ctx)
            return

        # --- データ所有者（所属）コンボボックス更新 ---
        if hasattr(parent_controller, 'data_owner_combo') and parent_controller.data_owner_combo:
            combo_owner = parent_controller.data_owner_combo
            combo_owner.clear()
            combo_owner.addItem("選択してください...", None)
            
            if group_id:
                try:
                    members, members_debug = load_group_members_with_debug(group_id)
                    current_user_id = get_current_user_id()
                    default_index = 0
                    if not members:
                        notes.append("サブグループメンバーが0件です")
                        combo_owner.clear()
                        combo_owner.addItem("メンバー0件（詳細（エラー）を確認）", None)
                        combo_owner.setEnabled(False)
                        ctx = _build_owner_debug_context(
                            dataset_id=str(dataset_id or ""),
                            dataset_json_path=str(dataset_json_path or ""),
                            dataset_data=dataset_data if isinstance(dataset_data, dict) else None,
                            group_id=str(group_id or ""),
                            members=[],
                            notes=notes,
                        )
                        ctx["is_error"] = True
                        ctx["members_debug"] = members_debug
                        _set_owner_detail_button_state(is_error=True, context=ctx)
                    else:
                        # 詳細不足（attributes が空）を検知
                        has_any_details = False
                        for m in members:
                            if not isinstance(m, dict):
                                continue
                            attrs = m.get('attributes', {}) if isinstance(m.get('attributes', {}), dict) else {}
                            if attrs.get('userName') or attrs.get('organizationName') or attrs.get('name'):
                                has_any_details = True
                                break
                        if not has_any_details:
                            notes.append("メンバー詳細（userName/organizationName）が取得できていません（IDのみ表示）")
                            ctx = _build_owner_debug_context(
                                dataset_id=str(dataset_id or ""),
                                dataset_json_path=str(dataset_json_path or ""),
                                dataset_data=dataset_data if isinstance(dataset_data, dict) else None,
                                group_id=str(group_id or ""),
                                members=members,
                                notes=notes,
                            )
                            ctx["is_error"] = False
                            ctx["members_debug"] = members_debug
                            _set_owner_detail_button_state(is_error=False, context=ctx)
                        else:
                            ctx = _build_owner_debug_context(
                                dataset_id=str(dataset_id or ""),
                                dataset_json_path=str(dataset_json_path or ""),
                                dataset_data=dataset_data if isinstance(dataset_data, dict) else None,
                                group_id=str(group_id or ""),
                                members=members,
                                notes=notes,
                            )
                            ctx["is_error"] = False
                            ctx["members_debug"] = members_debug
                            _set_owner_detail_button_state(is_error=False, context=ctx)
                    
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

                    # 詳細ダイアログで「実際にリストにエントリーされた要素」を強調するために保存
                    try:
                        ctx = getattr(parent_controller, "_data_owner_debug_context", None)
                        if isinstance(ctx, dict):
                            ctx["combo_entries"] = [
                                {
                                    "user_id": str(combo_owner.itemData(j) or ""),
                                    "text": str(combo_owner.itemText(j) or ""),
                                }
                                for j in range(combo_owner.count())
                                if j > 0
                            ]
                    except Exception:
                        pass
                    
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
                    notes.append(f"メンバー取得エラー: {e}")
                    ctx = _build_owner_debug_context(
                        dataset_id=str(dataset_id or ""),
                        dataset_json_path=str(dataset_json_path or ""),
                        dataset_data=dataset_data if isinstance(dataset_data, dict) else None,
                        group_id=str(group_id or ""),
                        members=None,
                        notes=notes,
                    )
                    ctx["is_error"] = True
                    _set_owner_detail_button_state(is_error=True, context=ctx)
            else:
                combo_owner.addItem("グループ情報なし", None)
                combo_owner.setEnabled(False)
                notes.append("dataset.json の relationships.group.data.id が空です")
                ctx = _build_owner_debug_context(
                    dataset_id=str(dataset_id or ""),
                    dataset_json_path=str(dataset_json_path or ""),
                    dataset_data=dataset_data if isinstance(dataset_data, dict) else None,
                    group_id="",
                    members=None,
                    notes=notes,
                )
                ctx["is_error"] = True
                _set_owner_detail_button_state(is_error=True, context=ctx)

        # --- 試料フォーム生成（常に基本情報の次に挿入） ---
        try:
            parent_controller.sample_form_widget = create_sample_form(widget, group_id, parent_controller)
            if parent_controller.sample_form_widget:
                # データセット選択(0), ドロップダウン(1), 他機能連携(2), 基本情報(3)の次に挿入
                sample_section = QWidget(widget)
                sample_section_layout = QVBoxLayout(sample_section)
                sample_section_layout.setContentsMargins(0, 0, 0, 0)
                sample_section_layout.setSpacing(6)

                sample_header = QWidget(sample_section)
                sample_header_layout = QHBoxLayout(sample_header)
                sample_header_layout.setContentsMargins(0, 0, 0, 0)
                sample_header_layout.setSpacing(8)

                sample_title = QLabel("試料情報", sample_header)
                sample_title.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;"
                )

                sample_mode_btn = QPushButton(sample_header)
                sample_mode_btn.setObjectName("sample_toggle_button")
                sample_mode_btn.setCheckable(True)
                sample_mode_btn.setChecked(False)  # デフォルト: 必須項目のみ表示
                sample_mode_btn.setToolTip("クリックで表示項目を切り替えます")
                sample_mode_btn.setStyleSheet(
                    "QPushButton {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};"
                    f"  color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};"
                    f"  border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};"
                    "  border-radius: 6px;"
                    "  padding: 2px 10px;"
                    "  min-height: 24px;"
                    "}"
                    "QPushButton:hover {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};"
                    "}"
                    "QPushButton:checked {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};"
                    f"  color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};"
                    f"  border: 1px solid {get_color(ThemeKey.BUTTON_INFO_BORDER)};"
                    "}"
                    "QPushButton:checked:hover {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};"
                    "}"
                )

                def _apply_sample_mode() -> None:
                    widgets = getattr(parent_controller, 'sample_input_widgets', None) or {}

                    show_all = bool(sample_mode_btn.isChecked())
                    # ラベルは「切り替え先（次にする動作）」が分かる文言にする
                    sample_mode_btn.setText("必須項目のみ表示する" if show_all else "全項目表示に切り替える")

                    # 試料名の「追加」ボタンは全項目表示のときのみ表示
                    try:
                        name_widget = widgets.get('name')
                        if name_widget is not None and hasattr(name_widget, 'set_add_button_visible'):
                            name_widget.set_add_button_visible(show_all)
                        elif name_widget is not None:
                            add_btn = name_widget.findChild(QPushButton, 'sample_name_add_button')
                            if add_btn is not None:
                                add_btn.setVisible(show_all)
                    except Exception:
                        pass

                    # 必須項目（新規/選択、試料名、試料管理者、匿名化）は常時表示
                    optional_keys = (
                        'description_label', 'description',
                        'composition_label', 'composition',
                        'url_label', 'url',
                        'tags_label', 'tags',
                        'related_samples_label', 'related_samples',
                    )
                    for key in optional_keys:
                        w = widgets.get(key)
                        if w is None:
                            continue
                        try:
                            w.setVisible(show_all)
                        except Exception:
                            pass

                sample_mode_btn.toggled.connect(lambda *_: _apply_sample_mode())

                sample_header_layout.addWidget(sample_title, 1)
                sample_header_layout.addWidget(sample_mode_btn, 0, Qt.AlignRight)
                sample_section_layout.addWidget(sample_header)

                # グループボックスの二重見出しを抑制（可能なら）
                try:
                    if hasattr(parent_controller.sample_form_widget, 'setTitle'):
                        parent_controller.sample_form_widget.setTitle("")
                except Exception:
                    pass
                sample_section_layout.addWidget(parent_controller.sample_form_widget)

                _apply_sample_mode()
                parent_controller.sample_form_container = sample_section

                layout.insertWidget(4, sample_section)
                sample_section.setVisible(True)
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
                # 一瞬だけ別ウィンドウとして表示されるのを防ぐため、親とフラグを再強制してからレイアウトへ挿入する。
                try:
                    form.setVisible(False)
                    form.setParent(widget)
                    form.setWindowFlags(Qt.Widget)
                    form.setWindowModality(Qt.NonModal)
                except Exception:
                    pass

                try:
                    widget.setUpdatesEnabled(False)
                except Exception:
                    pass
                # 固有情報は全て任意入力のため、フォーム表示/最小化トグルにする。
                # 最小化時も枠線（領域の枠）を残すため、外枠は QGroupBox で保持する。
                schema_group = QGroupBox(widget)
                schema_group.setObjectName("schema_form_group")
                try:
                    schema_group.setTitle("")
                except Exception:
                    pass
                schema_group.setStyleSheet(
                    "QGroupBox {"
                    f"  border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)};"
                    "  border-radius: 6px;"
                    "  margin-top: 6px;"
                    "}"
                )

                schema_section = QWidget(schema_group)
                schema_section_layout = QVBoxLayout(schema_section)
                schema_section_layout.setContentsMargins(10, 8, 10, 8)
                schema_section_layout.setSpacing(6)

                schema_group_layout = QVBoxLayout(schema_group)
                schema_group_layout.setContentsMargins(0, 0, 0, 0)
                schema_group_layout.setSpacing(0)
                schema_group_layout.addWidget(schema_section)

                schema_header = QWidget(schema_section)
                schema_header_layout = QHBoxLayout(schema_header)
                schema_header_layout.setContentsMargins(0, 0, 0, 0)
                schema_header_layout.setSpacing(8)

                schema_title = QLabel("固有情報", schema_header)
                schema_title.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;"
                )

                schema_mode_btn = QPushButton(schema_header)
                schema_mode_btn.setObjectName("schema_toggle_button")
                schema_mode_btn.setCheckable(True)
                schema_mode_btn.setChecked(False)  # デフォルト: 最小化
                schema_mode_btn.setToolTip("クリックで入力フォームの表示/最小化を切り替えます")
                schema_mode_btn.setStyleSheet(
                    "QPushButton {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};"
                    f"  color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};"
                    f"  border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};"
                    "  border-radius: 6px;"
                    "  padding: 2px 10px;"
                    "  min-height: 24px;"
                    "}"
                    "QPushButton:hover {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};"
                    "}"
                    "QPushButton:checked {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};"
                    f"  color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};"
                    f"  border: 1px solid {get_color(ThemeKey.BUTTON_INFO_BORDER)};"
                    "}"
                    "QPushButton:checked:hover {"
                    f"  background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};"
                    "}"
                )

                schema_header_layout.addWidget(schema_title, 1)
                schema_header_layout.addWidget(schema_mode_btn, 0, Qt.AlignRight)
                schema_section_layout.addWidget(schema_header)

                schema_summary_label = QLabel("", schema_section)
                schema_summary_label.setObjectName("schema_summary_label")
                schema_summary_label.setWordWrap(True)
                schema_summary_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_SECONDARY)};"
                )
                schema_section_layout.addWidget(schema_summary_label)

                # グループボックスの二重見出しを抑制（可能なら）
                try:
                    if hasattr(form, 'setTitle'):
                        form.setTitle("")
                except Exception:
                    pass
                schema_section_layout.addWidget(form)

                def _get_schema_value(w) -> str:
                    try:
                        if hasattr(w, 'currentText'):
                            return (w.currentText() or '').strip()
                        if hasattr(w, 'text'):
                            return (w.text() or '').strip()
                    except Exception:
                        return ''
                    return ''

                def _schema_summary_text() -> str:
                    # 可能なら schema_form_util 側で構築した key->widget/label を使って安定表示。
                    key_to_widget = getattr(form, '_schema_key_to_widget', {}) or {}
                    key_to_label = getattr(form, '_schema_key_to_label_widget', {}) or {}

                    parts: list[str] = []

                    if isinstance(key_to_widget, dict) and key_to_widget:
                        for key, w in key_to_widget.items():
                            if w is None:
                                continue
                            val = _get_schema_value(w)
                            label_text = None
                            try:
                                lw = key_to_label.get(key)
                                if lw is not None and hasattr(lw, 'text'):
                                    label_text = (lw.text() or '').strip()
                            except Exception:
                                label_text = None
                            label = label_text or str(key)
                            display = val if val else "（未入力）"
                            parts.append(f"{label}={display}")

                    # フォールバック（極力落ちないように）
                    if not parts:
                        try:
                            # QLineEdit / QComboBox を列挙（空の場合も未入力として列挙）
                            for w in (form.findChildren(QLineEdit) + form.findChildren(QComboBox)):
                                val = _get_schema_value(w)
                                name = (w.objectName() or w.placeholderText() or w.__class__.__name__).strip()
                                if not name:
                                    continue
                                display = val if val else "（未入力）"
                                parts.append(f"{name}={display}")
                        except Exception:
                            parts = []

                    if parts:
                        return "設定内容: " + "、".join(parts)
                    return "設定内容: （項目なし）"

                def _apply_schema_form_visibility() -> None:
                    expanded = bool(schema_mode_btn.isChecked())
                    # ラベルは「切り替え先（次にする動作）」が分かる文言にする
                    schema_mode_btn.setText("入力フォームを最小化" if expanded else "入力フォームを表示")
                    try:
                        form.setVisible(bool(expanded))
                    except Exception:
                        pass
                    try:
                        schema_summary_label.setVisible(not bool(expanded))
                        if not expanded:
                            schema_summary_label.setText(_schema_summary_text())
                    except Exception:
                        pass

                def _refresh_schema_summary_if_needed() -> None:
                    # 最小化中だけサマリを更新
                    try:
                        if bool(schema_mode_btn.isChecked()):
                            return
                        schema_summary_label.setText(_schema_summary_text())
                    except Exception:
                        return

                schema_mode_btn.toggled.connect(lambda *_: _apply_schema_form_visibility())
                _apply_schema_form_visibility()

                try:
                    for w in getattr(form, '_schema_key_to_widget', {}).values():
                        if hasattr(w, 'textChanged'):
                            w.textChanged.connect(lambda *_: _refresh_schema_summary_if_needed())
                        if hasattr(w, 'currentIndexChanged'):
                            w.currentIndexChanged.connect(lambda *_: _refresh_schema_summary_if_needed())
                except Exception:
                    pass

                parent_controller.schema_form_container = schema_group

                layout.insertWidget(5, schema_group)
                schema_form_widget = form
                parent_controller.schema_form_widget = schema_form_widget

                try:
                    widget.setUpdatesEnabled(True)
                except Exception:
                    pass
                try:
                    widget.update()
                except Exception:
                    pass
                
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

    from classes.utils.dataset_launch_manager import DatasetLaunchManager, DatasetPayload

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

    def _resolve_group_id_for_launch(dataset_id: str, raw_dataset: dict | None) -> str:
        # 可能なら listing 側の relationships から先に試す
        if isinstance(raw_dataset, dict):
            try:
                rel = raw_dataset.get("relationships") or {}
                gid = (((rel.get("group") or {}).get("data") or {}).get("id") or "")
                if gid:
                    return str(gid)
            except Exception:
                pass

        dataset_id = str(dataset_id or "").strip()
        if not dataset_id:
            return ""

        dataset_path = get_dynamic_file_path(f"output/rde/data/datasets/{dataset_id}.json")
        if not dataset_path or not os.path.exists(dataset_path):
            return ""
        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            group_data = (
                (((payload.get("data") or {}).get("relationships") or {}).get("group") or {}).get("data")
                or {}
            )
            if isinstance(group_data, dict):
                return str(group_data.get("id") or "")
        except Exception:
            pass
        return ""

    def _launch_to_subgroup_edit() -> None:
        payload = _get_current_dataset_payload_for_launch()
        if not payload:
            QMessageBox.warning(widget, "データセット未選択", "連携するデータセットを選択してください。")
            return

        group_id = _resolve_group_id_for_launch(payload["dataset_id"], payload.get("raw_dataset"))
        if not group_id:
            QMessageBox.warning(widget, "サブグループ未解決", "選択中データセットのサブグループIDを取得できませんでした。")
            return

        logger.info(
            "data_register: launch request target=subgroup_edit group_id=%s dataset_id=%s",
            group_id,
            payload["dataset_id"],
        )

        try:
            parent_controller.switch_mode("subgroup_create")
        except Exception:
            QMessageBox.warning(widget, "画面遷移失敗", "サブグループ画面へ遷移できませんでした。")
            return

        def _try_focus() -> None:
            try:
                root = None
                host = getattr(parent_controller, "parent", None)
                layout = getattr(host, "menu_area_layout", None)
                if layout is not None and hasattr(layout, "count") and layout.count() > 0:
                    item = layout.itemAt(layout.count() - 1)
                    root = item.widget() if item is not None else None

                if root is not None and hasattr(root, "focus_edit_subgroup_by_id"):
                    ok = bool(root.focus_edit_subgroup_by_id(group_id))
                    if not ok:
                        QMessageBox.information(
                            widget,
                            "サブグループ選択",
                            "サブグループ画面へ遷移しましたが、指定IDの自動選択に失敗しました。\n"
                            "閲覧・修正タブで手動選択してください。",
                        )
            except Exception:
                logger.debug("data_register: focus subgroup edit failed", exc_info=True)

        QTimer.singleShot(0, _try_focus)

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

    # 他機能連携ボタン（サブグループ閲覧・修正）
    launch_subgroup_edit_button = QPushButton("サブグループ閲覧・修正")
    launch_subgroup_edit_button.setStyleSheet(launch_button_style)
    launch_subgroup_edit_button.clicked.connect(_launch_to_subgroup_edit)
    launch_controls_layout.addWidget(launch_subgroup_edit_button)

    launch_controls_layout.addStretch()
    launch_controls_widget.setLayout(launch_controls_layout)

    widget._dataset_launch_buttons = [
        launch_dataset_edit_button,
        launch_dataset_dataentry_button,
        launch_subgroup_edit_button,
    ]  # type: ignore[attr-defined]

    # テーマ切替時に「他機能連携」の個別styleSheetを再適用（更新漏れ対策）
    try:
        from classes.utils.launch_ui_styles import apply_launch_controls_theme, bind_launch_controls_to_theme

        apply_launch_controls_theme(launch_label, widget._dataset_launch_buttons)
        bind_launch_controls_to_theme(launch_label, widget._dataset_launch_buttons)
    except Exception:
        pass

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
    required_missing_label = QLabel("未入力必須項目有り", widget)
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

    # 並列アップロード数（uploads 並列化）
    parallel_layout = QHBoxLayout()
    parallel_layout.setSpacing(8)
    parallel_label = QLabel("並列アップロード数", widget)
    parallel_spinbox = QSpinBox(widget)
    parallel_spinbox.setRange(1, 20)
    parallel_spinbox.setValue(5)
    parallel_spinbox.setToolTip("uploads へのアップロード並列数（既定: 5）")
    parallel_layout.addWidget(parallel_label)
    parallel_layout.addWidget(parallel_spinbox)
    parallel_layout.addStretch()

    # controller / widget から参照できるように保持
    parent_controller.parallel_upload_spinbox = parallel_spinbox
    widget.parallel_upload_spinbox = parallel_spinbox
    layout.addLayout(parallel_layout)

    # 最後にStretchを追加
    layout.addStretch()
    
    # レスポンシブデザイン対応
    widget.setMinimumWidth(600)  # 最小幅設定
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    

    # NOTE: 表示/非表示は呼び出し側（タブ/レイアウト）に委ねる。
    
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
    from qt_compat.widgets import QPushButton
    owner_error_btn = QPushButton("詳細")
    owner_error_btn.setObjectName("data_owner_error_button")
    owner_error_btn.setVisible(True)
    owner_error_btn.setEnabled(False)
    owner_error_btn.setToolTip("データ所有者（所属）の候補生成で参照したJSON/キーを表示します")
    try:
        owner_error_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    except Exception:
        pass
    try:
        owner_error_btn.setFixedWidth(owner_error_btn.sizeHint().width())
    except Exception:
        pass

    owner_row.addWidget(owner_label)
    owner_row.addWidget(owner_error_btn)
    owner_row.addWidget(owner_combo)
    layout.addLayout(owner_row)

    widgets = {
        "data_name": name_input,
        "data_desc": desc_input,
        "exp_id": expid_input,
        "data_owner": owner_combo,
        "data_owner_label": owner_label,
        "data_owner_error_button": owner_error_btn,
    }
    return group_box, widgets

# 補助関数: データ説明欄の値取得
def get_data_desc_value(desc_input):
    # QTextEditの場合はtoPlainText()、QLineEditの場合はtext()
    if hasattr(desc_input, 'toPlainText'):
        return desc_input.toPlainText()
    return desc_input.text()
