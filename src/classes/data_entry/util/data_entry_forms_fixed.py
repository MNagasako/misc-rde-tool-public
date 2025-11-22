"""
データ登録フォーム作成ユーティリティ (完全修正版)
正しい3項目構造（試料名、試料の説明、化学式・組成式・分子式）
既存試料選択機能・入力制御機能付き
"""

try:
    from qt_compat.widgets import (
        QFrame, QVBoxLayout, QHBoxLayout, QGroupBox, 
        QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton
    )
    from qt_compat.core import Qt
except ImportError as e:
    logger.error("PyQt5インポートエラー: %s", e)
    # フォールバック用の空実装
    class QFrame: pass
    class QVBoxLayout: pass


from .sample_loader import load_existing_samples, format_sample_display_name
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

import logging

# ロガー設定
logger = logging.getLogger(__name__)
# 共通スタイル定数をインポート
from classes.data_entry.conf.ui_constants import DATA_REGISTER_FORM_STYLE, ROW_STYLE_QSS

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
    # 共通フォームスタイルを適用
    input_group.setStyleSheet(DATA_REGISTER_FORM_STYLE)
    input_layout = QVBoxLayout(input_group)
    input_layout.setContentsMargins(12, 12, 12, 12)
    input_layout.setSpacing(10)

    row_style = ROW_STYLE_QSS

    # 新規/選択エリア（横並び）
    select_row = QHBoxLayout()
    select_label = QLabel("新規/選択")
    from classes.utils.label_style import apply_label_style
    apply_label_style(select_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    select_label.setMinimumWidth(120)
    sample_combo = QComboBox()
    sample_combo.setMinimumHeight(24)
    sample_combo.setStyleSheet(row_style)
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

    # 1. 試料名
    name_row = QHBoxLayout()
    name_label = QLabel("試料名 *")
    from classes.utils.label_style import apply_label_style
    apply_label_style(name_label, get_color(ThemeKey.TEXT_ERROR), bold=True)
    name_label.setMinimumWidth(120)
    name_input = QLineEdit()
    name_input.setPlaceholderText("試料名を入力してください")
    name_input.setMinimumHeight(24)
    name_input.setStyleSheet(row_style)
    name_row.addWidget(name_label)
    name_row.addWidget(name_input)
    input_layout.addLayout(name_row)

    # 2. 試料の説明（横並び）
    desc_row = QHBoxLayout()
    desc_label = QLabel("試料の説明")
    from classes.utils.label_style import apply_label_style
    apply_label_style(desc_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    desc_label.setMinimumWidth(120)
    desc_input = QTextEdit()
    desc_input.setMinimumHeight(32)
    desc_input.setMaximumHeight(48)
    desc_input.setPlaceholderText("試料の詳細説明を入力してください")
    desc_input.setStyleSheet(row_style)
    desc_row.addWidget(desc_label)
    desc_row.addWidget(desc_input)
    input_layout.addLayout(desc_row)

    # 3. 化学式・組成式・分子式
    formula_row = QHBoxLayout()
    formula_label = QLabel("化学式・組成式・分子式")
    from classes.utils.label_style import apply_label_style
    apply_label_style(formula_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    formula_label.setMinimumWidth(120)
    formula_input = QLineEdit()
    formula_input.setPlaceholderText("化学式、組成式、または分子式を入力")
    formula_input.setMinimumHeight(24)
    formula_input.setStyleSheet(row_style)
    formula_row.addWidget(formula_label)
    formula_row.addWidget(formula_input)
    input_layout.addLayout(formula_row)

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
        "name": name_input,
        "description": desc_input,
        "composition": formula_input,
        "save_button": save_button
    }
    
    logger.info("[FIXED] 試料入力エリア作成完了（新規/選択エリア含む3項目構造）")
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
        input_widgets["save_button"].setEnabled(True)
        
        # フィールドをクリア
        input_widgets["name"].setText("")
        input_widgets["description"].setText("")
        input_widgets["composition"].setText("")
        
        # プレースホルダーテキストを設定
        input_widgets["name"].setPlaceholderText("試料名を入力してください")
        input_widgets["description"].setPlaceholderText("試料の詳細説明を入力してください")
        input_widgets["composition"].setPlaceholderText("化学式、組成式、または分子式を入力")
        
    else:
        # 既存試料選択の場合：入力フィールドを無効化・データ表示
        logger.debug("[FIXED] 既存試料選択モード：入力フィールド無効化・データ表示")
        
        input_widgets["name"].setEnabled(False)
        input_widgets["description"].setEnabled(False)
        input_widgets["composition"].setEnabled(False)
        input_widgets["save_button"].setEnabled(False)
        
        # 既存データを表示
        input_widgets["name"].setText(selected_data.get("name", ""))
        input_widgets["description"].setText(selected_data.get("description", ""))
        input_widgets["composition"].setText(selected_data.get("composition", ""))
        
        # プレースホルダーをクリア
        input_widgets["name"].setPlaceholderText("")
        input_widgets["description"].setPlaceholderText("")
        input_widgets["composition"].setPlaceholderText("")

# 重複防止用 - 古い関数を無効化
def _build_sample_form_content(*args, **kwargs):
    """
    旧関数 - 無効化済み
    """
    logger.debug("[FIXED] 旧_build_sample_form_content関数は無効化されました")
    pass
