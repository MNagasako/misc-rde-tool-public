#!/usr/bin/env python3
"""
データ登録機能用フィルタユーティリティ（チェックボックス版）
"""
import os
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QCompleter, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# 親ディレクトリのsrcをPythonパスに追加
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent.parent
sys.path.insert(0, str(src_dir))

from config.common import SELF_JSON_PATH, DATASET_JSON_PATH

# 元のフィルタユーティリティから必要な関数をインポート
from .data_entry_filter_util import (
    get_current_user_id_for_data_entry,
    get_datasets_for_data_entry,
    get_subgroups_for_data_entry,
    get_user_role_in_dataset
)


def get_colored_dataset_display_name(dataset):
    """データセットの表示名を詳細情報付きで生成（チェックボックス版用）"""
    if not isinstance(dataset, dict):
        return "Unknown Dataset"
    
    # 基本情報を取得
    attributes = dataset.get('attributes', {})
    name = attributes.get('name', 'Unnamed Dataset')
    dataset_type = attributes.get('datasetType', 'UNKNOWN')
    grant_number = attributes.get('grantNumber', '')
    subject_title = attributes.get('subjectTitle', '')
    dataset_id = dataset.get('id', '')
    
    # テンプレート情報を取得
    template_info = dataset.get('relationships', {}).get('template', {}).get('data', {})
    template_id = template_info.get('id', '')
    
    # ユーザーロール情報を表示に含める
    user_role = dataset.get('_user_role', '')
    role_source = dataset.get('_role_source', '')
    
    # 権限アイコンを設定
    role_icon = {
        'OWNER': '👑',
        'ASSISTANT': '💁', 
        'MEMBER': '👥',
        'AGENT': '🤖'
    }.get(user_role, '❓')
    
    # データセットタイプアイコンを設定
    type_icon = {
        'ANALYSIS': '📊',
        'EXPERIMENT': '🔬',
        'SIMULATION': '💻'
    }.get(dataset_type, '📄')
    
    # 表示用フォーマット（詳細情報付き）
    display_parts = [f"{role_icon}"] # {user_role}
    

    
    # 課題番号/subjectTitle
    if grant_number:
        display_parts.append(f"<{grant_number}>")
    elif subject_title:
        display_parts.append(f"<{subject_title}>")

     # データセット名
    if name and name != 'Unnamed Dataset':
        display_parts.append(f"【{type_icon}{name}】") 

    # テンプレートID（短縮版）
    if template_id:
        # テンプレートIDを短縮して表示
        template_short = template_id.replace('ARIM-R6_', '').replace('_20241121', '').replace('_20241120', '').replace('_20241112', '')
        display_parts.append(f"[{template_short}]")
    
    # ロールソース情報（短縮）
    if role_source:
        source_short = {
            '直接管理': 'Direct',
            '申請者': 'Applicant', 
            'subGroup': 'subGrp',
            'データ所有者': 'DataOwner'
        }.get(role_source, role_source)
        display_parts.append(f"[{source_short}]")
    
    # ID情報（最後に短縮版）
    if dataset_id:
        display_parts.append(f"(ID:{dataset_id[:16]}...)")
    delimiter = "" #" | "
    return delimiter.join(display_parts)


# グローバルキャッシュ
_user_cache = {
    'user_subgroups': None,
    'user_grant_numbers': {},
    'user_datasets': None,
    'last_user_id': None,
    'last_update': 0
}

USER_CACHE_EXPIRY = 300  # 5分間のキャッシュ有効期間


