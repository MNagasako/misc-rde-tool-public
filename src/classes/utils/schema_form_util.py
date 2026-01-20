"""
スキーマフォーム生成ユーティリティ - ARIM RDE Tool
invoiceSchemaからUIフォームを動的生成する機能

主要機能:
- JSONスキーマからQGroupBox形式のフォーム生成
- コンボボックス・テキスト入力の自動配置
- 多言語ラベル対応
- フォーム値の取得サポート
"""

import json
from qt_compat.widgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QWidget
from qt_compat.core import Qt

import logging

# ロガー設定
logger = logging.getLogger(__name__)


def create_schema_form(schema_path, parent=None):
    """
    JSONスキーマファイルからPyQt5フォームを動的生成
    
    Args:
        schema_path (str): スキーマJSONファイルのパス
        parent (QWidget): 親ウィジェット
        
    Returns:
        QGroupBox: 生成されたフォーム、エラー時はNone
    """
    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        logger.error("スキーマファイル読み込み失敗: %s", e)
        return None

    # 固有情報（custom）セクションを取得
    custom = schema.get("properties", {}).get("custom")
    label_text = "固有情報"
    if isinstance(custom, dict):
        label_text = custom.get("label", {}).get("ja", label_text)

    # フォームグループ作成
    group = QGroupBox(label_text, parent)

    # 独立ダイアログとして表示されることを防ぐ
    from qt_compat.core import Qt
    group.setWindowFlags(Qt.Widget)  # 明示的にウィジェットフラグを設定
    group.setVisible(False)  # 初期状態では非表示に設定

    layout = QVBoxLayout(group)

    properties = {}
    if isinstance(custom, dict):
        properties = custom.get("properties", {}) or {}

    required_keys: set[str] = set()
    try:
        if isinstance(custom, dict):
            req_list = custom.get("required")
            if isinstance(req_list, list):
                required_keys.update([str(k) for k in req_list if k])
    except Exception:
        required_keys = set()

    key_to_widget = {}
    key_to_label_widget = {}
    key_to_row_widget = {}

    if not properties:
        # フォーム項目が定義されていない場合は説明ラベルのみ表示
        logger.info("スキーマに固有情報フィールドが存在しません: %s", schema_path)
        info_label = QLabel("このテンプレートには固有情報の入力項目が定義されていません。")
        info_label.setWordWrap(True)
        info_label.setObjectName("schema_form_no_custom_info")
        layout.addWidget(info_label)
        # 後続処理で共通メソッドを付与するため、空マップを設定
        key_to_widget = {}
    else:
        # プロパティ解析・フォーム要素生成
        for key, prop in properties.items():
            row_widget = QWidget(group)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)

            # ラベル作成
            label = QLabel(prop.get("label", {}).get("ja", key), row_widget)
            row.addWidget(label)
            key_to_label_widget[key] = label

            # 入力要素作成
            if "enum" in prop:
                # 選択肢がある場合：コンボボックス
                combo = QComboBox(row_widget)
                combo.addItem("")  # 初期値として空欄を追加
                combo.addItems([str(v) for v in prop["enum"]])
                combo.setEditable(False)
                combo.setPlaceholderText(prop.get("options", {}).get("placeholder", {}).get("ja", ""))
                combo.setCurrentIndex(0)  # 空欄をデフォルト選択
                row.addWidget(combo)
                key_to_widget[key] = combo
            else:
                # 自由入力：テキストフィールド
                edit = QLineEdit(row_widget)
                edit.setPlaceholderText(prop.get("options", {}).get("placeholder", {}).get("ja", ""))
                row.addWidget(edit)
                key_to_widget[key] = edit

            layout.addWidget(row_widget)
            key_to_row_widget[key] = row_widget

            try:
                if isinstance(prop, dict) and prop.get("required") is True:
                    required_keys.add(str(key))
            except Exception:
                pass

    group.setLayout(layout)
    # 英語key→widgetマッピングを保存
    group._schema_key_to_widget = key_to_widget
    group._schema_key_to_label_widget = key_to_label_widget
    group._schema_key_to_row_widget = key_to_row_widget
    group._schema_required_keys = sorted(required_keys)
    
    # フォーム操作メソッドを追加
    def get_form_data():
        """フォームから値を取得"""
        return get_schema_form_values(group)
    
    def set_form_data(data):
        """フォームに値を設定"""
        if not data or not hasattr(group, '_schema_key_to_widget'):
            return
        
        key_to_widget = getattr(group, '_schema_key_to_widget', {})
        logger.debug("set_form_data呼び出し: data=%s, available_keys=%s", data, list(key_to_widget.keys()))
        
        for key, value in data.items():
            if key in key_to_widget:
                widget = key_to_widget[key]
                try:
                    if hasattr(widget, 'setCurrentText'):
                        # コンボボックスの場合
                        widget.setCurrentText(str(value))
                        logger.debug("コンボボックス設定: %s=%s", key, value)
                    elif hasattr(widget, 'setText'):
                        # テキストフィールドの場合
                        widget.setText(str(value))
                        logger.debug("テキストフィールド設定: %s=%s", key, value)
                except Exception as e:
                    logger.warning("フィールド設定エラー (%s=%s): %s", key, value, e)
            else:
                logger.warning("未知のフィールドキー: %s", key)
    
    def clear_form():
        """フォームをクリア"""
        if not hasattr(group, '_schema_key_to_widget'):
            return
            
        key_to_widget = getattr(group, '_schema_key_to_widget', {})
        for key, widget in key_to_widget.items():
            try:
                if hasattr(widget, 'setCurrentIndex'):
                    widget.setCurrentIndex(0)  # コンボボックスは先頭（空欄）に
                elif hasattr(widget, 'setText'):
                    widget.setText('')  # テキストフィールドは空文字
            except Exception as e:
                logger.warning("フィールドクリアエラー (%s): %s", key, e)
    
    # メソッドをフォームに動的に追加
    group.get_form_data = get_form_data
    group.set_form_data = set_form_data
    group.clear_form = clear_form
    
    # 独立ダイアログ表示を防ぐ追加設定
    group.setWindowModality(Qt.NonModal)  # モーダルダイアログにしない
    group.setAttribute(Qt.WA_DeleteOnClose, False)  # 閉じてもオブジェクトを削除しない
    if parent is not None:
        group.setParent(parent)  # 親ウィジェットを明示的に再設定
    
    # デバッグ情報
    logger.debug("スキーマフォーム作成完了: parent=%s, flags=%s", type(parent) if parent else None, group.windowFlags())
    logger.debug("parent object id: %s", id(parent) if parent else None)
    logger.debug("group object id: %s", id(group))
    logger.debug("ウィンドウフラグ詳細: %s", int(group.windowFlags()))
    logger.debug("可視性: visible=%s, window=%s", group.isVisible(), group.isWindow())
    
    return group


