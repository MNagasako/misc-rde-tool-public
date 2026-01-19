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
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QCompleter, QMessageBox, QPushButton
)
from qt_compat.widgets import QSizePolicy
from qt_compat.core import Qt
from qt_compat.gui import QFont
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

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
    }.get(user_role, '') if user_role else ''
    
    # データセットタイプアイコンを設定
    type_icon = {
        'ANALYSIS': '📊',
        'EXPERIMENT': '🔬',
        'SIMULATION': '💻'
    }.get(dataset_type, '📄')
    
    # 表示用フォーマット（詳細情報付き）
    display_parts = [f"{role_icon}"] if role_icon else []
    

    
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
                        desc = str(attributes.get('description') or '').strip()
                        user_subgroups.append({
                            'id': group.get('id'),
                            'name': attributes.get('name', 'Unknown Group'),
                            'role': user_role,
                            'grant_numbers': group_grants,
                            'description': desc,
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

    # フィルタなし（全データセット表示）
    checkbox_no_filter = QCheckBox("フィルタなし")
    checkbox_no_filter.setToolTip("権限フィルタを適用せず、全データセットから選択します")
    
    # 権限フィルタのチェックボックス
    checkbox_owner = QCheckBox("👑 管理者")
    checkbox_assistant = QCheckBox("💁 管理者代理") 
    checkbox_member = QCheckBox("👥 チームメンバ")
    checkbox_agent = QCheckBox("🤖 登録代行者")
    
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

    checkbox_no_filter.setStyleSheet(checkbox_style + f"QCheckBox {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}")
    
    checkbox_owner.setStyleSheet(checkbox_style + f"QCheckBox {{ color: {get_color(ThemeKey.ROLE_OWNER_TEXT)}; }}")
    checkbox_assistant.setStyleSheet(checkbox_style + f"QCheckBox {{ color: {get_color(ThemeKey.ROLE_ASSISTANT_TEXT)}; }}")
    checkbox_member.setStyleSheet(checkbox_style + f"QCheckBox {{ color: {get_color(ThemeKey.ROLE_MEMBER_TEXT)}; }}")
    checkbox_agent.setStyleSheet(checkbox_style + f"QCheckBox {{ color: {get_color(ThemeKey.ROLE_AGENT_TEXT)}; }}")
    
    filter_layout.addWidget(checkbox_no_filter)
    filter_layout.addWidget(checkbox_owner)
    filter_layout.addWidget(checkbox_assistant)
    filter_layout.addWidget(checkbox_member)
    filter_layout.addWidget(checkbox_agent)

    # フィルタなし専用: キャッシュ強制更新ボタン
    refresh_no_filter_btn = QPushButton("更新")
    refresh_no_filter_btn.setToolTip("フィルタなしのキャッシュを破棄して再読み込みします")
    refresh_no_filter_btn.setEnabled(False)
    filter_layout.addWidget(refresh_no_filter_btn)
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
    status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt;")
    
    layout.addWidget(filter_widget)

    # サブグループ / 課題番号フィルタ（上位フィルタ）
    subgroup_filter_widget = QWidget(container)
    subgroup_layout = QHBoxLayout(subgroup_filter_widget)
    subgroup_layout.setContentsMargins(0, 0, 0, 0)
    subgroup_layout.setSpacing(6)

    subgroup_label = QLabel("サブグループ:")
    subgroup_label.setFont(QFont("", 9))
    subgroup_layout.addWidget(subgroup_label)

    subgroup_combo = QComboBox(subgroup_filter_widget)
    subgroup_combo.setMinimumWidth(340)
    subgroup_combo.setEditable(True)
    subgroup_combo.setInsertPolicy(QComboBox.NoInsert)
    subgroup_combo.setMaxVisibleItems(12)
    subgroup_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    subgroup_combo.setToolTip("サブグループでデータセット候補を絞り込みます")
    try:
        subgroup_combo.lineEdit().setPlaceholderText("サブグループで絞り込み")
    except Exception:
        pass
    subgroup_layout.addWidget(subgroup_combo, 1)

    grant_label = QLabel("課題番号:")
    grant_label.setFont(QFont("", 9))
    subgroup_layout.addWidget(grant_label)

    grant_combo = QComboBox(subgroup_filter_widget)
    grant_combo.setEditable(True)
    grant_combo.setInsertPolicy(QComboBox.NoInsert)
    grant_combo.setMinimumWidth(180)
    grant_combo.setToolTip("課題番号(grantNumber)でデータセット候補を絞り込みます")
    try:
        grant_combo.lineEdit().setPlaceholderText("課題番号で絞り込み")
    except Exception:
        pass
    subgroup_layout.addWidget(grant_combo)
    subgroup_layout.addStretch()

    # スタイル
    try:
        base_color = get_color(ThemeKey.TEXT_PRIMARY)
        muted_color = get_color(ThemeKey.TEXT_MUTED)
        subgroup_label.setStyleSheet(f"color: {muted_color};")
        grant_label.setStyleSheet(f"color: {muted_color};")
        _combo_style = f"QComboBox {{ color: {base_color}; }}"
        subgroup_combo.setStyleSheet(_combo_style)
        grant_combo.setStyleSheet(_combo_style)
    except Exception:
        pass

    layout.addWidget(subgroup_filter_widget)
    layout.addWidget(status_label)
    layout.addWidget(combo)

    # 選択中データセットの日時（JST）を表示
    try:
        from classes.utils.dataset_datetime_display import create_dataset_dates_label, attach_dataset_dates_label

        dataset_dates_label = create_dataset_dates_label(container)
        attach_dataset_dates_label(combo=combo, label=dataset_dates_label, data_role=Qt.UserRole)
        layout.addWidget(dataset_dates_label)
        container.dataset_dates_label = dataset_dates_label
    except Exception:
        pass

    # フィルタなし専用キャッシュ（表示名生成のコストを削減）
    no_filter_cache: dict = {
        "items": None,  # list[tuple[str, dict]]
        "count": 0,
        "ready": False,
    }

    def _ensure_completer():
        """QCompleterはcomboのモデルを直接使う（大量件数でのリスト生成を避ける）"""
        completer = getattr(container, "_dataset_completer", None)
        if completer is None:
            completer = QCompleter(combo.model(), combo)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            combo.setCompleter(completer)
            container._dataset_completer = completer
        else:
            try:
                completer.setModel(combo.model())
            except Exception:
                pass

    def _populate_combo(items):
        prev = combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("")
            for display_name, dataset in items:
                combo.addItem(display_name, dataset)
            combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(prev)
        _ensure_completer()

    def _ensure_grant_completer():
        completer = getattr(container, "_grant_completer", None)
        try:
            if completer is None:
                completer = QCompleter(grant_combo.model(), grant_combo)
                completer.setFilterMode(Qt.MatchContains)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                grant_combo.setCompleter(completer)
                container._grant_completer = completer
            else:
                completer.setModel(grant_combo.model())
        except Exception:
            pass

    def _ensure_subgroup_completer():
        completer = getattr(container, "_subgroup_completer", None)
        try:
            if completer is None:
                completer = QCompleter(subgroup_combo.model(), subgroup_combo)
                completer.setFilterMode(Qt.MatchContains)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                subgroup_combo.setCompleter(completer)
                container._subgroup_completer = completer
            else:
                completer.setModel(subgroup_combo.model())
        except Exception:
            pass

    def _get_selected_roles() -> list[str]:
        roles: list[str] = []
        if checkbox_owner.isChecked():
            roles.append("OWNER")
        if checkbox_assistant.isChecked():
            roles.append("ASSISTANT")
        if checkbox_member.isChecked():
            roles.append("MEMBER")
        if checkbox_agent.isChecked():
            roles.append("AGENT")
        return roles

    def _normalize_subgroup_item(raw: dict) -> Optional[dict]:
        """subGroup.json由来のgroupオブジェクトを、UIが扱う簡易dictへ正規化する。"""
        if not isinstance(raw, dict):
            return None
        if raw.get("type") != "group":
            return None
        gid = raw.get("id")
        attrs = raw.get("attributes", {}) if isinstance(raw.get("attributes"), dict) else {}
        name = str(attrs.get("name") or "").strip() or "Unknown Group"
        desc = str(attrs.get("description") or "").strip()
        subjects = attrs.get("subjects") if isinstance(attrs.get("subjects"), list) else []
        grant_numbers: list[str] = []
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            g = subject.get("grantNumber")
            if g:
                g = str(g).strip()
                if g:
                    grant_numbers.append(g)
        # 重複除去（順序維持）
        seen: set[str] = set()
        deduped: list[str] = []
        for g in grant_numbers:
            if g in seen:
                continue
            seen.add(g)
            deduped.append(g)

        return {
            "id": gid,
            "name": name,
            "description": desc,
            # フィルタなしでは全件表示するため role は空欄
            "role": "",
            "grant_numbers": deduped,
            "subjects_count": len(subjects),
        }

    def _populate_subgroup_combo(user_subgroups: list[dict]):
        # 可能なら現在の選択を維持
        prev_selected_id = None
        try:
            current = subgroup_combo.currentData()
            if isinstance(current, dict) and current.get("id"):
                prev_selected_id = str(current.get("id"))
        except Exception:
            prev_selected_id = None

        prev = subgroup_combo.blockSignals(True)
        try:
            subgroup_combo.clear()
            subgroup_combo.addItem("(フィルタなし)", None)
            for sg in user_subgroups:
                try:
                    name = str(sg.get('name') or '').strip() or 'Unknown'
                    role = str(sg.get('role') or '').strip()
                    desc = str(sg.get('description') or '').strip()
                    caption = f"{name}" if not desc else f"{name} ({desc})"
                    if role:
                        caption = f"{caption} [{role}]"
                    subgroup_combo.addItem(caption, sg)
                except Exception:
                    continue
            # 可能なら選択維持
            if prev_selected_id:
                restored = False
                for i in range(subgroup_combo.count()):
                    try:
                        data = subgroup_combo.itemData(i)
                        if isinstance(data, dict) and str(data.get("id")) == prev_selected_id:
                            subgroup_combo.setCurrentIndex(i)
                            restored = True
                            break
                    except Exception:
                        continue
                if not restored:
                    subgroup_combo.setCurrentIndex(0)
            else:
                subgroup_combo.setCurrentIndex(0)
        finally:
            subgroup_combo.blockSignals(prev)
        _ensure_subgroup_completer()

    def _populate_grant_combo(grants: list[str]):
        prev = grant_combo.blockSignals(True)
        try:
            current_text = (grant_combo.currentText() or '').strip()
            grant_combo.clear()
            grant_combo.addItem("(フィルタなし)")
            for g in grants:
                grant_combo.addItem(str(g))
            # 可能なら既存入力を維持
            if current_text and current_text in grants:
                idx = grant_combo.findText(current_text)
                if idx >= 0:
                    grant_combo.setCurrentIndex(idx)
            else:
                grant_combo.setCurrentIndex(0)
        finally:
            grant_combo.blockSignals(prev)
        _ensure_grant_completer()

    def _set_grant_combo_enabled(enabled: bool, placeholder: str | None = None):
        try:
            grant_combo.setEnabled(bool(enabled))
        except Exception:
            pass
        if placeholder is not None:
            try:
                if grant_combo.lineEdit():
                    grant_combo.lineEdit().setPlaceholderText(str(placeholder))
            except Exception:
                pass

    def _get_selected_subgroup() -> Optional[dict]:
        try:
            data = subgroup_combo.currentData()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _get_selected_grant() -> str:
        try:
            text = (grant_combo.currentText() or '').strip()
            if not text or text == "(フィルタなし)":
                return ""
            return text
        except Exception:
            return ""

    def _get_allowed_grants_by_subgroup() -> Optional[set[str]]:
        sg = _get_selected_subgroup()
        if not sg:
            return None
        grants = sg.get('grant_numbers')
        if not isinstance(grants, list) or not grants:
            return None
        try:
            return {str(g).strip() for g in grants if str(g).strip()}
        except Exception:
            return None

    def refresh_subgroup_and_grant_filters():
        """サブグループ/課題番号候補を読み込み、コンボを更新する。

        - 権限フィルタあり: ユーザー所属サブグループを、選択ロールで絞って表示
        - フィルタなし: subGroup.json由来の全サブグループを表示
        """
        try:
            current_user_id = get_current_user_id_for_data_entry()
            if not current_user_id:
                _populate_subgroup_combo([])
                _populate_grant_combo([])
                return

            # フィルタなし: 全サブグループ
            if checkbox_no_filter.isChecked():
                all_raw = get_subgroups_for_data_entry()
                all_items: list[dict] = []
                if isinstance(all_raw, list):
                    for raw in all_raw:
                        norm = _normalize_subgroup_item(raw)
                        if norm:
                            all_items.append(norm)
                elif isinstance(all_raw, dict):
                    norm = _normalize_subgroup_item(all_raw)
                    if norm:
                        all_items.append(norm)

                _populate_subgroup_combo(all_items)

                # 課題番号は「サブグループ選択後」に、そのサブグループに紐づくもののみを表示
                allowed = _get_allowed_grants_by_subgroup()
                if allowed is None:
                    _populate_grant_combo([])
                    _set_grant_combo_enabled(False, "先にサブグループを選択してください")
                else:
                    _populate_grant_combo(sorted(allowed))
                    _set_grant_combo_enabled(True, "課題番号で絞り込み")
                return

            # 権限フィルタあり: ユーザー所属サブグループ（選択ロールで絞る）
            info = get_user_subgroups_and_grants(current_user_id)
            user_subgroups = info.get("subgroups") if isinstance(info, dict) else []
            if not isinstance(user_subgroups, list):
                user_subgroups = []

            selected_roles = _get_selected_roles()
            if selected_roles:
                filtered_subgroups = [
                    sg for sg in user_subgroups
                    if isinstance(sg, dict) and str(sg.get("role") or "") in selected_roles
                ]
            else:
                filtered_subgroups = user_subgroups

            # 課題番号候補も、表示サブグループに合わせて絞る
            grants_from_subgroups: set[str] = set()
            for sg in filtered_subgroups:
                try:
                    for g in (sg.get("grant_numbers") or []):
                        if g:
                            grants_from_subgroups.add(str(g).strip())
                except Exception:
                    continue

            _populate_subgroup_combo(filtered_subgroups)
            _populate_grant_combo(sorted({g for g in grants_from_subgroups if g}))
            _set_grant_combo_enabled(True, "課題番号で絞り込み")
        except Exception:
            _populate_subgroup_combo([])
            _populate_grant_combo([])
            _set_grant_combo_enabled(False, "先にサブグループを選択してください")

    def _on_subgroup_changed(*_args):
        # サブグループ選択に応じて課題番号候補も絞り込み
        allowed = _get_allowed_grants_by_subgroup()
        if allowed is None:
            # 全候補へ戻す
            try:
                # いまの状態に応じて、候補を再構築
                refresh_subgroup_and_grant_filters()
                # refresh_subgroup_and_grant_filters() 内で grant_combo を更新済み
                update_filtered_datasets()
                return
            except Exception:
                _populate_grant_combo([])
                _set_grant_combo_enabled(False, "先にサブグループを選択してください")
        else:
            _populate_grant_combo(sorted(allowed))
            _set_grant_combo_enabled(True, "課題番号で絞り込み")
        update_filtered_datasets()

    def _on_grant_changed(*_args):
        update_filtered_datasets()

    def _build_no_filter_items(force_reload: bool = False):
        if (not force_reload) and no_filter_cache.get("ready") and isinstance(no_filter_cache.get("items"), list):
            return no_filter_cache["items"], int(no_filter_cache.get("count", 0))

        all_datasets = get_datasets_for_data_entry()
        items = [(get_colored_dataset_display_name(ds), ds) for ds in all_datasets]
        no_filter_cache["items"] = items
        no_filter_cache["count"] = len(all_datasets)
        no_filter_cache["ready"] = True
        return items, len(all_datasets)
    
    # データ読み込みと初期表示
    def update_filtered_datasets():
        """フィルタを適用してデータセット一覧を更新"""
        combo.clear()
        
        # 現在のユーザーIDを取得
        current_user_id = get_current_user_id_for_data_entry()
        if not current_user_id:
            status_label.setText("⚠️ ユーザー情報が取得できません")
            return
        
        # フィルタなしの場合は全件表示（ただしサブグループ/課題番号の上位フィルタは適用する）
        if checkbox_no_filter.isChecked():
            try:
                status_label.setText("🔍 フィルタなし: 読み込み中...")
                items, total = _build_no_filter_items(force_reload=False)
                allowed_grants = _get_allowed_grants_by_subgroup()
                selected_grant = _get_selected_grant()
                if allowed_grants or selected_grant:
                    filtered_items = []
                    for display_name, dataset in items:
                        try:
                            grant_number = (dataset.get('attributes', {}) or {}).get('grantNumber') if isinstance(dataset, dict) else None
                            grant_number = str(grant_number).strip() if grant_number else ""
                        except Exception:
                            grant_number = ""

                        if selected_grant:
                            if grant_number == selected_grant:
                                filtered_items.append((display_name, dataset))
                        elif allowed_grants is not None:
                            if grant_number and grant_number in allowed_grants:
                                filtered_items.append((display_name, dataset))
                    items = filtered_items

                _populate_combo(items)
                status_label.setText(f"✅ フィルタなし: {len(items)}件")
                return
            except Exception as e:
                status_label.setText(f"❌ エラー: {str(e)}")
                print(f"[ERROR] データセット更新エラー(フィルタなし): {e}")
                return

        # 選択された権限を取得
        selected_roles: List[str] = []
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
            
            # 最適化されたフィルタリング実行
            filtered_datasets = filter_datasets_by_checkbox_selection_optimized(current_user_id, selected_roles)

            # 上位フィルタ: サブグループ/課題番号
            allowed_grants = _get_allowed_grants_by_subgroup()
            selected_grant = _get_selected_grant()
            if allowed_grants or selected_grant:
                narrowed = []
                for dataset in filtered_datasets:
                    try:
                        grant_number = (dataset.get('attributes', {}) or {}).get('grantNumber') if isinstance(dataset, dict) else None
                        grant_number = str(grant_number).strip() if grant_number else ""
                    except Exception:
                        grant_number = ""

                    if selected_grant:
                        if grant_number == selected_grant:
                            narrowed.append(dataset)
                    elif allowed_grants is not None:
                        if grant_number and grant_number in allowed_grants:
                            narrowed.append(dataset)
                filtered_datasets = narrowed
            
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
            _ensure_completer()
            
        except Exception as e:
            status_label.setText(f"❌ エラー: {str(e)}")
            print(f"[ERROR] データセット更新エラー: {e}")
    
    # フィルタ変更時の処理
    def on_filter_changed():
        # 権限チェック状態に応じてサブグループ候補も連動
        if not checkbox_no_filter.isChecked():
            refresh_subgroup_and_grant_filters()
        update_filtered_datasets()

    def on_no_filter_changed():
        """フィルタなしのON/OFFで他チェックを無効化/復帰"""
        enabled = not checkbox_no_filter.isChecked()
        for cb in (checkbox_owner, checkbox_assistant, checkbox_member, checkbox_agent):
            cb.setEnabled(enabled)
        refresh_no_filter_btn.setEnabled(not enabled)
        refresh_subgroup_and_grant_filters()
        update_filtered_datasets()

    def on_refresh_no_filter_cache():
        """フィルタなしキャッシュを破棄して再構築"""
        if not checkbox_no_filter.isChecked():
            return
        no_filter_cache["items"] = None
        no_filter_cache["count"] = 0
        no_filter_cache["ready"] = False
        try:
            status_label.setText("🔄 フィルタなし: 再読み込み中...")
            items, total = _build_no_filter_items(force_reload=True)
            _populate_combo(items)
            status_label.setText(f"✅ フィルタなし: {total}件")
        except Exception as e:
            status_label.setText(f"❌ エラー: {str(e)}")
    
    # イベント接続（各チェックボックス）
    checkbox_owner.stateChanged.connect(on_filter_changed)
    checkbox_assistant.stateChanged.connect(on_filter_changed)
    checkbox_member.stateChanged.connect(on_filter_changed)
    checkbox_agent.stateChanged.connect(on_filter_changed)
    checkbox_no_filter.stateChanged.connect(on_no_filter_changed)
    refresh_no_filter_btn.clicked.connect(on_refresh_no_filter_cache)

    # 上位フィルタ（サブグループ/課題番号）
    try:
        subgroup_combo.currentIndexChanged.connect(_on_subgroup_changed)
    except Exception:
        pass
    try:
        grant_combo.currentIndexChanged.connect(_on_grant_changed)
    except Exception:
        pass
    try:
        grant_combo.editTextChanged.connect(_on_grant_changed)
    except Exception:
        pass
    
    # 初回読み込み
    refresh_subgroup_and_grant_filters()
    update_filtered_datasets()
    
    # データセット更新通知システムに登録
    def setup_dataset_refresh_notification():
        """データセット更新通知システムに登録"""
        try:
            from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
            dataset_notifier = get_dataset_refresh_notifier()
            
            def refresh_callback():
                """データセットリスト更新コールバック"""
                try:
                    print("[INFO] フィルタ付きドロップダウン: データセットリスト更新開始")
                    clear_user_cache()  # キャッシュクリア
                    no_filter_cache["items"] = None
                    no_filter_cache["count"] = 0
                    no_filter_cache["ready"] = False
                    update_filtered_datasets()  # データセット再読み込み
                    print("[INFO] フィルタ付きドロップダウン: データセットリスト更新完了")
                except Exception as e:
                    print(f"[ERROR] フィルタ付きドロップダウン: データセットリスト更新に失敗: {e}")
            
            dataset_notifier.register_callback(refresh_callback)
            print("[INFO] フィルタ付きドロップダウン: データセット更新通知に登録完了")
            
            # ウィジェット破棄時の通知解除用
            def cleanup_callback():
                dataset_notifier.unregister_callback(refresh_callback)
                print("[INFO] フィルタ付きドロップダウン: データセット更新通知を解除")
            
            container._cleanup_dataset_callback = cleanup_callback
            
        except Exception as e:
            print(f"[WARNING] フィルタ付きドロップダウン: データセット更新通知への登録に失敗: {e}")
    
    # 通知システム初期化
    setup_dataset_refresh_notification()
    
    # ウィジェットにアクセス用属性を設定
    container.dataset_dropdown = combo
    container.filter_widget = filter_widget
    container.status_label = status_label
    container.update_datasets = update_filtered_datasets
    container.clear_cache = clear_user_cache
    container.subgroup_filter_combo = subgroup_combo
    container.grant_number_combo = grant_combo
    container.refresh_subgroup_and_grant_filters = refresh_subgroup_and_grant_filters

    def _apply_role_filter_state(owner=True, assistant=True, member=True, agent=True, force_reload=False):
        # ロール指定が入る場合は「フィルタなし」を解除
        if checkbox_no_filter.isChecked():
            prev = checkbox_no_filter.blockSignals(True)
            checkbox_no_filter.setChecked(False)
            checkbox_no_filter.blockSignals(prev)
            for cb in (checkbox_owner, checkbox_assistant, checkbox_member, checkbox_agent):
                cb.setEnabled(True)

        checkboxes = [
            (checkbox_owner, owner),
            (checkbox_assistant, assistant),
            (checkbox_member, member),
            (checkbox_agent, agent),
        ]
        changed = False
        for checkbox, desired in checkboxes:
            if checkbox.isChecked() != desired:
                prev = checkbox.blockSignals(True)
                checkbox.setChecked(desired)
                checkbox.blockSignals(prev)
                changed = True
        if force_reload or changed:
            update_filtered_datasets()
        return changed

    def set_role_filters(owner=True, assistant=True, member=True, agent=True, force_reload=False):
        return _apply_role_filter_state(owner, assistant, member, agent, force_reload)

    def relax_filters_for_launch():
        _apply_role_filter_state(True, True, True, True, True)

    container.set_role_filters = set_role_filters
    container.relax_filters_for_launch = relax_filters_for_launch
    container.no_filter_checkbox = checkbox_no_filter
    container.no_filter_refresh_button = refresh_no_filter_btn
    container.refresh_no_filter_cache = on_refresh_no_filter_cache
    
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