def get_user_subgroups_and_grants(user_id):
    """
    ユーザーが所属するサブグループとgrantNumber情報を事前抽出（高速化）
    
    Args:
        user_id (str): ユーザーID
    
    Returns:
        dict: {
            'subgroups': [サブグループ情報],
            'grant_numbers': {grantNumber: role},
            'has_data': bool
        }
    """
    import time
    
    # キャッシュの有効性確認
    current_time = time.time()
    if (_user_cache['last_user_id'] == user_id and 
        _user_cache['user_subgroups'] is not None and
        current_time - _user_cache['last_update'] < USER_CACHE_EXPIRY):
        return {
            'subgroups': _user_cache['user_subgroups'],
            'grant_numbers': _user_cache['user_grant_numbers'],
            'has_data': len(_user_cache['user_grant_numbers']) > 0
        }
    
    print(f"[INFO] ユーザー({user_id[:8]}...)の所属サブグループを抽出中...")
    
    try:
        subgroups_data = get_subgroups_for_data_entry()
        user_subgroups = []
        user_grant_numbers = {}
        
        # subGroups データの構造を確認して処理
        if isinstance(subgroups_data, dict):
            # 単一グループオブジェクトの場合
            subgroups_to_process = [subgroups_data]
        elif isinstance(subgroups_data, list):
            # グループ配列の場合
            subgroups_to_process = subgroups_data
        else:
            print(f"[WARNING] 予期しないsubGroups構造: {type(subgroups_data)}")
            subgroups_to_process = []
        
        # includedデータも含めて処理するため、subGroup.jsonを直接読み込み
        try:
            subgroup_path = DATASET_JSON_PATH.replace('dataset.json', 'subGroup.json')
            with open(subgroup_path, 'r', encoding='utf-8') as f:
                full_data = json.load(f)
            
            # included配列からも追加のグループを取得
            included_groups = full_data.get('included', [])
            if isinstance(included_groups, list):
                subgroups_to_process.extend(included_groups)
                
        except Exception as e:
            print(f"[WARNING] included要素読み込みエラー: {e}")
        
        # 再帰的にすべてのサブグループをチェック
        def process_group_recursive(group):
            if not isinstance(group, dict):
                return
            
            # 現在のグループをチェック
            if group.get('type') == 'group':
                attributes = group.get('attributes', {})
                roles = attributes.get('roles', [])
                
                # このグループでのユーザーの権限を確認
                user_role = None
                for role in roles:
                    if isinstance(role, dict) and role.get('userId') == user_id:
                        user_role = role.get('role', 'MEMBER')
                        break
                
                if user_role:
                    # ユーザーが所属するグループの場合、grantNumberを抽出
                    subjects = attributes.get('subjects', [])
                    group_grants = []
                    
                    for subject in subjects:
                        if isinstance(subject, dict):
                            grant_number = subject.get('grantNumber')
                            if grant_number:
                                user_grant_numbers[grant_number] = user_role
                                group_grants.append(grant_number)
                    
                    if group_grants:  # grantNumberがある場合のみ追加
                        user_subgroups.append({
                            'id': group.get('id'),
                            'name': attributes.get('name', 'Unknown Group'),
                            'role': user_role,
                            'grant_numbers': group_grants,
                            'subjects_count': len(subjects)
                        })
            
            # 子グループも再帰的に処理
            children = group.get('relationships', {}).get('children', {}).get('data', [])
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict) and child.get('id'):
                        # 子グループの詳細が必要な場合は、別途読み込む必要あり
                        # 現在は基本情報のみ処理
                        pass
        
        # 全グループを処理
        for group in subgroups_to_process:
            process_group_recursive(group)
        
        # キャッシュ更新
        _user_cache['user_subgroups'] = user_subgroups
        _user_cache['user_grant_numbers'] = user_grant_numbers
        _user_cache['last_user_id'] = user_id
        _user_cache['last_update'] = current_time
        
        print(f"[INFO] 所属サブグループ: {len(user_subgroups)}個, grantNumber: {len(user_grant_numbers)}個")
        
        return {
            'subgroups': user_subgroups,
            'grant_numbers': user_grant_numbers,
            'has_data': len(user_grant_numbers) > 0
        }
        
    except Exception as e:
        print(f"[ERROR] ユーザーサブグループ抽出エラー: {e}")
        return {
            'subgroups': [],
            'grant_numbers': {},
            'has_data': False
        }