def get_schema_form_values(schema_form_widget, include_empty=False):
    """
    スキーマフォームからキー・値のペアを取得
    
    Args:
        schema_form_widget (QGroupBox): create_schema_form で生成されたフォーム
        include_empty (bool): 空値も空文字列として含めるかどうか
        
    Returns:
        dict: {key: value} の辞書
    """
    if not schema_form_widget or not hasattr(schema_form_widget, '_schema_key_to_widget'):
        return {}
    
    values = {}
    key_to_widget = getattr(schema_form_widget, '_schema_key_to_widget', {})
    
    for key, widget in key_to_widget.items():
        value = None
        if hasattr(widget, 'currentText'):
            value = widget.currentText()
        elif hasattr(widget, 'text'):
            value = widget.text()
        
        if value and value.strip():
            # 非空値はそのまま保存
            values[key] = value
        elif include_empty:
            # 空値を空文字列として保存（include_emptyがTrueの場合のみ）
            values[key] = ""
    
    return values


def get_schema_form_all_fields(schema_form_widget):
    """
    スキーマフォームの全フィールドを取得（空値は空文字列）
    
    Args:
        schema_form_widget (QGroupBox): create_schema_form で生成されたフォーム
        
    Returns:
        dict: 全フィールドの {key: value} の辞書（空値は空文字列）
    """
    return get_schema_form_values(schema_form_widget, include_empty=True)
