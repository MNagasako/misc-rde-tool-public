"""
スキーマフォーム生成ユーティリティ - ARIM RDE Tool v1.17.2
invoiceSchemaからUIフォームを動的生成する機能

主要機能:
- JSONスキーマからQGroupBox形式のフォーム生成
- コンボボックス・テキスト入力の自動配置
- 多言語ラベル対応
- フォーム値の取得サポート
"""

import json
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit
from PyQt5.QtCore import Qt


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
    
    # 独立ダイアログとして表示されることを防ぐ
    from PyQt5.QtCore import Qt
    group.setWindowFlags(Qt.Widget)  # 明示的にウィジェットフラグを設定
    group.setVisible(False)  # 初期状態では非表示に設定
    
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
    
    # フォーム操作メソッドを追加
    def get_form_data():
        """フォームから値を取得"""
        return get_schema_form_values(group)
    
    def set_form_data(data):
        """フォームに値を設定"""
        if not data or not hasattr(group, '_schema_key_to_widget'):
            return
        
        key_to_widget = getattr(group, '_schema_key_to_widget', {})
        print(f"[DEBUG] set_form_data呼び出し: data={data}, available_keys={list(key_to_widget.keys())}")
        
        for key, value in data.items():
            if key in key_to_widget:
                widget = key_to_widget[key]
                try:
                    if hasattr(widget, 'setCurrentText'):
                        # コンボボックスの場合
                        widget.setCurrentText(str(value))
                        print(f"[DEBUG] コンボボックス設定: {key}={value}")
                    elif hasattr(widget, 'setText'):
                        # テキストフィールドの場合
                        widget.setText(str(value))
                        print(f"[DEBUG] テキストフィールド設定: {key}={value}")
                except Exception as e:
                    print(f"[WARNING] フィールド設定エラー ({key}={value}): {e}")
            else:
                print(f"[WARNING] 未知のフィールドキー: {key}")
    
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
                print(f"[WARNING] フィールドクリアエラー ({key}): {e}")
    
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
    print(f"[DEBUG] スキーマフォーム作成完了: parent={type(parent) if parent else None}, flags={group.windowFlags()}")
    print(f"[DEBUG] parent object id: {id(parent) if parent else None}")
    print(f"[DEBUG] group object id: {id(group)}")
    print(f"[DEBUG] ウィンドウフラグ詳細: {int(group.windowFlags())}")
    print(f"[DEBUG] 可視性: visible={group.isVisible()}, window={group.isWindow()}")
    
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
