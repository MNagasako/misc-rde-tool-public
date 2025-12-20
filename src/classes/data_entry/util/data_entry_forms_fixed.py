"""
データ登録フォーム作成ユーティリティ (完全修正版)
正しい3項目構造（試料名、試料の説明、化学式・組成式・分子式）
既存試料選択機能・入力制御機能付き
"""



from .sample_loader import load_existing_samples, format_sample_display_name
from .group_member_loader import load_group_members
from .markdown_editor import MarkdownEditor
from .sample_names_widget import SampleNamesWidget
from .related_samples_widget import RelatedSamplesWidget
from .tag_input_widget import TagInputWidget
from classes.dataset.util.dataset_dropdown_util import get_current_user_id

import logging

# ロガー設定
logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QFrame, QVBoxLayout, QHBoxLayout, QGroupBox, 
        QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QCheckBox
    )
    from qt_compat.core import Qt
except ImportError as e:
    logger.error("PyQt5インポートエラー: %s", e)
    # フォールバック用の空実装
    class QFrame: pass
    class QVBoxLayout: pass



def create_sample_form(parent_widget, group_id=None, parent_controller=None):
    """
    試料フォームを作成 (正しい3項目構造・既存試料選択・入力制御機能付き)
    """
    logger.debug("[FIXED] 試料フォーム作成開始: group_id=%s", group_id)

    # QGroupBox単体を返すことで二重枠を防ぐ
    input_group, input_widgets = _create_sample_input_area(group_id)

    # 選択変更時の処理
    def on_sample_selection_changed():
        current_index = input_widgets["sample_combo"].currentIndex()
        selected_data = None
        if current_index > 0:
            selected_data = input_widgets["sample_combo"].currentData()
        _handle_sample_selection(selected_data, input_widgets)

    input_widgets["sample_combo"].currentIndexChanged.connect(on_sample_selection_changed)
    on_sample_selection_changed()

    if parent_controller:
        parent_controller.sample_input_widgets = input_widgets
        parent_controller.sample_combo = input_widgets["sample_combo"]

    logger.info("[FIXED] 試料フォーム作成完了")
    return input_group

