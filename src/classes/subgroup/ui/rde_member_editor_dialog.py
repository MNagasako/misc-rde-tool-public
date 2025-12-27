"""
rde-member.txt編集ダイアログ

メンバーの追加・削除・編集をGUIで行えるダイアログウィジェット
"""

import os
import json
import logging
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QMessageBox,
    QHeaderView
)
from qt_compat.core import Qt
from config.common import INPUT_DIR, get_dynamic_file_path
from classes.theme import get_color, get_qcolor, ThemeKey

# ロガー設定
logger = logging.getLogger(__name__)


class RdeMemberEditorDialog(QDialog):
    """rde-member.txt編集ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("カスタムメンバー編集 (rde-member.txt)")
        self.setMinimumSize(800, 500)
        
        self.member_path = os.path.join(INPUT_DIR, "rde-member.txt")
        self.members = []  # {"email": str, "role": str, "canCreateDatasets": bool, "canEditMembers": bool}
        self.email_to_user_map = {}  # メールアドレス→ユーザー情報マッピング
        
        self.setup_ui()
        self.load_members()
        self.load_email_to_user_map()
    
    def setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout()
        
        # 説明ラベル
        info_label = QLabel(
            "rde-member.txtのメンバーをカスタマイズします。\n"
            "メールアドレスはDICEアカウントとして登録されている必要があります。"
        )
        info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)}; padding: 5px;")
        layout.addWidget(info_label)
        
        # テーブル作成
        self.table = QTableWidget()
        self.table.setColumnCount(6)  # 氏名、メール、初期ロール、作成権限、編集権限、削除
        self.table.setHorizontalHeaderLabels(["氏名", "メールアドレス", "初期ロール", "データセット作成", "メンバー編集", ""]) 
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        # スタイルは_apply_table_style()で一元管理
        self._apply_table_style()
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)          # 氏名
        header.setSectionResizeMode(1, QHeaderView.Stretch)          # メール
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # 初期ロール
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # 作成権限
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # 編集権限
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents) # 削除
        
        layout.addWidget(self.table)
        
        # 追加UI
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("新規追加:"))
        
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("メールアドレス")
        add_layout.addWidget(self.email_input)
        
        self.role_combo = QComboBox()
        self.role_combo.addItems(["ASSISTANT", "OWNER"])
        add_layout.addWidget(self.role_combo)
        
        self.can_create_cb = QCheckBox("データセット作成")
        self.can_create_cb.setChecked(True)
        add_layout.addWidget(self.can_create_cb)
        
        self.can_edit_cb = QCheckBox("メンバー編集")
        self.can_edit_cb.setChecked(True)
        add_layout.addWidget(self.can_edit_cb)
        
        add_button = QPushButton("追加")
        add_button.clicked.connect(self.add_member)
        add_layout.addWidget(add_button)

        # 全行再フェッチ（手動更新）ボタン
        refresh_button = QPushButton("手動更新")
        refresh_button.setToolTip("氏名/メールをAPIで再取得してキャッシュ更新")
        refresh_button.clicked.connect(self.refresh_all_members)
        add_layout.addWidget(refresh_button)
        
        layout.addLayout(add_layout)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        self.save_button = QPushButton("保存")
        self.save_button.setStyleSheet(
            f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; "
            "font-weight: bold; padding: 8px;"
        )
        save_button = self.save_button
        save_button.clicked.connect(self.save_members)
        button_layout.addWidget(save_button)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_theme)

    def refresh_all_members(self):
        """rde-member.txtの全メンバーについてAPIで氏名/メールを再取得しキャッシュ更新"""
        try:
            from core.bearer_token_manager import BearerTokenManager
            from ..core.subgroup_api_helper import fetch_user_details_by_id
            from ..core.user_cache_manager import cache_user_from_api, get_cached_user
            import urllib.parse
            from net.http_helpers import proxy_get
            
            bearer_token = BearerTokenManager.get_valid_token()
            if not bearer_token:
                QMessageBox.warning(self, "認証エラー", "Bearer tokenが取得できません。ログインを確認してください。")
                return
            
            updated = 0
            for idx, member in enumerate(self.members):
                user_id = member.get('user_id', '')
                email = member.get('email', '').strip()
                user_name = member.get('userName', '').strip()
                
                # 氏名が空の場合はメールアドレスでAPI検索（新規追加と同じロジック）
                if not user_name and email:
                    try:
                        logger.info(f"[MemberEditor.refresh] 氏名空→メール検索: row={idx} MAIL={email}")
                        encoded_email = urllib.parse.quote_plus(email)
                        filter_param = urllib.parse.quote('filter[emailAddress]', safe='')
                        url = f"https://rde-user-api.nims.go.jp/users?{filter_param}={encoded_email}"
                        
                        headers = {
                            'Authorization': f'Bearer {bearer_token}',
                            'Accept': 'application/vnd.api+json',
                            'Content-Type': 'application/json'
                        }
                        
                        response = proxy_get(url, headers=headers)
                        response.raise_for_status()
                        
                        data = response.json()
                        users = data.get('data', [])
                        
                        if users:
                            user_data = users[0]
                            fetched_id = user_data.get('id', '')
                            fetched_name = user_data.get('attributes', {}).get('userName', '')
                            fetched_email = user_data.get('attributes', {}).get('emailAddress', email)
                            
                            # メンバー情報更新
                            if fetched_name:
                                member['userName'] = fetched_name
                                user_name = fetched_name
                            if fetched_id:
                                member['user_id'] = fetched_id
                                user_id = fetched_id
                            if fetched_email:
                                member['email'] = fetched_email
                            
                            # キャッシュに保存
                            cache_info = {
                                'userName': fetched_name,
                                'emailAddress': fetched_email,
                                'organizationName': user_data.get('attributes', {}).get('organizationName', ''),
                                'familyName': user_data.get('attributes', {}).get('familyName', ''),
                                'givenName': user_data.get('attributes', {}).get('givenName', '')
                            }
                            cache_user_from_api(fetched_id, cache_info)
                            
                            print(f"[MemberEditor.refresh] メール検索成功: row={idx} ID={fetched_id} NAME={fetched_name} MAIL={fetched_email}")
                            logger.info(f"[MemberEditor.refresh] メール検索成功: row={idx} ID={fetched_id} NAME={fetched_name} MAIL={fetched_email}")
                            updated += 1
                            continue
                        else:
                            logger.warning(f"[MemberEditor.refresh] メール検索結果なし: row={idx} MAIL={email}")
                    except Exception as e:
                        logger.error(f"[MemberEditor.refresh] メール検索エラー: row={idx} MAIL={email} ERROR={e}")
                
                # user_idがある場合は通常のID検索
                if user_id:
                    # キャッシュから既存のメール取得（空値時の保持用）
                    cached = get_cached_user(user_id)
                    cached_mail = cached.get('emailAddress', '') if cached else ''
                    
                    details = fetch_user_details_by_id(user_id, bearer_token)
                    if details:
                        name = details.get('userName', '')
                        mail = details.get('emailAddress', '')
                        
                        # 氏名は必ず更新（必須項目）
                        if name:
                            member['userName'] = name
                        else:
                            logger.warning(f"[MemberEditor.refresh] 氏名取得失敗: row={idx} ID={user_id}")
                        
                        # メールは空値の場合キャッシュの既存値を維持
                        if mail:
                            member['email'] = mail
                            # キャッシュにも保存（新しいメール）
                            cache_user_from_api(user_id, details)
                        else:
                            # メールが空の場合はキャッシュの既存メールを維持
                            if cached_mail:
                                logger.info(f"[MemberEditor.refresh] メール空値→キャッシュ維持: row={idx} ID={user_id} CACHED_MAIL={cached_mail}")
                                member['email'] = cached_mail
                            # キャッシュには氏名だけ更新（メールは既存のまま）
                            if cached:
                                cached['userName'] = name
                                cache_user_from_api(user_id, cached)
                            else:
                                # キャッシュがない場合は氏名だけで保存
                                cache_user_from_api(user_id, {'userName': name, 'emailAddress': member.get('email', '')})
                        
                        # シェルへ確実に出力
                        final_mail = member.get('email', '')
                        print(f"[MemberEditor.refresh] row={idx} ID={user_id} NAME={name} MAIL={final_mail}")
                        logger.info(f"[MemberEditor.refresh] row={idx} ID={user_id} NAME={name} MAIL={final_mail}")
                        updated += 1
            
            # 再描画
            self.populate_table()
            QMessageBox.information(self, "更新完了", f"{updated}件のメンバー情報を更新しました。")
        except Exception as e:
            QMessageBox.critical(self, "更新エラー", f"手動更新中にエラーが発生しました:\n{e}")
    
    def _apply_table_style(self):
        """テーブルスタイルを適用"""
        # Paletteを使って背景色を強制設定
        from qt_compat.gui import QPalette
        palette = self.table.palette()
        palette.setColor(QPalette.Base, get_qcolor(ThemeKey.TABLE_BACKGROUND))
        palette.setColor(QPalette.AlternateBase, get_qcolor(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE))
        palette.setColor(QPalette.Text, get_qcolor(ThemeKey.TABLE_ROW_TEXT))
        self.table.setPalette(palette)
        
        # QSSでその他のスタイルを設定
        self.table.setStyleSheet(f"""
            QTableWidget {{
                selection-background-color: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_SELECTED)};
                selection-color: {get_color(ThemeKey.TABLE_ROW_TEXT_SELECTED)};
                gridline-color: {get_color(ThemeKey.TABLE_BORDER)};
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QHeaderView::section {{
                background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
                color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};
                padding: 4px;
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
                font-weight: bold;
            }}
        """)
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        self._apply_table_style()
        if hasattr(self, 'save_button'):
            self.save_button.setStyleSheet(
                f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; "
                "font-weight: bold; padding: 8px;"
            )

        # 削除ボタン（×）のスタイルを再適用
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 5)
            if isinstance(w, QPushButton) and w.text() == "×":
                w.setStyleSheet(
                    f"""
                        QPushButton {{
                            background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                            color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                            font-weight: bold;
                            font-size: 14px;
                            border: none;
                            border-radius: 3px;
                            padding: 2px;
                        }}
                        QPushButton:hover {{
                            background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
                        }}
                        QPushButton:pressed {{
                            background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
                        }}
                    """
                )
        self.update()
    
    def load_email_to_user_map(self):
        """subGroup.jsonからメールアドレス→ユーザー情報マッピングを作成"""
        try:
            subgroup_json_path = get_dynamic_file_path("output/rde/data/subGroup.json")
            if os.path.exists(subgroup_json_path):
                with open(subgroup_json_path, 'r', encoding='utf-8') as f:
                    subgroup_data = json.load(f)
                
                # includedセクションからユーザー情報を抽出
                included_items = subgroup_data.get("included", [])
                for item in included_items:
                    if item.get("type") == "user":
                        attr = item.get("attributes", {})
                        email = attr.get('emailAddress', '').strip()
                        if email:
                            self.email_to_user_map[email] = {
                                'id': item.get('id', ''),
                                'userName': attr.get('userName', ''),
                                'organizationName': attr.get('organizationName', '')
                            }
                
                logger.debug("メールアドレスマップ読み込み完了: %s件", len(self.email_to_user_map))
        except Exception as e:
            logger.warning("subGroup.json読み込みエラー: %s", e)
    
    def load_members(self):
        """rde-member.txtからメンバー読み込み"""
        self.members = []
        
        if not os.path.exists(self.member_path):
            logger.info("rde-member.txt not found - creating new")
            return
        
        try:
            with open(self.member_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith('#'):
                    # コメント行の場合、次の行に関連データがあるかチェック
                    if line.startswith('# user_id:'):
                        # 次のメンバーデータ用のメタ情報
                        pass
                    continue
                
                # セミコロンで終わる場合は削除
                if line.endswith(';'):
                    line = line[:-1]
                
                parts = [x.strip() for x in line.split(',')]
                if len(parts) >= 4:
                    email = parts[0]
                    role_num = parts[1]
                    can_create = parts[2] == '1'
                    can_edit = parts[3] == '1'
                    
                    # 前のコメント行からuser_id/userNameを探す
                    user_id = ''
                    user_name = ''
                    if i > 0:
                        prev_line = lines[i-1].strip()
                        if prev_line.startswith('# user_id:'):
                            # 形式: # user_id: xxx | userName: yyy
                            parts_meta = prev_line[10:].split('|')
                            if len(parts_meta) >= 1:
                                user_id = parts_meta[0].strip()
                            if len(parts_meta) >= 2 and parts_meta[1].strip().startswith('userName:'):
                                user_name = parts_meta[1].replace('userName:', '').strip()
                    
                    self.members.append({
                        'email': email,
                        'role': 'OWNER' if role_num == '1' else 'ASSISTANT',
                        'canCreateDatasets': can_create,
                        'canEditMembers': can_edit,
                        'user_id': user_id,
                        'userName': user_name
                    })
            
            logger.debug("rde-member.txt読み込み完了: %s件", len(self.members))
            self.populate_table()
            
        except Exception as e:
            QMessageBox.warning(self, "読み込みエラー", f"rde-member.txtの読み込みに失敗しました:\n{str(e)}")
    
    def populate_table(self):
        """テーブルにデータを表示"""
        self.table.setRowCount(len(self.members))
        
        for row, member in enumerate(self.members):
            # 氏名（キャッシュ優先、なければmember内のuserName、さらになければメール→ユーザ情報マップ、最終手段としてAPI）
            user_name = member.get('userName', '')
            user_id = member.get('user_id', '')
            email_value = member.get('email', '').strip()

            # デバッグログ: 入力構造確認
            try:
                logger.info(
                    "[MemberEditor.populate] row=%s, keys=%s, ID=%s, NAME=%s, MAIL=%s",
                    row,
                    sorted(list(member.keys())),
                    (user_id or ''),
                    (user_name or ''),
                    (email_value or '')
                )
            except Exception:
                pass
            
            # user_idがない場合はemail_to_user_mapから取得試行
            if not user_id:
                user_info = self.email_to_user_map.get(member['email'], {})
                user_id = user_info.get('id', '')
                if not user_name:
                    user_name = user_info.get('userName', '')
            
            # キャッシュから取得試行
            if (not user_name or user_name == member['email']) and user_id:
                try:
                    from ..core.user_cache_manager import get_cached_user, cache_user_from_api
                    cached = get_cached_user(user_id)
                    if cached:
                        user_name = cached.get('userName', '')
                        logger.debug(f"キャッシュからユーザー名取得: {user_id} → {user_name}")
                    else:
                        # キャッシュにない場合はAPI経由取得を試みる
                        from ..core.subgroup_api_helper import fetch_user_details_by_id
                        from core.bearer_token_manager import BearerTokenManager
                        bearer_token = BearerTokenManager.get_valid_token()
                        if bearer_token:
                            user_details = fetch_user_details_by_id(user_id, bearer_token)
                            if user_details:
                                user_name = user_details.get('userName', '')
                                # キャッシュに保存
                                cache_user_from_api(user_id, user_details)
                                logger.debug(f"APIからユーザー名取得&キャッシュ保存: {user_id} → {user_name}")
                except Exception as e:
                    logger.debug(f"ユーザー名取得失敗（ID: {user_id}）: {e}")

            # デバッグログ: 補完後の状態
            try:
                logger.info(
                    "[MemberEditor.populate] after-complement row=%s, ID=%s, NAME=%s, MAIL=%s",
                    row,
                    (user_id or ''),
                    (user_name or ''),
                    (email_value or '')
                )
            except Exception:
                pass
            
            # 氏名・メールが欠損している場合はAPIで補完しキャッシュ更新
            try:
                if (not user_name or user_name.strip() == '') or (not email_value or email_value.strip() == ''):
                    from ..core.user_cache_manager import get_cached_user, cache_user_from_api
                    cached = None
                    if user_id:
                        cached = get_cached_user(user_id)
                    if cached:
                        # キャッシュから補完
                        user_name = user_name or cached.get('userName', '')
                        email_value = email_value or cached.get('emailAddress', '')
                        logger.debug(f"キャッシュ補完: {user_id} → name='{user_name}', email='{email_value}'")
                    else:
                        # APIから再取得
                        from ..core.subgroup_api_helper import fetch_user_details_by_id
                        from core.bearer_token_manager import BearerTokenManager
                        bearer_token = BearerTokenManager.get_valid_token()
                        if bearer_token and user_id:
                            user_details = fetch_user_details_by_id(user_id, bearer_token)
                            if user_details:
                                fetched_name = user_details.get('userName', '')
                                fetched_email = user_details.get('emailAddress', '')
                                if not user_name:
                                    user_name = fetched_name
                                if not email_value:
                                    email_value = fetched_email
                                # キャッシュ保存
                                cache_user_from_api(user_id, user_details)
                                # ローカルマップ更新
                                if email_value:
                                    self.email_to_user_map[email_value] = {
                                        'id': user_id,
                                        'userName': user_name,
                                        'organizationName': user_details.get('organizationName', '')
                                    }
                                # メンバー配列も更新
                                member['userName'] = user_name
                                member['email'] = email_value
                                logger.debug(f"API補完&キャッシュ更新: {user_id} → name='{user_name}', email='{email_value}'")
            except Exception as e:
                logger.debug(f"氏名/メール補完失敗（ID: {user_id}）: {e}")

            name_item = QTableWidgetItem(user_name)
            self.table.setItem(row, 0, name_item)

            # メールアドレス
            email_item = QTableWidgetItem(email_value or member['email'])
            self.table.setItem(row, 1, email_item)
            
            # 初期ロール
            role_item = QTableWidgetItem(member['role'])
            self.table.setItem(row, 2, role_item)
            
            # データセット作成
            create_item = QTableWidgetItem("○" if member['canCreateDatasets'] else "×")
            create_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, create_item)
            
            # メンバー編集
            edit_item = QTableWidgetItem("○" if member['canEditMembers'] else "×")
            edit_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, edit_item)
            
            # 削除ボタン
            delete_button = QPushButton("×")
            delete_button.setMaximumWidth(40)
            delete_button.setStyleSheet(
                f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                        font-weight: bold;
                        font-size: 14px;
                        border: none;
                        border-radius: 3px;
                        padding: 2px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
                    }}
                    QPushButton:pressed {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
                    }}
                """
            )
            delete_button.clicked.connect(lambda checked, r=row: self.delete_member(r))
            self.table.setCellWidget(row, 5, delete_button)
    
    def add_member(self):
        """メンバーを追加"""
        email = self.email_input.text().strip()
        
        if not email:
            QMessageBox.warning(self, "入力エラー", "メールアドレスを入力してください。")
            return
        
        # メールアドレス形式チェック
        if '@' not in email:
            QMessageBox.warning(self, "入力エラー", "有効なメールアドレスを入力してください。")
            return
        
        # 重複チェック
        if any(m['email'] == email for m in self.members):
            QMessageBox.warning(self, "重複エラー", "このメールアドレスは既に登録されています。")
            return
        
        # subGroup.jsonに存在するかチェック
        user_found = False
        if email in self.email_to_user_map:
            user_found = True
            logger.debug("メールアドレス %s は実施機関メンバーに存在します", email)
        else:
            # APIで存在確認
            logger.debug("メールアドレス %s はローカルに存在しないため、APIで検証します", email)
            
            from core.bearer_token_manager import BearerTokenManager
            bearer_token = BearerTokenManager.get_valid_token()
            
            if bearer_token:
                import urllib.parse
                from net.http_helpers import proxy_get
                
                try:
                    # APIでメールアドレス検索
                    encoded_email = urllib.parse.quote_plus(email)
                    filter_param = urllib.parse.quote('filter[emailAddress]', safe='')
                    url = f"https://rde-user-api.nims.go.jp/users?{filter_param}={encoded_email}"
                    
                    headers = {
                        'Authorization': f'Bearer {bearer_token}',
                        'Accept': 'application/vnd.api+json',
                        'Content-Type': 'application/json'
                    }
                    
                    response = proxy_get(url, headers=headers)
                    response.raise_for_status()
                    
                    data = response.json()
                    users = data.get('data', [])
                    
                    if users:
                        user_found = True
                        user_data = users[0]
                        user_id = user_data.get('id', '')
                        user_name = user_data.get('attributes', {}).get('userName', 'Unknown')
                        logger.debug("APIでユーザー発見: %s -> %s (ID: %s)", email, user_name, user_id)
                        
                        # キャッシュに保存
                        try:
                            from ..core.user_cache_manager import cache_user
                            cache_info = {
                                'userName': user_name,
                                'emailAddress': email,
                                'organizationName': user_data.get('attributes', {}).get('organizationName', ''),
                                'familyName': user_data.get('attributes', {}).get('familyName', ''),
                                'givenName': user_data.get('attributes', {}).get('givenName', '')
                            }
                            cache_user(user_id, cache_info, source="member_editor")
                            logger.debug(f"カスタムメンバー追加時にキャッシュ保存: {user_id} ({user_name})")
                            
                            # email_to_user_mapにも追加
                            self.email_to_user_map[email] = {
                                'id': user_id,
                                'userName': user_name,
                                'organizationName': cache_info['organizationName']
                            }
                        except Exception as cache_err:
                            logger.warning(f"キャッシュ保存失敗: {cache_err}")
                    else:
                        logger.warning("APIでもユーザーが見つかりません: %s", email)
                        
                except Exception as api_error:
                    logger.error("API検証エラー (%s): %s", email, api_error)
            else:
                logger.warning("Bearer token未取得のため、API検証をスキップ")
            
            # ユーザーが見つからない場合は確認ダイアログ
            if not user_found:
                reply = QMessageBox.question(
                    self,
                    "確認",
                    f"メールアドレス '{email}' はRDEシステムに登録されていないようです。\n"
                    "（実施機関メンバーおよびAPI検索で見つかりませんでした）\n\n"
                    "それでも追加しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
        
        # メンバー追加
        role = self.role_combo.currentText()
        can_create = self.can_create_cb.isChecked()
        can_edit = self.can_edit_cb.isChecked()
        
        # email_to_user_mapからuser_idとuserNameを取得
        user_info = self.email_to_user_map.get(email, {})
        user_id = user_info.get('id', '')
        user_name = user_info.get('userName', '')
        
        self.members.append({
            'email': email,
            'role': role,
            'canCreateDatasets': can_create,
            'canEditMembers': can_edit,
            'user_id': user_id,  # 追加
            'userName': user_name  # 追加
        })
        
        # 入力フィールドクリア
        self.email_input.clear()
        
        # テーブル再描画
        self.populate_table()
    
    def delete_member(self, row):
        """メンバーを削除"""
        if 0 <= row < len(self.members):
            email = self.members[row]['email']
            reply = QMessageBox.question(
                self,
                "削除確認",
                f"メンバー '{email}' を削除しますか?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                del self.members[row]
                self.populate_table()
    
    def save_members(self):
        """メンバーをrde-member.txtに保存"""
        try:
            # ディレクトリが存在しない場合は作成
            os.makedirs(INPUT_DIR, exist_ok=True)
            
            # ファイル内容生成
            lines = ["# mailaddress , role(1=OWNER,2=ASSISTANT),canCreateDatasets (1=True) , canEditMembers(1=True),;"]
            
            for member in self.members:
                role_num = '1' if member['role'] == 'OWNER' else '2'
                can_create = '1' if member['canCreateDatasets'] else '0'
                can_edit = '1' if member['canEditMembers'] else '0'
                
                # user_idとuserNameがあればコメント行として追加
                user_id = member.get('user_id', '')
                user_name = member.get('userName', '')
                if user_id or user_name:
                    meta_line = f"# user_id: {user_id} | userName: {user_name}"
                    lines.append(meta_line)
                
                line = f"{member['email']},{role_num},{can_create},{can_edit};"
                lines.append(line)
            
            # ファイル書き込み
            with open(self.member_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            QMessageBox.information(self, "保存完了", f"rde-member.txtを保存しました。\n{len(self.members)}件のメンバーを登録しました。")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"ファイルの保存に失敗しました:\n{str(e)}")
