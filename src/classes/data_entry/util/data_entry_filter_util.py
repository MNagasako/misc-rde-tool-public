"""
データ登録機能用フィルタユーティリティ
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from config.common import SELF_JSON_PATH, DATASET_JSON_PATH

# キャッシュ機能は削除済み - 高速検索機能で十分な性能を実現


def get_current_user_id_for_data_entry():
    """
    データ登録用に現在ログイン中のユーザーIDを取得
    
    Returns:
        str: ユーザーID、取得できない場合はNone
    """
    try:
        if not os.path.exists(SELF_JSON_PATH):
            return None
        
        with open(SELF_JSON_PATH, 'r', encoding='utf-8') as f:
            self_data = json.load(f)
        
        return self_data.get('data', {}).get('id')
        
    except Exception as e:
        print(f"[ERROR] データ登録用ユーザーID取得エラー: {e}")
        return None


def get_datasets_for_data_entry():
    """
    データ登録用にdataset.jsonから全データセットを取得（シンプル版）
    
    Returns:
        list: データセット一覧、取得できない場合は空リスト
    """
    try:
        if not os.path.exists(DATASET_JSON_PATH):
            print(f"[WARNING] dataset.jsonが見つかりません: {DATASET_JSON_PATH}")
            return []
        
        with open(DATASET_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        datasets = data.get('data', [])
        return datasets
        
    except Exception as e:
        print(f"[ERROR] dataset.json読み込みエラー: {e}")
        return []


def get_subgroups_for_data_entry():
    """
    データ登録用にsubGroup.jsonから全サブグループを取得（シンプル版）
    
    Returns:
        list: サブグループ一覧、取得できない場合は空リスト
    """
    try:
        subgroup_path = DATASET_JSON_PATH.replace('dataset.json', 'subGroup.json')
        if not os.path.exists(subgroup_path):
            print(f"[WARNING] subGroup.jsonが見つかりません: {subgroup_path}")
            return []
        
        with open(subgroup_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # dataが単一オブジェクトか配列かを確認
        subgroups_raw = data.get('data', [])
        if isinstance(subgroups_raw, dict):
            # 単一オブジェクトの場合は配列として扱う
            subgroups = [subgroups_raw]
        elif isinstance(subgroups_raw, list):
            # 配列の場合はそのまま
            subgroups = subgroups_raw
        else:
            print(f"[WARNING] subGroup.jsonの構造が予期しない形式です: {type(subgroups_raw)}")
            subgroups = []
        
        return subgroups
        
    except Exception as e:
        print(f"[ERROR] subGroup.json読み込みエラー: {e}")
        return []


def get_user_role_in_dataset(dataset_item, user_id):
    """
    指定ユーザーのデータセット内での権限を取得（シンプル版）
    grantNumberとsubGroup.jsonの関連性を活用した改善版
    
    Args:
        dataset_item (dict): データセット情報
        user_id (str): チェック対象のユーザーID
    
    Returns:
        str: 権限 ("OWNER", "ASSISTANT", "MEMBER", "AGENT", "VIEWER", "NONE")
    """
    if not isinstance(dataset_item, dict) or not user_id:
        return "NONE"
    
    try:
        # 1. 直接的な関係性をチェック（最高速）
        relationships = dataset_item.get('relationships', {})
        
        # manager（通常はOWNER権限）
        manager = relationships.get('manager', {}).get('data', {})
        if isinstance(manager, dict) and manager.get('id') == user_id:
            return "OWNER"
        
        # applicant（通常はOWNER権限）
        applicant = relationships.get('applicant', {}).get('data', {})
        if isinstance(applicant, dict) and applicant.get('id') == user_id:
            return "OWNER"
        
        # dataOwners（権限レベル要確認、通常はASSISTANT相当）
        data_owners = relationships.get('dataOwners', {}).get('data', [])
        if isinstance(data_owners, list):
            for owner in data_owners:
                if isinstance(owner, dict) and owner.get('id') == user_id:
                    return "ASSISTANT"
        
        # 2. grantNumberを使ってsubGroup.jsonから権限を取得（中速）
        grant_number = dataset_item.get('attributes', {}).get('grantNumber')
        if grant_number:
            role_from_subgroup = get_user_role_by_grant_number(grant_number, user_id)
            if role_from_subgroup and role_from_subgroup != "NONE":
                return role_from_subgroup
        
        # 3. グループメンバーシップから権限を推定（低速）
        group = relationships.get('group', {}).get('data', {})
        if group and group.get('id'):
            role = check_user_role_in_group(group.get('id'), user_id)
            if role and role != "NONE":
                return role
        
        # 4. 基本的なメンバーシップ確認（グループの一般メンバー）
        if check_basic_dataset_membership(dataset_item, user_id):
            return "MEMBER"
        
        return "NONE"
        
    except Exception as e:
        print(f"[ERROR] ユーザー権限判定エラー: {e}")
        return "NONE"


def get_user_role_by_grant_number(grant_number, user_id):
    """
    grantNumberを使ってsubGroup.jsonからユーザーの権限を取得
    
    Args:
        grant_number (str): 課題番号
        user_id (str): ユーザーID
    
    Returns:
        str: 権限レベル ("OWNER", "ASSISTANT", "MEMBER", "AGENT", "VIEWER", "NONE")
    """
    try:
        from config.common import SUBGROUP_JSON_PATH
        
        if not os.path.exists(SUBGROUP_JSON_PATH):
            print(f"[DEBUG] subGroup.jsonが存在しません: {SUBGROUP_JSON_PATH}")
            return "NONE"
        
        with open(SUBGROUP_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # included内のTEAMグループを検索
        for item in data.get('included', []):
            if (item.get('type') == 'group' and 
                item.get('attributes', {}).get('groupType') == 'TEAM'):
                
                # subjectsからgrantNumberが一致するグループを探す
                subjects = item.get('attributes', {}).get('subjects', [])
                for subject in subjects:
                    if subject.get('grantNumber') == grant_number:
                        # このグループでのユーザーの権限を確認
                        roles = item.get('attributes', {}).get('roles', [])
                        for role in roles:
                            if role.get('userId') == user_id:
                                user_role = role.get('role', 'MEMBER')
                                # デバッグメッセージを制限（本番環境では削除可能）
                                if grant_number == "test1":  # テスト用のgrantNumberのみ表示
                                    print(f"[DEBUG] grantNumber={grant_number}, user_id={user_id[:8]}..., role={user_role}")
                                return user_role
        
        
        # grantNumberによる権限が見つからない場合
        if grant_number == "test1":  # テスト用のgrantNumberのみ表示
            print(f"[DEBUG] grantNumber={grant_number}に対するuser_id={user_id[:8]}...の権限が見つかりませんでした")
        return "NONE"
        
    except Exception as e:
        print(f"[ERROR] grantNumberによる権限取得エラー: {e}")
        return "NONE"


def get_role_determination_source(dataset_item, user_id):
    """
    権限判定がどのロジックで決定されたかのソースを取得
    
    Args:
        dataset_item (dict): データセット情報
        user_id (str): ユーザーID
    
    Returns:
        str: 判定ソース ("直接管理", "申請者", "データ所有者", "subGroup", "グループ", "基本メンバー", "なし")
    """
    if not isinstance(dataset_item, dict) or not user_id:
        return "なし"
    
    try:
        relationships = dataset_item.get('relationships', {})
        
        # 1. manager確認
        manager = relationships.get('manager', {}).get('data', {})
        if isinstance(manager, dict) and manager.get('id') == user_id:
            return "直接管理"
        
        # 2. applicant確認
        applicant = relationships.get('applicant', {}).get('data', {})
        if isinstance(applicant, dict) and applicant.get('id') == user_id:
            return "申請者"
        
        # 3. dataOwners確認
        data_owners = relationships.get('dataOwners', {}).get('data', [])
        if isinstance(data_owners, list):
            for owner in data_owners:
                if isinstance(owner, dict) and owner.get('id') == user_id:
                    return "データ所有者"
        
        # 4. grantNumberによるsubGroup確認
        grant_number = dataset_item.get('attributes', {}).get('grantNumber')
        if grant_number:
            role_from_subgroup = get_user_role_by_grant_number(grant_number, user_id)
            if role_from_subgroup and role_from_subgroup != "NONE":
                return "subGroup"
        
        # 5. グループメンバーシップ確認
        group = relationships.get('group', {}).get('data', {})
        if group and group.get('id'):
            role = check_user_role_in_group(group.get('id'), user_id)
            if role:
                return "グループ"
        
        # 6. 基本メンバーシップ確認
        if check_basic_dataset_membership(dataset_item, user_id):
            return "基本メンバー"
        
        return "なし"
        
    except Exception as e:
        print(f"[ERROR] 権限判定ソース取得エラー: {e}")
        return "なし"


def check_basic_dataset_membership(dataset_item, user_id):
    """
    基本的なデータセットメンバーシップを確認（従来のcheck_user_is_memberと同等）
    
    Args:
        dataset_item (dict): データセット情報
        user_id (str): ユーザーID
    
    Returns:
        bool: メンバーかどうか
    """
    if not isinstance(dataset_item, dict) or not user_id:
        return False
    
    try:
        relationships = dataset_item.get('relationships', {})
        
        # manager をチェック
        manager = relationships.get('manager', {}).get('data', {})
        if isinstance(manager, dict) and manager.get('id') == user_id:
            return True
        
        # applicant をチェック
        applicant = relationships.get('applicant', {}).get('data', {})
        if isinstance(applicant, dict) and applicant.get('id') == user_id:
            return True
        
        # dataOwners をチェック
        data_owners = relationships.get('dataOwners', {}).get('data', [])
        if isinstance(data_owners, list):
            for owner in data_owners:
                if isinstance(owner, dict) and owner.get('id') == user_id:
                    return True
        
        return False
        
    except Exception as e:
        print(f"[ERROR] 基本メンバーシップ確認エラー: {e}")
        return False


def check_user_role_in_group(group_id, user_id):
    """
    グループ内でのユーザー権限を確認
    
    Args:
        group_id (str): グループID
        user_id (str): ユーザーID
    
    Returns:
        str: 権限レベル、なければNone
    """
    try:
        from config.common import SUBGROUP_JSON_PATH
        
        if not os.path.exists(SUBGROUP_JSON_PATH):
            return None
        
        with open(SUBGROUP_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # included内のgroupデータから該当グループを検索
        for item in data.get('included', []):
            if item.get('type') == 'group' and item.get('id') == group_id:
                roles = item.get('attributes', {}).get('roles', [])
                for role in roles:
                    if role.get('userId') == user_id:
                        return role.get('role', 'MEMBER')
        
        return None
        
    except Exception as e:
        print(f"[ERROR] グループ権限確認エラー: {e}")
        return None


def filter_datasets_by_user_role_checkbox(dataset_items, user_id, selected_roles):
    """
    チェックボックス形式の権限フィルタでデータセットをフィルタリング（シンプル版）
    
    Args:
        dataset_items (list): データセット一覧
        user_id (str): 現在のユーザーID
        selected_roles (list): 選択された権限リスト ["OWNER", "ASSISTANT", "MEMBER", "AGENT"]
    
    Returns:
        list: フィルタリングされたデータセット一覧（権限情報付き）
    """
    if not dataset_items or not user_id or not selected_roles:
        return []
    
    print(f"[INFO] データセットフィルタリング開始: {len(dataset_items)}件, 選択権限={selected_roles}")
    start_time = time.time()
    
    filtered_datasets = []
    
    # フィルタリング実行
    processed_count = 0
    for dataset in dataset_items:
        if processed_count % 200 == 0:
            print(f"[INFO] フィルタリング進行: {processed_count}/{len(dataset_items)}")
        
        user_role = get_user_role_in_dataset(dataset, user_id)
        
        if user_role in selected_roles:
            # データセットに権限情報を追加
            dataset_with_role = dataset.copy()
            dataset_with_role['_user_role'] = user_role
            dataset_with_role['_role_source'] = get_role_determination_source(dataset, user_id)
            filtered_datasets.append(dataset_with_role)
        
        processed_count += 1
    
    elapsed_time = time.time() - start_time
    print(f"[INFO] フィルタリング完了: {len(filtered_datasets)}件選択, 処理時間={elapsed_time:.2f}秒")
    
    return filtered_datasets


def get_dataset_display_name_with_role(dataset_item):
    """
    データセットの表示名に色付き権限情報を追加
    
    Args:
        dataset_item (dict): データセット情報（権限情報付き）
    
    Returns:
        str: 色付き権限情報付きの表示名
    """
    attributes = dataset_item.get('attributes', {})
    title = attributes.get('title', 'タイトルなし')
    
    # 権限情報がある場合は表示に追加
    user_role = dataset_item.get('_user_role')
    role_source = dataset_item.get('_role_source')
    
    if user_role and user_role != "NONE":
        # 権限別の絵文字と背景色
        role_display = {
            "OWNER": {"emoji": "👑", "color": "#FFD700", "text": "OWNER"},
            "ASSISTANT": {"emoji": "💁", "color": "#87CEEB", "text": "ASSIST"}, 
            "MEMBER": {"emoji": "👥", "color": "#98FB98", "text": "MEMBER"},
            "AGENT": {"emoji": "🤖", "color": "#DDA0DD", "text": "AGENT"}
        }
        
        role_info = role_display.get(user_role, {"emoji": "❓", "color": "#D3D3D3", "text": user_role})
        
        # 権限表示部分を作成
        role_part = f"{role_info['emoji']} {role_info['text']}"
        
        if role_source:
            return f"{role_part} | {title} (via {role_source})"
        else:
            return f"{role_part} | {title}"
    
    return title


def create_role_display_html(user_role, role_source=None):
    """
    HTML形式で色付き権限表示を作成
    
    Args:
        user_role (str): ユーザー権限
        role_source (str): 権限取得元
    
    Returns:
        str: HTML形式の権限表示
    """
    role_styles = {
        "OWNER": {"emoji": "👑", "bg": "#FFD700", "color": "#000", "text": "OWNER"},
        "ASSISTANT": {"emoji": "💁", "bg": "#4169E1", "color": "#FFF", "text": "ASSIST"}, 
        "MEMBER": {"emoji": "👥", "bg": "#32CD32", "color": "#000", "text": "MEMBER"},
        "AGENT": {"emoji": "🤖", "bg": "#9370DB", "color": "#FFF", "text": "AGENT"}
    }
    
    style = role_styles.get(user_role, {"emoji": "❓", "bg": "#808080", "color": "#FFF", "text": user_role})
    
    html = f'<span style="background-color: {style["bg"]}; color: {style["color"]}; padding: 2px 6px; border-radius: 3px; font-weight: bold; margin-right: 5px;">{style["emoji"]} {style["text"]}</span>'
    
    if role_source:
        html += f' <span style="color: #666; font-size: 90%;">via {role_source}</span>'
    
    return html


# 古いUI関数は削除済み - data_entry_filter_checkbox.pyの最新版を使用してください


def get_filtered_datasets(selected_roles: List[str]) -> List[Dict]:
    """
    指定された権限でフィルタリングされたデータセット一覧を取得
    
    Args:
        selected_roles (List[str]): フィルタリング対象の権限リスト
    
    Returns:
        List[Dict]: フィルタリングされたデータセット一覧
    """
    try:
        print(f"[INFO] フィルタリング開始: 選択権限={selected_roles}")
        
        # データセット一覧を取得
        datasets = get_datasets_for_data_entry()
        if not datasets:
            print("[WARNING] データセットが取得できませんでした")
            return []
        
        # 現在のユーザーIDを取得
        current_user_id = get_current_user_id_for_data_entry()
        if not current_user_id:
            print("[WARNING] ユーザーIDが取得できませんでした")
            return []
        
        # 権限フィルタリングを実行
        filtered_datasets = []
        for dataset in datasets:
            # ユーザーの権限をチェック
            user_role = get_user_role_in_dataset(dataset, current_user_id)
            
            if user_role in selected_roles:
                filtered_datasets.append(dataset)
        
        print(f"[INFO] フィルタリング完了: {len(filtered_datasets)}/{len(datasets)}件")
        return filtered_datasets
        
    except Exception as e:
        print(f"[ERROR] データセットフィルタリングエラー: {e}")
        return []
