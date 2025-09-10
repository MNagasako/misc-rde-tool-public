def check_global_sharing_enabled(dataset_item):
    """
    データセットの広域シェア設定が有効かどうかを判定
    
    Args:
        dataset_item (dict): データセット情報
    
    Returns:
        bool: 広域シェアが有効な場合True、無効の場合False
    """
    if not isinstance(dataset_item, dict):
        return False
    
    # allowsToViewDataListフィールドで判定
    return dataset_item.get('meta', {}).get('allowsToViewDataList', False)

def get_current_user_id():
    """
    現在ログイン中のユーザーIDを取得する
    
    Returns:
        str: ユーザーID、取得できない場合はNone
    """
    import os
    import json
    
    try:
        # self.jsonのパスを取得
        self_json_path = os.path.join('output', 'rde', 'data', 'self.json')
        
        if not os.path.exists(self_json_path):
            return None
        
        with open(self_json_path, 'r', encoding='utf-8') as f:
            self_data = json.load(f)
        
        return self_data.get('data', {}).get('id')
        
    except Exception as e:
        print(f"[ERROR] ユーザーID取得エラー: {e}")
        return None

def check_user_is_member(dataset_item, user_id):
    """
    指定ユーザーがデータセットの関係メンバー（manager、dataOwners、applicant）かどうかを判定
    
    Args:
        dataset_item (dict): データセット情報
        user_id (str): チェック対象のユーザーID
    
    Returns:
        bool: 関係メンバーの場合True、そうでない場合False
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
        print(f"[ERROR] ユーザーメンバーシップ判定エラー: {e}")
        return False

def check_dataset_type_match(dataset_item, dataset_type_filter):
    """
    データセットタイプが指定された条件に一致するかを判定
    
    Args:
        dataset_item (dict): データセット情報
        dataset_type_filter (str): データセットタイプフィルタ ("all", "RECIPE","ANALYSIS","PROPERTY_PERFORMANCE","REPORT", "CALCULATION","OTHERS")

    Returns:
        bool: 条件に一致する場合True、そうでない場合False
    """
    if dataset_type_filter == "all":
        return True
    
    if not isinstance(dataset_item, dict):
        return False
    
    try:
        dataset_type = dataset_item.get('attributes', {}).get('datasetType')
        return dataset_type == dataset_type_filter
        
    except Exception as e:
        print(f"[ERROR] データセットタイプ判定エラー: {e}")
        return False

def check_grant_number_match(dataset_item, grant_number_filter):
    """
    課題番号が指定された条件に一致するかを判定（部分一致）
    
    Args:
        dataset_item (dict): データセット情報
        grant_number_filter (str): 課題番号フィルタ（空文字列の場合は全件一致）
    
    Returns:
        bool: 条件に一致する場合True、そうでない場合False
    """
    if not grant_number_filter or grant_number_filter.strip() == "":
        return True
    
    if not isinstance(dataset_item, dict):
        return False
    
    try:
        grant_number = dataset_item.get('attributes', {}).get('grantNumber', '')
        if not grant_number:
            return False
        
        # 部分一致判定（大文字小文字を区別しない）
        return grant_number_filter.lower() in grant_number.lower()
        
    except Exception as e:
        print(f"[ERROR] 課題番号判定エラー: {e}")
        return False

def get_dataset_type_display_map():
    """
    データセットタイプの日本語表示名マッピングを取得
    
    Returns:
        dict: データセットタイプの日本語表示名マッピング
    """
    return {
        "RECIPE": "加工・計測レシピ型",
        "ANALYSIS": "構造解析・リファレンス型", 
        "PROPERTY_PERFORMANCE": "特性・性能規定型",
        "REPORT": "成果報告書型",
        "CALCULATION": "計算値・理論値型",
        "OTHERS": "その他"
    }

def get_unique_dataset_types(dataset_json_path):
    """
    dataset.jsonから利用可能なデータセットタイプのリストを取得
    
    Args:
        dataset_json_path (str): dataset.jsonのパス
    
    Returns:
        list: データセットタイプのリスト
    """
    import os
    import json
    
    if not os.path.exists(dataset_json_path):
        return []
    
    try:
        with open(dataset_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        dataset_types = set()
        for dataset in data.get('data', []):
            dataset_type = dataset.get('attributes', {}).get('datasetType')
            if dataset_type:
                dataset_types.add(dataset_type)
        
        return sorted(list(dataset_types))
        
    except Exception as e:
        print(f"[ERROR] データセットタイプ取得エラー: {e}")
        return []

def create_dataset_dropdown_all(dataset_json_path, parent=None, global_share_filter="both", user_membership_filter="both", dataset_type_filter="all", grant_number_filter=""):
    """
    dataset.jsonの全データセットをユーザーフィルタなしでQComboBox（検索付き）で表示
    広域シェア設定、ユーザーメンバーシップ、データセットタイプ、課題番号による複合フィルタリング機能を追加
    
    Args:
        dataset_json_path (str): dataset.jsonのパス
        parent (QWidget): 親ウィジェット
        global_share_filter (str): 広域シェアフィルタ ("enabled", "disabled", "both")
        user_membership_filter (str): ユーザーメンバーシップフィルタ ("member", "non_member", "both")
        dataset_type_filter (str): データセットタイプフィルタ ("all", "ANALYSIS", "RECIPE")
        grant_number_filter (str): 課題番号フィルタ（部分一致、空文字列で全件）
    """
    import os
    import json
    from PyQt5.QtWidgets import QVBoxLayout, QWidget, QLabel, QComboBox, QSizePolicy, QCompleter, QHBoxLayout, QRadioButton, QButtonGroup, QLineEdit, QGroupBox
    from PyQt5.QtCore import Qt

    combo = QComboBox(parent)
    combo.setMinimumWidth(320)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(12)
    combo.view().setMinimumHeight(240)
    
    # 広域シェアフィルタUI作成
    filter_widget = QWidget(parent)
    filter_layout = QHBoxLayout(filter_widget)
    filter_layout.setContentsMargins(0, 0, 0, 0)
    filter_layout.setSpacing(10)
    
    filter_label = QLabel("広域シェア設定:")
    filter_layout.addWidget(filter_label)
    
    # ラジオボタングループ
    button_group = QButtonGroup(filter_widget)
    
    radio_both = QRadioButton("両方")
    radio_enabled = QRadioButton("有効のみ")
    radio_disabled = QRadioButton("無効のみ")
    
    button_group.addButton(radio_both, 0)
    button_group.addButton(radio_enabled, 1)
    button_group.addButton(radio_disabled, 2)
    
    filter_layout.addWidget(radio_both)
    filter_layout.addWidget(radio_enabled)
    filter_layout.addWidget(radio_disabled)
    filter_layout.addStretch()
    
    # ユーザーメンバーシップフィルタUI作成
    membership_widget = QWidget(parent)
    membership_layout = QHBoxLayout(membership_widget)
    membership_layout.setContentsMargins(0, 0, 0, 0)
    membership_layout.setSpacing(10)
    
    membership_label = QLabel("関係メンバー:")
    membership_layout.addWidget(membership_label)
    
    # ユーザーメンバーシップ用ラジオボタングループ
    membership_button_group = QButtonGroup(membership_widget)
    
    membership_radio_both = QRadioButton("両方")
    membership_radio_member = QRadioButton("メンバーのみ")
    membership_radio_non_member = QRadioButton("非メンバーのみ")
    
    membership_button_group.addButton(membership_radio_both, 0)
    membership_button_group.addButton(membership_radio_member, 1)
    membership_button_group.addButton(membership_radio_non_member, 2)
    
    membership_layout.addWidget(membership_radio_both)
    membership_layout.addWidget(membership_radio_member)
    membership_layout.addWidget(membership_radio_non_member)
    membership_layout.addStretch()
    
    # データセットタイプフィルタUI作成
    type_widget = QWidget(parent)
    type_layout = QHBoxLayout(type_widget)
    type_layout.setContentsMargins(0, 0, 0, 0)
    type_layout.setSpacing(10)
    
    type_label = QLabel("データセットタイプ:")
    type_layout.addWidget(type_label)
    
    # データセットタイプ選択用コンボボックス
    type_combo = QComboBox(type_widget)
    type_combo.addItem("全て", "all")
    
    # 利用可能なデータセットタイプを動的に取得して日本語表示名を付ける
    available_types = get_unique_dataset_types(dataset_json_path)
    
    # データセットタイプの日本語表示名マッピングを取得
    type_display_map = get_dataset_type_display_map()
    
    for dtype in available_types:
        display_name = type_display_map.get(dtype, dtype)  # マッピングにない場合は元の名前を使用
        type_combo.addItem(display_name, dtype)
    
    type_layout.addWidget(type_combo)
    type_layout.addStretch()
    
    # 課題番号フィルタUI作成
    grant_widget = QWidget(parent)
    grant_layout = QHBoxLayout(grant_widget)
    grant_layout.setContentsMargins(0, 0, 0, 0)
    grant_layout.setSpacing(10)
    
    grant_label = QLabel("課題番号:")
    grant_layout.addWidget(grant_label)
    
    grant_line_edit = QLineEdit(grant_widget)
    grant_line_edit.setPlaceholderText("部分一致で検索（例：JPMXP1222）")
    grant_line_edit.setMinimumWidth(200)
    grant_layout.addWidget(grant_line_edit)
    grant_layout.addStretch()
    
    # デフォルト選択
    if global_share_filter == "enabled":
        radio_enabled.setChecked(True)
    elif global_share_filter == "disabled":
        radio_disabled.setChecked(True)
    else:
        radio_both.setChecked(True)
    
    if user_membership_filter == "member":
        membership_radio_member.setChecked(True)
    elif user_membership_filter == "non_member":
        membership_radio_non_member.setChecked(True)
    else:
        membership_radio_both.setChecked(True)
    
    # データセットタイプのデフォルト設定
    type_index = type_combo.findData(dataset_type_filter)
    if type_index >= 0:
        type_combo.setCurrentIndex(type_index)
    
    # 課題番号のデフォルト設定
    if grant_number_filter:
        grant_line_edit.setText(grant_number_filter)

    def load_and_filter_datasets(global_filter_type="both", membership_filter_type="both", dtype_filter="all", grant_filter=""):
        """データセットを読み込み、複合フィルタを適用してドロップダウンを更新"""
        combo.clear()
        combo.lineEdit().setPlaceholderText("データセット名・課題番号・タイトルで検索")
        
        # 現在ログイン中のユーザーIDを取得
        current_user_id = get_current_user_id()
        
        # dataset.jsonの読み込み
        if not os.path.exists(dataset_json_path):
            dataset_items = []
        else:
            try:
                with open(dataset_json_path, 'r', encoding='utf-8') as f:
                    dataset_data = json.load(f)
                if isinstance(dataset_data, dict) and 'data' in dataset_data:
                    dataset_items = dataset_data['data']
                elif isinstance(dataset_data, list):
                    dataset_items = dataset_data
                else:
                    dataset_items = []
            except Exception as e:
                print(f"[ERROR] dataset.jsonの読み込み・パースに失敗: {e}")
                dataset_items = []

        # 先頭に空欄を追加
        combo.addItem("", None)
        display_list = [""]
        filtered_count = 0
        total_count = len(dataset_items)
        
        for idx, item in enumerate(dataset_items):
            if not isinstance(item, dict):
                continue
            
            # 広域シェアフィルタの適用
            is_global_share_enabled = check_global_sharing_enabled(item)
            
            if global_filter_type == "enabled" and not is_global_share_enabled:
                continue
            elif global_filter_type == "disabled" and is_global_share_enabled:
                continue
            
            # ユーザーメンバーシップフィルタの適用
            is_user_member = check_user_is_member(item, current_user_id) if current_user_id else False
            
            if membership_filter_type == "member" and not is_user_member:
                continue
            elif membership_filter_type == "non_member" and is_user_member:
                continue
            
            # データセットタイプフィルタの適用
            if not check_dataset_type_match(item, dtype_filter):
                continue
            
            # 課題番号フィルタの適用
            if not check_grant_number_match(item, grant_filter):
                continue
            
            # 全フィルタ条件をクリアしたデータセットのみ表示対象
            filtered_count += 1
            
            attr = item.get('attributes', {})
            dataset_id = item.get('id')
            name = attr.get('name', dataset_id)
            subject_title = attr.get('subjectTitle', '')
            grant_number = attr.get('grantNumber', '')
            dataset_type = attr.get('datasetType', '')
            
            def truncate(text, maxlen=30):
                return (text[:maxlen] + '…') if text and len(text) > maxlen else text
            
            name_disp = truncate(name, 60)
            subject_disp = truncate(subject_title, 20)
            grant_disp = grant_number if grant_number else "<課題番号未設定>"
            
            # データセットタイプの日本語表示名を取得
            type_display_map = get_dataset_type_display_map()
            type_display = type_display_map.get(dataset_type, dataset_type) if dataset_type else "タイプ未設定"
            type_disp = f"[{type_display}]"
            
            # 広域シェア状態を表示に含める
            share_status = "🌐" if is_global_share_enabled else "🔒"
            user_status = "👤" if is_user_member else "👥"
            display = f"{share_status}{user_status} {type_disp} {grant_disp} {subject_disp} {name_disp}".strip()
            
            combo.addItem(display, dataset_id)
            # datasetのdictをUserRoleで保持
            try:
                combo.setItemData(combo.count()-1, item, Qt.UserRole)
            except Exception as e:
                print(f"[ERROR] combo.setItemData失敗: idx={combo.count()-1}, error={e}")
            display_list.append(display)
        
        combo.setCurrentIndex(0)
        
        # QCompleterで補完・絞り込み
        completer = QCompleter(display_list, combo)
        completer.setCaseSensitivity(False)
        completer.setFilterMode(Qt.MatchContains)
        popup_view = completer.popup()
        popup_view.setMinimumHeight(240)
        popup_view.setMaximumHeight(240)
        combo.setCompleter(completer)
        
        # フィルタ結果を表示
        print(f"[INFO] フィルタ適用 - 広域シェア: {global_filter_type}, メンバーシップ: {membership_filter_type}, データタイプ: {dtype_filter}, 課題番号: '{grant_filter}', 表示数: {filtered_count}/{total_count}")
        
        return filtered_count, total_count
    
    # フィルタ変更時の処理
    def on_filter_changed():
        # 現在選択されているフィルタを取得
        global_filter_types = {0: "both", 1: "enabled", 2: "disabled"}
        membership_filter_types = {0: "both", 1: "member", 2: "non_member"}
        
        global_filter_type = global_filter_types.get(button_group.checkedId(), "both")
        membership_filter_type = membership_filter_types.get(membership_button_group.checkedId(), "both")
        dtype_filter = type_combo.currentData() or "all"
        grant_filter = grant_line_edit.text().strip()
        
        filtered_count, total_count = load_and_filter_datasets(global_filter_type, membership_filter_type, dtype_filter, grant_filter)
        
        # 状況をラベルに表示
        if hasattr(combo, '_status_label'):
            status_text = f"表示中: {filtered_count}/{total_count} 件"
            combo._status_label.setText(status_text)
    
    button_group.buttonClicked[int].connect(lambda: on_filter_changed())
    membership_button_group.buttonClicked[int].connect(lambda: on_filter_changed())
    type_combo.currentTextChanged.connect(lambda: on_filter_changed())
    grant_line_edit.textChanged.connect(lambda: on_filter_changed())
    
    # 初回読み込み
    initial_global_filter = global_share_filter if global_share_filter in ["enabled", "disabled", "both"] else "both"
    initial_membership_filter = user_membership_filter if user_membership_filter in ["member", "non_member", "both"] else "both"
    initial_dtype_filter = dataset_type_filter if dataset_type_filter else "all"
    initial_grant_filter = grant_number_filter if grant_number_filter else ""
    filtered_count, total_count = load_and_filter_datasets(initial_global_filter, initial_membership_filter, initial_dtype_filter, initial_grant_filter)

    # ラベルとドロップダウンを縦に並べて返す
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    
    # データセット選択ラベル
    layout.addWidget(QLabel("データセット選択:"))
    
    # 広域シェアフィルタUI
    layout.addWidget(filter_widget)
    
    # ユーザーメンバーシップフィルタUI
    layout.addWidget(membership_widget)
    
    # データセットタイプフィルタUI
    layout.addWidget(type_widget)
    
    # 課題番号フィルタUI
    layout.addWidget(grant_widget)
    
    # 状況表示ラベル
    status_label = QLabel(f"表示中: {filtered_count}/{total_count} 件")
    status_label.setStyleSheet("color: #666; font-size: 9pt;")
    combo._status_label = status_label
    layout.addWidget(status_label)
    
    # ドロップダウン
    layout.addWidget(combo)
    
    container.setLayout(layout)
    container.dataset_dropdown = combo
    container.filter_widget = filter_widget
    container.membership_widget = membership_widget
    container.button_group = button_group
    container.membership_button_group = membership_button_group

    # 選択時に選択オブジェクトをポップアップ表示（動作確認用）
    def on_dataset_changed(idx):
        from PyQt5.QtWidgets import QMessageBox
        item = combo.itemData(idx, Qt.UserRole)
        if item is not None:
            import json
            # デバッグ用コメントアウト
            # msg = json.dumps(item, ensure_ascii=False, indent=2)
            # QMessageBox.information(parent, "選択データセット情報", msg)
            pass
    combo.currentIndexChanged.connect(on_dataset_changed)

    return container

def load_dataset_and_user_list(dataset_json_path, info_json_path):
    """
    dataset.jsonとinfo.jsonを結合し、grantNumber name userName organizationName のリストを返す
    """
    # データセット情報の取得
    if not os.path.exists(dataset_json_path):
        print(f"[ERROR] dataset_json_pathが存在しません: {dataset_json_path}")
        return []
    try:
        with open(dataset_json_path, 'r', encoding='utf-8') as f:
            dataset_data = json.load(f)
    except Exception as e:
        print(f"[ERROR] dataset.jsonの読み込み・パースに失敗: {e}")
        return []
    if isinstance(dataset_data, dict) and 'data' in dataset_data:
        dataset_items = dataset_data['data']
    elif isinstance(dataset_data, list):
        dataset_items = dataset_data
    else:
        print(f"[ERROR] dataset.jsonの形式が不正: {type(dataset_data)}")
        dataset_items = []
    print(f"[INFO] dataset.json件数: {len(dataset_items)}")

    # info.jsonの件数も表示
    if info_json_path and os.path.exists(info_json_path):
        try:
            with open(info_json_path, 'r', encoding='utf-8') as f:
                info_data = json.load(f)
            if isinstance(info_data, dict):
                info_count = len(info_data)
            elif isinstance(info_data, list):
                info_count = len(info_data)
            else:
                info_count = 0
            print(f"[INFO] info.json件数: {info_count}")
        except Exception as e:
            print(f"[ERROR] info.jsonの読み込み・パースに失敗: {e}")
    else:
        print(f"[WARNING] info.jsonが存在しません: {info_json_path}")

    # self.jsonの存在確認
    self_json_path = os.path.join(os.path.dirname(dataset_json_path), 'self.json')
    if os.path.exists(self_json_path):
        try:
            with open(self_json_path, 'r', encoding='utf-8') as f:
                self_data = json.load(f)
            if isinstance(self_data, dict):
                print(f"[INFO] self.json: dataキー有無: {'data' in self_data}, id: {self_data.get('data', {}).get('id')}")
            else:
                print(f"[INFO] self.json: dict型でない")
        except Exception as e:
            print(f"[ERROR] self.jsonの読み込み・パースに失敗: {e}")
    else:
        print(f"[WARNING] self.jsonが存在しません: {self_json_path}")

    # 自身のユーザーID取得
    self_json_path = os.path.join(os.path.dirname(dataset_json_path), 'self.json')
    user_id = None
    if os.path.exists(self_json_path):
        try:
            with open(self_json_path, 'r', encoding='utf-8') as f:
                self_data = json.load(f)
            user_id = self_data.get('data', {}).get('id')
        except Exception as e:
            print(f"[ERROR] self.jsonの読み込みに失敗: {e}")
    print(f"[dataset_dropdown_util] フィルタ抽出に使うユーザーID: {user_id}")

    # info.jsonは結合しない
    # user_map = {}  # info.jsonのusersマッピングは不要

    # データセットごとにuser情報を付与し、ユーザーIDでフィルタ
    result = []
    for item in dataset_items:
        if not isinstance(item, dict):
            continue
        attr = item.get('attributes', {})
        dataset_id = item.get('id')
        name = attr.get('name', dataset_id)
        subject_title = attr.get('subjectTitle', '')
        grant_number = attr.get('grantNumber', '')
        def truncate(text, maxlen=15):
            return (text[:maxlen] + '…') if text and len(text) > maxlen else text
        name_disp = truncate(name, 30)
        subject_disp = truncate(subject_title, 10)
        relationships = item.get('relationships', {})
        # --- フィルタ条件 ---
        match = False
        if user_id:
            # manager
            manager = relationships.get('manager', {}).get('data', {})
            if isinstance(manager, dict) and manager.get('id') == user_id:
                match = True
            # applicant
            applicant = relationships.get('applicant', {}).get('data', {})
            if isinstance(applicant, dict) and applicant.get('id') == user_id:
                match = True
            # dataOwners
            data_owners = relationships.get('dataOwners', {}).get('data', [])
            if isinstance(data_owners, list):
                for owner in data_owners:
                    if isinstance(owner, dict) and owner.get('id') == user_id:
                        match = True
                        break
            # attributes.ownerId/userId
            if attr.get('ownerId') == user_id or attr.get('userId') == user_id:
                match = True
            
            print(f"[DEBUG] dataset_id={dataset_id}, user_id={user_id}, match={match}")
        else:
            # user_idが取得できなければ全件表示（従来通り）
            match = True
            print(f"[DEBUG] user_idなし、全件表示: dataset_id={dataset_id}")
        
        if not match:
            continue
        # ---
        owner_id = None
        manager = relationships.get('manager', {}).get('data', {})
        if isinstance(manager, dict) and manager.get('id'):
            owner_id = manager.get('id')
        if not owner_id:
            applicant = relationships.get('applicant', {}).get('data', {})
            if isinstance(applicant, dict) and applicant.get('id'):
                owner_id = applicant.get('id')
        if not owner_id:
            data_owners = relationships.get('dataOwners', {}).get('data', [])
            if isinstance(data_owners, list) and len(data_owners) > 0 and isinstance(data_owners[0], dict):
                owner_id = data_owners[0].get('id')
        if not owner_id:
            owner_id = attr.get('ownerId') or attr.get('userId')
        # user_info = user_map.get(owner_id, {'userName': '', 'organizationName': ''})  # info.json結合しないので不要
        if grant_number:
            grant_disp = grant_number
        else:
            grant_disp = "<課題番号未設定>"
        display = f"{grant_disp} {subject_disp} {name_disp}".strip()
        if dataset_id:
            # grantNumberが未設定かどうかも返す。item自体も返す
            result.append((display, dataset_id, not bool(grant_number), item))
    return result

from PyQt5.QtWidgets import QComboBox, QSizePolicy, QCompleter
from PyQt5.QtCore import Qt

def create_dataset_dropdown_with_user(dataset_json_path, info_json_path, parent=None):
    """
    dataset.jsonとinfo.jsonを結合し、QComboBox（補完検索付き）を生成
    """
    from PyQt5.QtWidgets import QVBoxLayout, QWidget, QLabel
    combo = QComboBox(parent)
    combo.setMinimumWidth(320)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(12)
    combo.view().setMinimumHeight(240)
    # プレースホルダー
    combo.clear()
    combo.lineEdit().setPlaceholderText("データセット名・課題番号・タイトルで検索")

    # 件数情報取得（info.jsonは結合しない）
    dataset_count = 0
    self_id = None
    
    # 静的定数を使用してパス管理を統一
    from config.common import DATASET_JSON_PATH, INFO_JSON_PATH, SELF_JSON_PATH
    
    # 引数で渡されたパスを優先使用、フォールバックで静的定数を使用
    actual_dataset_json_path = dataset_json_path if dataset_json_path and os.path.exists(dataset_json_path) else DATASET_JSON_PATH
    actual_info_json_path = info_json_path if info_json_path and os.path.exists(info_json_path) else INFO_JSON_PATH
    
    print(f"[DEBUG] パス解決結果:")
    print(f"[DEBUG]   引数dataset_json_path: {dataset_json_path}")
    print(f"[DEBUG]   引数info_json_path: {info_json_path}")
    print(f"[DEBUG]   実際使用dataset_json_path: {actual_dataset_json_path}")
    print(f"[DEBUG]   実際使用info_json_path: {actual_info_json_path}")
    print(f"[DEBUG]   SELF_JSON_PATH: {SELF_JSON_PATH}")
    
    if actual_dataset_json_path and os.path.exists(actual_dataset_json_path):
        try:
            with open(actual_dataset_json_path, 'r', encoding='utf-8') as f:
                dataset_data = json.load(f)
            if isinstance(dataset_data, dict) and 'data' in dataset_data:
                dataset_count = len(dataset_data['data'])
            elif isinstance(dataset_data, list):
                dataset_count = len(dataset_data)
        except Exception as e:
            print(f"[ERROR] dataset.json読み込みエラー: {e}")
    else:
        print(f"[ERROR] dataset.jsonが存在しません: {actual_dataset_json_path}")
    
    # self.jsonも静的パス管理を使用
    self_json_path = SELF_JSON_PATH
    if os.path.exists(self_json_path):
        try:
            with open(self_json_path, 'r', encoding='utf-8') as f:
                self_data = json.load(f)
            if isinstance(self_data, dict):
                self_id = self_data.get('data', {}).get('id')
        except Exception:
            pass

    # 件数・パスラベル
    info_text = f"dataset.json: {dataset_count}件 / self.json: {'OK' if self_id else 'なし'}"
    # フルパスも表示
    dataset_json_abspath = os.path.abspath(actual_dataset_json_path) if actual_dataset_json_path else 'N/A'
    self_json_abspath = os.path.abspath(self_json_path) if os.path.exists(self_json_path) else 'なし'
    path_text = f"dataset.json: {dataset_json_abspath}\nself.json: {self_json_abspath}"
    info_label = QLabel(info_text)
    info_label.setStyleSheet("color: #1976d2; font-size: 10pt; padding: 2px 0px;")
    path_label = QLabel(path_text)
    path_label.setStyleSheet("color: #888; font-size: 9pt; padding: 0px 0px;")

    # ドロップダウン生成
    dataset_list = load_dataset_and_user_list(actual_dataset_json_path, actual_info_json_path)
    print(f"[DEBUG] dataset_list生成結果: {len(dataset_list)}件")
    print(f"[DEBUG] 使用したdataset_json_path: {actual_dataset_json_path}")
    print(f"[DEBUG] 使用したinfo_json_path: {actual_info_json_path}")
    print(f"[DEBUG] dataset_json_pathの存在確認: {os.path.exists(actual_dataset_json_path) if actual_dataset_json_path else False}")
    if not dataset_list:
        print(f"[WARNING] データセットリストが空です。")
        print(f"[WARNING] actual_dataset_json_path={actual_dataset_json_path}")
        print(f"[WARNING] 元の引数dataset_json_path={dataset_json_path}")
        print(f"[WARNING] actual_info_json_path={actual_info_json_path}")
        print(f"[WARNING] 元の引数info_json_path={info_json_path}")
    display_list = [display for display, _, _, _ in dataset_list]
    # 先頭に空欄を追加
    combo.addItem("", None)
    for idx, (display, dataset_id, is_grant_missing, item) in enumerate(dataset_list):
        print(f"[DEBUG] addItem: idx={idx}, display={display}, dataset_id={dataset_id}")
        combo.addItem(display, dataset_id)
        # datasetのdictをUserRoleで保持
        try:
            combo.setItemData(idx+1, item, Qt.UserRole)  # +1: 空欄分ずらす
        except Exception as e:
            print(f"[ERROR] combo.setItemData失敗: idx={idx}, error={e}")
        if is_grant_missing:
            try:
                combo.setItemData(idx+1, Qt.red, Qt.ForegroundRole)
            except Exception as e:
                print(f"[ERROR] combo.setItemData(色)失敗: idx={idx}, error={e}")
    combo.setCurrentIndex(0)

    # QCompleterで補完・絞り込み
    completer = QCompleter(display_list, combo)
    completer.setCaseSensitivity(False)
    completer.setFilterMode(Qt.MatchContains)
    popup_view = completer.popup()
    popup_view.setMinimumHeight(240)
    popup_view.setMaximumHeight(240)
    combo.setCompleter(completer)

    # ラベルとドロップダウンを縦に並べて返す（パスも追加）
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(info_label)
    layout.addWidget(path_label)
    layout.addWidget(combo)
    container.setLayout(layout)
    # combo自体にも参照を持たせておく（テストや外部取得用）
    container.dataset_dropdown = combo
    return container
import os
import sys
import json
from PyQt5.QtWidgets import QComboBox

def load_dataset_list(json_path):
    """
    dataset.json からデータセット名とIDのリストを取得
    """
    if not os.path.exists(json_path):
        return []
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 例: [{"id": ..., "attributes": {"name": ...}}, ...]
    if isinstance(data, dict) and 'data' in data:
        items = data['data']
    elif isinstance(data, list):
        items = data
    else:
        items = []
    result = []
    for item in items:
        if isinstance(item, dict):
            dataset_id = item.get('id')
            attr = item.get('attributes', {})
            name = attr.get('name', dataset_id)
            grant_number = attr.get('grantNumber', '')
            display = f"{grant_number} {name}".strip() if grant_number else name
    # --- バイナリ実行時のパス解決 ---
    def resolve_data_path(rel_path):
        # バイナリ: 実行ファイルのディレクトリ基準
        # シェル: このpyファイルの位置基準
        # パス管理システムを使用（CWD非依存）
        from config.common import get_base_dir
        return os.path.join(get_base_dir(), rel_path)

    # dataset.json
    if dataset_json_path:
        # dataset_json_pathが絶対パスでなければ、パス管理システムで解決
        if not os.path.isabs(dataset_json_path):
            dataset_json_path = resolve_data_path(dataset_json_path)
        if os.path.exists(dataset_json_path):
            try:
                with open(dataset_json_path, 'r', encoding='utf-8') as f:
                    dataset_data = json.load(f)
                if isinstance(dataset_data, dict) and 'data' in dataset_data:
                    dataset_count = len(dataset_data['data'])
                elif isinstance(dataset_data, list):
                    dataset_count = len(dataset_data)
            except Exception:
                pass
    # self.json
    self_json_path = os.path.join(os.path.dirname(dataset_json_path), 'self.json')
    if not os.path.isabs(self_json_path):
        self_json_path = resolve_data_path(self_json_path)
    if os.path.exists(self_json_path):
        try:
            with open(self_json_path, 'r', encoding='utf-8') as f:
                self_data = json.load(f)
            if isinstance(self_data, dict):
                self_id = self_data.get('data', {}).get('id')
        except Exception:
            pass
