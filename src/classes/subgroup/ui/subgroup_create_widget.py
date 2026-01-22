import os
import json
import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton, QHBoxLayout, 
    QMessageBox, QTabWidget, QDialog, QApplication, QComboBox, QSizePolicy
)
from ..core import subgroup_api_helper
from ..util.subgroup_ui_helpers import (
    SubgroupFormBuilder, SubgroupCreateHandler, MemberDataProcessor,
    show_selected_user_ids, load_user_entries, prepare_subgroup_create_request
)
from .subgroup_listing_widget import create_subgroup_listing_widget
from classes.theme import get_color, ThemeKey
from classes.utils.label_style import apply_label_style
from .subgroup_inherit_dialog import (
    GRANT_NUMBER_NOT_INHERITED_MESSAGE,
    SubgroupInheritDialog,
    build_subjects_with_grant_number_placeholder,
)

# ロガー設定
logger = logging.getLogger(__name__)



def create_subgroup_create_widget(parent, title, color, create_auto_resize_button):
    """サブグループ作成・修正のタブ付きウィジェット"""
    
    # メインコンテナ
    main_widget = QWidget()
    main_layout = QVBoxLayout()
    
    # タイトル
    label = QLabel(f"{title}機能")
    apply_label_style(label, get_color(ThemeKey.TEXT_PRIMARY), bold=True, point_size=16)
    #main_layout.addWidget(label)
    
    # タブウィジェット
    tab_widget = QTabWidget()
    
    # 新規作成タブ
    create_tab = create_original_subgroup_create_widget(parent, title, color, create_auto_resize_button)
    tab_widget.addTab(create_tab, "新規作成")
    
    # 修正タブ（遅延ロード：初回表示を軽くする）
    edit_tab = None
    edit_scroll = None
    edit_built = False

    # タブ切り替え時にサブグループリストをリフレッシュする機能を追加
    def _reset_window_height_to_screen(target_widget: QWidget) -> None:
        try:
            window = target_widget.window() if target_widget is not None else None
            if window is None:
                return
            screen = getattr(window, 'screen', None)
            if callable(screen):
                screen = screen()
            if screen is None:
                # fallback
                screen = QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
            # 縦サイズのみディスプレイに合わせる（その後はユーザーが変更可能）
            window.resize(window.width(), available.height())
        except Exception:
            logger.debug("subgroup_create: window height reset failed", exc_info=True)

    try:
        edit_scroll = QScrollArea()
        edit_scroll.setWidgetResizable(True)
        edit_scroll.setFrameStyle(0)
        edit_scroll.setContentsMargins(0, 0, 0, 0)
        placeholder = QLabel("閲覧・修正タブを読み込み中...")
        placeholder.setWordWrap(True)
        edit_scroll.setWidget(placeholder)
        tab_widget.addTab(edit_scroll, "閲覧・修正")
    except Exception as e:
        logger.warning("サブグループ修正タブのプレースホルダ作成に失敗: %s", e)
        edit_scroll = None

    # 一覧タブ（軽量・即時ロード）
    try:
        # parent は UIController 等(QWIdgetでない)が渡るケースがあるため、QTabWidget を親にする
        listing_tab = create_subgroup_listing_widget(tab_widget)
        tab_widget.addTab(listing_tab, "一覧")
    except Exception as e:
        logger.warning("サブグループ一覧タブの作成に失敗: %s", e)

    def _ensure_edit_tab_built() -> None:
        nonlocal edit_tab, edit_built
        if edit_built:
            return
        if edit_scroll is None:
            return
        try:
            from .subgroup_edit_widget import create_subgroup_edit_widget

            edit_tab = create_subgroup_edit_widget(parent, "サブグループ修正", color, create_auto_resize_button)
            edit_scroll.setWidget(edit_tab)
            edit_built = True
        except Exception as e:
            logger.warning("サブグループ修正タブの作成に失敗: %s", e)
            try:
                fallback = QLabel(f"閲覧・修正タブの読み込みに失敗しました: {e}")
                fallback.setWordWrap(True)
                edit_scroll.setWidget(fallback)
            except Exception:
                pass
            edit_built = True

    def on_tab_changed(index):
        """タブ切り替え時の処理"""
        try:
            current_text = ""
            try:
                current_text = tab_widget.tabText(index)
            except Exception:
                current_text = ""

            # 閲覧・修正タブが選択された場合
            if current_text == "閲覧・修正":
                _ensure_edit_tab_built()
                logger.info("修正タブが選択されました - サブグループリストをリフレッシュします")
                if edit_tab is not None and hasattr(edit_tab, '_refresh_subgroup_list'):
                    edit_tab._refresh_subgroup_list()
                    logger.info("サブグループリストのリフレッシュが完了しました")
                else:
                    logger.debug("サブグループリフレッシュ機能がスキップされました (edit_tab=%s)", edit_tab is not None)

                if edit_scroll is not None:
                    _reset_window_height_to_screen(edit_scroll)
        except Exception as e:
            logger.error("タブ切り替え時のリフレッシュ処理でエラー: %s", e)

    tab_widget.currentChanged.connect(on_tab_changed)

    # 外部連携用（データ登録→サブグループ閲覧・修正ジャンプ等）
    main_widget.tab_widget = tab_widget  # type: ignore[attr-defined]

    def focus_edit_subgroup_by_id(group_id: str) -> bool:
        group_id = str(group_id or "").strip()
        if not group_id:
            return False

        try:
            edit_index = -1
            for i in range(tab_widget.count()):
                if tab_widget.tabText(i) == "閲覧・修正":
                    edit_index = i
                    break
            if edit_index < 0:
                return False

            tab_widget.setCurrentIndex(edit_index)
            _ensure_edit_tab_built()

            if edit_tab is None:
                return False

            selector = getattr(edit_tab, "_subgroup_selector", None)
            if selector is not None and hasattr(selector, "select_group_by_id"):
                try:
                    # 一覧が古い可能性があるため、必要に応じて更新
                    refresh = getattr(edit_tab, "_refresh_subgroup_list", None)
                    if callable(refresh):
                        refresh()
                except Exception:
                    pass
                return bool(selector.select_group_by_id(group_id, prompt_clear_filter=True))
        except Exception:
            logger.debug("subgroup_create: focus_edit_subgroup_by_id failed", exc_info=True)

        return False

    main_widget.focus_edit_subgroup_by_id = focus_edit_subgroup_by_id  # type: ignore[attr-defined]
    
    main_layout.addWidget(tab_widget)
    main_widget.setLayout(main_layout)
    
    return main_widget

