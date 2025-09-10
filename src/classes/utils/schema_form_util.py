"""
スキーマフォーム生成ユーティリティ - ARIM RDE Tool v1.17.0
invoiceSchemaからUIフォームを動的生成する機能

主要機能:
- JSONスキーマからQGroupBox形式のフォーム生成
- コンボボックス・テキスト入力の自動配置
- 多言語ラベル対応
- フォーム値の取得サポート
"""

import json
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit


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
        print(f"[ERROR] スキーマファイル読み込み失敗: {e}")
        return None

    # 固有情報（custom）セクションを取得
    custom = schema.get("properties", {}).get("custom", {})
    if not custom:
        return None

    # フォームグループ作成
    group = QGroupBox(custom.get("label", {}).get("ja", "固有情報"), parent)
    layout = QVBoxLayout(group)

    # プロパティ解析・フォーム要素生成
    properties = custom.get("properties", {})
    key_to_widget = {}

    for key, prop in properties.items():
        row = QHBoxLayout()
        
        # ラベル作成
        label = QLabel(prop.get("label", {}).get("ja", key))
        row.addWidget(label)

        # 入力要素作成
        if "enum" in prop:
            # 選択肢がある場合：コンボボックス
            combo = QComboBox()
            combo.addItem("")  # 初期値として空欄を追加
            combo.addItems([str(v) for v in prop["enum"]])
            combo.setEditable(False)
            combo.setPlaceholderText(prop.get("options", {}).get("placeholder", {}).get("ja", ""))
            combo.setCurrentIndex(0)  # 空欄をデフォルト選択
            row.addWidget(combo)
            key_to_widget[key] = combo
        else:
            # 自由入力：テキストフィールド
            edit = QLineEdit()
            edit.setPlaceholderText(prop.get("options", {}).get("placeholder", {}).get("ja", ""))
            row.addWidget(edit)
            key_to_widget[key] = edit

        layout.addLayout(row)

    group.setLayout(layout)
    # 英語key→widgetマッピングを保存
    group._schema_key_to_widget = key_to_widget
    return group


def get_schema_form_values(schema_form_widget):
    """
    スキーマフォームからキー・値のペアを取得
    
    Args:
        schema_form_widget (QGroupBox): create_schema_form で生成されたフォーム
        
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
        
        if value and value.strip():  # 空値は除外
            values[key] = value
    
    return values
