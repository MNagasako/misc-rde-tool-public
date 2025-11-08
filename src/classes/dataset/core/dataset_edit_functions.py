"""
データセット編集用の関数群
"""
import json
import os
from qt_compat.widgets import QMessageBox, QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
from qt_compat.core import QDate, QTimer, Qt
from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
from core.bearer_token_manager import BearerTokenManager


def create_dataset_update_payload(selected_dataset, edit_dataset_name_edit, edit_grant_number_combo, 
                                edit_description_edit, edit_embargo_edit, edit_contact_edit,
                                edit_taxonomy_edit, edit_related_links_edit, edit_tags_edit,
                                edit_citation_format_edit, edit_license_combo, edit_data_listing_gallery_radio, edit_data_listing_tree_radio, 
                                selected_datasets_list, edit_anonymize_checkbox, edit_data_entry_prohibited_checkbox, 
                                edit_data_entry_delete_prohibited_checkbox, edit_share_core_scope_checkbox):
    """データセット更新用のペイロードを作成"""
    original_dataset_id = selected_dataset.get("id")  # 元のデータセットIDを明確に保存
    original_attrs = selected_dataset.get("attributes", {})
    original_relationships = selected_dataset.get("relationships", {})
    
    print(f"[DEBUG] 編集対象データセットID: {original_dataset_id}")
    print(f"[DEBUG] 編集対象データセット名: {original_attrs.get('name', '不明')}")
    
    # フォームから値を取得
    dataset_name = edit_dataset_name_edit.text().strip()
    
    # 課題番号の取得（コンボボックスから）
    grant_number = ""
    if edit_grant_number_combo.currentData():
        grant_number = edit_grant_number_combo.currentData()
    else:
        grant_number = edit_grant_number_combo.lineEdit().text().strip()
    
    description = edit_description_edit.toPlainText().strip()
    contact = edit_contact_edit.text().strip()
    
    # 利用ライセンスの取得
    license_id = ""
    if edit_license_combo.currentData():
        license_id = edit_license_combo.currentData()
    else:
        license_text = edit_license_combo.lineEdit().text().strip()
        if license_text:
            # テキスト入力の場合、IDと名前が混在している可能性があるため、IDを抽出
            if " - " in license_text:
                license_id = license_text.split(" - ")[0]
            else:
                license_id = license_text
    
    # エンバーゴ期間終了日
    embargo_qdate = edit_embargo_edit.date()
    embargo_str = embargo_qdate.toString("yyyy-MM-dd")
    embargo_date_iso = embargo_str + "T03:00:00.000Z"
    
    # タクソノミーキー（スペース区切りで処理）
    taxonomy_text = edit_taxonomy_edit.text().strip()
    taxonomy_keys = [key.strip() for key in taxonomy_text.split() if key.strip()] if taxonomy_text else []
    
    # 関連情報（新しい書式に対応）
    related_links_text = edit_related_links_edit.toPlainText().strip()
    related_links = []
    print(f"[DEBUG] 関連情報テキスト: '{related_links_text}'")
    
    if related_links_text:
        # コンマ区切りで分割
        items = related_links_text.split(',')
        for line_num, item in enumerate(items, 1):
            item = item.strip()
            if not item:  # 空項目はスキップ
                continue
            
            # TITLE:URL 形式を解析
            if ':' in item:
                try:
                    title, url = item.split(':', 1)
                    title = title.strip()
                    url = url.strip()
                    
                    if title and url:
                        link_obj = {
                            "title": title,
                            "url": url
                        }
                        related_links.append(link_obj)
                        print(f"[DEBUG] 関連情報追加 (項目{line_num}): {link_obj}")
                    else:
                        print(f"[WARNING] 項目{line_num}: タイトルまたはURLが空です - スキップ")
                except Exception as e:
                    print(f"[WARNING] 項目{line_num}: 解析エラー - スキップ ('{item}') - {e}")
            else:
                print(f"[WARNING] 項目{line_num}: 不正な書式 - スキップ ('{item}')")
    
    # TAGフィールド（テキストボックスに変更）
    tags_text = edit_tags_edit.text().strip()
    tags = []
    print(f"[DEBUG] TAGテキスト: '{tags_text}'")
    
    if tags_text:
        tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
        print(f"[DEBUG] 解析されたTAG: {tags}")
    
    # データセット引用の書式
    citation_format = edit_citation_format_edit.toPlainText().strip()
    print(f"[DEBUG] 引用書式: '{citation_format}'")
    
    print(f"[DEBUG] 最終的な関連情報リスト: {related_links}")
    print(f"[DEBUG] 最終的なTAGリスト: {tags}")
    print(f"[DEBUG] 最終的な引用書式: '{citation_format}'")
    
    # 関連データセット
    related_datasets = []
    for i in range(selected_datasets_list.count()):
        item = selected_datasets_list.item(i)
        related_dataset_id = item.data(Qt.UserRole)  # 変数名を変更して衝突を回避
        if related_dataset_id:
            related_datasets.append({
                "type": "dataset",
                "id": related_dataset_id
            })
    print(f"[DEBUG] 関連データセット: {len(related_datasets)}件")
    for idx, rel_ds in enumerate(related_datasets):
        print(f"[DEBUG] 関連データセット{idx+1}: ID={rel_ds['id']}")
        # 自分自身をチェック
        if rel_ds['id'] == original_dataset_id:
            print(f"[WARNING] 自分自身が関連データセットに含まれています: {rel_ds['id']}")
    
    # メインデータセットIDチェック
    print(f"[DEBUG] メインデータセットID: {original_dataset_id}")
    print(f"[DEBUG] メインデータセット名: {dataset_name}")
    
    # チェックボックス
    is_anonymized = edit_anonymize_checkbox.isChecked()
    is_data_entry_prohibited = edit_data_entry_prohibited_checkbox.isChecked()
    is_data_entry_delete_prohibited = edit_data_entry_delete_prohibited_checkbox.isChecked()
    share_core_scope = edit_share_core_scope_checkbox.isChecked()
    
    # データ一覧表示タイプ（ラジオボタンから取得）
    if edit_data_listing_tree_radio.isChecked():
        data_listing_type = "TREE"
    else:
        data_listing_type = "GALLERY"  # デフォルト
    print(f"[DEBUG] データ一覧表示タイプ: {data_listing_type}")
    
    # データ登録及び削除を禁止するオプション
    print(f"[DEBUG] データ登録及び削除を禁止する: {is_data_entry_delete_prohibited}")
    
    # 共有ポリシー（既存のものを保持しつつ、RDE全体共有のみ更新）
    sharing_policies = original_attrs.get("sharingPolicies", []).copy()
    
    # デフォルトの共有ポリシー（データセット開設機能と同じ）
    default_policies = [
        {
            "scopeId": "4df8da18-a586-4a0d-81cb-ff6c6f52e70f",
            "permissionToView": True,
            "permissionToDownload": True
        },
        {
            "scopeId": "22aec474-bbf2-4826-bf63-60c82d75df41",
            "permissionToView": share_core_scope,
            "permissionToDownload": True
        }
    ]
    
    # 既存のポリシーを更新または新規追加
    for new_policy in default_policies:
        scope_id = new_policy["scopeId"]
        found = False
        for i, existing_policy in enumerate(sharing_policies):
            if existing_policy.get("scopeId") == scope_id:
                sharing_policies[i] = new_policy
                found = True
                break
        if not found:
            sharing_policies.append(new_policy)
    
    # リレーションシップを明示的に構築（成功時のペイロード構造に合わせる）
    relationships = {
        "relatedDatasets": {
            "data": related_datasets
        }
    }
    
    # 既存の重要なリレーションシップを保持
    important_relationships = [
        "applicant", "dataOwners", "instruments", 
        "manager", "template", "group"
    ]
    
    for rel_name in important_relationships:
        if rel_name in original_relationships:
            relationships[rel_name] = original_relationships[rel_name]
            print(f"[DEBUG] リレーションシップ保持: {rel_name}")
    
    # ライセンス情報をリレーションシップに追加（成功時のペイロード構造に合わせる）
    if license_id and license_id.strip():
        relationships["license"] = {
            "data": {
                "type": "license",
                "id": license_id
            }
        }
        print(f"[DEBUG] ライセンスリレーションシップ追加: {license_id}")
    else:
        # ライセンスが選択されていない場合は、dataをnullに設定
        relationships["license"] = {
            "data": None
        }
        print(f"[DEBUG] ライセンス未選択 - data: null で設定")
    
    # ペイロード作成
    payload = {
        "data": {
            "type": "dataset",
            "id": original_dataset_id,  # 元のデータセットIDを使用
            "attributes": {
                "grantNumber": grant_number,
                "name": dataset_name,
                "description": description,
                "relatedLinks": related_links,
                "tags": tags,  # TAGフィールドを追加
                "citationFormat": citation_format,  # 引用書式を追加
                "contact": contact,
                "taxonomyKeys": taxonomy_keys,
                "dataListingType": data_listing_type,  # データ一覧表示タイプを設定
                "isDataEntryProhibited": is_data_entry_delete_prohibited,  # 新しいチェックボックスの値を使用
                "embargoDate": embargo_date_iso,
                "sharingPolicies": sharing_policies,
                "isAnonymized": is_anonymized
            },
            "relationships": relationships
        }
    }
    
    # ペイロードの詳細デバッグ情報
    print(f"[DEBUG] === ペイロード最終確認 ===")
    print(f"[DEBUG] データセットID: {payload['data']['id']}")
    print(f"[DEBUG] データセット名: {payload['data']['attributes']['name']}")
    print(f"[DEBUG] 関連データセット数: {len(payload['data']['relationships']['relatedDatasets']['data'])}")
    for idx, rel_ds in enumerate(payload['data']['relationships']['relatedDatasets']['data']):
        print(f"[DEBUG] 関連データセット{idx+1}: {rel_ds['id']}")
    print(f"[DEBUG] === ペイロード確認終了 ===")
    
    return payload