def create_original_subgroup_create_widget(parent, title, color, create_auto_resize_button):
    widget = QWidget()
    # 既存レイアウトがあればクリア
    if widget.layout() is not None:
        QWidget().setLayout(widget.layout())
    layout = QVBoxLayout()
    label = QLabel(f"{title}機能")
    apply_label_style(label, get_color(ThemeKey.TEXT_PRIMARY), bold=True, point_size=16)
    #layout.addWidget(label)

    button_style = f"background-color: {color}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; border-radius: 6px;"

    # --- 既存サブグループ読込（新規作成タブ最上段） ---
    # 閲覧・修正タブのフィルタ+コンボ実装を参照し、同等のUIを提供する
    existing_load_panel = QWidget()
    existing_load_panel.setObjectName("existingSubgroupLoadPanel")
    existing_load_panel.setStyleSheet(
        f"QWidget#existingSubgroupLoadPanel {{ "
        f"background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; "
        f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; "
        f"border-radius: 6px; "
        f"}}"
    )
    existing_load_layout = QVBoxLayout(existing_load_panel)
    existing_load_layout.setContentsMargins(10, 8, 10, 8)
    existing_load_layout.setSpacing(6)

    existing_load_title = QLabel("既存サブグループ読込")
    apply_label_style(existing_load_title, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    existing_load_layout.addWidget(existing_load_title)

    filter_row = QHBoxLayout()
    filter_label = QLabel("表示フィルタ:")
    filter_combo = QComboBox()
    filter_combo.setObjectName("existingSubgroupFilterCombo")
    filter_combo.addItem("OWNER", "owner")
    filter_combo.addItem("OWNER+ASSISTANT", "both")
    filter_combo.addItem("ASSISTANT", "assistant")
    filter_combo.addItem("MEMBER", "member")
    filter_combo.addItem("AGENT", "agent")
    filter_combo.addItem("VIEWER", "viewer")
    filter_combo.addItem("フィルタ無し", "none")
    filter_combo.setCurrentIndex(0)
    filter_row.addWidget(filter_label)
    filter_row.addWidget(filter_combo)

    refresh_btn = QPushButton("サブグループリスト更新")
    refresh_btn.setObjectName("existingSubgroupRefreshButton")
    filter_row.addWidget(refresh_btn)
    filter_row.addStretch()
    existing_load_layout.addLayout(filter_row)

    existing_group_combo = QComboBox()
    existing_group_combo.setObjectName("existingSubgroupCombo")
    existing_group_combo.setEditable(True)
    existing_group_combo.setInsertPolicy(QComboBox.NoInsert)
    existing_group_combo.setMaxVisibleItems(12)
    try:
        existing_group_combo.view().setMinimumHeight(240)
    except Exception:
        pass
    existing_group_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    load_row = QHBoxLayout()
    load_row.addWidget(existing_group_combo, 1)
    load_btn = QPushButton("読込")
    load_btn.setObjectName("existingSubgroupLoadButton")
    load_btn.setFixedWidth(80)
    load_row.addWidget(load_btn)
    existing_load_layout.addLayout(load_row)

    existing_desc_label = QLabel("")
    existing_desc_label.setObjectName("existingSubgroupDescriptionLabel")
    existing_desc_label.setWordWrap(True)
    existing_desc_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
    existing_load_layout.addWidget(existing_desc_label)

    layout.addWidget(existing_load_panel)

    # --- メンバー選択部（共通化コード使用） ---
    from config.common import OUTPUT_RDE_DIR, INPUT_DIR
    from ..util.subgroup_member_selector_common import create_common_subgroup_member_selector
    from ..core import subgroup_api_helper
    from core.bearer_token_manager import BearerTokenManager
    
    # Bearer token取得
    bearer_token = BearerTokenManager.get_valid_token()
    
    # 統合メンバーリスト取得（rde-member.txt + subGroup.json + API補完）
    unified_users, member_info_map = subgroup_api_helper.load_unified_member_list(
        subgroup_id=None,  # 新規作成時はNone
        dynamic_users=None,
        bearer_token=bearer_token
    )
    
    logger.debug("新規作成タブ: 統合メンバーリスト取得完了 - %s名", len(unified_users))
    
    # rde-member.txtからロール情報を抽出
    initial_roles = {}
    prechecked_user_ids = set()
    
    for user in unified_users:
        user_id = user.get('id')
        if user_id:
            # rde-member.txtから来たユーザーの場合、ロール情報を設定
            if 'role_from_file' in user:
                initial_roles[user_id] = user.get('role_from_file', 'ASSISTANT')
                prechecked_user_ids.add(user_id)
    
    logger.debug("新規作成タブ: 初期ロール設定完了 - %s名", len(initial_roles))
    
    # 共通化されたメンバー選択ウィジェット作成（統合ユーザーリストを使用）
    member_selector = create_common_subgroup_member_selector(
        initial_roles=initial_roles, 
        prechecked_user_ids=prechecked_user_ids,
        show_filter=True,  # 新規作成タブではフィルタを表示
        user_entries=unified_users  # 統合ユーザーリストを渡す
    )
    
    # widget参照用の属性設定（既存コードとの互換性維持）
    widget.user_rows = member_selector.user_rows
    widget.owner_radio_group = member_selector.owner_radio_group
    widget.member_selector = member_selector  # 共通セレクターへの参照を保持
    
    # スクロールエリア設定（余白を最小化、画面サイズ対応）
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameStyle(0)  # フレームを削除
    scroll.setContentsMargins(0, 0, 0, 0)  # スクロールエリアの余白を削除
    
    # スクロールエリアのスタイルシートで余白を完全に削除
    scroll.setStyleSheet("""
        QScrollArea {
            border: none;
            margin: 0px;
            padding: 0px;
        }
    """)
    
    member_selector.setMinimumWidth(520)
    member_selector.setMaximumWidth(800)
    scroll.setMinimumWidth(520)  # スクロールエリア幅も調整
    scroll.setMaximumWidth(800)  # 余分な余白を削除
    
    # 余白はできるだけメンバー領域が消費し、スクロールバーを出しにくくする
    scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    # メインウィンドウサイズ調整（親ウィジェットから辿る）- 画面サイズ制限付き
    try:
        main_window = widget
        while main_window.parent() is not None:
            main_window = main_window.parent()
        
        if hasattr(main_window, 'resize'):
            # 画面サイズを取得
            from qt_compat.widgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            max_window_height = int(screen.height() * 0.9)  # 画面の90%まで
            
            current_width = main_window.width()
            # 基本高さ + 必要な追加分を計算
            base_height = 600  # より小さい基本高さ
            additional_height = max(0, (member_count - 8) * 20)  # 8人を超える場合のみ追加
            calculated_height = base_height + additional_height
            
            # 画面の90%を超えないように制限
            new_height = min(calculated_height, max_window_height)
            main_window.resize(current_width, new_height)
            
            logger.debug("ウィンドウサイズ調整: %s → %s (画面制限: %s)", calculated_height, new_height, max_window_height)
            
    except Exception as e:
        # ウィンドウサイズ調整に失敗してもメンバー表示は続行
        pass
    
    # メンバーセレクターのラベルとスクロールエリアを余白なしで配置
    member_layout = QVBoxLayout()
    member_layout.setContentsMargins(0, 0, 0, 0)  # 完全に余白を削除
    member_layout.setSpacing(2)  # ラベルとテーブル間のスペースを最小化
    
    member_label = QLabel("グループメンバー選択（複数可）:")
    apply_label_style(member_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    member_layout.addWidget(member_label)
    # stretch=1 で余白を優先的に消費
    member_layout.addWidget(scroll, 1)
    
    layout.addLayout(member_layout)
    scroll.setWidget(member_selector)

    def _adjust_scroll_height_for_selector(selector_widget) -> None:
        try:
            screen = QApplication.primaryScreen().geometry()
            # できるだけスクロールを抑制するため、上限を少し大きめに取る
            max_scroll_height = int(screen.height() * 0.55)

            hinted = 0
            try:
                hinted = int(selector_widget.sizeHint().height())
            except Exception:
                hinted = 0

            member_count = len(getattr(selector_widget, "user_rows", []) or [])
            estimated = 47 + (member_count * 22)
            desired = max(hinted, estimated)

            # 小人数でもテーブルが見えない事故を防ぐ
            min_h = max(220, min(desired, max_scroll_height))
            scroll.setMinimumHeight(min_h)
            scroll.setMaximumHeight(max_scroll_height)
        except Exception:
            pass

    def _apply_inherited_members(group_data: dict) -> None:
        try:
            from ..util.subgroup_member_selector_common import (
                create_common_subgroup_member_selector_with_api_complement,
            )
            from core.bearer_token_manager import BearerTokenManager

            current_roles = {}
            for m in (group_data or {}).get("members", []) or []:
                if isinstance(m, dict) and m.get("id"):
                    current_roles[str(m.get("id"))] = str(m.get("role") or "MEMBER")

            token = BearerTokenManager.get_valid_token()
            new_selector = create_common_subgroup_member_selector_with_api_complement(
                initial_roles=current_roles,
                prechecked_user_ids=set(current_roles.keys()),
                subgroup_id=str((group_data or {}).get("id", "") or ""),
                bearer_token=token,
                show_filter=True,
                disable_internal_scroll=False,
            )

            scroll.setWidget(new_selector)
            widget.user_rows = new_selector.user_rows
            widget.owner_radio_group = new_selector.owner_radio_group
            widget.member_selector = new_selector
            try:
                create_handler.member_selector = new_selector
            except Exception:
                pass
            _adjust_scroll_height_for_selector(new_selector)
        except Exception as e:
            logger.warning("既存サブグループメンバー引継ぎに失敗: %s", e)

    def _apply_inherited_form_values(group_data: dict, form_widgets: dict, options: dict) -> None:
        if options.get("group_name"):
            form_widgets["group_name_edit"].setText(str((group_data or {}).get("name", "") or ""))
        if options.get("description"):
            form_widgets["desc_edit"].setText(str((group_data or {}).get("description", "") or ""))
        if options.get("subjects"):
            subjects_src = (group_data or {}).get("subjects", [])
            subjects = build_subjects_with_grant_number_placeholder(subjects_src)
            if not subjects:
                subjects = [{"grantNumber": GRANT_NUMBER_NOT_INHERITED_MESSAGE, "title": ""}]
            try:
                form_widgets["subjects_widget"].set_subjects_data(subjects)
            except Exception:
                pass
        if options.get("funds") and "funds_widget" in form_widgets:
            funds_src = (group_data or {}).get("funds", [])
            funds_list = []
            if isinstance(funds_src, list):
                for f in funds_src:
                    if isinstance(f, dict):
                        num = f.get("fundNumber", "")
                        if num:
                            funds_list.append(str(num))
                    else:
                        funds_list.append(str(f))
            try:
                form_widgets["funds_widget"].set_funding_numbers(funds_list)
            except Exception:
                pass

    # --- 選択ユーザー/ロール表示ボタン & カスタムメンバー編集ボタン ---
    button_row = QHBoxLayout()
    
    def on_show_selected():
        # 共通セレクターから直接user_rowsとuser_entriesを取得
        current_user_rows = member_selector.user_rows
        current_user_entries = member_selector.user_entries
        show_selected_user_ids(widget, current_user_rows, current_user_entries)
    exec_button = QPushButton("選択ユーザー/ロールを表示")
    exec_button.clicked.connect(on_show_selected)
    button_row.addWidget(exec_button)
    
    def on_edit_rde_member():
        """rde-member.txt編集ダイアログを開く"""
        from .rde_member_editor_dialog import RdeMemberEditorDialog
        dialog = RdeMemberEditorDialog(widget)
        result = dialog.exec()
        if result == QDialog.Accepted:
            # 保存後、メンバーセレクターをリフレッシュ
            QMessageBox.information(widget, "リフレッシュ", "メンバー設定を反映するには、このタブを再度開いてください。")
    
    edit_member_button = QPushButton("カスタムメンバー編集")
    edit_member_button.setToolTip("rde-member.txtのメンバーをGUIで編集")
    edit_member_button.clicked.connect(on_edit_rde_member)
    button_row.addWidget(edit_member_button)
    
    layout.addLayout(button_row)

    # --- 新しいクラスを使用したフォーム構築 ---
    form_builder = SubgroupFormBuilder(layout, create_auto_resize_button, button_style)
    form_widgets = form_builder.build_manual_input_form()
    
    # --- イベントハンドラー作成 ---
    create_handler = SubgroupCreateHandler(widget, parent, member_selector)

    # 既存サブグループ選択ロジック（閲覧・修正タブの SubgroupSelector を参照）
    try:
        from .subgroup_edit_widget import SubgroupSelector

        selector = SubgroupSelector(existing_group_combo, filter_combo, on_selection_changed=None)
        selector.load_existing_subgroups()

        # 新規作成タブでは「選択だけ」で外部チェック等を走らせないため、
        # currentTextChanged 経由のハンドラを外して indexChanged で description を更新する。
        try:
            existing_group_combo.currentTextChanged.disconnect(selector._on_combo_selection_changed)
        except Exception:
            pass

        def _update_selected_subgroup_description() -> None:
            try:
                group_data = existing_group_combo.currentData()
                if isinstance(group_data, dict):
                    desc = str(group_data.get("description", "") or "")
                    existing_desc_label.setText(desc)
                else:
                    existing_desc_label.setText("")
            except Exception:
                existing_desc_label.setText("")

        existing_group_combo.currentIndexChanged.connect(lambda _i: _update_selected_subgroup_description())
        _update_selected_subgroup_description()

        def on_refresh_existing_groups():
            selector.load_existing_subgroups()
            try:
                existing_desc_label.setText("")
            except Exception:
                pass

        refresh_btn.clicked.connect(on_refresh_existing_groups)

        def on_click_load_existing_group():
            group_data = existing_group_combo.currentData()
            if not isinstance(group_data, dict):
                QMessageBox.warning(widget, "選択エラー", "読み込むサブグループを選択してください。")
                return

            dialog = SubgroupInheritDialog(widget, group_data)
            if dialog.exec() != QDialog.Accepted:
                return
            options = dialog.selected_options()

            if options.get("members"):
                _apply_inherited_members(group_data)
            _apply_inherited_form_values(group_data, form_widgets, options)

        load_btn.clicked.connect(on_click_load_existing_group)
    except Exception as e:
        logger.warning("既存サブグループ読込UI初期化に失敗: %s", e)

    def on_create_subgroup_manual(user_entries_param=None):
        # 新しいクラスを使用して入力値とロール情報を取得
        group_name = form_widgets['group_name_edit'].text().strip()
        description = form_widgets['desc_edit'].text().strip()
        subjects = create_handler.extract_subjects_from_widget(form_widgets['subjects_widget'])
        # 研究資金番号を新ウィジェットから取得
        funds = form_widgets['funds_widget'].get_funding_numbers() if 'funds_widget' in form_widgets else []
        
        # ユーザーロール情報の抽出とバリデーション
        selected_user_ids, roles, owner_id, owner_count = create_handler.extract_user_roles()
        
        if not create_handler.validate_owner_selection(owner_count):
            return
            
        if owner_id:
            selected_user_ids = [owner_id] + selected_user_ids
        if not group_name:
            QMessageBox.warning(widget, "入力エラー", "グループ名を入力してください。")
            return
        if not selected_user_ids:
            QMessageBox.warning(widget, "ユーザー未選択", "追加するユーザーを1人以上選択してください。")
            return
            
        # API呼び出し用のペイロード作成
        paths = subgroup_api_helper.check_subgroup_files()
        if paths["missing"]:
            msg = f"必要なファイルが見つかりません: {', '.join(paths['missing'])}\n\n{paths['output_dir']} または {paths['input_dir']} に配置してください。"
            QMessageBox.warning(widget, "ファイル不足", msg)
            print(msg)
            return
            
        try:
            with open(paths["info_path"], encoding="utf-8") as f:
                info = json.load(f)
        except Exception as e:
            QMessageBox.warning(widget, "ファイル読み込みエラー", f"info.jsonの読み込みに失敗: {e}")
            return
            
        parent_id = info.get("project_group_id", "")
        payload = {
            "data": {
                "type": "group",
                "attributes": {
                    "name": group_name,
                    "description": description,
                    "subjects": subjects,
                    "funds": [{"fundNumber": f} for f in funds],
                    "roles": roles
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": parent_id
                        }
                    }
                }
            }
        }
        
        # 確認ダイアログ表示
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        msg_box, yes_btn = create_handler.create_confirmation_dialog(payload, payload_str)
        reply = msg_box.exec()
        
        if msg_box.clickedButton() != yes_btn:
            return
            
        # API送信処理
        api_url = "https://rde-api.nims.go.jp/groups"
        from core.bearer_token_manager import BearerTokenManager
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(widget)
        if not bearer_token:
            QMessageBox.warning(widget, "認証エラー", "Bearerトークンが取得できません。ログイン状態を確認してください。")
            return
            
        headers_dict = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Authorization": f"Bearer {bearer_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        
        # subgroup_api_helper の統一送信関数を使用（通知機能付き）
        success = subgroup_api_helper.send_subgroup_request(widget, api_url, headers_dict, payload, group_name, auto_refresh=True)
        
        if not success:
            logger.error("サブグループ作成に失敗: %s", group_name)
            return
    
    def on_create_subgroup_bulk():
        prepare_subgroup_create_request(widget, parent, member_selector.user_rows)
    
    # ボタン作成
    button_bulk, button_manual = form_builder.build_button_row({
        # 'bulk': on_create_subgroup_bulk,
        'manual': on_create_subgroup_manual
    })

    widget.setLayout(layout)
    return widget
