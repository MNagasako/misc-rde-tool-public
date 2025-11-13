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
        info_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info_label)
        
        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "メールアドレス", "ロール", "データセット作成", "メンバー編集", "操作"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
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
        
        layout.addLayout(add_layout)
        
        # ボタン
        button_layout = QHBoxLayout()
        
        save_button = QPushButton("保存")
        save_button.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; padding: 8px;")
        save_button.clicked.connect(self.save_members)
        button_layout.addWidget(save_button)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
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
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
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
                    
                    self.members.append({
                        'email': email,
                        'role': 'OWNER' if role_num == '1' else 'ASSISTANT',
                        'canCreateDatasets': can_create,
                        'canEditMembers': can_edit
                    })
            
            logger.debug("rde-member.txt読み込み完了: %s件", len(self.members))
            self.populate_table()
            
        except Exception as e:
            QMessageBox.warning(self, "読み込みエラー", f"rde-member.txtの読み込みに失敗しました:\n{str(e)}")
    
    def populate_table(self):
        """テーブルにデータを表示"""
        self.table.setRowCount(len(self.members))
        
        for row, member in enumerate(self.members):
            # メールアドレス
            email_item = QTableWidgetItem(member['email'])
            self.table.setItem(row, 0, email_item)
            
            # ロール
            role_item = QTableWidgetItem(member['role'])
            self.table.setItem(row, 1, role_item)
            
            # データセット作成
            create_item = QTableWidgetItem("○" if member['canCreateDatasets'] else "×")
            create_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, create_item)
            
            # メンバー編集
            edit_item = QTableWidgetItem("○" if member['canEditMembers'] else "×")
            edit_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, edit_item)
            
            # 削除ボタン
            delete_button = QPushButton("削除")
            delete_button.clicked.connect(lambda checked, r=row: self.delete_member(r))
            self.table.setCellWidget(row, 4, delete_button)
    
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
                        user_name = users[0].get('attributes', {}).get('userName', 'Unknown')
                        logger.debug("APIでユーザー発見: %s -> %s", email, user_name)
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
        
        self.members.append({
            'email': email,
            'role': role,
            'canCreateDatasets': can_create,
            'canEditMembers': can_edit
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
                
                line = f"{member['email']},{role_num},{can_create},{can_edit};"
                lines.append(line)
            
            # ファイル書き込み
            with open(self.member_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            QMessageBox.information(self, "保存完了", f"rde-member.txtを保存しました。\n{len(self.members)}件のメンバーを登録しました。")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"ファイルの保存に失敗しました:\n{str(e)}")