def _create_sample_input_area(group_id=None):
    """
    試料入力エリア作成（新規/選択エリアを含む・正しい3項目構造・入力制御機能付き）
    固有情報エリアと同じ横並びレイアウト・スタイルを適用
    """
    logger.debug("[FIXED] 試料入力エリア作成開始")
    
    input_group = QGroupBox("試料情報")
    # スタイルは親フォーム（DataRegisterTabWidget側で setStyleSheet(get_data_register_form_style())）に追従させる
    input_layout = QVBoxLayout(input_group)
    input_layout.setContentsMargins(8, 8, 8, 8)
    input_layout.setSpacing(6)

    # 新規/選択エリア（横並び）
    select_row = QHBoxLayout()
    select_label = QLabel("新規/選択")
    select_label.setMinimumWidth(120)
    sample_combo = QComboBox()
    sample_combo.setMinimumHeight(24)
    sample_combo.addItem("新規作成", None)
    if group_id:
        try:
            existing_samples = load_existing_samples(group_id)
            logger.debug("[FIXED] 既存試料取得結果: %s件", len(existing_samples))
            for sample in existing_samples:
                display_name = format_sample_display_name(sample)
                sample_combo.addItem(display_name, sample)
            if existing_samples:
                logger.debug("[FIXED] 既存試料をコンボボックスに追加: %s件", len(existing_samples))
            else:
                logger.debug("[FIXED] 既存試料データなし")
        except Exception as e:
            logger.error("[FIXED] 既存試料取得エラー: %s", e)
            sample_combo.addItem("既存試料取得エラー", None)
    else:
        logger.debug("[FIXED] グループIDなし - 既存試料取得をスキップ")
    select_row.addWidget(select_label)
    select_row.addWidget(sample_combo)
    input_layout.addLayout(select_row)

    # 1. 試料名 (SampleNamesWidget)
    name_row = QHBoxLayout()
    name_label = QLabel("試料名 *")
    name_label.setMinimumWidth(120)
    name_label.setAlignment(Qt.AlignTop) # 複数行になるため上寄せ
    
    sample_names_widget = SampleNamesWidget(max_samples=5)
    
    name_row.addWidget(name_label)
    name_row.addWidget(sample_names_widget)
    input_layout.addLayout(name_row)

    # 2. 試料の説明 (MarkdownEditor)
    desc_row = QHBoxLayout()
    desc_label = QLabel("試料の説明")
    desc_label.setMinimumWidth(120)
    desc_label.setAlignment(Qt.AlignTop)
    
    markdown_editor = MarkdownEditor()
    
    desc_row.addWidget(desc_label)
    desc_row.addWidget(markdown_editor)
    input_layout.addLayout(desc_row)

    # 3. 化学式・組成式・分子式
    formula_row = QHBoxLayout()
    formula_label = QLabel("化学式・組成式・分子式")
    formula_label.setMinimumWidth(120)
    formula_input = QLineEdit()
    formula_input.setPlaceholderText("化学式、組成式、または分子式を入力")
    formula_input.setMinimumHeight(24)
    formula_row.addWidget(formula_label)
    formula_row.addWidget(formula_input)
    input_layout.addLayout(formula_row)

    # 4. 参考URL (基本情報から移動)
    url_row = QHBoxLayout()
    url_label = QLabel("参考URL")
    url_label.setMinimumWidth(120)
    url_input = QLineEdit()
    url_input.setPlaceholderText("参考URL")
    url_input.setMinimumHeight(24)
    url_row.addWidget(url_label)
    url_row.addWidget(url_input)
    input_layout.addLayout(url_row)

    # 5. タグ (基本情報から移動)
    tag_row = QHBoxLayout()
    tag_label = QLabel("タグ(カンマ区切り)")
    tag_label.setMinimumWidth(120)
    tag_input = TagInputWidget()
    tag_input.setPlaceholderText("タグ(カンマ区切り)")
    tag_input.setMinimumHeight(24)
    tag_row.addWidget(tag_label)
    tag_row.addWidget(tag_input)
    input_layout.addLayout(tag_row)

    # 6. 試料管理者 (コンボボックス + 匿名化チェックボックス)
    manager_row = QHBoxLayout()
    manager_label = QLabel("試料管理者 *")
    manager_label.setMinimumWidth(120)
    
    manager_combo = QComboBox()
    manager_combo.setMinimumHeight(24)
    manager_combo.addItem("選択してください...", None)
    
    # グループメンバー読み込み
    if group_id:
        try:
            members = load_group_members(group_id)
            current_user_id = get_current_user_id()
            default_index = 0
            
            for i, member in enumerate(members):
                # メンバー情報の構造に合わせて調整 (id, attributes.name 等)
                # group_member_loaderの実装では、APIレスポンスのmembersリストを返す
                # JSON:API形式の場合、attributes内に情報がある
                user_id = member.get('id')
                attrs = member.get('attributes', {})
                # 名前情報の取得 (fullName, name, or familyName+givenName)
                name = attrs.get('fullName') or attrs.get('name')
                if not name:
                    f_name = attrs.get('familyName', '')
                    g_name = attrs.get('givenName', '')
                    if f_name or g_name:
                        name = f"{f_name} {g_name}".strip()
                    else:
                        name = user_id # フォールバック
                
                org = attrs.get('organizationName', '')
                display_text = f"{name} ({org})" if org else name
                
                manager_combo.addItem(display_text, user_id)
                
                # ログインユーザーと一致する場合、そのインデックスを記録
                # manager_comboには"選択してください..."が先頭にあるため、indexは i + 1
                if current_user_id and user_id == current_user_id:
                    default_index = i + 1
            
            # デフォルト選択: ログインユーザー > 先頭のメンバー
            if default_index > 0:
                manager_combo.setCurrentIndex(default_index)
            elif manager_combo.count() > 1:
                # ログインユーザーがいない場合は先頭のメンバー（index 1）を選択
                manager_combo.setCurrentIndex(1)
                
        except Exception as e:
            logger.error("グループメンバー読み込みエラー: %s", e)
            manager_combo.addItem("メンバー読み込みエラー", None)
            
    hide_owner_check = QCheckBox("匿名化")
    hide_owner_check.setToolTip("試料管理者を匿名化します")
    
    manager_row.addWidget(manager_label)
    manager_row.addWidget(manager_combo, 1)
    manager_row.addWidget(hide_owner_check)
    input_layout.addLayout(manager_row)

    # 7. 関連試料 (RelatedSamplesWidget)
    related_row = QHBoxLayout()
    related_label = QLabel("関連試料")
    related_label.setMinimumWidth(120)
    related_label.setAlignment(Qt.AlignTop)
    
    related_samples_widget = RelatedSamplesWidget(group_id=group_id)
    
    related_row.addWidget(related_label)
    related_row.addWidget(related_samples_widget)
    input_layout.addLayout(related_row)

    # 保存ボタン（非表示）
    button_row = QHBoxLayout()
    button_row.addStretch()
    save_button = QPushButton("試料情報保存")
    save_button.setMinimumHeight(28)
    save_button.setVisible(False)
    button_row.addWidget(save_button)
    input_layout.addLayout(button_row)

    input_widgets = {
        "sample_combo": sample_combo,
        "name": sample_names_widget, # Widget自体を格納
        "description": markdown_editor, # Widget自体を格納
        "composition": formula_input,
        "url": url_input,
        "tags": tag_input,
        "manager": manager_combo,
        "manager_label": manager_label,
        "hide_owner": hide_owner_check,
        "related_samples": related_samples_widget,
        "save_button": save_button
    }
    
    logger.info("[FIXED] 試料入力エリア作成完了（拡張版）")
    return input_group, input_widgets