def get_user_relevant_datasets(user_id):
    """
    ユーザーに関連するデータセットのみを事前抽出（超高速化）
    
    Args:
        user_id (str): ユーザーID
    
    Returns:
        list: ユーザーに関連するデータセットのみのリスト
    """
    import time
    
    # キャッシュ確認
    if (_user_cache['last_user_id'] == user_id and 
        _user_cache['user_datasets'] is not None and
        time.time() - _user_cache['last_update'] < USER_CACHE_EXPIRY):
        return _user_cache['user_datasets']
    
    print(f"[INFO] ユーザー関連データセットを抽出中...")
    start_time = time.time()
    
    try:
        # ユーザーのサブグループ情報を取得
        user_info = get_user_subgroups_and_grants(user_id)
        user_grant_numbers = set(user_info['grant_numbers'].keys())
        
        # 全データセットを取得
        all_datasets = get_datasets_for_data_entry()
        relevant_datasets = []
        
        for dataset in all_datasets:
            is_relevant = False
            
            # 1. 直接的な関係性チェック（高速）
            relationships = dataset.get('relationships', {})
            
            # manager/applicant/dataOwnersでの直接関係
            if (relationships.get('manager', {}).get('data', {}).get('id') == user_id or
                relationships.get('applicant', {}).get('data', {}).get('id') == user_id):
                is_relevant = True
            else:
                data_owners = relationships.get('dataOwners', {}).get('data', [])
                if isinstance(data_owners, list):
                    for owner in data_owners:
                        if isinstance(owner, dict) and owner.get('id') == user_id:
                            is_relevant = True
                            break
            
            # 2. grantNumberでの関連性チェック（高速）
            if not is_relevant:
                grant_number = dataset.get('attributes', {}).get('grantNumber')
                if grant_number and grant_number in user_grant_numbers:
                    is_relevant = True
            
            if is_relevant:
                relevant_datasets.append(dataset)
        
        # キャッシュ更新
        _user_cache['user_datasets'] = relevant_datasets
        
        elapsed_time = time.time() - start_time
        print(f"[INFO] 関連データセット抽出完了: {len(relevant_datasets)}件/{len(all_datasets)}件 ({elapsed_time:.2f}秒)")
        
        return relevant_datasets
        
    except Exception as e:
        print(f"[ERROR] 関連データセット抽出エラー: {e}")
        return []


def filter_datasets_by_checkbox_selection_optimized(user_id, selected_roles):
    """
    ユーザー関連データセットのみを対象とした超高速チェックボックスフィルタ
    
    Args:
        user_id (str): 現在のユーザーID
        selected_roles (list): 選択された権限リスト ["OWNER", "ASSISTANT", "MEMBER", "AGENT"]
    
    Returns:
        list: フィルタリングされたデータセット一覧（権限情報付き）
    """
    if not user_id or not selected_roles:
        return []
    
    print(f"[INFO] 最適化フィルタリング開始: 選択権限={selected_roles}")
    start_time = time.time()
    
    try:
        # ユーザー関連データセットのみを取得（大幅な高速化）
        relevant_datasets = get_user_relevant_datasets(user_id)
        
        if not relevant_datasets:
            print("[INFO] ユーザーに関連するデータセットが見つかりません")
            return []
        
        print(f"[INFO] 関連データセット対象: {len(relevant_datasets)}件で権限フィルタを実行")
        
        # ユーザーのgrantNumber権限を事前取得
        user_info = get_user_subgroups_and_grants(user_id)
        user_grant_roles = user_info['grant_numbers']
        
        filtered_datasets = []
        
        for dataset in relevant_datasets:
            # 高速な権限判定
            user_role = get_user_role_optimized(dataset, user_id, user_grant_roles)
            
            if user_role in selected_roles:
                # データセットに権限情報を追加
                dataset_with_role = dataset.copy()
                dataset_with_role['_user_role'] = user_role
                dataset_with_role['_role_source'] = get_role_source_optimized(dataset, user_id, user_grant_roles)
                filtered_datasets.append(dataset_with_role)
        
        elapsed_time = time.time() - start_time
        print(f"[INFO] 最適化フィルタリング完了: {len(filtered_datasets)}件選択, 処理時間={elapsed_time:.2f}秒")
        
        return filtered_datasets
        
    except Exception as e:
        print(f"[ERROR] 最適化フィルタリングエラー: {e}")
        return []


def get_user_role_optimized(dataset_item, user_id, user_grant_roles):
    """
    最適化された権限判定（事前抽出データ使用）+ 正しい優先順位
    
    Args:
        dataset_item (dict): データセット情報
        user_id (str): ユーザーID
        user_grant_roles (dict): {grantNumber: role} の事前抽出済み辞書
    
    Returns:
        str: 権限レベル
    """
    try:
        # 1. grantNumberを使った事前抽出済み権限確認（最優先）
        # subGroupでの権限が最も正確で詳細なため最優先
        grant_number = dataset_item.get('attributes', {}).get('grantNumber')
        if grant_number and grant_number in user_grant_roles:
            subgroup_role = user_grant_roles[grant_number]
            # subGroupでの権限がある場合はそれを優先
            return subgroup_role
        
        # 2. 直接的な関係性をチェック（subGroup権限がない場合のフォールバック）
        relationships = dataset_item.get('relationships', {})
        
        # manager/applicant
        manager = relationships.get('manager', {}).get('data', {})
        applicant = relationships.get('applicant', {}).get('data', {})
        
        if (isinstance(manager, dict) and manager.get('id') == user_id):
            return "OWNER"
        if (isinstance(applicant, dict) and applicant.get('id') == user_id):
            return "OWNER"
        
        # dataOwners
        data_owners = relationships.get('dataOwners', {}).get('data', [])
        if isinstance(data_owners, list):
            for owner in data_owners:
                if isinstance(owner, dict) and owner.get('id') == user_id:
                    return "ASSISTANT"
        
        # 3. 元の詳細権限判定ロジックを使用（最終フォールバック）
        if grant_number:
            detailed_role = get_user_role_in_dataset(dataset_item, user_id)
            if detailed_role and detailed_role != "NONE":
                return detailed_role
        
        return "NONE"
        
    except Exception as e:
        print(f"[ERROR] 最適化権限判定エラー: {e}")
        return "NONE"


