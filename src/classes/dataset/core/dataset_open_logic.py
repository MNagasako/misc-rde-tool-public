
from PyQt5.QtWidgets import QMessageBox
import os
import json
from PyQt5.QtWidgets import QComboBox, QLabel, QVBoxLayout, QHBoxLayout, QWidget
# from classes.data.logic.bearer_token_util import load_bearer_token_from_file  # TODO: 新構造で再実装
from classes.utils.api_request_helper import api_request  # refactored to use api_request_helper


def filter_groups_by_role(groups, filter_type="member", user_id=None):
    """グループを役割でフィルタリング"""
    filtered_groups = []
    for group in groups:
        roles = group.get("attributes", {}).get("roles", [])
        user_role = None
        
        # ユーザーの役割を取得（user_idが指定されている場合）
        if user_id:
            for role in roles:
                if role.get("userId") == user_id:
                    user_role = role.get("role")
                    break
        
        # フィルタ条件に応じて判定
        if filter_type == "none":  # フィルタなし
            filtered_groups.append(group)
        elif filter_type == "member":  # デフォルト：何らかの役割を持つ
            if user_role:
                filtered_groups.append(group)
        elif filter_type == "owner":  # OWNER のみ
            if user_role == "OWNER":
                filtered_groups.append(group)
        elif filter_type == "assistant":  # ASSISTANT のみ
            if user_role == "ASSISTANT":
                filtered_groups.append(group)
        elif filter_type == "owner_assistant":  # OWNER または ASSISTANT
            if user_role in ["OWNER", "ASSISTANT"]:
                filtered_groups.append(group)
        elif filter_type == "all_roles":  # OWNER、ASSISTANT、MEMBER、AGENT、VIEWER
            if user_role in ["OWNER", "ASSISTANT", "MEMBER", "AGENT", "VIEWER"]:
                filtered_groups.append(group)
    
    return filtered_groups