def _handle_sample_selection(selected_data, input_widgets):
    """
    試料選択変更時の処理（既存試料選択時は入力無効化・データ表示）
    
    Args:
        selected_data: 選択された試料データ（Noneなら新規作成）
        input_widgets: 入力ウィジェットの辞書
    """
    logger.debug("[FIXED] 試料選択変更: selected_data=%s", selected_data)
    
    if selected_data is None:
        # 新規作成の場合：入力フィールドを有効化・クリア
        logger.debug("[FIXED] 新規作成モード：入力フィールド有効化")
        
        input_widgets["name"].setEnabled(True)
        input_widgets["description"].setEnabled(True)
        input_widgets["composition"].setEnabled(True)
        input_widgets["url"].setEnabled(True)
        input_widgets["tags"].setEnabled(True)
        input_widgets["manager"].setEnabled(True)
        input_widgets["hide_owner"].setEnabled(True)
        input_widgets["related_samples"].setEnabled(True)
        input_widgets["save_button"].setEnabled(True)
        
        # フィールドをクリア
        input_widgets["name"].set_sample_names([])
        input_widgets["description"].setText("")
        input_widgets["composition"].setText("")
        input_widgets["url"].setText("")
        input_widgets["tags"].setText("")

        # 新規作成モード時の試料管理者は「データ所有者」と同様に
        # ログインユーザー優先→なければ先頭メンバーへデフォルト選択する。
        try:
            manager_combo = input_widgets.get("manager")
            if manager_combo is not None:
                current_user_id = get_current_user_id()
                if current_user_id:
                    idx = manager_combo.findData(current_user_id)
                    if idx >= 0:
                        manager_combo.setCurrentIndex(idx)
                    elif manager_combo.count() > 1:
                        manager_combo.setCurrentIndex(1)
                    else:
                        manager_combo.setCurrentIndex(0)
                elif manager_combo.count() > 1:
                    manager_combo.setCurrentIndex(1)
                else:
                    manager_combo.setCurrentIndex(0)
        except Exception:
            # 破棄済みQtオブジェクト参照などは無視
            pass
        input_widgets["hide_owner"].setChecked(False)
        input_widgets["related_samples"].set_related_samples([])
        
        # プレースホルダーテキストを設定
        # input_widgets["name"].setPlaceholderText("試料名を入力してください") # Widgetなのでメソッドなし
        # input_widgets["description"].setPlaceholderText("試料の詳細説明を入力してください") # Widgetなのでメソッドなし
        input_widgets["composition"].setPlaceholderText("化学式、組成式、または分子式を入力")
        input_widgets["url"].setPlaceholderText("参考URL")
        input_widgets["tags"].setPlaceholderText("タグ(カンマ区切り)")
        
    else:
        # 既存試料選択の場合：入力フィールドを無効化・データ表示
        logger.debug("[FIXED] 既存試料選択モード：入力フィールド無効化・データ表示")
        
        input_widgets["name"].setEnabled(False)
        input_widgets["description"].setEnabled(False)
        input_widgets["composition"].setEnabled(False)
        input_widgets["url"].setEnabled(False)
        input_widgets["tags"].setEnabled(False)
        input_widgets["manager"].setEnabled(False)
        input_widgets["hide_owner"].setEnabled(False)
        input_widgets["related_samples"].setEnabled(False)
        input_widgets["save_button"].setEnabled(False)
        
        # 既存データを表示
        # selected_data (attributes) から値を取得
        # namesはリスト
        names = selected_data.get("names", [])
        if not names and selected_data.get("name"):
             names = [selected_data.get("name")]
        input_widgets["name"].set_sample_names(names)
        
        input_widgets["description"].setText(selected_data.get("description", ""))
        input_widgets["composition"].setText(selected_data.get("composition", ""))
        input_widgets["url"].setText(selected_data.get("referenceUrl", ""))
        
        tags = selected_data.get("tags", [])
        input_widgets["tags"].setText(", ".join(tags) if tags else "")
        
        # manager (ownerId) の設定
        owner_id = selected_data.get("ownerId")
        if owner_id:
            index = input_widgets["manager"].findData(owner_id)
            if index >= 0:
                input_widgets["manager"].setCurrentIndex(index)
        
        input_widgets["hide_owner"].setChecked(selected_data.get("hideOwner", False))
        
        # relatedSamples の設定
        # relatedSamplesは [{"relatedSampleId": "...", "description": "..."}] の形式
        related_samples = selected_data.get("relatedSamples", [])
        input_widgets["related_samples"].set_related_samples(related_samples)
        
        # プレースホルダーをクリア
        input_widgets["composition"].setPlaceholderText("")
        input_widgets["url"].setPlaceholderText("")
        input_widgets["tags"].setPlaceholderText("")

# 重複防止用 - 古い関数を無効化
def _build_sample_form_content(*args, **kwargs):
    """
    旧関数 - 無効化済み
    """
    logger.debug("[FIXED] 旧_build_sample_form_content関数は無効化されました")
    pass