def get_role_source_optimized(dataset_item, user_id, user_grant_roles):
    """
    最適化された権限ソース判定（正しい優先順位）
    
    Args:
        dataset_item (dict): データセット情報
        user_id (str): ユーザーID
        user_grant_roles (dict): {grantNumber: role} の事前抽出済み辞書
    
    Returns:
        str: 権限取得元
    """
    try:
        # 1. grantNumber経由を最優先（subGroupでの権限が最も正確）
        grant_number = dataset_item.get('attributes', {}).get('grantNumber')
        if grant_number and grant_number in user_grant_roles:
            return "subGroup"
        
        # 2. 直接的な関係性確認（subGroup権限がない場合）
        relationships = dataset_item.get('relationships', {})
        
        if relationships.get('manager', {}).get('data', {}).get('id') == user_id:
            return "直接管理"
        if relationships.get('applicant', {}).get('data', {}).get('id') == user_id:
            return "申請者"
        
        data_owners = relationships.get('dataOwners', {}).get('data', [])
        if isinstance(data_owners, list):
            for owner in data_owners:
                if isinstance(owner, dict) and owner.get('id') == user_id:
                    return "データ所有者"
        
        return "不明"
        
    except Exception as e:
        return "エラー"


def filter_datasets_by_checkbox_selection(dataset_items, user_id, selected_roles):
    """
    チェックボックス選択に基づいてデータセットをフィルタリング（最適化版へのエイリアス）
    
    Args:
        dataset_items (list): データセット一覧（使用されません - 最適化のため）
        user_id (str): 現在のユーザーID
        selected_roles (list): 選択された権限リスト ["OWNER", "ASSISTANT", "MEMBER", "AGENT"]
    
    Returns:
        list: フィルタリングされたデータセット一覧（権限情報付き）
    """
    # 最適化版フィルタを呼び出し（dataset_itemsパラメータは無視）
    return filter_datasets_by_checkbox_selection_optimized(user_id, selected_roles)


# 重複関数削除済み - 上記の詳細版get_colored_dataset_display_name関数を使用