# 事前に選択されたグループ情報を引数で受け取る形に変更
def run_dataset_open_logic(parent=None, bearer_token=None, group_info=None, dataset_name=None, embargo_date_str=None, template_id=None, dataset_type=None, share_core_scope=False, anonymize=False):
    print(f"[DEBUG] run_dataset_open_logic: dataset_name={dataset_name}, embargo_date_str={embargo_date_str}, template_id={template_id}, dataset_type={dataset_type}, bearer_token={bearer_token}, group_info={group_info}")
    print(f"[DEBUG] share_core_scope={share_core_scope}, anonymize={anonymize}")
    # bearer_tokenが未指定なら親からの取得を試行
    if not bearer_token and parent and hasattr(parent, 'bearer_token'):
        bearer_token = parent.bearer_token
        print(f"[DEBUG] bearer_token loaded from parent: {bearer_token}")
    if group_info is None:
        QMessageBox.warning(parent, "グループ情報エラー", "グループが選択されていません。")
        return
    group_id = group_info.get("id")
    group_attr = group_info.get("attributes", {})
    group_name = group_attr.get("name", "")
    group_desc = group_attr.get("description", "")
    subjects = group_attr.get("subjects", [])
    # grantNumberはgroup_info直下にあればそれを優先、なければattributes.subjects[0].grantNumber
    grant_number = group_info.get("grantNumber") or (subjects[0].get("grantNumber") if subjects else "")
    # OWNERユーザーID取得
    owner_id = None
    for role in group_attr.get("roles", []):
        if role.get("role") == "OWNER":
            owner_id = role.get("userId")
            break
    if not (group_id and owner_id and grant_number):
        QMessageBox.warning(parent, "グループ情報エラー", "グループID/OWNER/課題番号が取得できませんでした。")
        return

    # データセット名
    name = dataset_name if dataset_name else group_name
    # embargoDate
    embargo_date = embargo_date_str if embargo_date_str else "2026-03-31"
    embargo_date_iso = embargo_date + "T03:00:00.000Z"
    # テンプレートIDとタイプ
    template_id = template_id or "ARIM-R6_TU-504_TEM-STEM_20241121"
    dataset_type = dataset_type or "ANALYSIS"

    # payload生成
    payload = {
        "data": {
            "type": "dataset",
            "attributes": {
                "datasetType": dataset_type,
                "name": name,
                "grantNumber": grant_number,
                "embargoDate": embargo_date_iso,
                "dataListingType": "GALLERY",
                "sharingPolicies": [
                    {"scopeId": "4df8da18-a586-4a0d-81cb-ff6c6f52e70f", "permissionToView": True, "permissionToDownload": False},
                    {"scopeId": "22aec474-bbf2-4826-bf63-60c82d75df41", "permissionToView": share_core_scope, "permissionToDownload": False}
                ],
                "isAnonymized": anonymize
            },
            "relationships": {
                "group": {"data": {"type": "group", "id": group_id}},
                "manager": {"data": {"type": "user", "id": owner_id}},
                "template": {"data": {"type": "datasetTemplate", "id": template_id}}
            }
        }
    }
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    print(f"[DEBUG] payload sharingPolicies: {payload['data']['attributes']['sharingPolicies']}")
    print(f"[DEBUG] payload isAnonymized: {payload['data']['attributes']['isAnonymized']}")

    # 簡易表示用テキスト
    attr = payload['data']['attributes']
    simple_text = (
        f"本当にデータセットを開設しますか？\n\n"
        f"データセット名: {attr.get('name')}\n"
        f"課題番号: {attr.get('grantNumber')}\n"
        f"データセットを匿名にする: {attr.get('isAnonymized')}\n"
        f"エンバーゴ期間終了日: {attr.get('embargoDate')}\n"
        f"共有範囲: {attr.get('sharingPolicies')}\n"
        f"\nこの操作はRDEに新規データセットを作成します。"
    )

    from PyQt5.QtWidgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QTextEdit
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("データセット開設の確認")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText(simple_text)
    yes_btn = msg_box.addButton(QMessageBox.Yes)
    no_btn = msg_box.addButton(QMessageBox.No)
    detail_btn = QPushButton("詳細表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(no_btn)
    msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")

    def show_detail():
        dlg = QDialog(parent)
        dlg.setWindowTitle("Payload 全文表示")
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit(dlg)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(payload_str)
        text_edit.setMinimumSize(600, 400)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec_()
    detail_btn.clicked.connect(show_detail)

    reply = msg_box.exec_()
    if msg_box.clickedButton() == yes_btn:
        success, result = create_dataset(bearer_token, payload=payload)
        if success:
            QMessageBox.information(parent, "データセット開設", "データセットの開設に成功しました。\nID: {}".format(result.get('data', {}).get('id', '不明') if isinstance(result, dict) else '不明'))
            
            # 成功時にdataset.jsonを自動再取得
            try:
                from PyQt5.QtCore import QTimer
                def auto_refresh():
                    try:
                        from classes.basic.core.basic_info_logic import auto_refresh_dataset_json
                        from classes.utils.progress_worker import SimpleProgressWorker
                        from classes.basic.ui.ui_basic_info import show_progress_dialog
                        
                        if bearer_token:
                            # プログレス表示付きで自動更新
                            worker = SimpleProgressWorker(
                                task_func=auto_refresh_dataset_json,
                                task_kwargs={'bearer_token': bearer_token},
                                task_name="データセット一覧自動更新"
                            )
                            
                            # プログレス表示
                            progress_dialog = show_progress_dialog(parent, "データセット一覧自動更新", worker)
                            
                    except Exception as e:
                        print(f"[ERROR] データセット一覧自動更新でエラー: {e}")
                
                # 少し遅延してから自動更新実行
                QTimer.singleShot(1000, auto_refresh)
                
            except Exception as e:
                print(f"[WARNING] データセット一覧自動更新の設定に失敗: {e}")
        else:
            QMessageBox.critical(parent, "データセット開設エラー", f"データセットの開設に失敗しました。\n{result}")
        update_dataset(bearer_token)
    else:
        print("[INFO] データセット開設処理はユーザーによりキャンセルされました。")

# グループ選択UIを事前に表示する関数
def create_group_select_widget(parent=None):
    from PyQt5.QtWidgets import QCheckBox
    # データ中核拠点広域シェア チェックボックス
    share_core_scope_checkbox = QCheckBox("データ中核拠点広域シェア（RDE全体での共有）を有効にする", parent)
    share_core_scope_checkbox.setChecked(False)
    # データセット匿名 チェックボックス
    anonymize_checkbox = QCheckBox("データセットを匿名にする", parent)
    anonymize_checkbox.setChecked(False)

    from PyQt5.QtWidgets import QWidget, QPushButton, QLineEdit, QDateEdit, QComboBox
    from PyQt5.QtCore import QDate, Qt
    import datetime
    from config.common import SUBGROUP_JSON_PATH, TEMPLATE_JSON_PATH, SELF_JSON_PATH, ORGANIZATION_JSON_PATH, INSTRUMENTS_JSON_PATH
    
    print(f"[DEBUG] データセット開設機能：パス確認完了")
    
    team_groups_raw = []
    try:
        # ログインユーザーID取得
        with open(SELF_JSON_PATH, encoding="utf-8") as f:
            self_data = json.load(f)
        user_id = self_data.get("data", {}).get("id", None)
        if not user_id:
            print("[ERROR] self.jsonからユーザーIDが取得できませんでした。")
        with open(SUBGROUP_JSON_PATH, encoding="utf-8") as f:
            sub_group_data = json.load(f)
        
        # 全てのTEAMグループを取得（フィルタ前）
        all_team_groups = []
        for item in sub_group_data.get("included", []):
            if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                all_team_groups.append(item)
        
        # デフォルトフィルタを適用
        team_groups_raw = filter_groups_by_role(all_team_groups, "owner_assistant", user_id)
    except Exception as e:
        print(f"[ERROR] subGroup.json/self.jsonの読み込み・フィルタに失敗: {e}")
        # ファイルが見つからない場合の詳細情報
        if "No such file or directory" in str(e) or "FileNotFoundError" in str(type(e).__name__):
            error_widget = QWidget(parent)
            error_layout = QVBoxLayout()
            error_layout.addWidget(QLabel("データセット開設機能が利用できません"))
            error_layout.addWidget(QLabel("必要なデータファイルが見つかりません。"))
            error_layout.addWidget(QLabel("先にデータ取得を実行してください。"))
            error_widget.setLayout(error_layout)
            return error_widget, [], None, None, None, None, None, []
    
    # フィルタ選択UI
    filter_combo = QComboBox(parent)
    #filter_combo.addItem("メンバー（何らかの役割を持つ）", "member")
    #filter_combo.addItem("フィルタなし（全てのグループ）", "none")
    filter_combo.addItem("管理者 または 管理者代理", "owner_assistant")
    filter_combo.addItem("管理者 のみ", "owner")
    filter_combo.addItem("管理者代理 のみ", "assistant")

    #filter_combo.addItem("管理者、管理者代理、メンバー、登録代行者、閲覧者", "all_roles")
    filter_combo.setCurrentIndex(0)  # デフォルト：メンバー
    
    # 初期グループリスト設定
    team_groups = team_groups_raw
    group_names = []
    for g in team_groups_raw:
        name = g.get('attributes', {}).get('name', '(no name)')
        subjects = g.get('attributes', {}).get('subjects', [])
        grant_count = len(subjects) if subjects else 0
        group_names.append(f"{name} ({grant_count}件の課題)")
    
    if not team_groups:
        error_widget = QWidget(parent)
        error_layout = QVBoxLayout()
        error_layout.addWidget(QLabel("利用可能なグループが見つかりません"))
        error_layout.addWidget(QLabel("サブグループ作成機能でグループを作成してください。"))
        error_widget.setLayout(error_layout)
        return error_widget, [], None, None, None, None, None, []
    
    from PyQt5.QtWidgets import QSizePolicy
    from PyQt5.QtWidgets import QCompleter
    
    # UIコンポーネントを先に定義（update_group_list関数で参照するため）
    combo = QComboBox(parent)
    combo.setMinimumWidth(200)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(12)
    combo.view().setMinimumHeight(240)
    combo.clear()
    
    # 課題番号選択欄を先に定義（update_group_list で参照するため）
    grant_combo = QComboBox(parent)
    grant_combo.setMinimumWidth(200)
    grant_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    grant_combo.setEditable(True)
    grant_combo.setInsertPolicy(QComboBox.NoInsert)
    grant_combo.setMaxVisibleItems(12)
    grant_combo.view().setMinimumHeight(240)
    grant_combo.clear()
    grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
    grant_combo.setEnabled(False)  # 初期状態では無効
    
    # グループ選択コンボボックス
    def update_group_list(filter_type="member"):
        """フィルタタイプに応じてグループリストを更新"""
        nonlocal team_groups, group_names, group_completer  # group_completer も追加
        
        filtered_groups = filter_groups_by_role(all_team_groups, filter_type, user_id)
        
        # グループ名リスト作成
        group_names_new = []
        for g in filtered_groups:
            name = g.get('attributes', {}).get('name', '(no name)')
            subjects = g.get('attributes', {}).get('subjects', [])
            grant_count = len(subjects) if subjects else 0
            group_names_new.append(f"{name} ({grant_count}件の課題)")
        
        # コンボボックス更新
        combo.clear()
        if group_names_new:
            combo.addItems(group_names_new)
            combo.setCurrentIndex(-1)  # 選択なし状態
            combo.lineEdit().setPlaceholderText("グループを選択してください")
            combo.setEnabled(True)
        else:
            combo.setEnabled(False)
            combo.lineEdit().setPlaceholderText("該当するグループがありません")
        
        # グループデータも更新
        team_groups = filtered_groups
        group_names = group_names_new
        
        # Completer も更新（重要！）
        try:
            group_completer.setModel(group_completer.model().__class__(group_names_new, group_completer))
            print(f"[DEBUG] Completer更新完了: {len(group_names_new)}件")
        except Exception as e:
            print(f"[WARNING] Completer更新に失敗: {e}")
        
        # 課題番号コンボボックスをクリア
        grant_combo.clear()
        grant_combo.setEnabled(False)
        grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
        
        return group_names_new
    
    # グループ選択コンボボックスの設定
    combo.lineEdit().setPlaceholderText("グループ名で検索")
    
    # Completer の初期化（先に行う）
    group_completer = QCompleter([], combo)  # 空リストで初期化
    group_completer.setCaseSensitivity(False)
    group_completer.setFilterMode(Qt.MatchContains)
    # 検索時の補完リスト（popup）の高さを12行分に制限
    popup_view = group_completer.popup()
    popup_view.setMinimumHeight(240)
    popup_view.setMaximumHeight(240)
    combo.setCompleter(group_completer)
    
    # 初期グループリスト設定
    update_group_list("owner_assistant")  # デフォルトフィルタで初期化（フィルタコンボの初期値に合わせる）
    
    # フィルタ変更時のイベントハンドラ
    def on_filter_changed():
        filter_type = filter_combo.currentData()
        print(f"[DEBUG] Filter changed to: {filter_type}")
        update_group_list(filter_type)  # update_group_list内でCompleterも更新される
        print(f"[DEBUG] Groups after filter: {len(team_groups)} groups")
        
    filter_combo.currentTextChanged.connect(on_filter_changed)
    
    # QComboBox自体のmousePressEventをラップして全リスト表示＋popup
    orig_mouse_press = combo.mousePressEvent
    def combo_mouse_press_event(event):
        print("[DEBUG] group combo (QComboBox) click: text=", combo.lineEdit().text())
        print("[DEBUG] group_names=", len(group_names))
        print("[DEBUG] combo.count before=", combo.count())
        if not combo.lineEdit().text():
            combo.clear()
            combo.addItems(group_names)
            print("[DEBUG] group combo: added all items")
        print("[DEBUG] combo.count after=", combo.count())
        combo.showPopup()
        orig_mouse_press(event)
    combo.mousePressEvent = combo_mouse_press_event

    # グループ選択時に課題番号リストを更新
    def on_group_changed():
        current_text = combo.lineEdit().text()
        print(f"[DEBUG] Group selection changed: {current_text}")
        
        # 課題番号コンボボックスをクリア
        grant_combo.clear()
        grant_combo.setEnabled(False)
        grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
        
        # 現在選択されているグループのインデックスを探す
        selected_group = None
        for i, name in enumerate(group_names):
            if name == current_text:
                selected_group = team_groups[i]
                break
        
        if selected_group:
            subjects = selected_group.get('attributes', {}).get('subjects', [])
            if subjects:
                grant_combo.setEnabled(True)
                grant_combo.lineEdit().setPlaceholderText("課題番号を選択")
                
                grant_items = []
                for subject in subjects:
                    grant_number = subject.get('grantNumber', '')
                    title = subject.get('title', '')
                    if grant_number:
                        display_text = f"{grant_number} - {title}" if title else grant_number
                        grant_items.append(display_text)
                        grant_combo.addItem(display_text, grant_number)
                
                if grant_items:
                    # 課題番号コンボボックス用のコンプリーター設定
                    grant_completer = QCompleter(grant_items, grant_combo)
                    grant_completer.setCaseSensitivity(False)
                    grant_completer.setFilterMode(Qt.MatchContains)
                    grant_popup_view = grant_completer.popup()
                    grant_popup_view.setMinimumHeight(240)
                    grant_popup_view.setMaximumHeight(240)
                    grant_combo.setCompleter(grant_completer)
                    
                    # 課題番号コンボボックスのクリックイベント
                    orig_grant_mouse_press = grant_combo.mousePressEvent
                    def grant_combo_mouse_press_event(event):
                        print("[DEBUG] grant combo click")
                        if not grant_combo.lineEdit().text():
                            grant_combo.clear()
                            for subject in subjects:
                                grant_number = subject.get('grantNumber', '')
                                title = subject.get('title', '')
                                if grant_number:
                                    display_text = f"{grant_number} - {title}" if title else grant_number
                                    grant_combo.addItem(display_text, grant_number)
                        grant_combo.showPopup()
                        orig_grant_mouse_press(event)
                    grant_combo.mousePressEvent = grant_combo_mouse_press_event
                    
                    # デフォルトで最初の課題番号を選択
                    if len(grant_items) == 1:
                        grant_combo.setCurrentIndex(0)
                    else:
                        grant_combo.setCurrentIndex(-1)
                        
                print(f"[DEBUG] Added {len(grant_items)} grant numbers to combo")
            else:
                grant_combo.lineEdit().setPlaceholderText("このグループには課題が登録されていません")
    
    # グループ選択の変更イベントを接続
    combo.lineEdit().textChanged.connect(on_group_changed)
    combo.currentTextChanged.connect(on_group_changed)

    # name入力欄
    name_edit = QLineEdit(parent)
    name_edit.setPlaceholderText("データセット名を入力")
    name_edit.setMinimumWidth(180)

    # embargoDate入力欄（翌年度末日をデフォルト）
    today = datetime.date.today()
    next_next_year = today.year + 2
    embargo_date = QDate(next_next_year, 3, 31)
    embargo_edit = QDateEdit(parent)
    embargo_edit.setDate(embargo_date)
    embargo_edit.setDisplayFormat("yyyy-MM-dd")
    embargo_edit.setCalendarPopup(True)
    embargo_edit.setMinimumWidth(120)

    # テンプレート選択欄（所属組織のinstrumentを使うテンプレートのみ抽出）
    template_list = []
    template_combo = QComboBox(parent)
    template_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    template_combo.setEditable(True)
    template_combo.setInsertPolicy(QComboBox.NoInsert)
    template_combo.setMaxVisibleItems(12)
    template_combo.view().setMinimumHeight(240)
    template_combo.clear()
    template_combo.lineEdit().setPlaceholderText("テンプレート名・装置名で検索")
    template_items = []
    # --- 所属組織名取得 ---
    org_name = None
    try:
        with open(SELF_JSON_PATH, encoding="utf-8") as f:
            self_data = json.load(f)
        org_name = self_data.get("data", {}).get("attributes", {}).get("organizationName")
    except Exception as e:
        print(f"[ERROR] self.jsonの読み込みに失敗: {e}")
    # --- 組織ID取得 ---
    org_id = None
    try:
        with open(ORGANIZATION_JSON_PATH, encoding="utf-8") as f:
            org_data = json.load(f)
        for org in org_data.get("data", []):
            if org.get("attributes", {}).get("nameJa") == org_name:
                org_id = org.get("id")
                break
    except Exception as e:
        print(f"[ERROR] organization.jsonの読み込みに失敗: {e}")
    # --- instrument IDリスト取得 ---
    instrument_ids = set()
    instrument_map = {}
    try:
        with open(INSTRUMENTS_JSON_PATH, encoding="utf-8") as f:
            instruments_data = json.load(f)
        for inst in instruments_data.get("data", []):
            inst_id = inst.get("id")
            attr = inst.get("attributes", {})
            name_ja = attr.get("nameJa", "")
            local_id = ""
            model_number = attr.get("modelNumber", "")
            for prog in attr.get("programs", []):
                if prog.get("localId"):
                    local_id = prog["localId"]
                    break
            instrument_map[inst_id] = {"nameJa": name_ja, "localId": local_id, "modelNumber": model_number, "organizationId": attr.get("organizationId")}
            if attr.get("organizationId") == org_id:
                instrument_ids.add(inst_id)
    except Exception as e:
        print(f"[ERROR] instruments.jsonの読み込みに失敗: {e}")
    # --- テンプレート抽出 ---
    try:
        with open(TEMPLATE_JSON_PATH, encoding="utf-8") as f:
            template_data = json.load(f)
        for item in template_data.get("data", []):
            tid = item.get("id", "")
            dtype = item.get("attributes", {}).get("datasetType", "")
            name_ja = item.get("attributes", {}).get("nameJa", tid)
            # instruments
            insts = item.get("relationships", {}).get("instruments", {}).get("data", [])
            inst_labels = []
            has_my_instrument = False
            for inst in insts:
                inst_id = inst.get("id")
                inst_info = instrument_map.get(inst_id)
                if inst_info:
                    if inst_id in instrument_ids:
                        has_my_instrument = True
                    label_parts = [inst_info['nameJa']]
                    if inst_info['localId']:
                        label_parts.append(f"[{inst_info['localId']}]")
                    if inst_info['modelNumber']:
                        label_parts.append(f"({inst_info['modelNumber']})")
                    inst_labels.append(" ".join(label_parts))
            if not has_my_instrument:
                continue  # 所属組織のinstrumentがなければ除外
            inst_label = ", ".join(inst_labels) if inst_labels else ""
            label = f"{name_ja} ({dtype})"
            if inst_label:
                label += f" | {inst_label}"
            template_list.append({"id": tid, "datasetType": dtype, "nameJa": name_ja, "instruments": inst_labels})
            template_items.append(label)
            template_combo.addItem(label, tid)
    except Exception as e:
        print(f"[ERROR] template.jsonの読み込みに失敗: {e}")
    template_combo.setMinimumWidth(260)
    template_completer = QCompleter(template_items, template_combo)
    template_completer.setCaseSensitivity(False)
    template_completer.setFilterMode(Qt.MatchContains)
    t_popup_view = template_completer.popup()
    t_popup_view.setMinimumHeight(240)
    t_popup_view.setMaximumHeight(240)
    template_combo.setCompleter(template_completer)
    template_combo.setCurrentIndex(-1)

    from PyQt5.QtWidgets import QFormLayout
    form_layout = QFormLayout()
    form_layout.setLabelAlignment(Qt.AlignRight)
    form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    # ラベルを太字に
    label_filter = QLabel("フィルタ:"); label_filter.setStyleSheet("font-weight: bold;")
    label_group = QLabel("グループ:"); label_group.setStyleSheet("font-weight: bold;")
    label_grant = QLabel("課題番号:"); label_grant.setStyleSheet("font-weight: bold;")
    label_name = QLabel("データセット名:"); label_name.setStyleSheet("font-weight: bold;")
    label_embargo = QLabel("エンバーゴ期間終了日:"); label_embargo.setStyleSheet("font-weight: bold;")
    label_template = QLabel("データセットテンプレート名:"); label_template.setStyleSheet("font-weight: bold;")
    form_layout.addRow(label_filter, filter_combo)
    form_layout.addRow(label_group, combo)
    form_layout.addRow(label_grant, grant_combo)
    form_layout.addRow(label_name, name_edit)
    form_layout.addRow(label_embargo, embargo_edit)
    form_layout.addRow(label_template, template_combo)
    form_layout.addRow(share_core_scope_checkbox)
    form_layout.addRow(anonymize_checkbox)
    # プレースホルダー色を緑系に
    combo.lineEdit().setStyleSheet("color: #228B22;")
    grant_combo.lineEdit().setStyleSheet("color: #228B22;")
    name_edit.setStyleSheet("color: #228B22;")
    embargo_edit.setStyleSheet("color: #228B22;")
    template_combo.lineEdit().setStyleSheet("color: #228B22;")
    open_btn = QPushButton("データセット開設", parent)
    open_btn.setStyleSheet("""
        QPushButton {
            background-color: #1976d2;
            color: white;
            font-weight: bold;
            font-size: 13px;
            border-radius: 6px;
            padding: 8px 20px;
        }
        QPushButton:hover {
            background-color: #1565c0;
        }
        QPushButton:pressed {
            background-color: #0d47a1;
        }
    """)
    form_layout.addRow(open_btn)
    container = QWidget(parent)
    container.setLayout(form_layout)

    def on_open():
        idx = combo.currentIndex()
        selected_group = None
        
        # グループ名から対応するグループを検索
        current_group_text = combo.lineEdit().text()
        for i, name in enumerate(group_names):
            if name == current_group_text:
                selected_group = team_groups[i]
                break
        
        if not selected_group:
            QMessageBox.warning(parent, "グループ未選択", "グループを選択してください。")
            return
        
        # 課題番号取得
        selected_grant_number = None
        grant_text = grant_combo.lineEdit().text()
        if grant_text and grant_combo.currentData():
            selected_grant_number = grant_combo.currentData()
        elif grant_text:
            # データが無い場合は、テキストから課題番号を抽出
            parts = grant_text.split(' - ')
            if parts:
                selected_grant_number = parts[0].strip()
        
        if not selected_grant_number:
            QMessageBox.warning(parent, "課題番号未選択", "課題番号を選択してください。")
            return
        
        # 選択されたグループに課題番号情報を追加
        group_info = dict(selected_group)
        group_info['grantNumber'] = selected_grant_number
        
        # 入力値取得
        dataset_name = name_edit.text().strip()
        embargo_qdate = embargo_edit.date()
        embargo_str = embargo_qdate.toString("yyyy-MM-dd")
        template_idx = template_combo.currentIndex()
        template_id = template_list[template_idx]["id"] if 0 <= template_idx < len(template_list) else ""
        dataset_type = template_list[template_idx]["datasetType"] if 0 <= template_idx < len(template_list) else "ANALYSIS"
        
        # 入力必須チェック
        if not group_info.get('attributes', {}).get('name'):
            QMessageBox.warning(parent, "入力エラー", "グループ名は必須です。")
            return
        if not selected_grant_number:
            QMessageBox.warning(parent, "入力エラー", "課題番号は必須です。")
            return
        if not dataset_name:
            QMessageBox.warning(parent, "入力エラー", "データセット名は必須です。")
            return
        if not embargo_str:
            QMessageBox.warning(parent, "入力エラー", "エンバーゴ期間終了日は必須です。")
            return
        if template_idx < 0 or not template_id:
            QMessageBox.warning(parent, "入力エラー", "テンプレートは必須です。")
            return
        
        # チェックボックスの値取得
        share_core_scope = share_core_scope_checkbox.isChecked()
        anonymize = anonymize_checkbox.isChecked()
        
        # bearer_tokenを親ウィジェットから取得
        bearer_token = None
        p = parent
        while p is not None:
            if hasattr(p, 'bearer_token'):
                bearer_token = getattr(p, 'bearer_token')
                break
            p = getattr(p, 'parent', None)
        
        print(f"[DEBUG] on_open: group={group_info.get('attributes', {}).get('name')}, grant_number={selected_grant_number}, dataset_name={dataset_name}, embargo_str={embargo_str}, template_id={template_id}, dataset_type={dataset_type}, bearer_token={bearer_token}, share_core_scope={share_core_scope}, anonymize={anonymize}")
        run_dataset_open_logic(parent, bearer_token, group_info, dataset_name, embargo_str, template_id, dataset_type, share_core_scope, anonymize)
    open_btn.clicked.connect(on_open)

    # サブグループ情報の更新機能を追加
    def refresh_subgroup_data():
        """サブグループ情報を再読み込みしてコンボボックスを更新"""
        try:
            # ウィジェットが破棄されていないかチェック
            if not combo or combo.parent() is None:
                print("[DEBUG] コンボボックスが破棄されているため更新をスキップ")
                return
                
            # subGroup.jsonから最新データを読み込み
            with open(SUBGROUP_JSON_PATH, encoding="utf-8") as f:
                sub_group_data = json.load(f)
            
            # 全てのTEAMグループを再取得
            new_all_team_groups = []
            for item in sub_group_data.get("included", []):
                if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                    new_all_team_groups.append(item)
            
            # グローバル変数を更新
            nonlocal all_team_groups, team_groups, group_names
            all_team_groups = new_all_team_groups
            
            # 現在のフィルタを適用して更新
            current_filter = filter_combo.currentData()
            update_group_list(current_filter or "owner_assistant")
            
            # Completer の更新 - これが重要！
            if group_completer and hasattr(group_completer, 'setModel'):
                group_completer.setModel(group_completer.model().__class__(group_names, group_completer))
            
            # コンボボックスの再構築（確実な更新のため）
            if combo and hasattr(combo, 'blockSignals'):
                combo.blockSignals(True)
                combo.clear()
                if group_names:
                    combo.addItems(group_names)
                    combo.setCurrentIndex(-1)  # 選択なし状態
                    combo.lineEdit().setPlaceholderText("グループを選択してください")
                    combo.setEnabled(True)
                else:
                    combo.setEnabled(False)
                    combo.lineEdit().setPlaceholderText("該当するグループがありません")
                combo.blockSignals(False)
                
                # UIの強制更新
                combo.update()
                combo.repaint()
            
            print(f"[INFO] サブグループ情報更新完了: {len(new_all_team_groups)}件のグループ, 表示: {len(group_names)}件")
            
        except Exception as e:
            print(f"[ERROR] サブグループ情報更新に失敗: {e}")
    
    # サブグループ更新通知システムに登録
    try:
        from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
        subgroup_notifier = get_subgroup_refresh_notifier()
        subgroup_notifier.register_callback(refresh_subgroup_data)
        print("[INFO] データセット開設タブ: サブグループ更新通知に登録完了")
        
        # ウィジェット破棄時の通知解除用
        def cleanup_callback():
            subgroup_notifier.unregister_callback(refresh_subgroup_data)
            print("[INFO] データセット開設タブ: サブグループ更新通知を解除")
        
        container._cleanup_subgroup_callback = cleanup_callback
        
    except Exception as e:
        print(f"[WARNING] サブグループ更新通知への登録に失敗: {e}")

    # 外部から呼び出し可能にする
    container._refresh_subgroup_data = refresh_subgroup_data

    return container, team_groups, combo, grant_combo, open_btn, name_edit, embargo_edit, template_combo, template_list, filter_combo

def create_dataset(bearer_token, payload, output_dir="output/rde/data"):
    """
    設備情報取得（ダミー）: 基本情報取得と同じAPI・保存処理
    payload引数で受け取った内容をそのまま送信
    """
    if not bearer_token:
        # TODO: 新構造ではbearer_tokenは呼び出し元から渡される想定
        print("[ERROR] Bearerトークンが指定されていません。")
        return
    url = "https://rde-api.nims.go.jp/datasets"

    if 'payload' in locals():
        pass  # payloadは引数で受け取る
    else:
        print("[ERROR] payloadが指定されていません。")
        return

    headers = {
        "Accept": "application/vnd.api+json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Authorization": f"Bearer {bearer_token}",
        "Connection": "keep-alive",
        "Content-Type": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    try:
        resp = api_request("POST", url, bearer_token=bearer_token, headers=headers, json_data=payload, timeout=15)  # refactored to use api_request_helper
        if resp is None:
            print("[ERROR] データセット開設API リクエスト失敗")
            return False, None
        resp.raise_for_status()
        data = resp.json()
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "create_dataset.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[INFO] 設備情報(create_dataset.json)の取得・保存に成功しました。")
        
        # データセット開設成功時に個別データセット情報を自動取得
        try:
            dataset_id = data.get("data", {}).get("id")
            if dataset_id:
                print(f"[INFO] データセット開設成功。個別データセット情報を自動取得中: {dataset_id}")
                from classes.basic.core.basic_info_logic import fetch_dataset_info_respectively_from_api
                fetch_dataset_info_respectively_from_api(bearer_token, dataset_id)
                print(f"[INFO] 個別データセット情報({dataset_id}.json)の自動取得完了")
            else:
                print("[WARNING] データセット開設レスポンスにIDが含まれていません")
        except Exception as e:
            print(f"[WARNING] 個別データセット情報の自動取得に失敗: {e}")
        
        return True, data
    except Exception as e:
        print(f"[ERROR] 設備情報の取得・保存に失敗しました: {e}")
        return False, str(e)


    

def update_dataset(bearer_token, output_dir="output/rde/data"):
    """
    設備情報取得（ダミー）: 基本情報取得と同じAPI・保存処理
    """
    if not bearer_token:
        print("[ERROR] Bearerトークンが取得できません。ログイン状態を確認してください。")
        return
    #url = "https://rde-api.nims.go.jp/datasetTemplates?programId=4bbf62be-f270-4a46-9682-38cd064607ba&teamId=22398c55-8620-430e-afa5-2405c57dd03c&sort=id&page[limit]=10000&page[offset]=0&include=instruments&fields[instrument]=nameJa%2CnameEn"
    url = "https://rde-api.nims.go.jp/datasets/5bfd6602-41c2-423a-8652-e9cbab71a172"

    return  # 一時的にAPI呼び出しを停止