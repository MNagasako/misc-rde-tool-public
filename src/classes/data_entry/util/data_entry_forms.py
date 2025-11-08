"""
データ登録用フォーム機能

試料選択フォーム、試料入力フォーム、インボイススキーマフォームの作成を担当します。
"""

from qt_compat.widgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QComboBox, QTextEdit, QFrame, QPushButton, QMessageBox, QGroupBox, QSizePolicy)
from qt_compat.gui import QFont
from qt_compat.core import QTimer
import json
import os
from config.common import get_dynamic_file_path

from classes.utils.schema_form_util import create_schema_form


def create_sample_form(parent=None):
    """試料登録フォームを作成（直接表示版）"""
    try:
        print(f"[DEBUG] 試料フォーム作成開始")
        
        # 巨大で目立つフレーム作成
        sample_frame = QFrame(parent)
        sample_frame.setObjectName("sample_frame")
        sample_frame.setFrameStyle(QFrame.Box | QFrame.Raised)
        sample_frame.setLineWidth(5)  # 太いボーダー
        sample_frame.setStyleSheet("""
            QFrame#sample_frame {
                background-color: #FF5722;
                border: 5px solid #D32F2F;
                border-radius: 10px;
                margin: 10px;
                padding: 20px;
            }
        """)
        
        # 固定サイズで強制表示
        sample_frame.setVisible(True)
        sample_frame.setFixedSize(800, 400)  # 固定サイズ
        
        # レイアウト設定
        layout = QVBoxLayout(sample_frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 超目立つタイトル
        title_label = QLabel("� 試料フォーム表示テスト - 見えていますか？ 🚨")
        title_label.setFont(QFont("", 16, QFont.Bold))
        title_label.setStyleSheet("color: #FFFFFF; background-color: #D32F2F; padding: 15px; border-radius: 5px;")
        layout.addWidget(title_label)
        
        # 大きなテストメッセージ
        test_label = QLabel("✅✅✅ このオレンジ色のボックスが見えれば成功です！✅✅✅")
        test_label.setFont(QFont("", 14, QFont.Bold))
        test_label.setStyleSheet("color: #FFFFFF; background-color: #FF5722; padding: 30px; border: 3px solid #FFFFFF;")
        test_label.setFixedHeight(150)
        layout.addWidget(test_label)
        
        print(f"[DEBUG] 試料フォーム作成完了 - サイズ={sample_frame.size()}")
        return sample_frame
        
    except Exception as e:
        print(f"[ERROR] 試料フォーム作成エラー: {e}")
        return None


def create_schema_form_from_path(schema_path, parent=None):
    """インボイススキーマからフォームを作成"""
    try:
        print(f"[DEBUG] スキーマフォーム作成開始: {schema_path}")
        print(f"[DEBUG] ファイル存在チェック: os.path.exists({schema_path}) = {os.path.exists(schema_path)}")
        print(f"[DEBUG] パス情報: os.path.isfile={os.path.isfile(schema_path)}, os.path.isdir={os.path.isdir(schema_path)}")
        print(f"[DEBUG] 親ディレクトリ存在: {os.path.exists(os.path.dirname(schema_path))}")
        
        if not os.path.exists(schema_path):
            print(f"[ERROR] スキーマファイル未存在: {schema_path}")
            # 類似ファイルを検索してみる
            dir_path = os.path.dirname(schema_path)
            file_name = os.path.basename(schema_path)
            if os.path.exists(dir_path):
                files = os.listdir(dir_path)
                similar_files = [f for f in files if f.startswith(file_name[:20])]
                print(f"[DEBUG] 類似ファイル: {similar_files[:5]}")
            return None
        
        # 既存のschema_form_utilを使用
        schema_form = create_schema_form(schema_path, parent)
        
        if schema_form:
            print(f"[DEBUG] スキーマフォーム作成完了")
            return schema_form
        else:
            print(f"[ERROR] スキーマフォーム作成失敗")
            return None
            
    except Exception as e:
        print(f"[ERROR] スキーマフォーム作成エラー: {e}")
        return None


def _build_sample_form_content(sample_form_widget, group_id, parent_controller):
    """試料フォームの内容を構築（既存試料データの読み込みのみ）"""
    try:
        print(f"[DEBUG] フォーム内容構築開始: group_id={group_id}")
        
        # 既存試料データの読み込み（フォーム内のコンボボックスを使用）
        sample_combo = sample_form_widget.findChild(QComboBox, "sample_combo")
        if sample_combo:
            # 既存項目をクリア（デフォルト項目以外）
            while sample_combo.count() > 1:
                sample_combo.removeItem(1)
            
            # 試料データファイルのパスを構築
            sample_file_path = get_dynamic_file_path(f'output/rde/data/samples/group_{group_id}.json')
            
            if os.path.exists(sample_file_path):
                try:
                    with open(sample_file_path, 'r', encoding='utf-8') as f:
                        sample_data = json.load(f)
                        
                    # 試料データをコンボボックスに追加
                    for sample in sample_data.get('samples', []):
                        sample_name = sample.get('name', 'Unnamed Sample')
                        sample_combo.addItem(sample_name, sample)
                        
                    print(f"[DEBUG] 既存試料を読み込み: {len(sample_data.get('samples', []))}件")
                    
                except Exception as file_error:
                    print(f"[WARNING] 試料ファイル読み込みエラー: {file_error}")
            else:
                print(f"[DEBUG] 試料ファイルが存在しません: {sample_file_path}")
            
            # 選択変更時のイベントハンドラを設定
            def on_sample_selected(index):
                if index == 0:  # デフォルト項目の場合はクリア
                    _clear_sample_inputs(sample_form_widget)
                else:
                    sample_data = sample_combo.itemData(index)
                    if sample_data:
                        _fill_sample_inputs(sample_form_widget, sample_data)
            
            sample_combo.currentIndexChanged.connect(on_sample_selected)
        
        print(f"[DEBUG] フォーム内容構築完了")
        
    except Exception as e:
        print(f"[ERROR] 試料フォーム内容構築エラー: {e}")
        import traceback
        traceback.print_exc()


def _fill_sample_inputs(sample_form_widget, sample_data):
    """試料データを入力フィールドに設定"""
    try:
        # 各入力フィールドを探して設定
        name_edit = sample_form_widget.findChild(QLineEdit, "sample_name")
        if name_edit:
            name_edit.setText(sample_data.get('name', ''))
            
        desc_edit = sample_form_widget.findChild(QTextEdit, "sample_description")
        if desc_edit:
            desc_edit.setPlainText(sample_data.get('description', ''))
            
        comp_edit = sample_form_widget.findChild(QTextEdit, "sample_composition")
        if comp_edit:
            comp_edit.setPlainText(sample_data.get('composition', ''))
            
        prep_edit = sample_form_widget.findChild(QTextEdit, "sample_preparation")
        if prep_edit:
            prep_edit.setPlainText(sample_data.get('preparation', ''))
            
        print(f"[DEBUG] 試料データを入力フィールドに設定完了: {sample_data.get('name', 'Unknown')}")
        
    except Exception as e:
        print(f"[ERROR] 試料データ設定エラー: {e}")


def _clear_sample_inputs(sample_form_widget):
    """試料入力フィールドをクリア"""
    try:
        # 各入力フィールドを探してクリア
        name_edit = sample_form_widget.findChild(QLineEdit, "sample_name")
        if name_edit:
            name_edit.clear()
            
        desc_edit = sample_form_widget.findChild(QTextEdit, "sample_description")
        if desc_edit:
            desc_edit.clear()
            
        comp_edit = sample_form_widget.findChild(QTextEdit, "sample_composition")
        if comp_edit:
            comp_edit.clear()
            
        prep_edit = sample_form_widget.findChild(QTextEdit, "sample_preparation")
        if prep_edit:
            prep_edit.clear()
            
        print(f"[DEBUG] 試料入力フィールドクリア完了")
        
    except Exception as e:
        print(f"[ERROR] 試料入力フィールドクリアエラー: {e}")