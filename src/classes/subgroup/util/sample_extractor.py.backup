"""
サブグループ関連試料抽出機能
"""

import os
import json
import webbrowser
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, 
    QListWidgetItem, QPushButton, QMessageBox, QTextEdit, QComboBox, QCompleter,
    QGroupBox
)
from PyQt5.QtCore import Qt
from config.common import get_samples_dir_path, SUBGROUP_JSON_PATH


class RelatedSamplesDialog(QDialog):
    """関連試料表示ダイアログ"""
    
    def __init__(self, subgroup_id, parent=None):
        super().__init__(parent)
        self.subgroup_id = subgroup_id
        self.samples_data = []
        self.all_subgroups = []  # 全サブグループリスト
        self.filtered_subgroups = []  # フィルタ済みサブグループリスト
        self.current_sharing_groups = []  # 選択中試料の共有グループリスト
        self.init_ui()
        self.load_samples()
        self.load_subgroups()
    
    def init_ui(self):
        """UI初期化"""
        self.setWindowTitle(f"関連試料一覧 - サブグループID: {self.subgroup_id}")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout()
        
        # タイトル
        title_label = QLabel(f"サブグループ「{self.subgroup_id}」の関連試料")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
        layout.addWidget(title_label)
        
        # 試料リスト
        self.sample_list = QListWidget()
        self.sample_list.itemDoubleClicked.connect(self.open_sample_link)
        layout.addWidget(self.sample_list)
        
        # 詳細表示エリア
        detail_label = QLabel("試料詳細:")
        detail_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(detail_label)
        
        self.detail_text = QTextEdit()
        self.detail_text.setMaximumHeight(150)
        layout.addWidget(self.detail_text)
        
        # 試料共有グループ設定エリア
        self._create_sharing_group_section(layout)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        self.open_link_btn = QPushButton("ブラウザで開く")
        self.open_link_btn.clicked.connect(self.open_selected_sample_link)
        self.open_link_btn.setEnabled(False)
        button_layout.addWidget(self.open_link_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # リスト選択変更イベント
        self.sample_list.itemSelectionChanged.connect(self.on_selection_changed)
    
    def _create_sharing_group_section(self, layout):
        """試料共有グループ設定セクションの作成"""
        group_box = QGroupBox("試料共有グループ設定")
        group_layout = QVBoxLayout()
        
        # フィルター部
        filter_layout = QHBoxLayout()
        filter_label = QLabel("表示フィルタ:")
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("OWNER", "owner")
        self.filter_combo.addItem("OWNER+ASSISTANT", "both") 
        self.filter_combo.addItem("ASSISTANT", "assistant")
        self.filter_combo.addItem("MEMBER", "member")
        self.filter_combo.addItem("AGENT", "agent")
        self.filter_combo.addItem("VIEWER", "viewer")
        self.filter_combo.addItem("フィルタ無し", "none")
        self.filter_combo.setCurrentIndex(0)
        self.filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()
        group_layout.addLayout(filter_layout)
        
        # === 共有グループ設定用 ===
        set_label = QLabel("共有グループを追加:")
        group_layout.addWidget(set_label)
        
        self.subgroup_combo = QComboBox()
        self.subgroup_combo.setMinimumWidth(400)
        self.subgroup_combo.setEditable(True)
        self.subgroup_combo.setInsertPolicy(QComboBox.NoInsert)
        self.subgroup_combo.setMaxVisibleItems(12)
        self.subgroup_combo.view().setMinimumHeight(240)
        
        # 補完機能を追加
        completer = QCompleter()
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.subgroup_combo.setCompleter(completer)
        
        group_layout.addWidget(self.subgroup_combo)
        
        self.set_sharing_group_btn = QPushButton("共有グループを設定")
        self.set_sharing_group_btn.clicked.connect(self.set_sharing_group)
        self.set_sharing_group_btn.setEnabled(False)
        group_layout.addWidget(self.set_sharing_group_btn)
        
        # === 共有グループ削除用 ===
        delete_label = QLabel("共有グループを削除:")
        delete_label.setStyleSheet("margin-top: 15px;")
        group_layout.addWidget(delete_label)
        
        self.delete_subgroup_combo = QComboBox()
        self.delete_subgroup_combo.setMinimumWidth(400)
        self.delete_subgroup_combo.setEditable(False)
        self.delete_subgroup_combo.setMaxVisibleItems(12)
        self.delete_subgroup_combo.view().setMinimumHeight(240)
        group_layout.addWidget(self.delete_subgroup_combo)
        
        self.delete_sharing_group_btn = QPushButton("共有グループを削除")
        self.delete_sharing_group_btn.clicked.connect(self.delete_sharing_group)
        self.delete_sharing_group_btn.setEnabled(False)
        group_layout.addWidget(self.delete_sharing_group_btn)
        
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
    
    def load_samples(self):
        """サンプルデータの読み込み"""
        samples_dir = get_samples_dir_path()
        sample_file = os.path.join(samples_dir, f"{self.subgroup_id}.json")
        
        if not os.path.exists(sample_file):
            self.show_error(f"サンプルファイルが見つかりません: {sample_file}")
            return
        
        try:
            with open(sample_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.samples_data = data.get('data', [])
            self.populate_sample_list()
            
        except Exception as e:
            self.show_error(f"サンプルファイルの読み込みエラー: {str(e)}")
    
    def populate_sample_list(self):
        """サンプルリストの表示"""
        self.sample_list.clear()
        
        if not self.samples_data:
            item = QListWidgetItem("関連試料が見つかりません")
            item.setFlags(Qt.NoItemFlags)
            self.sample_list.addItem(item)
            return
        
        for sample in self.samples_data:
            sample_id = sample.get('id', 'Unknown ID')
            attributes = sample.get('attributes', {})
            
            # 試料名の取得
            names = attributes.get('names', [])
            sample_name = names[0] if names else "名前なし"
            
            # 表示テキストの作成
            display_text = f"ID: {sample_id} | 名前: {sample_name}"
            
            # リストアイテムの作成
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, sample)
            self.sample_list.addItem(item)
        
        # 件数表示
        total_count = len(self.samples_data)
        self.setWindowTitle(f"関連試料一覧 ({total_count}件) - サブグループID: {self.subgroup_id}")
    
    def on_selection_changed(self):
        """リスト選択変更時の処理"""
        current_item = self.sample_list.currentItem()
        
        if not current_item:
            self.detail_text.clear()
            self.open_link_btn.setEnabled(False)
            self.set_sharing_group_btn.setEnabled(False)
            self.delete_sharing_group_btn.setEnabled(False)
            self.delete_subgroup_combo.clear()
            return
        
        sample_data = current_item.data(Qt.UserRole)
        if not sample_data:
            self.detail_text.clear()
            self.open_link_btn.setEnabled(False)
            self.set_sharing_group_btn.setEnabled(False)
            self.delete_sharing_group_btn.setEnabled(False)
            self.delete_subgroup_combo.clear()
            return
        
        # 詳細情報の表示
        self.display_sample_details(sample_data)
        self.open_link_btn.setEnabled(True)
        
        # 試料の共有グループ情報を取得
        self.load_sample_sharing_groups(sample_data.get('id'))
        
        # サブグループが選択されている場合のみボタンを有効化
        has_subgroup_selected = (self.subgroup_combo.currentData() is not None and 
                                  self.subgroup_combo.currentText() != "該当するサブグループがありません")
        self.set_sharing_group_btn.setEnabled(has_subgroup_selected)
        
        # 削除ボタンは共有グループが存在する場合のみ有効化
        has_sharing_groups = self.delete_subgroup_combo.count() > 0
        self.delete_sharing_group_btn.setEnabled(has_sharing_groups)
    
    def display_sample_details(self, sample_data):
        """試料詳細情報の表示"""
        sample_id = sample_data.get('id', 'Unknown ID')
        attributes = sample_data.get('attributes', {})
        
        details = []
        details.append(f"サンプルID: {sample_id}")
        
        # 名前
        names = attributes.get('names', [])
        if names:
            details.append(f"名前: {', '.join(names)}")
        
        # 説明
        description = attributes.get('description')
        if description:
            details.append(f"説明: {description}")
        
        # 組成
        composition = attributes.get('composition')
        if composition:
            details.append(f"組成: {composition}")
        
        # リンクURL
        sample_url = self.generate_sample_url(sample_id)
        details.append(f"\nRDEリンク: {sample_url}")
        
        self.detail_text.setPlainText('\n'.join(details))
    
    def generate_sample_url(self, sample_id):
        """サンプルURLの生成"""
        return f"https://rde-material.nims.go.jp/samples/samples/{sample_id}"
    
    def open_sample_link(self, item):
        """リストアイテムダブルクリック時の処理"""
        sample_data = item.data(Qt.UserRole)
        if sample_data:
            sample_id = sample_data.get('id')
            if sample_id:
                self.open_browser_link(sample_id)
    
    def open_selected_sample_link(self):
        """選択されたサンプルのリンクを開く"""
        current_item = self.sample_list.currentItem()
        if not current_item:
            return
        
        sample_data = current_item.data(Qt.UserRole)
        if sample_data:
            sample_id = sample_data.get('id')
            if sample_id:
                self.open_browser_link(sample_id)
    
    def open_browser_link(self, sample_id):
        """ブラウザでリンクを開く"""
        url = self.generate_sample_url(sample_id)
        try:
            webbrowser.open(url)
            print(f"[INFO] ブラウザでリンクを開きました: {url}")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ブラウザでリンクを開けませんでした: {str(e)}")
    
    def show_error(self, message):
        """エラーメッセージの表示"""
        QMessageBox.warning(self, "エラー", message)
        
        # リストにエラーメッセージを表示
        self.sample_list.clear()
        item = QListWidgetItem(f"エラー: {message}")
        item.setFlags(Qt.NoItemFlags)
        self.sample_list.addItem(item)
    
    def load_subgroups(self):
        """サブグループリストの読み込み"""
        if not os.path.exists(SUBGROUP_JSON_PATH):
            print(f"[WARNING] サブグループJSONファイルが見つかりません: {SUBGROUP_JSON_PATH}")
            return
        
        try:
            with open(SUBGROUP_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # subgroup.jsonの構造: data=親グループ(PROJECT), included=子サブグループ配列
            # 子サブグループのリストを取得
            self.all_subgroups = data.get('included', [])
            
            # includedがない場合は空リスト
            if not self.all_subgroups:
                print(f"[WARNING] サブグループ(included)が見つかりません")
                self.all_subgroups = []
            else:
                print(f"[INFO] サブグループを {len(self.all_subgroups)} 件読み込みました")
                
                # データ構造の確認（デバッグ用）
                if len(self.all_subgroups) > 0:
                    first_item = self.all_subgroups[0]
                    if isinstance(first_item, dict):
                        print(f"[DEBUG] サブグループの構造OK: type={first_item.get('type')}, name={first_item.get('attributes', {}).get('name', 'N/A')}")
                    else:
                        print(f"[WARNING] サブグループのデータ型が不正: {type(first_item)}")
            
            # 初期フィルタリング実行
            self.on_filter_changed()
            
        except Exception as e:
            print(f"[ERROR] サブグループ読み込みエラー: {str(e)}")
            import traceback
            traceback.print_exc()
            self.all_subgroups = []
    
    def on_filter_changed(self):
        """フィルタ変更時の処理"""
        filter_value = self.filter_combo.currentData()
        
        # フィルタリング実行
        self.filtered_subgroups = self._filter_subgroups(filter_value)
        
        # コンボボックスを更新
        self._populate_subgroup_combo()
    
    def _filter_subgroups(self, filter_value):
        """サブグループのフィルタリング（subgroup_edit_widget.pyと同等）"""
        if filter_value == "none":
            return self.all_subgroups.copy()
        
        current_user_id = self._get_current_user_id()
        if not current_user_id:
            print("[WARNING] ユーザーIDを取得できませんでした。フィルタなしで表示します。")
            return self.all_subgroups.copy()
        
        filtered = []
        for group in self.all_subgroups:
            # データ型チェック
            if not isinstance(group, dict):
                print(f"[WARNING] グループデータが辞書ではありません: type={type(group)}, value={group}")
                continue
            
            if self._should_include_group(group, filter_value, current_user_id):
                filtered.append(group)
        
        return filtered
    
    def _should_include_group(self, group, filter_value, current_user_id):
        """グループがフィルター条件に合致するかチェック（subgroup_edit_widget.pyと同等）"""
        attributes = group.get('attributes', {})
        if not isinstance(attributes, dict):
            print(f"[WARNING] attributes が辞書ではありません: type={type(attributes)}")
            return False
        
        roles = attributes.get('roles', [])
        user_roles = []
        for role in roles:
            if role.get("userId") == current_user_id:
                user_roles.append(role.get("role", ""))
        
        if filter_value == "owner" and "OWNER" in user_roles:
            return True
        elif filter_value == "both" and ("OWNER" in user_roles or "ASSISTANT" in user_roles):
            return True
        elif filter_value == "assistant" and "ASSISTANT" in user_roles:
            return True
        elif filter_value == "member" and "MEMBER" in user_roles:
            return True
        elif filter_value == "agent" and "AGENT" in user_roles:
            return True
        elif filter_value == "viewer" and "VIEWER" in user_roles:
            return True
        
        return False
    
    def _get_current_user_id(self):
        """現在のユーザーIDを取得（subgroup_edit_widget.pyと同等）"""
        try:
            from config.common import SELF_JSON_PATH
            with open(SELF_JSON_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("data", {}).get("id", "")
        except Exception as e:
            print(f"[DEBUG] ユーザーID取得エラー: {e}")
            return ""
    
    def _populate_subgroup_combo(self):
        """サブグループコンボボックスの更新（選択中サブグループを除外）"""
        self.subgroup_combo.clear()
        
        # 選択中のサブグループIDを除外
        excluded_subgroups = [group for group in self.filtered_subgroups 
                              if group.get('id') != self.subgroup_id]
        
        if not excluded_subgroups:
            self.subgroup_combo.addItem("該当するサブグループがありません", None)
            return
        
        # コンボボックスに追加
        display_texts = []
        for group in excluded_subgroups:
            # データ型チェック
            if not isinstance(group, dict):
                print(f"[WARNING] populate_subgroup_combo: グループデータが辞書ではありません: {type(group)}")
                continue
            
            group_id = group.get('id', '')
            attributes = group.get('attributes', {})
            if not isinstance(attributes, dict):
                print(f"[WARNING] populate_subgroup_combo: attributes が辞書ではありません")
                continue
            
            group_name = attributes.get('name', '名前なし')
            
            display_text = f"{group_name} (ID: {group_id})"
            self.subgroup_combo.addItem(display_text, group)
            display_texts.append(display_text)
        
        # 補完機能の更新
        completer = self.subgroup_combo.completer()
        if completer:
            from PyQt5.QtCore import QStringListModel
            completer.setModel(QStringListModel(display_texts))
    
    def load_sample_sharing_groups(self, sample_id):
        """試料の共有グループ情報を取得"""
        if not sample_id:
            self.delete_subgroup_combo.clear()
            return
        
        try:
            from classes.subgroup.core.subgroup_api_client import SubgroupApiClient
            api_client = SubgroupApiClient(self)
            
            # 試料詳細を取得（include=sharingGroups）
            sample_detail = api_client.get_sample_detail(sample_id)
            
            if not sample_detail:
                print(f"[WARNING] 試料詳細の取得に失敗しました: {sample_id}")
                self.delete_subgroup_combo.clear()
                return
            
            # 共有グループ情報を抽出
            included = sample_detail.get('included', [])
            sharing_groups = [item for item in included if item.get('type') == 'sharingGroup']
            
            self.current_sharing_groups = sharing_groups
            
            # 削除用コンボボックスに追加
            self.delete_subgroup_combo.clear()
            
            if not sharing_groups:
                self.delete_subgroup_combo.addItem("共有グループなし", None)
                print(f"[DEBUG] 試料 {sample_id} には共有グループが設定されていません")
                return
            
            for group in sharing_groups:
                group_id = group.get('id', '')
                group_name = group.get('attributes', {}).get('name', '名前なし')
                display_text = f"{group_name} (ID: {group_id})"
                self.delete_subgroup_combo.addItem(display_text, group)
            
            print(f"[DEBUG] 試料 {sample_id} の共有グループ: {len(sharing_groups)}件")
            
        except Exception as e:
            print(f"[ERROR] 共有グループ情報取得エラー: {e}")
            self.delete_subgroup_combo.clear()
            self.delete_subgroup_combo.addItem("取得エラー", None)
    
    def set_sharing_group(self):
        """試料に共有グループを設定"""
        # 選択された試料を取得
        current_item = self.sample_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "エラー", "試料が選択されていません")
            return
        
        sample_data = current_item.data(Qt.UserRole)
        if not sample_data:
            QMessageBox.warning(self, "エラー", "試料データが取得できません")
            return
        
        sample_id = sample_data.get('id')
        if not sample_id:
            QMessageBox.warning(self, "エラー", "試料IDが取得できません")
            return
        
        # 選択されたサブグループを取得
        selected_group = self.subgroup_combo.currentData()
        if not selected_group:
            QMessageBox.warning(self, "エラー", "サブグループが選択されていません")
            return
        
        group_id = selected_group.get('id', '')
        group_name = selected_group.get('attributes', {}).get('name', '')
        
        if not group_id or not group_name:
            QMessageBox.warning(self, "エラー", "サブグループIDまたは名前が取得できません")
            return
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self, 
            "確認", 
            f"試料「{sample_id}」に共有グループ「{group_name}」を設定しますか?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # API呼び出し
        from ..core.subgroup_api_client import SubgroupApiClient
        api_client = SubgroupApiClient(self)
        success, message = api_client.set_sample_sharing_group(sample_id, group_id, group_name)
        
        if success:
            QMessageBox.information(self, "成功", message)
            # 共有グループリストを再取得
            self.load_sample_sharing_groups(sample_id)
        else:
            QMessageBox.warning(self, "エラー", message)
    
    def delete_sharing_group(self):
        """試料から共有グループを削除"""
        # 選択された試料を取得
        current_item = self.sample_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "エラー", "試料が選択されていません")
            return
        
        sample_data = current_item.data(Qt.UserRole)
        if not sample_data:
            QMessageBox.warning(self, "エラー", "試料データが取得できません")
            return
        
        sample_id = sample_data.get('id')
        if not sample_id:
            QMessageBox.warning(self, "エラー", "試料IDが取得できません")
            return
        
        # 削除用コンボボックスから選択されたグループを取得
        selected_group = self.delete_subgroup_combo.currentData()
        if not selected_group:
            QMessageBox.warning(self, "エラー", "削除する共有グループが選択されていません")
            return
        
        group_id = selected_group.get('id', '')
        group_name = selected_group.get('attributes', {}).get('name', '')
        
        if not group_id:
            QMessageBox.warning(self, "エラー", "サブグループIDが取得できません")
            return
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self, 
            "確認", 
            f"試料「{sample_id}」から共有グループ「{group_name}」を削除しますか?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # API呼び出し
        from ..core.subgroup_api_client import SubgroupApiClient
        api_client = SubgroupApiClient(self)
        success, message = api_client.delete_sample_sharing_group(sample_id, group_id)
        
        if success:
            QMessageBox.information(self, "成功", message)
            # 共有グループリストを再取得
            self.load_sample_sharing_groups(sample_id)
        else:
            QMessageBox.warning(self, "エラー", message)


def show_related_samples_dialog(subgroup_id, parent=None):
    """関連試料ダイアログの表示"""
    if not subgroup_id:
        QMessageBox.warning(parent, "エラー", "サブグループIDが指定されていません。")
        return
    
    dialog = RelatedSamplesDialog(subgroup_id, parent)
    dialog.exec_()