def send_dataset_update_request(widget, parent, selected_dataset,
                               edit_dataset_name_edit, edit_grant_number_combo, edit_description_edit,
                               edit_embargo_edit, edit_contact_edit, edit_taxonomy_edit,
                               edit_related_links_edit, edit_tags_edit, edit_citation_format_edit, edit_license_combo,
                               edit_data_listing_gallery_radio, edit_data_listing_tree_radio, selected_datasets_list, 
                               edit_anonymize_checkbox, edit_data_entry_prohibited_checkbox, 
                               edit_data_entry_delete_prohibited_checkbox, edit_share_core_scope_checkbox, ui_refresh_callback=None):
    """データセット更新リクエストを送信"""
    
    # Bearer Token統一管理システムで取得
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
    if not bearer_token:
        QMessageBox.warning(widget, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
        return
    
    # ペイロード作成
    payload = create_dataset_update_payload(
        selected_dataset, edit_dataset_name_edit, edit_grant_number_combo,
        edit_description_edit, edit_embargo_edit, edit_contact_edit,
        edit_taxonomy_edit, edit_related_links_edit, edit_tags_edit,
        edit_citation_format_edit, edit_license_combo, edit_data_listing_gallery_radio, edit_data_listing_tree_radio, 
        selected_datasets_list, edit_anonymize_checkbox, edit_data_entry_prohibited_checkbox, 
        edit_data_entry_delete_prohibited_checkbox, edit_share_core_scope_checkbox
    )
    
    dataset_id = selected_dataset.get("id")
    dataset_name = edit_dataset_name_edit.text().strip()
    api_url = f"https://rde-api.nims.go.jp/datasets/{dataset_id}"
    
    # ヘッダー
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
        "sec-ch-ua-platform": '"Windows"'
    }
    
    # 確認ダイアログ
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    attr = payload['data']['attributes']
    
    # ライセンス情報をリレーションシップから取得
    license_info = "無し"
    relationships_data = payload['data'].get('relationships', {})
    if 'license' in relationships_data:
        license_data = relationships_data['license'].get('data')
        if license_data is not None:
            license_info = license_data.get('id', '無し')
        else:
            license_info = "無し"
    
    simple_text = (
        f"本当にデータセットを更新しますか？\n\n"
        f"データセット名: {attr.get('name')}\n"
        f"課題番号: {attr.get('grantNumber')}\n"
        f"説明: {attr.get('description')}\n"
        f"関連情報: {len(attr.get('relatedLinks', []))}件\n"
        f"TAG: {', '.join(attr.get('tags', []))}\n"
        f"引用書式: {attr.get('citationFormat', '未設定')}\n"
        f"利用ライセンス: {license_info}\n"
        f"データ一覧表示タイプ: {attr.get('dataListingType', 'GALLERY')}\n"
        f"エンバーゴ期間終了日: {attr.get('embargoDate')}\n"
        f"匿名化: {attr.get('isAnonymized')}\n"
        f"データ登録・削除禁止: {attr.get('isDataEntryProhibited')}\n"
        f"\nこの操作はARIMデータポータルのデータセット情報を更新します。"
    )
    
    msg_box = QMessageBox(widget)
    msg_box.setWindowTitle("データセット更新の確認")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText(simple_text)
    yes_btn = msg_box.addButton(QMessageBox.Yes)
    no_btn = msg_box.addButton(QMessageBox.No)
    detail_btn = QPushButton("詳細表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(no_btn)
    msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")
    
    def show_detail():
        dlg = QDialog(widget)
        dlg.setWindowTitle("Payload 全文表示")
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit(dlg)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(payload_str)
        text_edit.setMinimumSize(600, 400)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec()
    
    detail_btn.clicked.connect(show_detail)
    
    reply = msg_box.exec()
    if msg_box.clickedButton() == yes_btn:
        # API送信
        from classes.utils.api_request_helper import api_request  # セッション管理ベースのプロキシ対応
        try:
            # デバッグ出力
            print(f"[DEBUG] API URL: {api_url}")
            print(f"[DEBUG] Payload ID: {payload['data']['id']}")
            print(f"[DEBUG] Dataset ID from selected_dataset: {dataset_id}")
            print(f"[DEBUG] ID 一致確認: {payload['data']['id'] == dataset_id}")
            print(f"[DEBUG] HTTPメソッド: PATCH")
            
            # ペイロードの主要部分をログ出力
            attrs = payload['data']['attributes']
            rels = payload['data']['relationships']
            print(f"[DEBUG] ペイロード主要情報:")
            print(f"  - データセット名: {attrs.get('name')}")
            print(f"  - 課題番号: {attrs.get('grantNumber')}")
            print(f"  - 関連リンク数: {len(attrs.get('relatedLinks', []))}")
            print(f"  - 関連データセット数: {len(rels.get('relatedDatasets', {}).get('data', []))}")
            print(f"  - リレーションシップ: {list(rels.keys())}")
            
            # リレーションシップの詳細
            for rel_name, rel_data in rels.items():
                if rel_name == "relatedDatasets":
                    rel_count = len(rel_data.get('data', []))
                    print(f"    * {rel_name}: {rel_count}件")
                    for i, ds in enumerate(rel_data.get('data', [])):
                        print(f"      - [{i+1}] {ds.get('type')}: {ds.get('id')}")
                else:
                    print(f"    * {rel_name}: {type(rel_data)}")
            
            response = api_request('PATCH', api_url, headers=headers, json_data=payload, timeout=15)
            if response.status_code in (200, 201):
                # 成功時は簡潔なメッセージと詳細表示ボタン
                show_response_dialog(widget, "更新成功", f"データセット[{dataset_name}]の更新に成功しました。", response.text)
                
                # 成功時にdataset.jsonを自動再取得
                try:
                    from qt_compat.core import QTimer
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
                                progress_dialog = show_progress_dialog(widget, "データセット一覧自動更新", worker)
                                
                        except Exception as e:
                            print(f"[ERROR] データセット一覧自動更新でエラー: {e}")
                    
                    # 少し遅延してから自動更新実行（安全性向上のため遅延を増加）
                    QTimer.singleShot(2000, auto_refresh)  # 1秒 → 2秒に変更
                    
                    # UIリフレッシュコールバックを呼び出し（dataset.json更新後）
                    if ui_refresh_callback:
                        QTimer.singleShot(4000, ui_refresh_callback)  # 2秒 → 4秒に変更
                    
                    # グローバル通知を発行（他のタブも更新）
                    def notify_global_refresh():
                        try:
                            notifier = get_dataset_refresh_notifier()
                            notifier.notify_refresh()
                        except Exception as e:
                            print(f"[ERROR] グローバルリフレッシュ通知エラー: {e}")
                    
                    QTimer.singleShot(5000, notify_global_refresh)  # 3秒 → 5秒に変更
                    
                except Exception as e:
                    print(f"[WARNING] データセット一覧自動更新の設定に失敗: {e}")
                    # 自動更新が失敗してもUIリフレッシュは実行
                    if ui_refresh_callback:
                        QTimer.singleShot(1000, ui_refresh_callback)
            else:
                # 失敗時も詳細表示ボタン付きダイアログ
                error_message = f"Status: {response.status_code}"
                show_response_dialog(widget, "更新失敗", f"データセット[{dataset_name}]の更新に失敗しました。", f"{error_message}\n\n{response.text}")
        except Exception as e:
            QMessageBox.warning(widget, "APIエラー", f"API送信中にエラーが発生しました: {e}")
    else:
        print("[INFO] データセット更新処理はユーザーによりキャンセルされました。")


def show_response_dialog(parent, title, message, response_text):
    """
    レスポンス表示用の詳細ダイアログ（成功/失敗共通）
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    if "成功" in title:
        msg_box.setIcon(QMessageBox.Information)
    else:
        msg_box.setIcon(QMessageBox.Warning)
    msg_box.setText(message)
    
    # ボタン設定
    ok_btn = msg_box.addButton(QMessageBox.Ok)
    detail_btn = QPushButton("詳細表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(ok_btn)
    
    def show_response_detail():
        dlg = QDialog(parent)
        dlg.setWindowTitle(f"{title} - レスポンス詳細")
        dlg.setModal(True)
        dlg.resize(800, 600)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # タイトルラベル
        title_label = QLabel(f"{title} - レスポンス詳細")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1976d2; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # レスポンステキストエリア（スクロール対応）
        text_area = QTextEdit()
        
        # JSONかプレーンテキストかを判定して表示
        try:
            import json as json_lib
            parsed_json = json_lib.loads(response_text)
            formatted_text = json_lib.dumps(parsed_json, ensure_ascii=False, indent=2)
            text_area.setPlainText(formatted_text)
        except:
            text_area.setPlainText(response_text)
        
        text_area.setReadOnly(True)
        
        # フォント設定（等幅フォント）
        from qt_compat.gui import QFont
        font = QFont("Consolas", 10)
        text_area.setFont(font)
        
        # スタイル設定
        text_area.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px;
                background-color: white;
                line-height: 1.4;
            }
        """)
        
        layout.addWidget(text_area)
        
        # ボタンレイアウト
        from qt_compat.widgets import QHBoxLayout
        button_layout = QHBoxLayout()
        
        # 全選択ボタン
        select_all_btn = QPushButton("全選択 (Ctrl+A)")
        select_all_btn.setStyleSheet("background-color: #4caf50; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        select_all_btn.clicked.connect(text_area.selectAll)
        button_layout.addWidget(select_all_btn)
        
        # コピーボタン
        copy_btn = QPushButton("コピー (Ctrl+C)")
        copy_btn.setStyleSheet("background-color: #2196f3; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        
        def copy_text():
            from qt_compat.widgets import QApplication
            cursor = text_area.textCursor()
            if cursor.hasSelection():
                selected_text = cursor.selectedText()
                QApplication.clipboard().setText(selected_text)
            else:
                plain_text = text_area.toPlainText()
                QApplication.clipboard().setText(plain_text)
        
        copy_btn.clicked.connect(copy_text)
        button_layout.addWidget(copy_btn)
        
        button_layout.addStretch()
        
        # 閉じるボタン
        close_btn = QPushButton("閉じる (Esc)")
        close_btn.setStyleSheet("background-color: #757575; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        close_btn.clicked.connect(dlg.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        dlg.setLayout(layout)
        
        # キーボードショートカット設定
        from qt_compat.widgets import QShortcut
        from qt_compat.gui import QKeySequence
        from qt_compat.core import Qt
        
        # Ctrl+A で全選択
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, dlg)
        select_all_shortcut.activated.connect(text_area.selectAll)
        
        # Ctrl+C でコピー
        copy_shortcut = QShortcut(QKeySequence.Copy, dlg)
        copy_shortcut.activated.connect(copy_text)
        
        # Escape で閉じる
        escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), dlg)
        escape_shortcut.activated.connect(dlg.close)
        
        dlg.exec()
    
    detail_btn.clicked.connect(show_response_detail)
    msg_box.exec()