def create_checkbox_filter_dropdown(parent=None):
    """
    チェックボックス形式のフィルタ付きデータセットドロップダウンを作成
    
    Args:
        parent: 親ウィジェット
    
    Returns:
        QWidget: フィルタ付きドロップダウンウィジェット
    """
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(5, 5, 5, 5)
    layout.setSpacing(5)
    
    # フィルタ部分
    filter_widget = QWidget()
    filter_layout = QHBoxLayout(filter_widget)
    filter_layout.setContentsMargins(0, 0, 0, 0)
    
    filter_label = QLabel("権限:")
    filter_label.setFont(QFont("", 9))
    filter_layout.addWidget(filter_label)
    
    # 権限フィルタのチェックボックス
    checkbox_owner = QCheckBox("👑 OWNER")
    checkbox_assistant = QCheckBox("💁 ASSISTANT") 
    checkbox_member = QCheckBox("👥 MEMBER")
    checkbox_agent = QCheckBox("🤖 AGENT")
    
    # 初期状態では全てチェック
    checkbox_owner.setChecked(True)
    checkbox_assistant.setChecked(True)
    checkbox_member.setChecked(True)
    checkbox_agent.setChecked(True)
    
    # チェックボックスのスタイル設定
    checkbox_style = """
    QCheckBox {
        font-weight: bold;
        padding: 3px;
        margin: 2px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
    }
    """
    
    checkbox_owner.setStyleSheet(checkbox_style + "QCheckBox { color: #B8860B; }")
    checkbox_assistant.setStyleSheet(checkbox_style + "QCheckBox { color: #4169E1; }")
    checkbox_member.setStyleSheet(checkbox_style + "QCheckBox { color: #228B22; }")
    checkbox_agent.setStyleSheet(checkbox_style + "QCheckBox { color: #9370DB; }")
    
    filter_layout.addWidget(checkbox_owner)
    filter_layout.addWidget(checkbox_assistant)
    filter_layout.addWidget(checkbox_member)
    filter_layout.addWidget(checkbox_agent)
    filter_layout.addStretch()
    
    # ドロップダウンの作成
    combo = QComboBox(container)
    combo.setMinimumWidth(450)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(12)
    combo.view().setMinimumHeight(240)
    # 先頭に空欄＋プレースホルダー
    combo.addItem("")
    combo.setCurrentIndex(0)
    combo.lineEdit().setPlaceholderText("リストから選択、またはキーワードで検索して選択してください")
    
    # 状況表示ラベル
    status_label = QLabel("読み込み中...")
    status_label.setStyleSheet("color: #666; font-size: 9pt;")
    
    layout.addWidget(filter_widget)
    layout.addWidget(status_label)
    layout.addWidget(combo)
    
    # データ読み込みと初期表示
    def update_filtered_datasets():
        """チェックボックスフィルタを適用してデータセット一覧を更新"""
        combo.clear()
        
        # 現在のユーザーIDを取得
        current_user_id = get_current_user_id_for_data_entry()
        if not current_user_id:
            status_label.setText("⚠️ ユーザー情報が取得できません")
            return
        
        # 選択された権限を取得
        selected_roles = []
        if checkbox_owner.isChecked():
            selected_roles.append('OWNER')
        if checkbox_assistant.isChecked():
            selected_roles.append('ASSISTANT')
        if checkbox_member.isChecked():
            selected_roles.append('MEMBER')
        if checkbox_agent.isChecked():
            selected_roles.append('AGENT')
        
        # チェックボックスが何も選択されていない場合のエラーハンドリング
        if not selected_roles:
            QMessageBox.warning(container, "フィルタエラー", 
                               "少なくとも1つの権限を選択してください。\n"
                               "全てのチェックを外すことはできません。")
            # デフォルトでASSISTANTを選択
            checkbox_assistant.setChecked(True)
            selected_roles = ['ASSISTANT']
        
        try:
            # 最適化版フィルタリング実行（事前抽出されたデータセットのみ対象）
            status_label.setText(f"🔍 高速フィルタリング中...")
            
            # 最適化されたチェックボックスフィルタリング実行
            filtered_datasets = filter_datasets_by_checkbox_selection_optimized(current_user_id, selected_roles)
            
            # ドロップダウンの更新
            # 先頭に空欄を維持
            combo.clear()
            combo.addItem("")
            for dataset in filtered_datasets:
                display_name = get_colored_dataset_display_name(dataset)
                combo.addItem(display_name, dataset)  # データセット全体を格納
            combo.setCurrentIndex(0)
            
            # 完了状況を表示（関連データセット総数は表示しない）
            selected_roles_str = "+".join(selected_roles)
            #status_label.setText(f"✅ {selected_roles_str}: {len(filtered_datasets)}件")
            status_label.setText(f"✅ {len(filtered_datasets)}件")
            # オートコンプリート機能を設定
            completion_items = [get_colored_dataset_display_name(ds) for ds in filtered_datasets]
            completer = QCompleter(completion_items, combo)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            combo.setCompleter(completer)
            
        except Exception as e:
            status_label.setText(f"❌ エラー: {str(e)}")
            print(f"[ERROR] データセット更新エラー: {e}")
    
    # フィルタ変更時の処理
    def on_filter_changed():
        update_filtered_datasets()
    
    # イベント接続（各チェックボックス）
    checkbox_owner.stateChanged.connect(on_filter_changed)
    checkbox_assistant.stateChanged.connect(on_filter_changed)
    checkbox_member.stateChanged.connect(on_filter_changed)
    checkbox_agent.stateChanged.connect(on_filter_changed)
    
    # 初回読み込み
    update_filtered_datasets()
    
    # ウィジェットにアクセス用属性を設定
    container.dataset_dropdown = combo
    container.filter_widget = filter_widget
    container.status_label = status_label
    container.update_datasets = update_filtered_datasets
    container.clear_cache = clear_user_cache
    
    return container


def clear_user_cache():
    """ユーザー専用キャッシュをクリア"""
    global _user_cache
    _user_cache = {
        'user_subgroups': None,
        'user_grant_numbers': {},
        'user_datasets': None,
        'last_user_id': None,
        'last_update': 0
    }
    print("[INFO] ユーザー専用キャッシュをクリアしました")
